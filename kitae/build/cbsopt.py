# -*- coding: utf-8 -*-
"""**C.B.S(선택지 시간 제한) 게임 안 토글** — 시스템 설정 화면에 5번째 항목을 더한다.

`cbs_bypass`(ebgate.py)는 빌드할 때 EB 의 게이트를 지워 버린다. 이 패치는 EB 는 그대로 두고
게임 안 「시스템 설정」에서 플레이어가 켜고 끌 수 있게 한다. 기본값은 원작대로(수동).

## 값은 어디에 사나 — 메시지 테두리 워드의 비트 24

시스템 설정의 네 값은 두 곳에 산다.

  * `IGelConfig`(KITAHEGEL, 실행 중 값): 플래그 u16(`gel+0x296`, 1=고속 2=해설 건너뛰기)과
    메시지 테두리 워드 u32(`gel+0x298`) = `색 & 0xFFFFFF | (투명도+4)<<28`
  * `IGelFlexible`(이름→값 저장소, 세이브에 남는 쪽): 「ナレスキップ」「メッセージ速度」「メッセージボーダー」

테두리 워드는 **비트 24~27 이 비어 있고**, 모든 경로가 이 워드를 통째로 옮긴다 —
시스템 설정 확정(둘 다 씀), 타이틀(KITATITLE: Config→저장소), 세이브 로드(TRFVMSVIEW: 저장소→Config),
시스템 설정 열기(Config 에서 읽어 색은 `& 0xFFFFFF`, 투명도는 `>> 28` 로만 본다).
그래서 「제한 없음」을 비트 24 에 실으면 **세이브·로드·타이틀은 손대지 않아도** 값이 따라다닌다.
렌더러가 보는 알파 바이트는 1/255 달라질 뿐이다.

## KITAHEGEL — 게이트 옵코드 0x6E/0x6F

디스패치 표(`0x100131B4`, 옵코드로 바로 색인 — EB-FORMAT.md)의 두 칸을 `.text` 꼬리 스텁으로 돌린다.
스텁은 `r4 = gel` 에서 `@(0x298)` 의 비트 24 가 서 있으면 메모리의 대본에서 그 게이트를 0x00 다섯 개로
덮고 VM pc 를 되돌린다 — ebgate 가 디스크에서 하는 일을 실행 중에 그대로 한다(핸들러만 건너뛰면 안 된다:
`gel_stub` 주석). 아니면 원래 핸들러로 `jmp`. 표 칸은 절대주소지만
원래 재배치 항목이 있어 값만 바꾸면 된다. 스텁은 거리 리터럴만 쓴다(재배치 불필요).

## TRFSYSCONFIG — 5번째 행

객체 B(r8): +36..+48 하이라이트 스프라이트 4개, **+52 는 원래 비어 있다** → 5번째 스프라이트.
+64 커서, +68..+80 값 4개(+84 는 타이머라 5번째 값은 못 둔다 → 새 섹션의 상태 G).
글자는 (x, y, 문자열) 표 `0x100120A4` 를 한 번 그리고, 하이라이트를 `x - 1 + 값*간격` 으로 옮긴다.
행 간격 75 → 60 으로 줄여 5번째 행(라벨 y300, 선택지 y327)이 도움말 상자(y368) 위에 들어간다.
선택지 모양은 2행 「표준／고속」과 같게 해서 폭 50·간격 74·x336 을 그대로 쓴다.

  * 바이트: 커서 감기 3→4 두 곳, 하이라이트 밝기 루프 4→5
  * 훅(hook16, 새 섹션 `.kcbs` 1024B 로 bsrf):
      A 0x10001214 초기화 — 스프라이트 B+52 생성·크기·레이어 부착, 라벨·선택지 글자
      C 0x10001390 초기화 — G = (테두리 워드 >> 24) & 1
      E 0x100018E0 입력 — 커서 4 에서 좌우면 G 를 뒤집고 0x10001936 으로(값 배열은 안 건드린다)
      G 0x10001A8E 매 프레임 — 스프라이트 B+52 위치
      H 0x10001B54 확정 — 테두리 워드 r10 |= G << 24 (Config·저장소 둘 다 이 r10 을 쓴다)
      I 0x100016F0 소멸 — B+52 를 레이어에서 떼고 해제

훅이 덮은 16B 는 스텁이 그대로 다시 실행한다(덮은 자리에 pc 상대 명령이 없게 골랐다).
함수를 부르는 스텁은 `sts.l pr` 뒤에 16B 홈 영역을 잡는다 — 피호출자가 거기에 인자를 흘린다.
"""
import re
import struct

