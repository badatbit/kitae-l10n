"""Build (and read back) the translation workbook for one script.

The workbook is a UTF-8 TSV, one row per displayed line, carrying everything a
translator needs plus the identity needed to inject the result back:

    window   message window index (matches the EB 0x6B operand and MTG data)
    line     line number inside that window (0-based)
    speaker  who is talking, from EB opcode 0x6A + north01.sym
    kind     대사 / 독백 / 나레이션 / 선택지 / 대기
    voice    voice file, empty when the line is silent
    chars    drawn character count of the source (markup excluded)
    source   the original cp932 line
    target   translation -- fill this in; empty means "not translated yet"

Round-tripping keeps `window`/`line` as the key, so rows may be reordered or
partially filled without breaking injection.

Usage:
    python workbook.py KOTORI_01                # create/refresh the TSV
    python workbook.py KOTORI_01 --stats        # translation progress
"""
import io, os, sys, csv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cab import Cab
from windows import script_windows, display_len
import ebdis

DUMP = os.path.join(HERE, "..", "dump")
PLOT_CB = os.path.join(DUMP, "plot", "PLOT.CB")
MTG_CB = os.path.join(DUMP, "scn", "MTG.CB")
COLS = ["window", "line", "speaker", "kind", "voice", "chars", "source", "target"]

NARRATION = {"独白", "ナレーション", "説明", "文字", "システム", "メモ", "メッセージ"}


def path_for(script):
    return os.path.join(DUMP, "translate", f"{script.upper()}.tsv")


def build(script):
    plot_cab, mtg_cab = Cab(PLOT_CB), Cab(MTG_CB)
    wins, strs = script_windows(script, plot_cab, mtg_cab)

    eb = plot_cab.read(script.upper() + ".EB")
    sym = ebdis.speaker_names(plot_cab)
    spk, kindop = {}, {}
    for off, op, w, s in ebdis.messages(eb):
        if w is None:
            continue
        spk[w] = sym[s] if s is not None and s < len(sym) else "?"
        kindop[w] = op

    rows = []
    for m in wins:
        w = m["window"]
        who = spk.get(w, "?")
        op = kindop.get(w)
        if op == 0x74:
            kind = "선택지"
        elif op == 0x73:
            kind = "대기"
        elif who in NARRATION:
            kind = "독백" if who == "独白" else "나레이션"
        else:
            kind = "대사"
        for n, si in enumerate(m["strings"]):
            rows.append(dict(window=w, line=n, speaker=who, kind=kind,
                             voice=m["wave"], chars=display_len(strs[si]),
                             source=strs[si], target=""))
    return rows


def load(script):
    """Read an existing workbook back as {(window, line): row}."""
    p = path_for(script)
    if not os.path.exists(p):
        return {}
    out = {}
    with io.open(p, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out[(int(r["window"]), int(r["line"]))] = r
    return out


def save(script, rows):
    p = path_for(script)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, COLS, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        wr.writeheader()
        for r in rows:
            wr.writerow({c: r.get(c, "") for c in COLS})
    return p


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    script = sys.argv[1]
    if "--stats" in sys.argv:
        rows = list(load(script).values())
        done = sum(1 for r in rows if r.get("target", "").strip())
        print(f"{script}: {done}/{len(rows)} lines translated "
              f"({done / max(len(rows), 1) * 100:.1f}%)")
        return

    fresh = build(script)
    old = load(script)                       # keep any work already done
    kept = 0
    for r in fresh:
        prev = old.get((r["window"], r["line"]))
        if prev and prev.get("target", "").strip():
            r["target"] = prev["target"]
            kept += 1
    p = save(script, fresh)
    kinds = {}
    for r in fresh:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"{p}\n  {len(fresh)} lines  {kinds}  (kept {kept} existing translations)")


if __name__ == "__main__":
    main()
