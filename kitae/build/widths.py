# -*- coding: utf-8 -*-
"""글자별 전진폭 — **단일 출처**.

폰트를 굽는 쪽(글리프 위치)과 스텁이 읽는 표(전진폭)가 여기서 같은 값을 본다.
갈리면 화면이 통째로 틀어지므로 값을 두 군데 적지 않는다.

## 왜 잉크를 실측하는가

`ImageFont.getlength`·`textbbox` 는 **여백까지 포함한 상자**를 준다. 점(`.`)이
７px 로 나오는데 실제 잉크는 ４px 다. 그걸 모르고 사이드베어링을 잡았다가
`１４７．２` 가 벌어져 보였고, 고치고 나니 이번엔 `ＪＲ` 이 겹쳤다. 그래서
**직접 그려서 잰다.**

## 전각 칸에 반각 모양을 그린다

`０`·`。` 의 게임 원본 글리프는 １em 을 꽉 채운다. 폭만 좁히면 이웃과 겹치므로
그 칸에는 반각 모양(`0`·`.`)을 다시 그려 넣는다. `SHAPE` 가 그 대응이다.

## 값을 어떻게 정했나 (2026-08-09, 화면 비교로 확정)

    한글          22      Plex 실측 어드밴스(21)보다 １px 넓게 — 붙어 보이지 않게
    공백 `　`       9      Plex 값 ６ 은 어절이 붙어 보인다
    `。` `、`      잉크+9   문장부호 뒤에는 반각 공백만큼 숨을 둔다
    `．` `.` `，` `,`  잉크−1   **소수점·URL 은 숫자에 붙어야 한다**
    `・`           22      말줄임(・・・)과 나열(태평양・동해)을 겸하므로 가운데 정렬
    `『`          잉크+0   여는 쌍따옴표만 좌+1/우−1
    `』` `「` `」`    12
    숫자·알파벳     잉크+2   좌+1/우+1

`。` 가 줄 끝일 때는 뒤 여백이 필요 없지만 **넣지 않았다.** 스텁은 글자 코드만
보므로 줄 끝인지 모르고, 그 여백은 어차피 화면에 안 보인다. 클릭 대기 삼각형이
어긋나 보이면 그때 넣는다(루프에 인덱스 `r11` 과 개수가 다 있다).
"""
import functools

CELL = 24

# 전각 코드 → 그 칸에 실제로 그릴 모양
SHAPE = {"　": " ", "。": ".", "、": ",", "・": "·", "！": "!", "？": "?", "：": ":",
         "／": "/", "（": "(", "）": ")", "＋": "+", "－": "-", "％": "%", "～": "~",
         "「": "‘", "」": "’", "『": "“", "』": "”", "．": "."}
for _i in range(10):
    SHAPE[chr(0xFF10 + _i)] = chr(0x30 + _i)
for _i in range(26):
    SHAPE[chr(0xFF21 + _i)] = chr(0x41 + _i)
    SHAPE[chr(0xFF41 + _i)] = chr(0x61 + _i)

HANGUL = 22
SPACE = 9
SENT = "。、"                     # 뒤에 반각 공백
DEC = "．.，,"                    # 숫자에 붙는다
MID = "・"
QUOTE = "』「」"                  # 고정폭
QOPEN = "『"                      # 좌+1 / 우−1
CENTERED = MID + "「」"           # 좁은 칸 안에서 가운데
LATIN = set("０１２３４５６７８９")
LATIN |= {chr(0xFF21 + i) for i in range(26)} | {chr(0xFF41 + i) for i in range(26)}

QUOTE_W = 12
MID_W = 22
LATIN_L, LATIN_R = 1, 1
QOPEN_L, QOPEN_R = 1, -1
DEC_L, DEC_R = -2, 1


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

    def shape(self, ch):
        """그 칸에 실제로 그릴 모양."""
        return SHAPE.get(ch, ch)

    def width(self, ch):
        """전진폭(px). 1~CELL."""
        g = self.shape(ch)
        if ch in SENT:
            w = self.ink_w(g) + SPACE
        elif ch in DEC:
            w = self.ink_w(g) + DEC_L + DEC_R
        elif ch in QOPEN:
            w = self.ink_w(g) + QOPEN_L + QOPEN_R
        elif ch in LATIN:
            w = self.ink_w(g) + LATIN_L + LATIN_R
        elif ch == "　":
            w = SPACE
        elif ch == MID:
            w = MID_W
        elif ch in QUOTE:
            w = QUOTE_W
        elif "가" <= ch <= "힣":
            w = HANGUL
        else:
            w = self.ink_w(g) + 2
        return max(1, min(CELL, w))

    def offset(self, ch):
        """잉크를 펜에서 얼마나 밀어 그릴지 (가로만)."""
        g = self.shape(ch)
        lo, hi = self.ink(g)
        if ch in DEC:
            return DEC_L - lo
        if ch in QOPEN:
            return QOPEN_L - lo
        if ch in LATIN:
            return LATIN_L - lo
        if ch in CENTERED:
            return max(0, (self.width(ch) - (hi - lo)) // 2) - lo
        return -lo                       # 펜(좌측) 정렬
