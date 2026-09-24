import os
HERE = os.path.dirname(os.path.abspath(__file__))
"""Hangul codepage: assign Korean syllables to free font cells and inject glyphs.

The engine addresses a glyph by its raw cp932 byte pair (see font.py): the lead
byte picks one of 42 pages, the trail byte (0x40..0xFC) picks one of 189 cells.
It never validates the trail byte, so any cell in a page is usable -- including
ones cp932 leaves unassigned.

So a Korean build works like this:

  1. collect the distinct Korean characters the translation actually uses
  2. hand each one a free cell in the JIS level-2 region (leads 0xE0..0xEE),
     which this game's Japanese text barely touches
  3. render it from IBM Plex Sans KR into the two 1-bpp planes of the font
  4. emit those raw byte pairs instead of cp932 when building the .SMF

The mapping is written next to the build so the same bytes are reproduced every
time; adding new characters later appends rather than reshuffles.

Usage:
    python hangul.py build KOTORI_01      # codepage + patched TRFSTRINGS.DLL
    python hangul.py preview "안녕하세요"   # render through the patched font
"""
import io, json, os, sys

from kitae.core import font as fontmod
from kitae.core import workbook

DUMP = os.path.join(HERE, "..", "dump")
BUILD = os.path.join(DUMP, "build")
CODEPAGE = os.path.join(BUILD, "codepage.json")

TTF = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                   "Microsoft", "Windows", "Fonts", "IBMPlexSansKR-Regular.otf")

# JIS level-2 / IBM-extension pages: present in the font, almost unused by this
# game's script. Ordered so the emptiest pages are consumed first.
PAGES = [0xEE, 0xED, 0xE1, 0x9B, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7,
         0xE8, 0xE9, 0xEA, 0xE0, 0x9C, 0x9D, 0x9E, 0x9F, 0x99, 0x9A]
CELLS = [c for c in range(0x40, 0xFD) if c != 0x7F]      # 188 usable trail bytes
# ASCII·공백·합자 셀(widths.SYMBOL_CELLS)을 붙이는 페이지 — 한글 페이지 뒤, 연속으로.
# 한글이 넘치면 이 페이지의 남은 칸도 쓴다(폭표는 하위표라 섞여도 된다).
SYMBOL_PAGE = 0xE5


def is_hangul(ch):
    o = ord(ch)
    return 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F


def used_cells(cfg, refresh=False):
    """게임 자신의 대사가 실제로 그리는 칸 — 여기는 절대 덮으면 안 된다.

    폰트에 글리프가 들어 있는지로는 판단할 수 없다. JIS 2수준 페이지는 글리프가
    거의 다 차 있지만 이 게임 대사는 그중 극히 일부만 쓴다(0xE1/0xED/0xEE 는
    한 칸도 안 쓴다). 그래서 대사를 직접 훑어 쓰이는 칸만 추린다.

    결과는 data/used_cells.json 에 넣어 둔다 — 원본이 바뀌지 않는 한 같다.
    """
    cache = os.path.join(cfg.data_dir, "used_cells.json")
    if not refresh and os.path.exists(cache):
        with io.open(cache, encoding="utf-8") as fh:
            return {tuple(c) for c in json.load(fh)}

    import struct
    from kitae.core.cab import Cab
    used = set()
    root = cfg.path(cfg["work_dir"], "cb", "RESOURCE")
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if not name.upper().endswith(".CB"):
            continue
        try:
            cab = Cab(os.path.join(root, name))
        except Exception:
            continue
        for entry in cab.names:
            try:
                blob = cab.read(entry)
            except Exception:
                continue
            if blob[:4] != b".STR" or len(blob) < 12:
                continue
            # 문자열 블록만 본다. 헤더와 뒤따르는 .MSG 는 이진이라 글자로 세면
            # 있지도 않은 칸이 잔뜩 잡힌다.
            count = struct.unpack_from("<I", blob, 8)[0]
            pos, k = 12, 0
            while k < count:
                end = blob.find(b"\x00", pos)
                if end < 0:
                    break
                s, i = blob[pos:end], 0
                while i < len(s):
                    b = s[i]
                    if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < len(s):
                        used.add((b, s[i + 1]))
                        i += 2
                    else:
                        i += 1
                pos, k = end + 1, k + 1

    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with io.open(cache, "w", encoding="utf-8") as fh:
        json.dump(sorted(list(c) for c in used), fh)
    return used


