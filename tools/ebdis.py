"""EDL bytecode (.EB) disassembler and speaker attribution.

The scenario VM lives in TRF/KitaheGel.dll (CKitaheGel), image base 0x10000000.

    0x10005F34   interpreter main loop
    0x100131B4   opcode dispatch table, .data -- handler = *(base + opcode*4),
                 so entry 0 is NULL and real opcodes run 0x01..0x9C (156)
    0x10013428   operand-length table, .data  -- len = *(base + opcode)
    0x1000612C   handler for opcode 0x00 (statement boundary / scheduler yield)

The loop is literally

    op  = *pc                                 ; mov.b @r4,r1
    len = lentab[op]                          ; mov.b @(r0,r7),r3
    exec->operand = pc + 1                    ; mov.l r4,@(8,r8)
    exec->pc      = pc + 1 + len              ; mov.l r1,@(4,r8)
    handtab[op](gel)                          ; jsr @r5

so every instruction is

    <u8 opcode> <OPLEN[opcode] operand bytes, little-endian>

and opcode 0x00 is the statement terminator.  (The loop also supports a second,
"extended" two-byte opcode space selected when op >= gel->[16]; that field is
initialised to 0xFF, so it is never used in this build.)

The three opcodes that matter for translation work:

    0x6A  u16  set speaker  -- operand is an index into north01.sym group 0
    0x6B  u16  show message -- operand is the message-window index (same
                               numbering as MTG/<script>.SET and .WST)
    0x6C  u16  show message, alternate window mode
    0x73  u16  show message as a menu/choice item

Usage:
    python ebdis.py KOTORI_01              # speaker-annotated message list
    python ebdis.py KOTORI_01 --dis        # raw disassembly
    python ebdis.py --verify               # check every script against MTG
"""
import os, struct, sys, io, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cab import Cab, smf_strings

PLOT_CB = os.path.join(HERE, "..", "dump", "plot", "PLOT.CB")
MTG_CB = os.path.join(HERE, "..", "dump", "scn", "MTG.CB")

# Operand byte count per opcode, verbatim from KitaheGel.dll VA 0x10013428.
# Index == opcode byte.  Opcodes 0x9D..0xFF are invalid (no handler).
OPLEN = bytes((
    0, 4, 1, 2, 4, 1, 2, 4, 1, 2, 4, 2, 4, 8, 1, 4,     # 00-0f
    2, 0, 1, 1, 1, 0, 0, 0, 1, 2, 4, 4, 4, 4, 0, 0,     # 10-1f
    0, 1, 0, 1, 2, 4, 4, 4, 4, 2, 2, 2, 2, 2, 2, 2,     # 20-2f
    2, 2, 2, 2, 2, 0, 0, 0, 0, 0, 0, 4, 4, 4, 2, 2,     # 30-3f
    2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0, 0, 0, 0, 0,     # 40-4f
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,     # 50-5f
    0, 0, 0, 2, 2, 4, 2, 0, 2, 4, 2, 2, 2, 4, 4, 4,     # 60-6f
    4, 4, 2, 2, 4, 2, 2, 2, 2, 2, 2, 0, 0, 0, 0, 0,     # 70-7f
    2, 0, 2, 4, 2, 20, 2, 20, 2, 20, 2, 2, 2, 8, 2, 2,  # 80-8f
    2, 2, 2, 4, 0, 0, 0, 2, 4, 2, 2, 0,                 # 90-9b
))
MAXOP = 0x9C            # 0x9C has a handler but a zero-length operand slot

# Opcode names for the part of the instruction set that has been identified.
OPNAME = {
    0x00: "end",              # statement terminator (NULL handler)
    0x01: "jmp.abs",          # pc = base + u32
    0x02: "jmp.s8",           # pc += s8
    0x03: "jmp.s16",
    0x04: "jmp.s32",
    0x05: "jnz.s8",  0x06: "jnz.s16", 0x07: "jnz.s32",
    0x08: "jz.s8",   0x09: "jz.s16",  0x0a: "jz.s32",
    0x20: "pop",              # sp += 4
    0x21: "call.native",      # dispatch through the .EB symbol/label table
    0x23: "push.u8", 0x24: "push.u16", 0x25: "push.u32",
    0x31: "push.var",
    0x42: "store.u16",
    0x4f: "store.blk",
    0x67: "kita.event",
    0x6a: "speaker",          # <<< speaker channel / north01.sym index
    0x6b: "message",          # <<< show message window, mode 0
    0x6c: "message2",         # <<< show message window, mode 2
    0x6d: "message.sel", 0x6e: "message.sel2",
    0x6f: "message.sel3", 0x70: "message.sel4",
    0x73: "menu.item",        # <<< show message window as a menu choice
    0x74: "menu.item2",
    0x78: "vsc.cut",          # ITRFVisualPlot::(vt+20)(u16)
    0x79: "vsc.cut2",
    0x85: "trap.add", 0x87: "trap.add2", 0x89: "trap.add3",
    0x8d: "trap.set",
}

