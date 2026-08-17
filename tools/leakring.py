# -*- coding: utf-8 -*-
"""라이브 유출 링 — 글자 루프의 레지스터·레코드를 빈 RAM 에 남긴다.

flycast(인터프리터 모드) + Lua 서버로 주입한다. GDB 가 없는 빌드라서
중단점 대신 **훅이 직접 관측 데이터를 쓰게** 한다.

  훅 0x8CCAB5B4 (12B) ──braf──▶ 스텁(빈 RAM) ──rts──▶ 훅 다음

스텁은 매 글자:
  헤더  SCR+0  r10 · +4 r9 · +8 호출수 · +12 r13
  슬롯  SCR + (r11&31)*32 + 16 :
        +0 r8   +4 rec[0]  +8 rec[4]  +12 rec[8]  +16 rec[12]
        +20 r12(펜X)  +24 r11  +28 @r9(폭)
그리고 원래 훅 일(r4=@r9 폭, r11+=1)을 재현하고 돌아간다 — 화면은 순정 고정폭.

25글자 상한 < 32슬롯이라 창 하나가 통째로 남는다. 화면에 아는 문장을 띄우면
글자별 레코드가 슬롯 순서대로 잡혀 "무엇이 글자를 가리키는가"를 즉석 대조한다.

    python tools/leakring.py            # work/leak_inject.lua 생성
    python tools/lualink.py --file work/leak_inject.lua
"""
import io
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.stdout.reconfigure(encoding="utf-8")
from kitae.build import sh4                                  # noqa: E402

HOOK = 0x8CCAB5B4                      # 글자 루프 0x100035B4 의 RAM 자리
STUB = 0x8C230000                      # 1.5MB 빈 구간 한가운데
SCR = STUB + 0x80
RING = 0x440                           # 헤더 16 + 슬롯 32*32 여유


def movl_load(rm, rn):                 # mov.l @Rm,Rn
    return 0x6002 | (rn << 8) | (rm << 4)


def movl_store(rm, rn):                # mov.l Rm,@Rn
    return 0x2002 | (rn << 8) | (rm << 4)


def movl_store_disp(rm, disp, rn):     # mov.l Rm,@(disp,Rn)
    assert disp % 4 == 0 and 0 <= disp <= 60
    return 0x1000 | (rn << 8) | (rm << 4) | (disp // 4)


def and_imm(imm):                      # and #imm,R0
    return 0xC900 | (imm & 0xFF)


def build_stub():
    S = sh4
    body = [
        (S.movl_pc(0x38, 1), None),                          # r1 = SCR (리터럴)
        (movl_store(10, 1), "mov.l r10,@r1"),
        (movl_store_disp(9, 4, 1), "mov.l r9,@(4,r1)"),
        (S.movl_disp_rm(8, 1, 2), "mov.l @(8,r1),r2"),
        (S.add_imm(1, 2), "add #1,r2"),                      # 호출수
        (movl_store_disp(2, 8, 1), "mov.l r2,@(8,r1)"),
        (movl_store_disp(13, 12, 1), "mov.l r13,@(12,r1)"),
        (S.mov_reg(11, 0), "mov r11,r0"),
        (and_imm(31), "and #31,r0"),                         # 슬롯 = r11 & 31
        (S.shll2(0), "shll2 r0"),
        (S.shll2(0), "shll2 r0"),
        (S.shll(0), "shll r0"),                              # ×32
        (S.add_reg(1, 0), "add r1,r0"),
        (movl_store_disp(8, 16, 0), "mov.l r8,@(16,r0)"),
        (movl_load(8, 2), "mov.l @r8,r2"),
        (movl_store_disp(2, 20, 0), "mov.l r2,@(20,r0)"),
        (S.movl_disp_rm(4, 8, 2), "mov.l @(4,r8),r2"),
        (movl_store_disp(2, 24, 0), "mov.l r2,@(24,r0)"),
        (S.movl_disp_rm(8, 8, 2), "mov.l @(8,r8),r2"),
        (movl_store_disp(2, 28, 0), "mov.l r2,@(28,r0)"),
        (S.movl_disp_rm(12, 8, 2), "mov.l @(12,r8),r2"),
        (movl_store_disp(2, 32, 0), "mov.l r2,@(32,r0)"),
        (movl_store_disp(12, 36, 0), "mov.l r12,@(36,r0)"),
        (movl_store_disp(11, 40, 0), "mov.l r11,@(40,r0)"),
        (movl_load(9, 2), "mov.l @r9,r2"),
        (movl_store_disp(2, 44, 0), "mov.l r2,@(44,r0)"),
        # 원래 훅 재현 (자간·보정은 본문에서 0 — 기존 스텁들과 같은 근거)
        (movl_load(9, 4), "mov.l @r9,r4"),
        (S.add_imm(1, 11), "add #1,r11"),
        (S.rts(), "rts"),
        (S.nop(), "nop"),
    ]
    blob = S.assemble(body, va=STUB)
    assert len(blob) == 0x3C, len(blob)
    return blob + struct.pack("<I", SCR)


def build_hook():
    S = sh4
    body = [
        (S.movl_pc(4, 0), None),                             # r0 = 거리 (리터럴)
        (S.braf(0), "braf r0"),
        (S.nop(), "nop"),                                    # 지연 슬롯
        (S.nop(), "nop"),
    ]
    blob = S.assemble(body, va=HOOK)
    dist = (STUB - (HOOK + 2 + 4)) & 0xFFFFFFFF
    return blob + struct.pack("<I", dist)


def main():
    stub = build_stub()
    hook = build_hook()
    print("=== 스텁 ===")
    words = struct.unpack("<%dH" % ((len(stub) - 4) // 2), stub[:-4])
    for a, s in sh4.disasm(words, STUB):
        print(f"  {a:08x}  {s}")
    print(f"  {STUB+0x3C:08x}  .long {struct.unpack('<I', stub[-4:])[0]:#010x}")
    print(f"=== 훅 (거리 {struct.unpack('<I', hook[-4:])[0]:#010x}) ===")

    def lua_words(label, addr, blob):
        ws = struct.unpack("<%dH" % (len(blob) // 2), blob)
        arr = ",".join(f"0x{w:04X}" for w in ws)
        return (f"local {label}={{{arr}}}\n"
                f"for i,w in ipairs({label}) do poke16(0x{addr:08X}+(i-1)*2, w) end\n")

    lua = ["-- leakring 주입 (자동 생성)"]
    lua.append(f"for a=0x{SCR:08X},0x{SCR+RING-4:08X},4 do poke32(a,0) end")
    lua.append(lua_words("S", STUB, stub))
    lua.append(lua_words("H", HOOK, hook))                   # 훅은 마지막
    lua.append(f"return 'inject ok', hexdump(0x{STUB:08X},0x40), "
               f"hexdump(0x{HOOK:08X},12)")
    path = os.path.join("work", "leak_inject.lua")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lua) + "\n")
    print(f"→ {path}")


if __name__ == "__main__":
    main()
