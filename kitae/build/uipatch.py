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


def patch_all(cfg, lang, encode, base=None):
    """{디스크 경로: 패치된 바이트}. base 는 {이름: 이미 손댄 바이트}.

    자리에 들어가는 것은 제자리에, 넘치는 것은 남은 빈칸으로 옮기고 포인터를
    고쳐 쓴다 — kitae.build.relocate 참고.
    """
    from kitae.build import relocate

    base = base or {}
    out, warn = {}, []
    for name, doc in modules(cfg):
        rows = [dict(e, text=(e.get("text") or {}).get(lang) or "")
                for e in doc["entries"]
                if ((e.get("text") or {}).get(lang) or "").strip()]
        if not rows:
            continue
        disc_path = doc["path"]
        blob = base.get(name) or open(original(cfg, disc_path), "rb").read()

        blob, rep = relocate.apply(blob, rows, encode)
        out[disc_path] = blob
        msg = f"  {name}: 제자리 {rep['kept']}개"
        if rep["moved"]:
            msg += f", 이사 {len(rep['moved'])}개"
        msg += f"  (남은 빈칸 {rep['free_left']}B)"
        print(msg)
        for old, new, nref, text in rep["moved"][:4]:
            print(f"      {old:#08x} → {new:#08x}  포인터 {nref}곳  {text}")
        for e, why in rep["failed"]:
            warn.append(f"{name} {e['offset']:#x}: 자리 없음({why})  "
                        f"{e['text']!r}")
    for w in warn:
        print(f"  ⚠ {w}")
    return out, warn
