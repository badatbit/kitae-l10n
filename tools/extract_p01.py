"""Extract every asset the KOTORI_01 (plot P01) scenes reference.

Backgrounds and sprites are composed to PNG via image.py; movies are copied out
of the disc as-is (they are ordinary AVI with Cinepak video).

Usage:  python extract_p01.py [out-dir]     (default ../dump/assets/P01)
"""
import os, re, sys, struct, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gdfs import GdFs
from cab import Cab
from clss import parse
from image import compose

DUMP = os.path.join(HERE, "..", "dump")
CACHE = os.path.join(DUMP, "cb")


def cb(fs, disc_path):
    """Local cached copy of a .CB archive from the disc."""
    local = os.path.join(CACHE, os.path.basename(disc_path))
    if not os.path.exists(local):
        lba, size = fs.find(disc_path)
        os.makedirs(CACHE, exist_ok=True)
        with open(local, "wb") as f:
            f.write(fs.read(lba, size))
    return Cab(local)


def scene_resources(scv_cab, scene):
    """Resource paths ("BGn/bgn264.SET", ...) referenced by one scene."""
    try:
        buf = scv_cab.read(scene + ".SCV")
    except Exception:
        return []
    root, objs = parse(buf)
    out = []

    def walk(o):
        for s in re.findall(rb"[!-~]{5,}", o.payload):
            t = s.decode("ascii")
            if "/" in t and "." in t:
                out.append(t.split("/CLIP")[0])
        for c in o.children:
            walk(c)

    for o in objs:
        walk(o)
    return out


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DUMP, "assets", "P01")
    os.makedirs(out_dir, exist_ok=True)
    fs = GdFs()
    scv = cb(fs, "RESOURCE/SCN/SCV.CB")

    scenes = sorted({n[:-4] for n in scv.names if n.startswith("P01S")})
    refs = collections.OrderedDict()
    for s in scenes:
        for r in scene_resources(scv, s):
            refs.setdefault(r, []).append(s)
    print(f"{len(scenes)} scenes reference {len(refs)} distinct resources")

    by_arch = collections.defaultdict(list)
    for r in refs:
        arch, _, name = r.partition("/")
        by_arch[arch].append(name)

    made = failed = 0
    index = []
    for arch, names in sorted(by_arch.items()):
        disc = f"RESOURCE/{arch}.CB"
        try:
            archive = cb(fs, disc)
        except Exception as e:
            print(f"  skip {arch}: {e}")
            continue
        sub = os.path.join(out_dir, arch)
        os.makedirs(sub, exist_ok=True)
        for name in sorted(set(names)):
            if not name.lower().endswith(".set"):
                continue
            png = os.path.join(sub, name.rsplit(".", 1)[0] + ".png")
            try:
                img = compose(archive, name)
                img.save(png)
                made += 1
                index.append((f"{arch}/{name}", os.path.relpath(png, out_dir),
                              f"{img.size[0]}x{img.size[1]}",
                              ",".join(refs[f"{arch}/{name}"])))
            except Exception as e:
                failed += 1
                if failed <= 8:
                    print(f"  FAIL {arch}/{name}: {e}")
    print(f"composed {made} pictures, {failed} failed -> {out_dir}")

    # movies
    mov_dir = os.path.join(out_dir, "MOVIE")
    os.makedirs(mov_dir, exist_ok=True)
    for full, lba, size, is_dir in fs.walk():
        if is_dir or not full.upper().startswith("/RESOURCE/MOVIE/"):
            continue
        dst = os.path.join(mov_dir, os.path.basename(full))
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(fs.read(lba, size))
        print(f"  movie {os.path.basename(full)} ({size:,})")

    with open(os.path.join(out_dir, "INDEX.tsv"), "w", encoding="utf-8") as f:
        f.write("resource\tpng\tsize\tscenes\n")
        for row in index:
            f.write("\t".join(row) + "\n")
    print(f"index -> {os.path.join(out_dir, 'INDEX.tsv')}")


if __name__ == "__main__":
    main()
