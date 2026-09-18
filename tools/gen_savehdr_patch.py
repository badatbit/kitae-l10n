# -*- coding: utf-8 -*-
"""저장 슬롯 머리글 순서 바꾸기 — TRFVMSVIEW.DLL 코드 패치를 만들어 data/dllpatch.json 에 넣는다.

원본 0x10002cf4 는 슬롯 머리글을 `[도시 8B][스폿 …30B 고정][월][月][일][日][시간대]` 순으로
쓴다(장소는 서브루틴 0x10002f38 이 버퍼 앞에 고정 배치). 이것을
`[월][月][' '][일][日][EM][시간대][EM][도시 8B(EM 채움)][스폿 …30B]` 로 바꾼다.
숫자는 '０' 항목의 ko 를 `0`(ASCII 셀)으로 두어 엔진의 자릿수 조립이 ASCII 셀을 내고, 앞자리
패딩 '　' 항목은 FIGURE SPACE(U+2007, 폭 15), 시간대 앞 공백·15칸 필드는 EM SPACE 셀.

  * PATCH A/B: 앞머리의 장소 호출(0x10002d06 bsr)·strlen 호출(0x10002d0c jsr)·
    r9 전진(0x10002d1c add r0,r9) 을 nop — 날짜가 버퍼 맨 앞에 쓰이게.
  * HOOK D(0x10002d66, 12B): 月 두 바이트 뒤에 어절 공백(' ' 셀)을 끼운다(셀 바이트 직접).
  * HOOK C(0x10002e22, 12B): 시간대 끝(NUL 탐색) 뒤에 EM SPACE 셀 → 장소 서브루틴(r5=@(16,r8), r6=r9)
    → r9+=30 → 개행 → r5=保存日時, r0=strcpy 를 원본 리터럴 풀에서 읽어 복귀.
  * 스텁 둘(68B+24B)은 .text 꼬리 케이브(0x10004198, 104B)에. 절대주소는 하나도 안 박고
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


def _cell(ch):
    """코드페이지의 셀 바이트. 스텁이 글자 바이트를 직접 쓰므로 codepage.json 이 바뀌면 재생성."""
    cp = json.load(io.open(os.path.join(ROOT, "data", "codepage.json"), encoding="utf-8"))
    return bytes(cp[ch])


def _signed(b):
    return b - 0x100 if b >= 0x80 else b


def stub_c(va):
    """HOOK C 스텁. 진입: r9=시간대 문자열 시작(strcpy 직후), r8=레코드, pr=0x10002e2e.

    ★ hook_code 는 스텁까지의 거리를 r0 으로 만들어 `bsrf r0` 하므로 **진입 시 r0 은 원본 값
    (strlen 결과)이 아니다.** 처음엔 `add r0,r9` 로 시작했다가 r9 가 4,970B 뒤로 가 장소·개행·
    보존일시가 버퍼 밖에 쓰였다(화면엔 날짜만 남음). 그래서 시간대의 끝은 NUL 을 직접 찾는다.

    시간대와 장소 사이는 EM SPACE 셀(2바이트, 24px). base(0x10002f44)는 r12 에 보관한다
    (훅 뒤로 r11·r12 는 이 함수가 안 쓴다; 에필로그가 복원)."""
    base = 0x10002F44          # 장소함수 = base-12, 풀 = base+124 (둘 다 8비트 imm 안)
    L1 = va + 3 * 2
    em = _cell(chr(0x2003))
    body = [
        (S.sts_pr_push(), None),           # 0
        (S.bsr(0), None),                  # 1  bsr L1 (PC 얻기)
        (0x5584, "mov.l @(16,r8),r5"),     # 2  (지연) r5 = 장소 코드 — jsr 까지 아무도 안 건드린다
        (0x0B2A, "sts pr,r11"),            # 3  L1: r11 = L1
        (0xD000, None),                    # 4  mov.l K,r1
        (0x31BC, "add r11,r1"),            # 5  r1 = base
        (0x6C13, "mov r1,r12"),            # 6  r12 = base (보관)
        (0x6090, "mov.b @r9,r0"),          # 7  loop: 시간대 끝(NUL) 찾기
        (0x2008, "tst r0,r0"),             # 8
        (S.bt(1), None),                   # 9  → done(12)
        (S.bra(-5), None),                 # 10 → loop(7)
        (0x7901, "add #1,r9"),             # 11 (지연)
        (S.mov_imm(_signed(em[0]), 0), None),   # 12 done: EM SPACE 셀[0]
        (0x2900, "mov.b r0,@r9"),          # 13
        (S.mov_imm(_signed(em[1]), 0), None),   # 14 EM SPACE 셀[1]
        (0x8091, "mov.b r0,@(1,r9)"),      # 15
        (0x7902, "add #2,r9"),             # 16
        (0x6213, "mov r1,r2"),             # 17
        (0x72F4, "add #-12,r2"),           # 18 r2 = 장소함수
        (0x420B, "jsr @r2"),               # 19
        (0x6693, "mov r9,r6"),             # 20 (지연) r6 = 버퍼 위치
        (0x791E, "add #30,r9"),            # 21 장소 필드 30B
        (0xE10A, "mov #10,r1"),            # 22
        (0x2910, "mov.b r1,@r9"),          # 23 개행
        (0x7901, "add #1,r9"),             # 24
        (0x61C3, "mov r12,r1"),            # 25 r1 = base
        (0x717C, "add #124,r1"),           # 26 r1 = 풀 0x10002fc0
        (0x6012, "mov.l @r1,r0"),          # 27 r0 = strcpy 썽크
        (S.lds_pr_pop(), None),            # 28
        (S.rts(), "rts"),                  # 29
        (0x5512, "mov.l @(8,r1),r5"),      # 30 (지연) r5 = '保存日時'
    ]
    n = len(body)
    lit = (n * 2 + 3) & ~3
    body += [(S.nop(), "nop")] * ((lit - n * 2) // 2)
    body[4] = (S.movl_pc(lit - ((4 * 2 + 4) & ~3), 1), None)
    code = S.assemble(body, va)
    return code + struct.pack("<i", base - L1)


def stub_d(va):
    """HOOK D 스텁. 진입: r9=月 쓸 자리, pr=0x10002d72(그 자리의 mov.b r0,@r9 가 공백[1] 을 쓴다).

    '월'과 뒤따르는 어절 공백(' ' 셀, 9px)의 바이트를 codepage.json 에서 읽어 **직접** 쓴다 —
    리터럴 풀을 거치지 않아 PC 트릭·pr 보존이 필요 없고 24B 로 끝난다. 원본 `mov #9,r2` 재현."""
    wol = _cell("월")
    sp = _cell(" ")
    body = [
        (S.mov_imm(_signed(wol[0]), 0), None),  # 0  월[0]
        (0x8090, "mov.b r0,@(0,r9)"),           # 1
        (S.mov_imm(_signed(wol[1]), 0), None),  # 2  월[1]
        (0x8091, "mov.b r0,@(1,r9)"),           # 3
        (S.mov_imm(_signed(sp[0]), 0), None),   # 4  ' '[0]
        (0x8092, "mov.b r0,@(2,r9)"),           # 5
        (S.mov_imm(_signed(sp[1]), 0), None),   # 6  ' '[1] → 복귀지 0x10002d72 가 @r9 에 쓴다
        (0x7903, "add #3,r9"),                  # 7  r9 = ' '[1] 자리 (그 뒤 0x10002d7e 가 +1)
        (0xE209, "mov #9,r2"),                  # 8  원본 재현
        (S.rts(), "rts"),                       # 9
        (S.nop(), "nop"),                       # 10
        (S.nop(), "nop"),                       # 11 (4바이트 정렬)
    ]
    return S.assemble(body, va)


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
        f"저장 슬롯 머리글: 月 뒤 어절 공백 훅 (@{HOOK_D:#x} → 스텁 {d_va:#x})")
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
