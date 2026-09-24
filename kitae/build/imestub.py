# -*- coding: utf-8 -*-
"""한글 입력기 2단계 — TRFNAMEIN PutChar(0x10001000) 훅 + 두벌식 오토마타 SH4 스텁.

근거·설계: docs/IME.md. 규칙은 kitae/build/ime.py 의 파이썬 참조(`Composer`)와 같다 —
바꿀 땐 둘을 같이 바꾸고 `tools/ime_emu_test.py`(SH4 미니 에뮬레이터)로 대조한다.

## 훅

`0x10001010` 16B(`hook16`, 복귀 `0x10001020`). 프롤로그가 r8~r11·pr 을 밀고 `r15 -= 16`
했으므로 진입 시 r8=this, r5=code, r11=advance, 호출자 PR 은 @(16,r15). 스텁이 pr·r12~r14 를
더 밀면 @(32,r15).

## 흐름

  1. 호출자 PR 이 DOPUT 의 복귀점 → 재귀 호출 → 원본 8명령을 재현하고 rts (ORIG). ★ r4 = this 도
     되살린다 — 원본 본문이 r4 로 0x10003afc 를 부르는데 재귀 안에서 그 함수가 r4 를 덮는다
  2. code 가 자모(첫 셀 base 부터 40칸) → 오토마타(JAMO)
  3. 아니면 X 삭제(PR 0x10002c26/0x10002c3e)이고 이 칸을 조합 중 → 자모 하나 빼기(XDEL)
  4. 그 밖에는 상태를 버리고 원본(RESET_ORIG) — A 로 고른 빈칸·한자·가나, 포커스 이동

글자 쓰기는 PutChar 를 **재귀로** 다시 불러 원본 그대로 처리한다(커서 전진·클램프·0x10003afc·
0x100018dc 포함). 재귀는 1 에서 걸러진다. 오토마타가 처리한 뒤엔 에필로그 `0x10001050` 으로
가는 대신 r5 = 지금 칸·r11 = 0 으로 ORIG 를 지나 원본이 같은 값을 다시 쓰게 한다(DONE) — 반환값은 세 호출자 모두 안 쓴다.

## 자리

  * 본체(≈490B): 새 PE 섹션 `.kime` 512B — TRFNAMEIN 은 디스크 여유가 512B 뿐이다(`pesection.add`,
    `.reloc` 앞 VA). `.text` 꼬리 434B 엔 안 들어간다.
  * 헬퍼(SCAN·DOPUT·COMMIT·GLYPH) + 표 거리 슬롯: `.rdata` 블록 176 꼬리 [32,256)
  * 표(CHO2JONG·REST·SPLITCHO·UNDIPH·DJ·DIPH): `.rdata` 블록 175 꼬리
  * 상태 4B `{cur, cho, jung, jong}`: `.data` 꼬리 끝 `0x100161fc`. **cur 는 `~cursor`** 라 로더가
    채우는 0 이 곧 "쉼"이다(cursor 를 그대로 두면 0 이 "0번 칸에서 `가` 조합 중"으로 읽힌다 — 에뮬레이터
    시험에서 첫 키가 `각` 이 됐다). VirtualSize 를 RawSize 로 늘려 파일의 0 이 확실히 올라가게 한다.
  * 음절→셀 표: `.rdata` 블록 0~174 (`ime.patch` 가 심는다)

## 레지스터

  r8 this · r9 &state · r10 자모 색인(모음 경로에선 −19 한 모음 색인) · r11 헬퍼 베이스 H
  (원본 advance 는 RESET_ORIG 까지만 필요; XDEL 의 되돌림은 X 가 늘 0 이라 0 을 넣는다)
  r12 PR 거리 → 도깨비불 때 옮겨 갈 초성 · r13 &cursor(this+0x118) · r14 리터럴 베이스
  상태는 r1=초성 r2=중성 r3=종성(없음 = −1, 종성 없음 = 0)으로 들고 다니다 STORE 에서 저장.
  헬퍼 호출은 `mov r11,r7 / add #off,r7 / jsr @r7` — 섹션이 달라 bsr 이 못 닿는다.

## 없는 음절(표가 0)

받침을 붙인 결과가 표에 없으면(완성형 밖 — 「철」+ㅅ 의 「첧」처럼 겹받침 중간 상태가 흔하다) 지금
칸을 확정하고 그 자음을 새 초성으로 삼는다(FAIL → C_COMMIT). 무받침·ㄹ받침은 전부 굽기 때문에 모음
경로는 실패하지 않는다. 도깨비불로 새로 생기는 앞 음절이 없으면 지금 칸을 그대로 확정하고 모음만
따로 쓴다(V_SPLIT → V_CA). XDEL 에서 실패하면 키를 무시한다. 파이썬 참조는 `Composer(baked=...)`.
"""
import struct

