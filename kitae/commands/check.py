# -*- coding: utf-8 -*-
"""빌드에 필요한 것들이 갖춰졌는지 점검."""
import importlib
import os

from kitae.config import CONFIG_NAME, Config

GROUP = "setup"
HELP = "환경·원본·폰트가 준비됐는지 확인한다"


def _row(ok, label, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'}  {label:<22} {detail}")
    return ok


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

    print("\n준비됨" if ok else "\n미비 항목이 있습니다")
    return 0 if ok else 1
