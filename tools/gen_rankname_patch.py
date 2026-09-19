# -*- coding: utf-8 -*-
"""순위 표의 주인공 이름에 어절 공백을 넣는 패치를 만든다 (data/dllpatch.json).

TRFOPTIONGAME 의 순위 행은 조각을 이어 붙여 만든다:

    "1위 " + 점수 + "점　" + [성] + [이름] + 줄바꿈

성과 이름은 세이브와 같은 구조로 **12바이트 떨어진 두 칸**에서 각각 가져와 그냥
strcat 한다. 사이에 구분자 문자열이 없어 `타사카츠요시` 로 붙어 나온다(이름 확인창은
`　` 를 따로 한 번 더 붙여서 띄어 나온다). 번역만으로는 손댈 수 없어 코드로 넣는다.

다섯 화면(테니스·미로2종·퀴즈·슈팅/UFO)이 **같은 14바이트**를 쓴다:

    mov.l <strcat>,r0 · jsr @r0 · mov r8,r4      ; strcat(버퍼, 성)
    mov.l <strcat>,r0 · mov r12,r5 · jsr @r0 · mov r8,r4   ; strcat(버퍼, 이름)

이 14바이트를 훅 12바이트(vwstub.hook_code) + nop 으로 바꾸고, 케이브의 스텁이
`성 → 공백 → 이름` 순으로 세 번 strcat 한다. 진입 때 r8=버퍼, r5=성, r12=이름이고
strcat 는 COREDLL 임포트 썽크(0x10004CBC, `jmp @r0` 꼬리 점프)라 r8·r12 는 보존된다.

★ 공백 셀 바이트를 스텁이 직접 들고 있으므로 **codepage.json 이 바뀌면 재생성**해야
한다 (tools/gen_savehdr_patch.py 와 같은 제약).

실행: python tools/gen_rankname_patch.py   (work/orig/TRF/TRFOPTIONGAME.DLL 필요)
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
OPTION = "rank_name_space"
MOD = "/TRF/TRFOPTIONGAME.DLL"
TEXT_VA, TEXT_RAW = 0x10001000, 0x400
STRCAT = 0x10004CBC                 # COREDLL strcat 임포트 썽크
SEP = " "                           # 성과 이름 사이 — 어절 공백 셀(9px)

# 이름 두 조각을 이어 붙이는 자리(첫 `mov.l <strcat>,r0` 주소). 화면 5개가 같은 모양이다.
SITES = (0x10003DA2, 0x10003E92, 0x10003FA0, 0x10004062, 0x10004138)
SITE_LEN = 14
JSR_R0, MOV_R8_R4, MOV_R12_R5 = 0x400B, 0x6483, 0x65C3


def va2off(va):
    return TEXT_RAW + (va - TEXT_VA)


def _cell(ch):
    cp = json.load(io.open(os.path.join(ROOT, "data", "codepage.json"), encoding="utf-8"))
    return bytes(cp[ch])


def stub(va, sep_bytes):
    """성 → 공백 → 이름 순으로 strcat 세 번. 진입: r8=버퍼, r5=성, r12=이름."""
    lit_strcat = 32                  # 스텁 시작 기준 바이트 오프셋
    lit_sep = 36
    sep_at = 40
    prog = [
        (S.sts_pr_push(), "sts.l pr,@-r15"),                  # +0  pr 저장(jsr 가 덮는다)
        (S.movl_pc(lit_strcat - 4, 0), None),                 # +2  r0 = strcat
        (JSR_R0, "jsr @r0"),                                  # +4  strcat(r8, r5=성)
        (S.mov_reg(8, 4), "mov r8,r4"),                       # +6  지연 슬롯
        (S.movl_pc(lit_strcat - 12, 0), None),                # +8  r0 = strcat
        (S.movl_pc(lit_sep - 12, 5), None),                   # +10 r5 = 공백
        (JSR_R0, "jsr @r0"),                                  # +12 strcat(r8, 공백)
        (S.mov_reg(8, 4), "mov r8,r4"),                       # +14
        (S.movl_pc(lit_strcat - 20, 0), None),                # +16 r0 = strcat
        (MOV_R12_R5, "mov r12,r5"),                           # +18 r5 = 이름
        (JSR_R0, "jsr @r0"),                                  # +20 strcat(r8, 이름)
        (S.mov_reg(8, 4), "mov r8,r4"),                       # +22
        (S.lds_pr_pop(), "lds.l @r15+,pr"),                   # +24
        (S.nop(), "nop"),                                     # +26 lds→rts 사이 한 박자
        (S.rts(), "rts"),                                     # +28
        (S.nop(), "nop"),                                     # +30 지연 슬롯
    ]
    code = S.assemble(prog, va)
    assert len(code) == lit_strcat, len(code)
    return (code + struct.pack("<I", STRCAT) + struct.pack("<I", va + sep_at)
            + sep_bytes.ljust(4, b"\x00"))


def main():
    orig = os.path.join(ROOT, "work", "orig", "TRF", "TRFOPTIONGAME.DLL")
    b = open(orig, "rb").read()
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    optsz = struct.unpack_from("<H", b, pe + 20)[0]
    sec0 = pe + 24 + optsz
    assert b[sec0:sec0 + 5] == b".text"
    vsz, rva, rsz, raw = struct.unpack_from("<IIII", b, sec0 + 8)
    assert raw == TEXT_RAW and TEXT_VA == 0x10000000 + rva, (raw, rva)

    cave_va = (TEXT_VA + vsz + 3) & ~3          # 꼬리 케이브(4바이트 정렬)
    sep = _cell(SEP)
    code = stub(cave_va, sep)
    end_off = (cave_va - TEXT_VA) + len(code)
    if end_off > rsz:
        raise SystemExit(f"케이브 부족: {rsz - vsz}B 에 {len(code)}B")
    cave_off = va2off(cave_va)
    if any(b[cave_off:cave_off + len(code)]):
        raise SystemExit("케이브가 비어 있지 않다")

    patches = []

    def add(off, frm, to, why):
        assert len(frm) == len(to), (len(frm), len(to))
        assert b[off:off + len(frm)] == frm, hex(off)
        patches.append({"module": MOD, "offset": off, "from": frm.hex(), "to": to.hex(),
                        "why": why, "option": OPTION})

    for site in SITES:
        off = va2off(site)
        frm = b[off:off + SITE_LEN]
        w = struct.unpack("<7H", frm)
        # 모양 확인: mov.l <strcat>,r0 / jsr / mov r8,r4 / mov.l <strcat>,r0 / mov r12,r5 / jsr / mov r8,r4
        for i in (0, 3):
            assert w[i] >> 8 == 0xD0, hex(w[i])
            pool = ((site + 2 * i + 4) & ~3) + (w[i] & 0xFF) * 4
            assert struct.unpack_from("<I", b, va2off(pool))[0] == STRCAT, hex(pool)
        assert (w[1], w[2], w[4], w[5], w[6]) == (JSR_R0, MOV_R8_R4, MOV_R12_R5,
                                                  JSR_R0, MOV_R8_R4), [hex(x) for x in w]
        to = hook_code(site, cave_va) + S.to_bytes([S.nop()])
        add(off, frm, to, f"순위 표 이름: 성·이름 사이 어절 공백 훅 (@{site:#x} → 스텁 {cave_va:#x})")

    add(cave_off, bytes(len(code)), code,
        f"순위 표 이름 스텁 {len(code)}B @{cave_va:#x} — 성→공백→이름 strcat, .text 꼬리 케이브")
    new_vsz = end_off
    add(sec0 + 8, struct.pack("<I", vsz), struct.pack("<I", new_vsz),
        f".text VirtualSize {vsz:#x}→{new_vsz:#x} (케이브 스텁 포함)")

    path = os.path.join(ROOT, "data", "dllpatch.json")
    spec = json.load(io.open(path, encoding="utf-8"))
    spec["patches"] = [e for e in spec["patches"] if e.get("option") != OPTION] + patches
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(spec, ensure_ascii=False, indent=1) + "\n")
    print(f"{OPTION}: 패치 {len(patches)}개 → data/dllpatch.json")
    print(f"  스텁 {len(code)}B @ {cave_va:#x} (공백 셀 {sep.hex(' ')}), "
          f".text VirtualSize {vsz:#x}→{new_vsz:#x}")
    for s in SITES:
        print(f"  훅 @{s:#x}")


if __name__ == "__main__":
    main()
