"""ENC2 (de)compressor for Hudson TRF .CB archives (北へ。White Illumination).

Format, recovered 2026-08-05 by known-plaintext analysis and verified against
every ENC2 entry on the disc; subsequently confirmed instruction-by-instruction
against TRF/TRFSCORE.DLL (Windows CE SH-4 PE, image base 0x10000000):

    CTRFLzss::Decompress(this, src, srcLen, dst, dstLen)   VA 0x10002d54
        = slot 4 of the ITRFCompless vtable at .rdata 0x1004c748
    CBitStream::GetBit(this)                               VA 0x10002a7c

The container dispatcher at VA 0x100017d0 matches the chunk tag against
"ENC0"/"ENC1"/"ENC2" and creates the ITRFCompless implementation named
"ITRFCompless" (stored), "CTRFHuffman" (unused on this disc) or "CTRFLzss".

  The bit stream is read LSB-first within each byte (bit 0 of byte 0 comes
  first), while multi-bit VALUES are assembled MSB-first (the first bit read is
  the value's most significant bit).

  Loop:
    flag = 1 bit
      1 -> literal:  8 bits            -> emit that byte
      0 -> match:   12 bits  src       -> absolute position in the 4096B window
                    src == 0 IS THE END-OF-STREAM MARKER (see below)
                     4 bits  len - 2   -> match length, 2..17
                    emit window[(src + k) & 0xFFF] for k in 0..len-1

  Window: 4096-byte ring buffer, zero-filled at start. Every emitted byte
  (literal or copied) is written to the window at the write cursor, which then
  advances modulo 4096. **The write cursor starts at 1, not 0** — so the byte at
  output index i lives at window position (i + 1) & 0xFFF. Copies read through
  the same window they write to, so overlapping run-length matches work
  naturally. Position 0 is therefore never a legal match source, which is what
  frees `src == 0` to act as the terminator.

  Termination: the engine's loop has NO output-length check — it runs until it
  reads a match with src == 0. Emitted bytes past `out_size` are silently dropped
  by the engine's bounded output stream, but the window is still updated for them.
  Decoding here stops at `out_size` instead, which is equivalent for well-formed
  streams; an encoder, however, MUST emit the terminator.
  Measured on 154 real streams: 112 carry the explicit src == 0 terminator right
  after the last needed byte and the other 42 simply run out of bits there, and
  src == 0 never once appears mid-stream — consistent with position 0 being an
  illegal match source (the cursor starts at 1 and only reaches 0 after a full
  4096-byte wrap, by which time the encoder avoids it). Every compressed chunk is
  padded to a 4-byte boundary.

  The decompressed size is NOT stored in the stream; it comes from the CAB INFO
  record's `stored_size` field. The chunk's own u32 size is the compressed size.

Usage:
    from kitae.core.enc2 import decompress, compress
    plain = decompress(payload, expected_size)
"""

WINDOW_BITS = 12
WINDOW_SIZE = 1 << WINDOW_BITS
WINDOW_MASK = WINDOW_SIZE - 1
LENGTH_BITS = 4
MIN_MATCH = 2
MAX_MATCH = MIN_MATCH + (1 << LENGTH_BITS) - 1   # 17
START_POS = 1


def decompress(data: bytes, out_size: int) -> bytes:
    """Decompress an ENC2 chunk payload to exactly `out_size` bytes."""
    win = bytearray(WINDOW_SIZE)
    wpos = START_POS
    out = bytearray()
    pos = 0
    nbits = len(data) * 8

    def read_bit():
        nonlocal pos
        if pos >= nbits:
            raise ValueError(
                f"ENC2: stream exhausted after {len(out)}/{out_size} bytes")
        b = (data[pos >> 3] >> (pos & 7)) & 1
        pos += 1
        return b

    def read_val(n):
        v = 0
        for _ in range(n):
            v = (v << 1) | read_bit()
        return v

    while len(out) < out_size:
        if read_bit():
            c = read_val(8)
            out.append(c)
            win[wpos] = c
            wpos = (wpos + 1) & WINDOW_MASK
        else:
            src = read_val(WINDOW_BITS)
            length = read_val(LENGTH_BITS) + MIN_MATCH
            for k in range(length):
                c = win[(src + k) & WINDOW_MASK]
                out.append(c)
                win[wpos] = c
                wpos = (wpos + 1) & WINDOW_MASK

    return bytes(out[:out_size])


