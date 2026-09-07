# -*- coding: utf-8 -*-
"""SOZ.CB(관광 가이드 지도)에 한글 지도 라벨을 주입한다.

라벨 이미지는 **typelet 이 만든다** — `compose_file(project, member, specs)` 가
erased 베이스(핀·마커 보존) 위에 한글 텍스트를 얹은 최종 이미지를 돌려준다
(모드: 기본 overlay = erased+텍스트, text-only 는 blank 캔버스+텍스트). 이 모듈은
그 이미지를 **게임 텍스처(dds)에 넣는 일만** 한다:

  * 글리프 지도 : 라벨이 전용 아틀라스를 쓰면 빈 공간에 조각으로 패킹하고 픽처의
                 blit 을 새 위치로 재작성한다. 한 장이 차면 다음 장으로 흘려담는다.
  * 래스터 지도 : 라벨이 베이스 맵 텍스처를 공유하면(맵 위에 구워진 라벨) 그
                 blit 영역을 erased+한글로 덮어쓴다(.SET 불변, 맵 보존).

pic#0(베이스 맵 위 라벨=철도명 등)은 항상 래스터로 처리한다 — 글리프로 옮기면
베이스 맵 텍스처가 비어 맵이 소멸한다.

색은 감축하지 않는다(맵 아트 보존). 라벨이 닿은 LZSS 청크만 재인코딩하고 나머지
청크는 원본 바이트 그대로 둔다(encode_dds_mc). 그래도 원본 슬롯을 넘으면
`relocate.py` 가 아니라 `disc` 재배치로 슬롯을 넓힌다(soz_relayout 참조).
"""
import hashlib
import json
import os
import pickle
import struct
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from kitae.core.cab import Cab
from kitae.core import image as IM
from kitae.core.clss import parse
from kitae.core.enc2 import compress, decompress


# ───────────────────────────── typelet 렌더 ─────────────────────────────
def load_composer(jaguk_json, use_cache=True, typelet_root=None):
    """typelet 프로젝트를 열고 `compose(member_relative) -> PIL.Image|None` 반환.

    compose 는 그 멤버의 번역 행들을 모아 compose_file 로 최종 이미지를 만든다
    (erased 베이스 + 한글, 모드 반영). 게임 주입은 이 이미지만 소비한다.

    렌더는 멤버당 ~1s 로 느리므로, 결과를 typelet 산출 위치(images/injected/)에
    write-through 캐시한다. use_cache 면 이미 있는 PNG 를 로드(빠름) — 재개 가능.
    번역이 바뀌면 injected/ 를 지우고 다시 굽는다(또는 use_cache=False).

    typelet_root: type-lettering 코드 패키지 경로. 설치본이면 None(=cfg.typelet_root
    가 None 을 준다). 절대경로를 코드에 박지 않고 호출측(cfg)에서 넘긴다.
    """
    import sys
    if typelet_root and typelet_root not in sys.path:
        sys.path.insert(0, typelet_root)
    try:
        from typelet import config as tconfig, render as R, ledger as ledgermod
        from typelet.render import safe_path
    except ImportError as e:
        raise RuntimeError(
            "type-lettering(jaguk) 를 찾을 수 없습니다. `pip install -e` 로 설치하거나 "
            "kitae.config.json 의 paths.typelet 에 체크아웃 경로를 지정하세요."
        ) from e

    project = tconfig.load_path(Path(jaguk_json))
    data = ledgermod.load(project)
    styles = ledgermod.styles_map(data)
    all_rows = ledgermod.flat_rows(data)
    terms = ledgermod.load_terms(project, data)
    if terms:
        ledgermod.apply_terms(all_rows, terms)
    rules_map = ledgermod.rules(data)

    by_file = defaultdict(list)
    for row in all_rows:
        if not (row.get('ko') or row.get('ko_text') or '').strip():
            continue
        try:
            rs = R.resolve(row, styles)
        except R.SkipRow:
            continue
        by_file[rs.file].append(rs)

    inj_root = project.output_root
    base_root = project.base_root       # = images/erased (일본어만 지운 베이스)

    def compose(relative):
        specs = by_file.get(relative)
        if not specs:
            # 한글 레이블이 없는 멤버 — 원장의 규칙(rules) mode 로 판정한다.
            # 이 판단은 전부 jaguk 쪽 데이터로 끝난다(runner 는 몰라도 된다):
            #   no-text → GUI 와 똑같이 injected = erased(일본어만 지운 판)를 준다.
            #   그 밖(ignore·auto·번역대기) → None(원본 유지, 안 건드림).
            _, rule = ledgermod.match_rule(rules_map, relative)
            if ledgermod.rule_mode(rule) == 'no-text':
                bp = safe_path(base_root, relative)
                if bp.exists():
                    return Image.open(bp).convert('RGBA')
            return None
        p = safe_path(inj_root, relative)
        if use_cache and p.exists():
            return Image.open(p).convert('RGBA')
        img, _src, _b = R.compose_file(project, relative, specs, data=data)
        img = img.convert('RGBA')
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            img.save(p)
        except Exception:      # noqa: BLE001 (캐시 저장 실패는 치명적이지 않다)
            pass
        return img

    return compose


