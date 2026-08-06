"""Recursive parser for the TRF "CLSS" object serialisation.

Layout:
    "CLSS" u32 rootname_len rootname
    then a stream of records:
        FF FF FF FF | u32 obj_id | u16 cls_len | cls_name | u32 payload_len | payload

A container's payload starts with a u32 child count followed by the children's
records, so the whole thing is a tree.

Usage:
    python clss.py <file>            # print the object tree
"""
import struct, sys

MARK = b"\xff\xff\xff\xff"


class Obj:
    __slots__ = ("oid", "cls", "payload", "children")

    def __init__(self, oid, cls, payload):
        self.oid, self.cls, self.payload = oid, cls, payload
        self.children = []

    def __repr__(self):
        return f"<{self.cls}#{self.oid} {len(self.payload)}B {len(self.children)}ch>"

    def find(self, cls):
        """Depth-first search for all descendants of a class."""
        for c in self.children:
            if c.cls == cls:
                yield c
            yield from c.find(cls)


MAX_DEPTH = 12


def _read_record(buf, pos, end):
    """Validate and read one record at pos. Returns (obj_fields, next_pos) or None."""
    if pos + 14 > end or buf[pos:pos + 4] != MARK:
        return None
    oid = struct.unpack("<I", buf[pos + 4:pos + 8])[0]
    cl = struct.unpack("<H", buf[pos + 8:pos + 10])[0]
    p0 = pos + 10 + cl
    if cl == 0 or cl > 64 or p0 + 4 > end:
        return None
    name_raw = buf[pos + 10:p0]
    if not all(32 <= b < 127 for b in name_raw):
        return None
    plen = struct.unpack("<I", buf[p0:p0 + 4])[0]
    if p0 + 4 + plen > end:
        return None
    return (oid, name_raw.decode("ascii"), buf[p0 + 4:p0 + 4 + plen]), p0 + 4 + plen


def _records(buf, pos, end, depth=0):
    while pos < end:
        got = _read_record(buf, pos, end)
        if got is None:
            nxt = buf.find(MARK, pos + 1, end)
            if nxt < 0:
                return
            pos = nxt
            continue
        (oid, name, payload), pos = got
        obj = Obj(oid, name, payload)
        obj.children = parse_children(payload, depth + 1)
        yield obj


def parse_children(payload, depth=0):
    """Parse nested records inside a payload (after its leading u32 count)."""
    if depth >= MAX_DEPTH or len(payload) < 14:
        return []
    start = payload.find(MARK)
    if start < 0:
        return []
    # only recurse when the first candidate record actually validates
    if _read_record(payload, start, len(payload)) is None:
        return []
    return list(_records(payload, start, len(payload), depth))


def parse(buf):
    """Parse a whole CLSS blob; returns (root_class, [top-level objects])."""
    if buf[:4] != b"CLSS":
        raise ValueError("not a CLSS blob")
    nlen = struct.unpack("<I", buf[4:8])[0]
    root = buf[8:8 + nlen].rstrip(b"\x00").decode("ascii", "replace")
    return root, list(_records(buf, 8 + nlen, len(buf)))


def cstr(buf, pos):
    """Read a NUL-terminated cp932 string."""
    end = buf.find(b"\x00", pos)
    if end < 0:
        end = len(buf)
    return buf[pos:end].decode("cp932", "replace"), end + 1


def strings_in(payload, minlen=2):
    """Pull readable cp932 strings out of a payload."""
    out, cur, start = [], bytearray(), 0
    for i, b in enumerate(payload):
        if b == 0:
            if len(cur) >= minlen:
                try:
                    out.append((start, cur.decode("cp932")))
                except UnicodeDecodeError:
                    pass
            cur, start = bytearray(), i + 1
        else:
            if not cur:
                start = i
            cur.append(b)
    return out


def named_field(payload, key=b"NAME"):
    """Read a `key` + u32 length + cp932 string field out of a payload.

    Layout seen in CTRFLipControll / CTRFDataSet payloads:
        "NAME" 00 00 00 00 | u32 len | len bytes of cp932
    """
    i = payload.find(key)
    if i < 0:
        return ""
    j = i + len(key) + 4
    if j + 4 > len(payload):
        return ""
    ln = struct.unpack("<I", payload[j:j + 4])[0]
    if ln == 0 or j + 4 + ln > len(payload) or ln > 256:
        return ""
    return payload[j + 4:j + 4 + ln].decode("cp932", "replace")


def dump(obj, depth=0, maxdepth=6):
    pad = "  " * depth
    strs = [s for _, s in strings_in(obj.payload) if any(c.isalnum() or ord(c) > 0x7F for c in s)]
    hint = "  " + " ".join(repr(s) for s in strs[:4]) if strs else ""
    print(f"{pad}{obj.cls}#{obj.oid} ({len(obj.payload)}B, {len(obj.children)} children){hint}")
    if depth < maxdepth:
        for c in obj.children:
            dump(c, depth + 1, maxdepth)


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    root, objs = parse(data)
    print(f"root: {root}  ({len(objs)} top-level objects)")
    for o in objs:
        dump(o)