SPEAKER_OPS = (0x6a,)
# opcodes whose operand names a message window; 0x74 packs (window, slot)
MESSAGE_OPS = (0x6b, 0x6c, 0x73, 0x74)


def _window_of(op, val):
    return (val & 0xffff) if op == 0x74 else val


# --------------------------------------------------------------------------- #
# container

def parse_header(eb):
    """Return (hdr_size, version, n_blocks, tail_off, tail_size)."""
    return struct.unpack_from("<HHHHI", eb, 0)


def parse_blocks(eb):
    """Return (block_offsets, table2, labels).

    Each block is a NUL-terminated run of (u16 label_id, u16 code_offset)
    pairs preceded by a u16 tag; labels maps code_offset -> [(block, id)].
    """
    pos = 0x10
    t1 = []
    while True:
        v = struct.unpack_from("<H", eb, pos)[0]
        pos += 2
        if v == 0:
            break
        t1.append(v)
    t2 = []
    while True:
        v = struct.unpack_from("<H", eb, pos)[0]
        pos += 2
        if v == 0:
            break
        t2.append(v)
    labels = collections.defaultdict(list)
    blocks = []
    for bi, off in enumerate(t1):
        tag = struct.unpack_from("<H", eb, off - 2)[0]
        q, ent = off, []
        while True:
            lid = struct.unpack_from("<H", eb, q)[0]
            if lid == 0:
                break
            coff = struct.unpack_from("<H", eb, q + 2)[0]
            ent.append((lid, coff))
            labels[coff].append((bi, lid))
            q += 4
        blocks.append(dict(index=bi, offset=off, tag=tag, entries=ent))
    return blocks, t2, labels


def code_range(eb):
    """(start, end) of the instruction stream, or None for a stub file."""
    _, _, _, tail_off, _ = parse_header(eb)
    _, _, labels = parse_blocks(eb)
    if not labels:
        return None
    return min(labels), tail_off


def decode(eb):
    """Yield (offset, opcode, operand_bytes, value) over the whole stream.

    `value` is the operand decoded as an unsigned little-endian integer for
    1/2/4-byte operands, else None.
    """
    rng = code_range(eb)
    if rng is None:
        return
    start, end = rng
    pos = start
    while pos < end:
        op = eb[pos]
        if op > MAXOP:
            raise ValueError(f"invalid opcode {op:#04x} at {pos:#06x}")
        n = OPLEN[op] if op < len(OPLEN) else 0
        raw = eb[pos + 1:pos + 1 + n]
        val = None
        if n == 1:
            val = raw[0]
        elif n == 2:
            val = struct.unpack("<H", raw)[0]
        elif n == 4:
            val = struct.unpack("<I", raw)[0]
        yield pos, op, raw, val
        pos += 1 + n


# --------------------------------------------------------------------------- #
# symbols

def speaker_names(plot_cab):
    """north01.sym group 0 -- the speaker-name table indexed by opcode 0x6A."""
    d = plot_cab.read("north01.sym")
    assert d[:4] == b".STR"
    n0 = struct.unpack_from("<I", d, 8)[0]          # group-0 count (89)
    out, pos = [], 0x18
    while len(out) < n0:
        e = d.index(b"\x00", pos)
        out.append(d[pos:e].decode("cp932", "replace"))
        pos = e + 1
    return out


# --------------------------------------------------------------------------- #
# speaker attribution

def messages(eb):
    """Return [(offset, kind, window_index, speaker_index)] in program order.

    kind is the opcode (0x6B/0x6C/0x73/0x74).  speaker_index is the operand of
    the most recent 0x6A, or None if none preceded it.
    """
    out, spk = [], None
    for off, op, raw, val in decode(eb):
        if op in SPEAKER_OPS:
            spk = val
        elif op in MESSAGE_OPS:
            out.append((off, op, _window_of(op, val), spk))
    return out


def window_speakers(eb):
    """window index -> (speaker index, opcode).  Later writes win."""
    d = {}
    for off, op, win, spk in messages(eb):
        d[win] = (spk, op)
    return d


