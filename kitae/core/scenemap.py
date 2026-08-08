# -*- coding: utf-8 -*-
"""창(window)이 어느 씬·날짜·시간대에 속하는지 알아낸다.

번역은 날짜·시간 순으로 진행한다. 그런데 **창 번호 순서가 곧 날짜 순서는
아니다** — 33개 스크립트가 여러 날짜에 걸쳐 있고 그중 18개는 순서가 어긋난다.
`風呂` 는 14일치가 한 파일에 섞여 있다. 그래서 창마다 날짜를 붙여 둔다.

## 어떻게 알아내나

씬 제목은 `SCN/INIS.CB` 의 `P##.INI` 에 있고, 그 자체가 트리거 조건이다:

    P01S019=○８月１日／夜／ローズヒル南平岸／春野家／書斎
             날짜  시간대  장소        세부

어느 창이 어느 씬에 속하는지는 **EB 바이트코드**가 정한다. EB 의 블록 하나가
씬 하나이고, 블록의 진입점 표에서 코드 오프셋을 얻는다. 그 오프셋 구간 안에서
실행되는 `0x6B`/`0x6C`(창 표시) 명령의 피연산자가 그 씬의 창들이다.

**주의** — 블록마다 `0xE8`~`0xEC` 진입점이 다섯 개 있는데 이건 모든 블록이
공유하는 공통 핸들러라 전부 같은 오프셋을 가리킨다. 이걸 구간 경계로 쓰면
모든 블록이 같은 자리에서 시작하는 것처럼 보인다. **`0x20` 이상만** 그 씬 고유의
진입점이다.

## ★ 날짜를 번역 범위로 쓰지 말 것

여기서 나오는 날짜는 **제작진이 적어 둔 이야기상의 날짜**이지 플레이어가 그걸
언제 보는지가 아니다. `.INI` 는 어떤 코드도 대조하지 않는 문서일 뿐이다
(→ `kitae.build.scenes` 머리말).

`KAORU` 첫 장면은 제목이 `８月４日／午前／北海大／正門前` 인데, 北海大 는 첫날부터
갈 수 있는 장소라 **８월 ２일에도 나온다.** 장소에 가면 걸리는 만남이라
날짜가 문을 잠그지 않는다.

그래서 `date == "08-02"` 같은 조건으로 번역 범위를 자르면 반드시 구멍이 생긴다.
실제로 두 번 겪었다 — [[kotori_02_rest]] 의 아침 장면 １１２줄, 그리고 이 건.
**번역 단위는 스크립트 전체로 잡고**, 날짜는 순서를 정하는 데만 쓴다.
"""
import bisect
import collections
import io
import json
import os
import re

DATE = re.compile(r"^([0-9０-９]+)月([0-9０-９]+)日")
SLOTS = ("朝", "午前", "昼", "午後", "夕方", "夜")
TITLE = re.compile(r"^P\d+S(\d+)=○(.*)$", re.M)
PLOT = re.compile(r"^P(\d+)\s*=\s*(\S+)", re.M)
_Z = str.maketrans("０１２３４５６７８９", "0123456789")


def _int(s):
    return int(s.translate(_Z))


def plots(inis_cab):
    """{플롯번호: 시나리오명} — PLOTS.INI 가 정의한다."""
    for n in inis_cab.names:
        if n.upper().startswith("PLOTS"):
            txt = inis_cab.read(n).decode("cp932", "replace")
            return {int(a): b for a, b in PLOT.findall(txt)}
    return {}


def titles(inis_cab, pid):
    """{씬번호: 제목} — 없으면 빈 dict."""
    want = f"P{pid:02d}.INI".upper()
    name = next((n for n in inis_cab.names if n.upper() == want), None)
    if not name:
        return {}
    txt = inis_cab.read(name).decode("cp932", "replace")
    return {int(a): b.strip() for a, b in TITLE.findall(txt)}


def parse_title(t):
    """제목 → (날짜, 시간대, 장소). 날짜는 (월, 일) 또는 None."""
    f = [x.strip() for x in t.split("／")]
    d = DATE.match(f[0]) if f else None
    date = (_int(d.group(1)), _int(d.group(2))) if d else None
    slot = next((x for x in f if x in SLOTS), None)
    rest = [x for x in f[1:] if x not in SLOTS]
    return date, slot, "／".join(rest)


def scene_windows(plot_cab, script):
    """{씬번호: [창번호]} — EB 에서 뽑는다. EB 가 없으면 빈 dict."""
    from kitae.core import ebdis
    try:
        eb = plot_cab.read(script.upper() + ".EB")
    except Exception:
        return {}
    try:
        blocks, _t2, _lb = ebdis.parse_blocks(eb)
    except Exception:
        return {}
    # 0x20 이상만 씬 고유의 진입점 (0xE8~0xEC 는 공통 핸들러)
    starts = sorted((min(c for l, c in b["entries"] if l >= 0x20), b["index"])
                    for b in blocks if any(l >= 0x20 for l, _c in b["entries"]))
    if not starts:
        return {}
    bounds = [s for s, _ in starts]
    out = collections.defaultdict(set)
    for off, op, w, _spk in ebdis.messages(eb):
        if op in (0x6B, 0x6C):
            i = bisect.bisect_right(bounds, off) - 1
            if i >= 0:
                out[starts[i][1]].add(w)
    return {k: sorted(v) for k, v in out.items()}


def build(cfg):
    """전 스크립트의 씬 지도를 만든다. {시나리오: {씬번호: {...}}}"""
    from kitae.core.cab import Cab
    from kitae.build import uipatch
    plot = Cab(uipatch.original(cfg, "/RESOURCE/PLOT.CB"))
    inis = Cab(uipatch.original(cfg, "/RESOURCE/SCN/INIS.CB"))
    out = {}
    for pid, nm in sorted(plots(inis).items()):
        tt = titles(inis, pid)
        win = scene_windows(plot, nm)
        if not win:
            continue
        scenes = {}
        for sid, ws in sorted(win.items()):
            t = tt.get(sid, "")
            date, slot, place = parse_title(t)
            scenes[str(sid)] = {
                "title": t, "place": place, "windows": ws,
                "date": f"{date[0]:02d}-{date[1]:02d}" if date else None,
                "slot": slot,
            }
        out[nm] = {"plot": pid, "scenes": scenes}
    return out


def save(cfg):
    doc = build(cfg)
    p = os.path.join(cfg.data_dir, "scenes.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return p, doc


def load(cfg):
    p = os.path.join(cfg.data_dir, "scenes.json")
    if not os.path.exists(p):
        return save(cfg)[1]
    with io.open(p, encoding="utf-8") as fh:
        return json.load(fh)


def window_info(cfg, script):
    """{창번호: {scene, date, slot, place}} — 그 스크립트의 창별 정보."""
    doc = load(cfg)
    ent = doc.get(script) or doc.get(script.lower()) or doc.get(script.upper())
    if not ent:
        return {}
    out = {}
    for sid, s in ent["scenes"].items():
        for w in s["windows"]:
            # 한 창이 여러 씬에 걸치면 먼저 나온 씬을 쓴다
            out.setdefault(w, {"scene": int(sid), "date": s["date"],
                               "slot": s["slot"], "place": s["place"]})
    return out


def order_key(info):
    """날짜 → 시간대 → 씬 순으로 정렬하는 열쇠. 날짜 없는 것은 뒤로."""
    d = info.get("date") or "99-99"
    s = info.get("slot")
    return (d, SLOTS.index(s) if s in SLOTS else 9, info.get("scene", 9999))
