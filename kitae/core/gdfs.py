"""GD-ROM (GDI track03.bin) ISO9660 filesystem reader / extractor.

Usage:
    python gdfs.py list
    python gdfs.py extract <disc-path> <out-dir>     # e.g. RESOURCE/PLOT.CB
    python gdfs.py extract-all <out-dir>
"""
import struct, sys, os

TRACK = r"F:\dev-kitahe\kitahe-org\Kita He - White Illumination v2.002 (1999)(Hudson)(JP)[!]\track03.bin"
BASE_LBA = 45000
RAW = 2352  # raw mode-1 sector: 16B header + 2048B data + 288B EDC/ECC


class GdFs:
    def __init__(self, track=TRACK, base_lba=BASE_LBA):
        self.f = open(track, "rb")
        self.base = base_lba
        pvd = self.read_sector(self.base + 16)
        assert pvd[0] == 1 and pvd[1:6] == b"CD001", "PVD not found"
        root = pvd[156:156 + 34]
        self.root_lba = struct.unpack("<I", root[2:6])[0]
        self.root_size = struct.unpack("<I", root[10:14])[0]

    def read_sector(self, lba):
        self.f.seek((lba - self.base) * RAW)
        return self.f.read(RAW)[16:16 + 2048]

    def read(self, lba, size, offset=0):
        first = lba + offset // 2048
        skip = offset % 2048
        out = bytearray()
        for i in range((skip + size + 2047) // 2048):
            out += self.read_sector(first + i)
        return bytes(out[skip:skip + size])

    def walk(self, lba=None, size=None, path=""):
        """Yield (path, lba, size, is_dir) for every entry."""
        if lba is None:
            lba, size = self.root_lba, self.root_size
        data = self.read(lba, size)
        i = 0
        while i < len(data):
            ln = data[i]
            if ln == 0:
                i = (i // 2048 + 1) * 2048
                continue
            rec = data[i:i + ln]
            e_lba = struct.unpack("<I", rec[2:6])[0]
            e_size = struct.unpack("<I", rec[10:14])[0]
            flags = rec[25]
            name = rec[33:33 + rec[32]].decode("ascii", "replace").split(";")[0]
            if name not in ("\x00", "\x01"):
                full = f"{path}/{name}"
                if flags & 2:
                    yield full, e_lba, e_size, True
                    yield from self.walk(e_lba, e_size, full)
                else:
                    yield full, e_lba, e_size, False
            i += ln

    def find(self, want):
        want = "/" + want.strip("/").upper()
        for full, lba, size, is_dir in self.walk():
            if full.upper() == want and not is_dir:
                return lba, size
        raise FileNotFoundError(want)


def main():
    fs = GdFs()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        for full, lba, size, is_dir in fs.walk():
            print(f"{'D' if is_dir else ' '} lba={lba:>7} size={size:>11,}  {full}")
    elif cmd == "extract":
        want, outdir = sys.argv[2], sys.argv[3]
        lba, size = fs.find(want)
        dst = os.path.join(outdir, want.strip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        with open(dst, "wb") as o:
            o.write(fs.read(lba, size))
        print(f"extracted {want} -> {dst} ({size:,} bytes)")
    elif cmd == "extract-all":
        outdir = sys.argv[2]
        for full, lba, size, is_dir in fs.walk():
            if is_dir:
                continue
            dst = os.path.join(outdir, full.strip("/").replace("/", os.sep))
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "wb") as o:
                o.write(fs.read(lba, size))
            print(f"{full} ({size:,})")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