def original_font(cfg):
    """원본 디스크의 TRFSTRINGS.DLL 경로. 없으면 꺼내 둔다.

    Font() 의 기본 경로는 이전 빌드 산출물을 가리킬 수 있다. 거기서 시작하면
    지난번에 넣은 글리프가 얹힌 채로 쌓이고, '원래 비어 있었는가' 판단도
    틀어진다. 주입은 늘 순정에서 시작해야 한다.
    """
    dst = cfg.path(cfg["work_dir"], "orig", "TRF", "TRFSTRINGS.DLL")
    if not os.path.exists(dst):
        from kitae.core.gdfs import GdFs
        fs = GdFs(cfg.track(3))
        lba, size = fs.find("/TRF/TRFSTRINGS.DLL")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(fs.read(lba, size))
    return dst


def load_codepage():
    if os.path.exists(CODEPAGE):
        with io.open(CODEPAGE, encoding="utf-8") as fh:
            raw = json.load(fh)
        return {k: tuple(v) for k, v in raw.items()}
    return {}


def save_codepage(cp):
    os.makedirs(BUILD, exist_ok=True)
    with io.open(CODEPAGE, "w", encoding="utf-8") as fh:
        json.dump({k: list(v) for k, v in sorted(cp.items())}, fh,
                  ensure_ascii=False, indent=0)


def _decodable(lead, cell):
    """cp932 로 되읽을 수 있는 칸인가.

    ## ★ 왜 이걸 거르나

    파이프라인은 SMF 문자열을 **cp932 문자열로 들고 다닌다**(`smf_strings`).
    글리프 칸이라도 cp932 에 정의가 없으면(`0xEEED`·`0xEEEE` 가 그렇다) 되읽는
    순간 한 글자가 대체 문자 둘로 바뀌어 **길이가 틀어진다.** 게임은 두 바이트를
    그냥 그리므로 화면은 멀쩡한데, 우리 검사 도구만 어긋난 값을 본다 —
    실제로 `카`·`친` 때문에 타이밍이 어긋났다고 잘못 짚었다.

    화면에 나오는 결과는 같으니 칸을 옮겨도 손해가 없다. 되읽히는 칸만 쓴다.
    """
    try:
        bytes((lead, cell)).decode("cp932")
    except UnicodeDecodeError:
        return False
    return True


def assign(chars, cp=None, reserved=(), pages=None):
    """Give every new character a cell, keeping existing assignments stable."""
    cp = dict(cp or {})
    taken = set(cp.values()) | set(reserved)
    pages = pages or PAGES
    # 되읽을 수 없는 칸은 아예 후보에서 뺀다 — 위 `_decodable` 참고
    taken |= {(l, c) for l in pages for c in CELLS if not _decodable(l, c)}
    # 이미 배정돼 있더라도 못 읽는 칸이면 새로 받게 한다
    for ch in [c for c, s in cp.items() if not _decodable(*s)]:
        del cp[ch]
    slots = ((lead, cell) for lead in pages for cell in CELLS)
    for ch in sorted(chars):
        if ch in cp:
            continue
        for s in slots:
            if s not in taken:
                cp[ch] = s
                taken.add(s)
                break
        else:
            raise RuntimeError("out of free font cells")
        slots = ((lead, cell) for lead in pages for cell in CELLS
                 if (lead, cell) not in taken)
    return cp


JONG_L = 8                    # 종성 인덱스 8 = ㄹ


def jong_group(ch):
    """0 무받침 · 1 ㄹ받침 · 2 기타받침. 한글 음절이 아니면 None.

    조사 선택에 필요한 구분은 이 셋뿐이다 — 은/는·이/가 류는 받침 유무만,
    (으)로는 ㄹ 받침을 무받침과 같이 본다(`docs/JOSA-ENGINE.md`).
    """
    if not ("가" <= ch <= "힣"):
        return None
    j = (ord(ch) - 0xAC00) % 28
    return 0 if j == 0 else (1 if j == JONG_L else 2)