from kitae.build import sh4

SECTION = ".kcbs"
SECTION_SIZE = 1024             # 디스크 여유가 정확히 1024B (70656 → 71680)

LABEL = "C.B.S (커뮤니케이션 브레이크 시스템)"
CHOICES = "수동／자동"          # 0 = 수동(원작: 제한 시간 안에 끼어든다), 1 = 자동(게이트 없이 선택지)

# ── TRFSYSCONFIG ──────────────────────────────────────────────────────────────
SC_TABLE = 0x100120A4          # (x, y, 문자열) × 8
SC_YS = [60, 87, 120, 147, 180, 207, 240, 267]     # 원래 60 87 135 162 210 237 285 312
SC_YS_ORIG = [60, 87, 135, 162, 210, 237, 285, 312]
LX, LY, CX, CY = 72, 300, 336, 327
HL_W, HL_H, HL_STEP = 50, 26, 74
SC_POOL = 0x10001300           # 리터럴 풀: +0 0x80aaaaaa, +0x34 0x1000cc00, +0x3c 0x1000cd00, +0x40 생성 함수
SC_POOL_WANT = {0x00: 0x80AAAAAA, 0x34: 0x1000CC00, 0x3C: 0x1000CD00, 0x40: 0x10002A98}
SC_IIDP = 0x10001844           # = 0x10008500 (스프라이트 QueryInterface IID)
SC_BYTES = [(0x100018BA, 0xE303, 0xE304, "mov #3,r3 → #4 (위로 감기)"),
            (0x100018CE, 0xE303, 0xE304, "mov #3,r3 → #4 (아래로 감기)"),
            (0x10001978, 0xE104, 0xE105, "mov #4,r1 → #5 (하이라이트 루프)")]
HOOK_A, RES_A = 0x10001214, 0x10001224
HOOK_C, RES_C = 0x10001390, 0x100013A0
HOOK_E, RES_E = 0x100018E0, 0x100018F0
E_SKIP, E_RIGHT = 0x10001936, 0x1000190A
HOOK_G, RES_G = 0x10001A8E, 0x10001A9E
HOOK_H, RES_H = 0x10001B54, 0x10001B64
HOOK_I, RES_I = 0x100016F0, 0x10001700

# 훅이 덮는 원본 16B (다시 실행할 명령)
ORIG = {
    HOOK_A: ["mov.l @(20,r8),r5", "mov.l @r5,r1", "mov.l @(40,r1),r1", "jsr @r1",
             "mov r5,r4", "mov.l @(20,r8),r5", "mov.l @(16,r8),r6", "mov #108,r0"],
    HOOK_C: ["mov #-28,r3", "shld r3,r11", "mov #80,r4", "add r8,r4",
             "add #-4,r11", "mov.l r11,@r4", "mov #80,r0", "mov.l @(r0,r8),r5"],
    HOOK_E: ["mov r10,r0", "tst #4,r0", "bt 0x1000190a", "mov #-4,r5",
             "add r9,r5", "mov #64,r0", "mov.l @(r0,r5),r4", "add #68,r5"],
    HOOK_G: ["add #-1,r5", "mov.l @(4,r9),r6", "mul.l r2,r3", "mov.l @r7,r2",
             "sts macl,r1", "mov.l @(28,r2),r2", "jsr @r2", "add r1,r5"],
    HOOK_H: ["shll8 r10", "mov.l r3,@(20,r15)", "shlr8 r10", "or r4,r10",
             "mov #20,r4", "add r15,r4", "mov #20,r6", "add r15,r6"],
    HOOK_I: ["mov.l @(16,r15),r5", "mov.l @(24,r8),r6", "mov.l @r6,r2", "mov #112,r0",
             "mov.l @(r0,r2),r2", "jsr @r2", "mov r6,r4", "mov.l @(16,r15),r5"],
}

