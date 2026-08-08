# -*- coding: utf-8 -*-
"""글자 전진폭(자간) 실험 패치 — `TRFSTRINGS.DLL` 2바이트.

## 어디를 고치나

글자 엔진은 `TRFSTRINGS.DLL` 이다([PROPORTIONAL-WIDTH.md](../../docs/PROPORTIONAL-WIDTH.md)).
글자 루프 `0x10003558`~`0x100035C8` 안에서

    0x100035b4  mov.l  @r9,r4        ; 폭을 읽는다 — 모든 글자에 같은 값
    0x100035b8  add    @(52,r10),r4  ; + 자간
    0x100035be  sub    @(48,r10),r4  ; − 보정
    0x100035c8  add    r4,r12        ; ★ 펜 X 전진

`mov.l @r9,r4`(`0x6492`)는 **２바이트**고 `mov #imm,r4`(`0xE4ii`)도 **２바이트**다.
그래서 같은 길이로 갈아끼울 수 있다 — 오프셋도 재배치도 건드리지 않는다.

## ★ 이건 전역이다

모든 글자가 같은 폭이 된다. 공백도 마찬가지라 **어절 간격 문제는 안 풀린다.**
그건 슬롯별 폭 표가 있어야 한다. 이 패치의 목적은 두 가지 확인이다.

  1. `0x100035C8` 이 정말 펜 전진인가 (화면이 좁아지면 확정)
  2. 자간을 줄이면 실제로 보기 좋은가 — 한글 잉크가 ２２px 이므로 ２４→２２ 가 딱 맞고
     ２０ 까지 가면 촘촘해진다

## 그리기 폭은 따로다

`0x100035a8` 의 `mov.l @r9,r6`(`0x6692`)이 같은 값을 **그리기 호출에도** 넘긴다.
전진만 줄이면 잉크 위치가 어긋날 수 있다 — `風雨来記3` 가 겪은 좌측 정렬 문제와
같은 뿌리다. `draw=True` 로 그쪽도 함께 바꿔 볼 수 있다.

## 끄기

`kitae.config.json` 의 `font_advance` 를 지우거나 `null` 로 둔다.
"""
import struct

# (VA, 원래 워드, 무엇)
ADVANCE = (0x100035B4, 0x6492, "펜 전진용 폭")     # mov.l @r9,r4
DRAW = (0x100035A8, 0x6692, "그리기 호출용 폭")     # mov.l @r9,r6

MOV_IMM = {4: 0xE400, 6: 0xE600}                  # mov #imm,r4 / r6


def _text(blob):
    """(.text 파일 오프셋, .text 시작 VA)"""
    e = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, e + 20)[0]
    nsec = struct.unpack_from("<H", blob, e + 6)[0]
    base = struct.unpack_from("<I", blob, e + 24 + 28)[0]
    off = e + 24 + opt
    for i in range(nsec):
        b = blob[off + 40 * i: off + 40 * (i + 1)]
        if b[:8].rstrip(b"\0") == b".text":
            vs, rva, rs, raw = struct.unpack_from("<IIII", b, 8)
            return raw, base + rva
    raise ValueError(".text 를 못 찾았다")


