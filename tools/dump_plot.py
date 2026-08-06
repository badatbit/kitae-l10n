"""Dump PLOT.CB from the disc image: raw entries + readable UTF-8 text of SMF tables.

Usage:  python dump_plot.py [out-dir]     (default: ../dump/plot)
"""
import os, sys, struct, io, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdfs import GdFs
from cab import Cab, smf_strings


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "dump", "plot")
    raw_dir = os.path.join(out, "raw")
    txt_dir = os.path.join(out, "text")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(txt_dir, exist_ok=True)

    fs = GdFs()
    lba, size = fs.find("RESOURCE/PLOT.CB")
    cb_path = os.path.join(out, "PLOT.CB")
    with open(cb_path, "wb") as f:
        f.write(fs.read(lba, size))
    print(f"PLOT.CB -> {cb_path} ({size:,} bytes)")

    cab = Cab(cb_path)
    index_lines = []
    for nm in cab.names:
        tag, payload = cab.get(nm)
        dst = os.path.join(raw_dir, nm)
        with open(dst, "wb") as f:
            f.write(payload)
        note = ""
        if tag == b"ENC0" and payload[:4] == b".STR":
            strs = smf_strings(payload)
            base = os.path.splitext(nm)[0]
            tp = os.path.join(txt_dir, base + ".txt")
            with io.open(tp, "w", encoding="utf-8") as f:
                for i, s in enumerate(strs):
                    f.write(f"{i}\t{s}\n")
            note = f"-> text/{base}.txt ({len(strs)} strings)"
        index_lines.append(f"{nm}\t{tag.decode()}\t{len(payload)}\t{note}")
        print(f"  {nm} ({tag.decode()}, {len(payload):,}) {note}")

    with io.open(os.path.join(out, "INDEX.tsv"), "w", encoding="utf-8") as f:
        f.write("name\tenc\tsize\ttext\n")
        f.write("\n".join(index_lines) + "\n")
    print(f"\nindex -> {os.path.join(out, 'INDEX.tsv')}")


if __name__ == "__main__":
    main()
