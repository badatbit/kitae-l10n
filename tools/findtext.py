"""Locate a line of in-game text: which SMF table, index, plot and script.

Usage:
    python findtext.py "検索したい台詞"          # substring search
    python findtext.py -c 5 "台詞"               # with N lines of context
"""
import os, io, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
TEXT = os.path.join(HERE, "..", "dump", "plot", "text")
INIS = os.path.join(HERE, "..", "dump", "scn", "inis")

# plot id -> script name, from PLOTS.INI
def plot_map():
    m, rev = {}, {}
    p = os.path.join(INIS, "PLOTS.INI")
    if os.path.exists(p):
        for line in io.open(p, encoding="utf-8"):
            line = line.strip()
            if "=" in line and line.upper().startswith("P"):
                k, v = line.split("=", 1)
                m[k.upper()] = v
                rev[v.upper()] = k.upper()
    return m, rev


def load_tables():
    tables = {}
    for fn in sorted(os.listdir(TEXT)):
        if not fn.endswith(".txt"):
            continue
        rows = []
        for line in io.open(os.path.join(TEXT, fn), encoding="utf-8"):
            idx, _, s = line.rstrip("\n").partition("\t")
            rows.append(s)
        tables[fn[:-4]] = rows
    return tables


def norm(s):
    """Fold full/half-width spaces so screenshots paste cleanly."""
    return re.sub(r"[\s　]+", "", s)


def main():
    ctx = 0
    args = sys.argv[1:]
    if args and args[0] == "-c":
        ctx = int(args[1]); args = args[2:]
    if not args:
        print(__doc__); return
    needle = norm(args[0])

    pmap, rev = plot_map()
    tables = load_tables()
    hits = 0
    for name, rows in tables.items():
        for i, s in enumerate(rows):
            if needle and needle in norm(s):
                hits += 1
                plot = rev.get(name.upper(), "?")
                print(f"\n=== {name}.SMF  string #{i}   plot {plot} ({pmap.get(plot, name)}) ===")
                lo, hi = max(0, i - ctx), min(len(rows), i + ctx + 1)
                for j in range(lo, hi):
                    mark = ">>" if j == i else "  "
                    print(f" {mark} [{j:>4}] {rows[j]}")
    if not hits:
        print("no match")
    else:
        print(f"\n{hits} match(es)")


if __name__ == "__main__":
    main()