_ASSEMBLED = None


def _assembled(container):
    """data/assembled_sets.json — 조립본으로 추출·기록된 SET 이름 집합.

    dump 가 blit 을 합쳐 `<이름>.png` 하나로 저장한 SET 목록이다. jaguk 은 그
    조립본을 수정하고, build 는 여기 기록된 SET 이면 injected 조립본을 가져와
    blit 으로 되쪼개 주입한다. 목록에 없으면 pic 별 타일 이름으로 찾는다."""
    global _ASSEMBLED
    if _ASSEMBLED is None:
        import json
        p = Path(__file__).resolve().parents[2] / 'data' / 'assembled_sets.json'
        try:
            _ASSEMBLED = {k: set(v) for k, v in json.loads(
                p.read_text('utf-8')).items() if isinstance(v, list)}
        except FileNotFoundError:
            _ASSEMBLED = {}
    return _ASSEMBLED.get(container, set())


def composed_rgba(compose, mp, pi, container='SOZ'):
    """멤버(pic)의 합성 이미지를 numpy RGBA 로. 라벨 없으면 None."""
    if mp in _assembled(container):
        img = compose(f'{container}/{mp}.png')       # 조립본(jaguk 산출)
    else:
        img = compose(f'{container}/{mp}_{pi:02d}.png')
    return None if img is None else np.array(img)


# ───────────────────────────── CTRFPictures ─────────────────────────────
def parse_pics(payload):
    count = struct.unpack_from('<I', payload, 0)[0]
    pos, out = 4, []
    for _ in range(count):
        hdr, nblit, w, h = struct.unpack_from('<HHHH', payload, pos)
        ox, oy = struct.unpack_from('<hh', payload, pos + 8)
        blits = [[struct.unpack_from('<I', payload, pos + 12 + i * 20)[0],
                  list(struct.unpack_from('<4H', payload, pos + 12 + i * 20 + 4)),
                  list(struct.unpack_from('<4H', payload, pos + 12 + i * 20 + 12))]
                 for i in range(nblit)]
        out.append([hdr, w, h, ox, oy, blits])
        pos += 12 + nblit * 20
    return out, payload[pos:]


def build_pics(pics, trailing=b''):
    out = bytearray(struct.pack('<I', len(pics)))
    for hdr, w, h, ox, oy, blits in pics:
        out += struct.pack('<HHHHhh', hdr, len(blits), w, h, ox, oy)
        for tex, src, dst in blits:
            out += struct.pack('<I', tex) + struct.pack('<4H', *src) + struct.pack('<4H', *dst)
    return bytes(out) + trailing


# ─────────────────────────────── dds 인코딩 ──────────────────────────────
def _encode_dds(dds, newraw):
    """단일 LZSS 청크로 재인코딩(희소 아틀라스용). 헤더+4B갭 보존."""
    i = dds.find(b'IBUF'); lz = dds.find(b'LZSS')
    C = compress(newraw)
    chunk = b'LZSS' + struct.pack('<II', 4 + len(C), len(newraw)) + C
    nd = bytearray(dds[:lz]) + chunk
    nd[i + 4:i + 8] = struct.pack('<I', len(nd) - i)
    return bytes(nd)


