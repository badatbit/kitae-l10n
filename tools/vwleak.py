# -*- coding: utf-8 -*-
"""가변폭 라이브 유출 스텁/훅 생성기 — Flycast 메모리 조사용.

경위는 [PROPORTIONAL-WIDTH.md](../docs/PROPORTIONAL-WIDTH.md) §라이브 조사.
그리기 루프가 문자 코드를 어디서 얻는지 규명하려고, 훅 `0x100035B4` 에서
스텁으로 분기해 매 글자 `r10/r9/r11/r8` 을 고정 슬롯에 남긴다. 스텁은 원래 훅
코드(폭·자간·보정·인덱스)를 재현한 뒤 훅 다음(`0x8CCAB5C0`)으로 braf 복귀한다.

    python tools/vwleak.py 0x8CCB4200        # STUB_PHYS 를 케이브로 주고 워드 출력

## ★ 다이나렉이 라이브 스텁을 못 문다 (2026-08-14)

`STUB_PHYS = 0x8CFE0000`(RAM 빈 영역)에 스텁을 심고 훅에서 braf 로 뛰었더니
**인게임에서 리셋됐다.** 훅을 분기 없는 명령으로만 바꿨을 때(첫 실험 `mov #24`)는
리셋이 없었으므로, 원인은 스텁 로직이 아니라 **Flycast 다이나렉이 RAM 임의 영역으로의
braf 분기 타깃을 유효 코드 페이지로 못 잡는 것**이다. 링버퍼(미초기화 카운터로 범위
밖 store)는 이미 뺐는데도 단순 스텁이 리셋을 냈다.

다음 두 갈래로 푼다.
  1. **케이브 배치** — 스텁을 TRFSTRINGS `.text` 꼬리 케이브(phys 0x8CCA9000~
     0x8CCB4400 사이 0 구간)에 둔다. 이미 코드 페이지라 다이나렉이 코드로 인식할
     공산이 크다. 이 파일의 `stub_phys` 인자로 그 주소를 준다.
  2. **인터프리터 모드** — emu.cfg `Dynarec.Enabled = no`. 자기수정·임의 분기가
     안전하지만 WinCE 타이틀이라 매우 느리다.

물리↔가상은 비선형(MMU)이므로 유출된 포인터 값 해석은 페이지 테이블이 필요할 수
있다. 다만 스텁이 남기는 것은 값이므로, r10/r8 이 P1(0x8Cxxxxxx) 형식이면 그대로
읽을 수 있다.
"""
import struct
import sys

sys.path.insert(0, r"F:\dev-kitahe\kitahe-l10n")
from kitae.build import sh4

HOOK_PHYS = 0x8CCAB5B4
HOOK_RET = HOOK_PHYS + 12            # 0x8CCAB5C0
DEFAULT_STUB = 0x8CFE0000           # RAM 빈 영역 — 다이나렉이 못 뭄. 케이브로 교체하라
DEFAULT_SCRATCH = 0x8CFE4000        # 16B: r10,r9,r11,r8


def movl_store(rm, rn):              # mov.l Rm,@Rn
    return 0x2002 | (rn << 8) | (rm << 4)


def movl_store_disp(rm, disp, rn):  # mov.l Rm,@(disp,Rn)
    assert disp % 4 == 0 and 0 <= disp <= 60
    return 0x1000 | (rn << 8) | (rm << 4) | (disp // 4)


def build_stub(stub_phys=DEFAULT_STUB, scratch=DEFAULT_SCRATCH):
    S = sh4
    code = []

    def emit(word, intent):
        code.append((word, intent))

    emit(S.movl_pc(0, 0), None)                          # [0] r0=SCRATCH
    emit(movl_store(10, 0), "mov.l r10,@r0")             # [1]
    emit(movl_store_disp(9, 4, 0), "mov.l r9,@(4,r0)")   # [2]
    emit(movl_store_disp(11, 8, 0), "mov.l r11,@(8,r0)") # [3]
    emit(movl_store_disp(8, 12, 0), "mov.l r8,@(12,r0)") # [4]
    emit(S.movl_disp_rm(0, 9, 4), "mov.l @(0,r9),r4")    # [5] 폭
    emit(S.add_imm(1, 11), "add #1,r11")                 # [6]
    emit(S.movl_disp_rm(52, 10, 1), "mov.l @(52,r10),r1")# [7] 자간
    emit(S.add_reg(1, 4), "add r1,r4")                   # [8]
    emit(S.movl_disp_rm(48, 10, 2), "mov.l @(48,r10),r2")# [9] 보정
    emit(0x3428, "sub r2,r4")                            # [10]
    emit(S.movl_pc(0, 0), None)                          # [11] r0=ret dist
    emit(S.braf(0), "braf r0")                           # [12]
    emit(S.nop(), "nop")                                 # [13] 지연슬롯

    n = len(code)                                        # 14 words = 28B
    lit_off = (n * 2 + 3) & ~3                           # 0x1C
    off_scr = lit_off
    off_ret = lit_off + 4

    def pcdisp(idx, target_off):
        pc = (idx * 2 + 4) & ~3
        return target_off - pc

    ret_dist = HOOK_RET - (stub_phys + 12 * 2 + 4)       # braf at idx12

    code[0] = (S.movl_pc(pcdisp(0, off_scr), 0), None)
    code[11] = (S.movl_pc(pcdisp(11, off_ret), 0), None)

    blob = sh4.assemble(code, va=stub_phys)
    blob += b"\x00" * (lit_off - len(blob))
    blob += struct.pack("<II", scratch, ret_dist & 0xFFFFFFFF)
    return blob, code


def build_hook(stub_phys=DEFAULT_STUB):
    S = sh4
    braf_dist = stub_phys - (HOOK_PHYS + 2 + 4)          # braf at hook+2
    code = [
        (S.movl_pc(4, 0), None),                         # r0 = @(hook+8) = 거리
        (S.braf(0), "braf r0"),
        (S.nop(), "nop"),
        (S.nop(), "nop"),
    ]
    blob = sh4.assemble(code, va=HOOK_PHYS)
    blob += struct.pack("<I", braf_dist & 0xFFFFFFFF)
    return blob, braf_dist


def to_lua_words(blob):
    words = struct.unpack("<%dH" % (len(blob) // 2), blob)
    return ",".join("0x%04x" % w for w in words)


if __name__ == "__main__":
    stub_phys = int(sys.argv[1], 0) if len(sys.argv) > 1 else DEFAULT_STUB
    scratch = int(sys.argv[2], 0) if len(sys.argv) > 2 else DEFAULT_SCRATCH
    stub, code = build_stub(stub_phys, scratch)
    print("=== STUB disasm ===")
    words = struct.unpack("<%dH" % (len(stub) // 2), stub)
    for addr, txt in sh4.disasm(words[:14], stub_phys):
        print(f"  {addr:08x}  {txt}")
    hook, bd = build_hook(stub_phys)
    print(f"\nSTUB {len(stub)}B @ {stub_phys:08x}  SCRATCH {scratch:08x}")
    print(f"HOOK {len(hook)}B, braf_dist {bd:#x}")
    print("\nSTUB_WORDS =", to_lua_words(stub))
    print("HOOK_WORDS =", to_lua_words(hook))