from kitae.build import sh4
from kitae.build.ime import (JAMO_CHO, JAMO_JUNG, JONG, CHO2JONG, DOUBLE_JONG, SPLIT_JONG,
                             DIPH, UNDIPH, RDATA_VA, TABLE_OFF, jamo_base, _sections)

PUTCHAR = 0x10001000
HOOK = 0x10001010
RESUME = 0x10001020            # add #104,r0 — ORIG 가 r0(this+0xF0)·r2·r9·r10 을 원본대로 세우고 돌아가는 자리
EPILOGUE = 0x10001050          # mov #0,r0 / add #16,r15 / pop (참고 — DONE 은 ORIG 를 거친다)
X_PR = (0x10002C26, 0x10002C3E)   # X 삭제 호출자의 복귀 주소(PutChar(0x8140, 0))
A_PR = 0x10001358                 # A 커밋(참고·시험용)
STATE_VA = 0x100161FC          # .data 꼬리 끝 4B
TABLE_BLOCK, HELPER_BLOCK = 175, 176
SECTION = ".kime"
SECTION_SIZE = 512
# 훅이 덮는 원본 16B — 다른 빌드 방지
ORIG16 = bytes.fromhex("2a90836a0c3a3ce0ac3028e90c399262")

# 리터럴 풀(r14) 배치
L_STATE, L_JBASE, L_RET, L_X1, L_X2, L_PUT, L_H, L_TBL = range(0, 32, 4)
# 헬퍼 블록(H) 표 거리 슬롯
S_CHO2JONG, S_REST, S_SPLITCHO, S_UNDIPH, S_DJ, S_DIPH = range(0, 24, 4)
SLOTS = 24


def tables():
    """표 바이트와 각 표의 오프셋 dict."""
    rest = [0] * 28
    moved = [0] * 28
    for j, (r, m) in SPLIT_JONG.items():
        rest[j], moved[j] = r, m
    undiph = [UNDIPH.get(v, 0xFF) for v in range(21)]

    def pairs(d):
        out = b""
        for (a, b), r in sorted(d.items()):
            out += struct.pack("<HH", (a << 5) | b, r)
        return out + struct.pack("<HH", 0, 0)          # 끝 = 키 0, 값 0

    parts = [("CHO2JONG", bytes(CHO2JONG)), ("REST", bytes(rest)), ("SPLITCHO", bytes(moved)),
             ("UNDIPH", bytes(undiph)), ("DJ", pairs(DOUBLE_JONG)), ("DIPH", pairs(DIPH))]
    blob, offs = b"", {}
    for name, b in parts:
        if name in ("DJ", "DIPH") and len(blob) % 2:
            blob += b"\0"
        offs[name] = len(blob)
        blob += b
    return blob, offs


def _label_offsets(body):
    """라벨 → 명령 인덱스(바이트 오프셋은 ×2)."""
    out, i = {}, 0
    for ent in body:
        if isinstance(ent[0], str) and ent[0] not in ("MOVA", "bt", "bf", "bra", "bsr"):
            out[ent[0]] = i
        i += 1
    return out


