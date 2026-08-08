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


def _grow(cfg, name, disc_path, base_blob, rows, encode, nbytes=512):
    """PE 에 데이터 섹션을 붙이고 그 공간까지 써서 다시 배치한다.

    파일이 커지므로 **디스크 여유가 있어야 한다.** 없으면 시도하지 않는다 —
    만들어 놓고 디스크에서 거절당하면 빌드가 통째로 멈춘다.
    """
    from kitae.build import pesection, relocate
    slack = disc_slack(cfg, disc_path)
    if slack < nbytes:
        print(f"  {name}: 디스크 여유 {slack}B — 섹션을 붙일 수 없다")
        return None
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


def patch_all(cfg, lang, encode, base=None):
    """{디스크 경로: 패치된 바이트}. base 는 {이름: 이미 손댄 바이트}.

    자리에 들어가는 것은 제자리에, 넘치는 것은 남은 빈칸으로 옮기고 포인터를
    고쳐 쓴다 — kitae.build.relocate 참고.
    """
    from kitae.build import relocate, symbols

    # 심볼 이름은 절대 손대지 않는다 — 엔진이 EDL 전역변수를 이 이름으로 찾는다.
    # 한쪽만 한글이 되면 조회가 실패하고, 실패해도 조용히 초기값이 남는다.
    sym = symbols.names(cfg)
    base = base or {}
    out, warn, blocked = {}, [], []
    for name, doc in modules(cfg):
        rows = []
        for e in doc["entries"]:
            if not ((e.get("text") or {}).get(lang) or "").strip():
                continue
            if e["text"]["ja"] in sym:
                blocked.append((name, e["offset"], e["text"]["ja"]))
                continue
            rows.append(dict(e, text=e["text"][lang]))
        if not rows:
            continue
        disc_path = doc["path"]
        blob = base.get(name) or open(original(cfg, disc_path), "rb").read()

        # 실패한 항목이 있는 결과는 **쓰면 안 된다**. apply 는 옮길 문자열의
        # 옛 자리를 먼저 비우므로, 넣을 곳을 못 찾으면 그 자리에 이미 다른
        # 문자열이 들어가 있고 포인터는 옛 자리를 가리킨 채로 남는다. 그러면
        # 화면에 엉뚱한 문장이 나온다(TRFNAMEIN 에서 실제로 겪었다).
        # 그래서 못 넣는 것을 빼고 원본에서 다시 시도한다.
        base_blob, attempt, dropped = blob, list(rows), []
        # 한 바퀴에 하나씩만 빠질 수 있으므로 항목 수만큼 돌 수 있어야 한다.
        # 6번으로 끊었더니 ITEMMENU 가 통째로 안 들어갔다.
        for _round in range(len(rows) + 1):
            got, rep = relocate.apply(base_blob, attempt, encode)
            if rep["failed"]:
                got2, rep2 = relocate.compact(base_blob, attempt, encode)
                if not rep2["failed"]:
                    got, rep = got2, rep2
                    print(f"  {name}: 빈칸이 조각나 전체 재배치로 전환")
                else:
                    rep = rep2 if len(rep2["failed"]) < len(rep["failed"]) else rep
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
            grown = _grow(cfg, name, disc_path, base_blob, rows, encode)
            if grown is not None:
                blob, rep, dropped = grown
                print(f"  {name}: 자리가 모자라 PE 섹션을 붙였다")
        for e in dropped:
            warn.append(f"{name} {e['offset']:#x}: 자리 없음 — 원문 유지  "
                        f"{e['text']!r}")
        out[disc_path] = blob
        msg = f"  {name}: 제자리 {rep['kept']}개"
        if rep["moved"]:
            msg += f", 이사 {len(rep['moved'])}개"
        msg += f"  (남은 빈칸 {rep['free_left']}B)"
        print(msg)
        for old, new, nref, text in rep["moved"][:4]:
            print(f"      {old:#08x} → {new:#08x}  포인터 {nref}곳  {text}")
    if blocked:
        print(f"  심볼 이름이라 손대지 않음: {len(blocked)}개 "
              f"({', '.join(sorted({b[2] for b in blocked})[:5])} …)")
    for w in warn:
        print(f"  ⚠ {w}")
    return out, warn