def assign_josa(chars, cp=None, reserved=(), pages=None):
    """한글을 **받침군 순으로 전체 재배정**하고 경계를 함께 낸다. (cp, B1, B2).

    셀코드(`lead<<8 | trail`) 오름차순으로 `[무받침][ㄹ받침][기타받침]` 을 깔면
    런타임 받침 판정이 **비교 한 번**으로 끝난다. 표도 비트맵도 필요 없다.

        받침 있음 = cell >= B1      (은/는·이/가·을/를·와/과 …)
        으로/로   = cell >= B2      (무받침·ㄹ받침은 `로`)

    ★ 페이지를 **숫자 오름차순**으로 돈다. `PAGES` 는 안전한 순서(선호도)라 숫자
    순이 아니어서, 그대로 쓰면 셀코드가 단조가 아니게 되어 비교가 깨진다.
    ★ 한글은 기존 배정을 버리고 전부 새로 깐다 — 폰트·대사 전체 재굽기가 따라온다.
    한글이 아닌 배정(ASCII·공백·합자·기호)은 그대로 둔다.
    """
    cp = dict(cp or {})
    pages = sorted(int(p) for p in (pages or PAGES))
    hangul = {ch for ch in set(chars) | set(cp) if jong_group(ch) is not None}
    for ch in hangul:
        cp.pop(ch, None)
    taken = set(cp.values()) | set(reserved)
    taken |= {(l, c) for l in pages for c in CELLS if not _decodable(l, c)}
    slots = [(l, c) for l in pages for c in CELLS if (l, c) not in taken]
    if len(slots) < len(hangul):
        raise RuntimeError(f"한글 {len(hangul)}자에 빈 칸이 {len(slots)}칸뿐이다")
    for ch, slot in zip(sorted(hangul, key=lambda c: (jong_group(c), c)), slots):
        cp[ch] = slot
    return (cp,) + josa_bounds(cp)


def josa_bounds(cp):
    """배정에서 경계 (B1, B2) 를 읽어낸다. 받침군이 섞여 있으면 ValueError.

    빌드마다 다시 계산한다 — 파일로 남기지 않는다(단일 소스는 codepage 자체).
    """
    groups = {}
    for ch, slot in cp.items():
        g = jong_group(ch)
        if g is not None:
            groups.setdefault(g, []).append((slot[0] << 8) | slot[1])
    if not groups:
        return (0, 0)
    top = max(max(v) for v in groups.values()) + 1
    b1 = min(groups.get(1, []) + groups.get(2, []) + [top])
    b2 = min(groups.get(2, []) + [top])
    # 세 구간이 실제로 갈리는지 확인 — 어긋나면 훅이 조용히 틀린 조사를 고른다
    for g, lo, hi in ((0, 0, b1), (1, b1, b2), (2, b2, 1 << 16)):
        bad = [c for c in groups.get(g, []) if not lo <= c < hi]
        if bad:
            raise ValueError(f"받침군 {g} 의 셀 {len(bad)}개가 구간 밖: {bad[:4]}")
    return b1, b2


def contiguous_digits(cp, reserved=()):
    """ASCII 숫자 '0'~'9' 를 SYMBOL_PAGE 의 **연속 10칸**에 둔다.

    엔진은 저장 슬롯 날짜·슬롯 번호를 '０' 템플릿의 뒤 바이트에 n 을 더해 만든다(TRFVMSVIEW
    0x10002d5e 등). assign 은 게임이 쓰는 칸·못 읽는 칸을 건너뛰므로 숫자 사이에 구멍이 생길 수
    있고, 실제로 '8' 이 0x5A 로 밀려 8월이 한자로 나왔다(2026-09-19). 이미 연속이면 그대로."""
    digits = "0123456789"
    cells = [cp.get(d) for d in digits]
    if all(cells) and all(c[0] == cells[0][0] and c[1] == cells[0][1] + i for i, c in enumerate(cells)):
        return cp
    taken = (set(v for k, v in cp.items() if k not in digits) | set(reserved)
             | {(SYMBOL_PAGE, c) for c in CELLS if not _decodable(SYMBOL_PAGE, c)})
    for start in CELLS:
        run = [(SYMBOL_PAGE, start + i) for i in range(10)]
        if any(c[1] not in CELLS or c in taken for c in run):
            continue
        for d, c in zip(digits, run):
            cp[d] = c
        return cp
    raise RuntimeError("숫자 10칸 연속 자리가 없다")


