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
HOOK8 = 0x100035A6            # 본체 DrawChar 호출(vw_menu) — HOOK3 징검다리로 같은 스텁에 간다
HOOK8_ORIG = (0x64D3, 0x6692, 0x6583, 0x63D2, 0x533D, 0x430B)
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
    **각 글자 레코드의 x2(rec+8) = width | len<<16** 로 쓴다(len = 반각 1·전각 2, 그리기
    래퍼가 글리프 상자 12/24 를 고르는 단서 — stub_drawchar1 참고). rec = this+84 + 글자*128 + 줄*16
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

    ★ fontobj 는 **전역 글꼴(`*r9`)** 이 맞다 — 2026-09-20 에 `this+12` 로 바꿨다가 안내문이
    완전히 깨졌다(전역이 아닌 CTRFSquareStr 의 엉뚱한 리스트로 폭·len 을 매김). SetText 의
    토크나이즈는 0x1000394e 에서 전역의 QI 인터페이스(ITRFStrTimingImport)에 문자열을 넘기는
    쪽이고, 0x100039aa 의 `@(12,r8)->vt[12]()` 는 인자 없는 다른 호출이다. this+12 는 SetText 의
    인자 객체(0x1000ae8c 로 AddRef 대입)라 글꼴이 아니다. 선택 상자(CTRFMsgput)가 24px 균일로
    나오는 문제는 별도 — 자기검증(후보 리스트 첫 노드 코드 == 줄 첫 글자) 없이는 건드리지 말 것.
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
        (0x6692, "mov.l @r9,r6"),           # 12 r6 = fontobj (*&글꼴전역) — ★ this+12 아님(아래 주석)
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
        # store(42): rec.x2 = width | len<<16 ; r2 += 128 ; 다음 노드
        # ★ len(반각 1·전각 2)을 상위에 같이 싣는다 — DrawChar 래퍼가 글리프 상자를
        #   12/24 로 고르는 유일한 단서다(아래 stub_drawchar1 주석).
        (S.movl_disp_rm(12, 6, 1), "mov.l @(12,r6),r1"),  # 42 len
        (S.shll16(1), "shll16 r1"),      # 43
        (S.or_reg(1, 0), "or r1,r0"),    # 44 r0 = width | len<<16
        (0x2202, "mov.l r0,@r2"),        # 45
        (0xE120, "mov #32,r1"),          # 46 (★ 글자 스트라이드 320→128)
        (0x4108, "shll2 r1"),            # 47 128
        (0x321C, "add r1,r2"),           # 48
        (0x4710, "dt r7"),               # 49
        (0x6662, "mov.l @r6,r6"),        # 50 next
        (None, "bf loop"),               # 51 count 남으면 계속
        (None, "bra done"),              # 52
        (S.nop(), "nop"),                # 53
        # skip(54): len 0 노드 — count 안 줄이고 다음
        (0x6662, "mov.l @r6,r6"),        # 54
        (None, "bra loop"),              # 55
        (S.nop(), "nop"),                # 56
        # done(57): 원본 6워드
        (0x6BA3, "mov r10,r11"),         # 54
        (0x4B08, "shll2 r11"),           # 55
        (0xEC54, "mov #84,r12"),         # 56
        (0x3C8C, "add r8,r12"),          # 57
        (0xE520, "mov #32,r5"),          # 58 (★ 게임 copy 글자 스트라이드 320→128)
        (0x4508, "shll2 r5"),            # 59 128
        (S.rts(), "rts"),                # 60
        (S.nop(), "nop"),                # 61
    ]
    LOOP, LOOKUP_SUB, STORE, SKIP, DONE = 15, 35, 42, 54, 57
    def rel(i, t):                       # 분기 변위(워드): 목적지 - (분기+2)
        return t - (i + 2)
    body[16] = (S.bt(rel(16, DONE)), None)
    body[19] = (S.bt(rel(19, SKIP)), None)
    body[30] = (S.bt(rel(30, LOOKUP_SUB)), None)
    body[33] = (S.bra(rel(33, STORE)), None)
    body[51] = (S.bf(rel(51, LOOP)), None)
    body[52] = (S.bra(rel(52, DONE)), None)
    body[55] = (S.bra(rel(55, LOOP)), None)
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    body[7] = (S.mova(lit_off - ((7 * 2 + 4) & ~3)), None)   # mova table
    return S.assemble(body) + table_bytes


def stub_drawchar1(box_width=False):
    """DrawChar #1 래퍼(0x10003582 훅) — rec 완성 후 x2 를 글리프 상자(x1+11·x1+23, 끝 포함)로
    스왑하고 원래 x2(=width)를 스크래치에 보관한 뒤 jsr DrawChar 재발행. pr 은 스택 보존.

    ★★ 상자는 **반각 12 · 전각 24** 다 — 무조건 24 가 아니다 (2026-09-19).
    레코드 4칸은 글리프 아틀라스의 소스 사각형(x1,y1,x2,y2)이고, 엔진이 그걸 채우는
    자리(0x10007d40~0x10007d84)는 `len==1` 이면 **셀폭을 절반으로 줄여**
    (`shar` → 12) `x2 = x1 + 12 - 1` 로 쓴다. 아틀라스 칸 피치는 반각도 24 라서 오른쪽
    절반은 비어 있다. 그러니 반각에 x1+24 를 주면 **빈칸(또는 이전 문자열의 찌꺼기)
    12px 이 글자 뒤에 함께 그려지고**, 전진폭은 표대로 12 라 다음 글자가 그 위에 겹친다.
    한글 본문은 전부 2바이트 셀이라 안 드러났고, `itoa` 로 만든 숫자(퀴즈 `-제2문-`)와
    raw ASCII(순위표 `1위`)처럼 **런타임 1바이트 글자**에서만 터졌다.

    단서는 stub_rec_x2 가 rec.x2 상위 16비트에 실어 준 len(1/2)뿐이다 — 이 시점엔
    엔진의 원래 x2 가 이미 덮여 있다. 상자 = 12*len, 폭 = 하위 8비트.

    스크래치는 **DLL 자기 섹션의 쓰기가능 슬롯**(모듈 소유·안전). 두 스텁이 `mova`(PC상대,
    리로케이션 무관)로 공유한다. mova 변위는 페이로드 배치를 아는 apply() 가 채운다.
    반환: (바이트, mova 바이트오프셋).

    `box_width`(vw_menu, 2026-09-21): 아틀라스를 폭대로 촘촘히 굽는 HOOK7 과 짝 — 상자 = **폭 − 1**
    (하위 8비트). 촘촘한 아틀라스에선 x1+23 상자가 다음 글자 칸을 물고 오므로 타자 연출 중
    다음 글자의 왼쪽 조각이 먼저 보인다. 폭 상자면 정확히 자기 글리프만 그린다."""
    S = sh4
    if box_width:
        # ★ vw_menu 판(2026-09-21): 두 DrawChar 호출(그림자 0x1000358a · 본체 0x100035b0)을 **한 스텁**이 받는다
        #   (본체 쪽 HOOK8 은 HOOK3 의 징검다리로 뛴다). 어느 쪽인지는 PR 하위 16비트(0x358E / 0x35B2)로 가른다 —
        #   모듈 베이스가 64KB 정렬이라 재배치와 무관. 그림자: rec 완성·x2 스왑(폭−1)·스크래치 보관;
        #   본체: 스크래치의 폭만 꺼낸다. 둘 다 **r6 = 폭**(그리기 폭)·r7 = 줄 크기(높이)로 DrawChar 를 부른다.
        #   엔진은 r6=r7=줄 크기(24)를 넘겨 사각형을 24 로 늘려 그렸는데, 원본 대사는 전각뿐이라 드러나지 않았고
        #   폭 상자(16·8)에선 로마자·마침표가 가로로 늘어나 깨졌다(9/21 캡처). TextOut vt[4]/HOOK5 는 원래
        #   r6 에 글자 폭(24/12·표 폭)을 준다 — 같은 규약.
        body = [
            (0xC700, None),                  # 0  ★ mova scratch,r0 (변위 apply 패치)
            (0x6303, "mov r0,r3"),           # 1  r3 = 스크래치
            (0x012A, "sts pr,r1"),           # 2  복귀주소
            (0x611D, "extu.w r1,r1"),        # 3  하위 16비트
            (0x901A, None),                  # 4  mov.w LIT,r0 (= HOOK8 복귀 0x35B2)
            (0x3100, "cmp/eq r0,r1"),        # 5
            (S.bt(12), None),                # 6  → SITE2(20)
            (0x384C, "add r4,r8"),           # 7  r8 += 글자*128
            (0x382C, "add r2,r8"),           # 8  r8 += 줄*16 → rec 완성
            (0x5082, "mov.l @(8,r8),r0"),    # 9  rec.x2 = width | len<<16
            (0x2302, "mov.l r0,@r3"),        # 10 *scratch (len 포함 — 전진폭 훅이 되돌린다)
            (0x6503, "mov r0,r5"),           # 11
            (0x655C, "extu.b r5,r5"),        # 12 r5 = 폭
            (0x6653, "mov r5,r6"),           # 13 r6 = 폭 = 그리기 폭
            (0x75FF, "add #-1,r5"),          # 14 상자 = 폭 − 1 (끝 포함)
            (0x6082, "mov.l @r8,r0"),        # 15 rec.x1
            (0x305C, "add r5,r0"),           # 16
            (0x1802, "mov.l r0,@(8,r8)"),    # 17 rec.x2 = x1 + 폭 − 1
            (S.bra(3), None),                # 18 → CALL(23)
            (0x6792, "mov.l @r9,r7"),        # 19 (지연) r7 = 줄 크기
            (0x6632, "mov.l @r3,r6"),        # 20 SITE2: 스크래치
            (0x666C, "extu.b r6,r6"),        # 21 r6 = 폭
            (0x6792, "mov.l @r9,r7"),        # 22 r7 = 줄 크기
            (0x63D2, "mov.l @r13,r3"),       # 23 CALL: vtable
            (0x533D, "mov.l @(52,r3),r3"),   # 24 vt[13] = DrawChar
            (0x6583, "mov r8,r5"),           # 25 r5 = rec
            (0x4F22, "sts.l pr,@-r15"),      # 26
            (0x430B, "jsr @r3"),             # 27
            (0x64D3, "mov r13,r4"),          # 28 (지연) this
            (0x4F26, "lds.l @r15+,pr"),      # 29
            (S.rts(), "rts"),                # 30 → 0x1000358E / 0x100035B2
            (S.nop(), "nop"),                # 31
        ]
        lit_off = len(body) * 2              # 64: mov.w 변위 = (64 − ((4*2+4)&~3)) / 2 = 26 → 0x901A
        assert (lit_off - ((4 * 2 + 4) & ~3)) // 2 == 0x1A and lit_off % 4 == 0, lit_off
        code = S.assemble(body)
        got = dict(S.disasm([w for w, _ in body]))
        assert got[6 * 2].endswith(hex(20 * 2)) and got[18 * 2].endswith(hex(23 * 2)), got
        return code + struct.pack("<HH", (HOOK8 + HOOK3_LEN) & 0xFFFF, 0x0009), 0    # LIT16 + nop(정렬)
    body = [
        (0x384C, "add r4,r8"),           # 0  r8 += 글자*320
        (0x382C, "add r2,r8"),           # 1  r8 += 줄*16 → rec 완성
        (0x533D, "mov.l @(52,r3),r3"),   # 2  r3 = vtable[52] = DrawChar
        (0x5082, "mov.l @(8,r8),r0"),    # 3  r0 = rec.x2 (= width | len<<16)
        (S.mov_reg(0, 5), "mov r0,r5"),  # 4  r5 = 실린 값(len 꺼내려고 보관)
        (0x6103, "mov r0,r1"),           # 5  r1 = 실린 값
        (0xC700, None),                  # 6  ★ mova scratch,r0 (변위 apply 패치)
        (0x2012, "mov.l r1,@r0"),        # 7  *scratch = 실린 값 — ★ width 만 넣으면
                                         #    전진폭 훅이 len 없는 값을 되돌려 **다음
                                         #    프레임에 상자폭이 0** 이 된다(글자 실종).
        (S.shlr16(5), "shlr16 r5"),      # 8  r5 = len (반각 1 · 전각 2)
        (S.shll2(5), "shll2 r5"),        # 9  4*len
        (S.mov_reg(5, 1), "mov r5,r1"),  # 10
        (S.shll(1), "shll r1"),          # 11 8*len
        (S.add_reg(1, 5), "add r1,r5"),  # 12 r5 = 12*len = 상자폭(12/24)
        (S.add_imm(-1, 5), "add #-1,r5"),  # 13 ★ 끝 포함: 엔진 관례 x2 = x1 + 폭 − 1
                                         #    (0x10007d80). +폭 그대로 두면 한 열 더 샘플한다 —
                                         #    전각은 다음 칸 첫 열(빈 열)이라 안 보이지만 반각은
                                         #    자기 칸의 안 쓰는 오른쪽 절반이라 이전 문자열
                                         #    픽셀이 세로 한 줄로 드러난다(이름 확인창 `예` 뒤).
        (0x6082, "mov.l @r8,r0"),        # 14 r0 = rec.x1
        (S.add_reg(5, 0), "add r5,r0"),  # 15 x1 + 상자폭 − 1
        (0x1802, "mov.l r0,@(8,r8)"),    # 16 rec.x2
        (0x6583, "mov r8,r5"),           # 17 r5 = rec
        (0x4F22, "sts.l pr,@-r15"),      # 18 pr 저장
        (0x430B, "jsr @r3"),             # 19 DrawChar
        (0x64D3, "mov r13,r4"),          # 20 (지연슬롯) r4 = r13
        (0x4F26, "lds.l @r15+,pr"),      # 21 pr 복원
        (S.rts(), "rts"),                # 22 → 0x1000358E
        (S.nop(), "nop"),                # 23
    ]
    if len(body) % 2:                    # 4바이트 정렬 (스크래치 슬롯 정렬 유지)
        body.append((S.nop(), "nop"))
    return S.assemble(body), 6 * 2       # mova = body[6] → 오프셋 12


