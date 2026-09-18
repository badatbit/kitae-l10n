# -*- coding: utf-8 -*-
"""글리프 셀 목록과 글자별 전진폭 — **단일 출처**.

규칙은 [docs/KO-TEXT-RULES.md](../../docs/KO-TEXT-RULES.md). 폰트를 굽는 쪽(`hangul.inject`),
스텁이 읽는 폭표(`vwstub.build_table`), 검사기(`kitae check`), 미리보기(`kitae render`)가 전부
여기 값을 본다. 갈리면 화면이 통째로 틀어지므로 값을 두 군데 적지 않는다.

## 어떤 글리프가 셀을 받나 (2026-09-18)

  * 한글 완성형 — 번역에 실제로 쓰인 글자만(`hangul.assign`).
  * **ASCII** U+0021~U+007E — 엔진의 1바이트 처리(고정 12px)를 피하려고 2바이트 셀에
    재할당한다. 마크업 문자 `@ & % * $` 는 제외(그건 텍스트가 아니라 제어 코드).
  * 공백 셋: `' '`(어절, SPACE), EN SPACE(U+2002, 반각 12), EM SPACE(U+2003, 전각 24) — 셋 다
    전용 셀. 게임의 전각 공백 0x8140(U+3000)은 보호 항목(uipatch.is_fixed, raw 인코딩)에만
    남는데 폭은 **EN 과 같은 12** — 24 의 절반이라 반각 단위로 가운데 정렬을 맞출 수 있다
    (메뉴 라벨 `시스템　설정`, 예/아니요 칸 맞춤). 9 로 두면 정렬 계산이 안 맞는다(사용자 지시).
  * **합자** `LIGATURES` — `". "` 처럼 두 글자를 한 셀에. 글자 수(타이밍·줄 길이)를
    아끼려는 것. 텍스트는 두 글자 그대로 적고 인코더가 셀로 바꾼다.

## 폭을 어떻게 정하나

    한글          24      글꼴 상자(22)보다 넓게 — 25px 래스터가 23px 까지 나온다
    ' '            9      Plex 의 6 은 어절이 붙어 보인다
    EN / EM       12/24
    FOUR-PER-EM    6      U+2005 — EM 의 1/4. 제목 라벨 가운데 정렬의 반 EN 보정(`시스템 설정`: 앞 18px)
    FIGURE SPACE  = 숫자 폭(16) — 한 자리 월·일 앞자리 패딩
    숫자           고정폭  = 글꼴의 숫자 전진폭 +1 (Plex 는 tabular, 25px 에서 15+1=16 —
                          15 로는 숫자 오른쪽 끝이 미묘하게 잘려 보인다, 2026-09-19 지시)
    ASCII 나머지    글꼴 전진폭 그대로(사이드베어링 포함) — 여백 보정 없음
    `²` U+00B2     글꼴 전진폭(9) — 가이드 면적 `km²`. `㎢` 는 Plex 에서 44px 라 한 칸에 못 넣는다
    합자           구성 글자 폭의 합
    `・`           22      말줄임(・・・)·나열 겸용, 칸 가운데
    `⧵` U+29F5     24      선택지 구분 기호(시스템 설정 행) — 엔진이 24 고정 피치로 커서 상자를
                          두는 행에서 ASCII `/` 모양을 24 칸 가운데에. 그 행은 공백도 EM, 숫자도 전각
    그 밖(전각 기호·전각 로마자) 24  게임 원래 글리프, 고정폭

옛 보정(`。`=잉크+9, `．`=잉크−1, `『` 좌+1/우−1, 따옴표 12)은 없앴다 — 여백은 텍스트의
공백이 맡는다. 전각 로마자는 고정폭 영역(`Ａ 버튼`)에서만 쓰므로 게임 글리프 24 그대로.
"""
import functools

CELL = 24                     # 글리프 상자(px) = 전진폭 상한
HANGUL = 24
SPACE = 9                     # ' ' 어절 공백
EN = 12                       # U+2002 EN SPACE
EM = 24                       # U+2003 EM SPACE (전용 셀)
EN_SPACE, EM_SPACE, IDEO_SPACE = " ", " ", "　"
FOUR_PER_EM_SPACE = " "  # 6px — 반 EN. 메뉴 라벨을 반각 단위로 못 맞출 때(제목 `시스템 설정`)
Q4 = 6
FIGURE_SPACE = " "       # 숫자 폭의 공백 — 한 자리 월·일의 앞자리 패딩(저장 슬롯 날짜)
MID = "・"
MID_W = 22
SEP24 = "\u29f5"              # 선택지 구분 기호 — ASCII 슬래시 모양을 24 칸 가운데(고정 피치 행용)
DIGITS = "0123456789"
DIGIT_PAD = 1                 # 숫자 고정폭 = 글꼴 전진폭 + 1 (오른쪽 끝 잘림 방지)
MARKUP_CHARS = "@&%*$"        # 제어 코드 문자 — 글자로 쓰려면 전각 ％＆＊＠＄
FONT_ADV = "²"                # ASCII 밖인데 글꼴 전진폭을 쓰는 라틴 기호 (km²)