_CAND_CAP = 4096   # 후보 리스트 상한 (96→4096: 게임 원본 압축기 수준 도달, ~1s/청크)


def compress(data: bytes) -> bytes:
    """Produce a valid ENC2 stream for `data`.

    Not bit-identical to Hudson's encoder (match choices differ), but it decodes
    back to exactly the input, which is what archive rebuilding needs.
    """
    win = bytearray(WINDOW_SIZE)
    wpos = START_POS
    # positions in the window holding each byte value, most recent last
    buckets = [[] for _ in range(256)]
    bits = bytearray()

    def put_val(v, n):
        for i in range(n - 1, -1, -1):
            bits.append((v >> i) & 1)

    def push(byte):
        nonlocal wpos
        win[wpos] = byte
        buckets[byte].append(wpos)
        if len(buckets[byte]) > _CAND_CAP:   # cap the candidate list
            del buckets[byte][:-_CAND_CAP]
        wpos = (wpos + 1) & WINDOW_MASK

    i, n = 0, len(data)
    while i < n:
        best_len, best_src = 0, 0
        maxlen = min(MAX_MATCH, n - i)
        if maxlen >= MIN_MATCH:
            for p in reversed(buckets[data[i]]):
                # A copy reads through the window it is writing, so once k
                # reaches the source-to-cursor distance the decoder starts
                # seeing bytes emitted by this very match.
                dist = (wpos - p) & WINDOW_MASK
                if dist == 0 or p == 0:
                    # src == 0 is the end-of-stream marker, never a match source
                    continue
                ln = 0
                while ln < maxlen:
                    src = (data[i + ln - dist] if ln >= dist
                           else win[(p + ln) & WINDOW_MASK])
                    if src != data[i + ln]:
                        break
                    ln += 1
                if ln > best_len:
                    best_len, best_src = ln, p
                    if ln == maxlen:
                        break
        # a match costs 17 bits, literals cost 9 each -> worth it from length 2
        if best_len >= MIN_MATCH:
            bits.append(0)
            put_val(best_src, WINDOW_BITS)
            put_val(best_len - MIN_MATCH, LENGTH_BITS)
            for k in range(best_len):
                push(data[i + k])
            i += best_len
        else:
            bits.append(1)
            put_val(data[i], 8)
            push(data[i])
            i += 1

    # end-of-stream marker: match flag + src == 0. The engine's decode loop has
    # no length check and stops only here, so this is mandatory.
    bits.append(0)
    put_val(0, WINDOW_BITS)

    out = bytearray((len(bits) + 7) // 8)
    for idx, b in enumerate(bits):
        if b:
            out[idx >> 3] |= 1 << (idx & 7)
    out += b"\0" * (-len(out) % 4)      # chunk payloads are 4-byte aligned
    return bytes(out)


if __name__ == "__main__":
    import sys, struct, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from kitae.core.cab import Cab
    cab = Cab(sys.argv[1])
    i = cab.names.index(sys.argv[2])
    esz, eoff, _, _ = cab.entries[i]
    tag = cab.data[eoff:eoff + 4]
    csz = struct.unpack("<I", cab.data[eoff + 4:eoff + 8])[0]
    payload = cab.data[eoff + 8:eoff + 8 + csz]
    sys.stdout.buffer.write(payload if tag == b"ENC0" else decompress(payload, esz))