def stub_advance():
    """전진폭 훅(0x100035B4) — rec.x2 를 스크래치(= width|len<<16)로 **그대로** 되돌리고
    전진폭 r4 = 하위 8비트(width). 레코드는 프레임마다 다시 그려지므로 len 을 지우면
    다음 프레임 DrawChar 래퍼가 상자폭 0 을 계산한다.
    이어서 원본 자간(@52)·보정(@48)·charIdx++ 재현.  반환: (바이트, mova 바이트오프셋)."""
    S = sh4
    body = [
        (0xC700, None),                  # 0  ★ mova scratch,r0 (변위 apply 패치)
        (0x6002, "mov.l @r0,r0"),        # 1  r0 = tmp(= width|len<<16)
        (0x1802, "mov.l r0,@(8,r8)"),    # 2  rec.x2 = tmp (복원, len 포함)
        (S.and_imm(0xFF), "and #255,r0"),  # 3  r0 = width
        (0x6403, "mov r0,r4"),           # 4  r4 = width
        # 원본 자간/보정
        (0x7B01, "add #1,r11"),          # 5
        (0x51AD, "mov.l @(52,r10),r1"),  # 6
        (0x341C, "add r1,r4"),           # 7
        (0x52AC, "mov.l @(48,r10),r2"),  # 8
        (0x3428, "sub r2,r4"),           # 9
        (S.rts(), "rts"),                # 10
        (S.nop(), "nop"),                # 11
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
        # ★ 2026-09-21 되돌림: @(24,r15) 를 코드로 쓰려다 타이틀 메뉴가 겹쳤다(그 슬롯은 코드가 아니다).
        #   0x10009bec 는 raw 바이트 문자열에서 lead/trail 을 읽어 코드를 만들므로 r11−2/−1 되읽기가 맞다.
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
    #   copy(HOOK2 0x10003AE6): rec.x2 = width | len<<16  (게임의 x2 쓰기 0x10003b12 nop)
    #   DrawChar 래퍼(HOOK3 0x10003582): x2 를 x1+12*len(반각 12·전각 24)으로 스왑 후 jsr
    #   전진폭(HOOK 0x100035b4): rec.x2 복원 후 전진폭 = width
    # rec 는 obj 안 글리프와 함께 살아 동기 — 버퍼·카운트·재사용 desync 전부 없음.
    if mode is True:
        table, npages = build_table(cfg)
        s_adv, adv_mova = stub_advance_diag() if cfg.get("vw_diag") else stub_advance()   # vw_diag: 전진폭 링 로그(flycast 전용)
        s_dc1, dc1_mova = stub_drawchar1(box_width=bool(cfg.get("vw_menu")))   # vw_menu: 상자 = 폭−1 (HOOK7 짝)
        s_cpy = stub_rec_x2(table)          # (rec_x2 링 진단은 stub_rec_x2_diag — 예산상 전진폭 진단과 동시 사용 불가)
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
        if cfg.get("vw_menu"):
            # ★ HOOK8: 본체 DrawChar 호출도 HOOK3 스텁(징검다리 k=1)으로 — r6 = 폭으로 그리게 (stub_drawchar1 참조)
            for i, want in enumerate(HOOK8_ORIG):
                got = struct.unpack_from("<H", blob, raw + (HOOK8 - lo) + i * 2)[0]
                if got != want:
                    raise ValueError(f"{HOOK8 + i*2:#x} = {got:#06x}, {want:#06x} 기대")
            out[raw + (HOOK8 - lo): raw + (HOOK8 - lo) + HOOK3_LEN] = hook_code(HOOK8, t_va + 1 * tl)
        # ★ CTRFTextOut 전진폭 훅(HOOK5) — 스텁은 징검다리 3개 바로 뒤 케이브에.
        txout_note = ""
        if cfg.get("vw_txout", True):
            for i, want in enumerate(HOOK5_ORIG):
                got = struct.unpack_from("<H", blob, raw + (HOOK5 - lo) + i * 2)[0]
                if got != want:
                    raise ValueError(f"{HOOK5 + i*2:#x} = {got:#06x}, {want:#06x} 기대")
            table_va = va_cpy + (len(s_cpy) - len(table))
            _LAST["table_va"] = table_va          # HOOK6(TRFNCHAR)이 같은 표를 쓴다
            s5_va, s5_off = t_va + 3 * tl, t_off + 3 * tl
            assert s5_va % 4 == 0, hex(s5_va)
            if cfg.get("vw_menu"):
                # ★ vw_menu: HOOK7c 가 사각형에 진짜 폭을 남기므로 그리기 앞에서 r8 = 사각형 폭 (HOOK5b). 전진폭 훅(HOOK5)은 불필요.
                for i, want in enumerate(HOOK5B_ORIG):
                    got = struct.unpack_from("<H", blob, raw + (HOOK5B - lo) + i * 2)[0]
                    if got != want:
                        raise ValueError(f"{HOOK5B + i*2:#x} = {got:#06x}, {want:#06x} 기대")
                s5 = stub_txout_rect(s5_va)
                if any(out[s5_off:s5_off + len(s5)]):
                    raise ValueError(f"케이브 {s5_va:#x} 가 비어 있지 않다")
                out[s5_off:s5_off + len(s5)] = s5
                _grow_virtual(out, ".text", (s5_va - lo) + len(s5))
                out[raw + (HOOK5B - lo): raw + (HOOK5B - lo) + 16] = hook16(HOOK5B, s5_va, HOOK5B_RESUME)
                d1, d2 = struct.unpack_from("<ii", out, s5_off + len(s5) - 8)
                assert s5_va + len(s5) - 8 + d1 == HOOK5B_HELPER and s5_va + len(s5) - 4 + d2 == HOOK5B_NOTFOUND, (hex(d1), hex(d2))
                txout_note = f" · TXOut 사각형폭 훅 HOOK5b {HOOK5B:#x}→{s5_va:#x}({len(s5)}B, 표 {table_va:#x})"
            else:
                s5 = stub_txout_advance(s5_va, table_va)
                if any(out[s5_off:s5_off + len(s5)]):
                    raise ValueError(f"케이브 {s5_va:#x} 가 비어 있지 않다")
                out[s5_off:s5_off + len(s5)] = s5
                _grow_virtual(out, ".text", (s5_va - lo) + len(s5))
                out[raw + (HOOK5 - lo): raw + (HOOK5 - lo) + HOOK5_LEN] = hook_code(HOOK5, s5_va)
                txout_note = f" · TXOut 훅 {HOOK5:#x}→{s5_va:#x}({len(s5)}B, 표 {table_va:#x})"
        # ★ vw_menu: HOOK7 — CTRFSquareStr 아틀라스 굽기(0x10007c64)를 폭대로 촘촘히(줄 안 x1 = 앞 글자 x2+1).
        #   스텁은 HOOK5 스텁 바로 뒤 .text 꼬리 케이브(진단 스텁 자리와 같다 — vw_diag 와 동시 불가).
        if cfg.get("vw_menu"):
            if not cfg.get("vw_txout", True):
                raise ValueError("vw_menu(HOOK7)는 vw_txout 의 폭표·케이브를 쓴다 — vw_txout 을 켜라")
            if cfg.get("vw_diag"):
                raise ValueError("vw_menu 와 vw_diag 는 같은 케이브를 쓴다 — 하나만 켜라")
            for i, want in enumerate(HOOK7_ORIG):
                got = struct.unpack_from("<H", blob, raw + (HOOK7 - lo) + i * 2)[0]
                if got != want:
                    raise ValueError(f"{HOOK7 + i*2:#x} = {got:#06x}, {want:#06x} 기대")
            s7_va = (s5_va + len(s5) + 3) & ~3
            s7_off = raw + (s7_va - lo)
            s7 = stub_atlas_pack(s7_va, table_va)
            if s7_off + len(s7) > raw + _text_rsize(out):
                raise ValueError(f"HOOK7 스텁이 .text 꼬리를 넘는다: {s7_off + len(s7) - (raw + _text_rsize(out))}B")
            if any(out[s7_off:s7_off + len(s7)]):
                raise ValueError(f"케이브 {s7_va:#x} 가 비어 있지 않다")
            out[s7_off:s7_off + len(s7)] = s7
            _grow_virtual(out, ".text", (s7_va - lo) + len(s7))
            out[raw + (HOOK7 - lo): raw + (HOOK7 - lo) + 16] = hook16(HOOK7, s7_va, HOOK7_RESUME)
            lit = struct.unpack_from("<i", out, s7_off + len(s7) - 4)[0]
            assert s7_va + len(s7) - 4 + lit == table_va, (hex(lit), hex(table_va))
            txout_note += f" · 아틀라스 촘촘히 HOOK7 {HOOK7:#x}→{s7_va:#x}({len(s7)}B)"
            # HOOK7c — 굽기 뒤 저장 사각형 x2 = x1+폭−1. .text 꼬리가 찼으니 .rdata 꼬리(읽기 = 실행)에 둔다.
            for i, want in enumerate(HOOK7C_ORIG):
                got = struct.unpack_from("<H", blob, raw + (HOOK7C - lo) + i * 2)[0]
                if got != want:
                    raise ValueError(f"{HOOK7C + i*2:#x} = {got:#06x}, {want:#06x} 기대")
            c_va, c_off, c_room = _cave_sec(out, ".rdata")
            s7c = stub_atlas_x2()
            if len(s7c) > c_room:
                raise ValueError(f"HOOK7c 스텁 {len(s7c)}B 가 .rdata 꼬리 {c_room}B 를 넘는다")
            out[c_off:c_off + len(s7c)] = s7c
            _grow_virtual(out, ".rdata", (c_va - _section_va_of(out, ".rdata")) + len(s7c))
            out[raw + (HOOK7C - lo): raw + (HOOK7C - lo) + 16] = hook16(HOOK7C, c_va, HOOK7C_RESUME)
            txout_note += f" · HOOK7c {HOOK7C:#x}→{c_va:#x}({len(s7c)}B, .rdata)"
        # ★ josa: 동적 조사 훅. 스텁은 `.pdata` 꼬리(예외 테이블 뒤 빈칸)에 둔다 —
        #   `.text`·`.rdata` 꼬리는 가변폭 스텁으로 이미 찼다. SH4 는 읽기 = 실행.
        if cfg.get("josa"):
            for i, want in enumerate(JOSA_HOOK_ORIG):
                got = struct.unpack_from("<H", blob, raw + (JOSA_HOOK - lo) + i * 2)[0]
                if got != want:
                    raise ValueError(f"{JOSA_HOOK + i*2:#x} = {got:#06x}, {want:#06x} 기대")
            from kitae.build.hangul import _read_codepage
            marks = josa_literals(_read_codepage(cfg.path("data", "codepage.json")))
            if len(marks) != 1:
                raise ValueError(f"조사 마커는 아직 하나만 된다(현재 {len(marks)}개) — 스텁이 표가 아니다")
            name, mark, b1, yes, no = marks[0]
            j_va, j_off, j_room = _cave_sec(out, ".pdata")
            s_j = stub_josa(j_va, JOSA_ALLOC, mark, b1, yes, no)
            if len(s_j) > j_room:
                raise ValueError(f"조사 스텁 {len(s_j)}B 가 .pdata 꼬리 {j_room}B 를 넘는다")
            out[j_off:j_off + len(s_j)] = s_j
            _grow_virtual(out, ".pdata", (j_va - _section_va_of(out, ".pdata")) + len(s_j))
            out[raw + (JOSA_HOOK - lo): raw + (JOSA_HOOK - lo) + 16] = hook16(
                JOSA_HOOK, j_va, JOSA_RESUME)
            d = struct.unpack_from("<i", out, j_off + len(s_j) - 20)[0]
            assert j_va + len(s_j) - 20 + d == JOSA_ALLOC, hex(d)
            txout_note += (f" · 조사 훅 {JOSA_HOOK:#x}→{j_va:#x}({len(s_j)}B, .pdata) "
                           f"{name} 마커 {mark:#06x} B1 {b1:#06x}")
        # ★ vw_diag: 폰트 DrawChar 입구 진단 — HOOK5 스텁 바로 뒤 케이브(파일 크기 불변)
        if cfg.get("vw_diag"):
            if not cfg.get("vw_txout", True):
                raise ValueError("vw_diag 의 DrawChar 진단은 vw_txout 스텁 뒤에 놓인다 — vw_txout 을 켜라")
            for i, want in enumerate(DIAG_DC_ORIG):
                got = struct.unpack_from("<H", blob, raw + (DIAG_DC_HOOK - lo) + i * 2)[0]
                if got != want:
                    raise ValueError(f"{DIAG_DC_HOOK + i*2:#x} = {got:#06x}, {want:#06x} 기대")
            s6_va = (s5_va + len(s5) + 3) & ~3
            s6_off = raw + (s6_va - lo)
            s6 = stub_drawchar_diag(s6_va)
            pe_ = struct.unpack_from("<I", out, 0x3C)[0]; opt_ = struct.unpack_from("<H", out, pe_ + 20)[0]
            nsec_ = struct.unpack_from("<H", out, pe_ + 6)[0]; text_rsize = None
            for k in range(nsec_):
                h = pe_ + 24 + opt_ + 40 * k
                if out[h:h + 8].rstrip(bytes(1)) == b".text":
                    text_rsize = struct.unpack_from("<I", out, h + 16)[0]
            if s6_off + len(s6) > raw + text_rsize:
                raise ValueError(f"DrawChar 진단 스텁이 .text 꼬리를 넘는다: {s6_off + len(s6) - (raw + text_rsize)}B")
            if any(out[s6_off:s6_off + len(s6)]):
                raise ValueError(f"케이브 {s6_va:#x} 가 비어 있지 않다")
            out[s6_off:s6_off + len(s6)] = s6
            _grow_virtual(out, ".text", (s6_va - lo) + len(s6))
            out[raw + (DIAG_DC_HOOK - lo): raw + (DIAG_DC_HOOK - lo) + HOOK_LEN] = hook_code(DIAG_DC_HOOK, s6_va)
            txout_note += f" · DrawChar 진단 {DIAG_DC_HOOK:#x}→{s6_va:#x}({len(s6)}B)"
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


# ---------------------------------------------------------------------------
# ★ HOOK6 — 스탭롤 스크롤 줄(CTRFCharout, /TRF/TRFNCHAR.DLL) 전진폭 훅 (2026-09-20)
#
# 스탭롤(TRFROLL)은 처음 20줄만 CTRFTXOut(→HOOK5 가변폭)으로 그리고, 스크롤로 재사용되는
# 줄은 CTRFCharout 으로 그린다. CTRFCharout 은 TRFNCHAR.DLL 에만 구현돼 있고(다른 모듈은
# 안 쓴다) 글자마다 아틀라스 칸에 DrawChar 한 뒤 {x, y, w, h} 항목을 쌓는데, 2바이트 글자의
# w 를 상수 24 로 넣는다(0x100016fe). 이 w 가 화면 사각형 폭이자 펜 전진폭이다
# (0x100017b2 `@(8,entry)` → 그리기, 0x100017e2 → `@(40,frame) += w + 자간`).
#
# 훅: 0x100016f2~0x10001701(16B: 항목 포인터 계산 + w 저장)을
#     `mov.l LIT,r0 / bsrf r0 / nop / bra +3 / nop / LIT(4B) / nop` 로 바꾼다.
#     bsr(±4KB)로는 .text 꼬리 케이브(0x10002878~)에 못 닿아 bsrf 를 쓴다.
# 스텁: 항목 포인터를 다시 계산하고, 글자 코드(u16 lead<<8|trail, 문자열 객체 +38 배열,
#     색인 = @r13-1)로 폭표를 조회해 `@(8,entry)` 에 넣고 r3=24(다음 줄의 h 저장용)로 돌아간다.
# 폭표: TRFSTRINGS .ktrw 의 표 하나를 공유한다. 다른 모듈이라 절대주소를 못 쓰므로
#     폰트 객체(@(56,this), 컴포넌트 "Font"/ITRFFontC = TRFSTRINGS CTRFFont)의 vtable
#     (정적 0x1000dc10) 기준 **거리**로 찾는다. vtable 이 기대와 다르면(vt[13]-vt 검증) 24.
# 1바이트 글자(raw 항목의 ASCII)는 다른 블록(w=12)이라 손대지 않는다.
NCHAR_HOOK = 0x100016F2
NCHAR_HOOK_ORIG = (0x52AD, 0xE110, 0x4208, 0x319C, 0x4208, 0x312C, 0xE318, 0x1132)
NCHAR_RESUME = 0x10001702
# 폰트 객체(컴포넌트 "Font"/ITRFFontC = TRFSTRINGS CTRFFont, 등록 레코드 0x1001d2f8)의 vtable 후보.
# QI 맵(0x1000de3c)이 ITRFFont·ITRFFontC 를 오프셋 0 으로 두므로 객체 첫 dword 가 그대로 쓰인다:
# 단독 생성(0x10008e48) → 0x1000de9c, 집합 생성(0x10008f0c, +8 내부) → 0x1000de60. 둘 다 [13]=DrawChar 0x10008bac.
NCHAR_FONT_VTS = ((0x1000DE9C, 0x10008BAC), (0x1000DE60, 0x10008BAC))
_LAST = {}                        # apply() 가 남기는 표 주소 — apply_nchar 가 쓴다


def stub_nchar_width(stub_va, table_va):
    """CTRFCharout 2바이트 글자 폭 스텁. 들어올 때 r9=항목 배열, r10=this, r13=&색인(이미 +1),
    r14=프레임(@r14=문자열 객체). r0~r7 만 쓴다. 나갈 때 @(8,항목)=폭, r3=24.
    폰트 vtable 을 두 후보와 대조해(vt[13]−vt) 맞는 쪽의 (표−vt) 거리를 더해 표를 찾는다."""
    S = sh4
    (vt1, dc1), (vt2, dc2) = NCHAR_FONT_VTS
    L = {}
    body = [
        (S.movl_disp_rm(52, 10, 7), "mov.l @(52,r10),r7"),   # 0  k = 항목 수
        (S.shll2(7), "shll2 r7"),                             # 1
        (S.shll2(7), "shll2 r7"),                             # 2  k*16
        (S.add_reg(9, 7), "add r9,r7"),                       # 3
        (S.add_imm(16, 7), "add #16,r7"),                     # 4  r7 = 항목 포인터
        (0x60D2, "mov.l @r13,r0"),                            # 5  색인(+1 된 값)
        (S.add_imm(-1, 0), "add #-1,r0"),                     # 6
        (S.shll(0), "shll r0"),                               # 7  *2
        (0x62E2, "mov.l @r14,r2"),                            # 8  문자열 객체
        (S.add_imm(38, 2), "add #38,r2"),                     # 9  u16 코드 배열
        (S.movw_r0_rm(2, 0), "mov.w @(r0,r2),r0"),            # 10 코드 (lead<<8|trail)
        (S.extu_w(0, 0), "extu.w r0,r0"),                     # 11
        (S.mov_reg(0, 5), "mov r0,r5"),                       # 12
        (S.shlr8(0), "shlr8 r0"),                             # 13 page
        (S.mov_reg(0, 3), "mov r0,r3"),                       # 14 r3 = page
        (S.mov_reg(5, 0), "mov r5,r0"),                       # 15
        (S.and_imm(255), "and #255,r0"),                      # 16
        (S.mov_reg(0, 5), "mov r0,r5"),                       # 17 r5 = trail
        (S.movl_disp_rm(56, 10, 2), "mov.l @(56,r10),r2"),   # 18 폰트 객체
        (0x6222, "mov.l @r2,r2"),                             # 19 vt
        (S.movl_disp_rm(52, 2, 0), "mov.l @(52,r2),r0"),     # 20 vt[13]
        ("LIT_C1", 1),                                        # 21 mov.l C1,r1
        (S.add_reg(2, 1), "add r2,r1"),                       # 22 vt + (dc1 - vt1)
        (S.cmp_eq(1, 0), "cmp/eq r1,r0"),                     # 23
        ("bt", "USE1"),                                       # 24
        ("LIT_C2", 1),                                        # 25 mov.l C2,r1
        (S.add_reg(2, 1), "add r2,r1"),                       # 26
        (S.cmp_eq(1, 0), "cmp/eq r1,r0"),                     # 27
        ("bf", "FALLBACK"),                                   # 28
        ("LIT_D2", 4),                                        # 29 mov.l D2,r4
        ("bra", "HAVE"),                                      # 30
        (S.nop(), "nop"),                                     # 31
        ("USE1", ("LIT_D1", 4)),                              # 32 mov.l D1,r4
        ("HAVE", (S.add_reg(2, 4), "add r2,r4")),             # 33 r4 = 표
        (S.mov_reg(3, 0), "mov r3,r0"),                       # 34 page
        (S.movb_r0_rm(4, 0), "mov.b @(r0,r4),r0"),            # 35 페이지맵[page]
        (S.extu_b(0, 0), "extu.b r0,r0"),                     # 36
        (S.mov_reg(0, 1), "mov r0,r1"),                       # 37 pv
        (S.tst_imm(128), "tst #128,r0"),                      # 38 직접값?
        ("bt", "SUB"),                                        # 39
        (S.mov_reg(1, 0), "mov r1,r0"),                       # 40
        (S.and_imm(127), "and #127,r0"),                      # 41 폭 = pv&0x7F
        ("bra", "GOT"),                                       # 42
        (S.nop(), "nop"),                                     # 43
        ("SUB", (S.mov_reg(1, 0), "mov r1,r0")),              # 44 pv
        (S.add_imm(1, 0), "add #1,r0"),                       # 45
        (S.shll8(0), "shll8 r0"),                             # 46 *256
        (S.add_reg(4, 0), "add r4,r0"),                       # 47 +표
        (S.add_reg(5, 0), "add r5,r0"),                       # 48 +trail
        (0x6000, "mov.b @r0,r0"),                             # 49
        (S.extu_b(0, 0), "extu.b r0,r0"),                     # 50 폭
        ("GOT", (0x1702, "mov.l r0,@(8,r7)")),                # 51 항목.w = 폭
        (S.mov_imm(24, 3), "mov #24,r3"),                     # 52 r3 = 24 (h 저장용)
        (S.rts(), "rts"),                                     # 53
        (S.nop(), "nop"),                                     # 54
        ("FALLBACK", (S.mov_imm(24, 0), "mov #24,r0")),       # 55 vtable 이 둘 다 아님
        ("bra", "GOT"),                                       # 56
        (S.nop(), "nop"),                                     # 57
    ]
    # 라벨 풀기
    prog = []
    for ent in body:
        if isinstance(ent[0], str) and ent[0] in ("USE1", "HAVE", "SUB", "GOT", "FALLBACK"):
            L[ent[0]] = len(prog); ent = ent[1]
        prog.append(ent)
    lit_off = len(prog) * 2
    assert lit_off % 4 == 0, lit_off
    lits = {"LIT_C1": (0, dc1 - vt1), "LIT_C2": (4, dc2 - vt2), "LIT_D1": (8, table_va - vt1), "LIT_D2": (12, table_va - vt2)}
    final = []
    for i, ent in enumerate(prog):
        if isinstance(ent[0], str):
            kind = ent[0]
            if kind in lits:
                pc = (i * 2 + 4) & ~3
                final.append((S.movl_pc(lit_off + lits[kind][0] - pc, ent[1]), None))
            else:
                d = L[ent[1]] - (i + 2)
                final.append(({"bt": S.bt, "bf": S.bf, "bra": S.bra}[kind](d), None))
        else:
            final.append(ent)
    code = S.assemble(final, stub_va)
    for a, t in S.disasm([w for w, _ in final], stub_va):          # 분기 목적지 되읽기
        if t.startswith(("bf", "bt", "bra")):
            tgt = (int(t.split()[-1], 16) - stub_va) // 2
            if tgt not in L.values():
                raise ValueError(f"스텁 분기 {a:#x} {t} 가 엉뚱한 곳으로 간다")
    return code + b"".join(struct.pack("<i", v) for _off, v in sorted(lits.values()))

def nchar_hook_code(stub_va):
    """0x100016f2 에 놓는 16B: mov.l LIT,r0 / bsrf r0 / nop / bra 0x10001702 / nop / LIT / nop."""
    S = sh4
    prog = [
        (S.movl_pc(8, 0), None),                # 0x100016f2 → LIT @0x100016fc
        (S.bsrf(0), "bsrf r0"),                               # 0x100016f4 (PC=0x100016f8)
        (S.nop(), "nop"),                                     # 0x100016f6
        (S.bra((NCHAR_RESUME - (NCHAR_HOOK + 6 + 4)) // 2), None),   # 0x100016f8 → 0x10001702
        (S.nop(), "nop"),                                     # 0x100016fa
    ]
    code = S.assemble(prog, NCHAR_HOOK)
    lit = struct.pack("<i", stub_va - (NCHAR_HOOK + 2 + 4))  # bsrf: PC = 0x100016f4+4
    return code + lit + S.to_bytes([S.nop()])


def apply_nchar(cfg, blob, table_va=None):
    """/TRF/TRFNCHAR.DLL 에 HOOK6 을 심는다. (바이트, 로그 한 줄)."""
    table_va = table_va or _LAST.get("table_va")
    if not table_va:
        raise ValueError("TRFSTRINGS 폭표 주소를 모른다 — apply() 뒤에 불러야 한다")
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    base = struct.unpack_from("<I", blob, pe + 24 + 28)[0]
    text_va = text_raw = None
    for i in range(nsec):
        h = pe + 24 + opt + 40 * i
        if blob[h:h + 8].rstrip(bytes(1)) == b".text":
            _vs, rva, _rs, raw = struct.unpack_from("<IIII", blob, h + 8)
            text_va, text_raw = base + rva, raw
    if text_va is None:
        raise ValueError(".text 없음")
    hoff = text_raw + (NCHAR_HOOK - text_va)
    for i, want in enumerate(NCHAR_HOOK_ORIG):
        got = struct.unpack_from("<H", blob, hoff + i * 2)[0]
        if got != want:
            raise ValueError(f"TRFNCHAR {NCHAR_HOOK + i*2:#x} = {got:#06x}, {want:#06x} 기대")
    out = bytearray(blob)
    s_va, s_off = _cave(out, text_raw, text_va)
    stub = stub_nchar_width(s_va, table_va)
    if any(out[s_off:s_off + len(stub)]):
        raise ValueError(f"케이브 {s_va:#x} 가 비어 있지 않다")
    out[s_off:s_off + len(stub)] = stub
    _grow_virtual(out, ".text", (s_va - text_va) + len(stub))
    hook = nchar_hook_code(s_va)
    assert len(hook) == 16, len(hook)
    out[hoff:hoff + 16] = hook
    # 되읽기: bsrf 목적지 = 스텁, 리터럴 거리 = 표-vtable
    lit = struct.unpack_from("<i", out, hoff + 10)[0]
    assert NCHAR_HOOK + 6 + lit == s_va, (hex(lit), hex(s_va))
    c1, c2, d1, d2 = struct.unpack_from("<iiii", out, s_off + len(stub) - 16)
    (vt1, dc1), (vt2, dc2) = NCHAR_FONT_VTS
    assert (c1, c2, d1, d2) == (dc1 - vt1, dc2 - vt2, table_va - vt1, table_va - vt2), (c1, c2, d1, d2)
    note = (f"TRFNCHAR 훅 {NCHAR_HOOK:#x}→{s_va:#x}({len(stub)}B, 표 {table_va:#x} = 폰트 vt {vt1:#x}/{vt2:#x}"
            f"+거리) — 스탭롤 스크롤 줄(CTRFCharout) 가변폭")
    return bytes(out), note


# ---------------------------------------------------------------------------
# 진단용 HOOK2 스텁 (옵션 `vw_diag`, 기본 false, 커밋 금지) — 2026-09-20
# stub_rec_x2 와 같은 일을 하면서 SetText 줄마다 링(cnt 0x8CFE08FC, base 0x8CFE0900, 1024칸 순환)에
#   머리글 = count<<16 | line,  글자마다 = code<<16 | (width|len<<16 의 하위 16비트 = width)
# 를 남긴다. 팝업/선택 상자가 열릴 때 HOOK2 가 실제로 무엇을 읽고 무엇을 쓰는지 라이브로 본다.
# ★ 물리 RAM 꼭대기(0x8CFE....)는 redream 에서 죽는다 — flycast 전용, 옵션 끄면 원래 스텁.
DIAG_RING_CNT, DIAG_RING_BASE, DIAG_RING_MASK = 0x8CFE08FC, 0x8CFE0900, 0x3FF


def stub_rec_x2_diag(table_bytes):
    """stub_rec_x2 + 링 로그. 크기 예산: .ktrw 1024B 안에 adv24+dc1 48+scratch 4+cpy 가 들어가야
    TRFSTRINGS 가 디스크 익스텐트(+1024B)를 안 넘는다 → cpy ≤ 948 = 코드 172 + 리터럴 8 + 표 768.
    그래서 머리글은 count(≤25) 그대로, 글자는 code(≥0x8140) 그대로 남긴다(폭은 오프라인에서 표로 계산), 링은 256칸 순환."""
    S = sh4
    L = {}
    LOG = [  # ring[cnt] = r5 ; cnt = (cnt+1) & 0xFF   — r0·r1 사용 (8명령)
        (0x60B2, "mov.l @r11,r0"), (0x6103, "mov r0,r1"), (0x4108, "shll2 r1"), (0x31CC, "add r12,r1"),
        (0x2152, "mov.l r5,@r1"), (0x7001, "add #1,r0"), (0xC9FF, "and #255,r0"), (0x2B02, "mov.l r0,@r11"),
    ]
    body = [
        (0x6283, "mov r8,r2"), (0xE05C, "mov #92,r0"), (0x320C, "add r0,r2"),
        (0x61A3, "mov r10,r1"), (0x4108, "shll2 r1"), (0x4108, "shll2 r1"), (0x321C, "add r1,r2"),   # r2 = rec_0.x2
        ("MOVA", None),                                      # mova LIT,r0
        (0x6B02, "mov.l @r0,r11"),                          # r11 = ring cnt 주소
        (S.movl_disp_rm(4, 0, 12), "mov.l @(4,r0),r12"),    # r12 = ring base
        (0x7008, "add #8,r0"),
        (0x6303, "mov r0,r3"),                               # r3 = table
        (0xC512, "mov.w @(36,gbr),r0"), (0x600D, "extu.w r0,r0"), (0x6703, "mov r0,r7"),   # count
        (0x6573, "mov r7,r5"), *LOG,                              # 머리글 = count<<16
        (0x6692, "mov.l @r9,r6"), (0xE06C, "mov #108,r0"), (S.movl_r0_rm(6, 6), "mov.l @(r0,r6),r6"),   # r6 = head
        ("LOOP", (0x2668, "tst r6,r6")),
        ("bt", "DONE"),
        (S.movl_disp_rm(12, 6, 0), "mov.l @(12,r6),r0"), (0x2008, "tst r0,r0"),
        ("bt", "SKIP"),
        (S.movl_disp_rm(8, 6, 0), "mov.l @(8,r6),r0"), (0x6503, "mov r0,r5"), (S.extu_b(5, 5), "extu.b r5,r5"),
        (S.shlr8(0), "shlr8 r0"), (0x6103, "mov r0,r1"),
        (0x6013, "mov r1,r0"), (0x003C, "mov.b @(r0,r3),r0"), (0x600C, "extu.b r0,r0"), (0x6103, "mov r0,r1"),
        (0xC880, "tst #128,r0"),
        ("bt", "SUB"),
        (0x6013, "mov r1,r0"), (0xC97F, "and #127,r0"),
        ("bra", "STORE"), (S.nop(), "nop"),
        ("SUB", (0x6013, "mov r1,r0")), (0x7001, "add #1,r0"), (0x4018, "shll8 r0"), (0x303C, "add r3,r0"), (0x305C, "add r5,r0"),
        (0x6000, "mov.b @r0,r0"), (0x600C, "extu.b r0,r0"),
        ("STORE", (S.movl_disp_rm(12, 6, 1), "mov.l @(12,r6),r1")), (S.shll16(1), "shll16 r1"), (S.or_reg(1, 0), "or r1,r0"),
        (0x2202, "mov.l r0,@r2"),
        (S.movl_disp_rm(8, 6, 5), "mov.l @(8,r6),r5"), *LOG,   # 글자 = code<<16
        (0xE120, "mov #32,r1"), (0x4108, "shll2 r1"), (0x321C, "add r1,r2"),
        (0x4710, "dt r7"), (0x6662, "mov.l @r6,r6"),
        ("bf", "LOOP"),
        ("bra", "DONE"), (S.nop(), "nop"),
        ("SKIP", (0x6662, "mov.l @r6,r6")),
        ("bra", "LOOP"), (S.nop(), "nop"),
        ("DONE", (0x6BA3, "mov r10,r11")), (0x4B08, "shll2 r11"), (0xEC54, "mov #84,r12"), (0x3C8C, "add r8,r12"),
        (0xE520, "mov #32,r5"), (0x4508, "shll2 r5"),
        (S.rts(), "rts"), (S.nop(), "nop"),
    ]
    prog = []
    for ent in body:
        if isinstance(ent[0], str) and ent[0] in ("LOOP", "SUB", "STORE", "SKIP", "DONE"):
            L[ent[0]] = len(prog); ent = ent[1]
        prog.append(ent)
    n = len(prog)
    lit_off = (n * 2 + 3) & ~3
    prog += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    final = []
    for i, ent in enumerate(prog):
        if ent[0] == "MOVA":
            final.append((S.mova(lit_off - ((i * 2 + 4) & ~3)), None))
        elif isinstance(ent[0], str):
            final.append(({"bt": S.bt, "bf": S.bf, "bra": S.bra}[ent[0]](L[ent[1]] - (i + 2)), None))
        else:
            final.append(ent)
    code = S.assemble(final)
    out = code + struct.pack("<II", DIAG_RING_CNT, DIAG_RING_BASE) + table_bytes
    if len(out) > 948:
        raise ValueError(f"진단 스텁이 예산(948B)을 넘는다: {len(out)}")
    return out


def stub_advance_diag():
    """stub_advance + 링 로그(옵션 vw_diag). **표면 모드 객체(@(40,obj) 비트1)** 의 글자에서만
    ring[cnt] = obj(r10), ring[cnt+1] = 전진폭(r4) 을 남긴다 — 매 프레임 그리는 대사창은 비트1 이
    없어 링을 안 채운다. 팝업/선택 상자가 훅 경로(0x100034FC)로 그려지는지, 그때 전진폭이 얼마인지
    본다. 리터럴 [cnt, base] 는 코드 뒤 4정렬. 반환: (바이트, mova 오프셋 0)."""
    S = sh4
    body = [
        (0xC700, None),                  # 0  mova scratch,r0 (변위 apply 패치)
        (0x6002, "mov.l @r0,r0"),        # 1
        (0x1802, "mov.l r0,@(8,r8)"),    # 2  rec.x2 복원
        (S.and_imm(0xFF), "and #255,r0"),  # 3
        (0x6403, "mov r0,r4"),           # 4  r4 = width
        (0x7B01, "add #1,r11"),          # 5
        (0x51AD, "mov.l @(52,r10),r1"),  # 6
        (0x341C, "add r1,r4"),           # 7
        (0x52AC, "mov.l @(48,r10),r2"),  # 8
        (0x3428, "sub r2,r4"),           # 9  r4 = 전진폭 (여기까지 원본 스텁과 같다)
        (0xE048, "mov #72,r0"),          # 10 @(72,r15) = 이 줄의 글자수
        (S.movl_r0_rm(15, 0), "mov.l @(r0,r15),r0"),   # 11
        (0x8809, "cmp/eq #9,r0"),        # 12 9글자 줄(팝업 라벨)만
        ("bf", "DONE"),                  # 13
        ("MOVA", None),                  # 13 mova LIT,r0
        (0x6102, "mov.l @r0,r1"),        # 14 r1 = cnt 주소
        (S.movl_disp_rm(4, 0, 2), "mov.l @(4,r0),r2"),      # 15 r2 = base
        (0x6012, "mov.l @r1,r0"),        # 16 cnt
        (0x6303, "mov r0,r3"),           # 17
        (0x4308, "shll2 r3"),            # 18
        (0x332C, "add r2,r3"),           # 19 slot
        (0x23A2, "mov.l r10,@r3"),       # 20 obj
        (0x1341, "mov.l r4,@(4,r3)"),    # 21 advance
        (0x7002, "add #2,r0"),           # 22
        (S.and_imm(0xFF), "and #255,r0"),  # 23 256칸 순환
        (0x2102, "mov.l r0,@r1"),        # 24
        ("DONE", (S.rts(), "rts")),      # 25
        (S.nop(), "nop"),                # 26
    ]
    L = {}; prog = []
    for ent in body:
        if isinstance(ent[0], str) and ent[0] == "DONE":
            L["DONE"] = len(prog); ent = ent[1]
        prog.append(ent)
    n = len(prog)
    lit_off = (n * 2 + 3) & ~3
    prog += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    final = []
    for i, ent in enumerate(prog):
        if ent[0] == "MOVA":
            final.append((S.mova(lit_off - ((i * 2 + 4) & ~3)), None))
        elif ent[0] in ("bt", "bf"):
            final.append(({"bt": S.bt, "bf": S.bf}[ent[0]](L["DONE"] - (i + 2)), None))
        else:
            final.append(ent)
    code = S.assemble(final)
    return code + struct.pack("<II", DIAG_RING_CNT, DIAG_RING_BASE), 0


# 폰트 DrawChar(CTRFFont vt[13] 0x10008bac) 입구 진단 — 옵션 vw_diag. 0x10008bba(PR 저장 직후) 12B 를
# hook_code 로 바꾸고 스텁이 ring[cnt] = 호출자 PR(@r15), ring[cnt+1] = code<<16 | y1<<8 | x1 을 남긴 뒤
# 원본 6명령(mov.l r6,@(36,r15) / mov r4,r8 / mov r5,r13 / add #-24,r15 / mov #120,r9 / add r8,r9)을 재현하고
# rts 로 0x10008bc6 에 돌아간다. 누가 글자를 아틀라스/텍스처에 찍는지(호출자·사각형)를 본다.
DIAG_DC_HOOK = 0x10008BBA
DIAG_DC_ORIG = (0x1F69, 0x6843, 0x6D53, 0x7FE8, 0xE978, 0x398C)


def stub_drawchar_diag(stub_va):
    S = sh4
    body = [
        ("MOVA", None),                              # 0  mova LIT,r0
        (0x6102, "mov.l @r0,r1"),                    # 1  r1 = cnt 주소
        (S.movl_disp_rm(4, 0, 2), "mov.l @(4,r0),r2"),   # 2  r2 = base
        (0x6012, "mov.l @r1,r0"),                    # 3  cnt
        (0x6303, "mov r0,r3"), (0x4308, "shll2 r3"), (0x332C, "add r2,r3"),   # 4-6 slot
        (0x7002, "add #2,r0"), (S.and_imm(0xFF), "and #255,r0"), (0x2102, "mov.l r0,@r1"),   # 7-9 cnt 갱신
        (0x51F6, "mov.l @(24,r15),r1"),              # 10 스택의 r8 = 호출자(SquareStr vt[4])의 this
        (0x2312, "mov.l r1,@r3"),                    # 11
        (0x6153, "mov r5,r1"), (S.shll16(1), "shll16 r1"),          # 12-13 code<<16
        (0x6062, "mov.l @r6,r0"), (S.extu_b(0, 0), "extu.b r0,r0"), (S.or_reg(0, 1), "or r0,r1"),   # 14-16 | x1
        (S.movl_disp_rm(4, 6, 0), "mov.l @(4,r6),r0"), (S.extu_b(0, 0), "extu.b r0,r0"), (0x4018, "shll8 r0"), (S.or_reg(0, 1), "or r0,r1"),   # 17-20 | y1<<8
        (0x1311, "mov.l r1,@(4,r3)"),                # 21
        (0x1F69, "mov.l r6,@(36,r15)"), (0x6843, "mov r4,r8"), (0x6D53, "mov r5,r13"),   # 22-24 원본
        (0x7FE8, "add #-24,r15"), (0xE978, "mov #120,r9"), (0x398C, "add r8,r9"),      # 25-27 원본
        (S.rts(), "rts"), (S.nop(), "nop"),          # 28-29
    ]
    n = len(body)
    lit_off = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit_off - n * 2) // 2)
    final = []
    for i, ent in enumerate(body):
        if ent[0] == "MOVA":
            final.append((S.mova(lit_off - ((i * 2 + 4) & ~3)), None))
        else:
            final.append(ent)
    code = S.assemble(final, stub_va)
    return code + struct.pack("<II", DIAG_RING_CNT, DIAG_RING_BASE)


# ───────────────────────────────────────────────────────────────────────────────
# ★ HOOK7 (vw_menu, 2026-09-21) — 메뉴 팝업(CGeneralMenu, MENUSELECT.DLL) 가변폭.
#
# 팝업 라벨은 CTRFMsgput 이 **표면 모드**로 CTRFSquareStr 아틀라스(128×128, 한 줄 5칸×24)에 한 번 굽고,
# MENUSELECT 의 항목 빌더(vt[8] 0x10001678)가 **아틀라스 한 줄(24px 행) = 화면 120px 타일** 로 이어 붙여
# 띠를 만든다(타일 u 0..120/128, v 는 행 표). 그러니 글자 피치는 굽기 자리(x1=(i%5)*24)가 전부다.
#   7a TRFSTRINGS 0x10007d6e: 굽기 x1 = 같은 행 앞 글자의 x2+1(행 첫 글자는 0), 폭 = 폭표(2바이트) / 12(1바이트).
#      사각형 x2 = x1+폭−1 은 원본 코드가 그대로 만든다. 행 배정(i/5)은 그대로라 5글자/행.
#   7b MENUSELECT 0x100019aa(타일 루프 머리): 타일 폭 = 그 행 글자 폭 합 × k × 배율, u1(fr13) = 합/128.
#      행 폭은 CTRFMenu(+80)+152+i*4 의 항목 문자열 사본을 걸어 폭표로 다시 센다(0x20/0x09 는 전처리기가
#      지우므로 건너뜀). 폭표는 CTRFMenu vtable(0x1000d82c) 거리로 찾는다(HOOK6 과 같은 수법).
#      마지막 타일 다듬기(pad = 120 − count*24%120)는 r10=0 으로 끈다(2워드).
#   HOOK3 상자 = 폭−1 (stub_drawchar1(box_width=True)) — 촘촘한 아틀라스에서 다음 글자 조각이 새지 않게.
HOOK5B = 0x10009C90                       # TextOut vt[5]: 사각형 찾기 헬퍼 호출 자리 (16B 훅, vw_menu)
HOOK5B_ORIG = (0xE718, 0x64A3, 0x7B01, 0x66E3, 0xB040, 0x37FC, 0x2008, 0x8920)
HOOK5B_RESUME = 0x10009CA0
HOOK5B_HELPER = 0x10009D1C                # 사각형/텍스처 찾기 (this, code, &tex, &rect) → r0 = 찾음
HOOK5B_NOTFOUND = 0x10009CE2              # 못 찾으면 원본이 뛰던 곳(그리기 건너뜀)
HOOK7 = 0x10007D6E
HOOK7_ORIG = (0xD0B7, 0x011A, 0x400B, 0x1F1E, 0x5286, 0x0027, 0xE040, 0x011A)
HOOK7_RESUME = 0x10007D7E
MSEL_HOOK = 0x100019AA
MSEL_HOOK_ORIG = (0xE030, 0xF5F6, 0xD075, 0x400B, 0xF4EC, 0xE034, 0x94EC, 0x34FC)
MSEL_RESUME = 0x100019BA
MSEL_PAD = ((0x100018BA, 0xEA78, 0xEA00),     # mov #120,r10 → mov #0,r10
            (0x100018BC, 0x3A48, 0x0009))     # sub r4,r10   → nop
MSEL_W_HOOK = 0x10001858                  # W = float(글자수×24) 자리 (16B 훅) → W = 글자 폭 합
MSEL_W_ORIG = (0xE218, 0x61B2, 0x0217, 0x400B, 0x041A, 0x7904, 0xF90A, 0x50F9)
MSEL_W_RESUME = 0x10001868
MSEL_ITOF, MSEL_FADD, MSEL_FMUL = 0x10005D84, 0x10005F38, 0x10006140   # 게임의 FP 썽크(fr4,fr5→fr0 / r4→fr0)
MENU_VT, MENU_VT3 = 0x1000D82C, 0x10005CC4          # CTRFMenu vtable, vt[3]=SetItems (검증용 거리)
K_UNIT = 0x3907BAC1                                  # 화면 1px 의 월드 단위(빌더가 쓰는 상수)
INV128 = 0x3C000000                                  # 1/128


def _text_rsize(blob):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    for k in range(nsec):
        h = pe + 24 + opt + 40 * k
        if blob[h:h + 8].rstrip(bytes(1)) == b".text":
            return struct.unpack_from("<I", blob, h + 16)[0]
    raise KeyError(".text")


def hook16(hook_va, stub_va, resume_va):
    """16B 훅: mov.l LIT,r0 / bsrf r0 / nop / bra resume / nop / (nop) / LIT. r0 를 쓴다.
    LIT 는 (스텁 − (훅+6)) 거리 — 재배치 불필요. 훅 주소 4배수/2배수 둘 다 리터럴이 4정렬되게 놓는다."""
    S = sh4
    aligned = hook_va % 4 == 0
    prog = [
        (S.movl_pc(8, 0), None),                    # LIT 는 (PC&~3)+8
        (S.bsrf(0), "bsrf r0"),
        (S.nop(), "nop"),
        (S.bra((resume_va - (hook_va + 6 + 4)) // 2), None),
        (S.nop(), "nop"),
    ]
    if aligned:
        prog.append((S.nop(), "nop"))               # LIT 를 +12 로
    code = S.assemble(prog, hook_va)
    lit = struct.pack("<i", stub_va - (hook_va + 2 + 4))
    out = code + lit + (b"" if aligned else S.to_bytes([S.nop()]))
    assert len(out) == 16, len(out)
    return out


def _resolve(body, labels, lits, stub_va):
    """('bt'|'bf'|'bra', 라벨) · ('MOVA', 리터럴이름) · (라벨, 명령) 을 풀어 assemble 한다."""
    S = sh4
    L = {}
    prog = []
    for ent in body:
        if isinstance(ent[0], str) and ent[0] in labels:
            L[ent[0]] = len(prog); ent = ent[1]
        prog.append(ent)
    lit_off = len(prog) * 2
    assert lit_off % 4 == 0, lit_off
    final = []
    for i, ent in enumerate(prog):
        if isinstance(ent[0], str):
            kind = ent[0]
            if kind == "MOVA":
                final.append((S.mova(lit_off + lits[ent[1]] - ((i * 2 + 4) & ~3)), None))
            elif kind == "MOVW":
                d = (lit_off + lits[ent[1]] - (i * 2 + 4)) // 2
                assert 0 <= d <= 255 and (lit_off + lits[ent[1]] - (i * 2 + 4)) % 2 == 0, d
                final.append((0x9000 | d, None))
            else:
                final.append(({"bt": S.bt, "bf": S.bf, "bra": S.bra}[kind](L[ent[1]] - (i + 2)), None))
        else:
            final.append(ent)
    code = S.assemble(final, stub_va)
    for a, t in S.disasm([w for w, _ in final], stub_va):
        if t.startswith(("bf", "bt", "bra")):
            tgt = (int(t.split()[-1], 16) - stub_va) // 2
            if tgt not in L.values():
                raise ValueError(f"스텁 분기 {a:#x} {t} 가 엉뚱한 곳으로 간다")
    return code, lit_off


def stub_txout_rect(stub_va):
    """HOOK5b 스텁(TextOut 0x10009c90, vw_menu). 원본대로 헬퍼 0x10009d1c 를 부르고(사각형·텍스처 찾기), 찾았으면
    **r8 = 사각형 폭(x2−x1+1)** — HOOK7c 로 사각형이 진짜 폭이라 표 조회가 필요 없다. 그러면 원본이 r8 로 만드는
    그리기 폭(@(20,r15) = r8·배율/100)과 전진폭(0x10009ce2~) 이 저절로 폭이 된다(HOOK5 불필요). 못 찾으면 원본처럼
    0x10009ce2 로 뛴다. 엔진은 r8=24 를 넘겨 8텍셀 마침표를 24px 로 늘려 `_` 처럼 그렸다(9/22 캡처)."""
    S = sh4
    body = [
        (0xE718, "mov #24,r7"),               # 원본 0x10009c90~
        (0x64A3, "mov r10,r4"),
        (0x7B01, "add #1,r11"),
        (0x66E3, "mov r14,r6"),
        (0x37FC, "add r15,r7"),               # r7 = &rect 슬롯 (push 전 r15)
        (0x4F22, "sts.l pr,@-r15"),
        ("MOVA", "HELPER"),
        (0x6102, "mov.l @r0,r1"),
        (0x310C, "add r0,r1"),
        (0x410B, "jsr @r1"),
        (S.nop(), "nop"),
        (0x4F26, "lds.l @r15+,pr"),
        (0x2008, "tst r0,r0"),
        ("bt", "NF"),
        (0x51F6, "mov.l @(24,r15),r1"),       # rect
        (0x5812, "mov.l @(8,r1),r8"),         # x2
        (0x6012, "mov.l @r1,r0"),             # x1
        (0x3808, "sub r0,r8"),
        (0x7801, "add #1,r8"),                # r8 = 폭
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        ("NF", ("MOVA", "NOTFOUND")),
        (0x6102, "mov.l @r0,r1"),
        (0x310C, "add r0,r1"),
        (0x412B, "jmp @r1"),
        (S.nop(), "nop"),
    ]
    code, lit_off = _resolve(body, ("NF",), {"HELPER": 0, "NOTFOUND": 4}, stub_va)
    lit_va = stub_va + lit_off
    return code + struct.pack("<ii", HOOK5B_HELPER - lit_va, HOOK5B_NOTFOUND - (lit_va + 4))


def stub_atlas_pack(stub_va, table_va):
    """HOOK7a 스텁(TRFSTRINGS 0x10007d6e, 16B 훅). 들어올 때 macl=(i/5)*셀, r12=i, r8=this, r9=엔진폭(24/12),
    @(36,r15)=코드, @(40,r15)=len(1/2). 나갈 때 @(56,r15)=y1, r1=x1, r0=64, **r9 는 그대로**(굽기 블릿은 24·12
    사각형만 제대로 굽는다 — 폭 16 사각형을 주면 로마자가 깨진다, 9/21) — 원본 0x10007d7e 가 x2=x1+r9−1 을
    만들고 HOOK7c 가 저장 직전에 x2 = x1+폭−1 로 고친다. 폭은 @(4,r15), 다음 글자의 x1(운영 x)은 @(0,r15)
    (굽기 프레임의 빈 슬롯). 행 첫 글자 판정은 rect[i−1].y1 ≠ y1 (i%5 나눗셈 없이)."""
    S = sh4
    body = [
        (0x011A, "sts macl,r1"),              # y1 = (i/5)*셀
        (0x1F1E, "mov.l r1,@(56,r15)"),
        (0xE300, "mov #0,r3"),                # x1 기본 0
        (0x62C3, "mov r12,r2"),
        (0x2228, "tst r2,r2"),
        ("bt", "ROWSTART"),                   # i == 0
        (0x4208, "shll2 r2"),
        (0x4208, "shll2 r2"),                 # i*16
        (0xE074, "mov #116,r0"),
        (0x308C, "add r8,r0"),                # this+116 = &rect[-1]
        (0x320C, "add r0,r2"),                # r2 = &rect[i-1]
        (0x5021, "mov.l @(4,r2),r0"),         # 앞 글자 y1
        (0x3010, "cmp/eq r1,r0"),
        ("bf", "ROWSTART"),                   # 다른 행 → x1 = 0
        (0x63F2, "mov.l @r15,r3"),            # 운영 x
        ("ROWSTART", (0x6133, "mov r3,r1")),  # r1 = x1
        (0x50FA, "mov.l @(40,r15),r0"),       # len
        (0x8802, "cmp/eq #2,r0"),
        ("bf", "ONE"),                        # 1바이트: 엔진 12
        ("MOVA", "TABLE"),
        (0x6202, "mov.l @r0,r2"),
        (0x320C, "add r0,r2"),                # r2 = 폭표
        (0x50F9, "mov.l @(36,r15),r0"),       # 코드
        (0x6503, "mov r0,r5"),
        (0x4019, "shlr8 r0"),                 # page
        (0x002C, "mov.b @(r0,r2),r0"),        # 페이지맵
        (0xC880, "tst #128,r0"),
        ("bt", "SUB"),
        ("bra", "GOT"),
        (0xC97F, "and #127,r0"),              # (지연) 직접값
        ("SUB", (0x7001, "add #1,r0")),
        (0x4018, "shll8 r0"),
        (0x302C, "add r2,r0"),
        (0x655C, "extu.b r5,r5"),             # trail
        (0x305C, "add r5,r0"),
        (0x6000, "mov.b @r0,r0"),
        ("bra", "GOT"),
        (0x600C, "extu.b r0,r0"),             # (지연)
        ("ONE", (0xE00C, "mov #12,r0")),
        ("GOT", (0x1F01, "mov.l r0,@(4,r15)")),   # 폭 저장 (HOOK7c)
        (0x303C, "add r3,r0"),
        (0x2F02, "mov.l r0,@r15"),            # 운영 x = x1 + 폭
        (0xE040, "mov #64,r0"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        (S.nop(), "nop"),                     # 리터럴 4정렬
    ]
    code, lit_off = _resolve(body, ("ROWSTART", "SUB", "ONE", "GOT"), {"TABLE": 0}, stub_va)
    return code + struct.pack("<i", table_va - (stub_va + lit_off))


HOOK7C = 0x10007DA4                       # 굽기 뒤 사각형 저장 직전 (16B 훅)
HOOK7C_ORIG = (0x64C3, 0x51F6, 0x4408, 0x52FE, 0x4408, 0x710C, 0x314C, 0x1121)
HOOK7C_RESUME = 0x10007DB4


def stub_atlas_x2():
    """HOOK7c 스텁: @(60,r15)(x2) = @(52,r15)(x1) + @(4,r15)(폭) − 1, 원본 8명령 재현. 사각형 배열엔 진짜 폭이
    남아 대사(rec)·TextOut(사각형 복사)·모두 폭 사각형을 받는다. 자리는 .rdata 꼬리(SH4 는 읽기 = 실행)."""
    S = sh4
    body = [
        (0x50FD, "mov.l @(52,r15),r0"),
        (0x51F1, "mov.l @(4,r15),r1"),
        (0x301C, "add r1,r0"),
        (0x70FF, "add #-1,r0"),
        (0x1F0F, "mov.l r0,@(60,r15)"),
        (0x64C3, "mov r12,r4"),               # 원본 0x10007da4~
        (0x51F6, "mov.l @(24,r15),r1"),
        (0x4408, "shll2 r4"),
        (0x52FE, "mov.l @(56,r15),r2"),
        (0x4408, "shll2 r4"),
        (0x710C, "add #12,r1"),
        (0x314C, "add r4,r1"),
        (0x1121, "mov.l r2,@(4,r1)"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        (S.nop(), "nop"),
    ]
    return S.assemble(body)



def _section_va_of(blob, name):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    base = struct.unpack_from("<I", blob, pe + 24 + 28)[0]
    for i in range(nsec):
        h = pe + 24 + opt + 40 * i
        if blob[h:h + 8].rstrip(bytes(1)) == name.encode():
            return base + struct.unpack_from("<I", blob, h + 12)[0]
    raise KeyError(name)


def _cave_sec(blob, name):
    """섹션 `name` 꼬리의 연속 0 구간 (VA, 파일오프셋, 남은 바이트) — 4정렬."""
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    base = struct.unpack_from("<I", blob, pe + 24 + 28)[0]
    for i in range(nsec):
        h = pe + 24 + opt + 40 * i
        if blob[h:h + 8].rstrip(bytes(1)) != name.encode():
            continue
        _vs, rva, rsz, raw = struct.unpack_from("<IIII", blob, h + 8)
        end = raw + rsz
        k = 0
        while blob[end - 1 - k] == 0:
            k += 1
        off = (end - k + 3) & ~3
        return base + rva + (off - raw), off, end - off
    raise KeyError(name)


def stub_menu_tiles(stub_va, table_va):
    """HOOK7b 스텁(MENUSELECT 0x100019aa, 16B 훅; 원본 5+3명령을 대신한다). 들어올 때 r8=항목 i,
    r11=타일 t, r9=항목 구조체(+16 배율), @r14=CGeneralMenu, fr14=x0. 나갈 때 fr0=x1(=x0+타일폭),
    fr13=u1, @(48,r15)=타일폭(루프 끝 전진이 읽는다), r0=52, r4=r15+0x84 — 원본 0x100019ba 로 이어진다.
    FP 는 게임 썽크(itof/fadd/fmul)를 mova 거리 리터럴로 불러 FPSCR 처리까지 원본과 같게 한다."""
    S = sh4
    body = [
        (0x61E2, "mov.l @r14,r1"),            # this
        (0xE050, "mov #80,r0"),
        (0x011E, "mov.l @(r0,r1),r1"),        # CTRFMenu
        (0xE04C, "mov #76,r0"),
        (0x4000, "shll r0"),                  # 152
        (0x6283, "mov r8,r2"),
        (0x4208, "shll2 r2"),
        (0x302C, "add r2,r0"),
        (0x051E, "mov.l @(r0,r1),r5"),        # r5 = 항목 문자열 사본
        (0x6212, "mov.l @r1,r2"),             # CTRFMenu vtable
        (0x5123, "mov.l @(12,r2),r1"),        # vt[3]
        (0x3128, "sub r2,r1"),                # vt[3] − vt
        ("MOVA", "VT3"),
        (0x6302, "mov.l @r0,r3"),
        (0x3130, "cmp/eq r3,r1"),
        (0xE600, "mov #0,r6"),                # r6 = 폭표 (0 = 못 찾음 → 24)
        ("bf", "NOTBL"),
        (0x5601, "mov.l @(4,r0),r6"),
        (0x362C, "add r2,r6"),
        ("NOTBL", (0xEC00, "mov #0,r12")),   # r12 = 모드(0 타일 / 1 W)
        (0x012A, "sts pr,r1"),
        (0x611D, "extu.w r1,r1"),
        ("MOVW", "WRET"),                     # mov.w LIT16,r0 = W 훅 복귀 하위 16비트
        (0x3100, "cmp/eq r0,r1"),
        ("bf", "TILE"),
        (0xEC01, "mov #1,r12"),               # W 모드: 전부 센다
        (0xE200, "mov #0,r2"),
        ("bra", "SUMSET"),
        (0xE47F, "mov #127,r4"),              # (지연)
        ("TILE", (0x62B3, "mov r11,r2")),
        (0x6023, "mov r2,r0"),
        (0x4008, "shll2 r0"),
        (0x320C, "add r0,r2"),                # r2 = 5t = 건너뛸 글자 수
        (0xE405, "mov #5,r4"),                # 이 행에 남은 칸
        ("SUMSET", (0xE300, "mov #0,r3")),    # 합
        ("LOOP", (0x6050, "mov.b @r5,r0")),
        (0x600C, "extu.b r0,r0"),
        (0x2008, "tst r0,r0"),
        ("bt", "DONE"),
        (0x8820, "cmp/eq #32,r0"),
        ("bt", "SKIP1"),
        (0x8809, "cmp/eq #9,r0"),
        ("bt", "SKIP1"),
        (0xE181, "mov #-127,r1"),             # 0x81
        (0x611C, "extu.b r1,r1"),
        (0x3012, "cmp/hs r1,r0"),
        ("bf", "ONE"),
        (0xE19F, "mov #-97,r1"),              # 0x9f
        (0x611C, "extu.b r1,r1"),
        (0x3016, "cmp/hi r1,r0"),
        ("bf", "TWO"),
        (0xE1E0, "mov #-32,r1"),              # 0xe0
        (0x611C, "extu.b r1,r1"),
        (0x3012, "cmp/hs r1,r0"),
        ("bf", "ONE"),
        (0xE1EF, "mov #-17,r1"),              # 0xef
        (0x611C, "extu.b r1,r1"),
        (0x3016, "cmp/hi r1,r0"),
        ("bt", "ONE"),
        ("TWO", (0x6703, "mov r0,r7")),       # lead
        (0x8451, "mov.b @(1,r5),r0"),         # trail
        (0x600C, "extu.b r0,r0"),
        (0x4718, "shll8 r7"),
        (0x207B, "or r7,r0"),                 # 코드
        (0x7502, "add #2,r5"),
        (0x2668, "tst r6,r6"),
        ("bt", "W24"),
        (0x6703, "mov r0,r7"),
        (0x4019, "shlr8 r0"),                 # page
        (0x006C, "mov.b @(r0,r6),r0"),
        (0xC880, "tst #128,r0"),
        ("bt", "SUB"),
        ("bra", "HAVE"),
        (0xC97F, "and #127,r0"),              # (지연)
        ("SUB", (0x7001, "add #1,r0")),
        (0x4018, "shll8 r0"),
        (0x306C, "add r6,r0"),
        (0x677C, "extu.b r7,r7"),
        (0x307C, "add r7,r0"),
        (0x6000, "mov.b @r0,r0"),
        ("bra", "HAVE"),
        (0x600C, "extu.b r0,r0"),             # (지연)
        ("W24", (0xE018, "mov #24,r0")),
        ("HAVE", (0x6103, "mov r0,r1")),      # r1 = 폭
        ("bra", "COUNT"),
        (S.nop(), "nop"),
        ("ONE", (0x7501, "add #1,r5")),
        (0xE10C, "mov #12,r1"),
        ("COUNT", (0x2228, "tst r2,r2")),
        ("bt", "ADD"),
        ("bra", "LOOP"),
        (0x72FF, "add #-1,r2"),               # (지연) 건너뛰기
        ("ADD", (0x331C, "add r1,r3")),
        (0x4410, "dt r4"),
        ("bf", "LOOP"),
        ("bra", "DONE"),
        (S.nop(), "nop"),
        ("SKIP1", ("bra", "LOOP")),
        (0x7501, "add #1,r5"),                # (지연)
        ("DONE", (0x4F22, "sts.l pr,@-r15")),
        ("MOVA", "ITOF"),
        (0x6202, "mov.l @r0,r2"),
        (0x320C, "add r0,r2"),                # itof
        (0x6433, "mov r3,r4"),                # 행 폭 / 전체 폭
        (0x420B, "jsr @r2"),
        (S.nop(), "nop"),                     # fr0 = float(폭)
        (0x2CC8, "tst r12,r12"),
        ("bt", "TILEFP"),
        (0x4F26, "lds.l @r15+,pr"),           # W 모드 에필로그: 원본 0x10001862~ 재현
        (0x7904, "add #4,r9"),
        (0xF90A, "fmov fr0,@r9"),             # W = 글자 폭 합
        (0x50F9, "mov.l @(36,r15),r0"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        ("TILEFP", (0xF20C, "fmov fr0,fr2")),
        (0xF40C, "fmov fr0,fr4"),
        ("MOVA", "FADD"),
        (0x6702, "mov.l @r0,r7"),
        (0x370C, "add r0,r7"),                # fadd
        (0x5601, "mov.l @(4,r0),r6"),
        (0x360C, "add r0,r6"),                # fmul
        (0x700C, "add #12,r0"),               # FADD 리터럴(+12) → INV128(+24)
        (0xF508, "fmov @r0,fr5"),             # 1/128
        (0x460B, "jsr @r6"),
        (S.nop(), "nop"),
        (0xFD0C, "fmov fr0,fr13"),            # u1 = 행 폭/128
        (0xF42C, "fmov fr2,fr4"),
        ("MOVA", "KUNIT"),
        (0xF508, "fmov @r0,fr5"),             # k
        (0x460B, "jsr @r6"),
        (S.nop(), "nop"),
        (0xF40C, "fmov fr0,fr4"),
        (0xE010, "mov #16,r0"),
        (0xF596, "fmov @(r0,r9),fr5"),        # 배율
        (0x460B, "jsr @r6"),
        (S.nop(), "nop"),                     # fr0 = 타일 폭(단위)
        (0xF50C, "fmov fr0,fr5"),
        (0xF4EC, "fmov fr14,fr4"),
        (0x470B, "jsr @r7"),
        (S.nop(), "nop"),                     # fr0 = x0 + 타일 폭
        (0x4F26, "lds.l @r15+,pr"),
        (0xE030, "mov #48,r0"),
        (0xFF57, "fmov fr5,@(r0,r15)"),       # 루프 끝 전진(0x10001b40)이 읽는 타일 폭
        (0xE034, "mov #52,r0"),
        (0xE442, "mov #66,r4"),
        (0x4400, "shll r4"),
        (0x34FC, "add r15,r4"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        (S.nop(), "nop"),                     # 리터럴 4정렬
    ]
    labels = ("NOTBL", "TILE", "SUMSET", "LOOP", "TWO", "SUB", "W24", "HAVE", "ONE", "COUNT", "ADD", "SKIP1", "DONE", "TILEFP")
    lits = {"VT3": 0, "TABLE": 4, "ITOF": 8, "FADD": 12, "FMUL": 16, "KUNIT": 20, "INV128": 24, "WRET": 28}
    code, lit_off = _resolve(body, labels, lits, stub_va)
    lit_va = stub_va + lit_off
    # ★ 썽크 거리는 **더하는 r0 의 값** 기준: ITOF 는 mova ITOF(=+8) 로 r0=lit+8, FADD/FMUL 은 mova FADD(=+12) 로
    #   r0=lit+12 에서 더한다. 묶음 머리(lit_va) 기준으로 넣었다가 썽크 +8/+12 로 뛰어 팝업에서 멈췄다(9/21).
    vals = [MENU_VT3 - MENU_VT, table_va - MENU_VT, MSEL_ITOF - (lit_va + 8), MSEL_FADD - (lit_va + 12),
            MSEL_FMUL - (lit_va + 12), K_UNIT, INV128]
    return (code + b"".join(struct.pack("<i" if v < 0x80000000 else "<I", v) for v in vals)
            + struct.pack("<HH", (MSEL_W_HOOK + 6) & 0xFFFF, 0x0009))   # WRET: W 훅 복귀(hook16 = 훅+6) 하위 16비트


def apply_menu(cfg, blob, table_va=None):
    """/TRF/MENUSELECT.DLL 에 HOOK7b 를 심는다. (바이트, 로그 한 줄)."""
    table_va = table_va or _LAST.get("table_va")
    if not table_va:
        raise ValueError("TRFSTRINGS 폭표 주소를 모른다 — apply() 뒤에 불러야 한다")
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    base = struct.unpack_from("<I", blob, pe + 24 + 28)[0]
    text_va = text_raw = None
    for i in range(nsec):
        h = pe + 24 + opt + 40 * i
        if blob[h:h + 8].rstrip(bytes(1)) == b".text":
            _vs, rva, _rs, raw = struct.unpack_from("<IIII", blob, h + 8)
            text_va, text_raw = base + rva, raw
    if text_va is None:
        raise ValueError(".text 없음")
    hoff = text_raw + (MSEL_HOOK - text_va)
    for i, want in enumerate(MSEL_HOOK_ORIG):
        got = struct.unpack_from("<H", blob, hoff + i * 2)[0]
        if got != want:
            raise ValueError(f"MENUSELECT {MSEL_HOOK + i*2:#x} = {got:#06x}, {want:#06x} 기대")
    for va, want, _new in MSEL_PAD:
        got = struct.unpack_from("<H", blob, text_raw + (va - text_va))[0]
        if got != want:
            raise ValueError(f"MENUSELECT {va:#x} = {got:#06x}, {want:#06x} 기대")
    out = bytearray(blob)
    s_va, s_off = _cave(out, text_raw, text_va)
    stub = stub_menu_tiles(s_va, table_va)
    if any(out[s_off:s_off + len(stub)]):
        raise ValueError(f"케이브 {s_va:#x} 가 비어 있지 않다")
    out[s_off:s_off + len(stub)] = stub
    _grow_virtual(out, ".text", (s_va - text_va) + len(stub))
    out[hoff:hoff + 16] = hook16(MSEL_HOOK, s_va, MSEL_RESUME)
    woff = text_raw + (MSEL_W_HOOK - text_va)
    for i, want in enumerate(MSEL_W_ORIG):
        got = struct.unpack_from("<H", blob, woff + i * 2)[0]
        if got != want:
            raise ValueError(f"MENUSELECT {MSEL_W_HOOK + i*2:#x} = {got:#06x}, {want:#06x} 기대")
    out[woff:woff + 16] = hook16(MSEL_W_HOOK, s_va, MSEL_W_RESUME)     # 같은 스텁, PR 로 W 모드
    for va, _want, new in MSEL_PAD:
        struct.pack_into("<H", out, text_raw + (va - text_va), new)
    # 되읽기: bsrf 목적지, 리터럴 거리
    lit = struct.unpack_from("<i", out, hoff + 10)[0]
    assert MSEL_HOOK + 6 + lit == s_va, (hex(lit), hex(s_va))
    lit = struct.unpack_from("<i", out, woff + 12)[0]
    assert MSEL_W_HOOK + 6 + lit == s_va, (hex(lit), hex(s_va))
    lit_va = s_va + len(stub) - 32
    v = struct.unpack_from("<iiiiiII", out, s_off + len(stub) - 32)
    assert v[0] == MENU_VT3 - MENU_VT and v[1] == table_va - MENU_VT, v[:2]
    assert (lit_va + 8 + v[2], lit_va + 12 + v[3], lit_va + 12 + v[4]) == (MSEL_ITOF, MSEL_FADD, MSEL_FMUL), v[2:5]
    note = (f"MENUSELECT 훅 {MSEL_HOOK:#x}/{MSEL_W_HOOK:#x}→{s_va:#x}({len(stub)}B, 표 {table_va:#x} = CTRFMenu vt {MENU_VT:#x}+거리)"
            f" · pad 끔 — 팝업 항목 타일 폭·W = 글자 폭 합")
    return bytes(out), note


# ───────────────────────────────────────────────────────────────────────────────
# ★ HOOK9 (josa, 2026-09-24) — 동적 조사. 앞 글자 받침을 보고 조사 셀을 고른다.
#
# 토크나이저(0x100076DC)의 **2바이트 글자 경로**에서, 코드가 조사 마커 셀이면 노드로 붙기 직전에
# 실제 조사 셀로 바꿔치기한다. 마커는 `widths.JOSA`(`{은는}` → 은/는)가 한 칸을 받아 둔 것이라
# 글자 수·타이밍·줄 폭이 조사 한 글자와 똑같다 — 빌드 쪽은 손댈 게 없다.
#
#   0x1000783E 의 6명령(12B)이 훅 자리다. 들어올 때 r4 = 코드(lead<<8|trail).
#       mov.l r4,@(8,r14)      ; 프레임 +8 = code   ← 여기서 r4 를 바꾸면 끝
#       mov #2,r2 / mov.l r2,@(12,r14)   ; len = 2
#       mov.l @(20,r15),r13    ; r13 = 노드 리스트 헤더
#       mov #0,r6 / mov.l @(4,r13),r5    ; r5 = tail
#
#   **직전 글자**는 헤더 `+4`(tail)가 그대로 가리킨다 — 리스트를 훑을 필요가 없다
#   (0x10007A6E 가 노드를 붙일 때마다 tail 을 갱신한다). 노드 `+8` 이 코드다.
#   받침 판정은 `코드 >= B1` 비교 하나(hangul.assign_josa 의 셀 정렬).
#
#   ★ r0 주의: 훅 바로 앞(0x10007838)에서 r0 에 노드 할당 함수(0x1000851C)를 싣고
#   훅 뒤(0x1000784A)에서 `jsr @r0` 한다. 그런데 `hook_code` 가 r0 로 점프하므로 스텁이
#   **r0 를 되살려야 한다.** 절대주소를 쓸 수 없으니 거리 리터럴로 되짚는다.
#   ★ 훅은 두 명령 앞(0x1000783A)에서 16B 로 잡는다 — 스텁이 `.pdata` 꼬리에 있어 64KB 를
#   넘으므로 32비트 거리를 쓰는 `hook16` 이 필요하고, 그만큼 자리가 더 든다. 늘어난 두 명령
#   (`shll8 r4` / `or r1,r4`)은 코드를 완성하는 부분이라 스텁 맨 앞에서 그대로 재현한다.
JOSA_HOOK = 0x1000783A
JOSA_HOOK_ORIG = (0x4418, 0x241B, 0x1E42, 0xE202, 0x1E23, 0x5DF5, 0xE600, 0x55D1)
JOSA_RESUME = 0x1000784A
JOSA_ALLOC = 0x1000851C           # 노드 할당 함수 — 훅이 r0 를 깨므로 스텁이 복원한다


def stub_josa(stub_va, alloc_va, mark, b1, cell_yes, cell_no):
    """조사 스텁. 리터럴 5개(할당함수 거리 · 마커 · B1 · 받침형 셀 · 무받침형 셀)."""
    S = sh4
    body = [
        (0x4418, "shll8 r4"),                            # 0  ↓ 훅이 가져온 원본 두 명령
        (0x241B, "or r1,r4"),                            # 1  r4 = lead<<8 | trail (r1 해제)
        ("MOVA", "LIT"),                                 # 2  mova LIT,r0
        (0x6102, "mov.l @r0,r1"),                        # 1  r1 = 할당함수 거리
        (0x310C, "add r0,r1"),                           # 2  r1 = 할당함수 주소
        (S.movl_disp_rm(4, 0, 2), "mov.l @(4,r0),r2"),   # 3  r2 = 마커 셀
        (S.cmp_eq(2, 4), "cmp/eq r2,r4"),                # 4  이번 글자가 마커인가
        ("bf", "DONE"),                                  # 5  아니면 그대로
        (S.movl_disp_rm(20, 15, 3), "mov.l @(20,r15),r3"),   # 6  r3 = 리스트 헤더
        (S.movl_disp_rm(4, 3, 3), "mov.l @(4,r3),r3"),   # 7  r3 = tail 노드(직전 글자)
        (0x2338, "tst r3,r3"),                           # 8
        ("bt", "NOBAT"),                                 # 9  앞 글자가 없으면 무받침형
        (S.movl_disp_rm(8, 3, 3), "mov.l @(8,r3),r3"),   # 10 r3 = 직전 코드
        (S.movl_disp_rm(8, 0, 2), "mov.l @(8,r0),r2"),   # 11 r2 = B1
        (0x3322, "cmp/hs r2,r3"),                        # 12 직전 >= B1 → 받침 있음
        ("bf", "NOBAT"),                                 # 13
        (S.movl_disp_rm(12, 0, 4), "mov.l @(12,r0),r4"), # 14 r4 = 받침형 셀
        ("bra", "DONE"),                                 # 15
        (S.nop(), "nop"),                                # 16
        ("NOBAT", (S.movl_disp_rm(16, 0, 4), "mov.l @(16,r0),r4")),   # 17 r4 = 무받침형 셀
        ("DONE", (0x6013, "mov r1,r0")),                 # 18 r0 복원(할당함수)
        (0x1E42, "mov.l r4,@(8,r14)"),                   # 19 ↓ 원본 6명령
        (0xE202, "mov #2,r2"),                           # 20
        (0x1E23, "mov.l r2,@(12,r14)"),                  # 21
        (0x5DF5, "mov.l @(20,r15),r13"),                 # 22
        (0xE600, "mov #0,r6"),                           # 23
        (0x55D1, "mov.l @(4,r13),r5"),                   # 24
        (S.rts(), "rts"),                                # 25
        (S.nop(), "nop"),                                # 26
        (S.nop(), "nop"),                                # 27 리터럴 4정렬
    ]
    code, lit_off = _resolve(body, ("NOBAT", "DONE"), {"LIT": 0}, stub_va)
    lit_va = stub_va + lit_off
    # LIT: +0 할당함수 거리 · +4 마커 · +8 B1 · +12 받침형 · +16 무받침형
    return code + struct.pack("<iIIII", alloc_va - lit_va, mark, b1, cell_yes, cell_no)


def josa_literals(cp):
    """codepage 에서 (마커, B1, 받침형 셀, 무받침형 셀) 목록. 마커마다 한 벌."""
    from kitae.build.widths import JOSA
    from kitae.build.hangul import josa_bounds
    b1, _b2 = josa_bounds(cp)
    out = []
    for mark, (yes, no) in sorted(JOSA.items()):
        for need in (mark, yes, no):
            if need not in cp:
                raise ValueError(f"조사 셀 {need!r} 이 codepage 에 없다")
        cell = lambda s: (cp[s][0] << 8) | cp[s][1]
        out.append((mark, cell(mark), b1, cell(yes), cell(no)))
    return out
