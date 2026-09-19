# -*- coding: utf-8 -*-
"""아주 작은 SH4 어셈블러 — 스텁을 손으로 짜다 틀리지 않으려고 만들었다.

## 왜 필요한가

옵코드를 손으로 적다가 `mov.l @(disp,Rm),Rn` 의 니블 순서를 두 번 틀렸다
(`0x5nmd` 인데 `0x5ndm` 으로 적었다). 눈으로는 안 걸리고 화면에서야 드러난다.

그래서 **어셈블한 결과를 캡스톤으로 되읽어** 의도한 문장과 같은지 확인한다.
`assemble()` 이 그 검사를 항상 한다 — 다르면 예외를 던진다.

## 다루는 범위

스텁에 필요한 것만이다. 없는 명령은 `WORDS` 에 인코딩을 추가하면 된다.
분기는 `bt`/`bra` 만, 리터럴은 `mov.l @(disp,pc),Rn` 만 쓴다.
"""
import re
import struct

# 이름 → (마스크 만드는 함수, 되읽었을 때 기대하는 글자열)
def _n(v):      # 0..15 로 자른다
    return v & 0xF


def mov_imm(imm, rn):
    """mov #imm,Rn — imm 은 부호 있는 8비트"""
    return 0xE000 | (_n(rn) << 8) | (imm & 0xFF)


def mov_reg(rm, rn):
    return 0x6003 | (_n(rn) << 8) | (_n(rm) << 4)


def movl_disp_rm(disp, rm, rn):
    """mov.l @(disp,Rm),Rn — disp 는 바이트, 4의 배수"""
    assert disp % 4 == 0 and 0 <= disp <= 60
    return 0x5000 | (_n(rn) << 8) | (_n(rm) << 4) | _n(disp // 4)


def movb_r0_rm(rm, rn):
    """mov.b @(R0,Rm),Rn"""
    return 0x000C | (_n(rn) << 8) | (_n(rm) << 4)


def movw_r0_rm(rm, rn):
    """mov.w @(R0,Rm),Rn — 부호 확장되므로 뒤에 extu.w 가 필요하다"""
    return 0x000D | (_n(rn) << 8) | (_n(rm) << 4)


def movl_r0_rm(rm, rn):
    """mov.l @(R0,Rm),Rn"""
    return 0x000E | (_n(rn) << 8) | (_n(rm) << 4)


def extu_w(rm, rn):
    return 0x600D | (_n(rn) << 8) | (_n(rm) << 4)


def movl_pc(disp, rn):
    """mov.l @(disp,PC),Rn — disp 는 바이트, 4의 배수"""
    assert disp % 4 == 0 and 0 <= disp <= 1020
    return 0xD000 | (_n(rn) << 8) | (disp // 4)


def shlr8(rn):
    return 0x4019 | (_n(rn) << 8)


def shlr16(rn):
    return 0x4029 | (_n(rn) << 8)


def shll(rn):
    return 0x4000 | (_n(rn) << 8)


def shll2(rn):
    return 0x4008 | (_n(rn) << 8)


def shll8(rn):
    return 0x4018 | (_n(rn) << 8)


def shll16(rn):
    return 0x4028 | (_n(rn) << 8)


def or_reg(rm, rn):
    """or Rm,Rn"""
    return 0x200B | (_n(rn) << 8) | (_n(rm) << 4)


def and_imm(imm):
    """and #imm,R0 — R0 전용"""
    assert 0 <= imm <= 255
    return 0xC900 | imm


def extu_b(rm, rn):
    return 0x600C | (_n(rn) << 8) | (_n(rm) << 4)


def add_reg(rm, rn):
    return 0x300C | (_n(rn) << 8) | (_n(rm) << 4)


def add_imm(imm, rn):
    return 0x7000 | (_n(rn) << 8) | (imm & 0xFF)


def cmp_eq(rm, rn):
    return 0x3000 | (_n(rn) << 8) | (_n(rm) << 4)


def bt(disp_words):
    """bt — disp 는 (목적지-(현재+4))/2, 부호 있는 8비트"""
    return 0x8900 | (disp_words & 0xFF)


def bra(disp_words):
    return 0xA000 | (disp_words & 0xFFF)


def mova(disp, ):
    """mova @(disp,PC),R0 — R0 = (PC&~3) + disp. PC = 명령주소+4"""
    assert disp % 4 == 0 and 0 <= disp <= 1020
    return 0xC700 | (disp // 4)


def bsrf(rn):
    """bsrf Rn — PC(=명령주소+4) + Rn 으로 분기. 사거리 제한이 없다"""
    return 0x0003 | (_n(rn) << 8)


def tst_imm(imm):
    """tst #imm,R0 — T = ((R0 & imm) == 0)"""
    return 0xC800 | (imm & 0xFF)


def bf(disp_words):
    return 0x8B00 | (disp_words & 0xFF)


def braf(rn):
    """braf Rn — PC(=명령주소+4) + Rn 으로 점프. 돌아오지 않는다"""
    return 0x0023 | (_n(rn) << 8)


def rts():
    return 0x000B


def nop():
    return 0x0009


def movl_push(rm):
    """mov.l Rm,@-r15 — 스택 푸시"""
    return 0x2F06 | (_n(rm) << 4)


def movl_pop(rn):
    """mov.l @r15+,Rn — 스택 팝 (MOV.L @Rm+,Rn, m=15)"""
    return 0x6006 | (_n(rn) << 8) | (15 << 4)


def sts_pr_push():
    """sts.l pr,@-r15"""
    return 0x4F22


def lds_pr_pop():
    """lds.l @r15+,pr"""
    return 0x4F26


def bsr(disp_words):
    return 0xB000 | (disp_words & 0xFFF)


def to_bytes(words):
    return b"".join(struct.pack("<H", w) for w in words)


def disasm(words, va=0):
    """[(주소, '명령')] — 검증과 로그용."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_SH,
                     capstone.CS_MODE_LITTLE_ENDIAN | (1 << 4))
    return [(i.address, f"{i.mnemonic} {i.op_str}".strip())
            for i in md.disasm(to_bytes(words), va)]


_SP = re.compile(r"\s+")


def _norm(s):
    return _SP.sub("", s).lower().replace("r0,", "r0,")


def assemble(prog, va=0):
    """[(워드, '의도한 문장')] → 바이트. 캡스톤으로 되읽어 다르면 예외."""
    words = [w for w, _ in prog]
    got = disasm(words, va)
    if len(got) != len(prog):
        raise ValueError(f"디코드 {len(got)}개 / 기대 {len(prog)}개 — 인코딩 오류")
    for (w, want), (addr, real) in zip(prog, got):
        if want is None:
            continue
        if _norm(want) != _norm(real):
            raise ValueError(
                f"{addr:#x}: {w:#06x} 를 '{want}' 로 적었는데 '{real}' 로 읽힌다")
    return to_bytes(words)
