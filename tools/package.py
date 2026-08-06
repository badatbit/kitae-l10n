"""Assemble a runnable, patched copy of the game.

Copies the untouched tracks and the .gdi next to the patched data track, and
patches the engine DLL that carries the Korean glyphs. The result is a directory
redream (or a real GD-ROM loader) can open directly.

Usage:  python package.py [out-dir]      (default ../dist)
"""
import os, re, shutil, sys, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gdfs import GdFs, TRACK, BASE_LBA, RAW
import disc

DUMP = os.path.join(HERE, "..", "dump")
BUILD = os.path.join(DUMP, "build")
SRC_DIR = os.path.dirname(TRACK)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "dist")
    os.makedirs(out, exist_ok=True)

    gdi = next(f for f in os.listdir(SRC_DIR) if f.lower().endswith(".gdi"))
    base = os.path.splitext(gdi)[0]

    # 1. the patched data track must already carry the rebuilt PLOT.CB
    patched = os.path.join(BUILD, "track03.bin")
    if not os.path.exists(patched):
        raise SystemExit("run build_smf.py + disc.py first (no dump/build/track03.bin)")

    # 2. inject the Korean font into the copy of TRFSTRINGS.DLL on that track
    font_dll = os.path.join(BUILD, "TRF", "TRFSTRINGS.DLL")
    if os.path.exists(font_dll):
        data = open(font_dll, "rb").read()
        tmp = os.path.join(BUILD, "track03_font.bin")
        shutil.copyfile(patched, tmp)
        # patch in place: the DLL keeps its exact size, so LBAs never move
        fs = GdFs(track=tmp)
        lba, size = fs.find("TRF/TRFSTRINGS.DLL")
        if len(data) != size:
            raise SystemExit(f"font DLL changed size ({len(data)} vs {size})")
        image = bytearray(open(tmp, "rb").read())
        for i in range((size + 2047) // 2048):
            off = (lba + i - BASE_LBA) * RAW
            sec = bytearray(image[off:off + RAW])
            chunk = data[i * 2048:(i + 1) * 2048]
            sec[16:16 + len(chunk)] = chunk
            image[off:off + RAW] = disc.fix_sector(sec)
        open(tmp, "wb").write(bytes(image))
        patched = tmp
        print(f"font injected into the data track ({size:,} bytes at LBA {lba})")

    # 3. copy everything into place
    for name in sorted(os.listdir(SRC_DIR)):
        src = os.path.join(SRC_DIR, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(out, name)
        if name.lower().endswith("track03.bin"):
            shutil.copyfile(patched, dst)
            print(f"  {name}  <- patched")
        else:
            shutil.copyfile(src, dst)
            print(f"  {name}")

    # 4. verify the result reads back cleanly
    track3 = next(os.path.join(out, f) for f in os.listdir(out)
                  if f.lower().endswith("track03.bin"))
    fs = GdFs(track=track3)
    files = [f for f, l, s, d in fs.walk() if not d]
    lba, size = fs.find("RESOURCE/PLOT.CB")
    print(f"\nverify: {len(files)} files enumerable, PLOT.CB = {size:,} bytes")
    print(f"-> {os.path.abspath(out)}")
    print(f"   run:  redream.exe \"{os.path.join(os.path.abspath(out), gdi)}\"")


if __name__ == "__main__":
    main()
