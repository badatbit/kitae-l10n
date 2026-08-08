# -*- coding: utf-8 -*-
"""kitae gui — 번역 리뷰 GUI 를 띄운다 (로컬 웹).

원장(`translation/**.json`)은 읽기만 하고, 판정과 메모는 `data/review.json` 에
따로 쌓는다. 자세한 설명은 tools/review_server.py 머리말.

이름이 `review` 가 아닌 이유 — `kitae review` 는 **번역자가 남긴 질의(ask)** 를
md 로 내고 되돌리는 별개 커맨드다. 둘은 하는 일이 다르다. GUI 는 훑어보고
판정하는 곳, `review` 는 문구를 실제로 고쳐 원장에 반영하는 곳이다.
"""
import os
import subprocess
import sys

GROUP = "inspect"
HELP = "번역 리뷰 GUI (브라우저)"

TOOL = os.path.join("tools", "review_server.py")


def configure(p):
    p.add_argument("--port", type=int, default=8766,
                   help="포트 (기본 8766 — raiki gui 가 8765 를 쓴다)")
    p.add_argument("--no-open", action="store_true", dest="no_open",
                   help="브라우저를 자동으로 열지 않음")


def run(args):
    from kitae.config import Config
    cfg = Config.load()
    path = cfg.path(TOOL)
    if not os.path.exists(path):
        print(f"{TOOL} 이 없습니다")
        return 2
    cmd = [sys.executable, "-X", "utf8", path, "--port", str(args.port)]
    if args.no_open:
        cmd.append("--no-open")
    return subprocess.call(cmd, cwd=cfg.root)
