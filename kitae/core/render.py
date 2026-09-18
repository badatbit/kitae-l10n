# -*- coding: utf-8 -*-
"""게임 폰트로 텍스트를 그려 실제 표시를 미리 본다.

엔진과 같은 글리프를 쓰므로, 화면에 뜨기 전에 넘침·줄바꿈·글자 모양을 확인할 수
있다. 폰트는 두 평면으로 되어 있다 — 평면 0이 본체, 평면 1이 안티에일리어스
테두리다. 게임도 둘을 겹쳐 그리므로 여기서도 같은 방식으로 합성한다.

폭 계산: 전각 24px, 반각 12px. 메시지 창은 640px 화면 안에 그려지므로 기본
줄 폭을 26전각(=624px)으로 잡았다. 인라인 마크업(`@S@`, `&主人公&`)은 표시되지
않으므로 폭에서 제외한다.
"""
import os
import re

from kitae.core.windows import MARKUP

FULL = 24
HALF = 12
LINE_H = 26

# 두 평면의 관계: 평면 1 은 평면 0 의 부분집합이고, 글자 가장자리라서 픽셀이
# 일부만 덮이는 자리를 표시한다. 그래서 평면 0 전체를 꽉 찬 흰색으로 칠하면
# 획이 1픽셀씩 굵어진다. 안쪽(평면0 - 평면1)만 꽉 채우고 가장자리는 옅게 얹어야
# 게임과 같은 두께가 된다.
BODY = (255, 255, 255)
SHADOW = (0, 0, 0)
EDGE_ALPHA = 110        # 가장자리 픽셀의 덮임 정도
SHADOW_ALPHA = 200
SHADOW_EDGE_ALPHA = 90
SHADOW_OFFSET = (3, 3)
# 흰 글자와 검은 그림자가 동시에 보이도록 중간 밝기 배경을 기본으로 둔다.
BG = (118, 122, 130)


def _codes(text, cp, widths=None):
    """표시되는 (바이트열, 폭) 목록. 마크업은 건너뛴다. 글리프 단위는 hangul.units
    (합자 = 셀 하나), 폭은 widths(kitae.build.widths.Widths)가 있으면 그 값, 없으면 24/12."""
    from kitae.build.hangul import units
    out = []
    for u, mk in units(text):
        if mk:
            continue
        if u in cp:
            out.append((bytes(cp[u]), widths.width(u) if widths else FULL))
            continue
        if u in ("\u2003", "\u3000"):
            out.append((b"\x81\x40", widths.width(u) if widths else FULL))
            continue
        try:
            b = u.encode("cp932")
        except UnicodeEncodeError:
            out.append((None, FULL))          # 폰트에 없는 글자
            continue
        out.append((b, widths.width(u) if widths else (FULL if len(b) == 2 else HALF)))
    return out


def measure(text, cp, widths=None):
    """표시 폭(px)."""
    return sum(w for _, w in _codes(text, cp, widths))


def wrap(text, cp, width_px, widths=None):
    """폭에 맞춰 자른 줄 목록. 게임은 자동 개행을 하지 않으므로 확인용이다."""
    lines, cur, used = [], [], 0
    for code, w in _codes(text, cp, widths):
        if used + w > width_px and cur:
            lines.append(cur)
            cur, used = [], 0
        cur.append((code, w))
        used += w
    if cur:
        lines.append(cur)
    return lines or [[]]


def draw(lines, font, width_px, pad=8, bg=BG):
    """줄 목록(‘_codes’ 결과)을 이미지로."""
    from PIL import Image

    h = pad * 2 + LINE_H * len(lines)
    img = Image.new("RGB", (width_px + pad * 2, h), bg)
    dx, dy = SHADOW_OFFSET

    def _planes(code, w):
        """(안쪽 마스크, 가장자리 마스크). 안쪽 = 평면0 - 평면1."""
        try:
            p0 = font.get_glyph(code, plane=0).crop((0, 0, w, FULL)).convert("L")
        except Exception:
            return None, None
        try:
            p1 = font.get_glyph(code, plane=1).crop((0, 0, w, FULL)).convert("L")
        except Exception:
            p1 = None
        if p1 is None:
            return p0, None
        from PIL import ImageChops
        return ImageChops.subtract(p0, p1), p1

    def _at(alpha):
        return lambda v: alpha if v else 0

    for row, line in enumerate(lines):
        x, y = pad, pad + row * LINE_H
        for code, w in line:
            if code is None:                       # 폰트에 없는 글자
                img.paste((150, 60, 60), (x + 2, y + 2, x + w - 2, y + FULL - 2))
                x += w
                continue
            core, edge = _planes(code, w)
            if core is None:
                x += w
                continue
            img.paste(SHADOW, (x + dx, y + dy), core.point(_at(SHADOW_ALPHA)))
            if edge is not None:
                img.paste(SHADOW, (x + dx, y + dy),
                          edge.point(_at(SHADOW_EDGE_ALPHA)))
            img.paste(BODY, (x, y), core.point(_at(255)))
            if edge is not None:
                img.paste(BODY, (x, y), edge.point(_at(EDGE_ALPHA)))
            x += w
    return img


def render(text, font, cp=None, width=26 * FULL, pad=8, bg=BG, widths=None):
    """문자열 하나를 그린다 (필요하면 줄바꿈). widths 를 주면 가변폭으로."""
    return draw(wrap(text, cp or {}, width, widths), font, width, pad, bg)


def label_strip(text, width, height=18, fg=(150, 160, 180), bg=BG):
    """패널 위에 붙일 설명 줄 — 시스템 폰트로 그린다(게임 폰트가 아님)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (width, height), bg)
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("malgun.ttf", 12)
    except Exception:
        f = ImageFont.load_default()
    d.text((4, 2), text, font=f, fill=fg)
    return img


def side_by_side(panels, gap=12, bg=BG):
    """[(제목, 이미지), …] 를 가로로 잇는다."""
    from PIL import Image
    titled = []
    for title, im in panels:
        strip = label_strip(title, im.width)
        box = Image.new("RGB", (im.width, strip.height + im.height), bg)
        box.paste(strip, (0, 0))
        box.paste(im, (0, strip.height))
        titled.append(box)
    w = sum(p.width for p in titled) + gap * (len(titled) - 1)
    h = max(p.height for p in titled)
    out = Image.new("RGB", (w, h), bg)
    x = 0
    for p in titled:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def stack(images, gap=6, bg=BG):
    from PIL import Image
    w = max(i.width for i in images)
    h = sum(i.height for i in images) + gap * (len(images) - 1)
    out = Image.new("RGB", (w, h), bg)
    y = 0
    for i in images:
        out.paste(i, (0, y))
        y += i.height + gap
    return out