def _encode_dds_mc(dds, new16):
    """멀티청크 보존: 안 바뀐 청크는 원본 바이트 그대로, 바뀐 것만 재인코딩.
    밀집 베이스 텍스처에서 라벨이 닿은 청크만 커지므로 색 감축 없이도 작다."""
    i0 = dds.find(b'IBUF'); lz0 = dds.find(b'LZSS')
    new_raw = np.asarray(new16, dtype='<u2').tobytes()
    pos = lz0; orig = []
    while pos + 12 <= len(dds) and dds[pos:pos + 4] == b'LZSS':
        size, usize = struct.unpack_from('<II', dds, pos + 4)
        orig.append((dds[pos:pos + 8 + size], usize, dds[pos + 12:pos + 8 + size]))
        pos += 8 + size
    out = []; off = 0
    for full, usize, comp in orig:
        portion = new_raw[off:off + usize]
        if portion == decompress(comp, usize):
            out.append(full)
        else:
            C = compress(portion)
            out.append(b'LZSS' + struct.pack('<II', 4 + len(C), usize) + C)
        off += usize
    nd = bytearray(dds[:lz0]) + b''.join(out)
    nd[i0 + 4:i0 + 8] = struct.pack('<I', len(nd) - i0)
    return bytes(nd)


def _pack16(sub, fmt):
    """RGBA(HxWx4 uint8) → 텍스처 native 16bit (rmask,gmask,bmask,amask)."""
    rm, gm, bm, am = fmt
    out = np.zeros(sub.shape[:2], np.uint16)
    for ci, mask in ((0, rm), (1, gm), (2, bm)):
        if not mask:
            continue
        bits = bin(mask).count('1'); sh = (mask & -mask).bit_length() - 1
        out |= (sub[..., ci].astype(np.uint16) >> (8 - bits)) << sh
    if am:
        bits = bin(am).count('1'); sh = (am & -am).bit_length() - 1
        if bits == 1:
            out |= (sub[..., 3] > 127).astype(np.uint16) << sh
        else:
            out |= (sub[..., 3].astype(np.uint16) >> (8 - bits)) << sh
    return out


