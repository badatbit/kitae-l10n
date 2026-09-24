# -*- coding: utf-8 -*-
"""한글 입력기(IME) — 이름 입력 화면(TRFNAMEIN)에 두벌식 자모 입력. 근거·설계: docs/IME.md

1단계(이 파일, 빌드 쪽): 글꼴에 완성형 + 자모 40자를 넣고, かな 격자 표(90칸)를 자모로
바꾸고, 음절→셀 직접 표를 TRFNAMEIN `.rdata` 클래스명 슬롯 꼬리에 심는다.
2단계(예정): PutChar(0x10001000) 훅 + 두벌식 오토마타 스텁.

옵션 `ime`(kitae.config.json). 켜면 코드페이지가 커지므로 조사 엔진과 같은 세이브 호환 주의.
"""
import struct

JAMO_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"        # 초성 순(19)
JAMO_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"     # 중성 순(21)
JAMO = JAMO_CHO + JAMO_JUNG                          # 40 — 셀도 이 순서로 연속이어야 한다
BLANK = 0x8140                                       # 격자 빈칸 = 전각 공백(cp932), 원본과 같다

KANA_TABLE_VA = 0x10015454     # かな 격자 90칸 u16(lead<<8|trail), 행 우선 6행×15열(5칸 블록 3개)
KANA_N = 90
KANA_HEAD = "あいうえおはひふへほがぎぐげご"   # 원본 첫 행 — 다른 빌드 방지용 대조

RDATA_VA = 0x10006000          # 256B 슬롯 클래스명 표. 블록 0~229 의 [32,256) 은 NUL 뒤라 안 읽는다
TABLE_BLOCKS = 175             # 11,172 음절 / 64 = 174.6 → 블록 0~174
TABLE_OFF, TABLE_PER = 32, 64  # 블록 안 [32,160) 에 u16 64칸
N_SYL = 19 * 21 * 28


def grid():
    """かな 격자에 놓을 90칸(행 우선). 초성은 왼쪽 블록 4행, 모음은 가운데·오른쪽 블록."""
    rows = [
        "ㄱㄲㄴㄷㄸ" + "ㅏㅐㅑㅒㅓ" + "ㅔㅕㅖㅗㅘ",
        "ㄹㅁㅂㅃㅅ" + "ㅙㅚㅛㅜㅝ" + "ㅞㅟㅠㅡㅢ",
        "ㅆㅇㅈㅉㅊ" + "ㅣ" + " " * 4 + " " * 5,
        "ㅋㅌㅍㅎ" + " " + " " * 5 + " " * 5,
        " " * 15,
        " " * 15,
    ]
    out = [ch for r in rows for ch in r]
    assert len(out) == KANA_N, len(out)
    assert sorted(c for c in out if c != " ") == sorted(JAMO)
    return out


def chars():
    """글꼴에 더 넣을 글자: KS X 1001 완성형 2,350 + 무받침·ㄹ받침 전부(각 399) + 자모 40."""
    out = set(JAMO)
    for code in range(0xB0A1, 0xC9FF):
        try:
            ch = bytes([code >> 8, code & 0xFF]).decode("euc-kr")
        except Exception:
            continue
        if "가" <= ch <= "힣":
            out.add(ch)
    for cho in range(19):
        for jung in range(21):
            for jong in (0, 8):                  # 8 = ㄹ
                out.add(chr(0xAC00 + (cho * 21 + jung) * 28 + jong))
    return out


def syllable_table(cp):
    """음절 번호(0..11171) → 셀코드(lead<<8|trail), 없으면 0."""
    tbl = [0] * N_SYL
    for ch, (lead, trail) in cp.items():
        if len(ch) == 1 and "가" <= ch <= "힣":
            tbl[ord(ch) - 0xAC00] = (lead << 8) | trail
    return tbl


def jamo_base(cp):
    """자모 40개가 연속 셀인지 확인하고 첫 셀코드를 돌려준다."""
    codes = []
    for ch in JAMO:
        if ch not in cp:
            raise ValueError(f"자모 {ch!r} 가 codepage 에 없다 — hangul.contiguous_jamo 가 안 돌았다")
        lead, trail = cp[ch]
        codes.append((lead << 8) | trail)
    if codes != list(range(codes[0], codes[0] + len(codes))):
        raise ValueError(f"자모 셀이 연속이 아니다: {[hex(c) for c in codes[:6]]}…")
    return codes[0]


def _sections(blob):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    base = struct.unpack_from("<I", blob, pe + 24 + 28)[0]
    secs = {}
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        nm = blob[o:o + 8].rstrip(bytes(1)).decode("ascii", "replace")
        vs, rva, rs, raw = struct.unpack_from("<IIII", blob, o + 8)
        secs[nm] = (base + rva, vs, raw, rs)
    return secs


def patch(cfg, blob):
    """UI 패치가 끝난 TRFNAMEIN 바이트에 (1) かな 표 → 자모, (2) 음절→셀 표를 심는다."""
    from kitae.build.hangul import _read_codepage
    cp = _read_codepage(cfg.path("data", "codepage.json"))
    base = jamo_base(cp)
    out = bytearray(blob)
    secs = _sections(out)

    # (1) かな 격자 표 → 자모 셀
    dva, dvs, draw, drs = secs[".data"]
    off = draw + (KANA_TABLE_VA - dva)
    head = struct.unpack_from("<%dH" % len(KANA_HEAD), out, off)
    got = "".join(bytes([v >> 8, v & 0xFF]).decode("cp932", "replace") for v in head)
    if got != KANA_HEAD:
        raise ValueError(f"かな 표 첫 행이 다르다: {got!r} — 다른 빌드거나 이미 패치됨")
    cells = [BLANK if ch == " " else ((cp[ch][0] << 8) | cp[ch][1]) for ch in grid()]
    struct.pack_into("<%dH" % KANA_N, out, off, *cells)

    # (2) 음절→셀 표 — .rdata 클래스명 슬롯 꼬리 [32,160) 에 64칸씩
    rva, rvs, rraw, rrs = secs[".rdata"]
    tbl = syllable_table(cp)
    baked = sum(1 for v in tbl if v)
    for bi in range(TABLE_BLOCKS):
        boff = rraw + bi * 256
        head_len = len(out[boff:boff + 32].rstrip(bytes(1)))
        if head_len >= TABLE_OFF or any(out[boff + TABLE_OFF: boff + TABLE_OFF + TABLE_PER * 2]):
            raise ValueError(f".rdata 블록 {bi} 꼬리가 비어 있지 않다(머리 {head_len}B) — 표를 심을 수 없다")
        chunk = tbl[bi * TABLE_PER:(bi + 1) * TABLE_PER]
        chunk += [0] * (TABLE_PER - len(chunk))
        struct.pack_into("<%dH" % TABLE_PER, out, boff + TABLE_OFF, *chunk)

    note = (f"IME 1단계: かな 표 90칸 → 자모(첫 셀 {base:#06x}) · 음절→셀 표 {baked}/{N_SYL} "
            f"→ .rdata 블록 0~{TABLE_BLOCKS - 1}")
    return bytes(out), note
