"""Patch a file inside the GD-ROM image, in place, keeping the layout.

The data track is raw 2352-byte CD-ROM Mode 1 sectors: 12 sync + 4 header +
2048 data + 4 EDC + 8 zero + 172 P-parity + 104 Q-parity. Rewriting the payload
therefore means recomputing EDC and the Reed-Solomon P/Q parity, which this
module does (and self-tests against untouched sectors).

Replacing a file only works when the new content is not larger than the space the
original occupies, because everything else on the disc keeps its LBA. The file
size stored in the ISO9660 directory record is updated so the loader sees the new
length.

Usage:
    python disc.py selftest
    python disc.py patch RESOURCE/PLOT.CB <new-file> <out-track03.bin>
"""
import os, struct, sys

from kitae.core.gdfs import GdFs, RAW, BASE_LBA, TRACK

# ---------------------------------------------------------------- EDC / ECC
_EDC = []
for _i in range(256):
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xD8018001 if _e & 1 else 0)
    _EDC.append(_e)

_F = [0] * 256
_B = [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    _F[_i] = _j
    _B[_i ^ _j] = _i


def edc(data):
    c = 0
    for b in data:
        c = _EDC[(c ^ b) & 0xFF] ^ (c >> 8)
    return c & 0xFFFFFFFF


def _ecc_block(src, major_count, minor_count, major_mult, minor_inc, dest, off):
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = _F[a]
        a = _B[_F[a] ^ b]
        dest[off + major] = a
        dest[off + major + major_count] = a ^ b


def fix_sector(sec):
    """Recompute EDC and P/Q parity of one raw Mode 1 sector (2352 bytes)."""
    s = bytearray(sec)
    struct.pack_into("<I", s, 2064, edc(s[0:2064]))
    s[2068:2076] = b"\x00" * 8
    # P is computed over header+data+EDC+zeros (86*24 == 2064 bytes)
    _ecc_block(s[12:2076], 86, 24, 2, 86, s, 2076)
    # Q spans the same region *plus* the P parity just written (52*43 == 2236)
    _ecc_block(s[12:2248], 52, 43, 86, 88, s, 2248)
    return bytes(s)


# ---------------------------------------------------------------- patching
def sector_of(track, lba):
    off = (lba - BASE_LBA) * RAW
    with open(track, "rb") as f:
        f.seek(off)
        return f.read(RAW)


def selftest(n=6):
    """Recomputing an untouched sector must reproduce it byte for byte."""
    fs = GdFs()
    lba, _ = fs.find("RESOURCE/PLOT.CB")
    ok = 0
    for i in range(n):
        raw = sector_of(TRACK, lba + i)
        if fix_sector(raw) == raw:
            ok += 1
        else:
            a = fix_sector(raw)
            first = next(j for j in range(RAW) if a[j] != raw[j])
            print(f"  sector {lba+i}: differs at {first} "
                  f"({a[first]:02x} vs {raw[first]:02x})")
    print(f"selftest: {ok}/{n} sectors reproduced exactly")
    return ok == n


def patch(disc_path, new_data, out_track, src_track=None):
    """Replace one file's contents. `src_track` lets patches be chained."""
    src_track = src_track or TRACK
    fs = GdFs(track=src_track)
    lba, orig_size = fs.find(disc_path)
    cap = ((orig_size + 2047) // 2048) * 2048
    if len(new_data) > cap:
        raise ValueError(f"{len(new_data)} bytes will not fit in {cap} "
                         f"({(len(new_data)-cap+2047)//2048} extra sectors needed)")

    with open(src_track, "rb") as f:
        image = bytearray(f.read())
    payload = new_data + b"\x00" * (cap - len(new_data))
    for i in range(cap // 2048):
        off = (lba + i - BASE_LBA) * RAW
        sec = bytearray(image[off:off + RAW])
        sec[16:2064] = payload[i * 2048:(i + 1) * 2048]
        image[off:off + RAW] = fix_sector(sec)

    # update the size field in the ISO9660 directory record
    patched = 0
    for full, dlba, dsize, is_dir in fs.walk():
        if is_dir or full.strip("/").upper() != disc_path.strip("/").upper():
            continue
        parent = full.rsplit("/", 1)[0] or "/"
        for pfull, plba, psize, pdir in [("/", fs.root_lba, fs.root_size, True)] + \
                [(a, b, c, d) for a, b, c, d in fs.walk() if d]:
            if pfull.rstrip("/") != parent.rstrip("/"):
                continue
            for si in range((psize + 2047) // 2048):
                off = (plba + si - BASE_LBA) * RAW
                sec = bytearray(image[off:off + RAW])
                data = sec[16:2064]
                p = 0
                while p < len(data):
                    ln = data[p]
                    if ln == 0:
                        break
                    elba = struct.unpack("<I", data[p + 2:p + 6])[0]
                    if elba == dlba:
                        struct.pack_into("<I", data, p + 10, len(new_data))
                        struct.pack_into(">I", data, p + 14, len(new_data))
                        patched += 1
                    p += ln
                sec[16:2064] = data
                image[off:off + RAW] = fix_sector(sec)
    with open(out_track, "wb") as f:
        f.write(bytes(image))
    print(f"patched {disc_path}: {len(new_data):,} bytes into {cap:,} "
          f"({cap - len(new_data):,} spare), {patched} directory record(s) updated")
    print(f"-> {out_track}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    if sys.argv[1] == "selftest":
        selftest()
    elif sys.argv[1] == "patch":
        src = sys.argv[5] if len(sys.argv) > 5 else None
        patch(sys.argv[2], open(sys.argv[3], "rb").read(), sys.argv[4], src)
    else:
        print(__doc__)


def replace_same_size(track, disc_path, data):
    """Overwrite a file that keeps its exact size, so no LBA moves."""
    fs = GdFs(track=track)
    lba, size = fs.find(disc_path)
    if len(data) != size:
        raise ValueError(f"{disc_path}: size changed ({len(data)} vs {size})")
    image = bytearray(open(track, "rb").read())
    for i in range((size + 2047) // 2048):
        off = (lba + i - BASE_LBA) * RAW
        sec = bytearray(image[off:off + RAW])
        chunk = data[i * 2048:(i + 1) * 2048]
        sec[16:16 + len(chunk)] = chunk
        image[off:off + RAW] = fix_sector(sec)
    open(track, "wb").write(bytes(image))
    return lba, size


def diff_against(track, orig_track):
    """Files whose size or contents differ from the original dump.

    Compares whole files: the font DLL's glyph area starts past 0x1D000, so a
    "first N bytes" check would silently report an injected font as unchanged.
    """
    import hashlib

    new, orig = GdFs(track=track), GdFs(track=orig_track)
    out = []
    for full, l, s, d in new.walk():
        if d:
            continue
        ol, osz = orig.find(full.strip("/"))
        if s != osz:
            out.append(full)
            continue
        a = hashlib.blake2b(new.read(l, s), digest_size=16).digest()
        b = hashlib.blake2b(orig.read(ol, osz), digest_size=16).digest()
        if a != b:
            out.append(full)
    return out


if __name__ == "__main__":
    main()
