# -*- coding: utf-8 -*-
"""가변폭 — 폭 표를 심고 글자마다 전진폭을 다르게 준다.

경위와 근거는 [PROPORTIONAL-WIDTH.md](../../docs/PROPORTIONAL-WIDTH.md).
값은 [widths.py](widths.py) 한 곳에서 온다.

## 훅 자리

글자 루프(`0x10003558`~`0x100035C8`)의

    0x100035b4  mov.l  @r9,r4        ; 폭 — 모든 글자에 같은 값
    0x100035b6  add    #1,r11        ; 글자 인덱스
    0x100035b8  mov.l  @(52,r10),r1  ; + `*N` 자간
    0x100035ba  add    r1,r4
    0x100035bc  mov.l  @(48,r10),r2  ; − 보정
    0x100035be  sub    r2,r4
    0x100035c8  add    r4,r12        ; 펜 X 전진

`0x100035B4`~`0x100035BF` **１２바이트**를 통째로 스텁 호출로 바꾼다. 본문에
`*N` escape 가 없으면 `+52`·`−48` 은 ０ 이라 잃을 게 없고, `add #1,r11` 은
스텁 첫 줄로 옮긴다.

## ★ 재배치가 필요 없다

새 섹션의 절대주소를 코드에 박으면 로드 때 안 밀려 죽는다(`風雨来記3` 가 겪은
함정). 대신 **전부 상대로** 짠다.

  * 훅 → 스텁: `bsrf` 는 `PC + Rn` 이라 사거리 제한이 없다. `Rn` 에 넣는 값이
    **거리**이므로 로드 주소와 무관하다. (`bsr` 은 ±４KB 라 못 닿는다 —
    `.text` 의 유일한 케이브가 훅에서 ３６KB 떨어져 있다)
  * 스텁 → 표: `mova` 로 PC 상대 주소를 얻는다. 표를 스텁 바로 뒤에 붙인다.

그래서 `.reloc` 에 넣을 것이 하나도 없다.

## 무엇을 깨도 되나 (역어셈블로 확인)

훅 직후가 `r1`·`r2`·`r0` 을 차례로 덮어쓰고 `cmp/gt` 로 `T` 를 새로 만든다.
그러므로 **`r0`~`r3` 과 `T` 는 자유**. 살릴 것은 `r4`(결과)·`r8`(레코드)·
`r9`~`r13`·`r15`. `bsrf` 가 덮는 `pr` 은 이 함수가 끝에서 스택에서 꺼내므로
루프 도중에는 살릴 필요가 없다.

## 표 구조

    페이지맵 256B   코드>>8 →  0x80|w  그 페이지는 전부 폭 w (한 바이트로 끝)
                              0..0x7F 하위표 번호
    하위표 N×256B   코드&0xFF → 폭

**한글 페이지는 전부 ２２ 단일값**이라 하위표가 필요 없다. 그래서 페이지맵에
직접값을 넣어 ６페이지분(1,536B)을 덜어냈다 — 디스크 익스텐트가 １섹터
모자랐다. 지금은 페이지맵 + 하위표 ３장 = 1,024B.

손대지 않는 페이지는 `0x80|24` 라 기본폭이 저절로 나온다 — 별도 검사가 없다.
"""
import struct

from kitae.build import sh4

