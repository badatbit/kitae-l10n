# -*- coding: utf-8 -*-
"""주인공 성/이름 사이 전각공백 — `&主人公名前&` 이 「성이름」으로 붙어 나오는 것.

## 무엇을 고치나

`&主人公名前&` 은 KITAE.DLL 이 이름 버퍼(`0x100130b8`)에 **성+이름을 붙여** 채운
문자열로 치환된다. 조립은 두 곳(`0x10001f42`, `0x10002352`)에서

    strcpy(full, 성)      ; strcpy 임포트 thunk 0x10003f20
    strcat(full, 이름)    ; strcat 임포트 thunk 0x10003f2c

성과 이름 사이에 아무것도 없어 「타사카츠요시」로 붙는다. 한국어는 성·이름을
띄우는 게 자연스러워 「타사카　츠요시」로 만든다.

**단 성이 한 글자면 붙여 쓴다** — 한국식 이름은 「유　명산」이 아니라 「유명산」이다.
스텁에 들어올 때 버퍼엔 `strcpy` 가 넣은 **성만** 들어 있으므로 거기서 길이를 본다.
`full[0] == 0`(성 없음)이거나 `full[2] == 0`(2바이트 한 글자)이면 공백을 건너뛴다.

## 어떻게

`strcpy`·`strcat` 은 **공유 임포트 thunk** 라 못 고친다(9회·3회 호출). 대신 두
호출 지점의 **strcat 리터럴**(각 풀 슬롯이 그 함수에서 한 번만 쓰인다 — 확인함)을
스텁으로 돌린다.

    sep_strcat(r4=full, r5=이름):
        strcat(full, "　")   ; 전각공백 먼저
        strcat(full, 이름)   ; 원래 이름  (꼬리호출)
        return

원래 호출 지점의 지연슬롯이 `r4=full, r5=이름` 을 세워 주므로 스텁 시그니처가
strcat 과 같다.

## 재배치 안전

  * 두 리터럴 슬롯(`0x10002048`·`0x1000240c`)은 원래 절대 VA(strcat)라 `.reloc`
    엔트리가 이미 있다 — 값을 같은 DLL 내 스텁 VA 로 바꿔도 로더가 같이 보정한다.
  * 스텁이 strcat 을 부를 때는 `bsrf`/`braf` 에 **델타**를 실어 부른다. 델타는
    로드 주소와 무관하므로 `.reloc` 이 필요 없다(가변폭에서 쓴 기법).

## 자리

스텁은 `.text` 꼬리 케이브(VirtualSize `0x31ca` ~ RawSize `0x3200`)에 둔다. 4정렬 뒤
여유가 **52B 뿐**이라 스텁이 딱 맞는다 — 명령을 더 넣을 자리가 없다.
그 자리는 매핑 밖이라 VirtualSize 를 RawSize 까지 늘려 매핑되게 한다.
"""
import struct

from kitae.build import sh4

STRCAT = 0x10003F2C            # strcat 임포트 thunk
STRCPY = 0x10003F20            # strcpy 임포트 thunk (call-site 확인용)
SITES = (0x10002048, 0x1000240C)   # strcat 리터럴 슬롯(각 함수 1회) → 스텁으로
# 호출 지점이 우리가 아는 그 조립인지 확인 — 다르면 다른 빌드다
SITE_LOADS = {0x10002048: 0x10001F42, 0x1000240C: 0x10002352}


