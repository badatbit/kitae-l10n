# -*- coding: utf-8 -*-
"""저장 슬롯 머리글 순서 바꾸기 — TRFVMSVIEW.DLL 코드 패치를 만들어 data/dllpatch.json 에 넣는다.

원본 0x10002cf4 는 슬롯 머리글을 `[도시 8B][스폿 …30B 고정][월][月][일][日][시간대]` 순으로
쓴다(장소는 서브루틴 0x10002f38 이 버퍼 앞에 고정 배치). 이것을
`[월][月][전각공백][일][日][시간대][전각공백][도시 8B][스폿 …30B]` 로 바꾼다.

  * PATCH A/B: 앞머리의 장소 호출(0x10002d06 bsr)·strlen 호출(0x10002d0c jsr)·
    r9 전진(0x10002d1c add r0,r9) 을 nop — 날짜가 버퍼 맨 앞에 쓰이게.
  * HOOK D(0x10002d66, 12B): 月 두 바이트 뒤에 전각공백을 끼운다(원본 6워드 재현).
  * HOOK C(0x10002e22, 12B): 시간대 뒤에 전각공백 → 장소 서브루틴(r5=@(16,r8), r6=r9)
    → r9+=30 → 개행 → r5=保存日時, r0=strcpy 를 원본 리터럴 풀에서 읽어 복귀.
  * 스텁 둘(60B+40B)은 .text 꼬리 케이브(0x10004198, 104B)에. 절대주소는 하나도 안 박고
    `bsr L; sts pr,rN` 으로 얻은 PC 에 **거리 상수**를 더해 풀·함수에 닿는다 → 재배치 불필요.
  * .text VirtualSize 를 케이브 사용분만큼 키운다.

버퍼는 슬롯당 88B(호출자 0x10002140: 92B 레코드 +4). 새 줄 길이 = 20+2+30+1+14+16+NUL = 84.
스폿명은 도시 8B 와 합쳐 30B 필드 안이어야 하므로 **11자(22B) 이하**.

실행: python tools/gen_savehdr_patch.py  (work/orig/TRF/TRFVMSVIEW.DLL 필요)
"""
import io
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from kitae.build import sh4                      # noqa: E402
from kitae.build.vwstub import hook_code         # noqa: E402

S = sh4
OPTION = "save_header_reorder"
MOD = "/TRF/TRFVMSVIEW.DLL"
TEXT_VA, TEXT_RAW = 0x10001000, 0x400
PLACE_FN = 0x10002F38          # 장소 필드 빌더(r5=코드, r6=버퍼)
POOL_STRCPY = 0x10002FC0       # 리터럴 풀: strcpy 썽크 주소(재배치됨)
POOL_HOZON = 0x10002FC8        # 리터럴 풀: '保存日時' 문자열 주소(재배치됨)
POOL_TSUKI = 0x10002DC4        # 리터럴 풀: '月' 문자열 주소(재배치됨)
HOOK_D, HOOK_C = 0x10002D66, 0x10002E22
NOPS = ((0x10002D06, 0xB117), (0x10002D0C, 0x400B), (0x10002D1C, 0x390C))
HOOK_D_ORIG = (0xD417, 0x6240, 0x2920, 0x7901, 0x8441, 0xE209)
HOOK_C_ORIG = (0xD569, 0x390C, 0xD066, 0xE10A, 0x2910, 0x7901)


def va2off(va):
    return TEXT_RAW + (va - TEXT_VA)