def render_glyph(ch, size=21, y_off=2, ttf=None, widths=None):
    """24x24 grayscale of one character from IBM Plex Sans KR.

    ## ★ 세로는 글자마다 맞추지 않는다

    예전에는 잉크 높이로 칸 가운데를 맞췄다. 한글끼리는 높이가 비슷해 티가 안
    났지만 **기준선이 글자마다 흔들리고**, `。` 같은 낮은 글자가 공중에 뜬다.
    지금은 폰트의 ascent/descent 로 기준선을 한 번 정하고 모든 글자를 거기에
    올린다 — 가로만 조정한다.

    `widths` 를 주면(kitae.build.widths.Widths) 가로 위치도 그쪽을 따른다:
    전각 칸에 반각 모양을 **좌측 정렬**로 그린다. 가변폭 전진폭과 짝이라
    스텁이 없으면 켜지 않는다 — 폭이 24 인데 잉크만 왼쪽에 붙으면 더 이상하다.
    """
    from PIL import Image, ImageDraw, ImageFont
    ttf = ttf or TTF
    if not os.path.exists(ttf):
        raise FileNotFoundError(ttf)
    font = ImageFont.truetype(ttf, size)
    img = Image.new("L", (24, 24), 0)
    d = ImageDraw.Draw(img)

    if widths is not None:
        g, ox = widths.shape(ch), widths.offset(ch)
        d.text((ox, widths.baseline), g, font=font, fill=255, anchor="ls")
        return img

    asc, desc = font.getmetrics()
    baseline = (24 - (asc + desc)) // 2 + asc + y_off - 2
    try:
        box = d.textbbox((0, 0), ch, font=font)
    except Exception:
        box = (0, 0, size, size)
    x = (24 - (box[2] - box[0])) // 2 - box[0]      # 가로는 칸 가운데
    d.text((x, baseline), ch, font=font, fill=255, anchor="ls")
    return img


def planes(gray, solid=128, edge=40):
    """Split a grayscale glyph into the engine's body / anti-alias planes."""
    from PIL import Image
    body = gray.point(lambda v: 255 if v >= solid else 0, mode="1")
    fringe = gray.point(lambda v: 255 if edge <= v < solid else 0, mode="1")
    return body, fringe


# 보호 항목(raw)용 — 엔진이 바이트로 조립하는 UI 문자열. 표기는 규칙(§2)과 같다:
#   ' '  (어절 공백)      -> 어절 공백 셀 (2바이트, 9px)   ← 2026-09-19: 스폿명 `로즈힐 미나미히라기시`
#   U+2002 EN SPACE       -> 0x20    엔진 반각 공백 12px (1바이트) — 메뉴 라벨 정렬
#   U+3000                -> 0x8140  게임 전각 공백(폭표 12 = EN, 2바이트) — 고정 폭 필드
#   그 밖의 셀(한글·EM·FIGURE·FOUR-PER-EM(6px)·／ …) -> 셀. ASCII 는 1바이트 그대로(색인 접두·서식).
_SPACER = {"\u2002": b"\x20", "\u3000": b"\x81\x40"}
_IDEO = b"\x81\x40"


def units(text):
    """텍스트 → 글리프 단위 [(문자열, 마크업 여부)]. 합자(widths.LIGATURES)는 한 단위.

    인코더·타이밍·검사기·미리보기가 같은 분해를 쓴다 — 글자 수는 바이트가 아니라
    **렌더링될 글리프 수**다(docs/KO-TEXT-RULES.md §4)."""
    from kitae.core.windows import MARKUP_ALL
    from kitae.build.widths import LIGATURES, JOSA
    out, pos = [], 0
    # 조사 마커가 합자보다 길므로 먼저 본다 (`{은는}` 5글자 → 한 단위)
    longest = max([len(k) for k in JOSA] or [0])

    def split(seg):
        i, n = 0, len(seg)
        while i < n:
            for k in range(longest, 2, -1):
                if seg[i:i + k] in JOSA:
                    out.append((seg[i:i + k], False))
                    i += k
                    break
            else:
                if seg[i:i + 2] in LIGATURES:
                    out.append((seg[i:i + 2], False))
                    i += 2
                else:
                    out.append((seg[i], False))
                    i += 1
                continue

    for m in MARKUP_ALL.finditer(text):
        split(text[pos:m.start()])
        out.append((m.group(), True))
        pos = m.end()
    split(text[pos:])
    return out