def _pe(blob):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    secs = {}
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        nm = blob[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        vs, va, rs, ra = struct.unpack_from("<IIII", blob, o + 8)
        secs[nm] = {"hdr": o, "va": 0x10000000 + va, "vs": vs, "ra": ra, "rs": rs}
    return pe, secs


def _stub(stub_va):
    """sep_strcat 스텁 바이트. strcat 은 bsrf/braf 델타로 부른다."""
    S = sh4
    # 명령 20개(40B) + 델타 2개(8B) + 전각공백(4B) = 52B — 케이브에 딱 맞다.
    # 데이터(d1,d2,space)는 코드 뒤 4정렬.
    TAIL = 17                                   # 공백을 건너뛸 때 가는 자리
    body = [
        (0x6040, "mov.b @r4,r0"),               # [0] 성 첫 바이트
        (0x2008, "tst r0,r0"),                  # [1]
        (S.bt(TAIL - (2 + 2)), None),           # [2] 성이 비었으면 공백 없이
        (0x8442, "mov.b @(2,r4),r0"),           # [3] 성 셋째 바이트
        (0x2008, "tst r0,r0"),                  # [4]
        (S.bt(TAIL - (5 + 2)), None),           # [5] 2바이트(한 글자)면 붙여 쓴다
        (S.movl_push(4), "mov.l r4,@-r15"),     # [6] full 저장
        (S.movl_push(5), "mov.l r5,@-r15"),     # [7] 이름 저장
        (S.sts_pr_push(), "sts.l pr,@-r15"),    # [8] pr 저장
        (S.mova(0), None),                      # [9] r0 = "　" (뒤에서 disp)
        (S.mov_reg(0, 5), "mov r0,r5"),         # [10] r5 = 공백
        (S.movl_pc(0, 0), None),                # [11] r0 = delta1
        (S.bsrf(0), "bsrf r0"),                 # [12] strcat(full,"　")
        (S.nop(), "nop"),                       # [13]
        (S.lds_pr_pop(), "lds.l @r15+,pr"),     # [14] pr 복원
        (S.movl_pop(5), "mov.l @r15+,r5"),      # [15] 이름 복원
        (S.movl_pop(4), "mov.l @r15+,r4"),      # [16] full 복원
        (S.movl_pc(0, 0), None),                # [17] TAIL: r0 = delta2
        (S.braf(0), "braf r0"),                 # [18] 꼬리 strcat(full,이름)
        (S.nop(), "nop"),                       # [19]
    ]
    code_len = len(body) * 2                    # 40
    d1_off = code_len                           # 델타1
    d2_off = code_len + 4                       # 델타2
    sp_off = code_len + 8                       # 전각공백
    body[9] = (S.mova(sp_off - (((9 * 2) + 4) & ~3)), None)
    body[11] = (S.movl_pc(d1_off - (((11 * 2) + 4) & ~3), 0), None)
    body[17] = (S.movl_pc(d2_off - (((17 * 2) + 4) & ~3), 0), None)
    blob = S.assemble(body, va=stub_va)
    # 되읽기: 두 조건 분기가 정말 TAIL 로 가는가
    for a, t in S.disasm([w for w, _ in body], stub_va):
        if t.startswith("bt") and int(t.split()[-1], 16) != stub_va + TAIL * 2:
            raise ValueError(f"스텁 분기 {a:#x} {t} 가 TAIL({stub_va + TAIL*2:#x}) 이 아니다")
    # 델타: strcat - (분기명령주소 + 4)
    bsrf_va = stub_va + 12 * 2
    braf_va = stub_va + 18 * 2
    delta1 = (STRCAT - (bsrf_va + 4)) & 0xFFFFFFFF
    delta2 = (STRCAT - (braf_va + 4)) & 0xFFFFFFFF
    blob += struct.pack("<II", delta1, delta2)
    blob += bytes.fromhex("81400000")           # 전각공백(cp932 0x8140) + NUL
    return blob


def apply(blob):
    """KITAE.DLL 바이트를 받아 성/이름 공백 패치를 적용한 바이트를 돌려준다."""
    out = bytearray(blob)
    pe, secs = _pe(out)
    text = secs[".text"]
    tb, tvs, tra, trs = text["va"], text["vs"], text["ra"], text["rs"]

    def raw(va):
        return tra + (va - tb)

    # 조립 호출 지점 검증 — 리터럴이 정말 strcat 을 싣고 있나
    for slot in SITES:
        if struct.unpack_from("<I", out, raw(slot))[0] != STRCAT:
            raise ValueError(f"리터럴 {slot:#x} 가 strcat 이 아니다 — 다른 빌드")

    # 케이브: 현재 VirtualSize 끝을 4정렬 → 스텁 시작
    stub_va = (tb + tvs + 3) & ~3
    stub = _stub(stub_va)
    if stub_va + len(stub) > tb + trs:
        raise ValueError(f"케이브 부족: 스텁 {len(stub)}B, 여유 {tb + trs - stub_va}B")
    off = raw(stub_va)
    if any(out[off:off + len(stub)]):
        raise ValueError("케이브가 비어 있지 않다")
    out[off:off + len(stub)] = stub

    # VirtualSize 를 RawSize 까지 늘려 스텁이 매핑되게 한다
    struct.pack_into("<I", out, text["hdr"] + 8, trs)     # VirtualSize = RawSize

    # 두 strcat 리터럴을 스텁으로 재지정(.reloc 이 이미 있어 재배치 안전)
    for slot in SITES:
        struct.pack_into("<I", out, raw(slot), stub_va)

    note = (f"이름 공백: 스텁 {len(stub)}B @ {stub_va:#x} · "
            f"strcat 리터럴 {len(SITES)}곳 재지정")
    return bytes(out), note
