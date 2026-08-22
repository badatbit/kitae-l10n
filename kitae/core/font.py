"""Built-in 24x24 bitmap font of the Dreamcast game (TRF engine, Hudson 1999).

All glyph bitmaps live in TRF/TRFSTRINGS.DLL's `.data` section.  TRFSTRINGS.DLL
exports no glyph symbol at all: TRFFONT.DLL (`CTRFFont::DrawChar`, VA 0x10001240)
reaches the data through the `ITRFAFontSet` COM vtable (0x1000DF80), whose slots
4..8 are one-instruction accessors returning hard-coded addresses.

Address rule (exactly what the engine does)
-------------------------------------------
A character is a raw Shift-JIS (cp932) code unit.

  half-width  (single byte 0x20..0x7F)
      addr = HW_BASE[plane] + (c - 0x20) * 36            # 12x24, 1bpp, 36 bytes
                                                         # bits packed continuously,
                                                         # bit = y*12 + x, MSB first

  full-width  (lead, trail)
      i    = LEAD_TABLE.index(lead)                      # linear search, 42 entries
      addr = FW_BASE[plane] + i * 189 * 72 + (trail - 0x40) * 72
                                                         # 24x24, 1bpp, 72 bytes
                                                         # 3 bytes per row, MSB = leftmost

There is NO Shift-JIS -> JIS conversion, no *94, no *188 and no 0x7F fixup.  Each
lead byte owns a flat page of 189 cells covering trail 0x40..0xFC inclusive, so
trail 0x7F (invalid in Shift-JIS) still occupies a (blank) slot.  Lead bytes that
carry no cp932 characters at all -- 0x85, 0x86, 0xEB, 0xEC -- are simply absent
from LEAD_TABLE, which is what makes a naive linear JIS index fail.

Two 1-bpp planes are stored and drawn on top of each other for anti-aliasing:
plane 0 (solid, colour 0xFF000000) and plane 1 (edge fringe, colour 0x50000000).

Engine bug worth knowing: the "lead byte not found" guard in DrawChar tests
LEAD_TABLE[i-1] instead of LEAD_TABLE[i], so it never fires.  An unlisted lead
byte falls through with i = 42 and reads one page past the array (which lands on
the plane-A page table) -- garbage pixels, but no crash.

Font face is `ＤＦ中丸ゴシック体` (DF Nakamaru Gothic), name string at VA 0x1001EE38.
"""
import os
import struct

__all__ = [
    "Font", "glyph_addr", "get_glyph", "render", "LEAD_TABLE",
    "FW_STRIDE", "HW_STRIDE", "CELLS_PER_LEAD",
]

# ---------------------------------------------------------------- constants
IMAGE_BASE = 0x10000000
DATA_VA = 0x1001D000          # .data section
DATA_RAW = 0x0001B400         # .data file offset
DATA_SIZE = 0x00119200

FW_STRIDE = 72                # 24x24 @ 1bpp, 3 bytes/row
HW_STRIDE = 36                # 12x24 @ 1bpp, continuous bit packing
CELLS_PER_LEAD = 189          # trail 0x40 .. 0xFC inclusive
PAGE_STRIDE = CELLS_PER_LEAD * FW_STRIDE      # 0x3528

# section offsets (= VA - DATA_VA = fileoff - DATA_RAW)
HW_BASE = (0x00000320, 0x000010A0)            # plane 0, plane 1
FW_BASE = (0x00001E78, 0x0008D7B0)            # plane 0, plane 1
LEAD_TABLE_OFF = 0x00001E4C                   # 42 bytes + NUL terminator
PAGE_TABLE_OFF = (0x0008D708, 0x00119040)     # 42 * u32 VA, plane 0 / plane 1
FONT_NAME_OFF = 0x00001E38                    # UTF-16LE, NUL terminated

LEAD_TABLE = bytes.fromhex(
    "818283848788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f"
    "e0e1e2e3e4e5e6e7e8e9eaedee")
assert len(LEAD_TABLE) == 42
LEAD_INDEX = {b: i for i, b in enumerate(LEAD_TABLE)}
NUM_SLOTS = len(LEAD_TABLE) * CELLS_PER_LEAD  # 7938

def _default_dll():
    # 경로 해석은 kitae.config 한 곳에 모았다 (env > config paths > 저장소 dump/).
    try:
        from kitae.config import Config
        p = Config.load().trfstrings_dll()
    except Exception:
        p = os.environ.get("TRFSTRINGS_DLL")
        if p and not os.path.exists(p):
            p = None
    if p:
        return p
    raise FileNotFoundError(
        "TRFSTRINGS.DLL not found; pass a path to Font(), set $TRFSTRINGS_DLL, "
        "또는 kitae.config.json 의 paths.trfstrings_dll 을 지정하세요")


