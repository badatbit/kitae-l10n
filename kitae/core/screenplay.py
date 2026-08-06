"""Build an annotated screenplay for one scenario script.

Merges every source we can currently read:

  exact, from SCN/INIS.CB   scene titles, stage directions (developer comments)
  exact, from SCN/SCV.CB    speaker channels (CTRFLipControll), resources,
                            cut timeline (ElmPlaySound / ElmMaterial2D / ...)
  exact, from PLOT.CB       dialogue text (SMF)
  exact, from MTG.CB        per-window voice file (.WST) and character timing (.SET)

What is NOT yet known is which scene each message window belongs to: the message
flow lives in the EB bytecode, which is not decoded. So the scene script and the
message stream are emitted as two sections, with the verified overlap called out.

Usage:
    python script.py KOTORI_01 [out-file]
"""
import os, io, re, sys, struct, collections
HERE = os.path.dirname(os.path.abspath(__file__))

from kitae.core.cab import Cab, smf_strings
from kitae.core.clss import parse, named_field
from kitae.core.windows import script_windows
from kitae.core import ebdis

DUMP = os.path.join(HERE, "..", "dump")
INIS = os.path.join(DUMP, "scn", "inis")


def parse_ini(path):
    sec, out = None, collections.OrderedDict()
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line:
                continue
            m = re.match(r"^\[(.+)\]$", line)
            if m:
                sec = m.group(1)
                out.setdefault(sec, [])
                continue
            if "=" in line and sec is not None:
                k, v = line.split("=", 1)
                out[sec].append((k, v))
    return out


def clean(s):
    """Trim the stray tail bytes seen after some NAME fields."""
    return s.split("\x00")[0].strip()


def _emit_msg(w, m, win_speaker, strs, tag=""):
    spk = win_speaker.get(m["window"], "-")
    voice = m["wave"] or ("무음" if m["want"] else "-")
    flag = "" if m["ok"] else " ⚠글자수"
    w.write(f"      [{m['window']:>4}] {spk:<7}{tag:<4} {voice:<11}{flag}\n")
    for i in m["strings"]:
        w.write(f"             {strs[i]}\n")