def stub_c(va):
    """HOOK C 스텁. 진입: r9=날짜 끝(시간대 strlen 은 r0), r8=레코드, pr=0x10002e2e."""
    base = 0x10002F44          # 장소함수 = base-12, 풀 = base+124 (둘 다 8비트 imm 안)
    L1 = va + 8 * 2
    body = [
        (S.sts_pr_push(), None),           # 0
        (0x390C, "add r0,r9"),             # 1  (원본) r9 += strlen(시간대)
        (0xE081, "mov #-127,r0"),          # 2  0x81
        (0x2900, "mov.b r0,@r9"),          # 3  구분 전각공백[0]
        (0xE040, "mov #64,r0"),            # 4  0x40
        (0x8091, "mov.b r0,@(1,r9)"),      # 5  구분 전각공백[1]
        (S.bsr(0), None),                  # 6  bsr L1 (PC 얻기)
        (0x7902, "add #2,r9"),             # 7  (지연) r9 += 2
        (0x0B2A, "sts pr,r11"),            # 8  L1: r11 = L1
        (0xD000, None),                    # 9  mov.l K,r1
        (0x31BC, "add r11,r1"),            # 10 r1 = base
        (0x6213, "mov r1,r2"),             # 11
        (0x72F4, "add #-12,r2"),           # 12 r2 = 장소함수
        (0x5584, "mov.l @(16,r8),r5"),     # 13 r5 = 장소 코드
        (0x420B, "jsr @r2"),               # 14
        (0x6693, "mov r9,r6"),             # 15 (지연) r6 = 버퍼 위치
        (0x791E, "add #30,r9"),            # 16 장소 필드 30B
        (0xE10A, "mov #10,r1"),            # 17
        (0x2910, "mov.b r1,@r9"),          # 18 개행
        (0x7901, "add #1,r9"),             # 19
        (0xD000, None),                    # 20 mov.l K,r1
        (0x31BC, "add r11,r1"),            # 21 r1 = base
        (0x717C, "add #124,r1"),           # 22 r1 = 풀 0x10002fc0
        (0x6012, "mov.l @r1,r0"),          # 23 r0 = strcpy 썽크
        (0x5512, "mov.l @(8,r1),r5"),      # 24 r5 = '保存日時'
        (S.lds_pr_pop(), None),            # 25
        (S.rts(), "rts"),                  # 26
        (S.nop(), "nop"),                  # 27
    ]
    lit = len(body) * 2
    assert lit % 4 == 0 and lit == 56
    body[9] = (S.movl_pc(lit - ((9 * 2 + 4) & ~3), 1), None)
    body[20] = (S.movl_pc(lit - ((20 * 2 + 4) & ~3), 1), None)
    code = S.assemble(body, va)
    return code + struct.pack("<i", base - L1)


def stub_d(va):
    """HOOK D 스텁. 진입: r9=月 쓸 자리, pr=0x10002d72(그 자리의 mov.b r0,@r9 가 공백[1] 을 쓴다)."""
    L2 = va + 3 * 2
    body = [
        (S.sts_pr_push(), None),           # 0
        (S.bsr(0), None),                  # 1  bsr L2
        (0xE209, "mov #9,r2"),             # 2  (지연) 원본 mov #9,r2 재현
        (0x032A, "sts pr,r3"),             # 3  L2: r3 = L2
        (0xD000, None),                    # 4  mov.l K4,r4
        (0x343C, "add r3,r4"),             # 5  r4 = 풀 0x10002dc4
        (0x6442, "mov.l @r4,r4"),          # 6  r4 = '月' 문자열(재배치된 주소)
        (0x6040, "mov.b @r4,r0"),          # 7
        (0x8090, "mov.b r0,@(0,r9)"),      # 8  月[0]
        (0x8441, "mov.b @(1,r4),r0"),      # 9
        (0x8091, "mov.b r0,@(1,r9)"),      # 10 月[1]
        (0xE081, "mov #-127,r0"),          # 11
        (0x8092, "mov.b r0,@(2,r9)"),      # 12 공백[0]
        (0xE040, "mov #64,r0"),            # 13 공백[1] → 복귀지 0x10002d72 가 @r9 에 쓴다
        (0x7903, "add #3,r9"),             # 14 r9 = 공백[1] 자리 (그 뒤 0x10002d7e 가 +1)
        (S.lds_pr_pop(), None),            # 15
        (S.rts(), "rts"),                  # 16
        (S.nop(), "nop"),                  # 17
    ]
    lit = len(body) * 2
    assert lit % 4 == 0 and lit == 36
    body[4] = (S.movl_pc(lit - ((4 * 2 + 4) & ~3), 4), None)
    code = S.assemble(body, va)
    return code + struct.pack("<i", POOL_TSUKI - L2)


