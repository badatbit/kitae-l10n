import os
HERE = os.path.dirname(os.path.abspath(__file__))
"""Hangul codepage: assign Korean syllables to free font cells and inject glyphs.

The engine addresses a glyph by its raw cp932 byte pair (see font.py): the lead
byte picks one of 42 pages, the trail byte (0x40..0xFC) picks one of 189 cells.
It never validates the trail byte, so any cell in a page is usable -- including
ones cp932 leaves unassigned.

So a Korean build works like this:

  1. collect the distinct Korean characters the translation actually uses
  2. hand each one a free cell in the JIS level-2 region (leads 0xE0..0xEE),
     which this game's Japanese text barely touches
  3. render it from IBM Plex Sans KR into the two 1-bpp planes of the font
  4. emit those raw byte pairs instead of cp932 when building the .SMF

The mapping is written next to the build so the same bytes are reproduced every
time; adding new characters later appends rather than reshuffles.

Usage:
    python hangul.py build KOTORI_01      # codepage + patched TRFSTRINGS.DLL
    python hangul.py preview "안녕하세요"   # render through the patched font
"""
import io, json, os, sys

from kitae.core import font as fontmod
from kitae.core import workbook

DUMP = os.path.join(HERE, "..", "dump")
BUILD = os.path.join(DUMP, "build")
CODEPAGE = os.path.join(BUILD, "codepage.json")

TTF = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                   "Microsoft", "Windows", "Fonts", "IBMPlexSansKR-Regular.otf")

# JIS level-2 / IBM-extension pages: present in the font, almost unused by this
# game's script. Ordered so the emptiest pages are consumed first.
PAGES = [0xEE, 0xED, 0xE1, 0x9B, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7,
         0xE8, 0xE9, 0xEA, 0xE0, 0x9C, 0x9D, 0x9E, 0x9F, 0x99, 0x9A]
CELLS = [c for c in range(0x40, 0xFD) if c != 0x7F]      # 188 usable trail bytes


def is_hangul(ch):
    o = ord(ch)
    return 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F


def used_cells(f):
    """Cells this game's own text already draws, so we never clobber them."""
    used = set()
    for name in ("free_cells",):
        pass
    try:
        free = set(tuple(c) for c in f.free_cells())
    except Exception:
        free = None
    return free


def load_codepage():
    if os.path.exists(CODEPAGE):
        with io.open(CODEPAGE, encoding="utf-8") as fh:
            raw = json.load(fh)
        return {k: tuple(v) for k, v in raw.items()}
    return {}


def save_codepage(cp):
    os.makedirs(BUILD, exist_ok=True)
    with io.open(CODEPAGE, "w", encoding="utf-8") as fh:
        json.dump({k: list(v) for k, v in sorted(cp.items())}, fh,
                  ensure_ascii=False, indent=0)


def assign(chars, cp=None, reserved=(), pages=None):
    """Give every new character a cell, keeping existing assignments stable."""
    cp = dict(cp or {})
    taken = set(cp.values()) | set(reserved)
    pages = pages or PAGES
    slots = ((lead, cell) for lead in pages for cell in CELLS)
    for ch in sorted(chars):
        if ch in cp:
            continue
        for s in slots:
            if s not in taken:
                cp[ch] = s
                taken.add(s)
                break
        else:
            raise RuntimeError("out of free font cells")
        slots = ((lead, cell) for lead in pages for cell in CELLS
                 if (lead, cell) not in taken)
    return cp


def render_glyph(ch, size=21, y_off=2, ttf=None):
    """24x24 grayscale of one character from IBM Plex Sans KR."""
    from PIL import Image, ImageDraw, ImageFont
    ttf = ttf or TTF
    if not os.path.exists(ttf):
        raise FileNotFoundError(ttf)
    ttf = ImageFont.truetype(ttf, size)
    img = Image.new("L", (24, 24), 0)
    d = ImageDraw.Draw(img)
    try:
        box = d.textbbox((0, 0), ch, font=ttf)
    except Exception:
        box = (0, 0, size, size)
    x = (24 - (box[2] - box[0])) // 2 - box[0]
    y = (24 - (box[3] - box[1])) // 2 - box[1] + y_off - 2
    d.text((x, y), ch, font=ttf, fill=255)
    return img


def planes(gray, solid=128, edge=40):
    """Split a grayscale glyph into the engine's body / anti-alias planes."""
    from PIL import Image
    body = gray.point(lambda v: 255 if v >= solid else 0, mode="1")
    fringe = gray.point(lambda v: 255 if edge <= v < solid else 0, mode="1")
    return body, fringe


def encode(text, cp):
    """Korean-aware replacement for `text.encode('cp932')`."""
    out = bytearray()
    for ch in text:
        if ch in cp:
            out += bytes(cp[ch])
        else:
            out += ch.encode("cp932")
    return bytes(out)


