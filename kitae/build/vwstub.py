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

# ★ 조사 훅 — inner 진입(0x10003AE6, r11=문자열 시작)에서 글자수(@(28,r14))와
# r11 에서 글자수*2 글자(=*4 바이트, 두 배 길이) 복사. @(28,r14)가 실제 길이의
# 절반이면 뒷부분이 드러난다. 원본 6워드(r11,r12,r5 세팅) 재현. 복귀 0x10003AF2.
HOOK2 = 0x10003AE6
HOOK2_LEN = 12
HOOK2_ORIG = (0x6BA3, 0x4B08, 0xEC54, 0x3C8C, 0xE550, 0x4508)

# ★ DrawChar #1 래퍼 훅 — 첫 DrawChar(vtable[52]) 호출 구간(0x10003582~0x1000358D,
# jsr+지연슬롯 포함)을 스텁으로 감싼다. 스텁이 rec 완성→x2 스왑(width→x1+24)→jsr
# DrawChar 재발행. 진입 시 r8=obj+84, r4=글자*320, r2=줄*16, r3=@r13, r13=렌더러,
# r6/r7=폭배열. 복귀 0x1000358E. 트램폴린은 r0만 클로버.
HOOK3 = 0x10003582
HOOK3_LEN = 12
HOOK3_ORIG = (0x384C, 0x533D, 0x382C, 0x6583, 0x430B, 0x64D3)

# ★ (진단) 문자열→텍스처 렌더러 진입 뒤(pr 저장 후) 0x100076DC. r5=문자열. 여기서
# 받은 문자열을 스크래치에 덤프해 실제 몇 글자 받는지 본다. 복귀 0x100076E8.
HOOK4 = 0x100076DC
HOOK4_LEN = 12
HOOK4_ORIG = (0x6843, 0x6A53, 0x7FB0, 0x6EF3, 0x7FBC, 0x548E)

# ★ CTRFTextOut 전진폭 훅 — CTRFTXOut(타이틀 VMS 메시지·가이드북 도시 설명·옵션·저장
# 안내 등 12개 모듈)이 품은 CTRFTextOut::DrawString(0x10009bec)의 전진 구간
# 0x10009CE2~0x10009CED(12B: mov.l lit,r0 / mov #100,r5 / mov.l @(48,r10),r2 /
# mul.l r2,r8 / jsr @r0 / sts macl,r4). r8 은 상자폭(24=2바이트, 12=1바이트)이고
# 같은 r8 이 0x10009cb6 의 DrawChar 상자폭에도 쓰이므로 **상자는 두고 전진만** 표로
# 바꾼다. 글자 코드는 r11(이미 글자 뒤로 전진)에서 되읽는다: r8==24 면
# (@(r11-2)<<8)|@(r11-1), 아니면 원래 12 유지. 복귀 0x10009CEE. 임시 r0~r5 (r6·r7 불변).
# 스텁은 .ktrw 가 아니라 .text 꼬리 케이브(징검다리 뒤)에 둔다 — .ktrw 는 디스크
# 익스텐트 한계라 68B 뿐이고, 케이브면 훅 bsrf(16비트)로 바로 닿고 나눗셈 썽크
# 0x1000b4e0 도 bsr(±4KB) 안이다. 표는 .ktrw 의 기존 표를 mova+거리 리터럴로 공유.
HOOK5 = 0x10009CE2
HOOK5_LEN = 12
HOOK5_ORIG = (0xD056, 0xE564, 0x52AC, 0x0827, 0x400B, 0x041A)
HOOK5_DIV = 0x1000B4E0        # 원본이 jsr 하던 나눗셈 썽크(COREDLL #2001, r4/r5→r0)


# ★ 디스크 익스텐트에 여유가 1,024B 뿐이다.
# TRFSTRINGS 의 ISO 엔트리는 1,275,904B 인데 원본이 1,274,880B 다. 그래서
# 스텁+표가 그 안에 들어가야 한다 — 하위표는 두 장까지만 쓴다.
#   스텁 52 + 페이지맵 256 + 하위표 2×256 = 820B  → 파일 정렬 1,024B
MAX_SUBS = 2


def build_table(cfg, swap=False, probe=None):
    """(표 바이트, 하위표 수). 값은 전부 widths.Widths — 코드페이지의 모든 셀(한글·ASCII·
    공백·합자)과 `・`·전각 공백 0x8140(=EN 12), 그리고 1바이트 ASCII(보호 항목용, 엔진 반각 12).

    `swap` 이면 코드 키의 두 바이트를 뒤집는다 — 엔진이 `mov.w` 한 번으로 읽으면
    리틀엔디언이라 `0xEE 0xB0` 이 `0xB0EE` 가 된다. `probe` 는 한글 페이지 전부를 그
    폭으로 강제한다(진단용).

    하위표는 두 장(MAX_SUBS, 디스크 익스텐트)뿐이다. 기본폭(24)이 아닌 칸이 많은 페이지
    순으로 준다 — 지금은 ASCII 셀 페이지(SYMBOL_PAGE)와 `・`·공백이 든 0x81. 한글 페이지는
    전부 24 라 페이지맵 직접값으로 끝난다."""
    import collections
    from kitae.build.hangul import _read_codepage, is_hangul
    from kitae.build.widths import EN, MID, Widths

    W = Widths(cfg)
    cp = _read_codepage(cfg.path("data", "codepage.json"))

    def key(a, b):
        return (b << 8) | a if swap else (a << 8) | b

    table = {}
    for ch, cell in cp.items():
        table[key(*cell)] = probe if (probe and is_hangul(ch)) else W.width(ch)
    mid = MID.encode("cp932")
    table[key(mid[0], mid[1])] = W.width(MID)
    table[key(0x81, 0x40)] = EN                       # 게임 전각 공백(보호 항목) = 반각 단위 12
    for c in range(0x20, 0x7F):
        table[c] = 12                                 # 1바이트(보호 항목): 엔진 반각

    pages = {}
    for code, w in table.items():
        pages.setdefault(code >> 8, {})[code & 0xFF] = w

    pagemap = bytearray([0x80 | DEFAULT_W]) * 256
    subs = bytearray()
    nsub = 0

    def rank(q):                                      # 기본폭 아닌 칸이 많은 순
        return -sum(1 for w in pages[q].values() if w != DEFAULT_W)

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
            if len(ws) > 1:
                print(f"  ⚠ 폭표: 페이지 {p:#x} 는 폭이 {len(ws)}종인데 하위표가 없어 {w} 로 뭉갬")
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


