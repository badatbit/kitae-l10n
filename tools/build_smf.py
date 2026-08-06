"""Rebuild a .SMF from a translation workbook, then repack it into PLOT.CB.

A .SMF is:

    ".STR" u32 total_size u32 count      then `count` NUL-terminated cp932 strings
    ".MSG" u32 size                      then size/8 records of
                                             u32 line_count, u32 byte_offset

`byte_offset` is relative to the start of the string block (i.e. offset 12 in the
file). Replacing text changes every offset after it, so the whole `.MSG` table is
recomputed; the per-window line counts are preserved exactly, which is what keeps
the engine's window structure intact.

Rules the rebuild enforces:
  * a window keeps its line count -- a translation must stay on the same number
    of lines as the original, otherwise the window would swallow the next line
  * inline markup (`@S@`, `@P@`, `&主人公&`) must survive; we warn if a line's
    markup set changes
  * untranslated lines fall back to the original text

Usage:
    python build_smf.py KOTORI_01            # write dump/build/KOTORI_01.SMF
    python build_smf.py KOTORI_01 --cab      # also repack dump/build/PLOT.CB
"""
import io, os, re, sys, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cab import Cab, smf_strings
from windows import msg_table, MARKUP
import workbook

DUMP = os.path.join(HERE, "..", "dump")
PLOT_CB = os.path.join(DUMP, "plot", "PLOT.CB")
BUILD = os.path.join(DUMP, "build")
ENCODING = "cp932"


def rebuild_smf(script, rows, original):
    """Return new .SMF bytes built from `rows` (workbook) over `original`."""
    src = smf_strings(original)
    table = msg_table(original)
    if table is None:
        raise ValueError("original .SMF has no .MSG table")

    # window -> [line -> text]
    text = list(src)
    warnings = []
    for (w, ln), r in rows.items():
        tgt = (r.get("target") or "").strip()
        if not tgt:
            continue
        lines, start = table[w] if w < len(table) else (0, None)
        if start is None or ln >= lines:
            warnings.append(f"win {w} line {ln}: outside the window's {lines} line(s)")
            continue
        si = start + ln
        if set(MARKUP.findall(r.get("source", ""))) != set(MARKUP.findall(tgt)):
            warnings.append(f"win {w} line {ln}: inline markup changed")
        text[si] = tgt

    # encode; report anything cp932 cannot hold (Korean will land here until the
    # font/codepage work is done -- that is expected and reported, not hidden)
    import hangul
    cp = hangul.load_codepage()

    blob = bytearray()
    offsets = []
    unencodable = []
    for i, s in enumerate(text):
        offsets.append(len(blob))
        try:
            blob += hangul.encode(s, cp)
        except UnicodeEncodeError as e:
            unencodable.append((i, s[e.start:e.end]))
            blob += src[i].encode(ENCODING, "replace")
        blob += b"\x00"

    out = bytearray()
    out += b".STR" + struct.pack("<II", 12 + len(blob), len(text)) + blob
    msg = bytearray()
    for w, (lines, start) in enumerate(table):
        msg += struct.pack("<II", lines, offsets[start] if start is not None else 0)
    out += b".MSG" + struct.pack("<I", len(msg)) + msg
    return bytes(out), warnings, unencodable


def repack_cab(src_path, replacements, dst_path):
    """Rewrite a .CB, substituting the given {entry_name: raw_bytes}."""
    cab = Cab(src_path)
    entries, blobs = [], []
    for i, name in enumerate(cab.names):
        esz, eoff, eidx, ft = cab.entries[i]
        tag = cab.data[eoff:eoff + 4]
        if name in replacements:
            body = replacements[name]
            tag = b"ENC0"            # store replacements uncompressed
            esz = len(body)          # INFO size == real file size
        else:
            # copy the stored chunk verbatim, including its padding, and keep
            # the INFO size untouched (it is the *uncompressed* size for ENC2
            # and the exact file size for ENC0, which may be odd)
            sz = struct.unpack("<I", cab.data[eoff + 4:eoff + 8])[0]
            body = cab.data[eoff + 8:eoff + 8 + sz]
        entries.append([esz, 0, eidx, ft])
        blobs.append((tag, body))

    names_blob = b"".join(n.encode("cp932") + b"\x00" for n in cab.names)
    info_sz = 4 + len(cab.names) * 20
    str_sz = 4 + len(names_blob)
    fcb_size = (8 + info_sz) + (8 + str_sz)
    pos = 16 + fcb_size

    data_chunks = []
    for i, (tag, body) in enumerate(blobs):
        pad = (-len(body)) % 2
        entries[i][1] = pos
        chunk = tag + struct.pack("<I", len(body) + pad) + body + b"\x00" * pad
        data_chunks.append(chunk)
        pos += len(chunk)

    out = bytearray()
    out += b"/CAB" + struct.pack("<I", pos - 8)
    out += b"/FCB" + struct.pack("<I", fcb_size)
    out += b"INFO" + struct.pack("<I", info_sz) + struct.pack("<I", len(cab.names))
    for esz, eoff, eidx, ft in entries:
        out += struct.pack("<QIII", ft, esz, eoff, eidx)
    out += b".STR" + struct.pack("<I", str_sz) + struct.pack("<I", len(cab.names))
    out += names_blob
    for c in data_chunks:
        out += c
    open(dst_path, "wb").write(bytes(out))
    return len(out)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    script = sys.argv[1].upper()
    os.makedirs(BUILD, exist_ok=True)
    plot = Cab(PLOT_CB)
    original = plot.read(script + ".SMF")
    rows = workbook.load(script)
    if not rows:
        print(f"no workbook at {workbook.path_for(script)} -- run workbook.py first")
        return

    smf, warns, bad = rebuild_smf(script, rows, original)
    dst = os.path.join(BUILD, script + ".SMF")
    open(dst, "wb").write(smf)
    done = sum(1 for r in rows.values() if (r.get("target") or "").strip())
    print(f"{dst}: {len(smf):,} bytes (original {len(original):,}), "
          f"{done}/{len(rows)} lines translated")
    for w in warns[:10]:
        print("  WARN", w)
    if bad:
        print(f"  {len(bad)} line(s) contain characters cp932 cannot encode "
              f"(expected until the font codepage is decided); e.g. {bad[:3]}")

    if "--cab" in sys.argv:
        out = os.path.join(BUILD, "PLOT.CB")
        size = repack_cab(PLOT_CB, {script + ".SMF": smf}, out)
        orig = os.path.getsize(PLOT_CB)
        print(f"{out}: {size:,} bytes (original {orig:,}, "
              f"{'fits' if size <= orig else 'TOO BIG by %d' % (size - orig)})")
        # sanity: reopen and compare every entry
        chk = Cab(out)
        assert chk.names == plot.names, "entry list changed"
        diff = [n for n in chk.names
                if n != script + ".SMF" and chk.read(n) != plot.read(n)]
        print(f"  verify: {len(chk.names)} entries, {len(diff)} unintended diffs")


if __name__ == "__main__":
    main()