def inject(cfg, chars):
    """설정을 받아 필요한 글자만 폰트에 넣고, 패치된 DLL 경로를 돌려준다."""
    from kitae.core import font as fontmod

    out_dir = cfg.path(cfg["work_dir"], "build", "TRF")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, "TRFSTRINGS.DLL")

    f = fontmod.Font()
    pages = [int(p) for p in cfg["font"].get("pages") or PAGES]
    allowed = {(l, c) for l in pages for c in CELLS}
    try:
        free = {tuple(c) for c in f.free_cells()}
        reserved = {s for s in allowed if s not in free}
    except Exception:
        reserved = set()

    cp_path = os.path.join(cfg.data_dir, "codepage.json")
    cp = _read_codepage(cp_path)
    cp = assign(chars, cp, reserved, pages)
    _write_codepage(cp_path, cp)

    ttf = cfg.path(cfg["font"]["ttf"]) if cfg["font"].get("ttf") else TTF
    size = int(cfg["font"].get("size", 21))
    yoff = int(cfg["font"].get("y_offset", 2))
    for ch in sorted(chars):
        body, fringe = planes(render_glyph(ch, size, yoff, ttf))
        code = bytes(cp[ch])
        f.set_glyph(code, body, 0)
        f.set_glyph(code, fringe, 1)
    f.save(dst)
    return dst


def decode(data, cp):
    """`encode` 의 역 — 배정된 칸을 한글로 되돌린다.

    게임 바이트를 사람이 읽으려면 필요하다. cp932 로 그냥 읽으면 배정된 칸이
    엉뚱한 한자로 보여서 빌드 결과를 눈으로 확인할 수 없다.
    """
    rev = {bytes(v): k for k, v in cp.items()}
    out, i, n = [], 0, len(data)
    while i < n:
        two = data[i:i + 2]
        if two in rev:
            out.append(rev[two])
            i += 2
            continue
        lead = data[i]
        w = 2 if (0x81 <= lead <= 0x9F or 0xE0 <= lead <= 0xFC) and i + 1 < n else 1
        out.append(data[i:i + w].decode("cp932", "replace"))
        i += w
    return "".join(out)


def decoder(cfg):
    """게임 바이트를 읽을 수 있는 문자열로 바꾸는 함수."""
    cp = _read_codepage(os.path.join(cfg.data_dir, "codepage.json"))

    def dec(data):
        return decode(data, cp)
    return dec


def encoder(cfg):
    """번역문을 게임 바이트로 바꾸는 함수. cp932 + 배정된 한글 칸."""
    cp = _read_codepage(os.path.join(cfg.data_dir, "codepage.json"))

    def enc(text):
        return encode(text, cp)
    return enc


def _read_codepage(path):
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            return {k: tuple(v) for k, v in json.load(fh).items()}
    return {}


def _write_codepage(path, cp):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump({k: list(v) for k, v in sorted(cp.items())}, fh,
                  ensure_ascii=False, indent=0)


def build(script):
    rows = workbook.load(script)
    chars = {c for r in rows.values() for c in (r.get("target") or "")
             if is_hangul(c)}
    print(f"{script}: {len(chars)} distinct Hangul characters in the translation")
    if not chars:
        print("  (nothing translated yet -- fill in the workbook's target column)")
        return

    f = fontmod.Font()
    reserved = set()
    free = used_cells(f)
    if free is not None:
        allowed = {(l, c) for l in PAGES for c in CELLS}
        reserved = {s for s in allowed if s not in free}
        print(f"  {len(reserved)} cell(s) in the target pages are already in use "
              f"-- skipping them")

    cp = assign(chars, load_codepage(), reserved)
    save_codepage(cp)
    print(f"  codepage -> {CODEPAGE} ({len(cp)} characters)")

    for ch in sorted(chars):
        body, fringe = planes(render_glyph(ch))
        code = bytes(cp[ch])
        f.set_glyph(code, body, 0)       # solid body
        f.set_glyph(code, fringe, 1)     # anti-alias fringe
    out = os.path.join(BUILD, "TRF")
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, "TRFSTRINGS.DLL")
    f.save(dst)
    print(f"  patched font -> {dst}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    if sys.argv[1] == "build":
        build(sys.argv[2])
    elif sys.argv[1] == "preview":
        cp = load_codepage()
        os.environ["TRFSTRINGS_DLL"] = os.path.join(BUILD, "TRF", "TRFSTRINGS.DLL")
        import importlib
        importlib.reload(fontmod)
        text = sys.argv[2]
        from PIL import Image
        img = Image.new("1", (24 * len(text), 24), 0)
        for i, ch in enumerate(text):
            code = bytes(cp[ch]) if ch in cp else ch.encode("cp932")
            img.paste(fontmod.get_glyph(code), (i * 24, 0))
        p = os.path.join(BUILD, "preview.png")
        img.resize((img.width * 2, img.height * 2)).save(p)
        print("->", p)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
