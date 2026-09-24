# -*- coding: utf-8 -*-
"""한글 입력기(IME) — 이름 입력 화면(TRFNAMEIN)에 두벌식 자모 입력. 근거·설계: docs/IME.md

1단계(이 파일, 빌드 쪽): 글꼴에 완성형 + 자모 40자를 넣고, かな 격자 표(90칸)를 자모로
바꾸고, 음절→셀 직접 표를 TRFNAMEIN `.rdata` 클래스명 슬롯 꼬리에 심는다.
2단계(kitae/build/imestub.py): PutChar(0x10001000) 훅 + 두벌식 오토마타 SH4 스텁 — 아래 `Composer` 를 옮긴 것.

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


# ───────────────────────────────────────────────────────────────────────────────
# 두벌식 오토마타 — 파이썬 참조 구현. 2단계 SH4 스텁은 이 규칙을 그대로 옮긴다.
# 상태 = (커서, 초성, 중성, 종성) 인덱스(없으면 None). 결과는 "쓰기" 동작 목록:
#   ("put", 글자, advance)  — 커서 칸에 글자를 쓰고 advance 면 커서를 한 칸 넘긴다(PutChar 와 같다)
JONG = [None] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")   # 종성 28 (0 = 없음)
CHO2JONG = [JONG.index(c) if c in JONG else 0 for c in JAMO_CHO]          # ㄸㅃㅉ → 0
JONG2CHO = [JAMO_CHO.index(c) if (c is not None and c in JAMO_CHO) else None for c in JONG]   # 겹받침·없음 → None
_DOUBLE = {("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ",
           ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ",
           ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ"}
DOUBLE_JONG = {(JONG.index(a), JAMO_CHO.index(b)): JONG.index(r) for (a, b), r in _DOUBLE.items()}
# 종성 → (남는 종성, 떨어져 나가는 초성): 겹받침은 둘로, 홑받침은 (0, 그 초성)
SPLIT_JONG = {JONG.index(r): (JONG.index(a), JAMO_CHO.index(b)) for (a, b), r in _DOUBLE.items()}
for _i, _c in enumerate(JONG):
    if _i and _i not in SPLIT_JONG:
        SPLIT_JONG[_i] = (0, JAMO_CHO.index(_c))
_DIPH = {("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ",
         ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ"}
DIPH = {(JAMO_JUNG.index(a), JAMO_JUNG.index(b)): JAMO_JUNG.index(r) for (a, b), r in _DIPH.items()}
UNDIPH = {r: a for (a, _b), r in DIPH.items()}          # 복모음 → 앞 모음 (삭제용)


def compose(cho, jung, jong=0):
    return chr(0xAC00 + (cho * 21 + jung) * 28 + (jong or 0))


class Composer:
    """이름 바 커서 하나를 따라가는 조합 상태. `feed(자모)`·`delete()` 가 put 동작 목록을 낸다.

    `baked(글자)` 가 False 인 음절(글꼴에 없음)은 받침으로 만들지 않고, 지금 칸을 확정한 뒤 그 자음을
    새 초성으로 삼는다 — 「철」+ㅅ 은 「첧」이 완성형에 없으니 「철」 확정 후 「ㅅ」(→「철수」).
    SH4 스텁(imestub)의 FAIL → C_COMMIT 과 같은 규칙."""

    def __init__(self, baked=None):
        self.cursor = None                      # 상태가 붙어 있는 커서 칸 (None = 쉼)
        self.cho = self.jung = self.jong = None
        self.baked = baked or (lambda ch: True)

    def _reset(self):
        self.cursor = None
        self.cho = self.jung = self.jong = None

    def _cur(self):
        if self.jung is None:
            return JAMO_CHO[self.cho]
        return compose(self.cho, self.jung, self.jong or 0)

    def feed(self, cursor, ch):
        """자모 `ch` 입력. 커서가 상태와 다르면 새로 시작한다."""
        if self.cursor != cursor:
            self._reset()
            self.cursor = cursor
        acts = []

        def commit():                            # 지금 칸을 확정하고 커서를 넘긴다
            acts.append(("put", self._cur(), True))
            self.cursor = cursor + 1
            self.cho = self.jung = self.jong = None

        if ch in JAMO_CHO:
            c = JAMO_CHO.index(ch)
            if self.cho is None:
                self.cho = c
            elif self.jung is None:                          # 초성만 있는데 또 자음
                commit(); self.cho = c
            elif self.jong is None:
                jg = CHO2JONG[c]
                if jg and self.baked(compose(self.cho, self.jung, jg)): self.jong = jg
                else: commit(); self.cho = c
            else:
                dj = DOUBLE_JONG.get((self.jong, c))
                if dj and self.baked(compose(self.cho, self.jung, dj)): self.jong = dj
                else: commit(); self.cho = c
            acts.append(("put", self._cur(), False))
            return acts
        v = JAMO_JUNG.index(ch)
        if self.cho is None:                                 # 홀로 선 모음: 그대로 쓰고 넘긴다
            acts.append(("put", ch, True)); self._reset(); return acts
        if self.jung is None:
            self.jung = v
        elif self.jong is None:
            dv = DIPH.get((self.jung, v))
            if dv: self.jung = dv
            else:
                commit(); acts.append(("put", ch, True)); self._reset(); return acts
        else:                                                # 도깨비불: 받침이 다음 초성으로
            rest, moved = SPLIT_JONG[self.jong]
            self.jong = rest or None
            commit()
            self.cho, self.jung = moved, v
        acts.append(("put", self._cur(), False))
        return acts

    def delete(self, cursor):
        """X: 조합 중이면 자모 하나만 뺀다. 아니면 None(게임 원래 삭제에 맡김)."""
        if self.cursor != cursor or self.cho is None:
            self._reset(); return None
        if self.jong is not None:
            self.jong = SPLIT_JONG[self.jong][0] or None
        elif self.jung is not None:
            self.jung = UNDIPH.get(self.jung)
        else:
            self._reset(); return [("put", None, False)]        # 빈칸으로
        return [("put", self._cur(), False)]


def _selftest():
    def run(keys, dels=()):
        cp_, cur, cells = Composer(), 0, {}
        for k in keys:
            for kind, ch, adv in cp_.feed(cur, k):
                cells[cur] = ch
                if adv: cur += 1
        return "".join(cells[i] for i in sorted(cells))
    cases = {"ㄱㅏㅁㅏ": "가마", "ㅎㅏㄴㄱㅡㄹ": "한글", "ㄱㅗㅏ": "과", "ㅂㅏㄹㄱ": "밝", "ㅂㅏㄹㄱㅡㄴ": "발근",
             "ㅇㅣㅆㅏ": "이싸", "ㄱㄱㅏ": "ㄱ가", "ㅏㄱ": "ㅏㄱ", "ㅇㅜㅣ": "위", "ㄷㅏㄹㄱ": "닭", "ㅅㅓㅜㄹ": "서ㅜㄹ"}
    for k, want in cases.items():
        got = run(k)
        assert got == want, (k, got, want)
    ks = {c for c in chars() if "가" <= c <= "힣"}
    cp_ = Composer(baked=ks.__contains__); cur, cells = 0, {}
    for k in "ㅊㅓㄹㅅㅜ":
        for _kind, ch, adv in cp_.feed(cur, k):
            cells[cur] = ch
            if adv: cur += 1
    assert "".join(cells[i] for i in sorted(cells)) == "철수", cells
    c = Composer(); c.feed(0, "ㄷ"); c.feed(0, "ㅏ"); c.feed(0, "ㄹ"); c.feed(0, "ㄱ")
    assert c.delete(0) == [("put", "달", False)] and c.delete(0) == [("put", "다", False)]
    assert c.delete(0) == [("put", "ㄷ", False)] and c.delete(0) == [("put", None, False)]
    return "오토마타 참조 구현 OK"


if __name__ == "__main__":
    print(_selftest())
