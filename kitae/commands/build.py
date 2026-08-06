# -*- coding: utf-8 -*-
"""번역을 게임에 주입해 실행 가능한 이미지를 만든다."""
import glob
import os
import shutil

from kitae import translation
from kitae.config import Config

GROUP = "build"
HELP = "폰트·대사·타이밍을 넣어 dist/ 를 만든다"


def configure(p):
    p.add_argument("scripts", nargs="*", help="시나리오 (없으면 설정의 scripts)")
    p.add_argument("--lang", help="주입할 언어 (기본 설정의 target)")
    p.add_argument("--no-font", action="store_true", help="폰트 주입 생략")
    p.add_argument("--dry-run", action="store_true", help="디스크는 건드리지 않는다")


def run(args):
    cfg = Config.load()
    lang = cfg.check_lang(args.lang or cfg["target"])
    scripts = [s.upper() for s in (args.scripts or cfg["scripts"])]
    src = cfg["source"]

    docs = {}
    for s in scripts:
        d = translation.load(cfg, s)
        if not d:
            print(f"{s}: translation 파일이 없습니다 — kitae extract {s}")
            return 1
        docs[s] = d
        done, tot = translation.stats(d, [lang])[lang]
        print(f"{s}: {lang} {done}/{tot}줄 번역됨")

    if args.dry_run:
        print("\n--dry-run: 여기서 멈춥니다")
        return 0

    # 이 아래는 기존 파이프라인 모듈에 위임한다. 각 단계는
    #   1) 필요한 글자를 폰트에 주입
    #   2) .SMF 재작성 (.MSG 오프셋 재계산) → PLOT.CB 재포장
    #   3) 글자 수가 바뀐 창의 MTG 타이밍 리샘플
    #   4) 원본 트랙 사본에 두 아카이브를 제자리 패치
    #   5) 같은 크기인 폰트 DLL 교체
    # 순서를 지켜야 한다 — 자세한 이유는 docs/pipeline.md 참고.
    from kitae.build import runner
    return runner.build(cfg, scripts, lang, want_font=not args.no_font)
