# -*- coding: utf-8 -*-
"""DLL 안의 시스템 텍스트를 제자리에서 바꾼다.

대사와 달리 문자열 테이블이 없으므로 있던 자리를 덮어쓴다. 그래서 번역문의
바이트 길이가 `avail`(원문 + 정렬 패딩) 이하여야 한다 — 넘으면 다음 문자열을
먹어 버린다. 길이 검사는 여기서 한 번 더 한다(번역 파일이 손으로 고쳐질 수 있다).

원본은 늘 디스크에서 꺼낸다. 이전 빌드 산출물에서 시작하면 지난번 패치가 얹힌
채로 쌓인다 — 폰트에서 이미 한 번 겪었다.
"""
import io
import json
import os
import re


def modules(cfg):
    """번역 파일이 있는 모듈 목록. [(이름, 문서)]"""
    d = cfg.path("translation", "ui")
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        with io.open(os.path.join(d, name), encoding="utf-8") as fh:
            doc = json.load(fh)
        if isinstance(doc, dict) and doc.get("entries"):
            out.append((doc["module"], doc))
    return out


def original(cfg, disc_path):
    """원본 디스크에서 꺼낸 모듈 경로. 없으면 꺼내 둔다."""
    dst = cfg.path(cfg["work_dir"], "orig", *disc_path.strip("/").split("/"))
    if not os.path.exists(dst):
        from kitae.core.gdfs import GdFs
        fs = GdFs(cfg.track(3))
        lba, size = fs.find(disc_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(fs.read(lba, size))
    return dst


_ASCII = re.compile(r"[\t\x20-\x7e]")


def is_fixed(e):
    """엔진이 바이트로 다루는(조립·해석·고정 폭) 항목 — 문자 규칙(docs/KO-TEXT-RULES.md
    §5)을 적용하지 않고 옛 인코딩(ASCII 1바이트, U+3000=0x8140, 합자 없음)으로 넣는다.

    판정: `fixed` 를 명시했으면 그 값(true/false)이 우선한다. 없으면 원문에 ASCII(서식
    템플릿·색인 접두·탭·반각 정렬 공백)가 있거나, 원문이 전각 공백으로 시작/끝나면(조각
    조립·칸 맞춤) 보호 항목이다. `fixed: false` 는 자동 판정을 끄는 용도 — 예: TRFNAMEIN
    85984 `　さんでいいですか？　` 는 앞뒤 전각 공백으로 raw 로 잡히지만 실제로는 이름 뒤에
    strcat 돼 CTRFMessage 로 그려질 뿐이라 바이트 위치 제약이 없다. raw 면 `?` 가 엔진 반각
    글리프(12px 상자를 잉크로 꽉 채우는 굵은 픽셀 글자)로, 셀이면 우리가 구운 Plex 셀로 나온다."""
    from kitae.core.windows import MARKUP_ALL
    ja = (e.get("text") or {}).get("ja") or ""
    plain = MARKUP_ALL.sub("", ja)          # `&マフラー&` 의 & 는 ASCII 가 아니라 마크업
    if "fixed" in e:                        # 명시 값이 자동 판정보다 우선 (false 로 끌 수 있다)
        return bool(e["fixed"])
    return (bool(_ASCII.search(plain))
            or ja.startswith("　") or ja.endswith("　"))


def texts(cfg, lang):
    """번역에 쓰인 글자 전부 — 폰트에 넣을 글자를 모을 때 쓴다."""
    out = set()
    for _name, doc in modules(cfg):
        for e in doc["entries"]:
            out.update((e.get("text") or {}).get(lang) or "")
    return out


def disc_slack(cfg, disc_path):
    """이 파일을 디스크에서 몇 바이트까지 키울 수 있나."""
    from kitae.core.gdfs import GdFs
    fs = GdFs(cfg.track(3))
    rows = []
    for r in fs.walk():
        if r[-1]:
            continue
        lba, size = fs.find(r[0])
        rows.append((lba, size, r[0]))
    rows.sort()
    i = next((k for k, (_l, _s, q) in enumerate(rows) if q == disc_path), None)
    if i is None:
        return 0
    lba, size, _ = rows[i]
    nsect = (size + 2047) // 2048
    tail = nsect * 2048 - size
    gap = (rows[i + 1][0] - (lba + nsect)) * 2048 if i + 1 < len(rows) else 0
    return tail + gap


def _grow(cfg, name, disc_path, base_blob, rows, encode, nbytes=768):
    """PE 에 데이터 섹션을 붙이고 그 공간까지 써서 다시 배치한다.

    파일이 커지므로 **디스크 여유가 있어야 한다.** 없으면 시도하지 않는다 —
    만들어 놓고 디스크에서 거절당하면 빌드가 통째로 멈춘다.
    """
    from kitae.build import pesection, relocate
    slack = disc_slack(cfg, disc_path)
    if slack < nbytes:
        # 요청보다 여유가 작으면 여유에 맞춰 줄여서라도 붙인다 (512 정렬).
        # 768 로 올렸을 때 여유가 딱 512 이던 모듈(TRFGUIDEMAP 등)이 통째로
        # 실패하던 회귀의 재발 방지 — 크게 안 되면 예전 크기로라도.
        nbytes = (slack // 512) * 512
        if nbytes <= 0:
            print(f"  {name}: 디스크 여유 {slack}B — 섹션을 붙일 수 없다")
            return None
        print(f"  {name}: 디스크 여유 {slack}B — 섹션을 {nbytes}B 로 줄여 붙인다")
    try:
        blob, off, size = pesection.add(base_blob, ".ktr", nbytes)
    except Exception as e:
        print(f"  {name}: 섹션을 붙일 수 없다 ({e})")
        return None
    got, rep = relocate.apply(blob, rows, encode,
                              extra_free=[(off, size - 1)])
    if rep["failed"]:
        return None
    return got, rep, []


def _section_vsizes(blob):
    """섹션명 → VirtualSize. 파일 꼬리(FileAlignment 패딩)는 VirtualSize
    밖이면 **메모리에 로드되지 않는다** — 그 주소를 가리키게 하면 미매핑
    접근으로 게임이 리셋된다 (SOUNDROOM 무한 리붓 사고의 원인)."""
    import struct
    pe = struct.unpack_from("<I", blob, 0x3c)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    off = pe + 24 + opt
    out = {}
    for i in range(nsec):
        b = blob[off + i * 40:off + i * 40 + 40]
        name = b[:8].rstrip(b"\0").decode("ascii", "replace")
        vsize = struct.unpack_from("<I", b, 8)[0]
        out[name] = vsize
    return out


def _spare_tails(blob):
    """섹션 안 널 패딩 중 어디서도 참조하지 않는 영역 — 문자열 이사 공간.

    반드시 **VirtualSize 안쪽**이어야 한다 — 그 밖의 파일 꼬리는 메모리에
    안 올라간다. .data 꼬리는 0 초기화 런타임 변수일 수 있고(SOUNDROOM 에서
    실제 참조 4곳 확인), .reloc/.pdata 는 로더 소유라 제외한다.
    .text/.rdata 의 매핑 안쪽 꼬리만, 인바운드 참조 0 일 때만.
    """
    import struct
    from kitae.core import pestr
    from kitae.build import relocate
    out = []
    secs = pestr.sections(blob)
    vsizes = _section_vsizes(blob)
    vm = relocate._va_map(secs)
    for name, _va, ro, rs in secs:
        if name not in (".text", ".rdata"):
            continue
        hi = ro + min(rs, vsizes.get(name, rs))   # ★ 매핑되는 범위까지만
        i = hi
        while i > ro and blob[i - 1] == 0:
            i -= 1
        n = hi - i - 4                     # 끝 4B 는 여유로 남긴다
        if n < 48:
            continue
        lo_va = relocate.off_to_va(vm, i)
        hi_va = relocate.off_to_va(vm, hi - 1)
        if lo_va is None or hi_va is None:
            continue
        used = False
        for j in range(0, len(blob) - 3):
            v = struct.unpack_from("<I", blob, j)[0]
            if lo_va <= v <= hi_va:
                used = True
                break
        if not used:
            out.append((i, n))
    return out


def patch_all(cfg, lang, encode, base=None, verbose=False):
    """{디스크 경로: 패치된 바이트}. base 는 {이름: 이미 손댄 바이트}.

    자리에 들어가는 것은 제자리에, 넘치는 것은 남은 빈칸으로 옮기고 포인터를
    고쳐 쓴다 — kitae.build.relocate 참고.
    """
    from kitae.build import relocate, symbols, xref

    # 심볼 이름과 겹치는 문자열은 **코드 참조로 한 번 더 가른다.**
    # north01.sym 에 있다고 다 키는 아니다 — 우연히 이름만 같고 화면에만 나오는
    # 것도 많다(五稜郭, 元町, ベイエリア …). 코드가 주소를 만지는 것만 막는다.
    sym = symbols.names(cfg)
    mods = modules(cfg)

    # 한 모듈에서라도 키로 판정되면 **모든 모듈에서** 키로 본다.
    # 같은 이름이 모듈마다 다르게 나오는데(ＵＦＯできる 가 COMMONSAVE 에선 키,
    # TRFOPTIONGAME 에선 표시), 표 형태를 다 알아보지는 못하므로 안전한 쪽으로
    # 묶는다. 잘못 번역하면 증상이 조용해서 찾기가 어렵고, 못 번역하면 눈에 띈다.
    keyed = set()
    for name, doc in mods:
        risky = {e["text"]["ja"] for e in doc["entries"]
                 if ((e.get("text") or {}).get(lang) or "").strip()
                 and e["text"]["ja"] in sym}
        if not risky:
            continue
        for _off, ja, _ko, how in xref.scan(cfg, name, doc, lang, only=risky):
            if how != "display":
                keyed.add(ja)

    base = base or {}
    out, warn, blocked = {}, [], []
    for name, doc in mods:
        rows = []
        for e in doc["entries"]:
            # 비었는지는 ASCII 공백만 벗겨 본다 — str.strip() 은 EM SPACE·FIGURE SPACE 도 지워서
            # 공백만으로 된 칸 맞춤 항목(저장 슬롯 15칸 필드, 자릿수 패딩)을 미번역으로 오판했다.
            if not ((e.get("text") or {}).get(lang) or "").strip(" \t\r\n"):
                continue
            # `force` 는 키 차단을 뚫는다 — 같은 ja 가 다른 모듈에선 키라도
            # 이 자리는 표시용임을 사람이 확인했을 때만 쓴다(검토 근거를 남긴다).
            if e["text"]["ja"] in keyed and not e.get("force"):
                blocked.append((name, e["offset"], e["text"]["ja"]))
                continue
            rows.append(dict(e, text=e["text"][lang]))
        if not rows:
            continue
        # 보호 항목은 raw 로 — 인코더는 (text, raw) 를 받는다(hangul.encoder)
        fixed_texts = {e["text"][lang] for e in doc["entries"]
                       if ((e.get("text") or {}).get(lang) or "").strip(" \t\r\n") and is_fixed(e)}

        def enc(t, _enc=encode, _fixed=fixed_texts):
            return _enc(t, raw=t in _fixed)
        disc_path = doc["path"]
        blob = base.get(name) or open(original(cfg, disc_path), "rb").read()

        # 실패한 항목이 있는 결과는 **쓰면 안 된다**. apply 는 옮길 문자열의
        # 옛 자리를 먼저 비우므로, 넣을 곳을 못 찾으면 그 자리에 이미 다른
        # 문자열이 들어가 있고 포인터는 옛 자리를 가리킨 채로 남는다. 그러면
        # 화면에 엉뚱한 문장이 나온다(TRFNAMEIN 에서 실제로 겪었다).
        # 그래서 못 넣는 것을 빼고 원본에서 다시 시도한다.
        base_blob, attempt, dropped = blob, list(rows), []
        spare = _spare_tails(base_blob)     # 섹션 꼬리 패딩 — 이사 공간에 포함
        # 한 바퀴에 하나씩만 빠질 수 있으므로 항목 수만큼 돌 수 있어야 한다.
        # 6번으로 끊었더니 ITEMMENU 가 통째로 안 들어갔다.
        for _round in range(len(rows) + 1):
            got, rep = relocate.apply(base_blob, attempt, enc,
                                      extra_free=spare)
            if rep["failed"]:
                got2, rep2 = relocate.compact(base_blob, attempt, enc)
                if not rep2["failed"]:
                    got, rep = got2, rep2
                    print(f"  {name}: 빈칸이 조각나 전체 재배치로 전환")
                # compact 의 실패는 "참조를 못 찾음"/"풀이 모자람" 같은 **전체
                # 중단 표지**라 개별 항목 실패 목록이 아니다 — 이걸 apply 실패와
                # 개수로 비교해 고르면, 매 라운드 애먼 항목 하나가 지목·탈락해
                # SOUNDROOM 에서 252/282 가 떨어졌다. compact 가 실패하면 항상
                # apply 의 실제 실패 목록으로 떨군다.
            if not rep["failed"]:
                blob = got
                break
            bad = [e for e, _why in rep["failed"]]
            dropped += bad
            keep = {id(e) for e in bad}
            attempt = [e for e in attempt if id(e) not in keep]
        if dropped:
            # 소유 공간으로 안 되면 PE 에 데이터 섹션을 붙여 본다. 파일이
            # 커지므로 ISO 여유가 필요하고, 로더가 받아 줄지는 미확인이다.
            grown = _grow(cfg, name, disc_path, base_blob, rows, enc)
            if grown is not None:
                blob, rep, dropped = grown
                print(f"  {name}: 자리가 모자라 PE 섹션을 붙였다")
        for e in dropped:
            warn.append(f"{name} {e['offset']:#x}: 자리 없음 — 원문 유지  "
                        f"{e['text']!r}")
        out[disc_path] = blob
        if verbose:
            msg = f"    {name}: 제자리 {rep['kept']}개"
            if rep["moved"]:
                msg += f", 이사 {len(rep['moved'])}개"
            msg += f"  (남은 빈칸 {rep['free_left']}B)"
            print(msg)
            for old, new, nref, text in rep["moved"][:4]:
                print(f"        {old:#08x} → {new:#08x}  포인터 {nref}곳  {text}")
    if blocked and verbose:
        print(f"    심볼 이름이라 손대지 않음: {len(blocked)}개 "
              f"({', '.join(sorted({b[2] for b in blocked})[:5])} …)")
    if blocked:
        # 무엇이 왜 막혔는지 남긴다 — 번역이 안 나오는 이유를 찾을 때 본다
        p = os.path.join(cfg.data_dir, "untranslatable.json")
        doc = {"note": "조회 키라서 번역하지 않은 문자열. docs/UI-TEXT.md 참고",
               "count": len(blocked),
               "entries": [{"module": m, "offset": f"{o:#08x}", "ja": t}
                           for m, o, t in sorted(blocked)]}
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    for w in warn:
        print(f"  ⚠ {w}")
    return out, warn