def glyph_string(text):
    """타이밍·줄 길이용 문자열 — 글리프 하나당 한 글자(합자는 첫 글자). `@..@`·`&..&` 는
    빼고, `%N%` 같은 나머지 마크업은 예전 display_len 과 같게 글자로 남긴다."""
    from kitae.core.windows import MARKUP
    return "".join(u if mk else u[0] for u, mk in units(MARKUP.sub("", text)))


def encode(text, cp, raw=False):
    """번역문 → 게임 바이트. 배정된 셀(한글·ASCII·공백·합자) + cp932.

    `raw` 는 보호 항목(uipatch.is_fixed): ASCII 는 1바이트 그대로(단 ' ' 는 어절 공백 셀),
    EN SPACE 는 1바이트 0x20, U+3000 은 0x8140, 합자·ASCII 셀 재할당은 하지 않는다 — 엔진이
    바이트를 세거나 조립하는 문자열. 정렬용 12px 공백은 EN 으로 적는다."""
    out = bytearray()
    if raw:
        for ch in text:
            if ch in _SPACER:                       # EN → 0x20(1바이트), U+3000 → 0x8140 — 셀 규칙보다 먼저
                out += _SPACER[ch]
            elif ch in cp and (ord(ch) > 0x7F or ch == " "):
                out += bytes(cp[ch])
            else:
                out += ch.encode("cp932")
        return bytes(out)
    for u, mk in units(text):
        if mk:
            out += u.encode("cp932")            # 제어 코드는 1바이트 그대로
        elif u in cp:
            out += bytes(cp[u])
        elif u == "\u3000":
            out += _IDEO
        else:
            out += u.encode("cp932")
    return bytes(out)


def inject(cfg, chars, verbose=False):
    """설정을 받아 필요한 글자만 폰트에 넣고, 패치된 DLL 경로를 돌려준다."""
    from kitae.core import font as fontmod

    out_dir = cfg.path(cfg["work_dir"], "build", "TRF")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, "TRFSTRINGS.DLL")

    # 늘 순정 폰트에서 시작한다 — 지난 빌드의 글리프가 얹히면 안 된다
    f = fontmod.Font(original_font(cfg))
    pages = [int(p) for p in cfg["font"].get("pages") or PAGES]
    allowed = {(l, c) for l in pages for c in CELLS}
    reserved = used_cells(cfg) & allowed
    if reserved and verbose:
        print(f"    게임이 쓰는 {len(reserved)}칸은 비켜 간다")

    cp_path = os.path.join(cfg.data_dir, "codepage.json")
    cp = _read_codepage(cp_path)
    # ASCII·공백·합자 셀은 SYMBOL_PAGE 에 먼저(연속으로), 한글은 그 뒤 페이지 순서대로.
    from kitae.build.widths import SYMBOL_CELLS
    symbols = set(SYMBOL_CELLS)
    cp = assign(symbols, cp, reserved, [SYMBOL_PAGE])
    cp = contiguous_digits(cp, reserved)
    if cfg.get("josa"):                      # 받침순 전체 재배정 (docs/JOSA-ENGINE.md)
        cp, b1, b2 = assign_josa(set(chars) - symbols, cp, reserved, pages)
        if verbose:
            print(f"    조사 배정: B1={b1:#06x} B2={b2:#06x}")
    else:
        cp = assign(set(chars) - symbols, cp, reserved, pages)
    _write_codepage(cp_path, cp)
    chars = set(chars) | symbols

    ttf = cfg.path(cfg["font"]["ttf"]) if cfg["font"].get("ttf") else TTF
    size = int(cfg["font"].get("size", 21))
    yoff = int(cfg["font"].get("y_offset", 2))

    # 글리프는 늘 widths 를 따른다(ASCII 셀은 글꼴 원점 그대로, `・` 는 가운데).
    # 폭표(가변폭)와 짝이라 값을 두 군데 적지 않는다.
    from kitae.build.widths import REDRAW, Widths
    W = Widths(cfg)

    for ch in sorted(chars):
        body, fringe = planes(render_glyph(ch, size, yoff, ttf, widths=W))
        code = bytes(cp[ch])
        f.set_glyph(code, body, 0)
        f.set_glyph(code, fringe, 1)

    # 게임 전각 칸에 다시 그리는 것은 `・`(가운데 22px)뿐 — 전각 로마자·기호는 게임
    # 글리프 24 고정폭 그대로(docs/KO-TEXT-RULES.md §6).
    for ch in REDRAW:
        code = ch.encode("cp932")
        body, fringe = planes(render_glyph(ch, size, yoff, ttf, widths=W))
        f.set_glyph(code, body, 0)
        f.set_glyph(code, fringe, 1)
    if verbose:
        print(f"    셀 {len(symbols)}개(ASCII·공백·합자·구분기호) 포함, 재그림 {len(REDRAW)}칸")

    f.save(dst)
    return dst