HOOK = 0x100035B4
HOOK_LEN = 12                 # 0x100035B4 ~ 0x100035BF
DEFAULT_W = 24
# ★ 문자 코드는 레코드에 없다. 레코드(`obj+84 + 글자*320 + 크기*16`)는 텍스처
# 사각형이다 — 진단판으로 `+12` 를 폭으로 써 봤더니 모든 글자가 똑같이 ２４
# 안팎이었다(바이트 길이 1·2 였다면 반각·전각이 갈렸어야 한다).
#
# 코드는 **따로 u16 배열**에 있다. 엔진 자신이 여섯 군데에서 이렇게 읽는다
# (`0x100033BE`·`0x100033EE`·`0x100031C4` …):
#
#     mov.l  @(0x1FFC,obj),r0    ; 코드 배열
#     shll   idx                 ; ×2
#     mov.w  @(r0,idx),r1        ; u16 코드
#     extu.w r1,r1
#
# 이어서 `shad #-12` 로 상위 니블을 뽑아 분류하므로 **cp932 그대로**
# (`lead<<8 | trail`, 반각은 바이트 값)다. 우리 표의 키와 같다.
#
# 객체 배치 — 레코드 배열이 폭 배열 바로 앞에서 정확히 끝난다:
#     obj+0x0054  레코드 25글자 × 320  (= 20크기 × 16B)
#     obj+0x1F94  폭 배열 (크기별)      ← 루프의 `@r9`
#     obj+0x1FF4  현재 인덱스
#     obj+0x1FFC  ★ 코드 배열 포인터
#     obj+0x2004  글자 수
# ★ 오프셋 주의 — 코드 배열을 쓰는 자리는 전부 기준에서 **４를 빼고** 나서
# `0x1FFC` 를 더한다.
#
#     0x10003126  mov.l @(52,r14),r13
#     0x10003128  add   #-4,r13          ← 이것
#     0x1000312a  mov.w 0x1FF4,r2        인덱스
#     0x1000312e  mov.w 0x2004,r1        개수
#
# 그렇게 보였지만 `+0x1FF8` 은 **포인터가 아니었다 — 인게임에서 죽는다.**
# 기준이 다른 두 객체가 섞여 있다는 뜻이다. 오프셋은 `0x1FFC` 로 둔다. 우리 루프는 `r10` 을 그대로 쓴다
# (폭 배열도 `r10+0x1F94` 로 바로 간다). 처음에 `0x1FFC` 로 읽었다가 늘
# 작은 값이 나왔다 — 상위 바이트가 항상 ０ 이라 어느 글자든 페이지 ０ 에
# 떨어졌고, 그래서 한글 폭을 ２２·２４·４０ 어느 것으로 바꿔도 화면이
# 꿈쩍하지 않았다.
CODE_PTR = 0x1FFC             # obj+0x1FF8 = u16 코드 배열 포인터
OBJ_REG = 10                  # 루프에서 r10 = 객체, r11 = 글자 인덱스

# 훅이 덮는 원래 워드 — 다르면 다른 빌드다
HOOK_ORIG = (0x6492, 0x7B01, 0x51AD, 0x341C, 0x52AC, 0x3428)


# ★ 디스크 익스텐트에 여유가 1,024B 뿐이다.
# TRFSTRINGS 의 ISO 엔트리는 1,275,904B 인데 원본이 1,274,880B 다. 그래서
# 스텁+표가 그 안에 들어가야 한다 — 하위표는 두 장까지만 쓴다.
#   스텁 52 + 페이지맵 256 + 하위표 2×256 = 820B  → 파일 정렬 1,024B
MAX_SUBS = 2


def build_table(cfg, swap=False, probe=None):
    """(표 바이트, 하위표 수).

    `swap` 이면 코드 키의 두 바이트를 뒤집는다 — 엔진이 `mov.w` 한 번으로
    읽으면 리틀엔디언이라 `0xEE 0xB0` 이 `0xB0EE` 가 된다.
    `probe` 를 주면 코드페이지(한글) 전부를 그 폭으로 강제한다 — 진단용.
    """
    import io
    import json
    from kitae.build.widths import CELL, SHAPE, Widths

    W = Widths(cfg)
    with io.open(cfg.path("data", "codepage.json"), encoding="utf-8") as fh:
        cp = json.load(fh)

    def key(a, b):
        return (b << 8) | a if swap else (a << 8) | b

    table = {}
    for ch, cell in cp.items():
        table[key(cell[0], cell[1])] = probe or W.width(ch)
    for ch in SHAPE:
        try:
            b = ch.encode("cp932")
        except Exception:
            continue
        table[b[0] if len(b) == 1 else key(b[0], b[1])] = W.width(ch)
    for c in range(0x20, 0x7F):
        table[c] = max(1, min(CELL, W.ink_w(chr(c)) + 2))

    pages = {}
    for code, w in table.items():
        pages.setdefault(code >> 8, {})[code & 0xFF] = w

    import collections
    pagemap = bytearray([0x80 | DEFAULT_W]) * 256
    subs = bytearray()
    nsub = 0
    # ★ 하위표는 두 장뿐이라 **어느 페이지에 주느냐가 곧 품질**이다.
    # 전에는 "폭 종류가 많은 순"으로 줬더니 URL 용 ASCII 페이지가 한 장을
    # 가져가고, 정작 공백이 든 페이지가 대표값 １３ 으로 뭉개졌다
    # (공백 9 → 13, `。` 10 → 13). 본문에서 １９,０００번 나오는 공백이
    # ２１７번 나오는 URL 에 밀린 것이다.
    #
    # 그래서 **본문에서 실익이 있는 페이지를 먼저** 준다. 공백이 든 페이지와
    # 전각 숫자·라틴이 든 페이지 — 가변폭으로 얻는 것이 거기 다 있다.
    # (한글 페이지는 전부 ２２ 단일값이라 하위표가 필요 없다)
    key = [ch.encode("cp932")[0] for ch in ("　", "０")]

    def rank(q):
        return (key.index(q) if q in key else len(key),
                -len(set(pages[q].values())))

    for p in sorted(pages, key=rank):
        ws = set(pages[p].values())
        if len(ws) > 1 and nsub < MAX_SUBS:
            pagemap[p] = nsub
            nsub += 1
            row = bytearray([DEFAULT_W]) * 256
            for low, w in pages[p].items():
                row[low] = w
            subs += row
        else:
            w = collections.Counter(pages[p].values()).most_common(1)[0][0]
            assert w < 0x80
            pagemap[p] = 0x80 | w
    return bytes(pagemap) + bytes(subs), nsub


