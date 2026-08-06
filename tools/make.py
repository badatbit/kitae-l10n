"""Full build: workbook -> font -> .SMF -> timing -> disc -> dist/

Always starts from the pristine disc dump, so a half-finished earlier run can
never leak into the result (that bit us once: a stale dump/build/track03.bin
made a "font only" build still carry an old PLOT.CB).

Steps:
  1. inject the Hangul the translation actually uses into TRFSTRINGS.DLL
  2. rebuild <script>.SMF (recomputing the .MSG offsets) and repack PLOT.CB
  3. resample MTG timing for any window whose character count changed
  4. patch both archives into a fresh copy of the data track
  5. replace the font DLL in place and copy everything to dist/
  6. report exactly which files differ from the original

Usage:  python make.py KOTORI_01 [--no-font]
"""
import glob, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gdfs import GdFs, TRACK, BASE_LBA, RAW
import disc

DUMP = os.path.join(HERE, "..", "dump")
BUILD = os.path.join(DUMP, "build")
DIST = os.path.join(HERE, "..", "dist")
SRC_DIR = os.path.dirname(TRACK)


def run(*args):
    print(f"\n$ {' '.join(os.path.basename(a) for a in args[1:])}")
    r = subprocess.run([sys.executable] + list(args), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    print((r.stdout or "").rstrip())
    if r.returncode:
        print((r.stderr or "").rstrip())
        raise SystemExit(f"step failed: {args}")


def replace_file(track, disc_path, data):
    """Overwrite a same-size file in place (no LBA moves)."""
    fs = GdFs(track=track)
    lba, size = fs.find(disc_path)
    if len(data) != size:
        raise SystemExit(f"{disc_path}: size changed ({len(data)} vs {size})")
    image = bytearray(open(track, "rb").read())
    for i in range((size + 2047) // 2048):
        off = (lba + i - BASE_LBA) * RAW
        sec = bytearray(image[off:off + RAW])
        chunk = data[i * 2048:(i + 1) * 2048]
        sec[16:16 + len(chunk)] = chunk
        image[off:off + RAW] = disc.fix_sector(sec)
    open(track, "wb").write(bytes(image))
    print(f"  replaced {disc_path} at LBA {lba} ({size:,} bytes)")


def main():
    script = (sys.argv[1] if len(sys.argv) > 1 else "KOTORI_01").upper()
    want_font = "--no-font" not in sys.argv
    os.makedirs(BUILD, exist_ok=True)

    if want_font:
        run(os.path.join(HERE, "hangul.py"), "build", script)
    run(os.path.join(HERE, "build_smf.py"), script, "--cab")
    run(os.path.join(HERE, "build_mtg.py"), script)

    # start clean
    os.makedirs(DIST, exist_ok=True)
    for name in sorted(os.listdir(SRC_DIR)):
        src = os.path.join(SRC_DIR, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(DIST, name))
    track = glob.glob(os.path.join(DIST, "*track03.bin"))[0]
    print(f"\nfresh copy of the disc in {DIST}")

    for disc_path, built in (("RESOURCE/PLOT.CB", os.path.join(BUILD, "PLOT.CB")),
                             ("RESOURCE/MTG.CB", os.path.join(BUILD, "MTG.CB"))):
        if not os.path.exists(built):
            continue
        tmp = track + ".tmp"
        disc.patch(disc_path, open(built, "rb").read(), tmp, track)
        os.replace(tmp, track)

    font = os.path.join(BUILD, "TRF", "TRFSTRINGS.DLL")
    if want_font and os.path.exists(font):
        replace_file(track, "TRF/TRFSTRINGS.DLL", open(font, "rb").read())

    new, orig = GdFs(track=track), GdFs()
    diff = []
    for full, l, s, d in new.walk():
        if d:
            continue
        ol, osz = orig.find(full.strip("/"))
        if s != osz or new.read(l, min(s, 65536)) != orig.read(ol, min(osz, 65536)):
            diff.append(full)
    print(f"\nfiles differing from the original: {diff}")
    gdi = os.path.basename(glob.glob(os.path.join(DIST, "*.gdi"))[0])
    print(f'run:  redream.exe "{os.path.join(os.path.abspath(DIST), gdi)}"')


if __name__ == "__main__":
    main()