# ---------------------------------------------------------------- addressing
def _encode(ch):
    """str/int/bytes -> cp932 bytes (1 or 2)."""
    if isinstance(ch, (bytes, bytearray)):
        return bytes(ch)
    if isinstance(ch, int):
        return bytes([ch]) if ch < 0x100 else bytes([ch >> 8, ch & 0xFF])
    return ch.encode("cp932")


def slot(ch):
    """Full-width character -> (lead_index, trail_index, linear slot 0..7937).

    Returns None for half-width characters or for a lead byte the font has no
    page for (0x85, 0x86, 0xEB, 0xEC, 0xEF..0xFC)."""
    b = _encode(ch)
    if len(b) != 2:
        return None
    i = LEAD_INDEX.get(b[0])
    if i is None or not (0x40 <= b[1] <= 0xFC):
        return None
    t = b[1] - 0x40
    return i, t, i * CELLS_PER_LEAD + t


def glyph_secoff(ch, plane=0):
    """Offset of the glyph inside TRFSTRINGS.DLL's .data section, or None."""
    b = _encode(ch)
    if len(b) == 1:
        if not (0x20 <= b[0] <= 0x7F):
            return None
        return HW_BASE[plane] + (b[0] - 0x20) * HW_STRIDE
    s = slot(b)
    if s is None:
        return None
    i, t, _ = s
    return FW_BASE[plane] + i * PAGE_STRIDE + t * FW_STRIDE


def glyph_addr(ch, plane=0):
    """File offset of the glyph inside TRFSTRINGS.DLL (what you patch).

    Use `glyph_va()` for the runtime virtual address and `glyph_secoff()` for the
    offset within the `.data` section."""
    o = glyph_secoff(ch, plane)
    return None if o is None else DATA_RAW + o


def glyph_va(ch, plane=0):
    """Runtime virtual address of the glyph (image base 0x10000000)."""
    o = glyph_secoff(ch, plane)
    return None if o is None else DATA_VA + o


def glyph_size(ch):
    """(width, height, nbytes) for a character."""
    b = _encode(ch)
    return (12, 24, HW_STRIDE) if len(b) == 1 else (24, 24, FW_STRIDE)