RULER = (8, 16, 28, 40)


def table_ruler(shift):
    """진단용 페이지맵 — 페이지 번호의 두 비트를 **폭으로 부호화**한다.

        폭 = RULER[(페이지 >> shift) & 3]        8 / 16 / 28 / 40

    엔진이 넘겨주는 코드가 무엇인지 모를 때 그 코드의 상위 바이트를 화면에서
    직접 읽어내는 자다. `shift` 를 ６·４·２·０ 으로 네 판 구우면 ２５６페이지가
    한 값으로 좁혀진다 — 네 폭이 확연히 달라 눈으로 틀릴 여지가 없다.

    한글 페이지(`0x9B`·`0xE1`~`0xE3`·`0xED`·`0xEE`)를 ４０ 으로 올려도 화면이
    안 변했는데 **모든** 페이지를 ４０ 으로 하니 변했다. 그래서 코드가 우리가
    아는 cp932 짝이 아님이 확정됐다. 바이트를 뒤집은 것도 아니었다.
    """
    return bytes(0x80 | RULER[(p >> shift) & 3] for p in range(256)), 0


def table_low(shift):
    """진단용 — **하위 바이트**를 폭으로 부호화한다.

        모든 페이지 → 하위표 0,  하위표0[i] = RULER[(i >> shift) & 3]

    눈금자 네 판으로 코드의 상위 바이트가 항상 ０ 임이 드러났다(한글이 어느
    글자든 같은 폭이었다). 그러면 코드는 사실상 한 바이트다. 그게 무엇인지 —
    cp932 트레일 바이트인지, 리드 바이트인지, 다른 번호인지 — 를 가른다.

    `방` 은 우리 코드페이지에서 `0xEE 0xB0` 이므로

        트레일(0xB0=176) 이면  shift=6 에서 ２８px
        리드  (0xEE=238) 이면  shift=6 에서 ４０px
    """
    return bytes(256) + bytes(RULER[(i >> shift) & 3] for i in range(256)), 1


def table_uniform(width=40):
    """진단용 페이지맵 — **２５６페이지 전부 직접값 `width`**. 하위표 없음.

    "스텁이 우리 표를 실제로 타는가" 를 이진으로 묻는다. 어느 코드가 오든
    같은 값이 나오므로 코드가 무엇인지와 무관하다.

        전부 벌어짐  → 표를 탄다. 그러면 한글이 ２０ 이었던 건 **코드가
                       우리가 아는 cp932 짝이 아니어서** 엉뚱한 페이지를
                       맞힌 것이다
        한글만 그대로 → 한글은 이 루프를 아예 안 지난다
    """
    return bytes([0x80 | width]) * 256, 0