def main():
    orig = os.path.join(ROOT, "work", "orig", "TRF", "TRFVMSVIEW.DLL")
    b = open(orig, "rb").read()
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    optsz = struct.unpack_from("<H", b, pe + 20)[0]
    sec0 = pe + 24 + optsz
    assert b[sec0:sec0 + 5] == b".text"
    vsz, rva, rsz, raw = struct.unpack_from("<IIII", b, sec0 + 8)
    assert raw == TEXT_RAW and TEXT_VA == 0x10000000 + rva, (raw, rva)
    cave_va = TEXT_VA + vsz
    assert cave_va % 4 == 0
    c_va = cave_va
    sc = stub_c(c_va)
    d_va = c_va + len(sc)
    assert d_va % 4 == 0
    sd = stub_d(d_va)
    total = len(sc) + len(sd)
    if vsz + total > rsz:
        raise SystemExit(f"케이브 부족: {rsz - vsz}B 에 {total}B")
    cave_off = va2off(cave_va)
    if any(b[cave_off:cave_off + total]):
        raise SystemExit("케이브가 비어 있지 않다")

    def word(va):
        return struct.unpack_from("<H", b, va2off(va))[0]

    for va, orig_w in NOPS:
        assert word(va) == orig_w, hex(va)
    for hook, origs in ((HOOK_D, HOOK_D_ORIG), (HOOK_C, HOOK_C_ORIG)):
        for i, w in enumerate(origs):
            assert word(hook + 2 * i) == w, hex(hook + 2 * i)

    patches = []

    def add(off, frm, to, why):
        assert len(frm) == len(to)
        assert b[off:off + len(frm)] == frm, hex(off)
        patches.append({"module": MOD, "offset": off, "from": frm.hex(), "to": to.hex(),
                        "why": why, "option": OPTION})

    def words(ws):
        return b"".join(struct.pack("<H", w) for w in ws)

    for va, orig_w in NOPS:
        add(va2off(va), words([orig_w]), words([0x0009]),
            f"저장 슬롯 머리글 순서: 앞머리 장소 호출/strlen/r9 전진 무력화 (@{va:#x})")
    add(va2off(HOOK_D), words(HOOK_D_ORIG), hook_code(HOOK_D, d_va),
        f"저장 슬롯 머리글: 月 뒤 전각공백 훅 (@{HOOK_D:#x} → 스텁 {d_va:#x})")
    add(va2off(HOOK_C), words(HOOK_C_ORIG), hook_code(HOOK_C, c_va),
        f"저장 슬롯 머리글: 시간대 뒤에 장소 붙이는 훅 (@{HOOK_C:#x} → 스텁 {c_va:#x})")
    add(cave_off, bytes(total), sc + sd,
        f"저장 슬롯 머리글 스텁 C({len(sc)}B @{c_va:#x}) + D({len(sd)}B @{d_va:#x}) — .text 꼬리 케이브")
    add(sec0 + 8, struct.pack("<I", vsz), struct.pack("<I", vsz + total),
        f".text VirtualSize {vsz:#x}→{vsz + total:#x} (케이브 스텁 포함)")

    path = os.path.join(ROOT, "data", "dllpatch.json")
    spec = json.load(io.open(path, encoding="utf-8"))
    spec["patches"] = [e for e in spec["patches"] if e.get("option") != OPTION] + patches
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"dllpatch.json: {OPTION} 패치 {len(patches)}개 "
          f"(스텁 C {len(sc)}B @{c_va:#x}, D {len(sd)}B @{d_va:#x}, 케이브 {rsz - vsz}B)")
    blob = sc + sd
    ws = [struct.unpack_from("<H", blob, i)[0] for i in range(0, total, 2)]
    for a, t in S.disasm(ws, c_va):
        print(f"  {a:x}: {t}")


if __name__ == "__main__":
    main()