# --------------------------------------------------------------------------- #
# CLI

def dis(script, plot_cab, out):
    eb = plot_cab.read(script.upper() + ".EB")
    hs, ver, nb, toff, tsz = parse_header(eb)
    blocks, t2, labels = parse_blocks(eb)
    names = speaker_names(plot_cab)
    out.write(f"; {script.upper()}.EB  size={len(eb):#x} version={ver} "
              f"blocks={nb} tail={toff:#x}+{tsz:#x}\n")
    for b in blocks:
        out.write(f";  block {b['index']:2} @{b['offset']:#06x} tag={b['tag']:#x} "
                  f"labels={len(b['entries'])} "
                  f"{b['entries'][0][1]:#x}..{b['entries'][-1][1]:#x}\n")
    spk = None
    for off, op, raw, val in decode(eb):
        for bi, lid in labels.get(off, []):
            out.write(f"blk{bi}.L{lid:#x}:\n")
        if op == 0x6a:
            spk = val
        txt = ""
        if op == 0x6a:
            txt = f"   ; {names[val] if val < len(names) else '?'}"
        elif op in MESSAGE_OPS:
            txt = (f"   ; window {_window_of(op, val)}, speaker "
                   f"{names[spk] if spk is not None and spk < len(names) else '?'}")
        out.write(f"{off:04x}: {op:02x} {OPNAME.get(op,''):<12} "
                  f"{'' if val is None else hex(val):<12}"
                  f"{' '.join('%02x' % b for b in raw) if OPLEN[op] > 4 else ''}{txt}\n")


def report(script, plot_cab, mtg_cab, out):
    from windows import script_windows
    eb = plot_cab.read(script.upper() + ".EB")
    names = speaker_names(plot_cab)
    wins, strs = script_windows(script, plot_cab, mtg_cab)
    ws = window_speakers(eb)
    out.write(f"# {script.upper()}: {len(wins)} windows, {len(strs)} strings\n")
    for w in wins:
        spk, op = ws.get(w["window"], (None, None))
        nm = names[spk] if spk is not None and spk < len(names) else "-"
        kind = {0x6b: "msg", 0x6c: "msg2", 0x73: "menu", 0x74: "menu2"}.get(op, "?")
        line = " / ".join(strs[i] for i in w["strings"])
        out.write(f"[{w['window']:>4}] {nm:<8} {kind:<5} {w['wave']:<11} {line}\n")


def verify(plot_cab, mtg_cab, out):
    from windows import script_windows
    names = speaker_names(plot_cab)
    scripts = sorted(n[:-3] for n in plot_cab.names if n.upper().endswith(".EB"))
    tot = ok = 0
    for s in scripts:
        eb = plot_cab.read(s + ".EB")
        try:
            ms = messages(eb)
        except Exception as e:
            out.write(f"{s:<14} DECODE FAIL: {e}\n")
            continue
        if not ms:
            out.write(f"{s:<14} (empty)\n")
            continue
        try:
            wins, strs = script_windows(s, plot_cab, mtg_cab)
            nwin = len(wins)
        except Exception:
            nwin = None
        maxw = max(w for _, _, w, _ in ms)
        nospk = sum(1 for _, _, _, sp in ms if sp is None)
        good = nospk == 0 and (nwin is None or maxw < nwin)
        tot += 1
        ok += good
        # narration check: speaker 1 == "独白" should have no voice file
        mono = voiced_mono = 0
        if nwin:
            ws = window_speakers(eb)
            for w in wins:
                sp = ws.get(w["window"], (None, None))[0]
                if sp == 1:
                    mono += 1
                    if w["wave"]:
                        voiced_mono += 1
        out.write(f"{s:<14} msgs={len(ms):5} maxwin={maxw:5} mtgwin={nwin} "
                  f"no-speaker={nospk} monologue={mono}(voiced {voiced_mono}) "
                  f"{'OK' if good else '**'}\n")
    out.write(f"{ok}/{tot} scripts consistent\n")


def main():
    args = [a for a in sys.argv[1:]]
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    plot_cab = Cab(PLOT_CB)
    if not args or args[0] in ("-h", "--help"):
        out.write(__doc__ + "\n")
    elif args[0] == "--verify":
        verify(plot_cab, Cab(MTG_CB), out)
    elif "--dis" in args:
        dis(args[0], plot_cab, out)
    else:
        report(args[0], plot_cab, Cab(MTG_CB), out)
    out.flush()


if __name__ == "__main__":
    main()
