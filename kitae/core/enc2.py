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


_CAND_CAP = 4096   # 2바이트 쌍 후보 상한. 4096 이면 구판(1바이트 버킷 4096)과
                   # 원시 텍스처에서 **바이트 수까지 동일한 압축률**, 속도 ~7.6배
                   # (512 는 +0.17% — M05 가 40→32색으로 떨어질 만큼의 차이였다)


def compress(data: bytes) -> bytes:
    """Produce a valid ENC2 stream for `data`.

    Not bit-identical to Hudson's encoder (match choices differ), but it decodes
    back to exactly the input, which is what archive rebuilding needs.

    구현 메모 — 창(4096B 링)은 언제나 "직전 4095바이트의 출력"이고 인코더의
    출력은 입력 그대로이므로, 매치 탐색은 입력 버퍼의 자기 참조(절대 위치)로
    한다. 길이 2 이상의 매치는 반드시 첫 2바이트가 같으므로 2바이트 쌍 해시
    체인이 후보 공간을 빠짐없이 덮는다. src 필드는 절대 위치 p 의 창 좌표
    (p+1)&0xFFF (쓰기 커서가 1에서 시작) — 0 은 EOS 마커라 그 좌표는 건너뛴다.
    겹침 매치(dist < len)는 data[p+k] == data[i+k] 비교가 그대로 성립한다
    (디코더가 창을 쓰면서 읽는 동작과 동치).
    """
    n = len(data)
    bits = bytearray()
    append = bits.append

    def put_val(v, nb):
        for j in range(nb - 1, -1, -1):
            append((v >> j) & 1)

    heads = {}          # (b0<<8 | b1) -> [절대 위치 …] (최신이 뒤)
    i = 0
    while i < n:
        best_len = 0
        best_src = 0
        maxlen = MAX_MATCH if n - i >= MAX_MATCH else n - i
        if maxlen >= MIN_MATCH:
            chain = heads.get((data[i] << 8) | data[i + 1])
            if chain:
                lo = i - WINDOW_MASK           # 창 밖(거리 ≥ 4096)은 무효
                for p in reversed(chain):      # 최신(가까운) 후보부터
                    if p < lo:
                        break                  # 이 뒤는 전부 더 오래된 위치
                    if (p + 1) & WINDOW_MASK == 0:
                        continue               # src == 0 은 EOS 마커
                    ln = 2
                    while ln < maxlen and data[p + ln] == data[i + ln]:
                        ln += 1
                    if ln > best_len:
                        best_len = ln
                        best_src = (p + 1) & WINDOW_MASK
                        if ln == maxlen:
                            break
        # a match costs 17 bits, literals cost 9 each -> worth it from length 2
        if best_len >= MIN_MATCH:
            append(0)
            put_val(best_src, WINDOW_BITS)
            put_val(best_len - MIN_MATCH, LENGTH_BITS)
            end = i + best_len
        else:
            append(1)
            put_val(data[i], 8)
            end = i + 1
        while i < end:                         # 지나간 위치를 체인에 등록
            if i + 1 < n:
                key = (data[i] << 8) | data[i + 1]
                c = heads.get(key)
                if c is None:
                    heads[key] = [i]
                else:
                    c.append(i)
                    if len(c) > _CAND_CAP:
                        del c[:-_CAND_CAP]
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
