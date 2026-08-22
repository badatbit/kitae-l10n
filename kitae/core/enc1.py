"""ENC1 decompressor for Hudson TRF .CB archives (북へ。White Illumination).

ENC1 = **static Huffman**, but the code table is NOT stored canonically (as
DEFLATE/JPEG do). Instead the header carries per-symbol **weights** (byte
frequencies) and the tree is rebuilt at load time by the exact greedy algorithm
the engine uses — so the decoder must reproduce that construction, tie-breaking
included, or the codes come out different. (This is why treating the header as a
canonical code-length / counts-per-length table never satisfies Kraft.)

The runtime handler is `CTRFHuffman`; on this disc its `Compress`/`Decompress`
vtable slots are the shared `_purecall` stub (`0x10034cb8`, used 1233× across
TRFSCORE.DLL), i.e. **left unimplemented in the shipping build** — the 32 ENC1
chunks (11 `.SET`, 21 sound `.p04`; 3442 ENC2 / 13177 ENC0 for comparison) are
build-tool leftovers. The format was recovered from the data instead and every
one of the 32 chunks round-trips to its exact `stored_size`.

Header (byte stream):
    start = u8
    loop:
        end = u8
        if end >= start:  for sym in start..end:  weight[sym] = u8
        start = u8
        if start == 0:  break            # a zero start byte ends the table
    (the first range may legitimately start at 0, hence the do/while shape)

Tree: leaves 0..255 are byte values; leaf 256 is the end-of-stream marker and
is given weight 1. Repeatedly combine the two lowest-weight live nodes (weights
are kept modulo 0x10000); strict `>` comparisons reproduce the engine's
index-order tie-breaking. Internal nodes are appended from index 257 up; the
last one created is the root.

Bitstream (immediately after the table): bits are read **LSB-first** within each
byte (bit 0 of the byte first). At each node, bit 0 → zero-child, bit 1 →
one-child, until a leaf; leaf 256 stops decoding.

The decompressed size is not in the stream — it comes from the CAB INFO record's
`stored_size`, passed here as `out_size`.

Usage:
    from kitae.core.enc1 import decompress
    plain = decompress(payload, expected_size)
"""

END_MARKER = 256
_INF = 513          # scratch "infinity" node used while picking the two minima


def decompress(data: bytes, out_size: int | None = None) -> bytes:
    """Decompress an ENC1 chunk payload. If `out_size` is given it is checked."""
    # nodes[i] = [weight, zero_child, one_child]; 0..255 bytes, 256 end marker,
    # 257.. internal nodes, 513 the temporary infinity sentinel.
    nodes = [[0, 0, 0] for _ in range(514)]
    pos = 0

    def u8():
        nonlocal pos
        if pos >= len(data):
            raise ValueError("ENC1 header is truncated")
        v = data[pos]
        pos += 1
        return v

    # --- weight table -----------------------------------------------------
    start = u8()
    while True:
        end = u8()
        if end >= start:
            for sym in range(start, end + 1):
                nodes[sym][0] = u8()
        start = u8()
        if start == 0:
            break
    nodes[END_MARKER][0] = 1

    # --- rebuild the Huffman tree the way CTRFHuffman does ----------------
    nodes[_INF][0] = 0xFFFF
    nxt = END_MARKER + 1
    while True:
        first = second = _INF
        for i in range(nxt):
            w = nodes[i][0]
            if not w:
                continue
            if nodes[first][0] > w:
                second, first = first, i
            elif nodes[second][0] > w:
                second = i
        if second == _INF:
            break
        nodes[nxt] = [(nodes[first][0] + nodes[second][0]) & 0xFFFF, first, second]
        nodes[first][0] = 0
        nodes[second][0] = 0
        nxt += 1
    root = nxt - 1

    # --- decode the bitstream (LSB-first) ---------------------------------
    bit = pos * 8
    nbits = len(data) * 8
    out = bytearray()
    while True:
        node = root
        while node > END_MARKER:
            if bit >= nbits:
                raise ValueError("ENC1 bitstream ended before the end marker")
            b = (data[bit >> 3] >> (bit & 7)) & 1
            bit += 1
            node = nodes[node][2 if b else 1]
        if node == END_MARKER:
            break
        out.append(node)
        if out_size is not None and len(out) > out_size:
            raise ValueError("ENC1 output exceeded the expected size")

    if out_size is not None and len(out) != out_size:
        raise ValueError(
            f"ENC1 size mismatch: decoded {len(out)}, expected {out_size}")
    return bytes(out)


if __name__ == "__main__":
    import sys, struct, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    from kitae.core.cab import Cab
    cab = Cab(sys.argv[1])
    i = cab.names.index(sys.argv[2])
    esz, eoff, _, _ = cab.entries[i]
    csz = struct.unpack("<I", cab.data[eoff + 4:eoff + 8])[0]
    payload = cab.data[eoff + 8:eoff + 8 + csz]
    sys.stdout.buffer.write(decompress(payload, esz))