def stub_flat(width=22):
    """진단용 — 표를 안 보고 무조건 `width` 를 돌려준다.

    사슬(훅 → 징검다리 → 스텁 → 복귀)이 정상인지 값 문제와 갈라내려고 쓴다.
    이걸로 글자가 **고르게** 나오면 사슬은 멀쩡하고 표를 찾는 자리가 틀린 것,
    여전히 들쭉날쭉하면 스텁이 `r4` 를 제대로 못 넘기는 것이다.
    """
    S = sh4
    return S.assemble([
        (S.add_imm(1, 11), "add #1,r11"),        # 훅에서 밀려난 것
        (S.mov_imm(width, 4), f"mov #{width},r4"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ])


def stub_len():
    """진단용 — 레코드 `+12`(바이트 길이)에 ８을 곱해 폭으로 쓴다.

    토크나이저는 노드 `+8` 에 코드, `+12` 에 **바이트 길이**(반각 1 · 전각 2)를
    넣는다(`0x10007840`·`0x10007BC8` 에서 확인). 레코드 채우는 루프가 그 네
    워드를 그대로 베끼므로, 그리기 루프의 `@(12,r8)` 은 １ 또는 ２ 여야 한다.

    그래서 `폭 = @(12,r8) × 8` 로 두면

        전각(한글) 전부 **１６px 로 균일**   → 레코드가 생각대로다
        들쭉날쭉하거나 화면이 깨짐          → `r8` 이 그 레코드가 아니다

    `+8` 이 코드인지 직접 보는 것보다 훨씬 알아보기 쉽다 — 코드는 값이 제각각이라
    화면만 봐서는 맞는지 틀린지 가릴 수가 없다.
    """
    S = sh4
    return S.assemble([
        (S.add_imm(1, 11), "add #1,r11"),               # 훅에서 밀려난 것
        (S.movl_disp_rm(12, 8, 4), "mov.l @(12,r8),r4"),
        (S.shll2(4), "shll2 r4"),                       # ×4
        (S.shll(4), "shll r4"),                         # ×8
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ])


def stub_code():
    """스텁 기계어. 리터럴과 표가 이 코드 **바로 뒤**(4바이트 정렬)에 붙는다."""
    S = sh4
    body = [
        (S.movl_pc(0, 0), None),                             # r0 = 0x1FFC (뒤에서)
        (S.movl_r0_rm(OBJ_REG, 3), "mov.l @(r0,r10),r3"),    # r3 = 코드 배열
        (S.mov_reg(11, 0), "mov r11,r0"),
        (S.shll(0), "shll r0"),                              # 인덱스 × 2
        (S.movw_r0_rm(3, 3), "mov.w @(r0,r3),r3"),           # ★ u16 코드
        (S.extu_w(3, 3), "extu.w r3,r3"),
        # ★ 코드를 읽은 **뒤에** 인덱스를 올린다. 원래 `add #1,r11` 은 폭을 읽은
        # 다음 자리였다 — 먼저 올리면 한 글자씩 밀린 코드를 보게 된다.
        (S.add_imm(1, 11), "add #1,r11"),
        (S.mova(0), None),                    # mova @(표,PC),r0 — 뒤에서 채운다
        (S.mov_reg(0, 1), "mov r0,r1"),                      # r1 = 표 주소
        (S.mov_reg(3, 0), "mov r3,r0"),
        (S.shlr8(0), "shlr8 r0"),                            # r0 = 페이지
        (S.movb_r0_rm(1, 2), "mov.b @(r0,r1),r2"),
        (S.extu_b(2, 2), "extu.b r2,r2"),                    # 페이지맵 값
        (S.mov_reg(2, 0), "mov r2,r0"),
        (S.tst_imm(0x80), "tst #128,r0"),                    # 최상위 비트?
        (S.bf(0), None),                                     # 켜져 있으면 직접값
        (S.shll8(2), "shll8 r2"),                            # 번호*256
        (S.mov_imm(1, 0), "mov #1,r0"),
        (S.shll8(0), "shll8 r0"),                            # 256
        (S.add_reg(0, 2), "add r0,r2"),                      # 페이지맵 건너뜀
        (S.add_reg(1, 2), "add r1,r2"),                      # 하위표 주소
        (S.extu_b(3, 0), "extu.b r3,r0"),                    # 코드 하위 바이트
        (S.movb_r0_rm(2, 4), "mov.b @(r0,r2),r4"),           # ★ 폭
        (S.extu_b(4, 4), "extu.b r4,r4"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        (S.mov_reg(2, 4), "mov r2,r4"),                      # direct:
        (S.add_imm(-128, 4), "add #-128,r4"),                # 0x80 을 뺀다
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ]
    direct = 26
    bf_at = 15
    body[bf_at] = (S.bf(direct - (bf_at + 2)), None)

    n = len(body)
    lit_off = (n * 2 + 3) & ~3                  # 리터럴도 표도 4바이트 정렬
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    table_off = lit_off + 4
    # mov.l/mova 둘 다 R0 = (PC & ~3) + disp, PC = 명령주소 + 4
    body[0] = (S.movl_pc(lit_off - ((0 * 2 + 4) & ~3), 0), None)
    body[7] = (S.mova(table_off - ((7 * 2 + 4) & ~3)), None)
    return S.assemble(body) + struct.pack("<I", CODE_PTR), table_off


def hook_code(hook_va, stub_va):
    """훅 １２바이트. `bsrf` 로 스텁까지 상대 분기한다."""
    S = sh4
    # ★ bsrf 는 다섯째 명령(주소 hook+8)이다. 목적지 = (bsrf주소+4) + r0.
    # 예전에 `extu.b` 를 넣고도 이 식을 hook+6 으로 두어 **２바이트 어긋난**
    # 자리로 뛰었다. 명령을 하나 더하거나 빼면 여기도 같이 고쳐야 한다.
    BSRF_AT = 8
    delta = stub_va - (hook_va + BSRF_AT + 4)
    if delta <= 0:
        raise ValueError(f"스텁이 훅보다 앞에 있다: {delta:#x}")
    hi, lo = delta >> 8, delta & 0xFF
    # `add #imm` 은 부호 확장이다. lo 가 0x80 이상이면 음수로 들어가므로
    # 상위를 하나 올리고 하위를 음수로 준다 — 합은 같다.
    if lo >= 0x80:
        hi, lo = hi + 1, lo - 0x100
    if hi > 0xFF:
        raise ValueError(f"거리 {delta:#x} 가 64KB 를 넘는다")
    # `mov #imm` 은 부호 확장이므로 hi 가 0x80 이상이면 `extu.b` 로 지운다
    body = [
        (S.mov_imm(hi - 0x100 if hi >= 0x80 else hi, 0), None),
        (S.extu_b(0, 0), "extu.b r0,r0"),          # 부호 확장 제거 → 0..255
        (S.shll8(0), "shll8 r0"),                  # hi<<8
        (S.add_imm(lo, 0), None),                  # + lo  → r0 = 거리
        (S.bsrf(0), "bsrf r0"),
        (S.nop(), "nop"),                          # 지연 슬롯
    ]
    code = S.assemble(body)
    assert len(code) == HOOK_LEN, len(code)
    return code


def trampoline(tramp_va, stub_va):
    """징검다리 — 훅에서 닿는 `.text` 케이브에 놓고 스텁까지 길게 뛴다.

    훅의 １２바이트로는 １６비트 거리밖에 못 만드는데 새 섹션은 １MB 넘게
    떨어져 있다(TRFSTRINGS 가 대부분 폰트 데이터다). 그래서 두 단으로 간다.

        훅 --bsrf(16비트)--> 징검다리 --braf(32비트 리터럴)--> 스텁 --rts--> 훅 다음

    `braf` 라 `pr` 을 안 건드리므로 스텁의 `rts` 가 훅 자리로 정확히 돌아온다.
    리터럴은 **거리**라 로드 주소와 무관하다 — 재배치가 필요 없다.
    """
    S = sh4
    body = [
        (S.movl_pc(4, 0), None),          # mov.l @(4,pc),r0  → 리터럴
        (S.braf(0), "braf r0"),
        (S.nop(), "nop"),                 # 지연 슬롯
        (S.nop(), "nop"),                 # 리터럴 4바이트 정렬용
    ]
    code = S.assemble(body)
    # braf 는 인덱스 1(주소 +2). 목적지 = (그 주소 + 4) + r0
    delta = stub_va - (tramp_va + 2 + 4)
    return code + struct.pack("<i", delta)


SECTION = ".ktrw"
CHARS = 0x60000020            # CODE | EXECUTE | READ


def _section_va(blob, name):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    base_va = struct.unpack_from("<I", blob, pe + 24 + 28)[0]
    o = pe + 24 + opt
    for i in range(nsec):
        b = blob[o + 40 * i: o + 40 * (i + 1)]
        if b[:8].rstrip(bytes(1)) == name.encode():
            return base_va + struct.unpack_from("<I", b, 12)[0]
    raise KeyError(name)


def apply(cfg, blob):
    """(새 DLL 바이트, 설명). 섹션을 붙이고 표를 싣고 훅을 건다."""
    from kitae.build import advance, pesection

    raw, lo = advance._text(blob)
    for i, want in enumerate(HOOK_ORIG):
        got = struct.unpack_from("<H", blob, raw + (HOOK - lo) + i * 2)[0]
        if got != want:
            raise ValueError(
                f"{HOOK + i * 2:#x} 워드가 {got:#06x} — {want:#06x} 를 기대했다. "
                "다른 빌드이거나 이미 패치된 파일이다")

    mode = cfg.get("font_variable")
    flat = mode in ("flat", "len")
    if mode == "cp40":
        code, _ = stub_code()
        table, npages = build_table(cfg, probe=40)
    elif isinstance(mode, str) and mode.startswith("low"):
        code, _ = stub_code()
        table, npages = table_low(int(mode[3:]))
    elif isinstance(mode, str) and mode.startswith("ruler"):
        code, _ = stub_code()
        table, npages = table_ruler(int(mode[5:]))
    elif mode == "swap40":
        code, _ = stub_code()
        table, npages = build_table(cfg, swap=True, probe=40)
    elif mode == "page40":
        flat = False
    if mode == "cp40":
        code, _ = stub_code()
        table, npages = build_table(cfg, probe=40)
    elif isinstance(mode, str) and mode.startswith("low"):
        code, _ = stub_code()
        table, npages = table_low(int(mode[3:]))
    elif isinstance(mode, str) and mode.startswith("ruler"):
        code, _ = stub_code()
        table, npages = table_ruler(int(mode[5:]))
    elif mode == "swap40":
        code, _ = stub_code()
        table, npages = build_table(cfg, swap=True, probe=40)
    elif mode == "page40":
        code, _ = stub_code()
        table, npages = table_uniform()
    elif mode == "len":
        code, table, npages = stub_len(), b"", 0
    elif flat:
        code, table, npages = stub_flat(), b"", 0
    else:
        code, _ = stub_code()
        table, npages = build_table(cfg)
    payload = code + table

    out, foff, _fsize = pesection.add(blob, SECTION, len(payload), CHARS)
    va = _section_va(out, SECTION)

    out = bytearray(out)
    out[foff:foff + len(payload)] = payload

    # `.text` 꼬리의 빈 자리에 징검다리를 놓는다 — 훅에서 １６비트로 닿는다
    tramp_va, tramp_off = _cave(out, raw, lo)
    tramp = trampoline(tramp_va, va)
    if any(out[tramp_off:tramp_off + len(tramp)]):
        raise ValueError(f"케이브 {tramp_va:#x} 가 비어 있지 않다")
    out[tramp_off:tramp_off + len(tramp)] = tramp
    # ★ 케이브는 파일 패딩이라 `.text` 의 **가상 크기 밖**이다. 그대로 두면
    # 로더가 그 자리를 안 올려 ０만 실행된다 — 실제로 그래서 무한 반복이
    # 안 고쳐졌다. 징검다리 끝까지 덮이도록 VirtualSize 를 늘린다.
    _grow_virtual(out, ".text", (tramp_va - lo) + len(tramp))

    hook = hook_code(HOOK, tramp_va)
    out[raw + (HOOK - lo): raw + (HOOK - lo) + HOOK_LEN] = hook

    # ★ 뛰는 자리를 다시 계산해 맞는지 본다. 예전에 명령을 하나 더하고 거리
    # 식을 안 고쳐 ２바이트 어긋난 자리로 뛰었다 — 죽지는 않고 글자 인덱스가
    # 안 늘어 같은 음성이 １초마다 되풀이됐다. 눈으로는 못 잡는 종류다.
    _check_jump(out, raw, lo, tramp_va, va)

    what = (f"가변폭[진단 {mode}]: 스텁 {len(code)}B" if flat else
            f"가변폭: 스텁 {len(code)}B + 표 {len(table)}B({npages}페이지)")
    note = f"{what} @ {va:#x} · 징검다리 {tramp_va:#x} · 훅 {HOOK:#x}"
    return bytes(out), note


def _grow_virtual(blob, name, need):
    """섹션의 VirtualSize 를 `need` 이상으로 늘린다. raw 안이어야 한다."""
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    o = pe + 24 + opt
    for i in range(nsec):
        h = o + 40 * i
        if blob[h:h + 8].rstrip(bytes(1)) != name.encode():
            continue
        vsize, rva, rsize, _r = struct.unpack_from("<IIII", blob, h + 8)
        if need <= vsize:
            return vsize
        if need > rsize:
            raise ValueError(f"{name}: 가상 {need}B 가 파일 {rsize}B 를 넘는다")
        struct.pack_into("<I", blob, h + 8, need)
        return need
    raise KeyError(name)


def _check_jump(blob, text_raw, text_va, tramp_va, stub_va):
    """훅과 징검다리가 **정말 그 자리로 뛰는지** 바이트에서 되짚는다.

    거리 식을 손으로 맞추다 어긋나면 죽지도 않고 조용히 틀린다. 그래서 만든
    바이트를 다시 해석해 목적지를 계산하고 기대값과 대조한다.
    """
    def w(va):
        return struct.unpack_from("<H", blob, text_raw + (va - text_va))[0]

    # 훅: mov #hi,r0 / extu.b / shll8 / add #lo,r0 / bsrf r0
    hi = w(HOOK) & 0xFF
    lo_ = w(HOOK + 6) & 0xFF
    if lo_ >= 0x80:
        lo_ -= 0x100
    r0 = ((hi << 8) + lo_) & 0xFFFFFFFF
    got = HOOK + 8 + 4 + r0
    if got != tramp_va:
        raise ValueError(f"훅이 {got:#x} 로 뛴다 — 징검다리는 {tramp_va:#x} 다")

    # 징검다리: mov.l @(4,pc),r0 / braf r0 / nop / nop / .long 거리
    off = text_raw + (tramp_va - text_va)
    # ★ CPU 가 실제로 읽는 자리에서 꺼낸다. `mov.l @(disp,PC)` 는
    # `(PC & ~3) + disp`, PC = 명령주소 + 4. 우리가 쓴 자리와 다를 수 있다.
    disp = (w(tramp_va) & 0xFF) * 4
    lit_va = ((tramp_va + 4) & ~3) + disp
    if lit_va != tramp_va + 8:
        raise ValueError(
            f"리터럴을 {lit_va:#x} 에서 읽는데 쓴 자리는 {tramp_va + 8:#x} 다 — "
            "징검다리가 4바이트 정렬이 아니다")
    delta = struct.unpack_from("<i", blob, text_raw + (lit_va - text_va))[0]
    got = tramp_va + 2 + 4 + delta
    if got != stub_va:
        raise ValueError(f"징검다리가 {got:#x} 로 뛴다 — 스텁은 {stub_va:#x} 다")


def _cave(blob, text_raw, text_va):
    """`.text` 꼬리의 연속 ０ 구간. (VA, 파일오프셋) — 짝수 주소로 맞춘다."""
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    o = pe + 24 + opt
    size = None
    for i in range(nsec):
        b = blob[o + 40 * i: o + 40 * (i + 1)]
        if b[:8].rstrip(bytes(1)) == b".text":
            size = struct.unpack_from("<I", b, 16)[0]
    end = text_raw + size
    k = 0
    while blob[end - 1 - k] == 0:
        k += 1
    if k < 32:
        raise ValueError(f".text 꼬리 빈 자리가 {k}B 뿐이다")
    # ★ 4바이트 정렬이어야 한다. `mov.l @(disp,PC)` 는 `(PC & ~3)` 기준이라
    # 홀수 워드 주소에 놓으면 내림이 걸려 **리터럴을 2바이트 앞에서 읽는다.**
    # 실제로 0x1000C31A 에 놓았다가 그렇게 어긋났다 — 캡스톤 출력의
    # `mov.l 0x1000c320,r0` 이 이미 말해 주고 있었는데 지나쳤다.
    off = (end - k + 3) & ~3
    va = text_va + (off - text_raw)
    assert va % 4 == 0, hex(va)
    return va, off