# ---------------------------------------------------------------- the font
class Font:
    def __init__(self, path=None):
        self.path = path or _default_dll()
        with open(self.path, "rb") as f:
            self.dll = bytearray(f.read())
        self.data = memoryview(self.dll)[DATA_RAW:DATA_RAW + DATA_SIZE]
        got = bytes(self.data[LEAD_TABLE_OFF:LEAD_TABLE_OFF + 42])
        if got != LEAD_TABLE:
            raise ValueError(f"lead table mismatch at {LEAD_TABLE_OFF:#x}: {got.hex()}")

    # -- introspection ----------------------------------------------------
    @property
    def face_name(self):
        raw = bytes(self.data[FONT_NAME_OFF:FONT_NAME_OFF + 64])
        return raw.split(b"\x00\x00")[0].decode("utf-16-le", "replace").rstrip("\x00")

    def page_table(self, plane=0):
        off = PAGE_TABLE_OFF[plane]
        return [struct.unpack_from("<I", self.data, off + 4 * i)[0] for i in range(42)]

    # -- raw bitmap access -------------------------------------------------
    def glyph_bytes(self, ch, plane=0):
        o = glyph_secoff(ch, plane)
        if o is None:
            return None
        n = glyph_size(ch)[2]
        return bytes(self.data[o:o + n])

    def set_glyph_bytes(self, ch, raw, plane=0):
        """Overwrite a glyph in the in-memory DLL image (see .save())."""
        o = glyph_secoff(ch, plane)
        w, h, n = glyph_size(ch)
        if o is None:
            raise KeyError(f"no glyph slot for {ch!r}")
        if len(raw) != n:
            raise ValueError(f"expected {n} bytes, got {len(raw)}")
        self.dll[DATA_RAW + o:DATA_RAW + o + n] = raw

    # -- PIL ---------------------------------------------------------------
    def get_glyph(self, ch, plane=0, antialias=False, scale=1):
        """Return a PIL image of the glyph (24x24 full-width, 12x24 half-width).

        plane 0 = solid body, plane 1 = anti-alias fringe.
        antialias=True composites both planes into an 8-bit greyscale image."""
        from PIL import Image
        w, h, n = glyph_size(ch)
        if antialias:
            a = self.get_glyph(ch, 0).convert("L").point(lambda v: 255 if v else 0)
            b = self.get_glyph(ch, 1).convert("L").point(lambda v: 110 if v else 0)
            from PIL import ImageChops
            im = ImageChops.lighter(a, b)
        else:
            raw = self.glyph_bytes(ch, plane)
            if raw is None:
                im = Image.new("1", (w, h), 0)
            elif w == 24:
                im = Image.frombytes("1", (24, 24), raw)
            else:
                # 12 px rows are NOT byte aligned: bits run continuously
                bits = int.from_bytes(raw, "big")
                im = Image.new("1", (12, 24), 0)
                px = im.load()
                for y in range(24):
                    row = (bits >> (288 - 12 * (y + 1))) & 0xFFF
                    for x in range(12):
                        px[x, y] = (row >> (11 - x)) & 1
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        return im

    def set_glyph(self, ch, img, plane=0):
        """Store a PIL image (any mode; non-zero = ink) into a glyph slot."""
        w, h, n = glyph_size(ch)
        img = img.convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1")
        if img.size != (w, h):
            img = img.resize((w, h))
        if w == 24:
            self.set_glyph_bytes(ch, img.tobytes(), plane)
        else:
            bits = 0
            px = img.load()
            for y in range(24):
                for x in range(12):
                    bits = (bits << 1) | (1 if px[x, y] else 0)
            self.set_glyph_bytes(ch, bits.to_bytes(36, "big"), plane)

    def render(self, text, antialias=True, scale=1, bg=0, fg=255):
        """Render a string; returns a PIL 'L' image, half-width chars 12px wide."""
        from PIL import Image
        widths = [glyph_size(c)[0] for c in text]
        im = Image.new("L", (max(1, sum(widths)), 24), bg)
        x = 0
        for c, w in zip(text, widths):
            try:
                g = self.get_glyph(c, antialias=antialias)
            except (UnicodeEncodeError, KeyError):
                x += w
                continue
            g = g.convert("L")
            if (bg, fg) != (0, 255):
                g = g.point(lambda v: bg + (fg - bg) * v // 255)
            im.paste(g, (x, 0))
            x += w
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        return im

    def render_lines(self, lines, antialias=True, scale=1, gap=1):
        from PIL import Image
        imgs = [self.render(t, antialias=antialias) for t in lines]
        im = Image.new("L", (max(i.width for i in imgs), (24 + gap) * len(imgs)), 0)
        for k, g in enumerate(imgs):
            im.paste(g, (0, k * (24 + gap)))
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        return im

    # -- patching ----------------------------------------------------------
    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.dll)
        return path

    # -- slot bookkeeping ---------------------------------------------------
    def is_blank(self, ch, plane=0):
        raw = self.glyph_bytes(ch, plane)
        return raw is None or not any(raw)

    def free_cells(self, used=(), leads=None):
        """List of (lead, trail) cells available for replacement glyphs.

        `used` is an iterable of characters / 2-byte codes to keep.
        `leads` restricts the search (default: leads 0x99..0xEE, i.e. JIS
        level-2 kanji + the NEC-selected IBM extensions)."""
        keep = set()
        for c in used:
            b = _encode(c)
            if len(b) == 2:
                keep.add((b[0], b[1]))
        if leads is None:
            leads = [l for l in LEAD_TABLE if l >= 0x99]
        return [(l, t) for l in leads for t in range(0x40, 0xFD)
                if (l, t) not in keep]


# ---------------------------------------------------------------- module API
_shared = None


def _f():
    global _shared
    if _shared is None:
        _shared = Font()
    return _shared


def get_glyph(ch, plane=0, antialias=False, scale=1):
    return _f().get_glyph(ch, plane, antialias, scale)


def render(text, antialias=True, scale=1):
    return _f().render(text, antialias=antialias, scale=scale)


# ---------------------------------------------------------------- self test
if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    f = Font()
    print(f"font file : {f.path}")
    print(f"face      : {f.face_name}")
    print(f"lead pages: {len(LEAD_TABLE)}  cells/page: {CELLS_PER_LEAD}  slots: {NUM_SLOTS}")
    print(f"plane0 fw : secoff {FW_BASE[0]:#x}  fileoff {DATA_RAW+FW_BASE[0]:#x}  "
          f"VA {DATA_VA+FW_BASE[0]:#x}")
    pt = f.page_table(0)
    assert pt[0] == DATA_VA + FW_BASE[0] and pt[41] - pt[0] == 41 * PAGE_STRIDE
    print("page table plane0 verified (contiguous, step 0x%x)" % PAGE_STRIDE)
    for ch in "７月日あアＡ":
        print(f"  {ch}  cp932={_encode(ch).hex()}  slot={slot(ch)[2]:5d}  "
              f"fileoff={glyph_addr(ch):#08x}  VA={glyph_va(ch):#x}")

    for name, text in (("font_line1.png", "７月３１日　札幌"),
                       ("font_line2.png", "ねぇお母さん！")):
        p = os.path.join(out, name)
        f.render(text, antialias=True, scale=3).save(p)
        print("wrote", p)
    p = os.path.join(out, "font_sample.png")
    f.render_lines([
        "７月３１日　札幌",
        "ねぇお母さん！",
        "明日だよね？　あの人が来るの・・",
        "あいうえおアイウエオ亜唖娃阿哀",
        "ＡＢＣ０１２３ Half-width ASCII 0123!",
    ], scale=2).save(p)
    print("wrote", p)
