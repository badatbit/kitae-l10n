"""Dump the scene/plot/timing archives, transparently decompressing ENC2.

Usage:  python dump_scn.py [out-dir]      (default: ../dump/scn)
"""
import os, sys, struct, io, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdfs import GdFs
from cab import Cab
from sjis2utf8 import is_text

ARCHIVES = ["RESOURCE/SCN/INIS.CB", "RESOURCE/SCN/PLOTS.CB",
            "RESOURCE/SCN/SCV.CB", "RESOURCE/MTG.CB", "RESOURCE/MENU.CB"]


def clss_objects(buf):
    """Walk a CLSS object tree; yield (obj_id, class_name, payload)."""
    if buf[:4] != b"CLSS":
        return
    nlen = struct.unpack("<I", buf[4:8])[0]
    pos = 8 + nlen
    while pos + 14 <= len(buf):
        if buf[pos:pos + 4] != b"\xff\xff\xff\xff":
            pos += 1
            continue
        oid = struct.unpack("<I", buf[pos + 4:pos + 8])[0]
        cl = struct.unpack("<H", buf[pos + 8:pos + 10])[0]
        name = buf[pos + 10:pos + 10 + cl].decode("ascii", "replace")
        plen = struct.unpack("<I", buf[pos + 10 + cl:pos + 14 + cl])[0]
        payload = buf[pos + 14 + cl:pos + 14 + cl + plen]
        yield oid, name, payload
        pos += 14 + cl + plen


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "dump", "scn")
    fs = GdFs()
    summary = []
    for arch in ARCHIVES:
        lba, size = fs.find(arch)
        local = os.path.join(out, os.path.basename(arch))
        os.makedirs(out, exist_ok=True)
        with open(local, "wb") as f:
            f.write(fs.read(lba, size))
        cab = Cab(local)
        sub = os.path.join(out, os.path.basename(arch).rsplit(".", 1)[0].lower())
        os.makedirs(sub, exist_ok=True)
        classes, n_enc2 = {}, 0
        for i, nm in enumerate(cab.names):
            tag, _ = cab.get(nm)
            if tag == b"ENC2":
                n_enc2 += 1
            data = cab.read(nm)
            # Text entries are cp932 on disc; write them as UTF-8 so editors can
            # show them. The rebuild path must encode back to cp932.
            if is_text(data):
                data = data.decode("cp932").encode("utf-8")
            with open(os.path.join(sub, nm.replace("/", "_")), "wb") as f:
                f.write(data)
            for _, cn, _p in clss_objects(data):
                classes[cn] = classes.get(cn, 0) + 1
        summary.append((arch, len(cab.names), n_enc2, classes))
        print(f"{arch:<24} {len(cab.names):>5} files ({n_enc2} were ENC2) -> {sub}")

    print("\nCLSS classes seen (now readable):")
    allc = {}
    for _, _, _, classes in summary:
        for k, v in classes.items():
            allc[k] = allc.get(k, 0) + v
    for k, v in sorted(allc.items(), key=lambda x: -x[1]):
        print(f"  {k:<26} {v:>7,}")


if __name__ == "__main__":
    main()