ASCII_CELLS = tuple(chr(c) for c in range(0x21, 0x7F) if chr(c) not in MARKUP_CHARS)
LIGATURES = (". ", ", ", "! ", "? ", ": ", " (", ") ")
# 폰트 셀이 필요한 비한글 글리프 전부 (hangul.SYMBOL_PAGE 에 이 순서로 붙는다)
SYMBOL_CELLS = (" ", EN_SPACE, EM_SPACE, SEP24, FIGURE_SPACE, FOUR_PER_EM_SPACE) + ASCII_CELLS + LIGATURES + tuple(FONT_ADV)

# 칸에 실제로 그릴 모양이 문자와 다른 것. REDRAW 는 그중 게임 cp932 칸을 덮어 그리는 것.
SHAPE = {MID: "·", SEP24: "/"}
REDRAW = (MID,)


def is_ascii_cell(ch):
    return len(ch) == 1 and 0x21 <= ord(ch) < 0x7F


class Widths:
    """폰트 하나에 대한 폭·잉크 계산. `cfg` 의 TTF 와 크기를 쓴다."""

    def __init__(self, cfg):
        from PIL import ImageFont
        self.size = int(cfg["font"].get("size", 21))
        self.font = ImageFont.truetype(cfg.path(cfg["font"]["ttf"]), self.size)
        asc, desc = self.font.getmetrics()
        # 세로는 글자마다 맞추지 않는다 — 한 기준선에 올린다
        self.baseline = (CELL - (asc + desc)) // 2 + asc

    @functools.lru_cache(maxsize=4096)
    def ink(self, ch):
        """(왼쪽, 오른쪽) 잉크 경계. 펜 원점 기준."""
        from PIL import Image, ImageDraw
        im = Image.new("L", (CELL * 3, CELL * 3), 0)
        ImageDraw.Draw(im).text((CELL, CELL), ch, font=self.font,
                                fill=255, anchor="ls")
        b = im.getbbox()
        return (0, 0) if b is None else (b[0] - CELL, b[2] - CELL)

    def ink_w(self, ch):
        lo, hi = self.ink(ch)
        return hi - lo

    @functools.lru_cache(maxsize=4096)
    def adv(self, s):
        """글꼴의 전진폭(px, 반올림) — 사이드베어링 포함."""
        return int(round(self.font.getlength(s)))

    @functools.lru_cache(maxsize=1)
    def digit_w(self):
        return max(self.adv(d) for d in DIGITS) + DIGIT_PAD

    def shape(self, ch):
        """그 칸에 실제로 그릴 모양."""
        return SHAPE.get(ch, ch)

    def width(self, ch):
        """전진폭(px). 1~CELL. 합자는 구성 글자 폭의 합."""
        if ch in LIGATURES:
            w = sum(self.width(c) for c in ch)
        elif ch == " ":
            w = SPACE
        elif ch == EN_SPACE:
            w = EN
        elif ch == EM_SPACE:
            w = EM
        elif ch == FIGURE_SPACE:
            w = self.digit_w()
        elif ch == FOUR_PER_EM_SPACE:
            w = Q4
        elif ch == IDEO_SPACE:              # 0x8140 — 보호 항목의 전각 공백 = EN(반각 단위 정렬)
            w = EN
        elif ch == MID:
            w = MID_W
        elif ch == SEP24:
            w = CELL
        elif ch in DIGITS:
            w = self.digit_w()
        elif is_ascii_cell(ch) or ch in FONT_ADV:
            w = self.adv(ch)
        elif "가" <= ch <= "힣":
            w = HANGUL
        else:
            w = CELL                        # 게임 글리프(전각 기호·전각 로마자)
        return max(1, min(CELL, w))

    def offset(self, ch):
        """잉크를 펜에서 얼마나 밀어 그릴지 (가로만). 기본은 글꼴 원점 그대로."""
        if ch in (MID, SEP24):                # 칸 가운데
            lo, hi = self.ink(self.shape(ch))
            return max(0, (self.width(ch) - (hi - lo)) // 2) - lo
        # 한글: 글꼴이 이미 사이드베어링을 갖고 있다(`긱` 2 · `거` 1 · `굛` 0 —
        # 디자이너가 글자마다 정한 것). ASCII·합자도 같은 이유로 손대지 않는다.
        return 0
