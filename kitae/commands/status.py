# -*- coding: utf-8 -*-
"""번역 진행 상황."""
import os

from kitae import translation
from kitae.config import Config

GROUP = "work"
HELP = "언어별 번역 진행률을 보여준다"


def configure(p):
    p.add_argument("scripts", nargs="*")
    p.add_argument("--by-kind", action="store_true", help="종류별로 나눠 본다")


def run(args):
    cfg = Config.load()
    langs = cfg["languages"]
    scripts = [s.upper() for s in (args.scripts or cfg["scripts"])]

    head = f"{'script':<14}{'lines':>7}" + "".join(f"{l:>12}" for l in langs)
    print(head)
    print("-" * len(head))
    totals = {l: [0, 0] for l in langs}
    for script in scripts:
        doc = translation.load(cfg, script)
        if not doc:
            print(f"{script:<14}{'-':>7}   (translation 파일 없음 — kitae extract)")
            continue
        st = translation.stats(doc, langs)
        row = f"{script:<14}{len(doc['entries']):>7}"
        for l in langs:
            done, tot = st[l]
            totals[l][0] += done
            totals[l][1] += tot
            row += f"{done:>6}/{tot:<5}" if tot else f"{'-':>12}"
        print(row)

        if args.by_kind:
            kinds = {}
            for e in doc["entries"]:
                k = e.get("kind", "?")
                d = kinds.setdefault(k, {l: [0, 0] for l in langs})
                for l in langs:
                    d[l][1] += 1
                    if ((e.get("text") or {}).get(l) or "").strip():
                        d[l][0] += 1
            for k in sorted(kinds):
                cells = "".join(f"{kinds[k][l][0]:>6}/{kinds[k][l][1]:<5}"
                                for l in langs)
                print(f"  {k:<12}{'':>7}{cells}")

    print("-" * len(head))
    row = f"{'TOTAL':<14}{totals[langs[0]][1]:>7}"
    for l in langs:
        done, tot = totals[l]
        pct = f"{done / tot * 100:.0f}%" if tot else "-"
        row += f"{done:>6}/{tot:<3}{pct:>3}"
    print(row)
    return 0
