# -*- coding: utf-8 -*-
"""번역 대상 텍스트를 translation/<SCRIPT>.json 으로 뽑는다."""
import os

from kitae import translation
from kitae.config import Config

GROUP = "work"
HELP = "게임에서 대사를 뽑아 번역 파일을 만든다/갱신한다"

NARRATION = {"独白", "ナレーション", "説明", "文字", "システム", "メモ", "メッセージ"}


def configure(p):
    p.add_argument("scripts", nargs="*", help="시나리오 이름 (없으면 설정의 scripts)")


def _build(cfg, script):
    """게임 데이터에서 항목 목록을 만든다."""
    from kitae.core.cab import Cab
    from kitae.core.windows import script_windows, display_len
    from kitae.core import ebdis, scenemap

    from kitae.build import uipatch
    plot = Cab(uipatch.original(cfg, "/RESOURCE/PLOT.CB"))
    mtg = Cab(uipatch.original(cfg, "/RESOURCE/MTG.CB"))
    wins, strs = script_windows(script, plot, mtg)

    eb = plot.read(script.upper() + ".EB")
    sym = ebdis.speaker_names(plot)
    spk, op = {}, {}
    for _off, o, w, s in ebdis.messages(eb):
        if w is not None:
            spk[w] = sym[s] if s is not None and s < len(sym) else "?"
            op[w] = o

    # 창이 어느 씬·날짜·시간대에 속하는지 — 번역은 날짜순으로 진행한다
    where = scenemap.window_info(cfg, script)

    src = cfg["source"]
    entries = []
    for m in wins:
        w = m["window"]
        who = spk.get(w, "?")
        o = op.get(w)
        kind = ("선택지" if o == 0x74 else "대기" if o == 0x73
                else "독백" if who == "独白"
                else "나레이션" if who in NARRATION else "대사")
        at = where.get(w) or {}
        for n, si in enumerate(m["strings"]):
            entries.append({
                "window": w, "line": n, "speaker": who, "kind": kind,
                "scene": at.get("scene"), "date": at.get("date"),
                "slot": at.get("slot"), "place": at.get("place"),
                "voice": m["wave"], "chars": display_len(strs[si]),
                "text": {src: strs[si]},
            })
    return {"script": script.upper(), "source": src, "entries": entries}


def run(args):
    cfg = Config.load()
    scripts = [s.upper() for s in (args.scripts or cfg["scripts"])]
    for script in scripts:
        try:
            fresh = _build(cfg, script)
        except FileNotFoundError as e:
            print(f"{script}: 원본 아카이브가 없습니다 ({e}). "
                  f"먼저 kitae unpack --all 로 꺼내세요")
            return 1
        doc = translation.load(cfg, script)
        merged = translation.merge(doc, fresh, cfg["languages"])
        p = translation.save(cfg, script, merged)
        st = translation.stats(merged, cfg["languages"])
        summary = "  ".join(f"{k} {v[0]}/{v[1]}" for k, v in st.items())
        print(f"{os.path.relpath(p, cfg.root)}  {len(merged['entries'])}줄   {summary}")
    return 0
