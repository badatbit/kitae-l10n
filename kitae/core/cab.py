"""Hudson TRF .CB archive (/CAB container) parser / extractor.

Container layout (all chunk sizes EXCLUDE the 8-byte tag+size header):
    "/CAB" u32(total)  "/FCB" u32(fcb_size)
        "INFO" u32(sz): u32 count, then count * 20-byte records
                        { u64 FILETIME, u32 stored_size, u32 abs_offset, u32 index }
        ".STR" u32(sz): u32 count, then null-terminated cp932 filenames
    then at each abs_offset a data chunk:
        "ENC0" u32(sz): raw data
        "ENC2" u32(sz): compressed data (algorithm not yet reversed)

SMF string table (".STR" file inside PLOT.CB / SONG.CB):
    ".STR" u32(total_size) u32(count), then null-terminated cp932 strings.

Usage:
    python cab.py list <file.cb>
    python cab.py extract <file.cb> <out-dir>
    python cab.py smf <file.cb> <entry-name>      # dump strings of an SMF entry
"""
import struct, sys, os


class Cab:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        assert self.data[:4] == b"/CAB", "not a /CAB file"
        fcb_size = struct.unpack("<I", self.data[12:16])[0]
        self.entries = []   # (size, offset, index, filetime)
        self.names = []
        pos, end = 16, 16 + fcb_size
        while pos < end:
            tag = self.data[pos:pos + 4]
            sz = struct.unpack("<I", self.data[pos + 4:pos + 8])[0]
            body = self.data[pos + 8:pos + 8 + sz]
            if tag == b"INFO":
                cnt = struct.unpack("<I", body[0:4])[0]
                for i in range(cnt):
                    ft, esz, eoff, eidx = struct.unpack("<QIII", body[4 + i*20:4 + (i+1)*20])
                    self.entries.append((esz, eoff, eidx, ft))
            elif tag == b".STR":
                self.names = [x.decode("cp932", "replace")
                              for x in body[4:].split(b"\x00") if x]
            pos += 8 + sz

    def get(self, name):
        """Return (enc_tag, stored_payload) for entry by name, still compressed."""
        i = self.names.index(name)
        esz, eoff, _, _ = self.entries[i]
        tag = self.data[eoff:eoff + 4]
        sz = struct.unpack("<I", self.data[eoff + 4:eoff + 8])[0]
        return tag, self.data[eoff + 8:eoff + 8 + sz]

    def resolve(self, name):
        """Entry name matching `name`, ignoring case (the SCV data and the
        archive index disagree on capitalisation: BGn264.SET vs bgn264.SET)."""
        if name in self.names:
            return name
        low = name.lower()
        for n in self.names:
            if n.lower() == low:
                return n
        raise KeyError(name)

    def read(self, name):
        """Return the decoded contents of an entry (ENC2 is decompressed)."""
        name = self.resolve(name)
        i = self.names.index(name)
        esz = self.entries[i][0]
        tag, payload = self.get(name)
        if tag == b"ENC0":
            return payload[:esz]
        if tag == b"ENC2":
            from kitae.core.enc2 import decompress
            return decompress(payload, esz)
        raise NotImplementedError(f"{name}: unsupported encoding {tag!r}")


def smf_strings(payload):
    """Parse a .STR string-table file (SMF)."""
    assert payload[:4] == b".STR", "not a .STR table"
    count = struct.unpack("<I", payload[8:12])[0]
    out, pos = [], 12
    while len(out) < count and pos < len(payload):
        end = payload.index(b"\x00", pos)
        out.append(payload[pos:end].decode("cp932", "replace"))
        pos = end + 1
    return out


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    cab = Cab(path)
    if cmd == "list":
        for (esz, eoff, eidx, ft), nm in zip(cab.entries, cab.names):
            enc = cab.data[eoff:eoff + 4].decode("ascii", "replace")
            print(f"[{eidx:4}] off={eoff:#9x} size={esz:>9,} {enc}  {nm}")
    elif cmd == "extract":
        outdir = sys.argv[3]
        os.makedirs(outdir, exist_ok=True)
        for nm in cab.names:
            tag, payload = cab.get(nm)
            safe = nm.replace("/", "_")
            with open(os.path.join(outdir, safe + ("" if tag == b"ENC0" else ".enc2")), "wb") as o:
                o.write(payload)
            print(f"{nm} ({tag.decode()}, {len(payload):,})")
    elif cmd == "smf":
        tag, payload = cab.get(sys.argv[3])
        assert tag == b"ENC0", f"entry is {tag}, need ENC2 decompressor"
        for i, s in enumerate(smf_strings(payload)):
            print(f"{i:5}  {s}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