def decode(data, cp):
    """`encode` 의 역 — 배정된 칸을 한글로 되돌린다.

    게임 바이트를 사람이 읽으려면 필요하다. cp932 로 그냥 읽으면 배정된 칸이
    엉뚱한 한자로 보여서 빌드 결과를 눈으로 확인할 수 없다.
    """
    rev = {bytes(v): k for k, v in cp.items()}
    out, i, n = [], 0, len(data)
    while i < n:
        two = data[i:i + 2]
        if two in rev:
            out.append(rev[two])
            i += 2
            continue
        lead = data[i]
        w = 2 if (0x81 <= lead <= 0x9F or 0xE0 <= lead <= 0xFC) and i + 1 < n else 1
        out.append(data[i:i + w].decode("cp932", "replace"))
        i += w
    return "".join(out)


def decoder(cfg):
    """게임 바이트를 읽을 수 있는 문자열로 바꾸는 함수."""
    cp = _read_codepage(os.path.join(cfg.data_dir, "codepage.json"))

    def dec(data):
        return decode(data, cp)
    return dec


def encoder(cfg):
    """번역문을 게임 바이트로 바꾸는 함수. `enc(text, raw=False)` — raw 는 encode 참고."""
    cp = _read_codepage(os.path.join(cfg.data_dir, "codepage.json"))

    def enc(text, raw=False):
        return encode(text, cp, raw=raw)
    return enc


def _read_codepage(path):
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            return {k: tuple(v) for k, v in json.load(fh).items()}
    return {}


def _write_codepage(path, cp):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump({k: list(v) for k, v in sorted(cp.items())}, fh,
                  ensure_ascii=False, indent=0)


def build(script):
    rows = workbook.load(script)
    chars = {c for r in rows.values() for c in (r.get("target") or "")
             if is_hangul(c)}
    print(f"{script}: {len(chars)} distinct Hangul characters in the translation")
    if not chars:
        print("  (nothing translated yet -- fill in the workbook's target column)")
        return

    f = fontmod.Font()
    reserved = set()
    free = used_cells(f)
    if free is not None:
        allowed = {(l, c) for l in PAGES for c in CELLS}
        reserved = {s for s in allowed if s not in free}
        print(f"  {len(reserved)} cell(s) in the target pages are already in use "
              f"-- skipping them")

    cp = assign(chars, load_codepage(), reserved)
    save_codepage(cp)
    print(f"  codepage -> {CODEPAGE} ({len(cp)} characters)")

    for ch in sorted(chars):
        body, fringe = planes(render_glyph(ch))
        code = bytes(cp[ch])
        f.set_glyph(code, body, 0)       # solid body
        f.set_glyph(code, fringe, 1)     # anti-alias fringe
    out = os.path.join(BUILD, "TRF")
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, "TRFSTRINGS.DLL")
    f.save(dst)
    print(f"  patched font -> {dst}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    if sys.argv[1] == "build":
        build(sys.argv[2])
    elif sys.argv[1] == "preview":
        cp = load_codepage()
        os.environ["TRFSTRINGS_DLL"] = os.path.join(BUILD, "TRF", "TRFSTRINGS.DLL")
        import importlib
        importlib.reload(fontmod)
        text = sys.argv[2]
        from PIL import Image
        img = Image.new("1", (24 * len(text), 24), 0)
        for i, ch in enumerate(text):
            code = bytes(cp[ch]) if ch in cp else ch.encode("cp932")
            img.paste(fontmod.get_glyph(code), (i * 24, 0))
        p = os.path.join(BUILD, "preview.png")
        img.resize((img.width * 2, img.height * 2)).save(p)
        print("->", p)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