# ── KITAHEGEL ─────────────────────────────────────────────────────────────────
GEL_DISPATCH = 0x100131B4
GEL_GATES = {0x6E: 0x10003944, 0x6F: 0x100039C4}
GEL_BORDER = 0x298             # gel + : 메시지 테두리 워드 (IGelConfig+8 의 +0x290)


# ── 작은 인코더 — 문장 하나 → 워드. sh4.assemble 이 캡스톤으로 되읽어 확인한다 ─────
_R = r"r(\d+)"
_FORMS = [
    (rf"mov #(-?\d+),{_R}$", lambda i, n: 0xE000 | int(n) << 8 | (int(i) & 0xFF)),
    (rf"mov {_R},{_R}$", lambda m, n: 0x6003 | int(n) << 8 | int(m) << 4),
    (rf"mov\.l @\((\d+),{_R}\),{_R}$", lambda d, m, n: 0x5000 | int(n) << 8 | int(m) << 4 | int(d) // 4),
    (rf"mov\.l {_R},@\((\d+),{_R}\)$", lambda m, d, n: 0x1000 | int(n) << 8 | int(m) << 4 | int(d) // 4),
    (rf"mov\.l @{_R},{_R}$", lambda m, n: 0x6002 | int(n) << 8 | int(m) << 4),
    (rf"mov\.l {_R},@{_R}$", lambda m, n: 0x2002 | int(n) << 8 | int(m) << 4),
    (rf"mov\.l @\(r0,{_R}\),{_R}$", lambda m, n: 0x000E | int(n) << 8 | int(m) << 4),
    (rf"mov\.l @r15\+,{_R}$", lambda n: 0x60F6 | int(n) << 8),
    (r"sts\.l pr,@-r15$", lambda: 0x4F22),
    (r"lds\.l @r15\+,pr$", lambda: 0x4F26),
    (rf"sts pr,{_R}$", lambda n: 0x002A | int(n) << 8),
    (rf"lds {_R},pr$", lambda m: 0x402A | int(m) << 8),
    (rf"sts macl,{_R}$", lambda n: 0x001A | int(n) << 8),
    (rf"add #(-?\d+),{_R}$", lambda i, n: 0x7000 | int(n) << 8 | (int(i) & 0xFF)),
    (rf"add {_R},{_R}$", lambda m, n: 0x300C | int(n) << 8 | int(m) << 4),
    (rf"cmp/eq {_R},{_R}$", lambda m, n: 0x3000 | int(n) << 8 | int(m) << 4),
    (rf"tst {_R},{_R}$", lambda m, n: 0x2008 | int(n) << 8 | int(m) << 4),
    (rf"or {_R},{_R}$", lambda m, n: 0x200B | int(n) << 8 | int(m) << 4),
    (rf"xor {_R},{_R}$", lambda m, n: 0x200A | int(n) << 8 | int(m) << 4),
    (rf"mul\.l {_R},{_R}$", lambda m, n: 0x0007 | int(n) << 8 | int(m) << 4),
    (rf"shld {_R},{_R}$", lambda m, n: 0x400D | int(n) << 8 | int(m) << 4),
    (r"tst #(\d+),r0$", lambda i: 0xC800 | int(i)),
    (r"and #(\d+),r0$", lambda i: 0xC900 | int(i)),
    (rf"shll2 {_R}$", lambda n: 0x4008 | int(n) << 8),
    (rf"shll8 {_R}$", lambda n: 0x4018 | int(n) << 8),
    (rf"shll16 {_R}$", lambda n: 0x4028 | int(n) << 8),
    (rf"shlr8 {_R}$", lambda n: 0x4019 | int(n) << 8),
    (rf"shlr16 {_R}$", lambda n: 0x4029 | int(n) << 8),
    (rf"jsr @{_R}$", lambda n: 0x400B | int(n) << 8),
    (rf"jmp @{_R}$", lambda n: 0x402B | int(n) << 8),
    (rf"mov\.b r0,@\((\d+),{_R}\)$", lambda d, n: 0x8000 | int(n) << 4 | int(d)),
    (rf"mov\.b r0,@{_R}$", lambda n: 0x2000 | int(n) << 8),
    (r"rts$", lambda: 0x000B),
    (r"nop$", lambda: 0x0009),
]


def _a(text):
    for pat, fn in _FORMS:
        m = re.match(pat, text)
        if m:
            return (fn(*m.groups()), text)
    raise ValueError(f"인코더가 모르는 문장: {text}")


def _asm(lines):
    """문장 / ('bt'|'bf'|'bra', 라벨) / ('MOVA', 이름) / (라벨, 문장) → imestub._assemble 형식."""
    out = []
    for x in lines:
        if isinstance(x, str):
            out.append(_a(x))
        elif isinstance(x[1], str) and x[0] not in ("bt", "bf", "bra", "bsr", "MOVA"):
            out.append((x[0], _a(x[1])))           # (라벨, 문장)
        else:
            out.append(x)
    return out


def _replicate(hook, shift=0):
    """덮은 원본 명령. `bt` 처럼 pc 상대인 것은 빼고(호출 쪽이 따로 푼다), 스택 거리는 shift 만큼 민다."""
    out = []
    for t in ORIG[hook]:
        if t.startswith("bt "):
            continue
        if shift:
            t = re.sub(r"@\((\d+),r15\)", lambda m: f"@({int(m.group(1)) + shift},r15)", t)
        out.append(t)
    return out


def chars():
    """폰트에 넣어야 하는 글자."""
    from kitae.build import hangul
    return {c for c in LABEL + CHOICES if hangul.is_hangul(c)}


# ── PE 도우미 ─────────────────────────────────────────────────────────────────
def _secs(blob):
    from kitae.build.imestub import _headers
    return _headers(blob)


def _off(secs, va):
    for s in secs.values():
        if s["va"] <= va < s["va"] + max(s["vs"], s["rs"]):
            return s["raw"] + va - s["va"]
    raise ValueError(f"{va:#x} 가 어느 섹션에도 없다")


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _reloc_rvas(blob):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    rva, size = struct.unpack_from("<II", blob, pe + 24 + 96 + 5 * 8)
    secs = _secs(blob)
    base = struct.unpack_from("<I", blob, pe + 24 + 28)[0]
    o = _off(secs, base + rva)
    end = o + size
    out = set()
    while o < end:
        page, n = struct.unpack_from("<II", blob, o)
        if n == 0:
            break
        for i in range((n - 8) // 2):
            e = _u16(blob, o + 8 + 2 * i)
            if e >> 12 == 3:
                out.add(page + (e & 0xFFF))
        o += n
    return out, base


# ── KITAHEGEL ─────────────────────────────────────────────────────────────────
def gel_stub():
    """옵코드 하나의 스텁 본문. 'H' 리터럴 = (원래 핸들러 − 리터럴 주소).

    「자동」이면 ebgate 와 **똑같이** 만든다 — 메모리에 올라온 대본의 이 게이트 5바이트를 0x00 으로
    덮고 VM pc 를 게이트 머리로 되돌린다. VM 은 0x00 을 표가 아니라 0x1000612C 로 따로 처리하므로
    (대기·동기화) 핸들러만 건너뛰어서는 원작과 똑같이 시간 제한이 걸린다(10/5 인게임 확인).
    VM = @(28,gel), 오퍼랜드 포인터 = @(8,VM) = 옵코드+1, pc = @(4,VM)."""
    return _asm([
        "mov #83,r0", "shll2 r0", "add r0,r0",          # r0 = 664 = 0x298
        "mov.l @(r0,r4),r0",                            # 테두리 워드
        "shlr16 r0", "shlr8 r0", "tst #1,r0",
        ("bt", "ORIG"),
        "mov.l @(28,r4),r1",                            # VM
        "mov.l @(8,r1),r2", "add #-1,r2",               # 게이트 머리
        "mov #0,r0",
        "mov.b r0,@r2", "mov.b r0,@(1,r2)", "mov.b r0,@(2,r2)",
        "mov.b r0,@(3,r2)", "mov.b r0,@(4,r2)",
        "mov.l r2,@(4,r1)",                             # pc ← 게이트 머리 → 0x00 다섯 번
        "rts", "nop",
        ("ORIG", "nop"),
        ("MOVA", "H"),
        "mov.l @r0,r1", "add r0,r1",
        "jmp @r1", "nop",
    ])


def apply_gel(blob):
    """KITAHEGEL: 게이트 옵코드 두 칸을 .text 꼬리 스텁으로. 파일 크기 그대로."""
    from kitae.build.imestub import _assemble
    out = bytearray(blob)
    secs = _secs(out)
    relocs, base = _reloc_rvas(out)
    text = secs[".text"]
    va = (text["va"] + text["vs"] + 3) & ~3
    placed = []
    for op, handler in GEL_GATES.items():
        slot = GEL_DISPATCH + 4 * op
        so = _off(secs, slot)
        cur = struct.unpack_from("<I", out, so)[0]
        if cur != handler:
            raise ValueError(f"옵코드 {op:#x} 칸이 {cur:#x} — {handler:#x} 가 아니다(다른 빌드거나 이미 패치됨)")
        if slot - base not in relocs:
            raise ValueError(f"옵코드 {op:#x} 칸에 재배치 항목이 없다 — 절대주소를 바꿀 수 없다")
        code, lit_off, _L = _assemble(gel_stub(), va, {"H": 0})
        stub = code + struct.pack("<i", handler - (va + lit_off))
        o = _off(secs, va) if va < text["va"] + text["rs"] else None
        if o is None or va + len(stub) > text["va"] + text["rs"]:
            raise ValueError(".text 꼬리에 자리가 없다")
        if any(out[o:o + len(stub)]):
            raise ValueError(f".text 꼬리 {va:#x} 가 비어 있지 않다")
        out[o:o + len(stub)] = stub
        struct.pack_into("<I", out, so, va)
        placed.append((op, va))
        va = (va + len(stub) + 3) & ~3
    struct.pack_into("<I", out, text["hdr"] + 8, va - text["va"])     # VirtualSize
    note = "C.B.S 토글(KITAHEGEL): " + ", ".join(f"옵코드 {op:#x}→{v:#x}" for op, v in placed)
    return bytes(out), note


# ── TRFSYSCONFIG ──────────────────────────────────────────────────────────────
LITS = ["POOL", "IIDP", "CX", "CY", "LX", "LY", "ESKIP", "ERIGHT", "G"]


def _lit(name):
    return 4 * LITS.index(name)


def sc_body():
    L = _lit
    body = []
    # ── A: 초기화 — 스프라이트·글자
    body += [("A", "sts.l pr,@-r15"), "add #-20,r15",
             ("MOVA", "LIT"), "mov r0,r3",
             f"mov.l @({L('POOL')},r3),r1", "add r3,r1",          # r1 = 풀
             "mov r1,r2", "add #48,r2",
             "mov.l @(12,r2),r4", "mov #0,r5", "mov.l @(4,r2),r6",
             "mov r8,r7", "add #52,r7",
             "mov.l @(16,r2),r0", "jsr @r0", "nop",              # 생성 → B+52
             "mov.l @(52,r8),r4", "tst r4,r4", ("bt", "A_TEXT"),
             ("MOVA", "LIT"), f"mov.l @({L('POOL')},r0),r1", "add r0,r1", "mov.l @r1,r7",
             f"mov #{HL_W},r5", f"mov #{HL_H},r6",
             "mov.l @r4,r1", "mov.l @(12,r1),r1", "jsr @r1", "nop",   # 크기·색
             "mov.l @(16,r8),r4", "mov.l @(52,r8),r5", "mov.l @r4,r1",
             "mov #108,r0", "mov.l @(r0,r1),r1", "jsr @r1", "nop",   # 레이어에 붙이기
             ("A_TEXT", "mov #-1,r1"), "mov.l r1,@(16,r15)",
             "mov.l @(20,r8),r4", ("MOVA", "S_LABEL"), "mov r0,r7",
             ("MOVA", "LIT"), f"mov.l @({L('LX')},r0),r5", f"mov.l @({L('LY')},r0),r6",
             "mov.l @r4,r1", "mov.l @(20,r1),r1", "jsr @r1", "nop",
             "mov #-1,r1", "mov.l r1,@(16,r15)",
             "mov.l @(20,r8),r4", ("MOVA", "S_CHO"), "mov r0,r7",
             ("MOVA", "LIT"), f"mov.l @({L('CX')},r0),r5", f"mov.l @({L('CY')},r0),r6",
             "mov.l @r4,r1", "mov.l @(20,r1),r1", "jsr @r1", "nop"]
    body += _replicate(HOOK_A)              # 안의 jsr 도 홈 영역을 쓰니 프레임은 그 뒤에 푼다
    body += ["add #20,r15", "lds.l @r15+,pr", "rts", "nop"]
    # ── C: 초기화 — G = (테두리 >> 24) & 1
    body += [("C", "mov r11,r0"), "shlr16 r0", "shlr8 r0", "and #1,r0", "mov r0,r1",
             ("MOVA", "G"), "mov.l r1,@r0"]
    body += _replicate(HOOK_C)
    body += ["rts", "nop"]
    # ── E: 좌우 입력
    body += [("E", "mov r10,r0"), "tst #12,r0", ("bt", "E_NORMAL"),
             "mov.l @r13,r1", "mov #4,r2", "cmp/eq r1,r2", ("bf", "E_NORMAL"),
             ("MOVA", "G"), "mov.l @r0,r1", "mov #1,r2", "xor r2,r1", "mov.l r1,@r0",
             "sts pr,r1", ("MOVA", "LIT"), f"mov.l @({L('ESKIP')},r0),r2", "add r2,r1",
             "lds r1,pr", "rts", "nop",
             ("E_NORMAL", "mov r10,r0"), "tst #4,r0", ("bf", "E_LEFT"),
             "sts pr,r1", ("MOVA", "LIT"), f"mov.l @({L('ERIGHT')},r0),r2", "add r2,r1",
             "lds r1,pr", "rts", "nop",
             ("E_LEFT", "mov #-4,r5")]
    body += _replicate(HOOK_E)[3:]          # add r9,r5 / mov #64,r0 / mov.l @(r0,r5),r4 / add #68,r5
    body += ["rts", "nop"]
    # ── G: 매 프레임 — 스프라이트 B+52 위치
    body += [("G", "sts.l pr,@-r15"), "add #-16,r15"]
    body += _replicate(HOOK_G)
    body += ["mov.l @(52,r8),r4", "tst r4,r4", ("bt", "G_DONE"),
             ("MOVA", "G"), "mov.l @r0,r1", f"mov #{HL_STEP},r5", "mul.l r1,r5", "sts macl,r5",
             ("MOVA", "LIT"), f"mov.l @({L('CX')},r0),r1", "add #-1,r1", "add r1,r5",
             f"mov.l @({L('CY')},r0),r6",
             "mov.l @r4,r1", "mov.l @(28,r1),r1", "jsr @r1", "nop",
             ("G_DONE", "add #16,r15"), "lds.l @r15+,pr", "rts", "nop"]
    # ── H: 확정 — r10 |= G << 24
    body += [("H", _replicate(HOOK_H)[0])] + _replicate(HOOK_H)[1:]
    body += [("MOVA", "G"), "mov.l @r0,r1", "shll16 r1", "shll8 r1", "or r1,r10", "rts", "nop"]
    # ── I: 소멸 — B+52 떼고 해제. 원래 프레임의 @(16,r15) 는 여기서 @(44,r15)
    body += [("I", "sts.l pr,@-r15"), "add #-24,r15"]
    body += _replicate(HOOK_I, shift=28)[:-1]
    body += ["mov.l @(52,r8),r4", "tst r4,r4", ("bt", "I_DONE"),
             "mov #0,r1", "mov.l r1,@(16,r15)",
             ("MOVA", "LIT"), f"mov.l @({L('IIDP')},r0),r1", "add r0,r1", "mov.l @r1,r5",
             "mov r15,r6", "add #16,r6", "mov.l @r4,r1", "mov.l @r1,r1", "jsr @r1", "nop",  # QI
             "mov.l @(16,r15),r5", "mov.l @(16,r8),r4", "mov.l @r4,r1",
             "mov #112,r0", "mov.l @(r0,r1),r1", "jsr @r1", "nop",                         # 떼기
             "mov.l @(16,r15),r4", "tst r4,r4", ("bt", "I_REL"),
             "mov.l @r4,r1", "mov.l @(8,r1),r1", "jsr @r1", "nop",
             ("I_REL", "mov.l @(52,r8),r4"), "mov.l @r4,r1", "mov.l @(8,r1),r1", "jsr @r1", "nop",
             "mov #0,r1", "mov.l r1,@(52,r8)",
             ("I_DONE", _replicate(HOOK_I, shift=28)[-1]),
             "add #24,r15", "lds.l @r15+,pr", "rts", "nop"]
    return _asm(body)


def apply_sysconfig(blob, encode):
    """TRFSYSCONFIG(UI 패치 뒤)에 5번째 행을 넣는다. 파일이 1024B 커진다."""
    from kitae.build import pesection
    from kitae.build.imestub import _assemble
    from kitae.build.vwstub import hook16
    out = bytearray(blob)
    secs = _secs(out)
    if SECTION in secs:
        raise ValueError("이미 C.B.S 토글이 들어 있다")

    # 원본 확인 — 훅 자리 명령, 바이트 패치 자리, 리터럴 풀, 표의 y
    text = secs[".text"]
    for hook, want in ORIG.items():
        got = [t for _a_, t in sh4.disasm(
            [_u16(out, _off(secs, hook) + 2 * i) for i in range(8)], hook)]
        if [g.replace(" ", "") for g in got] != [w.replace(" ", "") for w in want]:
            raise ValueError(f"훅 {hook:#x} 자리가 원본이 아니다: {got}")
    for va, old, new, _why in SC_BYTES:
        if _u16(out, _off(secs, va)) != old:
            raise ValueError(f"{va:#x} 가 {old:#06x} 가 아니다")
    for k, v in SC_POOL_WANT.items():
        if struct.unpack_from("<I", out, _off(secs, SC_POOL + k))[0] != v:
            raise ValueError(f"리터럴 풀 {SC_POOL + k:#x} 가 {v:#x} 가 아니다")
    ys = [struct.unpack_from("<I", out, _off(secs, SC_TABLE + 12 * i + 4))[0] for i in range(8)]
    if ys != SC_YS_ORIG:
        raise ValueError(f"표의 y 가 원본이 아니다: {ys}")

    # 새 섹션 (코드·실행·읽기·쓰기 — G 를 여기 둔다)
    grown, new_raw, _ = pesection.add(bytes(out), SECTION, SECTION_SIZE, 0xE0000020)
    out = bytearray(grown)
    secs = _secs(out)
    m_va = secs[SECTION]["va"]

    lab = encode(LABEL) + b"\0"
    cho = encode(CHOICES) + b"\0"
    lab += b"\0" * (-len(lab) % 4)
    nlit = 4 * len(LITS)
    lits = {"LIT": 0, "G": _lit("G"), "S_LABEL": nlit, "S_CHO": nlit + len(lab)}
    code, lit_off, labels = _assemble(sc_body(), m_va, lits)
    lit_va = m_va + lit_off

    def hook_ret(hook):
        return hook + 6                  # hook16 의 bsrf 복귀점

    vals = {"POOL": SC_POOL - lit_va, "IIDP": SC_IIDP - lit_va,
            "CX": CX, "CY": CY, "LX": LX, "LY": LY,
            "ESKIP": E_SKIP - hook_ret(HOOK_E), "ERIGHT": E_RIGHT - hook_ret(HOOK_E), "G": 0}
    litblob = b"".join(struct.pack("<i", vals[n]) for n in LITS) + lab + cho
    body = code + litblob
    if len(body) > SECTION_SIZE:
        raise ValueError(f"스텁 {len(body)}B 가 섹션 {SECTION_SIZE}B 를 넘는다")
    out[new_raw:new_raw + len(body)] = body

    for hook, res, lab_ in ((HOOK_A, RES_A, "A"), (HOOK_C, RES_C, "C"), (HOOK_E, RES_E, "E"),
                            (HOOK_G, RES_G, "G"), (HOOK_H, RES_H, "H"), (HOOK_I, RES_I, "I")):
        o = _off(secs, hook)
        out[o:o + 16] = hook16(hook, m_va + labels[lab_] * 2, res)
    for va, _old, new, _why in SC_BYTES:
        struct.pack_into("<H", out, _off(secs, va), new)
    for i, y in enumerate(SC_YS):
        struct.pack_into("<I", out, _off(secs, SC_TABLE + 12 * i + 4), y)
    note = f"C.B.S 토글(TRFSYSCONFIG): 5번째 행 · 훅 6곳 → {SECTION} {m_va:#x} ({len(body)}B)"
    return bytes(out), note
