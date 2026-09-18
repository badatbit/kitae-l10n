# -*- coding: utf-8 -*-
"""한국어 텍스트 규칙(docs/KO-TEXT-RULES.md)의 판정 — 변환기와 검사기가 **같은 함수**를 쓴다.

  * `bad_chars`      §1 문자 집합 밖의 글자
  * `fix_spacing` / `space_violations`   §2-2·3 `. , ! ? :` 뒤 공백, 줄 끝 공백 없음
  * `line_glyphs` / `line_px`             §4 줄 길이(글리프 수·픽셀), 이름 토큰 8

마크업(`@..@` `&..&` `%N%` `*N` `$N`)은 보이지 않으므로 전부 제외하고 본다.
"""
import collections
import re

from kitae.core.windows import MARKUP_ALL

EN_SPACE, EM_SPACE, IDEO_SPACE, FIGURE_SPACE = " ", " ", "　", " "
PUNCT = ".,!?:"                      # 뒤에 공백이 오는 문장부호
CLOSERS = ")』」>・'\""              # 이 앞에는 공백을 넣지 않는다
SPACES = " " + EN_SPACE + EM_SPACE + FIGURE_SPACE
_ALNUM = re.compile(r"[0-9A-Za-z]")

LIMIT_GLYPHS = 25                    # 엔진 레코드 한도 (vw_extension=false)
LIMIT_GLYPHS_EXT = 62                # vw_extension=true
LIMIT_PX = 600
NAME_TOKEN = "&主人公名前&"
NAME_GLYPHS = 8                      # 성 4 + 공백 1 + 이름 3

ALLOWED_SYMBOLS = set("『』「」・―ー○△▼☆◎♂♀●〒§※■□♪×ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ\u29f5²")   # U+29F5 = 24px 구분 기호, ² = km²(글꼴 전진폭)   # ー 는 장음(대사 114곳)
FW_ROMAN = {chr(0xFF21 + i) for i in range(26)} | {chr(0xFF41 + i) for i in range(26)}
FW_MARK = set("％＆＊＠＄")          # 마크업과 겹치는 문자의 전각형


def is_hangul(ch):
    o = ord(ch)
    return 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F


def allowed(ch):
    """문자 집합(§1). 한자·키릴·그리스는 게임 글리프(24)라 허용 — 퀴즈의 지명 읽기,
    留根算酢(르네상스) 같은 말장난, 타냐의 러시아어가 의도적으로 쓴다. 가나는 미번역 흔적이라
    막는다(장음 ー 만 예외)."""
    o = ord(ch)
    return (is_hangul(ch) or 0x20 <= o < 0x7F or ch == "\n" or ch in SPACES
            or ch in ALLOWED_SYMBOLS or ch in FW_ROMAN or ch in FW_MARK
            or 0x4E00 <= o <= 0x9FFF or 0x0400 <= o <= 0x04FF or 0x0370 <= o <= 0x03FF)


def visible(text):
    """마크업을 뺀 텍스트."""
    return MARKUP_ALL.sub("", text)


def bad_chars(text):
    """{글자: 횟수} — 문자 집합 밖. U+3000 도 여기 잡힌다."""
    return collections.Counter(ch for ch in visible(text) if not allowed(ch))


def _seq(text):
    """마크업 밖 글자들의 [(위치, 글자)]."""
    out, pos = [], 0
    for m in MARKUP_ALL.finditer(text):
        out += [(i, text[i]) for i in range(pos, m.start())]
        pos = m.end()
    out += [(i, text[i]) for i in range(pos, len(text))]
    return out


def _wants_space(prev, c, nxt):
    if c not in PUNCT or nxt is None:
        return False
    if nxt in SPACES or nxt == "\n" or nxt in PUNCT or nxt in CLOSERS:
        return False
    # 토큰 안의 구분점: 12:31, 1.5, a.b, 1,000 — 양쪽이 영숫자면 공백 없음
    if c in ".,:" and prev is not None and _ALNUM.match(prev) and _ALNUM.match(nxt):
        return False
    return True


def _insert_points(text):
    seq = _seq(text)
    pts = set()
    for k, (pos, ch) in enumerate(seq):
        prev = seq[k - 1][1] if k else None
        nxt = seq[k + 1][1] if k + 1 < len(seq) else None
        if _wants_space(prev, ch, nxt):
            pts.add(pos + 1)
    return pts


def fix_spacing(text):
    """`. , ! ? :` 뒤에 공백을 넣고 줄 끝 공백을 지운다."""
    pts = _insert_points(text)
    out = "".join(text[i] + (" " if i + 1 in pts else "") for i in range(len(text)))
    return "\n".join(l.rstrip(SPACES) for l in out.split("\n"))


def space_violations(text):
    """[(줄 번호, 문제)] — 공백 규칙 위반."""
    bad = []
    lines = text.split("\n")
    for pos in sorted(_insert_points(text)):
        ln = text.count("\n", 0, pos)
        bad.append((ln, f"`{text[pos - 1]}` 뒤 공백 없음"))
    for ln, l in enumerate(lines):
        if l != l.rstrip(SPACES):
            bad.append((ln, "줄 끝 공백"))
        if "  " in l:
            bad.append((ln, "어절 공백 둘 이상"))
    return bad


def line_glyphs(line):
    """한 줄의 글리프 수 — 합자는 1, 이름 토큰은 8, 그 밖의 마크업은 0."""
    from kitae.build.hangul import units
    n = sum(1 for u, mk in units(line) if not mk)
    return n + NAME_GLYPHS * line.count(NAME_TOKEN)


def line_px(line, widths):
    """한 줄의 표시 폭(px). 이름 토큰은 한글 8칸."""
    from kitae.build.hangul import units
    from kitae.build.widths import HANGUL
    px = sum(widths.width(u) for u, mk in units(line) if not mk)
    return px + NAME_GLYPHS * HANGUL * line.count(NAME_TOKEN)