def _pack16_region(reg, rm, gm, bm):
    """래스터 덮어쓰기용: 정수 스케일로 채널 인코딩(디코더 to_image 와 동일)."""
    R_, G, B, A = (reg[..., 0].astype(np.int32), reg[..., 1].astype(np.int32),
                   reg[..., 2].astype(np.int32), reg[..., 3].astype(np.int32))
    am = (~(rm | gm | bm)) & 0xFFFF

    def sh(m):
        s = (m & -m).bit_length() - 1
        return s, (m >> s)
    rs, rmax = sh(rm); gs, gmax = sh(gm); bs, bmax = sh(bm)
    v = ((R_ * rmax // 255) << rs) | ((G * gmax // 255) << gs) | ((B * bmax // 255) << bs)
    if am:
        as_, amax = sh(am)
        v |= (A * amax // 255) << as_
    v[A == 0] = 0
    return v.astype('<u2')


def _free_finder(occupied, W, H):
    """occupied(bool HxW) 밖에서 w×h 빈 rect 를 찾는 함수 반환(적분영상, step1)."""
    integ = np.zeros((H + 1, W + 1), np.int32)
    integ[1:, 1:] = np.cumsum(np.cumsum(occupied.astype(np.int32), 0), 1)

    def find(w, h):
        for y in range(0, H - h):
            row = integ[y + h] - integ[y]
            window = row[w:] - row[:-w]
            xs = np.nonzero(window == 0)[0]
            if xs.size:
                return int(xs[0]), y
        return None
    return find


# ─────────────────────────── 글리프 주입(패킹) ───────────────────────────
def inject_glyph(cab, set_name, compose, verbose=False, container='SOZ'):
    """전용 아틀라스를 쓰는 팝업 라벨을 빈 공간에 패킹하고 blit 을 재작성.

    반환: (new_set_bytes, {dds: bytes}, base_rows) / 'RASTER' / None.
      base_rows: pic#0(베이스 라벨)이 있으면 그 relative — 호출자가 래스터로 병합.
    """
    mp = set_name[:-4]
    setb = cab.read(set_name)
    root, objs = parse(setb)
    names = [s.decode('cp932', 'replace') for s in IM._find(objs, 'CTRFTexture').payload[4:].split(b'\0')
             if s and s.lower().endswith(b'.dds')]
    pics, trailing = parse_pics(IM._find(objs, 'CTRFPictures').payload)

    # 라벨 픽처 = 합성 이미지가 있는 pic. pic#0 은 베이스(래스터로 넘김).
    label_pics, base_has = {}, False
    for n in range(len(pics)):
        arr = composed_rgba(compose, mp, n, container)
        if arr is None or not (arr[..., 3] > 0).any():
            continue
        if n == 0:
            base_has = True
        else:
            label_pics[n] = arr
    if not label_pics:
        return 'RASTER' if base_has else None

    tex_size = [IM.TrfImage(cab.read(n)).to_image().size for n in names]
    base_tex = set(b[0] for b in pics[0][5])

    # 풀 = 팝업이 쓰는 모든 텍스처(base 공유 포함 — occ 가 pic#0 보호) + 여분. 큰 것부터.
    label_tex = set()
    for pi in label_pics:
        label_tex |= set(b[0] for b in pics[pi][5])
    atlas_of = {}
    for pi in label_pics:
        allt = set(b[0] for b in pics[pi][5])
        atlas_of[pi] = max(allt, key=lambda ti: tex_size[ti][0] * tex_size[ti][1])
    pool = list(label_tex)
    for ti in range(len(names)):
        if ti in pool:
            continue
        if not any(ti == b[0] for pj in range(len(pics)) for b in pics[pj][5]):
            pool.append(ti)
    pool.sort(key=lambda ti: -tex_size[ti][0] * tex_size[ti][1])

    # 텍스처 상태: occ(보존=라벨 아닌 픽처 src), a16, find, fmt
    st = {}
    for ti in pool:
        Wt, Ht = tex_size[ti]
        occ = np.zeros((Ht, Wt), bool)
        for pj in range(len(pics)):
            if pj in label_pics:
                continue
            for tex_i, src, dst in pics[pj][5]:
                if tex_i == ti:
                    occ[src[1]:src[3] + 1, src[0]:src[2] + 1] = True
        ti_img = IM.TrfImage(cab.read(names[ti]))
        rm, gm, bm = ti_img.rmask, ti_img.gmask, ti_img.bmask
        am = 0xffff & ~(rm | gm | bm)
        a16 = np.frombuffer(ti_img.raw(), dtype='<u2').reshape(Ht, Wt).copy()
        if ti not in base_tex:
            a16[~occ] = 0        # 희소 아틀라스만 통째 비움. 밀집 base_tex 는 청크 보존.
        st[ti] = {'W': Wt, 'H': Ht, 'occ': occ, 'a16': a16,
                  'find': _free_finder(occ, Wt, Ht), 'fmt': (rm, gm, bm, am)}

    # 합성 이미지를 bbox 크롭 → 높이 내림차순으로 패킹
    items = []
    for pi, arr_full in label_pics.items():
        op = arr_full[..., 3] > 0
        ys, xs = np.nonzero(op)
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        arr = arr_full[y0:y1, x0:x1]
        items.append((arr.shape[0], arr.shape[1], pi, arr, x0, y0))
    items.sort(key=lambda t: (-t[0], -t[1]))

    def place(pw, ph, prefer):
        for ti in [prefer] + [t for t in pool if t != prefer]:
            sp = st[ti]['find'](pw, ph)
            if sp:
                return ti, sp[0], sp[1]
        return None

    packed = {}           # pi -> [(ti, fx, fy, sx, sy, pw, ph), ...]
    render_cache = {}     # pi -> (arr, x0, y0)
    for h, w, pi, arr, x0, y0 in items:
        pieces = []
        colnz = (arr[..., 3] > 0).any(axis=0)
        queue, xx = [], 0
        while xx < w:                       # 공백(투명 열) 분할 = 단어 단위
            if not colnz[xx]:
                xx += 1; continue
            xs0 = xx
            while xx < w and colnz[xx]:
                xx += 1
            ys = np.nonzero((arr[:, xs0:xx, 3] > 0).any(axis=1))[0]
            queue.append((xs0, int(ys[0]), xx - xs0, int(ys[-1] - ys[0] + 1)))
        fail = False
        while queue:
            sx, sy, pw, ph = queue.pop(0)
            am = arr[sy:sy + ph, sx:sx + pw, 3] > 0
            if not am.any():
                continue
            xnz = np.nonzero(am.any(0))[0]; ynz = np.nonzero(am.any(1))[0]
            sx += int(xnz[0]); sy += int(ynz[0])
            pw = int(xnz[-1] - xnz[0] + 1); ph = int(ynz[-1] - ynz[0] + 1)
            spot = place(pw, ph, atlas_of[pi])
            if spot:
                ti, fx, fy = spot
                sub = arr[sy:sy + ph, sx:sx + pw]
                val = _pack16(sub, st[ti]['fmt'])
                reg = st[ti]['a16'][fy:fy + ph, fx:fx + pw]
                reg[:] = 0
                m = sub[..., 3] > 0
                reg[m] = val[m]
                st[ti]['occ'][fy:fy + ph, fx:fx + pw] = True
                st[ti]['find'] = _free_finder(st[ti]['occ'], st[ti]['W'], st[ti]['H'])
                pieces.append((ti, fx, fy, sx, sy, pw, ph))
            elif pw <= 3 and ph <= 3:
                fail = True; break
            elif pw >= ph:
                half = pw // 2
                queue.insert(0, (sx + half, sy, pw - half, ph))
                queue.insert(0, (sx, sy, half, ph))
            else:
                half = ph // 2
                queue.insert(0, (sx, sy + half, pw, ph - half))
                queue.insert(0, (sx, sy, pw, half))
        if fail:
            if verbose:
                print(f'  ⚠ {mp} 공간부족 (pic#{pi})')
            return None
        packed[pi] = pieces
        render_cache[pi] = (arr, x0, y0)

    new_dds = {}
    for ti in {p[0] for pcs in packed.values() for p in pcs}:
        raw = cab.read(names[ti])
        if ti in base_tex:
            new_dds[names[ti]] = _encode_dds_mc(raw, st[ti]['a16'])
        else:
            new_dds[names[ti]] = _encode_dds(raw, st[ti]['a16'].astype('<u2').tobytes())

    # blit 재작성: 픽처 origin = 조각들의 최소 화면좌표, 조각을 (sx,sy)로 이어붙임
    for pi in label_pics:
        hdr, w, h, _ox, _oy, _ = pics[pi]
        if not packed.get(pi):
            pics[pi] = [hdr, w, h, _ox, _oy, []]; continue
        arr, x0, y0 = render_cache[pi]
        nox, noy = x0, y0
        blits = []
        for ti, fx, fy, sx, sy, pw, ph in packed[pi]:
            blits.append([ti, [fx, fy, fx + pw - 1, fy + ph - 1],
                          [sx, sy, sx + pw - 1, sy + ph - 1]])
        pics[pi] = [hdr, w, h, nox, noy, blits]

    newpay = build_pics(pics, trailing)
    pn = setb.find(b'CTRFPictures'); po = pn + 12
    old = struct.unpack_from('<I', setb, po)[0]
    newset = setb[:po] + struct.pack('<I', len(newpay)) + newpay + setb[pn + 16 + old:]
    base_rows = f'{container}/{mp}_00.png' if base_has else None
    return newset, new_dds, base_rows


# ─────────────────────────── 래스터 주입(덮어쓰기) ──────────────────────────
def inject_raster(cab, set_name, compose, only_pics=None, container='SOZ'):
    """라벨 blit 영역을 합성 이미지(erased+한글)로 덮어쓴다. .SET 불변.
    only_pics: None=모든 라벨 픽처. {0}이면 pic#0 만(글리프와 병합용)."""
    mp = set_name[:-4]
    setb = cab.read(set_name)
    root, objs = parse(setb)
    names = [s.decode('cp932', 'replace') for s in IM._find(objs, 'CTRFTexture').payload[4:].split(b'\0')
             if s and s.lower().endswith(b'.dds')]
    pics, _ = parse_pics(IM._find(objs, 'CTRFPictures').payload)

    label_pics = {}
    for n in range(len(pics)):
        if only_pics is not None and n not in only_pics:
            continue
        arr = composed_rgba(compose, mp, n, container)
        if arr is not None and (arr[..., 3] > 0).any():
            label_pics[n] = arr
    if not label_pics:
        return None

    base_src = {}   # tex -> bool mask (pic#0 이 쓰는 영역 = 보호)
    for tex_i, src, dst in pics[0][5]:
        t = IM.TrfImage(cab.read(names[tex_i])).to_image()
        base_src.setdefault(tex_i, np.zeros((t.height, t.width), bool))[
            src[1]:src[3] + 1, src[0]:src[2] + 1] = True

    tex_raw, tex_fmt, changed = {}, {}, set()
    for pi, inj in label_pics.items():
        ox, oy = pics[pi][3], pics[pi][4]
        for tex_i, src, dst in pics[pi][5]:
            if tex_i not in tex_raw:
                t = IM.TrfImage(cab.read(names[tex_i]))
                tex_raw[tex_i] = np.frombuffer(t.raw(), '<u2').reshape(t.height, t.width).copy()
                tex_fmt[tex_i] = (t.rmask, t.gmask, t.bmask)
            arr16 = tex_raw[tex_i]
            sx0, sy0, sx1, sy1 = src
            rw, rh = sx1 - sx0 + 1, sy1 - sy0 + 1
            bm = base_src.get(tex_i)
            if pi != 0 and bm is not None and bm[sy0:sy1 + 1, sx0:sx1 + 1].any():
                continue                    # 다른 라벨이 base 맵과 겹치면 보호
            px, py = ox + dst[0], oy + dst[1]
            reg = inj[py:py + rh, px:px + rw]
            if reg.shape[:2] != (rh, rw):
                continue
            rm, gm, bmk = tex_fmt[tex_i]
            arr16[sy0:sy0 + rh, sx0:sx0 + rw] = _pack16_region(reg, rm, gm, bmk)
            changed.add(tex_i)

    new_dds = {}
    for ti in changed:
        new_dds[names[ti]] = _encode_dds_mc(cab.read(names[ti]), tex_raw[ti])
    return setb, new_dds


# ─────────────────────────────── 라우팅 ──────────────────────────────────
def inject_set(cab, set_name, compose, verbose=False, container='SOZ'):
    """글리프 먼저 시도, 실패/공유 시 래스터. 반환: ((setb, new_dds), kind)."""
    res = inject_glyph(cab, set_name, compose, verbose, container)
    if res == 'RASTER':
        return inject_raster(cab, set_name, compose, container=container), 'raster'
    if res is None:
        rr = inject_raster(cab, set_name, compose, container=container)
        return rr, ('raster-fb' if rr else 'none')
    setb, new_dds, base_rows = res
    if base_rows:                            # pic#0 베이스 라벨 → erase+overlay 병합
        rr = inject_raster(cab, set_name, compose, only_pics={0}, container=container)
        if rr:
            _, base_dds = rr
            if set(new_dds) & set(base_dds):     # 팝업이 pic#0 텍스처에 spill → 안전 폴백
                rrall = inject_raster(cab, set_name, compose, container=container)
                return rrall, ('raster-fb' if rrall else 'none')
            new_dds = {**new_dds, **base_dds}
        return (setb, new_dds), 'glyph+base'
    return (setb, new_dds), 'glyph'


_CACHE_SALT = b"imgcache-v2"    # 인코딩 알고리즘이 바뀌면 올린다 (캐시 무효화)


def _inject_digest(cab, set_name, compose, container):
    """SET 주입 입력의 지문 — SET 바이트 · 참조 dds 바이트 · pic 별 합성 이미지."""
    mp = set_name[:-4]
    setb = cab.read(set_name)
    h = hashlib.sha256(_CACHE_SALT)
    h.update(setb)
    root, objs = parse(setb)
    names = [s.decode('cp932', 'replace')
             for s in IM._find(objs, 'CTRFTexture').payload[4:].split(b'\0')
             if s and s.lower().endswith(b'.dds')]
    for nm in names:
        h.update(cab.read(nm))
    pics, _ = parse_pics(IM._find(objs, 'CTRFPictures').payload)
    for pi in range(len(pics)):
        arr = composed_rgba(compose, mp, pi, container)
        h.update(b'-' if arr is None else arr.tobytes())
    return h.hexdigest()


def _inject_cached(cab, set_name, compose, verbose, container, raster_only,
                   cache_dir):
    """digest 가 같으면 지난 인코딩 결과(pkl)를 재사용한다.

    주입 비용의 대부분은 LZSS 재압축이라, 입력(SET·dds·합성 이미지)이 안 바뀐
    SET 은 인코딩을 통째로 건너뛰는 것이 가장 큰 절약이다. 캐시는
    work/imgcache/<컨테이너>/<SET>.pkl — work/build 와 달리 빌드가 비우지
    않는다. 인코딩 알고리즘이 바뀌면 _CACHE_SALT 를 올려 무효화한다.
    """
    mp = set_name[:-4]
    digest = _inject_digest(cab, set_name, compose, container)
    p = os.path.join(cache_dir, container, mp + '.pkl')
    if os.path.exists(p):
        try:
            with open(p, 'rb') as fh:
                c = pickle.load(fh)
            if c.get('digest') == digest:
                return c['res'], c['kind']
        except Exception:        # noqa: BLE001 — 캐시 손상은 다시 만들면 된다
            pass
    if raster_only:
        res, kind = inject_raster(cab, set_name, compose, container=container), 'raster'
    else:
        res, kind = inject_set(cab, set_name, compose, verbose, container)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as fh:
        pickle.dump({'digest': digest, 'res': res, 'kind': kind}, fh)
    return res, kind


def build_replacements(cab, compose, verbose=False, set_prefix='soz_', container='SOZ', raster_only=False, cache_dir=None):
    """CB 안 `set_prefix`* .SET 을 주입 → {entry_name: bytes} + 리포트.
    SOZ 는 기본(soz_/SOZ). M08 이름판은 set_prefix='bghut', container='M08'.
    cache_dir 를 주면 입력이 안 바뀐 SET 의 인코딩을 건너뛴다(_inject_cached)."""
    maps = sorted({n[:-4] for n in cab.names
                   if n.lower().endswith('.set') and n.lower().startswith(set_prefix.lower())})
    repl, report = {}, []
    for mp in maps:
        sn = [x for x in cab.names if x[:-4] == mp and x.lower().endswith('.set')][0]
        try:
            if cache_dir:
                res, kind = _inject_cached(cab, sn, compose, verbose, container,
                                           raster_only, cache_dir)
            elif raster_only:
                res, kind = inject_raster(cab, sn, compose, container=container), 'raster'
            else:
                res, kind = inject_set(cab, sn, compose, verbose, container)
        except Exception as e:            # noqa: BLE001
            report.append((mp, f'ERR {type(e).__name__}:{e}', 0)); continue
        if not res:
            report.append((mp, 'none', 0)); continue
        newset, new_dds = res
        repl[sn] = newset; repl.update(new_dds)
        report.append((mp, kind, len(new_dds)))
    return repl, report


def quantized_compose(compose, k):
    """compose 결과를 K색으로 중앙값절단 감축(dither 없음)한 compose 를 돌려준다.

    erased 가 원본 텍스처보다 색이 많으면(부드러운 그라데이션) RGB555 로 패킹해도
    LZSS 런이 짧아 dds 가 커진다. 색을 줄이면 평탄한 런이 생겨 압축이 회복된다.
    슬롯을 넘는 컨테이너에만 쓴다. 알파는 보존(오버레이 대비, 무텍스트는 불투명).
    """
    cache = {}
    def c(rel):
        img = compose(rel)
        if img is None:
            return None
        if rel not in cache:
            rgb = img.convert('RGB').quantize(
                colors=k, method=Image.MEDIANCUT, dither=Image.NONE).convert('RGB')
            a = img.convert('RGBA').split()[3]
            cache[rel] = Image.merge('RGBA', (*rgb.split(), a))
        return cache[rel]
    return c


def build_to_fit(cab_path, compose, container, cap, out_path,
                 steps=(None, 128, 96, 64, 48, 40, 32), cache_dir=None):
    """CB 를 슬롯(cap 바이트)에 맞게 만든다 — 원화질 우선, 넘치면 색을 낮춰 재시도.

    제자리 패치는 슬롯을 못 넘으니(다음 파일 침범), erased 가 무거워 넘칠 때
    가장 높은 화질(가장 큰 K)로 맞춘다. 반환 (report, k_used):
      k_used=None  원화질로 맞음
      k_used=<int> 그 색수로 감축해 맞음
      report=None  최저 감축(steps 끝)으로도 못 맞춤 → 호출측이 건너뛴다

    cache_dir 를 주면 ① 인코딩 캐시(build_replacements) ② 지난 빌드에서 맞았던
    색수 기록(fit_<컨테이너>.json)으로 사다리를 건너뛴다. 화질 재탐색(erased 를
    가볍게 고친 뒤)은 그 기록 파일을 지우고 빌드하면 된다.
    """
    from kitae.build.smf import repack_cab
    fit_rec = os.path.join(cache_dir, f'fit_{container}.json') if cache_dir else None
    if fit_rec and os.path.exists(fit_rec):
        try:
            k0 = json.load(open(fit_rec, encoding='utf-8')).get('k')
        except Exception:        # noqa: BLE001
            k0 = None
        if k0 is not None:
            steps = tuple([k0] + [s for s in steps
                                  if s is not None and s < k0])
    last = None
    for k in steps:
        comp = compose if k is None else quantized_compose(compose, k)
        repl, rep = build_replacements(Cab(cab_path), comp,
                                       set_prefix="", container=container,
                                       raster_only=True, cache_dir=cache_dir)
        if not repl:
            return [], None                 # 주입할 것이 없음(정상)
        repack_cab(cab_path, repl, out_path)
        if os.path.getsize(out_path) <= cap:
            if fit_rec:
                json.dump({'k': k}, open(fit_rec, 'w', encoding='utf-8'))
            return rep, k
        last = (rep, k)
    return None, (last[1] if last else None)


# ─────────────────────────── 디스크 재배치/적용 ───────────────────────────
def _stub_debug_cb(src_track, work_dir, debug_name='RESOURCE/DEBUG.CB'):
    """DEBUG.CB(미사용 테스트 자산)를 dds 단색(0)화로 축소한 바이트 반환.
    dds 크기는 유지(SET blit 유효), 내용만 0 → 압축 극소."""
    from kitae.core.gdfs import GdFs
    from kitae.build.smf import repack_cab
    fs = GdFs(track=src_track)
    lba, size = fs.find(debug_name)
    tmp = Path(work_dir) / 'DEBUG.orig.CB'
    tmp.write_bytes(fs.read(lba, size))
    cab = Cab(str(tmp))
    repl = {nm: _encode_dds(cab.read(nm), bytes(len(IM.TrfImage(cab.read(nm)).raw())))
            for nm in cab.names if nm.lower().endswith('.dds')}
    out = Path(work_dir) / 'DEBUG.stub.CB'
    repack_cab(str(tmp), repl, str(out))
    data = out.read_bytes()
    tmp.unlink(); out.unlink()
    return data


def apply_to_disc(src_track, out_track, soz_bytes, work_dir,
                  soz_name='RESOURCE/SOZ.CB', debug_name='RESOURCE/DEBUG.CB'):
    """SOZ.CB 를 soz_bytes 로 교체. 원 슬롯을 넘으면 바로 뒤 DEBUG.CB 를 축소·이동해
    공간을 만든다(DEBUG 외 파일은 LBA 불변). 반환: 요약 dict."""
    from kitae.core.gdfs import GdFs, BASE_LBA, RAW
    from kitae.build.disc import fix_sector, patch as disc_patch
    fs = GdFs(track=src_track)
    soz_lba, soz_old = fs.find(soz_name)
    cap = ((soz_old + 2047) // 2048) * 2048
    if len(soz_bytes) <= cap:
        disc_patch(soz_name, soz_bytes, out_track, src_track)
        return {'relocated': False, 'soz': len(soz_bytes), 'cap': cap}

    dbg = _stub_debug_cb(src_track, work_dir, debug_name)
    dbg_lba, _ = fs.find(debug_name)
    after = [l for f, l, s, d in fs.walk() if not d and l > dbg_lba]
    next_lba = min(after) if after else None
    soz_sec = (len(soz_bytes) + 2047) // 2048
    new_dbg_lba = soz_lba + soz_sec
    dbg_sec = (len(dbg) + 2047) // 2048
    if next_lba is not None and new_dbg_lba + dbg_sec > next_lba:
        raise ValueError(
            f'재배치 후에도 공간부족: DEBUG 끝 {new_dbg_lba + dbg_sec} > 다음 {next_lba}')

    image = bytearray(open(src_track, 'rb').read())

    def write_payload(lba, data):
        n = (len(data) + 2047) // 2048
        pad = data + b'\x00' * (n * 2048 - len(data))
        for i in range(n):
            off = (lba + i - BASE_LBA) * RAW
            sec = bytearray(image[off:off + RAW])
            sec[16:2064] = pad[i * 2048:(i + 1) * 2048]
            image[off:off + RAW] = fix_sector(sec)

    write_payload(soz_lba, soz_bytes)
    write_payload(new_dbg_lba, dbg)

    dirs = [("/", fs.root_lba, fs.root_size)] + [(a, b, c) for a, b, c, d in fs.walk() if d]

    def update_record(old_dlba, new_lba, new_size):
        for _pf, pl, ps in dirs:
            for si in range((ps + 2047) // 2048):
                off = (pl + si - BASE_LBA) * RAW
                sec = bytearray(image[off:off + RAW]); d = sec[16:2064]; p = 0
                while p < len(d):
                    ln = d[p]
                    if ln == 0:
                        break
                    if struct.unpack('<I', d[p + 2:p + 6])[0] == old_dlba:
                        struct.pack_into('<I', d, p + 2, new_lba)
                        struct.pack_into('>I', d, p + 6, new_lba)
                        struct.pack_into('<I', d, p + 10, new_size)
                        struct.pack_into('>I', d, p + 14, new_size)
                    p += ln
                sec[16:2064] = d
                image[off:off + RAW] = fix_sector(sec)

    update_record(soz_lba, soz_lba, len(soz_bytes))         # SOZ: LBA 불변, size만
    update_record(dbg_lba, new_dbg_lba, len(dbg))           # DEBUG: LBA + size
    open(out_track, 'wb').write(bytes(image))
    return {'relocated': True, 'soz': len(soz_bytes), 'debug': len(dbg),
            'debug_lba': new_dbg_lba, 'next_lba': next_lba}
