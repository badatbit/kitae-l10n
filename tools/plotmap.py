"""Reconstruct the scenario schedule from scene titles in the plot INIs.

Scene titles are slash-separated fields that encode when and where a scene
happens, e.g.  ○８月２日／午前／北海道庁／道庁前（ひとりの場合）
                 date    time  place       spot      condition

Writes a structured TSV plus a human-readable calendar summary.

Usage:  python plotmap.py [out-dir]     (default: ../dump/plotmap)
"""
import os, io, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
INIS = os.path.join(HERE, "..", "dump", "scn", "inis")

ZEN = str.maketrans("０１２３４５６７８９", "0123456789")
DATE_RE = re.compile(r"^([０-９0-9]{1,2})月([０-９0-9]{1,2})日")
TIMES = ["早朝", "朝", "午前中", "午前", "昼", "午後", "夕方", "夜中", "夜", "深夜"]


def as_time(field):
    """Return a normalised time slot, or '' if this field is not one.

    Handles alternation like 午前｜午後 (scene valid in either slot).
    """
    parts = [p.strip() for p in re.split(r"[｜|・]", field) if p.strip()]
    if parts and all(p in TIMES for p in parts):
        return "｜".join("午前" if p == "午前中" else p for p in parts)
    return ""


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


def parse_title(title):
    """Split a scene title into (date, time, place, detail, condition)."""
    t = title.lstrip("○●◎ ").strip()
    cond = ""
    m = re.search(r"[（(]([^）)]*)[）)]\s*$", t)
    if m:
        cond = m.group(1)
        t = t[:m.start()].strip()
    parts = [p.strip() for p in re.split(r"[／/]", t) if p.strip()]
    date = time = ""
    if parts:
        m = DATE_RE.match(parts[0])
        if m:
            date = f"{int(m.group(1).translate(ZEN)):02d}-{int(m.group(2).translate(ZEN)):02d}"
            parts = parts[1:]
    if parts:
        t = as_time(parts[0])
        if t:
            time = t
            parts = parts[1:]
    # A whole-day outing occupies the slot a time-of-day would: "琴梨と札幌デート"
    route = ""
    if parts and re.search(r"デート|と札幌|と函館|と一緒", parts[0]):
        route = parts[0]
        parts = parts[1:]
    place = parts[0] if parts else ""
    detail = "／".join(parts[1:]) if len(parts) > 1 else ""
    return date, time, route, place, detail, cond


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "dump", "plotmap")
    os.makedirs(out_dir, exist_ok=True)

    plots = {}
    pl = parse_ini(os.path.join(INIS, "PLOTS.INI"))
    for k, v in pl.get("PLOTS", []):
        plots[k.upper()] = v

    rows = []
    for fn in sorted(os.listdir(INIS)):
        if not fn.upper().endswith(".INI") or fn.upper() == "PLOTS.INI":
            continue
        plot = fn.rsplit(".", 1)[0].upper()
        ini = parse_ini(os.path.join(INIS, fn))
        resources = dict(ini.get("contain", []))
        for scene, title in ini.get(plot, []):
            date, time, route, place, detail, cond = parse_title(title)
            nev = len(ini.get(scene, []))
            rows.append(dict(plot=plot, script=plots.get(plot, "?"), scene=scene,
                             date=date, time=time, route=route, place=place,
                             detail=detail, cond=cond, events=nev,
                             resources=resources.get(scene, ""), title=title))

    tsv = os.path.join(out_dir, "scenes.tsv")
    with io.open(tsv, "w", encoding="utf-8", newline="") as f:
        cols = ["plot", "script", "scene", "date", "time", "route", "place",
                "detail", "cond", "events", "resources", "title"]
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]).replace("\t", " ") for c in cols) + "\n")

    dated = [r for r in rows if r["date"]]
    print(f"{len(rows)} scenes across {len(set(r['plot'] for r in rows))} plots")
    print(f"{len(dated)} carry an explicit date ({len(dated)/len(rows)*100:.0f}%)")
    print(f"-> {tsv}")

    # calendar
    bydate = collections.defaultdict(lambda: collections.Counter())
    for r in dated:
        bydate[r["date"]][r["time"] or (f"[{r['route']}]" if r["route"] else "?")] += 1
    print("\ncalendar (scenes per in-game day):")
    for d in sorted(bydate):
        tot = sum(bydate[d].values())
        order = [t for t in TIMES if t in bydate[d]] + [t for t in bydate[d] if t not in TIMES]
        print(f"  {d}  {tot:>4} scenes   " + " ".join(f"{t}:{bydate[d][t]}" for t in order))

    places = collections.Counter(r["place"] for r in rows if r["place"])
    print(f"\n{len(places)} distinct places; top 20:")
    for p, c in places.most_common(20):
        print(f"  {c:>4}  {p}")

    conds = collections.Counter(r["cond"] for r in rows if r["cond"])
    print(f"\n{len(conds)} distinct branch conditions; top 20:")
    for p, c in conds.most_common(20):
        print(f"  {c:>4}  {p}")


if __name__ == "__main__":
    main()