# ── 탐침: 레코드 `+8` 이 문자 코드인지 확인한다 ──────────────────────────────
#
# 그리기 루프의 `r8` 은 이번 글자의 １６바이트 레코드를 가리킨다. 레코드는
# `0x10003B08`~`0x10003B1A` 에서 네 워드(+0 +4 +8 +12)를 그대로 베껴 만들어지고,
# 토크나이저는 노드의 **`+8` 에 문자 코드**를 넣는다(`0x10007BC8`). 그러니
# `@(8,r8)` 이 코드일 것이다 — 화면으로 확인한다.
#
# `mov #imm` 한 방으로는 못 하므로 뒤따르는 `*N` 자간 계산까지 덮는다.
# 본문에 `*N` escape 가 없으면 그 두 필드는 ０ 이라 덮어도 잃을 게 없다.
#
#   0x100035B4  mov.b  @(8,r8),r0     코드의 하위 바이트
#   0x100035B6  add    #1,r11         ← 글자 인덱스. 그대로 둔다
#   0x100035B8  extu.b r0,r4          부호 없이 0..255
#   0x100035BA  shlr2  r4             ÷4
#   0x100035BC  shlr   r4             ÷2  → 0..31
#   0x100035BE  add    #4,r4          +4  → 4..35 (화면 밖으로 안 날아가게)
#
# 같은 글자가 이어지면 간격이 고르고, 다른 글자면 들쭉날쭉해진다.
# `shift` 로 나누고 `base` 를 더해 폭 범위를 정한다. 좁으면 글자가 겹쳐
# 차이를 눈으로 못 가린다 — 처음에 ÷8+4(4~35px)로 했다가 절반씩 겹쳤다.
# 글리프 잉크가 ２２px 이므로 **바닥을 １８ 쯤에 두어야** 읽으면서 차이가 보인다.
SHIFT_OPS = {3: (0x4409, 0x4401),      # shlr2 + shlr  → ÷8
             4: (0x4409, 0x4409)}      # shlr2 + shlr2 → ÷16

PROBE_SITES = (
    (0x100035B4, 0x6492),      # mov.l @r9,r4       → mov.b @(8,r8),r0
    (0x100035B8, 0x51AD),      # mov.l @(52,r10),r1 → extu.b r0,r4
    (0x100035BA, 0x341C),      # add   r1,r4        → 시프트 1
    (0x100035BC, 0x52AC),      # mov.l @(48,r10),r2 → 시프트 2
    (0x100035BE, 0x3428),      # sub   r2,r4        → add #base,r4
)


def probe(blob, shift=4, base=18):
    """레코드 `+8` 의 하위 바이트로 전진폭을 만든다. (새 바이트, 설명)"""
    if shift not in SHIFT_OPS:
        raise ValueError(f"shift 는 {sorted(SHIFT_OPS)} 중 하나여야 한다: {shift}")
    if not 0 <= base <= 127:
        raise ValueError(f"base 는 0~127 이어야 한다: {base}")
    s1, s2 = SHIFT_OPS[shift]
    new = (0x8488, 0x640C, s1, s2, 0x7400 | base)
    raw, lo = _text(blob)
    out = bytearray(blob)
    for (va, want), w in zip(PROBE_SITES, new):
        fo = raw + (va - lo)
        got = struct.unpack_from("<H", out, fo)[0]
        if got != want:
            raise ValueError(f"{va:#x} 워드가 {got:#06x} — {want:#06x} 를 기대했다")
        struct.pack_into("<H", out, fo, w)
    hi = base + (255 >> shift)
    return bytes(out), [f"탐침 @(8,r8)>>{shift} + {base}  →  {base}~{hi}px"]


def patch(blob, width, draw=False):
    """(새 바이트, 바꾼 자리 설명). 원래 워드가 다르면 멈춘다."""
    if not 0 <= width <= 127:
        raise ValueError(f"폭은 0~127 이어야 한다 (mov #imm 는 8비트): {width}")
    raw, lo = _text(blob)
    out = bytearray(blob)
    done = []
    sites = [(ADVANCE, 4)] + ([(DRAW, 6)] if draw else [])
    for (va, want, what), reg in sites:
        fo = raw + (va - lo)
        got = struct.unpack_from("<H", out, fo)[0]
        if got != want:
            raise ValueError(
                f"{va:#x} 의 워드가 {got:#06x} 다 — {want:#06x} 를 기대했다. "
                "다른 빌드이거나 이미 패치된 파일이다")
        struct.pack_into("<H", out, fo, MOV_IMM[reg] | width)
        done.append(f"{va:#x} {what} → mov #{width},r{reg}")
    return bytes(out), done
