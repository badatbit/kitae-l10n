# -*- coding: utf-8 -*-
"""게임 폰트로 텍스트를 그려 미리 본다."""
import os

from kitae import translation
from kitae.config import Config

GROUP = "work"
HELP = "게임 폰트로 대사를 그려 PNG로 저장한다 (원문/번역 나란히 비교)"


def configure(p):
    p.add_argument("script", nargs="?", help="시나리오 (없으면 설정의 첫 항목)")
    p.add_argument("-w", "--window", help="창 번호 또는 범위 (예: 1  또는  0-8)")
    p.add_argument("-t", "--text", help="임의의 문자열을 그린다 (창 대신)")
    p.add_argument("-l", "--lang", action="append",
                   help="그릴 언어. 여러 번 주면 나란히 비교 (기본 source+target)")
    p.add_argument("--width", type=int, default=26,
                   help="한 줄 전각 글자 수 (기본 26 = 624px)")
    p.add_argument("-o", "--out", help="저장 경로 (기본 work/preview.png)")
    p.add_argument("--scale", type=int, default=1, help="확대 배수")


def _font(cfg):
    from kitae.core import font as fontmod
    # 패치본이 있으면 그걸로 — 실제 빌드와 같은 글리프를 본다
    for cand in (cfg.path(cfg["work_dir"], "build", "TRF", "TRFSTRINGS.DLL"),
                 cfg.path(cfg["work_dir"], "cb", "TRF", "TRFSTRINGS.DLL")):
        if os.path.exists(cand):
            os.environ["TRFSTRINGS_DLL"] = cand
            break
    return fontmod.Font()


def _codepage(cfg):
    from kitae.build.hangul import _read_codepage
    return _read_codepage(os.path.join(cfg.data_dir, "codepage.json"))


def _windows(arg):
    if not arg:
        return None
    if "-" in arg:
        a, b = arg.split("-", 1)
        return range(int(a), int(b) + 1)
    return [int(arg)]


def run(args):
    from kitae.core import render as R

    cfg = Config.load()
    font = _font(cfg)
    cp = _codepage(cfg)
    width = args.width * R.FULL
    langs = args.lang or [cfg["source"], cfg["target"]]
    out = cfg.path(args.out or os.path.join(cfg["work_dir"], "preview.png"))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    if args.text:
        img = R.render(args.text, font, cp, width)
    else:
        script = (args.script or cfg["scripts"][0]).upper()
        doc = translation.load(cfg, script)
        if not doc:
            print(f"{script}: translation 파일이 없습니다 — kitae extract {script}")
            return 1
        wanted = _windows(args.window)
        by_win = {}
        for e in doc["entries"]:
            if wanted is not None and e["window"] not in wanted:
                continue
            by_win.setdefault(e["window"], []).append(e)
        if not by_win:
            print("해당하는 창이 없습니다")
            return 1

        blocks = []
        for w in sorted(by_win)[:40]:
            entries = sorted(by_win[w], key=lambda e: e["line"])
            head = entries[0]
            panels = []
            for lang in langs:
                lines = []
                over = False
                for e in entries:
                    t = (e.get("text") or {}).get(lang) or ""
                    wrapped = R.wrap(t, cp, width)
                    if len(wrapped) > 1:
                        over = True
                    lines += wrapped
                title = (f"[{w}] {head.get('speaker','')} · {lang}"
                         f"{'  ⚠ 폭 초과' if over else ''}")
                panels.append((title, R.draw(lines, font, width)))
            blocks.append(R.side_by_side(panels))
        img = R.stack(blocks)

    if args.scale > 1:
        img = img.resize((img.width * args.scale, img.height * args.scale))
    img.save(out)
    print(f"{os.path.relpath(out, cfg.root)}  ({img.width}x{img.height})")
    return 0
