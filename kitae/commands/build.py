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
    p.add_argument("scripts", nargs="*",
                   help="시나리오 (없으면 설정의 scripts) / `image` = 이미지만 빌드")
    p.add_argument("--lang", help="주입할 언어 (기본 설정의 target)")
    p.add_argument("--no-font", action="store_true", help="폰트 주입 생략")
    p.add_argument("--dry-run", action="store_true", help="디스크는 건드리지 않는다")
    p.add_argument("--inject", action="store_true",
                   help="image: 패키징 전에 jaguk 렌더를 다시 돌린다 "
                        "(injected 캐시 비움 — 기본은 캐시/즉석 생성. "
                        "렌더만 따로는 `kitae inject image`)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="자세한 로그 — 대본별 번역 수, 타이밍 창별 변경, "
                        "UI 재배치 상세 (기본은 과정·파일 단위 요약)")


def run(args):
    cfg = Config.load()
    lang = cfg.check_lang(args.lang or cfg["target"])

    # `kitae build image` — 이미지만 (jaguk compose → CB → 디스크).
    # 대사·폰트는 직전 빌드의 work/build 산출물을 재사용한다.
    if args.scripts and args.scripts[0].lower() == "image":
        from kitae.build import runner
        return runner.build_images(cfg, rerender=args.inject, lang=lang)
    scripts = [s.upper() for s in (args.scripts or cfg["scripts"])]
    src = cfg["source"]

    docs = {}
    stats = []
    for s in scripts:
        d = translation.load(cfg, s)
        if not d:
            print(f"{s}: translation 파일이 없습니다 — kitae extract {s}")
            return 1
        docs[s] = d
        done, tot = translation.stats(d, [lang])[lang]
        stats.append((s, done, tot))
    print(f"번역: {sum(d for _, d, _ in stats):,}"
          f"/{sum(t for _, _, t in stats):,}줄 ({len(scripts)}대본)")
    if args.verbose:
        for s, done, tot in stats:
            print(f"    {s}: {done}/{tot}줄")

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
    return runner.build(cfg, scripts, lang, want_font=not args.no_font,
                        verbose=args.verbose)
