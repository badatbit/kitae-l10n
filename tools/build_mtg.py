"""Rebuild MTG timing data so it matches the translated text length.

`MTG/<script>.SET` holds one `CTRFMsgTiming` object per message window, and its
payload is `u32 count` followed by one `(u8, u8)` pair **per drawn character**:
the first byte looks like a duration, the second carries the lip-sync shape in
its high nibble. The engine walks that array in step with the characters it
draws, so a translation with a different character count makes it run off the
end -- which crashes on the message window.

Windows without voice have an empty (2-byte) payload and need no work.

Since the pairs are tied to the recorded voice, the rebuild *resamples* the
original curve onto the new character count rather than inventing values: new
pair i takes the original pair at `i * old / new`. Pacing and mouth shapes are
preserved; sync drifts only as much as the length change itself.

Usage:
    python build_mtg.py KOTORI_01           # -> dump/build/MTG.CB
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cab import Cab
from windows import script_windows, display_len, clss_objects
from build_smf import repack_cab
import workbook

DUMP = os.path.join(HERE, "..", "dump")
BUILD = os.path.join(DUMP, "build")
PLOT_CB = os.path.join(DUMP, "plot", "PLOT.CB")
MTG_CB = os.path.join(DUMP, "scn", "MTG.CB")


def resample(payload, new_count):
    """Stretch/shrink a CTRFMsgTiming payload to `new_count` characters."""
    if len(payload) <= 4:
        return payload                      # silent window: nothing to scale
    old = (len(payload) - 4) // 2
    if old == new_count or new_count <= 0:
        return payload
    pairs = [payload[4 + i * 2:6 + i * 2] for i in range(old)]
    out = bytearray(struct.pack("<I", new_count + 1))
    for i in range(new_count):
        out += pairs[min(old - 1, i * old // new_count)]
    return bytes(out)


def rebuild_set(script, original, new_chars):
    """Rewrite a .SET blob, resampling each window's timing. `new_chars` maps
    window index -> new character count (missing = unchanged)."""
    out = bytearray(original)
    # walk the objects back-to-front so earlier offsets stay valid
    objs = [(oid, cls, p) for oid, cls, p in clss_objects(original)]
    spans = []
    pos = 0
    idx = 0
    for oid, cls, payload in objs:
        if cls != "CTRFMsgTiming":
            continue
        # locate this payload in the blob (payloads are unique enough by offset)
        pos = original.find(payload, pos) if payload else pos
        spans.append((idx, pos, len(payload)))
        pos += max(len(payload), 1)
        idx += 1

    changed = 0
    for wi, off, ln in reversed(spans):
        if wi not in new_chars:
            continue
        old_payload = bytes(out[off:off + ln])
        new_payload = resample(old_payload, new_chars[wi])
        if new_payload == old_payload:
            continue
        # the payload length is stored in the u32 right before it
        struct.pack_into("<I", out, off - 4, len(new_payload))
        out[off:off + ln] = new_payload
        changed += 1
    return bytes(out), changed


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    script = sys.argv[1].upper()
    plot, mtg = Cab(PLOT_CB), Cab(MTG_CB)
    wins, strs = script_windows(script, plot, mtg)
    rows = workbook.load(script)

    new_chars = {}
    for m in wins:
        w = m["window"]
        if m["want"] is None:
            continue                        # silent window
        texts = []
        touched = False
        for n, si in enumerate(m["strings"]):
            r = rows.get((w, n))
            t = (r.get("target") or "").strip() if r else ""
            if t:
                touched = True
            texts.append(t or strs[si])
        if touched:
            n = sum(display_len(t) for t in texts)
            if n != m["want"]:
                new_chars[w] = n

    print(f"{len(new_chars)} window(s) need new timing: "
          f"{sorted(new_chars.items())[:8]}")
    name = script.lower() + ".SET"
    blob, changed = rebuild_set(script, mtg.read(name), new_chars)
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, "MTG.CB")
    size = repack_cab(MTG_CB, {name: blob}, out)
    orig = os.path.getsize(MTG_CB)
    print(f"rewrote {changed} timing record(s)")
    print(f"{out}: {size:,} bytes (original {orig:,}, "
          f"{'fits' if size <= orig else 'TOO BIG by %d' % (size - orig)})")

    chk = Cab(out)
    diff = [n for n in chk.names if n != name and chk.read(n) != mtg.read(n)]
    print(f"  verify: {len(chk.names)} entries, {len(diff)} unintended diffs")
    # confirm the rebuilt timing now matches
    bad = 0
    for wi, (_, _, p) in enumerate(clss_objects(chk.read(name))):
        if wi in new_chars and (len(p) - 4) // 2 != new_chars[wi]:
            bad += 1
    print(f"  timing lengths still wrong: {bad}")


if __name__ == "__main__":
    main()
