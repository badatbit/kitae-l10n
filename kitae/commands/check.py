# -*- coding: utf-8 -*-
"""빌드에 필요한 것들이 갖춰졌는지 점검."""
import glob
import importlib
import io
import json
import os

from kitae.config import CONFIG_NAME, Config

GROUP = "setup"
HELP = "환경·원본·폰트가 준비됐는지 확인한다"


def _row(ok, label, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'}  {label:<22} {detail}")
    return ok


def glossary(cfg, lang):
    """확정 표기를 어긴 줄. [(파일, 창, 줄, 일본어, 번역, 기대한 표기)]

    긴 표기부터 지워 나간다 — `北海大学` 를 먼저 처리하지 않으면 그 안의
    `北海大` 가 걸려서 멀쩡한 줄을 어겼다고 한다.
    """
    p = cfg.path("translation", "glossary.json")
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8") as fh:
        terms = json.load(fh)["terms"]
    terms.sort(key=lambda t: -len(t["ja"]))

    bad = []
    root = cfg.path("translation")
    for f in sorted(glob.glob(os.path.join(root, "**", "*.json"), recursive=True)):
        with io.open(f, encoding="utf-8") as fh:
            try:
                doc = json.load(fh)
            except ValueError:
                continue
        if not isinstance(doc, dict) or "entries" not in doc:
            continue
        for e in doc["entries"]:
            ja, ko = e["text"]["ja"], (e["text"].get(lang) or "").strip()
            if not ko:
                continue
            rest_ja, rest_ko = ja, ko
            for t in terms:
                while t["ja"] in rest_ja:
                    rest_ja = rest_ja.replace(t["ja"], "", 1)
                    if t["ko"] in rest_ko:
                        rest_ko = rest_ko.replace(t["ko"], "", 1)
                    else:
                        bad.append((os.path.relpath(f, cfg.root),
                                    e.get("window"), e.get("line"),
                                    ja, ko, t["ko"]))
                        break
    return bad


def run(args):
    cfg = Config.load()
    print(f"저장소: {cfg.root}")
    ok = True

    ok &= _row(cfg.exists, CONFIG_NAME,
               "" if cfg.exists else "kitae init 을 먼저 실행하세요")

    for mod, why in (("PIL", "이미지 변환"), ("capstone", "역어셈블(선택)")):
        try:
            importlib.import_module(mod)
            _row(True, mod, why)
        except ImportError:
            if mod == "capstone":
                _row(True, mod, f"{why} — 없음, 선택 사항")
            else:
                ok &= _row(False, mod, f"{why} — pip install pillow")

    d = cfg.dir("orig_dir")
    has_dir = bool(cfg["orig_dir"]) and os.path.isdir(d)
    ok &= _row(has_dir, "원본 덤프", d or "미설정")
    if has_dir:
        track = cfg.track(3)
        ok &= _row(bool(track), "데이터 트랙",
                   os.path.basename(track) if track else "track03 을 못 찾음")
        gdi = cfg.gdi()
        _row(bool(gdi), ".gdi", os.path.basename(gdi) if gdi else "없음(선택)")

    ttf = cfg["font"].get("ttf")
    ttf_path = cfg.path(ttf) if ttf else ""
    _row(bool(ttf) and os.path.exists(ttf_path), "폰트",
         ttf_path or "미설정 — 번역 언어에 새 글자가 필요하면 설정해야 함")

    langs = cfg["languages"]
    ok &= _row(cfg["source"] in langs and cfg["target"] in langs, "언어",
               f"{langs}  원문 {cfg['source']} → {cfg['target']}")

    n = 0
    if os.path.isdir(cfg.translation_dir):
        n = len([f for f in os.listdir(cfg.translation_dir)
                 if f.lower().endswith(".json")])
    _row(True, "번역 파일", f"{n}개 (translation/)")

    bad = glossary(cfg, cfg["target"])
    if bad is None:
        _row(True, "확정 표기", "glossary.json 없음 — 검사 생략")
    else:
        ok &= _row(not bad, "확정 표기",
                   "일치" if not bad else f"어긋난 곳 {len(bad)}곳")
        for f, w, ln, ja, ko, want in bad[:10]:
            print(f"          {f} [{w}.{ln}]  `{want}` 이어야 한다")
            print(f"            원문 {ja}")
            print(f"            번역 {ko}")
        if len(bad) > 10:
            print(f"          … {len(bad) - 10}곳 더")

    print("\n준비됨" if ok else "\n미비 항목이 있습니다")
    return 0 if ok else 1