def scene_info(scv_cab, scene):
    """Speakers, resources and cut timeline for one scene."""
    try:
        buf = scv_cab.read(scene + ".SCV")
    except (ValueError, NotImplementedError):
        return None
    root, objs = parse(buf)
    speakers, res, cuts = [], [], []

    def walk(o):
        if o.cls == "CTRFLipControll":
            n = clean(named_field(o.payload))
            if n:
                speakers.append(n)
        elif o.cls in ("CTRFResourceWave", "CTRFResourceMidi", "CTRFResourceMp3",
                       "CTRFResourceMovie", "CTRFResource"):
            for s in re.findall(rb"[!-~]{4,}", o.payload):
                t = s.decode("ascii")
                if "/" in t or "." in t:
                    res.append(t)
                    break
        elif o.cls == "CTRFCutScheduler":
            elems = []
            def sub(x):
                for c in x.children:
                    if c.cls.startswith("Elm"):
                        elems.append(c.cls[3:])
                    sub(c)
            sub(o)
            cuts.append(elems)
        for c in o.children:
            walk(c)

    for o in objs:
        if o.cls == "CTRFResourceList":
            for s in re.findall(rb"[!-~]{4,}", o.payload):
                res.append(s.decode("ascii"))
        walk(o)

    seen, ures = set(), []
    for r in res:
        if r not in seen:
            seen.add(r)
            ures.append(r)
    return dict(speakers=speakers, resources=ures, cuts=cuts)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    script = sys.argv[1]

    plot_cab = Cab(os.path.join(DUMP, "plot", "PLOT.CB"))
    mtg_cab = Cab(os.path.join(DUMP, "scn", "MTG.CB"))
    scv_cab = Cab(os.path.join(DUMP, "scn", "SCV.CB"))

    # script -> plot id
    plots = {v.upper(): k.upper() for k, v in parse_ini(
        os.path.join(INIS, "PLOTS.INI")).get("PLOTS", [])}
    plot = plots.get(script.upper())
    if not plot:
        print(f"unknown script {script}; known: {sorted(plots)[:8]} ...")
        return

    ini_path = next((os.path.join(INIS, f) for f in os.listdir(INIS)
                     if f.rsplit(".", 1)[0].upper() == plot), None)
    ini = parse_ini(ini_path) if ini_path else {}
    scenes = ini.get(plot, [])

    wins, strs = script_windows(script, plot_cab, mtg_cab)

    # speaker per window + which EB scene block each message sits in
    eb = plot_cab.read(script.upper() + ".EB")
    sym = ebdis.speaker_names(plot_cab)
    msgs = ebdis.messages(eb)
    blocks, _t2, _labels = ebdis.parse_blocks(eb)
    # scene block -> lowest code offset among its own (non-shared) labels
    starts = []
    for b in blocks:
        offs = [o for lid, o in b["entries"] if lid < 0xE0]
        if offs:
            starts.append((min(offs), b["index"]))
    starts.sort()
    stream = list(ebdis.decode(eb))
    blk_lo, blk_hi = {}, {}
    for n, (s, bi) in enumerate(starts):
        blk_lo[bi] = s
        blk_hi[bi] = starts[n + 1][0] if n + 1 < len(starts) else len(eb)

    def block_of(off):
        hit = None
        for s, bi in starts:
            if s <= off:
                hit = bi
            else:
                break
        return hit
    win_speaker, win_block, win_kind = {}, {}, {}
    for off, kind, win, spk in msgs:
        if win is None:
            continue
        win_speaker[win] = sym[spk] if spk is not None and spk < len(sym) else "?"
        win_block[win] = block_of(off)
        win_kind[win] = kind

    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        DUMP, "script", f"{script.upper()}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    w = io.open(out_path, "w", encoding="utf-8")

    w.write(f"# {script.upper()}  (플롯 {plot})  자동 생성 스크립트\n")
    w.write(f"# 씬 {len(scenes)}개 / 메시지 창 {len(wins)}개 / 문자열 {len(strs)}개\n#\n")
    w.write("# [확정] 씬 제목·연출지시(INIS), 화자채널·리소스·컷(SCV), 대사(SMF),\n")
    w.write("#        음성·타이밍(MTG), 창별 화자 + EB 씬블록(EB 옵코드 0x6A/0x6B)\n")
    w.write("# 주의: EB 씬블록 번호는 INI 씬 번호와 다르다(코드 없는 씬은 EB에서 빠짐)\n")
    w.write("=" * 78 + "\n\n")

    # ---- align EB blocks to INI scenes (order-preserving, speaker-set scored) ----
    infos = {scene: scene_info(scv_cab, scene) for scene, _ in scenes}
    blk_wins = collections.defaultdict(list)
    for m in wins:
        blk_wins[win_block.get(m["window"])].append(m)
    blk_ids = sorted(b for b in blk_wins if b is not None)
    blk_spk = {b: {win_speaker.get(m["window"], "?") for m in blk_wins[b]} for b in blk_ids}

    def compat(b, scene):
        """Score a block<->scene pairing.

        CTRFLipControll only declares speakers that have a lip-synced portrait,
        so the scene's channel list is a SUBSET of the speakers the block
        actually uses -- score by how much of the channel list the block covers.
        """
        info = infos.get(scene)
        chans = set(info["speakers"]) if info else set()
        spk = blk_spk[b]
        if not chans:
            # a scene that declares no speaker should carry no dialogue
            return 0.9 if not spk else 0.1
        if not spk:
            return 0.2
        cover = len(spk & chans) / len(chans)
        return 1.0 + cover * 2 + (0.7 if chans <= spk else 0)

    ids = [s for s, _ in scenes]
    NB, NS = len(blk_ids), len(ids)
    NEG = float("-inf")
    dp = [[NEG] * (NS + 1) for _ in range(NB + 1)]
    back = [[None] * (NS + 1) for _ in range(NB + 1)]
    dp[0][0] = 0.0
    for i in range(NB + 1):
        for j in range(NS + 1):
            if dp[i][j] == NEG:
                continue
            if j < NS and dp[i][j] > dp[i][j + 1]:           # scene has no EB code
                dp[i][j + 1], back[i][j + 1] = dp[i][j], (i, j, None)
            if i < NB and j < NS:
                v = dp[i][j] + compat(blk_ids[i], ids[j])
                if v > dp[i + 1][j + 1]:
                    dp[i + 1][j + 1], back[i + 1][j + 1] = v, (i, j, blk_ids[i])
    scene_block, i, j = {}, NB, NS
    while (i, j) != (0, 0) and back[i][j]:
        pi, pj, b = back[i][j]
        if b is not None:
            scene_block[ids[pj]] = b
        i, j = pi, pj
    matched = 0
    for s, b in scene_block.items():
        chans = set(infos[s]["speakers"]) if infos.get(s) else set()
        if chans and chans <= blk_spk[b]:
            matched += 1
    with_chan = sum(1 for s, _ in scenes if infos.get(s) and infos[s]["speakers"])
    w.write(f"■ 씬별 대본  (EB 블록 {NB}개 → INI 씬 {NS}개 정렬)\n")
    w.write(f"   정렬 근거: 씬이 선언한 화자채널이 그 블록의 실제 화자에 모두 포함되는가\n")
    w.write(f"   → 화자채널을 가진 씬 {with_chan}개 중 {matched}개가 완전 포함 (정렬 신뢰도)\n\n")
    for scene, title in scenes:
        info = infos.get(scene)
        w.write(f"── {scene}  {title}\n")
        if info:
            if info["speakers"]:
                w.write(f"   화자채널: {', '.join(info['speakers'])}\n")
            if info["resources"]:
                w.write(f"   리소스  : {', '.join(info['resources'][:14])}"
                        f"{' …' if len(info['resources']) > 14 else ''}\n")
            if info["cuts"]:
                w.write(f"   컷 {len(info['cuts'])}개: ")
                w.write(" | ".join(
                    f"#{i}[{','.join(sorted(set(c))) or '-'}]"
                    for i, c in enumerate(info["cuts"][:8])))
                w.write(" …\n" if len(info["cuts"]) > 8 else "\n")
        else:
            w.write("   (SCV 없음)\n")
        for k, v in ini.get(scene, []):
            w.write(f"     ·{k[-3:]}  {v}\n")

        b = scene_block.get(scene)
        if b is None:
            w.write("   (EB 코드 없음 — 무비/연출 전용 씬)\n\n")
            continue
        chans = set(info["speakers"]) if info else set()
        if not chans:
            mark = "블록경계 참고"
        elif chans <= blk_spk[b]:
            mark = "블록경계 확실"
        else:
            miss = ", ".join(sorted(chans - blk_spk[b]))
            mark = f"⚠ 블록경계 불확실 — 선언된 {miss} 이(가) 이 블록에 없음"
        w.write(f"   ── 대사 (EB 블록 #{b}, {mark}) ──\n")
        winmap = {m["window"]: m for m in blk_wins[b]}
        lo = min(o for o, _k, _w, _s in msgs
                 if _w in winmap) if winmap else None
        page_open = False
        for off, op, operand, val in stream:
            if not (blk_lo[b] <= off < blk_hi[b]):
                continue
            if op == 0x6A:                                  # set speaker
                continue
            if op in (0x78, 0x79):                          # select VSC cut
                w.write(f"      ▸ 컷 지정  cut={val & 0x3FFF}\n")
                continue
            if op == 0x73:                                  # wait for input
                m = winmap.get(val)
                if m:
                    _emit_msg(w, m, win_speaker, strs)
                w.write("      ─ (입력 대기) ─\n")
                page_open = False
                continue
            if op == 0x74:                                  # menu choice
                m = winmap.get(val)
                if m:
                    _emit_msg(w, m, win_speaker, strs, tag="선택지")
                continue
            if op in (0x6B, 0x6C):
                m = winmap.get(val)
                if m:
                    _emit_msg(w, m, win_speaker, strs)
                page_open = True
        w.write("\n")

    orphan = [m for m in wins if win_block.get(m["window"]) is None]
    if orphan:
        w.write("\n" + "=" * 78 + "\n■ 블록 미상 메시지\n")
        for m in orphan:
            w.write(f"   [{m['window']:>4}] {win_speaker.get(m['window'],'-')}\n")
            for i in m["strings"]:
                w.write(f"          {strs[i]}\n")
    w.close()

    nvoice = sum(1 for m in wins if m["wave"])
    known = sum(1 for m in wins if m["window"] in win_speaker)
    print(f"wrote {out_path}")
    print(f"  scenes={len(scenes)}  windows={len(wins)}  speaker-known={known}  "
          f"voiced={nvoice}  strings={len(strs)}  "
          f"char-mismatch={sum(1 for m in wins if not m['ok'])}")


if __name__ == "__main__":
    main()
