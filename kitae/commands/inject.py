# -*- coding: utf-8 -*-
"""kitae inject — 번역 주입 렌더 (원장 → 주입 트리, 게임 파일은 안 건드림).

    image   jaguk 원장(translation/images/lettering.json)을 렌더해
            images/injected/ 에 저장한다. 게임 패키징은 `kitae build image`.

텍스트 계열은 여기 없다 — 텍스트는 중간 트리 없이 `kitae build` 가 원장에서
바로 아카이브로 넣는다. 이미지는 사람이 산출물을 눈으로 검수하는 단계가
있어서 렌더(inject)와 패키징(build)이 갈라져 있다 (raiki inject image 와
같은 관계). jaguk 은 렌더 엔진으로만 쓴다 — 서브커맨드를 노출하지 않는다.
"""
import sys

GROUP = "build"
HELP = "이미지 렌더 — image: jaguk 원장 → images/injected (패키징은 kitae build image)"


def configure(p):
    p.add_argument("items", nargs="*", help="렌더할 것 (image — 기본)")
    p.add_argument("--only", default="", help="파일명 부분일치 필터")
    p.add_argument("--list", action="store_true", dest="list_only",
                   help="대상만 나열")


def run(args):
    from kitae.config import Config
    cfg = Config.load()
    items = args.items or ["image"]
    if items != ["image"]:
        print(f"모르는 아이템: {items} — 지원: image")
        return 1
    root = cfg.typelet_root()
    if root and root not in sys.path:
        sys.path.insert(0, root)
    try:
        from typelet import config as tconf
        from typelet import render as trender
    except ImportError:
        print("typelet(type-lettering)을 찾지 못했습니다 — kitae.config.json 의 "
              "paths.typelet 또는 환경변수 TYPELET_ROOT 를 확인하세요.")
        return 1
    from pathlib import Path
    project = tconf.load_path(Path(cfg.path("images", "jaguk.json")))
    return trender.run(project, only=args.only, list_only=args.list_only)