def _assemble(body, va, lits=None):
    """('bt'|'bf'|'bra'|'bsr', 라벨) · ('MOVA', 리터럴) · (라벨, 명령) 을 풀어 조립하고,
    캡스톤으로 되읽어 **모든 분기가 의도한 라벨 주소로 가는지** 하나씩 대조한다.
    (sh4.bt 는 거리를 8비트로 잘라 버려 넘치면 조용히 엉뚱한 곳으로 간다.)"""
    S = sh4
    L = _label_offsets(body)
    prog, want = [], []                 # want[i] = 분기 목적지 VA (없으면 None)
    for ent in body:
        if isinstance(ent[0], str) and ent[0] in L:
            ent = ent[1]
        prog.append(ent)
    if len(prog) % 2:
        prog.append((S.nop(), "nop"))
    lit_off = len(prog) * 2
    final = []
    for i, ent in enumerate(prog):
        tgt = None
        if isinstance(ent[0], str):
            kind = ent[0]
            if kind == "MOVA":
                d = lit_off + (lits or {})[ent[1]] - ((i * 2 + 4) & ~3)
                final.append((S.mova(d), None))
            else:
                disp = L[ent[1]] - (i + 2)
                if kind in ("bt", "bf"):
                    assert -128 <= disp <= 127, (kind, ent[1], disp)
                else:
                    assert -2048 <= disp <= 2047, (kind, ent[1], disp)
                final.append(({"bt": S.bt, "bf": S.bf, "bra": S.bra, "bsr": S.bsr}[kind](disp), None))
                tgt = va + L[ent[1]] * 2
        else:
            final.append(ent)
        want.append(tgt)
    code = S.assemble(final, va)
    for (a, t), tgt in zip(S.disasm([w for w, _ in final], va), want):
        if tgt is not None and int(t.split()[-1], 16) != tgt:
            raise ValueError(f"{a:#x} {t} → {tgt:#x} 이어야 한다")
    return code, lit_off, L


