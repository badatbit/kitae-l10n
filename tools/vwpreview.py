# -*- coding: utf-8 -*-
"""가변폭 미리보기 — 굽기 전에 폭 표를 눈으로 확인한다.

    python tools/vwpreview.py

값은 전부 `kitae/build/widths.py` 에서 온다. **여기서 값을 정하지 않는다** —
두 군데 적으면 갈린다. 바꾸려면 그 모듈을 고친다.

결과는 `tmp/vwNNN.png` (번호가 올라간다). 위가 원본(전각 고정 24px), 아래가 제안.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont       # noqa: E402
from kitae.config import Config                   # noqa: E402
from kitae.build.widths import CELL, Widths       # noqa: E402

SAMPLE = ["토마코마이",
          "코토리는　무척　즐거워　보인다。",
          "８월３일　아침・・・오늘도　날씨는　좋다。",
          "『붉은　벽돌』이라　불리는　이　건물은",
          "２０００엔으로　저렴하다。１２３４５",
          "ＪＲ　삿포로역에서　１０분　（무료）",
          "있잖아　오빠。징기스칸　좋아해？",
          "태평양・한국해・그리고　오호츠크해。",
          "동쪽　끝의　１４７．２ｍ　ＴＶ탑。"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="안 주면 tmp/vwNNN.png 로 번호가 올라간다")
    a = ap.parse_args()

    cfg = Config.load()
    W = Widths(cfg)
    f = W.font
    small = ImageFont.truetype(cfg.path(cfg["font"]["ttf"]), 15)

    def render(lines, variable):
        wpx = CELL * 27
        img = Image.new("L", (wpx, (CELL + 6) * len(lines)), 0)
        d = ImageDraw.Draw(img)
        y = 0
        for s in lines:
            x = 0
            for ch in s:
                if variable:
                    g, ox, adv = W.shape(ch), W.offset(ch), W.width(ch)
                else:
                    g = ch
                    b = d.textbbox((0, 0), ch, font=f)
                    ox, adv = (CELL - (b[2] - b[0])) // 2 - b[0], CELL
                d.text((x + ox, y + W.baseline), g, font=f, fill=255, anchor="ls")
                x += adv
            y += CELL + 6
        return img.crop((0, 0, wpx, y))

    def label(txt):
        im = Image.new("L", (CELL * 27, 20), 0)
        ImageDraw.Draw(im).text((2, 2), txt, font=small, fill=170)
        return im

    parts = [label("원본 (전각 고정 24px)"), render(SAMPLE, False),
             label("제안 (kitae/build/widths.py)"), render(SAMPLE, True)]
    h = sum(p.height for p in parts) + 8 * len(parts)
    out = Image.new("L", (CELL * 27, h), 0)
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height + 8

    if a.out:
        path = cfg.path(a.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
    else:
        d = cfg.path("tmp")
        os.makedirs(d, exist_ok=True)
        n = 1 + max([int(x[2:5]) for x in os.listdir(d)
                     if x.startswith("vw") and x[2:5].isdigit()] or [0])
        path = os.path.join(d, f"vw{n:03d}.png")
    out.save(path)
    for s in SAMPLE:
        print(f"  {sum(W.width(c) for c in s):>4}px ← {len(s) * CELL:>4}px   {s}")
    print(path)


if __name__ == "__main__":
    main()
