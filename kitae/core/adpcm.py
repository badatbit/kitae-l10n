# -*- coding: utf-8 -*-
"""음성 파일(aNNNN.p04) 디코더 — 드림캐스트 AICA 4비트 ADPCM.

헤더가 없는 raw 스트림이다. 한 바이트에 니블 두 개가 들어 있고 낮은 니블이
먼저다. 재생 주파수는 파일에 없으므로 밖에서 준다.

대사(aNNNN.p04)는 18000Hz 다 — TRFSTRINGS.DLL 0x1000374C 에서 WAVEFORMATEX
를 `wFormatTag=32(Yamaha ADPCM), 1ch, 18000Hz, 4bit` 으로 짜서 넘긴다. 효과음
(se/ses*.p04)만 22050Hz 다.
"""
import struct

DIFF = [1, 3, 5, 7, 9, 11, 13, 15, -1, -3, -5, -7, -9, -11, -13, -15]
SCALE = [0x0E6, 0x0E6, 0x0E6, 0x0E6, 0x133, 0x199, 0x200, 0x266] * 2


def decode(data):
    """4비트 ADPCM → 16비트 PCM 샘플 목록."""
    cur, step = 0, 127
    out = []
    for b in data:
        for nib in (b & 0x0F, b >> 4):
            cur += (step * DIFF[nib]) >> 3
            cur = -32768 if cur < -32768 else (32767 if cur > 32767 else cur)
            step = (step * SCALE[nib]) >> 8
            step = 0x7F if step < 0x7F else (0x6000 if step > 0x6000 else step)
            out.append(cur)
    return out


def to_wav(samples, rate=18000):
    """PCM 목록을 WAV 바이트로."""
    body = struct.pack(f"<{len(samples)}h", *samples)
    return (b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(body)) + body)


def p04_to_wav(data, rate=18000):
    return to_wav(decode(data), rate)