def helper_body():
    """헬퍼 블록 코드(H+SLOTS 부터). SCAN·DOPUT·COMMIT·COMMIT_G·GLYPH — 본체가 `add #off,r7` 로
    부르므로 모두 H 에서 128B 안에 있어야 한다(`helper_offsets` 가 검사)."""
    S = sh4
    M = S.movl_disp_rm
    return [
        # SCAN(r0=키, r4=쌍 표) → r0 = 값(없으면 0). r6·r7 사용. 끝 = 키 0·값 0.
        ("SCAN", (0x6645, "mov.w @r4+,r6")),
        (0x666D, "extu.w r6,r6"),
        (0x6745, "mov.w @r4+,r7"),
        (0x677D, "extu.w r7,r7"),
        (0x3060, "cmp/eq r6,r0"),
        ("bt", "S_FOUND"),
        (0x2668, "tst r6,r6"),
        ("bf", "SCAN"),
        ("S_FOUND", (0x6073, "mov r7,r0")),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        # DOPUT(r5=셀, r6=advance): PutChar 재귀 — 복귀점(jsr 뒤 +4)이 재귀 판별 기준
        ("DOPUT", (0x4F22, "sts.l pr,@-r15")),
        (M(L_PUT, 14, 0), f"mov.l @({L_PUT},r14),r0"),
        (0x30EC, "add r14,r0"),
        (0x400B, "jsr @r0"),
        (0x6483, "mov r8,r4"),
        ("DOPUT_RET", (0x4F26, "lds.l @r15+,pr")),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        # COMMIT(r1,r2,r3): 지금 칸을 확정(advance) 하고 상태 커서 = 새 커서
        ("COMMIT", (0x4F22, "sts.l pr,@-r15")),
        ("bsr", "GLYPH"),
        (S.nop(), "nop"),
        ("bra", "CG_BODY"),
        (S.nop(), "nop"),
        # COMMIT_G(r5=셀): 셀을 이미 구했을 때
        ("COMMIT_G", (0x4F22, "sts.l pr,@-r15")),
        ("CG_BODY", (0xE601, "mov #1,r6")),
        ("bsr", "DOPUT"),
        (S.nop(), "nop"),
        (0x60D2, "mov.l @r13,r0"),
        (0x6007, "not r0,r0"),
        (0x2900, "mov.b r0,@r9"),                      # 상태 커서 = ~새 커서
        (0x4F26, "lds.l @r15+,pr"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        # GLYPH(r1=초성, r2=중성, r3=종성) → r5 = 셀(없으면 0). r0·r4·r6 사용, r1~r3 보존.
        ("GLYPH", (0x6023, "mov r2,r0")),
        (0x88FF, "cmp/eq #-1,r0"),
        ("bf", "G_SYL"),
        (M(L_JBASE, 14, 5), f"mov.l @({L_JBASE},r14),r5"),
        (0x351C, "add r1,r5"),                     # 초성 자모 셀 = base + cho
        (S.rts(), "rts"),
        (S.nop(), "nop"),
        ("G_SYL", (0x6413, "mov r1,r4")),
        (0x4408, "shll2 r4"),
        (0x341C, "add r1,r4"),
        (0x4408, "shll2 r4"),
        (0x341C, "add r1,r4"),                     # r4 = 21·cho
        (0x342C, "add r2,r4"),                     # + jung
        (0x6643, "mov r4,r6"),
        (0x4608, "shll2 r6"),                      # ×4
        (0x4408, "shll2 r4"),
        (0x4408, "shll2 r4"),
        (0x4400, "shll r4"),                       # ×32
        (0x3468, "sub r6,r4"),                     # ×28
        (0x343C, "add r3,r4"),                     # + jong = 음절 번호
        (0x6043, "mov r4,r0"),
        (0xC93F, "and #63,r0"),
        (0x4000, "shll r0"),
        (0x6603, "mov r0,r6"),                     # (idx&63)·2
        (0xE0C0, "mov #-64,r0"),
        (0x2049, "and r4,r0"),
        (0x4008, "shll2 r0"),                      # (idx>>6)·256
        (0x306C, "add r6,r0"),
        (M(L_TBL, 14, 6), f"mov.l @({L_TBL},r14),r6"),
        (0x36EC, "add r14,r6"),                    # .rdata + 32
        (0x056D, "mov.w @(r0,r6),r5"),
        (0x655D, "extu.w r5,r5"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ]


def helper_offsets():
    """H 기준 바이트 오프셋 {SCAN, DOPUT, COMMIT, COMMIT_G, GLYPH, DOPUT_RET}."""
    L = _label_offsets(helper_body())
    out = {k: SLOTS + v * 2 for k, v in L.items() if k in ("SCAN", "DOPUT", "COMMIT", "COMMIT_G", "GLYPH", "DOPUT_RET")}
    for k in ("SCAN", "DOPUT", "COMMIT", "COMMIT_G", "GLYPH"):
        assert out[k] <= 127, (k, out[k])
    return out


def main_body(h):
    """본체. `h` = helper_offsets()."""
    S = sh4
    M = S.movl_disp_rm

    def call(name, slot=None):                         # 헬퍼 호출 4명령(지연 슬롯에 하나 실을 수 있다)
        return [(0x67B3, "mov r11,r7"), (0x7700 | h[name], f"add #{h[name]},r7"),
                (0x470B, "jsr @r7"), slot or (S.nop(), "nop")]

    load_state = [(0x8491, "mov.b @(1,r9),r0"), (0x6103, "mov r0,r1"),
                  (0x8492, "mov.b @(2,r9),r0"), (0x6203, "mov r0,r2"),
                  (0x8493, "mov.b @(3,r9),r0"), (0x6303, "mov r0,r3")]
    body = [
        (0x4F22, "sts.l pr,@-r15"),
        (S.movl_push(12), "mov.l r12,@-r15"),
        (S.movl_push(13), "mov.l r13,@-r15"),
        (S.movl_push(14), "mov.l r14,@-r15"),
        ("MOVA", "LIT"),
        (0x6E03, "mov r0,r14"),
        (M(32, 15, 12), "mov.l @(32,r15),r12"),
        (0x3CE8, "sub r14,r12"),                        # r12 = 호출자 PR − 리터럴 베이스
        (M(L_RET, 14, 1), f"mov.l @({L_RET},r14),r1"),
        (0x3C10, "cmp/eq r1,r12"),
        ("bt", "ORIG"),                                 # 재귀(DOPUT) → 원본
        (0x69E2, "mov.l @r14,r9"),
        (0x39EC, "add r14,r9"),                         # r9 = &state
        (0xED46, "mov #70,r13"),
        (0x4D08, "shll2 r13"),
        (0x3D8C, "add r8,r13"),                         # r13 = &cursor (this+0x118)
        (M(L_JBASE, 14, 0), f"mov.l @({L_JBASE},r14),r0"),
        (0x6A53, "mov r5,r10"),
        (0x3A08, "sub r0,r10"),                         # r10 = code − 자모 첫 셀
        (0xE028, "mov #40,r0"),
        (0x3A02, "cmp/hs r0,r10"),
        ("bf", "JAMO"),
        (M(L_X1, 14, 1), f"mov.l @({L_X1},r14),r1"),
        (0x3C10, "cmp/eq r1,r12"),
        ("bt", "XDEL"),
        (M(L_X2, 14, 1), f"mov.l @({L_X2},r14),r1"),
        (0x3C10, "cmp/eq r1,r12"),
        ("bt", "XDEL"),
        ("RESET_ORIG", (0xE000, "mov #0,r0")),
        (0x2900, "mov.b r0,@r9"),                       # 상태 버림(쉼 = 0)
        # ORIG: 되돌리고 훅이 덮은 원본 8명령의 결과(r0·r2·r9·r10)를 만들어 0x10001020 으로
        ("ORIG", (S.movl_pop(14), "mov.l @r15+,r14")),
        (S.movl_pop(13), "mov.l @r15+,r13"),
        (S.movl_pop(12), "mov.l @r15+,r12"),
        (0x4F26, "lds.l @r15+,pr"),
        (0x6A83, "mov r8,r10"),
        (0x7A5A, "add #90,r10"),
        (0x7A5A, "add #90,r10"),                        # r10 = this + 0xB4
        (0x69A3, "mov r10,r9"),
        (0x7964, "add #100,r9"),                        # r9 = this + 0x118
        (0x6292, "mov.l @r9,r2"),                       # r2 = cursor
        (0x60A3, "mov r10,r0"),
        (0x703C, "add #60,r0"),                         # r0 = this + 0xF0 (0x10001020 이 +104 한다)
        (S.rts(), "rts"),
        (0x6483, "mov r8,r4"),                          # ★ r4 = this — 원본 본문이 0x10003afc(r4) 를 부른다.
        #   재귀 DOPUT 안의 0x10003afc 가 r4 를 덮으므로 되살려야 한다(인게임 리셋의 원인, 에뮬레이터는 못 잡았다)
        # XDEL: 이 칸을 조합 중이면 자모 하나만 뺀다
        ("XDEL", (M(L_H, 14, 11), f"mov.l @({L_H},r14),r11")),
        (0x3BEC, "add r14,r11"),
        (0x60D2, "mov.l @r13,r0"),
        (0x6007, "not r0,r0"),                          # 상태 커서 = ~cursor (0 = 쉼)
        (0x6190, "mov.b @r9,r1"),
        (0x3010, "cmp/eq r1,r0"),
        ("bf", "XD_RESET"),
        (0x8491, "mov.b @(1,r9),r0"),
        (0x88FF, "cmp/eq #-1,r0"),
        ("bt", "XD_RESET"),
    ] + load_state[1:] + [
        (0x2338, "tst r3,r3"),
        ("bt", "XD_JUNG"),
        (M(S_REST, 11, 4), f"mov.l @({S_REST},r11),r4"),
        (0x34BC, "add r11,r4"),
        (0x034C, "mov.b @(r0,r4),r3"),                  # 종성 → 남는 종성
        ("bra", "STORE"),
        (S.nop(), "nop"),
        ("XD_JUNG", (0x6023, "mov r2,r0")),
        (0x88FF, "cmp/eq #-1,r0"),
        ("bt", "XD_RESET"),                             # 초성뿐 → 빈칸(원본) + 상태 버림
        (M(S_UNDIPH, 11, 4), f"mov.l @({S_UNDIPH},r11),r4"),
        (0x34BC, "add r11,r4"),
        (0x024C, "mov.b @(r0,r4),r2"),                  # 복모음 → 앞 모음, 홑모음 → −1
        ("bra", "STORE"),
        (S.nop(), "nop"),
        ("XD_RESET", (0xEB00, "mov #0,r11")),           # X 는 advance 0
        ("bra", "RESET_ORIG"),
        (S.nop(), "nop"),
        # JAMO: 커서가 상태와 다르면 새로 시작
        ("JAMO", (M(L_H, 14, 11), f"mov.l @({L_H},r14),r11")),
        (0x3BEC, "add r14,r11"),
        (0x60D2, "mov.l @r13,r0"),
        (0x6007, "not r0,r0"),                          # 상태 커서 = ~cursor (0 = 쉼)
        (0x6190, "mov.b @r9,r1"),
        (0x3010, "cmp/eq r1,r0"),
        ("bt", "J_SAME"),
        (0x2900, "mov.b r0,@r9"),
        (0xE0FF, "mov #-1,r0"),
        (0x8091, "mov.b r0,@(1,r9)"),
        (0x8092, "mov.b r0,@(2,r9)"),
        (0xE000, "mov #0,r0"),
        (0x8093, "mov.b r0,@(3,r9)"),
        ("J_SAME", load_state[0]),
    ] + load_state[1:] + [
        (0xE013, "mov #19,r0"),
        (0x3A02, "cmp/hs r0,r10"),
        ("bt", "VOWEL"),
        # 자음
        (0x6013, "mov r1,r0"),
        (0x88FF, "cmp/eq #-1,r0"),
        ("bt", "C_NEW"),                                # 초성 없음 → 초성
        (0x6023, "mov r2,r0"),
        (0x88FF, "cmp/eq #-1,r0"),
        ("bt", "C_COMMIT"),                             # 초성만 → 확정하고 새 초성
        (0x2338, "tst r3,r3"),
        ("bf", "C_DJ"),
        (0x64B2, "mov.l @r11,r4"),
        (0x34BC, "add r11,r4"),
        (0x60A3, "mov r10,r0"),
        (0x004C, "mov.b @(r0,r4),r0"),                  # 초성 → 종성(ㄸㅃㅉ 는 0)
        (0x2008, "tst r0,r0"),
        ("bt", "C_COMMIT"),
        (0x6303, "mov r0,r3"),
        ("bra", "STORE"),
        (S.nop(), "nop"),
        ("C_DJ", (0x6033, "mov r3,r0")),
        (0x4008, "shll2 r0"),
        (0x4008, "shll2 r0"),
        (0x4000, "shll r0"),
        (0x20AB, "or r10,r0"),                          # 키 = jong<<5 | cho
        (M(S_DJ, 11, 4), f"mov.l @({S_DJ},r11),r4"),
    ] + call("SCAN", (0x34BC, "add r11,r4")) + [
        (0x2008, "tst r0,r0"),
        ("bt", "C_COMMIT"),
        (0x6303, "mov r0,r3"),                          # 겹받침
        ("bra", "STORE"),
        (S.nop(), "nop"),
        ("C_COMMIT", call("COMMIT")[0]),
    ] + call("COMMIT")[1:] + [
        ("C_NEW", (0x61A3, "mov r10,r1")),
        (0xE2FF, "mov #-1,r2"),
        (0xE300, "mov #0,r3"),
        # STORE: 셀을 구해 0 이면 무시, 아니면 상태 저장 + 이 칸에 쓰기(advance 0)
        ("STORE", call("GLYPH")[0]),
    ] + call("GLYPH")[1:] + [
        (0x2558, "tst r5,r5"),
        ("bt", "FAIL"),
        (0x6013, "mov r1,r0"),
        (0x8091, "mov.b r0,@(1,r9)"),
        (0x6023, "mov r2,r0"),
        (0x8092, "mov.b r0,@(2,r9)"),
        (0x6033, "mov r3,r0"),
        (0x8093, "mov.b r0,@(3,r9)"),
    ] + call("DOPUT", (0xE600, "mov #0,r6")) + [
        # DONE: 오토마타가 처리함. r5 = 지금 칸의 값, r11 = 0 으로 ORIG 를 지나가면 원본 본문이
        # 같은 값을 다시 쓰고(0x10003afc 한 번 더 — 멱등) 전진 없이 0 을 돌려준다. 에필로그로 뛰는 것보다 짧다.
        ("DONE", (0x60D2, "mov.l @r13,r0")),
        (0x4000, "shll r0"),
        (0x7040, "add #64,r0"),                         # cells = &cursor + 0x40
        (0x05DD, "mov.w @(r0,r13),r5"),
        (0xEB00, "mov #0,r11"),
        ("bra", "ORIG"),
        (S.nop(), "nop"),
        # FAIL: 표에 없는 음절. 자음(r10 < 19)이 받침으로 못 붙은 것이면 지금 칸을 확정하고 그 자음을
        # 새 초성으로(철+ㅅ → 첧 이 없으니 「철」 확정 후 「ㅅ」). 그 밖(XDEL: r10 ≥ 40, 모음: 무받침이라
        # 실패하지 않는다)은 키를 무시한다.
        ("FAIL", (0xE013, "mov #19,r0")),
        (0x3A02, "cmp/hs r0,r10"),
        ("bt", "DONE"),
        (0x8493, "mov.b @(3,r9),r0"),
        (0x6303, "mov r0,r3"),                          # 종성은 저장된(성공한) 상태로 되돌려 확정
        ("bra", "C_COMMIT"),
        (S.nop(), "nop"),
        # 모음
        ("VOWEL", (0x7AED, "add #-19,r10")),
        (0x6013, "mov r1,r0"),
        (0x88FF, "cmp/eq #-1,r0"),
        ("bt", "V_ALONE"),                              # 홀로 선 모음
        (0x6023, "mov r2,r0"),
        (0x88FF, "cmp/eq #-1,r0"),
        ("bt", "V_SET"),                                # 초성만 → 중성
        (0x2338, "tst r3,r3"),
        ("bf", "V_SPLIT"),
        (0x6023, "mov r2,r0"),
        (0x4008, "shll2 r0"),
        (0x4008, "shll2 r0"),
        (0x4000, "shll r0"),
        (0x20AB, "or r10,r0"),                          # 키 = jung<<5 | v
        (M(S_DIPH, 11, 4), f"mov.l @({S_DIPH},r11),r4"),
    ] + call("SCAN", (0x34BC, "add r11,r4")) + [
        (0x2008, "tst r0,r0"),
        ("bt", "V_CA"),                                 # 복모음 아님 → 확정 + 모음 홀로
        (0x6203, "mov r0,r2"),
        ("bra", "STORE"),
        (S.nop(), "nop"),
        ("V_SET", (0x62A3, "mov r10,r2")),
        ("bra", "STORE"),
        (S.nop(), "nop"),
        # 도깨비불: 받침(의 뒷부분)이 다음 초성으로
        ("V_SPLIT", (0x6033, "mov r3,r0")),
        (M(S_SPLITCHO, 11, 4), f"mov.l @({S_SPLITCHO},r11),r4"),
        (0x34BC, "add r11,r4"),
        (0x0C4C, "mov.b @(r0,r4),r12"),                 # r12 = 옮겨 갈 초성
        (M(S_REST, 11, 4), f"mov.l @({S_REST},r11),r4"),
        (0x34BC, "add r11,r4"),
        (0x034C, "mov.b @(r0,r4),r3"),                  # r3 = 남는 종성
    ] + call("GLYPH") + [
        (0x2558, "tst r5,r5"),
        ("bf", "V_SPLIT_OK"),
        (0x8493, "mov.b @(3,r9),r0"),                   # 앞 음절이 없다 → 원래 종성으로 확정
        (0x6303, "mov r0,r3"),
        ("bra", "V_CA"),
        (S.nop(), "nop"),
        ("V_SPLIT_OK", call("COMMIT_G")[0]),
    ] + call("COMMIT_G")[1:] + [
        (0x61C3, "mov r12,r1"),
        (0xE300, "mov #0,r3"),
        ("bra", "V_SET"),
        (S.nop(), "nop"),
        ("V_CA", call("COMMIT")[0]),
    ] + call("COMMIT")[1:] + [
        # V_ALONE: 모음 자모를 그대로 쓰고 넘긴다, 상태 버림
        ("V_ALONE", (M(L_JBASE, 14, 5), f"mov.l @({L_JBASE},r14),r5")),
        (0x35AC, "add r10,r5"),
        (0x7513, "add #19,r5"),                         # 모음 자모 셀 = base + 19 + v
        (0xE601, "mov #1,r6"),
        (0xE000, "mov #0,r0"),
    ] + call("DOPUT", (0x2900, "mov.b r0,@r9")) + [    # 상태 버림(지연 슬롯)
        ("bra", "DONE"),
        (S.nop(), "nop"),
    ]
    return body


def _headers(blob):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    base = struct.unpack_from("<I", blob, pe + 24 + 28)[0]
    out = {}
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        nm = blob[o:o + 8].rstrip(bytes(1)).decode("ascii", "replace")
        vs, rva, rs, raw = struct.unpack_from("<IIII", blob, o + 8)
        out[nm] = {"hdr": o, "va": base + rva, "vs": vs, "raw": raw, "rs": rs}
    return out


def apply(blob, cp):
    """ime.patch 가 끝난 TRFNAMEIN 에 훅·스텁·헬퍼·표·상태를 심는다. 파일이 512B 커진다."""
    from kitae.build import pesection
    from kitae.build.vwstub import hook16
    out = bytearray(blob)
    secs = _headers(out)
    if SECTION in secs:
        raise ValueError("이미 IME 훅이 들어 있다")
    text = secs[".text"]
    hoff = text["raw"] + (HOOK - text["va"])
    if out[hoff:hoff + 16] != ORIG16:
        raise ValueError(f"{HOOK:#x} 가 원본이 아니다 — 다른 빌드거나 이미 패치됨")

    # 상태 4B — .data 꼬리 끝. 로더가 0 으로 채우도록 VirtualSize 를 RawSize 까지
    data = secs[".data"]
    if STATE_VA + 4 != data["va"] + data["rs"]:
        raise ValueError("STATE_VA 가 .data 꼬리 끝이 아니다 — 다른 빌드")
    soff = data["raw"] + (STATE_VA - data["va"])
    if any(out[soff:soff + 4]):
        raise ValueError("상태 자리가 비어 있지 않다")
    struct.pack_into("<I", out, data["hdr"] + 8, data["rs"])

    # 표·헬퍼 — .rdata 클래스명 슬롯 꼬리
    rd = secs[".rdata"]

    def block(bi):
        off = rd["raw"] + bi * 256
        head = len(out[off:off + 32].rstrip(bytes(1)))
        if head >= TABLE_OFF or any(out[off + TABLE_OFF: off + 256]):
            raise ValueError(f".rdata 블록 {bi} 꼬리가 비어 있지 않다(머리 {head}B)")
        return rd["va"] + bi * 256 + TABLE_OFF, off + TABLE_OFF

    t_va, t_off = block(TABLE_BLOCK)
    h_va, h_off = block(HELPER_BLOCK)
    tbl, toffs = tables()
    out[t_off:t_off + len(tbl)] = tbl
    h = helper_offsets()
    slots = b"".join(struct.pack("<i", t_va + toffs[k] - h_va)
                     for k in ("CHO2JONG", "REST", "SPLITCHO", "UNDIPH", "DJ", "DIPH"))
    assert len(slots) == SLOTS
    hcode, _, _ = _assemble(helper_body(), h_va + SLOTS)
    hblob = slots + hcode
    if len(hblob) > 256 - TABLE_OFF or len(tbl) > 256 - TABLE_OFF:
        raise ValueError(f"헬퍼 {len(hblob)}B / 표 {len(tbl)}B 가 블록 꼬리 224B 를 넘는다")
    out[h_off:h_off + len(hblob)] = hblob

    # 본체 — 새 섹션(코드·실행·읽기)
    grown, new_raw, _raw_size = pesection.add(bytes(out), SECTION, SECTION_SIZE, 0x60000020)
    out = bytearray(grown)
    m_va = _headers(out)[SECTION]["va"]
    code, lit_off, _ = _assemble(main_body(h), m_va, {"LIT": 0})
    lit_va = m_va + lit_off
    lits = [STATE_VA - lit_va, jamo_base(cp), (h_va + h["DOPUT_RET"]) - lit_va,
            X_PR[0] - lit_va, X_PR[1] - lit_va, PUTCHAR - lit_va,
            h_va - lit_va, (RDATA_VA + TABLE_OFF) - lit_va]
    main = code + struct.pack("<8i", *lits)
    if len(main) > SECTION_SIZE:
        raise ValueError(f"본체 {len(main)}B 가 섹션 {SECTION_SIZE}B 를 넘는다")
    out[new_raw:new_raw + len(main)] = main

    out[hoff:hoff + 16] = hook16(HOOK, m_va, RESUME)
    note = (f"IME 2단계: 훅 {HOOK:#x}→{m_va:#x}({len(main)}B, {SECTION}) · "
            f"헬퍼 .rdata 블록 {HELPER_BLOCK}({len(hblob)}B) · 표 블록 {TABLE_BLOCK}({len(tbl)}B) · "
            f"상태 {STATE_VA:#x}")
    return bytes(out), note