def stub_rec8(shift=24):
    """진단용 — 레코드 `+8` 값의 한 바이트를 눈금자로 읽는다.

        폭 = 페이지맵[(@(8,r8) >> shift) & 0xFF]

    `+8` 은 글꼴이 준 메트릭 중 **글자마다 다른 유일한 값**이다(첫 판에서 폭이
    제각각 나왔던 근거). 그것이 포인터인지 작은 번호인지 가른다 — 인덱스가
    항상 ０~２５５ 라 표 밖으로 나가지 않아 죽을 위험이 없다.

        상위 바이트가 0x8C 대  → RAM 포인터
        상위 바이트가 0x00    → 작은 번호 (글리프 인덱스일 수 있다)
    """
    S = sh4
    # ★ `mova` 는 결과를 **r0 에** 넣는다. 인덱스를 r0 에 먼저 만들어 두면
    # 덮어쓴다 — 인덱스는 r2 에 두었다가 `mova` 뒤에 옮긴다.
    body = [(S.movl_disp_rm(8, 8, 3), "mov.l @(8,r8),r3"),
            (S.add_imm(1, 11), "add #1,r11"),
            (S.mov_reg(3, 2), "mov r3,r2")]
    if shift >= 16:
        body.append((S.shlr16(2), "shlr16 r2"))
    for _ in range((shift % 16) // 8):
        body.append((S.shlr8(2), "shlr8 r2"))
    body += [
        (S.extu_b(2, 2), "extu.b r2,r2"),
        (S.mova(0), None),                     # r0 = 표
        (S.mov_reg(0, 1), "mov r0,r1"),        # r1 = 표
        (S.mov_reg(2, 0), "mov r2,r0"),        # r0 = 인덱스
        (S.movb_r0_rm(1, 4), "mov.b @(r0,r1),r4"),
        (S.extu_b(4, 4), "extu.b r4,r4"),
        (S.add_imm(-128, 4), "add #-128,r4"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ]
    mova_at = next(i for i, x in enumerate(body) if x[1] is None)
    n = len(body)
    table_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((table_off - n * 2) // 2)
    body[mova_at] = (S.mova(table_off - ((mova_at * 2 + 4) & ~3)), None)
    return S.assemble(body), table_off


def stub_chain(chain=(0x1FE4, 0x1FFC)):
    """`r10` 에서 오프셋을 따라 두 번 역참조해 코드 배열에 닿는 스텁.

    코드 배열은 `ITRFStrTiming` 객체의 `+0x1FFC`(= `+0x1FF8` 과 같은 버퍼)에
    있다 — `0x10003478` 이 거기에 `malloc(글자수*2)` 를 넣고 호출자가 준 u16 을
    베낀다. 그런데 그리기 루프의 `r10` 은 그 객체가 아니다(`+0x1FF8` 로 읽었더니
    인게임에서 죽었다). 루프가 매 글자 넘기는 `*(r10+0x1FE4)` 가 그 객체로 보여
    한 단계 더 따라간다.
    """
    S = sh4
    body = [
        (S.movl_pc(0, 0), None),                             # r0 = chain[0]
        (S.movl_r0_rm(OBJ_REG, 3), "mov.l @(r0,r10),r3"),
        (S.movl_pc(0, 0), None),                             # r0 = chain[1]
        (S.movl_r0_rm(3, 3), "mov.l @(r0,r3),r3"),           # r3 = 코드 배열
        (S.mov_reg(11, 0), "mov r11,r0"),
        (S.shll(0), "shll r0"),
        (S.movw_r0_rm(3, 3), "mov.w @(r0,r3),r3"),
        (S.extu_w(3, 3), "extu.w r3,r3"),
        (S.add_imm(1, 11), "add #1,r11"),
        (S.mova(0), None),
        (S.mov_reg(0, 1), "mov r0,r1"),
        (S.mov_reg(3, 0), "mov r3,r0"),
        (S.shlr8(0), "shlr8 r0"),
        (S.movb_r0_rm(1, 2), "mov.b @(r0,r1),r2"),
        (S.extu_b(2, 2), "extu.b r2,r2"),
        (S.mov_reg(2, 0), "mov r2,r0"),
        (S.tst_imm(0x80), "tst #128,r0"),
        (S.bf(0), None),
        (S.shll8(2), "shll8 r2"),
        (S.mov_imm(1, 0), "mov #1,r0"),
        (S.shll8(0), "shll8 r0"),
        (S.add_reg(0, 2), "add r0,r2"),
        (S.add_reg(1, 2), "add r1,r2"),
        (S.extu_b(3, 0), "extu.b r3,r0"),
        (S.movb_r0_rm(2, 4), "mov.b @(r0,r2),r4"),
        (S.extu_b(4, 4), "extu.b r4,r4"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        (S.mov_reg(2, 4), "mov r2,r4"),                      # direct:
        (S.add_imm(-128, 4), "add #-128,r4"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ]
    direct, bf_at = 28, 17
    body[bf_at] = (S.bf(direct - (bf_at + 2)), None)
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    table_off = lit_off + 8                     # 리터럴 두 개
    body[0] = (S.movl_pc(lit_off - ((0 * 2 + 4) & ~3), 0), None)
    body[2] = (S.movl_pc(lit_off + 4 - ((2 * 2 + 4) & ~3), 0), None)
    body[9] = (S.mova(table_off - ((9 * 2 + 4) & ~3)), None)
    blob = S.assemble(body) + struct.pack("<II", chain[0], chain[1])
    return blob, table_off


def stub_code():
    """스텁 기계어. 표가 이 코드 **바로 뒤**(4바이트 정렬)에 붙는다.

    ★ 코드는 `obj+0x3C` 의 **노드 리스트**에 있다(2026-08-15 라이브 확정).
    `obj+0x1FFC` 는 코드 배열이 아니라 모든 객체가 공유하는 테이블(`0x01A5D0D4`)이라,
    거기서 읽으면 텍스트와 무관하게 인덱스만 같으면 같은 폭이 나온다(위치-의존 버그).

    노드 접근:
        r3 = *(obj+0x3C)        노드 리스트 헤더 va (엔진과 같은 주소공간이라 그대로 역참조)
        r3 = 헤더 + 0x20        node[0] (헤더 뒤 0x20 부터 노드가 늘어선다)
        r3 = node[0] + r11*16   글자 인덱스 r11 번째 노드 (16B stride)
        r3 = *(node+0)          u16 code (little-endian [trail,lead])

    ★ 가정: 노드가 물리 연속(마크업 없는 UI 시스템 메시지)이고 노드 idx = 글자 idx.
    인게임은 마크업 토큰이 섞여 어긋날 수 있다 — 먼저 UI 로 검증한다.
    `r10` 이 obj 인 것은 그대로다(`0x10003536` 레코드=obj+0x54, `@(52,r10)` 자간).
    """
    # ★ 스크래치 배열 전진판 — 우리 대사창 전용 그리기 루프라 rec+8(렌더용)을 안
    # 건드리고, 전진폭만 우리 배열 0x8CFE0100[charIdx] 에서 읽는다. 복사 루프가 그
    # 배열을 width 로 채운다. rec+8 안 건드리니 렌더는 게임 원래(24)대로, 재렌더 충돌도
    # 없음. 배열은 P1(0x8C) 물리라 va↔phys 무관.
    # ★ 스크래치 배열 전진판 (원래 로직 포함) — 훅이 덮는 원래 6워드는 @r9(전진폭
    # 기본) + add#1,r11(charIdx++) + 자간 + 보정 이다. 우리는 @r9 자리만 배열값으로
    # 바꾸고 나머지 원래 로직(charIdx++, 자간, 보정)은 그대로 재현해야 한다. 안 그러면
    # r11 이 안 늘어 같은 글자 무한 반복 → hang. rec+8(렌더)은 안 건드림.
    #   r4 = 배열[charIdx] (0이면 @r9 fallback) → +자간 -보정 → penX += r4
    S = sh4
    body = [
        (0x60B3, "mov r11,r0"),          # r0 = charIdx (증가 전)
        (0xC9FF, "and #255,r0"),         # & 0xFF (배열 밖 방지)
        (0x4008, "shll2 r0"),            # *4
        (S.movl_pc(0, 1), None),         # r1 = 0x8CFE0100 (배열)
        (0x310C, "add r0,r1"),
        (0x6412, "mov.l @r1,r4"),        # [5] r4 = 배열[charIdx]
        (0xE028, "mov #40,r0"),          # [6] 상한 CELL(=40)
        (0x3406, "cmp/hi r0,r4"),        # [7] r4 > 40 ? (미초기화 0xC0C0C0 등 거름)
        (0x8901, None),                  # [8] bt use_r9
        (0x2448, "tst r4,r4"),           # [9] r4 == 0 ?
        (0x8B00, None),                  # [10] bf skip — 유효값이면 배열 사용
        (0x6492, "mov.l @r9,r4"),        # [11] use_r9: @r9 fallback (0 또는 >40)
        # skip: ↓ 원래 6워드의 나머지 5워드 (charIdx++, 자간, 보정)
        (0x7B01, "add #1,r11"),          # [12] ★ charIdx++
        (0x51AD, "mov.l @(52,r10),r1"),  # [13] 자간
        (0x341C, "add r1,r4"),           # [14]
        (0x52AC, "mov.l @(48,r10),r2"),  # [15] 보정
        (0x3428, "sub r2,r4"),           # [16]
        (S.rts(), "rts"),                # [17]
        (S.nop(), "nop"),
    ]
    body[8] = (S.bt(11 - (8 + 2)), None)   # bt use_r9(idx11): r4>40 → fallback
    body[10] = (S.bf(12 - (10 + 2)), None)  # bf skip(idx12): 유효값 → 배열 사용
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[3] = (S.movl_pc(lit_off - ((3 * 2 + 4) & ~3), 1), None)
    return S.assemble(body) + struct.pack("<I", 0x8CFE0100), 0


def stub_code2():
    """복사 루프(0x10003B12) 스텁 — 배열[charIdx] = width(POC 12)를 채우고 훅이 덮은
    원래 6워드(레코드 store)를 그대로 재실행한다. r4 = 글자 인덱스+1(0x10003B10 에서
    이미 ++), 그래서 인덱스는 r4-1. 임시로 r5,r6 만 쓴다(다음 반복 0x10003AF4/B00 에서
    재설정되므로 안전). r0,r1,r2,r3,r7,r14 는 원본이 쓰므로 안 건드린다."""
    # ★ r0 복원판 — hook2 의 bsrf 분기 계산이 r0 를 덮는데, 원본 마지막 워드
    # (mov.w @(r0,r14),r2)가 r0=36 을 기대한다(0x10003AFA 에서 세팅). 그래서 스텁 맨
    # 앞에 mov #36,r0 로 복원한다. 그다음 배열[j]=12 채우고 원본 6워드 재실행.
    # (배열 계산은 r5,r6 만 쓰고 r0 를 안 건드림.)
    S = sh4
    body = [
        (0xE024, "mov #36,r0"),          # ★ r0 = 36 복원 (hook2 bsrf 가 덮었음)
        (0x6543, "mov r4,r5"),           # r5 = j+1
        (0x75FF, "add #-1,r5"),          # r5 = j
        (0x4508, "shll2 r5"),            # r5 = j*4
        (S.movl_pc(0, 6), None),         # r6 = 0x8CFE0100 (배열)
        (0x365C, "add r5,r6"),           # r6 = 배열 + j*4
        (0xE50C, "mov #12,r5"),          # POC width 12
        (0x2652, "mov.l r5,@r6"),        # 배열[j] = 12
        (0xE550, "mov #80,r5"),          # ★ r5 복원 (stride) — 다음 반복 mul.l r4,r5 가
        (0x4508, "shll2 r5"),            #    r5=320 을 기대(80<<2). 안 하면 j*12 로 어긋남
        # ↓ 원본 6워드 재실행
        (0x1212, "mov.l r1,@(8,r2)"),    # dst+8 = x2
        (0x5371, "mov.l @(4,r7),r3"),    # src y1
        (0x1231, "mov.l r3,@(4,r2)"),    # dst+4 = y1
        (0x5173, "mov.l @(12,r7),r1"),   # src y2
        (0x1213, "mov.l r1,@(12,r2)"),   # dst+12 = y2
        (0x02ED, "mov.w @(r0,r14),r2"),  # r2 = 루프 카운터 (r0=36 필요)
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[4] = (S.movl_pc(lit_off - ((4 * 2 + 4) & ~3), 6), None)
    return S.assemble(body) + struct.pack("<I", 0x8CFE0100)


def stub_draw_bufkeytrace():
    """진단 — draw 훅에서 (키, r11)를 링(cnt 0x8CFE08FC, base 0x8CFE0900, 4B=key<<8|r11)에
    기록. 버퍼 읽기·원본 꼬리 그대로(화면 정상). 키별 r11 최대치 = draw 가 그 줄을 몇 번
    읽는지(그리기 횟수). copy 의 조각수(@(36,gbr))와 비교해 불일치를 확인한다."""
    S = sh4
    body = [
        (0x6093, "mov r9,r0"),           # 0
        (0x4009, "shlr2 r0"),            # 1
        (0xC9FF, "and #255,r0"),         # 2  key
        (0x6503, "mov r0,r5"),           # 3  r5 = key (로그용)
        (0x4008, "shll2 r0"),            # 4
        (0x4008, "shll2 r0"),            # 5
        (0x4000, "shll r0"),             # 6  key*32
        (0xD30D, None),                  # 7  mov.l buf,r3
        (0x330C, "add r0,r3"),           # 8
        (0x60B3, "mov r11,r0"),          # 9  charIdx
        (0x330C, "add r0,r3"),           # 10
        (0x6430, "mov.b @r3,r4"),        # 11 폭
        (0x644C, "extu.b r4,r4"),        # 12
        # 로그 (key<<8 | r11) → ring[cnt++]
        (0xD00B, None),                  # 13 mov.l dcnt,r0
        (0x6102, "mov.l @r0,r1"),        # 14 cnt
        (0x6213, "mov r1,r2"),           # 15
        (0x7201, "add #1,r2"),           # 16
        (0x2022, "mov.l r2,@r0"),        # 17 cnt++
        (0x6013, "mov r1,r0"),           # 18
        (0xC97F, "and #127,r0"),         # 19
        (0x4008, "shll2 r0"),            # 20 *4
        (0xD208, None),                  # 21 mov.l dring,r2
        (0x322C, "add r0,r2"),           # 22 슬롯
        (0x6053, "mov r5,r0"),           # 23 key
        (0x4018, "shll8 r0"),            # 24 key<<8
        (0x20BB, "or r11,r0"),           # 25 | r11
        (0x2202, "mov.l r0,@r2"),        # 26 ring[cnt]=key<<8|r11
        # 원본 꼬리
        (0x7B01, "add #1,r11"),          # 27
        (0x51AD, "mov.l @(52,r10),r1"),  # 28
        (0x341C, "add r1,r4"),           # 29
        (0x52AC, "mov.l @(48,r10),r2"),  # 30
        (0x3428, "sub r2,r4"),           # 31
        (S.rts(), "rts"),                # 32
        (S.nop(), "nop"),                # 33
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[7] = (S.movl_pc(lit_off - ((7 * 2 + 4) & ~3), 3), None)        # buf
    body[13] = (S.movl_pc(lit_off + 4 - ((13 * 2 + 4) & ~3), 0), None)  # dcnt
    body[21] = (S.movl_pc(lit_off + 8 - ((21 * 2 + 4) & ~3), 2), None)  # dring
    return S.assemble(body) + struct.pack("<III", 0x8CFE0100, 0x8CFE08FC, 0x8CFE0900)


def stub_draw_orig():
    """draw 훅(0x100035B4) — 전진폭을 버퍼[키*32 + charIdx](0x8CFE0100)에서 읽는다.
    키 = (r9 >> 2) & 0x3F. r9 = 폭배열 주소(obj+0x1F94+줄*4)로, copy 가 쓴 키와 같아
    카운터 없이 정합한다. copy 가 채운 폭을 전진폭으로. 뒤이어 원본 자간/보정 재현.
    r0,r1,r2,r3 임시."""
    S = sh4
    body = [
        (0x6093, "mov r9,r0"),           # 0  r9 = 폭배열 주소
        (0x4009, "shlr2 r0"),            # 1  >>2
        (0xC9FF, "and #255,r0"),         # 2  & 0xFF (256슬롯, 키 충돌 감소)
        (0x4008, "shll2 r0"),            # 3
        (0x4008, "shll2 r0"),            # 4
        (0x4000, "shll r0"),             # 5  키*32
        (0xD306, None),                  # 6  mov.l buf_addr,r3   (0x8CFE0100)
        (0x330C, "add r0,r3"),           # 7  버퍼[키]
        (0x60B3, "mov r11,r0"),          # 8  charIdx
        (0x330C, "add r0,r3"),           # 9  버퍼[키+charIdx]
        (0x6430, "mov.b @r3,r4"),        # 10 폭
        (0x644C, "extu.b r4,r4"),        # 11
        # ── 원본 자간/보정 (charIdx++, +obj52, -obj48) ──
        (0x7B01, "add #1,r11"),          # 12
        (0x51AD, "mov.l @(52,r10),r1"),  # 13
        (0x341C, "add r1,r4"),           # 14
        (0x52AC, "mov.l @(48,r10),r2"),  # 15
        (0x3428, "sub r2,r4"),           # 16
        (S.rts(), "rts"),                # 17
        (S.nop(), "nop"),                # 18
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[6] = (S.movl_pc(lit_off - ((6 * 2 + 4) & ~3), 3), None)       # buf_addr
    return S.assemble(body) + struct.pack("<I", 0x8CFE0100)


def stub_draw_recwidth():
    """draw 훅(0x100035B4) — 고정폭 @r9 대신 레코드(rec=r8)의 글리프 폭(x2-x1 =
    rec+8 - rec+0)을 전진폭으로. rec 는 draw 가 자기 charIdx(줄 기준)로 읽으므로
    copy 의 어절 charIdx 문제와 무관하게 정합한다. 뒤이어 원본의 자간/보정 재현."""
    S = sh4
    body = [
        (0x5482, "mov.l @(8,r8),r4"),    # 0  r4 = x2
        (0x6182, "mov.l @r8,r1"),        # 1  r1 = x1
        (0x3418, "sub r1,r4"),           # 2  r4 = x2 - x1 = 글리프 폭
        (0x60B3, "mov r11,r0"),          # 3  charIdx (진단: 폭 기록)
        (0xC9FF, "and #255,r0"),         # 4
        (0x4008, "shll2 r0"),            # 5
        (0xD304, None),                  # 6  mov.l arr,r3
        (0x330C, "add r0,r3"),           # 7
        (0x2342, "mov.l r4,@r3"),        # 8  배열[charIdx] = 글리프 폭
        (0x7B01, "add #1,r11"),          # 9  charIdx++ (원본)
        (0x51AD, "mov.l @(52,r10),r1"),  # 10 원본: + obj[52]
        (0x341C, "add r1,r4"),           # 11
        (0x52AC, "mov.l @(48,r10),r2"),  # 12 원본: - obj[48]
        (0x3428, "sub r2,r4"),           # 13
        (S.rts(), "rts"),                # 14
        (S.nop(), "nop"),                # 15
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[6] = (S.movl_pc(lit_off - ((6 * 2 + 4) & ~3), 3), None)      # arr
    return S.assemble(body) + struct.pack("<I", 0x8CFE0100)


def stub_draw_trace():
    """draw 훅(0x100035B4) 진단 스텁 — draw 카운터(0x8CFE00E0)로 순차, 배열2
    (0x8CFE0300)에 draw charIdx(r11)를 호출 순서대로 기록. 그다음 원본 6워드 재실행.
    임시 r0,r1,r3 (원본이 곧 r1,r2,r4,r11 재설정하므로 무관)."""
    S = sh4
    body = [
        (0xD309, None),                  # 0  mov.l dcnt_addr,r3
        (0x6032, "mov.l @r3,r0"),        # 1  cnt
        (0x6103, "mov r0,r1"),           # 2  save
        (0x7001, "add #1,r0"),           # 3
        (0x2302, "mov.l r0,@r3"),        # 4  cnt++
        (0x6013, "mov r1,r0"),           # 5  cnt
        (0xC9FF, "and #255,r0"),         # 6
        (0x4008, "shll2 r0"),            # 7
        (0xD306, None),                  # 8  mov.l arr2_addr,r3
        (0x330C, "add r0,r3"),           # 9
        (0x23B2, "mov.l r11,@r3"),       # 10 배열2[cnt] = draw charIdx
        (0x6492, "mov.l @r9,r4"),        # 11 원본 6워드
        (0x7B01, "add #1,r11"),          # 12
        (0x51AD, "mov.l @(52,r10),r1"),  # 13
        (0x341C, "add r1,r4"),           # 14
        (0x52AC, "mov.l @(48,r10),r2"),  # 15
        (0x3428, "sub r2,r4"),           # 16
        (S.rts(), "rts"),                # 17
        (S.nop(), "nop"),                # 18
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[0] = (S.movl_pc(lit_off - ((0 * 2 + 4) & ~3), 3), None)      # dcnt_addr
    body[8] = (S.movl_pc(lit_off + 4 - ((8 * 2 + 4) & ~3), 3), None)  # arr2_addr
    return S.assemble(body) + struct.pack("<II", 0x8CFE00E0, 0x8CFE0300)


def stub_measure_addrtrace():
    """진단 — 복사 훅에서 (폭배열주소, 첫글자코드)를 링에 기록만 하고 폭은 안 건드림
    (화면은 원본 고정 24). 링: 카운터 0x8CFE07FC, 엔트리 8B[+0 addr, +4 code]
    at 0x8CFE0800(다른 스크래치와 겹치지 않게). 줄마다 한 번(inner 진입) 호출되므로 화면의 모든 줄 주소가 순서대로
    쌓인다. 이걸 라이브로 덤프해 파일을/방향버튼의 obj 주소가 같은지(재사용) 다른지
    (해시충돌) 판별한다. r8=obj, r10=줄, r11=글자포인터."""
    S = sh4
    body = [
        (0xD30D, None),                  # 0  mov.l cnt_addr,r3
        (0x6032, "mov.l @r3,r0"),        # 1  cnt
        (0x6203, "mov r0,r2"),           # 2  save cnt
        (0x7001, "add #1,r0"),           # 3
        (0x2302, "mov.l r0,@r3"),        # 4  cnt++
        (0x6023, "mov r2,r0"),           # 5  cnt
        (0xC97F, "and #127,r0"),         # 6  &127
        (0x4008, "shll2 r0"),            # 7
        (0x4000, "shll r0"),             # 8  *8
        (0xD30B, None),                  # 9  mov.l ring_addr,r3
        (0x330C, "add r0,r3"),           # 10 슬롯
        # 폭배열 주소 = obj + 0x1F94 + 줄*4
        (0x6083, "mov r8,r0"),           # 11 obj
        (0xD10B, None),                  # 12 mov.l off,r1  (0x1F94)
        (0x301C, "add r1,r0"),           # 13
        (0x61A3, "mov r10,r1"),          # 14 줄
        (0x4108, "shll2 r1"),            # 15 줄*4
        (0x301C, "add r1,r0"),           # 16 폭배열 주소
        (0x2302, "mov.l r0,@r3"),        # 17 슬롯+0 = addr
        # 첫 글자 코드 (@r11 2바이트)
        (0x62B0, "mov.b @r11,r2"),       # 18 lead
        (0x622C, "extu.b r2,r2"),        # 19
        (0x4218, "shll8 r2"),            # 20 lead<<8
        (0x84B1, "mov.b @(1,r11),r0"),   # 21 trail  (mov.b @(1,r11),r0)
        (0x600C, "extu.b r0,r0"),        # 22
        (0x202B, "or r2,r0"),            # 23 code
        (0x1301, "mov.l r0,@(4,r3)"),    # 24 슬롯+4 = code
        # ── 원본 6워드 (0x10003AE6~) 재현 ──
        (0x6BA3, "mov r10,r11"),         # 25
        (0x4B08, "shll2 r11"),           # 26
        (0xEC54, "mov #84,r12"),         # 27
        (0x3C8C, "add r8,r12"),          # 28
        (0xE550, "mov #80,r5"),          # 29
        (0x4508, "shll2 r5"),            # 30
        (S.rts(), "rts"),                # 31
        (S.nop(), "nop"),                # 32
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[0] = (S.movl_pc(lit_off - ((0 * 2 + 4) & ~3), 3), None)       # cnt_addr
    body[9] = (S.movl_pc(lit_off + 4 - ((9 * 2 + 4) & ~3), 3), None)   # ring_addr
    body[12] = (S.movl_pc(lit_off + 8 - ((12 * 2 + 4) & ~3), 1), None) # off
    return S.assemble(body) + struct.pack("<III", 0x8CFE07FC, 0x8CFE0800, 0x1F94)


def stub_rendumpstring():
    """진단 — 렌더러 진입(0x100076DC, r5=문자열)에서 받은 문자열을 스크래치(0x8CFE0A00,
    96B, 널종료)에 복사. 원본 6워드 재현 후 0x100076E8 복귀. 이게 40자면 렌더러가 40 받는
    것 → 25 캡은 렌더 내부(텍스처 너비/조각수). r0~r3 임시, r4·r5·r8·r15 보존."""
    S = sh4
    body = [
        (0x6153, "mov r5,r1"),           # 0  string src
        (0x2118, "tst r1,r1"),           # 1  널?
        (0x8909, "bt 0x1a"),             # 2  → skip(13)
        (0xD009, None),                  # 3  mov.l scratch,r0
        (0xE230, "mov #48,r2"),          # 4  96B 상한
        # loop(5):
        (0x6311, "mov.w @r1,r3"),        # 5
        (0x2338, "tst r3,r3"),           # 6  널 종료?
        (0x8904, "bt 0x1a"),             # 7  → skip(13)
        (0x2031, "mov.w r3,@r0"),        # 8
        (0x7102, "add #2,r1"),           # 9
        (0x7002, "add #2,r0"),           # 10
        (0x4210, "dt r2"),               # 11
        (0x8BF7, "bf 0xa"),              # 12 → loop(5)
        # skip(13): 원본 6워드 재현
        (0x6843, "mov r4,r8"),           # 13
        (0x6A53, "mov r5,r10"),          # 14
        (0x7FB0, "add #-80,r15"),        # 15
        (0x6EF3, "mov r15,r14"),         # 16
        (0x7FBC, "add #-68,r15"),        # 17
        (0x548E, "mov.l @(56,r8),r4"),   # 18
        (S.rts(), "rts"),                # 19 → 0x100076E8
        (S.nop(), "nop"),                # 20
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[3] = (S.movl_pc(lit_off - ((3 * 2 + 4) & ~3), 0), None)   # scratch
    return S.assemble(body) + struct.pack("<I", 0x8CFE0A00)


def stub_copy_strdump():
    """진단 — copy 훅(0x10003AE6)에서 받은 문자열(r11)을 스크래치(0x8CFE0A00, 128B)에
    복사하고 조각수(@(36,gbr))를 0x8CFE0AFC 에 기록. 원본 6워드(스트라이드 128) 재현.
    문자열 길이(널까지)가 40자면 copy 가 40 받는 것 → 캡은 조각수(vt[24]) 상류."""
    S = sh4
    body = [
        (0x61B3, "mov r11,r1"),          # 0  string src
        (0x2118, "tst r1,r1"),           # 1  r11 널?
        (0x8909, "bt 0x1a"),             # 2  → skip(13)
        (0xD00B, None),                  # 3  mov.l scratch,r0
        (0xE230, "mov #48,r2"),          # 4  48 halfword(96B) 상한
        # loop(5):
        (0x6311, "mov.w @r1,r3"),        # 5
        (0x2338, "tst r3,r3"),           # 6  널 종료?
        (0x8904, "bt 0x1a"),             # 7  → skip(13)
        (0x2031, "mov.w r3,@r0"),        # 8
        (0x7102, "add #2,r1"),           # 9
        (0x7002, "add #2,r0"),           # 10
        (0x4210, "dt r2"),               # 11
        (0x8BF7, "bf 0xa"),              # 12 → loop(5)
        # skip(13): 조각수 로그
        (0xC512, "mov.w @(36,gbr),r0"),  # 13
        (0x600D, "extu.w r0,r0"),        # 14
        (0xD106, None),                  # 15 mov.l cntaddr,r1
        (0x2102, "mov.l r0,@r1"),        # 16
        # 원본 6워드 (스트라이드 128)
        (0x6BA3, "mov r10,r11"),         # 17
        (0x4B08, "shll2 r11"),           # 18
        (0xEC54, "mov #84,r12"),         # 19
        (0x3C8C, "add r8,r12"),          # 20
        (0xE520, "mov #32,r5"),          # 21
        (0x4508, "shll2 r5"),            # 22
        (S.rts(), "rts"),                # 23
        (S.nop(), "nop"),                # 24
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[3] = (S.movl_pc(lit_off - ((3 * 2 + 4) & ~3), 0), None)       # scratch
    body[15] = (S.movl_pc(lit_off + 4 - ((15 * 2 + 4) & ~3), 1), None) # cntaddr
    return S.assemble(body) + struct.pack("<II", 0x8CFE0A00, 0x8CFE0AFC)


def stub_rec_x2(table_bytes):
    """copy 훅(0x10003AE6, 줄 단위) — **토크나이저 노드 리스트**를 걸어 글자별 폭을
    **각 글자 레코드의 x2(rec+8) = width** 로 쓴다. rec = this+84 + 글자*128 + 줄*16
    이므로 x2 = this+92 + 줄*16, 글자마다 +128. 게임의 x2 쓰기(0x10003b12)는 apply 에서
    nop. 원본 6워드 재현. 보존필수 r4(=0)·r13·r9. table 은 mova(pc-상대).

    ★ 왜 raw 문자열(r11)이 아니라 노드 리스트인가 — `&主人公名前&` 같은 토큰은
    렌더러(0x100076DC)가 fontobj+612 의 (치환문,토큰) 표로 **런타임에 펼친다**.
    raw 줄을 파싱하면 토큰 7글자(`&`+한자5+`&`)에 폭을 주고 그 자리엔 이름이 그려져
    폭이 어긋났다(이름 안 공백이 24, 뒤 `．` 실종). 토크나이저는 글자마다
    `fontobj+0x6C` 리스트에 노드(+0 next · +8 code · +12 len)를 append 하고, 치환문
    경로(0x10007a28~)도 같은 리스트에 같은 형식으로 붙이며, 마크업(`@..@` `%..%`)은
    노드를 안 만든다. 리스트는 SetString 진입마다 비워지니 HOOK2 시점엔 **이 줄의
    펼쳐진 글자만** 순서대로 들어 있다. `$N` 숫자 노드는 len 0 → 건너뛴다.

    fontobj 는 절대주소 없이 `*r9` 로 얻는다 — 레코드 빌드 함수가 0x10003918 에서
    r9 = &글꼴전역(0x1001D16C) 로 두고 HOOK2 까지 안 덮는다(정적 확인)."""
    S = sh4
    body = [
        (0x6283, "mov r8,r2"),           # 0  this
        (0xE05C, "mov #92,r0"),          # 1  84+8
        (0x320C, "add r0,r2"),           # 2  this+92
        (0x61A3, "mov r10,r1"),          # 3  줄
        (0x4108, "shll2 r1"),            # 4
        (0x4108, "shll2 r1"),            # 5  줄*16
        (0x321C, "add r1,r2"),           # 6  r2 = rec_0.x2
        (0xC720, None),                  # 7  mova table,r0 (변위는 아래서 채움)
        (0x6303, "mov r0,r3"),           # 8  table base
        (0xC512, "mov.w @(36,gbr),r0"),  # 9  글자수(그려지는 글자)
        (0x600D, "extu.w r0,r0"),        # 10
        (0x6703, "mov r0,r7"),           # 11 count
        (0x6692, "mov.l @r9,r6"),        # 12 r6 = fontobj (*&글꼴전역)
        (0xE06C, "mov #108,r0"),         # 13 0x6C
        (S.movl_r0_rm(6, 6), "mov.l @(r0,r6),r6"),  # 14 r6 = head node
        # loop(15):
        (0x2668, "tst r6,r6"),           # 15
        (None, "bt done"),               # 16 (null → done)
        (S.movl_disp_rm(12, 6, 0), "mov.l @(12,r6),r0"),  # 17 len
        (0x2008, "tst r0,r0"),           # 18
        (None, "bt skip"),               # 19 len 0 → 건너뜀
        (S.movl_disp_rm(8, 6, 0), "mov.l @(8,r6),r0"),    # 20 code
        (0x6503, "mov r0,r5"),           # 21
        (S.extu_b(5, 5), "extu.b r5,r5"),  # 22 trail = code & 0xFF
        (S.shlr8(0), "shlr8 r0"),        # 23
        (0x6103, "mov r0,r1"),           # 24 page = code >> 8
        # lookup(25):
        (0x6013, "mov r1,r0"),           # 25 page
        (0x003C, "mov.b @(r0,r3),r0"),   # 26 페이지맵
        (0x600C, "extu.b r0,r0"),        # 27 pv
        (0x6103, "mov r0,r1"),           # 28
        (0xC880, "tst #128,r0"),         # 29
        (None, "bt subtable"),           # 30
        # direct(31):
        (0x6013, "mov r1,r0"),           # 31
        (0xC97F, "and #127,r0"),         # 32
        (None, "bra store"),             # 33
        (S.nop(), "nop"),                # 34
        # subtable(35):
        (0x6013, "mov r1,r0"),           # 35
        (0x7001, "add #1,r0"),           # 36
        (0x4018, "shll8 r0"),            # 37
        (0x303C, "add r3,r0"),           # 38
        (0x305C, "add r5,r0"),           # 39
        (0x6000, "mov.b @r0,r0"),        # 40
        (0x600C, "extu.b r0,r0"),        # 41
        # store(42): rec.x2 = width ; r2 += 128 ; 다음 노드
        (0x2202, "mov.l r0,@r2"),        # 42
        (0xE120, "mov #32,r1"),          # 43 (★ 글자 스트라이드 320→128)
        (0x4108, "shll2 r1"),            # 44 128
        (0x321C, "add r1,r2"),           # 45
        (0x4710, "dt r7"),               # 46
        (0x6662, "mov.l @r6,r6"),        # 47 next
        (None, "bf loop"),               # 48 count 남으면 계속
        (None, "bra done"),              # 49
        (S.nop(), "nop"),                # 50
        # skip(51): len 0 노드 — count 안 줄이고 다음
        (0x6662, "mov.l @r6,r6"),        # 51
        (None, "bra loop"),              # 52
        (S.nop(), "nop"),                # 53
        # done(54): 원본 6워드
        (0x6BA3, "mov r10,r11"),         # 54
        (0x4B08, "shll2 r11"),           # 55
        (0xEC54, "mov #84,r12"),         # 56
        (0x3C8C, "add r8,r12"),          # 57
        (0xE520, "mov #32,r5"),          # 58 (★ 게임 copy 글자 스트라이드 320→128)
        (0x4508, "shll2 r5"),            # 59 128
        (S.rts(), "rts"),                # 60
        (S.nop(), "nop"),                # 61
    ]
    LOOP, LOOKUP_SUB, STORE, SKIP, DONE = 15, 35, 42, 51, 54
    def rel(i, t):                       # 분기 변위(워드): 목적지 - (분기+2)
        return t - (i + 2)
    body[16] = (S.bt(rel(16, DONE)), None)
    body[19] = (S.bt(rel(19, SKIP)), None)
    body[30] = (S.bt(rel(30, LOOKUP_SUB)), None)
    body[33] = (S.bra(rel(33, STORE)), None)
    body[48] = (S.bf(rel(48, LOOP)), None)
    body[49] = (S.bra(rel(49, DONE)), None)
    body[52] = (S.bra(rel(52, LOOP)), None)
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[7] = (S.mova(lit_off - ((7 * 2 + 4) & ~3)), None)   # mova table
    return S.assemble(body) + table_bytes


def stub_drawchar1():
    """DrawChar #1 래퍼(0x10003582 훅) — rec 완성 후 x2 를 x1+24(풀박스)로 스왑하고
    원래 x2(=width)를 스크래치에 보관한 뒤 jsr DrawChar 재발행. pr 은 스택 보존.

    스크래치는 **DLL 자기 섹션의 쓰기가능 슬롯**(모듈 소유·안전). 두 스텁이 `mova`(PC상대,
    리로케이션 무관)로 공유한다. mova 변위는 페이로드 배치를 아는 apply() 가 채운다.
    반환: (바이트, mova 바이트오프셋)."""
    S = sh4
    body = [
        (0x384C, "add r4,r8"),           # 0  r8 += 글자*320
        (0x382C, "add r2,r8"),           # 1  r8 += 줄*16 → rec 완성
        (0x533D, "mov.l @(52,r3),r3"),   # 2  r3 = vtable[52] = DrawChar
        (0x5082, "mov.l @(8,r8),r0"),    # 3  r0 = rec.x2 (=width)
        (0x6103, "mov r0,r1"),           # 4  r1 = width 보관
        (0xC700, None),                  # 5  ★ mova scratch,r0 (변위 apply 패치)
        (0x2012, "mov.l r1,@r0"),        # 6  *scratch = width
        (0x6082, "mov.l @r8,r0"),        # 7  r0 = rec.x1
        (0x7018, "add #24,r0"),          # 8  x1+24
        (0x1802, "mov.l r0,@(8,r8)"),    # 9  rec.x2 = x1+24 (풀박스)
        (0x6583, "mov r8,r5"),           # 10 r5 = rec
        (0x4F22, "sts.l pr,@-r15"),      # 11 pr 저장
        (0x430B, "jsr @r3"),             # 12 DrawChar
        (0x64D3, "mov r13,r4"),          # 13 (지연슬롯) r4 = r13
        (0x4F26, "lds.l @r15+,pr"),      # 14 pr 복원
        (S.rts(), "rts"),                # 15 → 0x1000358E
        (S.nop(), "nop"),                # 16
    ]
    if len(body) % 2:                    # 4바이트 정렬 (스크래치 슬롯 정렬 유지)
        body.append((S.nop(), "nop"))
    return S.assemble(body), 5 * 2       # mova = body[5] → 오프셋 10


def stub_advance():
    """전진폭 훅(0x100035B4) — rec.x2 를 스크래치(=width)로 복원하고 전진폭 r4=width.
    이어서 원본 자간(@52)·보정(@48)·charIdx++ 재현.  반환: (바이트, mova 바이트오프셋)."""
    S = sh4
    body = [
        (0xC700, None),                  # 0  ★ mova scratch,r0 (변위 apply 패치)
        (0x6002, "mov.l @r0,r0"),        # 1  r0 = tmp(=width)
        (0x1802, "mov.l r0,@(8,r8)"),    # 2  rec.x2 = tmp (복원)
        (0x6403, "mov r0,r4"),           # 3  r4 = width
        # 원본 자간/보정
        (0x7B01, "add #1,r11"),          # 4
        (0x51AD, "mov.l @(52,r10),r1"),  # 5
        (0x341C, "add r1,r4"),           # 6
        (0x52AC, "mov.l @(48,r10),r2"),  # 7
        (0x3428, "sub r2,r4"),           # 8
        (S.rts(), "rts"),                # 9
        (S.nop(), "nop"),                # 10
    ]
    if len(body) % 2:                    # 4바이트 정렬
        body.append((S.nop(), "nop"))
    return S.assemble(body), 0           # mova = body[0] → 오프셋 0


def stub_measure(table_bytes):
    """복사 훅(0x10003A5A) 스텁 — 코드(@r11=글자 문자열 포인터)→페이지맵→배열[r10=charIdx].
    끝에 원본 6워드(gbr=r14 기준 전진폭 누적)를 정확 재실행하고 복귀.

    ★ table 은 이 스텁 바로 뒤(array 리터럴 다음)에 붙이고 **mova(pc-상대)**로
    읽는다 — DLL 이 재배치돼(0x01cf...) 로드되므로 절대 VA(0x10138xxx)를 리터럴로
    넣으면 엉뚱한 주소를 읽어 리부트한다. array(0x8CFE0100)는 물리 하드웨어
    스크래치라 재배치와 무관해 절대값 그대로 써도 된다.

    r10(charIdx)·r11(글자포인터)은 안 건드린다(읽기만). 임시 r0,r1,r2,r3 는 원본
    6워드가 곧 r0,r2,r3 를 재설정하므로 무관. 현재 페이지맵 직접값(0x80|폭)만."""
    # ★ 폭 계산 — inner 진입(0x10003AE6, r8=obj, r10=줄, r11=줄시작, @(36,gbr)=글자수).
    # 버퍼 키 = (폭배열주소 obj+0x1F94+줄*4 >> 2) & 0x3F. draw 의 r9 와 같은 값이라
    # 카운터 없이 정합. 줄 전체를 1/2바이트 파싱해 폭(전각2/반각1)을 버퍼[키*32+글자]에.
    # ★ 폭은 코드→테이블(build_table) 조회: 페이지맵[페이지]가 직접값(0x80|폭)이면
    # 그 폭, 아니면 하위표[번호][trail]. 2바이트=페이지/trail, 1바이트=페이지0/코드.
    # table 은 스텁 뒤(리터럴 다음)에 붙여 mova(pc-상대)로 읽는다(재배치 무관).
    S = sh4
    body = [
        (0x6083, "mov r8,r0"),           # 0  obj
        (0xD125, None),                  # 1  mov.l off,r1   (0x1F94)
        (0x301C, "add r1,r0"),           # 2  obj+0x1F94
        (0x61A3, "mov r10,r1"),          # 3  줄
        (0x4108, "shll2 r1"),            # 4  줄*4
        (0x301C, "add r1,r0"),           # 5  폭배열 주소
        (0x4009, "shlr2 r0"),            # 6  >>2
        (0xC9FF, "and #255,r0"),         # 7  & 0xFF (256슬롯, 키 충돌 감소)
        (0x4008, "shll2 r0"),            # 8
        (0x4008, "shll2 r0"),            # 9
        (0x4000, "shll r0"),             # 10 키*32
        (0xD221, None),                  # 11 mov.l buf,r2   (0x8CFE0100)
        (0x320C, "add r0,r2"),           # 12 버퍼[키]
        (0xC721, None),                  # 13 mova table,r0
        (0x6303, "mov r0,r3"),           # 14 r3 = table base
        (0xC512, "mov.w @(36,gbr),r0"),  # 15 글자수
        (0x600D, "extu.w r0,r0"),        # 16
        (0x6703, "mov r0,r7"),           # 17 남은 글자
        (0x66B3, "mov r11,r6"),          # 18 커서(줄시작)
        # loop(19):
        (0x6060, "mov.b @r6,r0"),        # 19 현재 바이트
        (0x600C, "extu.b r0,r0"),        # 20
        (0xE57F, "mov #127,r5"),         # 21
        (0x7502, "add #2,r5"),           # 22 0x81
        (0x3053, "cmp/ge r5,r0"),        # 23 r0>=0x81 ?
        (0x8B03, "bf 0x3a"),             # 24 → check_e0(29)
        (0xE57F, "mov #127,r5"),         # 25
        (0x7520, "add #32,r5"),          # 26 0x9F
        (0x3503, "cmp/ge r0,r5"),        # 27 0x9F>=r0 ?
        (0x890C, "bt 0x54"),             # 28 → is2(42)
        # check_e0(29):
        (0xE570, "mov #112,r5"),         # 29
        (0x4500, "shll r5"),             # 30 0xE0
        (0x3053, "cmp/ge r5,r0"),        # 31 r0>=0xE0 ?
        (0x8B03, "bf 0x4a"),             # 32 → is1(37)
        (0xE57F, "mov #127,r5"),         # 33
        (0x7570, "add #112,r5"),         # 34 0xEF
        (0x3503, "cmp/ge r0,r5"),        # 35 0xEF>=r0 ?
        (0x8904, "bt 0x54"),             # 36 → is2(42)
        # is1(37): 1바이트 — page=0, trail=코드
        (0x6503, "mov r0,r5"),           # 37 trail = 코드
        (0xE100, "mov #0,r1"),           # 38 page = 0
        (0x7601, "add #1,r6"),           # 39 커서 +1
        (0xA005, "bra 0x5e"),            # 40 → lookup(47)
        (S.nop(), "nop"),                # 41 (지연슬롯)
        # is2(42): 2바이트 — page=첫바이트, trail=둘째
        (0x6103, "mov r0,r1"),           # 42 page
        (0x8461, "mov.b @(1,r6),r0"),    # 43 trail
        (0x600C, "extu.b r0,r0"),        # 44
        (0x6503, "mov r0,r5"),           # 45 trail
        (0x7602, "add #2,r6"),           # 46 커서 +2
        # lookup(47): page=r1, trail=r5, table=r3
        (0x6013, "mov r1,r0"),           # 47 page
        (0x003C, "mov.b @(r0,r3),r0"),   # 48 페이지맵[page]
        (0x600C, "extu.b r0,r0"),        # 49 pv
        (0x6103, "mov r0,r1"),           # 50 pv 보관
        (0xC880, "tst #128,r0"),         # 51 pv&0x80==0 ?
        (0x8903, "bt 0x72"),             # 52 → subtable(57)
        # 직접(53): 폭 = pv & 0x7F
        (0x6013, "mov r1,r0"),           # 53
        (0xC97F, "and #127,r0"),         # 54
        (0xA007, "bra 0x80"),            # 55 → store(64)
        (S.nop(), "nop"),                # 56 (bra 지연슬롯 — r0 폭 보존)
        # subtable(57): 폭 = @(table + (pv+1)*256 + trail)
        (0x6013, "mov r1,r0"),           # 57 pv
        (0x7001, "add #1,r0"),           # 58 pv+1
        (0x4018, "shll8 r0"),            # 59 *256
        (0x303C, "add r3,r0"),           # 60 table +
        (0x305C, "add r5,r0"),           # 61 + trail
        (0x6000, "mov.b @r0,r0"),        # 62 하위표
        (0x600C, "extu.b r0,r0"),        # 63 폭
        # store(64):
        (0x2200, "mov.b r0,@r2"),        # 64 버퍼[글자] = 폭
        (0x7201, "add #1,r2"),           # 65
        (0x4710, "dt r7"),               # 66
        (0x8BCE, "bf 0x26"),             # 67 → loop(19)  (disp -50)
        # ── 원본 6워드 (0x10003AE6~0x10003AF0) 재현 ──
        (0x6BA3, "mov r10,r11"),         # 67
        (0x4B08, "shll2 r11"),           # 68
        (0xEC54, "mov #84,r12"),         # 69
        (0x3C8C, "add r8,r12"),          # 70
        (0xE550, "mov #80,r5"),          # 71
        (0x4508, "shll2 r5"),            # 72
        (S.rts(), "rts"),                # 73
        (S.nop(), "nop"),                # 74
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    table_off = lit_off + 8                                             # off(4)+buf(4) 다음
    body[1] = (S.movl_pc(lit_off - ((1 * 2 + 4) & ~3), 1), None)        # off
    body[11] = (S.movl_pc(lit_off + 4 - ((11 * 2 + 4) & ~3), 2), None)  # buf
    body[13] = (S.mova(table_off - ((13 * 2 + 4) & ~3)), None)          # mova table
    return S.assemble(body) + struct.pack("<II", 0x1F94, 0x8CFE0100) + table_bytes


def stub_draw_codeprobe_line():
    """진단 — draw 훅에서 줄=(r9-obj-0x1F94)>>2 로 글자 인덱스를 역산하고, 코드배열
    *(obj+0x1FF8)[줄] 를 읽어 ring[줄](0x8CFE0800 + 줄*4)에 코드를 기록. 폭은 원본
    (@r9) 유지(정상화면). 널이면 기록 생략. 이 코드가 화면 글자(파E1D3…)와 맞는지,
    엔디안이 맞는지 본다. obj=r10, r9=폭배열주소, r11=조각."""
    S = sh4
    # ring[0]=r9, [1]=r10(obj), [2]=*(obj+0x1FE4), [3]=*(obj+0x1FF8),
    # [4]=*(obj+0x2000), [5]=*(obj+0x2004). 어느 오프셋이 코드배열 ptr 인지 찾는다.
    body = [
        (0xD30F, None),                   # 0  mov.l ring,r3
        (0x2392, "mov.l r9,@r3"),         # 1  [0]=r9
        (0x13A1, "mov.l r10,@(4,r3)"),    # 2  [1]=r10
        (0xD00F, None),                   # 3  mov.l off1FE4,r0
        (0x61A3, "mov r10,r1"),           # 4
        (0x310C, "add r0,r1"),            # 5
        (0x6112, "mov.l @r1,r1"),         # 6
        (0x1312, "mov.l r1,@(8,r3)"),     # 7  [2]=*(obj+0x1FE4)
        (0xD00D, None),                   # 8  mov.l off1FF8,r0
        (0x61A3, "mov r10,r1"),           # 9
        (0x310C, "add r0,r1"),            # 10
        (0x6112, "mov.l @r1,r1"),         # 11
        (0x1313, "mov.l r1,@(12,r3)"),    # 12 [3]=*(obj+0x1FF8)
        (0xD00C, None),                   # 13 mov.l off2000,r0
        (0x61A3, "mov r10,r1"),           # 14
        (0x310C, "add r0,r1"),            # 15
        (0x6112, "mov.l @r1,r1"),         # 16
        (0x1314, "mov.l r1,@(16,r3)"),    # 17 [4]=*(obj+0x2000)
        (0xD00A, None),                   # 18 mov.l off2004,r0
        (0x61A3, "mov r10,r1"),           # 19
        (0x310C, "add r0,r1"),            # 20
        (0x6112, "mov.l @r1,r1"),         # 21
        (0x1315, "mov.l r1,@(20,r3)"),    # 22 [5]=*(obj+0x2004)
        # 원본 6워드
        (0x6492, "mov.l @r9,r4"),         # 23
        (0x7B01, "add #1,r11"),           # 24
        (0x51AD, "mov.l @(52,r10),r1"),   # 25
        (0x341C, "add r1,r4"),            # 26
        (0x52AC, "mov.l @(48,r10),r2"),   # 27
        (0x3428, "sub r2,r4"),            # 28
        (S.rts(), "rts"),                 # 29
        (S.nop(), "nop"),                 # 30
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[0] = (S.movl_pc(lit_off - ((0 * 2 + 4) & ~3), 3), None)        # ring
    body[3] = (S.movl_pc(lit_off + 4 - ((3 * 2 + 4) & ~3), 0), None)    # off1FE4
    body[8] = (S.movl_pc(lit_off + 8 - ((8 * 2 + 4) & ~3), 0), None)    # off1FF8
    body[13] = (S.movl_pc(lit_off + 12 - ((13 * 2 + 4) & ~3), 0), None) # off2000
    body[18] = (S.movl_pc(lit_off + 16 - ((18 * 2 + 4) & ~3), 0), None) # off2004
    return S.assemble(body) + struct.pack("<IIIII", 0x8CFE0800, 0x1FE4, 0x1FF8, 0x2000, 0x2004)


def stub_draw_codewidth(table_bytes):
    """draw 훅(0x100035B4, 글자당) — 전진폭을 **글자 코드로 즉석 계산**한다. 코드는
    obj 자신의 코드배열 *(obj+0x1FF8)[줄] 에서 읽는다(draw 가 살아있는 obj 를 그대로
    읽으므로 화면 글리프와 항상 동기 — 버퍼·copy훅·키 불필요). 줄(=글자 인덱스)은
    draw 자신이 만든 r9 로 역산: 줄 = (r9 - obj - 0x1F94) >> 2. 코드배열 ptr 이 0 이면
    원본 @r9(고정폭)로 안전 폴백. 글리프 크기(0x10003574/a8 의 @r9 읽기)는 건드리지
    않아 상자 24 유지, 전진폭만 좁아진다.

    진입: r8=rec, r9=폭배열주소, r10=obj, r11=charIdx(조각). 임시 r0,r1,r2,r3,r5
    (원본 꼬리가 r1,r2 재설정; r4=결과). table 은 스텁 뒤에 mova 로."""
    S = sh4
    body = [
        (0xC71E, "mova table,r0"),        # 0  table base (disp 재계산)
        (0x6303, "mov r0,r3"),            # 1  r3 = table base
        # 줄 = (r9 - obj - 0x1F94) >> 2
        (0x6093, "mov r9,r0"),            # 2
        (0x30A8, "sub r10,r0"),           # 3  r9-obj
        (0xD117, None),                   # 4  mov.l off1F94,r1
        (0x3018, "sub r1,r0"),            # 5  -0x1F94 = 줄*4
        (0x4009, "shlr2 r0"),             # 6  줄
        # 코드배열 ptr = *(obj + 0x1FF8)
        (0xD117, None),                   # 7  mov.l off1FF8,r1
        (0x62A3, "mov r10,r2"),           # 8
        (0x321C, "add r1,r2"),            # 9  obj+0x1FF8
        (0x6222, "mov.l @r2,r2"),         # 10 코드배열 ptr
        (0x2228, "tst r2,r2"),            # 11 ptr==0 ?
        (0x891D, "bt 0x56"),              # 12 → use_orig(43) 널 폴백
        # code = codearr[줄]  (u16)
        (0x4000, "shll r0"),              # 13 줄*2
        (0x002D, "mov.w @(r0,r2),r0"),    # 14 code
        (0x600D, "extu.w r0,r0"),         # 15
        # page = code>>8 (상위바이트), trail = code&0xFF
        (0x6503, "mov r0,r5"),            # 16 code 보관
        (0x4019, "shlr8 r0"),             # 17 page = 상위바이트
        (0x6103, "mov r0,r1"),            # 18 r1 = page
        (0x6053, "mov r5,r0"),            # 19 code
        (0x600C, "extu.b r0,r0"),         # 20 trail = 하위바이트
        (0x6503, "mov r0,r5"),            # 21 r5 = trail
        # lookup (page=r1, trail=r5, table=r3) → 폭 r0
        (0x6013, "mov r1,r0"),            # 22 page
        (0x003C, "mov.b @(r0,r3),r0"),    # 23 페이지맵[page]
        (0x600C, "extu.b r0,r0"),         # 24 pv
        (0x6103, "mov r0,r1"),            # 25 pv 보관
        (0xC880, "tst #128,r0"),          # 26 pv&0x80==0 ?
        (0x8903, "bt 0x40"),              # 27 → subtable(32)
        # 직접(28): 폭 = pv & 0x7F
        (0x6013, "mov r1,r0"),            # 28
        (0xC97F, "and #127,r0"),          # 29
        (0xA007, "bra 0x4e"),             # 30 → setr4(39)
        (S.nop(), "nop"),                 # 31 (지연슬롯)
        # subtable(32): 폭 = @(table + (pv+1)*256 + trail)
        (0x6013, "mov r1,r0"),            # 32 pv
        (0x7001, "add #1,r0"),            # 33
        (0x4018, "shll8 r0"),             # 34 *256
        (0x303C, "add r3,r0"),            # 35 table+
        (0x305C, "add r5,r0"),            # 36 +trail
        (0x6000, "mov.b @r0,r0"),         # 37
        (0x600C, "extu.b r0,r0"),         # 38 폭
        # setr4(39): r4 = 폭
        (0x6403, "mov r0,r4"),            # 39
        (0xA002, "bra 0x58"),             # 40 → tail(44)
        (S.nop(), "nop"),                 # 41 (지연슬롯)
        (S.nop(), "nop"),                 # 42 (정렬용, use_orig 위치)
        # use_orig(43): 원본 고정폭
        (0x6492, "mov.l @r9,r4"),         # 43 (bt 목적지)
        # tail: 원본 자간/보정
        (0x7B01, "add #1,r11"),           # 44
        (0x51AD, "mov.l @(52,r10),r1"),   # 45
        (0x341C, "add r1,r4"),            # 46
        (0x52AC, "mov.l @(48,r10),r2"),   # 47
        (0x3428, "sub r2,r4"),            # 48
        (S.rts(), "rts"),                 # 49
        (S.nop(), "nop"),                 # 50
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    table_off = lit_off + 8                                             # off1F94(4)+off1FF8(4) 다음
    body[0] = (S.mova(table_off - ((0 * 2 + 4) & ~3)), None)            # mova table
    body[4] = (S.movl_pc(lit_off - ((4 * 2 + 4) & ~3), 1), None)        # off1F94
    body[7] = (S.movl_pc(lit_off + 4 - ((7 * 2 + 4) & ~3), 1), None)    # off1FF8
    return S.assemble(body) + struct.pack("<II", 0x1F94, 0x1FF8) + table_bytes


def stub_width_direct(table_bytes):
    """복사 훅(0x10003AE6, 글자당 1회) — 글자 코드(@r11)→표(build_table)로 전진폭을
    구해 **게임 자신의 폭배열[charIdx] = this+0x1F94+charIdx*4** 에 직접 쓴다. draw 는
    이 배열을 @r9 로 그대로 읽으므로 별도 버퍼·키·draw훅이 필요 없다. 폭배열은 this
    안에 있어 글리프(rec)와 함께 채워지고 지워져 항상 동기된다 — 재사용/오염 무관.

    ★ 게임은 0x10003b3c 에서 폭배열[charIdx]=24 로 덮어쓰므로, 그 store 한 워드를
    apply() 에서 nop 으로 죽인다. vt[84] 호출(부작용)은 남긴다.
    진입: r8=this, r10=charIdx, r11=글자포인터. 보존필수 r4(=0 조각idx)·r13(글리프
    src)·r8·r10·r15. 임시 r0,r1,r2,r3,r5,r6. r11/r12/r5 는 끝의 원본 6워드가 재설정."""
    S = sh4
    body = [
        (0xC71E, "mova table,r0"),        # 0  table base → r0  (disp 재계산)
        (0x6303, "mov r0,r3"),            # 1  r3 = table base
        # 글자 코드 파싱 (@r11)
        (0x60B0, "mov.b @r11,r0"),        # 2  lead
        (0x600C, "extu.b r0,r0"),         # 3
        (0xE57F, "mov #127,r5"),          # 4
        (0x7502, "add #2,r5"),            # 5  0x81
        (0x3053, "cmp/ge r5,r0"),         # 6  r0>=0x81 ?
        (0x8B03, "bf 0x18"),              # 7  → check_e0(12)
        (0xE57F, "mov #127,r5"),          # 8
        (0x7520, "add #32,r5"),           # 9  0x9F
        (0x3503, "cmp/ge r0,r5"),         # 10 0x9F>=r0 ?
        (0x890B, "bt 0x30"),              # 11 → is2(24)
        # check_e0(12):
        (0xE570, "mov #112,r5"),          # 12
        (0x4500, "shll r5"),              # 13 0xE0
        (0x3053, "cmp/ge r5,r0"),         # 14 r0>=0xE0 ?
        (0x8B03, "bf 0x28"),              # 15 → is1(20)
        (0xE57F, "mov #127,r5"),          # 16
        (0x7570, "add #112,r5"),          # 17 0xEF
        (0x3503, "cmp/ge r0,r5"),         # 18 0xEF>=r0 ?
        (0x8903, "bt 0x30"),              # 19 → is2(24)
        # is1(20): 1바이트 page=0 trail=code
        (0x6503, "mov r0,r5"),            # 20 trail=code
        (0xE100, "mov #0,r1"),            # 21 page=0
        (0xA004, "bra 0x38"),             # 22 → lookup(28)
        (S.nop(), "nop"),                 # 23 (지연슬롯)
        # is2(24): 2바이트 page=lead trail=@(1,r11)
        (0x6103, "mov r0,r1"),            # 24 page
        (0x84B1, "mov.b @(1,r11),r0"),    # 25 trail
        (0x600C, "extu.b r0,r0"),         # 26
        (0x6503, "mov r0,r5"),            # 27 trail
        # lookup(28): page=r1 trail=r5 table=r3
        (0x6013, "mov r1,r0"),            # 28 page
        (0x003C, "mov.b @(r0,r3),r0"),    # 29 페이지맵[page]
        (0x600C, "extu.b r0,r0"),         # 30 pv
        (0x6103, "mov r0,r1"),            # 31 pv 보관
        (0xC880, "tst #128,r0"),          # 32 pv&0x80==0 ?
        (0x8903, "bt 0x4c"),              # 33 → subtable(38)
        # 직접(34): 폭 = pv & 0x7F
        (0x6013, "mov r1,r0"),            # 34
        (0xC97F, "and #127,r0"),          # 35
        (0xA007, "bra 0x5a"),             # 36 → store(45)
        (S.nop(), "nop"),                 # 37 (bra 지연슬롯)
        # subtable(38): 폭 = @(table + (pv+1)*256 + trail)
        (0x6013, "mov r1,r0"),            # 38 pv
        (0x7001, "add #1,r0"),            # 39 pv+1
        (0x4018, "shll8 r0"),             # 40 *256
        (0x303C, "add r3,r0"),            # 41 table+
        (0x305C, "add r5,r0"),            # 42 +trail
        (0x6000, "mov.b @r0,r0"),         # 43 하위표
        (0x600C, "extu.b r0,r0"),         # 44 폭
        # store(45): 폭배열[charIdx]=폭 ; 폭배열 = this+0x1F94+charIdx*4
        (0x6383, "mov r8,r3"),            # 45 this
        (0xD103, None),                   # 46 mov.l off1F94,r1
        (0x331C, "add r1,r3"),            # 47 this+0x1F94
        (0x61A3, "mov r10,r1"),           # 48 charIdx
        (0x4108, "shll2 r1"),             # 49 *4
        (0x331C, "add r1,r3"),            # 50 +charIdx*4
        (0x2302, "mov.l r0,@r3"),         # 51 폭배열[charIdx]=폭
        # ── 원본 6워드 (0x10003AE6~0x10003AF0) 재현 ──
        (0x6BA3, "mov r10,r11"),          # 52
        (0x4B08, "shll2 r11"),            # 53
        (0xEC54, "mov #84,r12"),          # 54
        (0x3C8C, "add r8,r12"),           # 55
        (0xE550, "mov #80,r5"),           # 56
        (0x4508, "shll2 r5"),             # 57
        (S.rts(), "rts"),                 # 58
        (S.nop(), "nop"),                 # 59
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    table_off = lit_off + 4                                             # off1F94(4) 다음
    body[0] = (S.mova(table_off - ((0 * 2 + 4) & ~3)), None)            # mova table
    body[46] = (S.movl_pc(lit_off - ((46 * 2 + 4) & ~3), 1), None)      # off1F94
    return S.assemble(body) + struct.pack("<I", 0x1F94) + table_bytes


DIAG_SCRATCH = 0x8CFE0000


def stub_diag():
    """진단 — 스텁이 읽는 (header, node주소, code) 를 SCRATCH[r11] 에 기록하고
    폭은 24 고정(화면 정상). 화면 뒤 라이브로 SCRATCH 를 읽어 스텁 실제 동작을 본다.

        SCRATCH[r11*16] = +0 header(*(obj+0x3C)) · +4 node(header+0x20+r11*16) · +8 code

    node/ code 계산은 stub_code 와 같은 가정을 그대로 쓴다 — 그 가정이 맞는지
    화면 밖에서 검증하는 게 목적이다. SCRATCH 는 P1(0x8C) 라 va↔phys 무관.
    """
    S = sh4

    def store(rm, rn):
        return 0x2002 | (rn << 8) | (rm << 4)

    def store_d(rm, disp, rn):
        return 0x1000 | (rn << 8) | (rm << 4) | (disp // 4)

    # ★ this 구조 덤프판 — this+8/+12 는 288/54(크기값)였다. 진짜 픽셀 버퍼 포인터
    # (0x0C../0x8C.. 주소)를 찾으려 this(r13)의 여러 오프셋을 뜬다. 폭 24 고정.
    #   [0]=this+0 [4]=+4 [8]=+16 [12]=+20 [16]=+24 [20]=+28 [24]=+32 [28]=+36
    # ★ charIdx 별 폭배열 스캔판 — 폭배열[charIdx]=*(obj+0x1F94+charIdx*4) 가 글자마다
    # 채워지는지(값) 아니면 일부 0 인지 본다. obj=r10. 폭 24 고정.
    body = [
        (S.movl_pc(0, 1), None),                          # [0] r1 = SCRATCH
        (S.mov_reg(11, 0), "mov r11,r0"),
        (0xC90F, "and #15,r0"),                            # slot = charIdx & 0xF
        (S.shll(0), "shll r0"), (S.shll(0), "shll r0"),    # slot*4
        (S.add_reg(1, 0), "add r1,r0"),                    # dest = SCRATCH + slot*4
        (S.mov_reg(11, 2), "mov r11,r2"),
        (0x4208, "shll2 r2"),                              # charIdx*4
        (S.movl_pc(0, 3), None),                          # [8] r3 = 0x1F94
        (0x33AC, "add r10,r3"),                            # r3 = obj + 0x1F94
        (0x332C, "add r2,r3"),                             # r3 = obj + 0x1F94 + charIdx*4
        (0x6332, "mov.l @r3,r3"),                          # r3 = 폭배열[charIdx]
        (0x2032, "mov.l r3,@r0"),                          # [slot] = 폭배열[charIdx]
        (S.add_imm(1, 11), "add #1,r11"),
        (S.mov_imm(24, 4), "mov #24,r4"),                  # 폭 24 고정
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[0] = (S.movl_pc(lit_off - ((0 * 2 + 4) & ~3), 1), None)
    body[8] = (S.movl_pc(lit_off + 4 - ((8 * 2 + 4) & ~3), 3), None)
    return S.assemble(body) + struct.pack("<II", DIAG_SCRATCH, 0x1F94)


def hook_code(hook_va, stub_va):
    """훅 １２바이트. `bsrf` 로 스텁까지 상대 분기한다.

    ★ 거리를 **r0** 에 만들어 뛰므로 스텁에 들어갈 때 r0 은 훅 자리의 원본 값이 아니다.
    스텁이 원본 r0(예: 직전 strlen 결과)을 써야 하면 스텁 안에서 다시 구해야 한다
    (tools/gen_savehdr_patch.py 의 HOOK C 가 이걸로 한 번 깨졌다)."""
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


def stub_txout_advance(stub_va, table_va, div_va=HOOK5_DIV):
    """CTRFTextOut 전진폭 훅(0x10009CE2) 스텁 — 2바이트 글자면 폭표(.ktrw 의 기존 표)로
    전진폭을 구하고, 원본대로 r4=폭*@(48,r10)(배율), r5=100 으로 나눗셈 썽크를 불러
    r0 를 돌려준다. 1바이트 글자(r8==12)는 원래 12. 표 주소는 mova 로 얻은 리터럴
    자리에 (표-리터럴) 거리를 더해 만든다 — 절대주소가 없어 재배치가 필요 없다."""
    S = sh4
    body = [
        (0x6283, "mov r8,r2"),            # 0  w = 상자폭(24/12)
        (0xE018, "mov #24,r0"),           # 1
        (0x3800, "cmp/eq r0,r8"),         # 2  2바이트 글자?
        (S.bf(29), None),                 # 3  → one_byte(34)
        (0x61B3, "mov r11,r1"),           # 4
        (0x71FE, "add #-2,r1"),           # 5  r1 = 글자 시작
        (0x6010, "mov.b @r1,r0"),         # 6  lead
        (0x600C, "extu.b r0,r0"),         # 7
        (0x6303, "mov r0,r3"),            # 8  r3 = page
        (0x8411, "mov.b @(1,r1),r0"),     # 9  trail
        (0x600C, "extu.b r0,r0"),         # 10
        (0x6503, "mov r0,r5"),            # 11 r5 = trail
        (0xC700, None),                   # 12 mova LIT,r0 (변위 아래서)
        (0x6102, "mov.l @r0,r1"),         # 13 r1 = 표-LIT 거리
        (0x301C, "add r1,r0"),            # 14 r0 = 표
        (0x6403, "mov r0,r4"),            # 15 r4 = 표
        (0x6033, "mov r3,r0"),            # 16 page
        (0x004C, "mov.b @(r0,r4),r0"),    # 17 페이지맵[page]
        (0x600C, "extu.b r0,r0"),         # 18
        (0x6103, "mov r0,r1"),            # 19 pv
        (0xC880, "tst #128,r0"),          # 20 직접값?
        (S.bt(3), None),                  # 21 → sub(26)
        (0x6013, "mov r1,r0"),            # 22
        (0xC97F, "and #127,r0"),          # 23 폭 = pv&0x7F
        (S.bra(7), None),                 # 24 → got(33)
        (S.nop(), "nop"),                 # 25
        (0x6013, "mov r1,r0"),            # 26 sub: pv
        (0x7001, "add #1,r0"),            # 27
        (0x4018, "shll8 r0"),             # 28 *256
        (0x304C, "add r4,r0"),            # 29 +표
        (0x305C, "add r5,r0"),            # 30 +trail
        (0x6000, "mov.b @r0,r0"),         # 31
        (0x600C, "extu.b r0,r0"),         # 32 폭
        (0x6203, "mov r0,r2"),            # 33 got: w = 폭
        (0x51AC, "mov.l @(48,r10),r1"),   # 34 one_byte: 배율
        (0x0217, "mul.l r1,r2"),          # 35 macl = w*배율
        (0xE564, "mov #100,r5"),          # 36
        (S.sts_pr_push(), None),          # 37 pr 보존(훅 복귀주소)
        (0xB000, None),                   # 38 bsr 썽크 (변위 아래서)
        (0x041A, "sts macl,r4"),          # 39 (지연슬롯) r4 = w*배율
        (S.lds_pr_pop(), None),           # 40
        (S.rts(), "rts"),                 # 41
        (S.nop(), "nop"),                 # 42
        (S.nop(), "nop"),                 # 43 (4바이트 정렬)
    ]
    lit_off = len(body) * 2
    assert lit_off % 4 == 0, lit_off
    body[12] = (S.mova(lit_off - ((12 * 2 + 4) & ~3)), None)
    bsr_pc = stub_va + 38 * 2 + 4
    d = (div_va - bsr_pc) // 2
    if not -2048 <= d <= 2047 or (div_va - bsr_pc) % 2:
        raise ValueError(f"bsr 거리 {div_va - bsr_pc:#x} 가 ±4KB 밖 (스텁 {stub_va:#x})")
    body[38] = (S.bsr(d), None)
    code = S.assemble(body, stub_va)
    # 되읽기: bsr 목적지·mova 리터럴 자리 검증
    got = [a for a, t in S.disasm([w for w, _ in body], stub_va) if t.startswith("bsr")]
    if len(got) != 1:
        raise ValueError("bsr 이 하나가 아니다")
    return code + struct.pack("<i", table_va - (stub_va + lit_off))


SECTION = ".ktrw"
CHARS = 0xE0000020            # CODE | EXECUTE | READ | WRITE (스텁이 폭 스크래치 4B 를 쓴다)


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


def stub_draw_codeprobe():
    """진단 — draw 훅에서 글자 코드를 obj 자신의 코드배열 *(obj+0x1FE4) 에서 r11(줄내
    charIdx)로 읽어 (r9주소, code)를 링에 기록. 폭은 원본 유지(정상화면). 이 코드가
    화면의 실제 글자(파일을…)와 맞으면 draw 가 살아있는 obj 에서 직접 폭을 계산할 수
    있다는 뜻(버퍼/copy 훅 불필요). obj=r10, r11=줄내 charIdx."""
    S = sh4
    body = [
        (0xD30E, None),                  # 0  mov.l off1FF8,r0
        (0x61A3, "mov r10,r1"),          # 1  obj
        (0x310C, "add r0,r1"),           # 2  obj+0x1FE4
        (0x6112, "mov.l @r1,r1"),        # 3  코드배열 ptr
        (0x60B3, "mov r11,r0"),          # 4  charIdx
        (0x4000, "shll r0"),             # 5  *2
        (0x021D, "mov.w @(r0,r1),r2"),   # 6  code
        (0x622D, "extu.w r2,r2"),        # 7
        # 링 기록 [r9][code]
        (0xD30A, None),                  # 8  mov.l cnt_addr,r3
        (0x6032, "mov.l @r3,r0"),        # 9
        (0x6103, "mov r0,r1"),           # 10
        (0x7001, "add #1,r0"),           # 11
        (0x2302, "mov.l r0,@r3"),        # 12 cnt++
        (0x6013, "mov r1,r0"),           # 13
        (0xC97F, "and #127,r0"),         # 14
        (0x4008, "shll2 r0"),            # 15
        (0x4000, "shll r0"),             # 16 *8
        (0xD306, None),                  # 17 mov.l ring_addr,r3
        (0x330C, "add r0,r3"),           # 18 슬롯
        (0x2392, "mov.l r9,@r3"),        # 19 +0 = r9
        (0x1321, "mov.l r2,@(4,r3)"),    # 20 +4 = code
        # ── 원본 6워드 ──
        (0x6492, "mov.l @r9,r4"),        # 21
        (0x7B01, "add #1,r11"),          # 22
        (0x51AD, "mov.l @(52,r10),r1"),  # 23
        (0x341C, "add r1,r4"),           # 24
        (0x52AC, "mov.l @(48,r10),r2"),  # 25
        (0x3428, "sub r2,r4"),           # 26
        (S.rts(), "rts"),                # 27
        (S.nop(), "nop"),                # 28
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[0] = (S.movl_pc(lit_off - ((0 * 2 + 4) & ~3), 0), None)       # off1FE4
    body[8] = (S.movl_pc(lit_off + 4 - ((8 * 2 + 4) & ~3), 3), None)   # cnt_addr
    body[17] = (S.movl_pc(lit_off + 8 - ((17 * 2 + 4) & ~3), 3), None) # ring_addr
    return S.assemble(body) + struct.pack("<III", 0x1FF8, 0x8CFE07FC, 0x8CFE0800)


def stub_draw_linetrace():
    """진단 — draw 훅에서 줄 시작(r11==0)마다 (r9주소, 0xFFFFFFFF마커)를 copy 와 같은
    링(cnt 0x8CFE07FC, base 0x8CFE0800)에 기록. 폭은 원본(@r9 고정 24) 유지 →
    화면 정상. copy 는 [addr, code], draw 는 [addr, 0xFFFFFFFF] 라 링 순서를 보면
    copy/draw 가 문자열마다 번갈아(C0 C1 C2 D0 D1 D2 …) 도는지 아니면 몰아서
    (C0…C15 D0…D15) 도는지 판별된다. r9=폭배열주소, r11=charIdx."""
    S = sh4
    body = [
        (0x60B3, "mov r11,r0"),          # 0  charIdx
        (0x2008, "tst r0,r0"),           # 1  r11==0 ?
        (0x8B0D, "bf 0x22"),             # 2  아니면 로깅 건너뜀 → skip(17)
        (0xD30C, None),                  # 3  mov.l cnt_addr,r3
        (0x6032, "mov.l @r3,r0"),        # 4  cnt
        (0x6203, "mov r0,r2"),           # 5  save
        (0x7001, "add #1,r0"),           # 6
        (0x2302, "mov.l r0,@r3"),        # 7  cnt++
        (0x6023, "mov r2,r0"),           # 8
        (0xC97F, "and #127,r0"),         # 9
        (0x4008, "shll2 r0"),            # 10
        (0x4000, "shll r0"),             # 11 *8
        (0xD308, None),                  # 12 mov.l ring_addr,r3
        (0x330C, "add r0,r3"),           # 13 슬롯
        (0x2392, "mov.l r9,@r3"),        # 14 슬롯+0 = r9(addr)
        (0xE0FF, "mov #-1,r0"),          # 15 0xFFFFFFFF 마커
        (0x1301, "mov.l r0,@(4,r3)"),    # 16 슬롯+4 = 마커
        # skip(17): ── 원본 6워드 (폭 @r9 고정) ──
        (0x6492, "mov.l @r9,r4"),        # 17
        (0x7B01, "add #1,r11"),          # 18
        (0x51AD, "mov.l @(52,r10),r1"),  # 19
        (0x341C, "add r1,r4"),           # 20
        (0x52AC, "mov.l @(48,r10),r2"),  # 21
        (0x3428, "sub r2,r4"),           # 22
        (S.rts(), "rts"),                # 23
        (S.nop(), "nop"),                # 24
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[3] = (S.movl_pc(lit_off - ((3 * 2 + 4) & ~3), 3), None)      # cnt_addr
    body[12] = (S.movl_pc(lit_off + 4 - ((12 * 2 + 4) & ~3), 3), None) # ring_addr
    return S.assemble(body) + struct.pack("<II", 0x8CFE07FC, 0x8CFE0800)


def apply(cfg, blob):
    """(새 DLL 바이트, 설명). 섹션을 붙이고 표를 싣고 훅을 건다."""
    from kitae.build import advance, pesection

    raw, lo = advance._text(blob)

    if cfg.get("font_variable") == "binpoc":
        # ★ 그냥 바이너리 직접 패치 (트램폴린 없이 2워드). 복사 루프 0x100038D0 에서
        # dst 레코드 x2 를 x1+11(폭 12)로 강제. r3=x1 은 0x10003B0C 직전에 이미 있다.
        #   0x10003B0E: mov.l @(8,r7),r1 (0x5172) → add #11,r3      (0x730B)
        #   0x10003B12: mov.l r1,@(8,r2) (0x1212) → mov.l r3,@(8,r2) (0x1232)
        for va, orig in ((0x100035B4, 0x6492),):
            got = struct.unpack_from("<H", blob, raw + (va - lo))[0]
            if got != orig:
                raise ValueError(f"{va:#x} = {got:#06x}, expected {orig:#06x}")
        out = bytearray(blob)
        # ★ 유저 통찰판 — 레코드 x2(목적지)는 24 그대로 두어 stretch 를 없앤다.
        # 전진폭만 12 로 좁힌다(그리기 루프 0x100035B4 mov.l @r9,r4 → mov #12,r4).
        # 글리프는 24 상자에 왜곡 없이 그려지되 다음 글자가 12 겹쳐 들어온다. 폰트를
        # 좌측정렬+실측폭으로 만들면 겹침이 여백이라 무해해진다.
        struct.pack_into("<H", out, raw + (0x100035B4 - lo), 0xE40C)   # mov #12,r4 (전진폭)
        return bytes(out), "가변폭 POC: 목적지 24 유지 + 전진폭 12 (stretch 없음, 겹침)"

    if cfg.get("font_variable") == "wire":
        # ★ 배선 검증 (b) — 전진폭을 rec+16(여유필드)에서 읽는다. 그리기 루프
        # 0x100035B4 mov.l @r9,r4 → mov.l @(16,r8),r4. 인라인이라 무한루프 없음.
        # rec+16 은 아직 0 이라 전진 ~0(글자 겹침)이지만, 라이브 poke 로 흔들어
        # 전진이 rec+16 을 따라오는지 확인한다. 되면 복사 루프서 rec+16=width 채운다.
        if struct.unpack_from("<H", blob, raw + (0x100035B4 - lo))[0] != 0x6492:
            raise ValueError("0x100035B4 != 0x6492")
        out = bytearray(blob)
        struct.pack_into("<H", out, raw + (0x100035B4 - lo), 0x5484)   # mov.l @(16,r8),r4
        return bytes(out), "배선검증(b): 전진폭 = rec+16 (그리기 인라인)"

    for i, want in enumerate(HOOK_ORIG):
        got = struct.unpack_from("<H", blob, raw + (HOOK - lo) + i * 2)[0]
        if got != want:
            raise ValueError(
                f"{HOOK + i * 2:#x} 워드가 {got:#06x} — {want:#06x} 를 기대했다. "
                "다른 빌드이거나 이미 패치된 파일이다")

    mode = cfg.get("font_variable")
    flat = mode in ("flat", "len")
    if isinstance(mode, str) and mode.startswith("rec8:"):
        code, _ = stub_rec8(int(mode[5:]))
        table, npages = table_ruler(0)
    elif mode == "chain40":
        code, _ = stub_chain()
        table, npages = build_table(cfg, probe=40)
    elif mode == "cp40":
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
    if isinstance(mode, str) and mode.startswith("rec8:"):
        code, _ = stub_rec8(int(mode[5:]))
        table, npages = table_ruler(0)
    elif mode == "chain40":
        code, _ = stub_chain()
        table, npages = build_table(cfg, probe=40)
    elif mode == "cp40":
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
    elif mode == "diag":
        code, table, npages = stub_diag(), b"", 0
    elif flat:
        code, table, npages = stub_flat(), b"", 0
    else:
        code = stub_draw_orig()               # (진단) draw: 버퍼[키*32+charIdx]
        table, npages = build_table(cfg)

    # ★★ 정식 방식 (mode is True) — rec.x2 에 글자별 폭을 실어 그린다 (3 훅):
    #   copy(HOOK2 0x10003AE6): rec.x2 = width  (게임의 x2 쓰기 0x10003b12 nop)
    #   DrawChar 래퍼(HOOK3 0x10003582): x2 를 x1+24 풀박스로 스왑 후 jsr DrawChar
    #   전진폭(HOOK 0x100035b4): rec.x2 복원 후 전진폭 = width
    # rec 는 obj 안 글리프와 함께 살아 동기 — 버퍼·카운트·재사용 desync 전부 없음.
    if mode is True:
        table, npages = build_table(cfg)
        s_adv, adv_mova = stub_advance()
        s_dc1, dc1_mova = stub_drawchar1()
        s_cpy = stub_rec_x2(table)
        # 폭 스크래치 4B 를 s_dc1 뒤(두 mova 앞)에 4정렬로 끼운다 → 물리 RAM 대신 모듈 메모리.
        base = len(s_adv) + len(s_dc1)
        scratch_off = (base + 3) & ~3
        payload = s_adv + s_dc1 + b"\0" * (scratch_off - base) + b"\0\0\0\0" + s_cpy
        out, foff, _fsize = pesection.add(blob, SECTION, len(payload), CHARS)
        va = _section_va(out, SECTION)
        va_adv, va_dc1, va_cpy = va, va + len(s_adv), va + scratch_off + 4
        out = bytearray(out)
        out[foff:foff + len(payload)] = payload
        # mova @(disp,pc),r0 변위 채우기: target=scratch_off. disp=(scratch_off-((off&~3)+4))//4
        for moff in (adv_mova, len(s_adv) + dc1_mova):
            disp = (scratch_off - ((moff & ~3) + 4)) // 4
            if not 0 <= disp <= 255:
                raise ValueError(f"mova 변위 {disp} 범위밖 (moff={moff}, scratch={scratch_off})")
            out[foff + moff] = disp       # 0xC7dd 저바이트
        for hookva, horig in ((HOOK, HOOK_ORIG), (HOOK3, HOOK3_ORIG), (HOOK2, HOOK2_ORIG)):
            for i, want in enumerate(horig):
                got = struct.unpack_from("<H", blob, raw + (hookva - lo) + i * 2)[0]
                if got != want:
                    raise ValueError(f"{hookva + i*2:#x} = {got:#06x}, {want:#06x} 기대")
        t_va, t_off = _cave(out, raw, lo)
        tl = len(trampoline(t_va, va_adv))
        for k, (hookva, hlen, stubva) in enumerate((
                (HOOK, HOOK_LEN, va_adv), (HOOK3, HOOK3_LEN, va_dc1), (HOOK2, HOOK2_LEN, va_cpy))):
            tva, toff = t_va + k * tl, t_off + k * tl
            tr = trampoline(tva, stubva)
            if any(out[toff:toff + len(tr)]):
                raise ValueError(f"케이브 {tva:#x} 가 비어 있지 않다")
            out[toff:toff + len(tr)] = tr
            _grow_virtual(out, ".text", (tva - lo) + len(tr))
            out[raw + (hookva - lo): raw + (hookva - lo) + hlen] = hook_code(hookva, tva)
        # ★ CTRFTextOut 전진폭 훅(HOOK5) — 스텁은 징검다리 3개 바로 뒤 케이브에.
        txout_note = ""
        if cfg.get("vw_txout", True):
            for i, want in enumerate(HOOK5_ORIG):
                got = struct.unpack_from("<H", blob, raw + (HOOK5 - lo) + i * 2)[0]
                if got != want:
                    raise ValueError(f"{HOOK5 + i*2:#x} = {got:#06x}, {want:#06x} 기대")
            table_va = va_cpy + (len(s_cpy) - len(table))
            s5_va, s5_off = t_va + 3 * tl, t_off + 3 * tl
            assert s5_va % 4 == 0, hex(s5_va)
            s5 = stub_txout_advance(s5_va, table_va)
            if any(out[s5_off:s5_off + len(s5)]):
                raise ValueError(f"케이브 {s5_va:#x} 가 비어 있지 않다")
            out[s5_off:s5_off + len(s5)] = s5
            _grow_virtual(out, ".text", (s5_va - lo) + len(s5))
            out[raw + (HOOK5 - lo): raw + (HOOK5 - lo) + HOOK5_LEN] = hook_code(HOOK5, s5_va)
            txout_note = f" · TXOut 훅 {HOOK5:#x}→{s5_va:#x}({len(s5)}B, 표 {table_va:#x})"
        # 게임의 rec.x2 쓰기 (0x10003b12 mov.l r1,@(8,r2) = 0x1212) → nop
        if struct.unpack_from("<H", blob, raw + (0x10003B12 - lo))[0] != 0x1212:
            raise ValueError("0x10003b12 != 0x1212")
        struct.pack_into("<H", out, raw + (0x10003B12 - lo), 0x0009)
        # ★ 글자 스트라이드 320→128 (레코드 격자 25글자→62글자, 줄 20→8).
        #   draw 프롤로그 0x10003542 mov #80,r1 (=0xE150) → mov #32,r1 (=0xE120).
        #   copy 쪽은 stub_rec_x2 안에서 이미 mov #32 로 재현. 최대 3줄이라 8줄 여유 안전.
        if struct.unpack_from("<H", blob, raw + (0x10003542 - lo))[0] != 0xE150:
            raise ValueError("0x10003542 != 0xE150")
        struct.pack_into("<H", out, raw + (0x10003542 - lo), 0xE120)
        # ★ >25자 확장 전용 크기 패치 (접은 실험). redream 이 25칸 배열 오버플로로
        #   죽는 원인 후보라 vw_extension=false 면 걸지 않는다. 핵심 프로포셔널(≤25/줄)은
        #   이것 없이 동작. cfg 로 껐을 때 원본 25 클램프·원본 버퍼 alloc 그대로 나간다.
        if cfg.get("vw_extension", True):
            # 렌더러 조각수 클램프 min(cnt,25) → min(cnt,62). 0x10007c32 mov #25,r3
            #   (0xE319), 0x10007c38 mov #25,r2 (0xE219) → #62 (0xE33E / 0xE23E).
            for cva, orig, new in ((0x10007C32, 0xE319, 0xE33E), (0x10007C38, 0xE219, 0xE23E)):
                if struct.unpack_from("<H", blob, raw + (cva - lo))[0] != orig:
                    raise ValueError(f"{cva:#x} != {orig:#06x}")
                struct.pack_into("<H", out, raw + (cva - lo), new)
            # 글리프 버퍼 크기 alloc(@(40,r8)+1) → +64 (조각수 62 여유). 0x10007766
            #   add #1,r4 (0x7401) → add #64,r4 (0x7440).
            if struct.unpack_from("<H", blob, raw + (0x10007766 - lo))[0] != 0x7401:
                raise ValueError("0x10007766 != 0x7401")
            struct.pack_into("<H", out, raw + (0x10007766 - lo), 0x7440)
        ext = "확장" if cfg.get("vw_extension", True) else "핵심만(≤25)"
        note = (f"가변폭(rec.x2·{ext}): adv{len(s_adv)}+dc1{len(s_dc1)}+cpy{len(s_cpy)}B "
                f"표{len(table)}B({npages}p) @ {va:#x} · 훅 {HOOK:#x}/{HOOK3:#x}/{HOOK2:#x}"
                f"→{t_va:#x} · 0x10003b12 nop{txout_note}")
        return bytes(out), note

    # (mode is not True: 단일 draw 훅 진단 경로)
    payload = code + table
    out, foff, _fsize = pesection.add(blob, SECTION, len(payload), CHARS)
    va = _section_va(out, SECTION)
    out = bytearray(out)
    out[foff:foff + len(payload)] = payload
    tramp_va, tramp_off = _cave(out, raw, lo)
    tramp = trampoline(tramp_va, va)
    if any(out[tramp_off:tramp_off + len(tramp)]):
        raise ValueError(f"케이브 {tramp_va:#x} 가 비어 있지 않다")
    out[tramp_off:tramp_off + len(tramp)] = tramp
    _grow_virtual(out, ".text", (tramp_va - lo) + len(tramp))
    out[raw + (HOOK - lo): raw + (HOOK - lo) + HOOK_LEN] = hook_code(HOOK, tramp_va)
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
