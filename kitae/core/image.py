"""Decode the TRF image format (`CTRFImageBuffer` / `IBUF`) to PNG.

Layout inside a `.dds` entry of a .CB archive (they are not Microsoft DDS):

    "CLSS" u32 len "CTRFImageBuffer\0"
    "IBUF" u32 payload_size
        u32 0
        u16 width, u16 height
        u16 pitch_bytes, u16 ?
        u32 flags
        u32 0
        u32 red_mask, u32 green_mask, u32 blue_mask     e.g. f800 / 07e0 / 001f
        u8  alpha_bits, u8 red_bits, u8 green_bits, u8 blue_bits
        u8  ?, u8 ?, u8 ?, u8 ?
        then one or more chunks:
            "LZSS" u32 size   then  u32 uncompressed_size + compressed data
        `size` counts everything after itself, so the next chunk starts at
        chunk_offset + 8 + size and the compressed data is size-4 bytes.

A background is bigger than one texture, so `<name>.SET` describes how to
compose the final picture:

    CTRFTexture   the .dds file names, in index order
    CTRFPictures  u32 count, u16 header_size(16), u16 blit_count,
                  u16 width, u16 height,
                  then blit_count records of
                    u32 texture_index,
                    u16 sx0, sy0, sx1, sy1,     (inclusive source rect)
                    u16 dx0, dy0, dx1, dy1      (inclusive destination rect)

e.g. bgn264 = 640x480 built from a 512x512 texture plus two strips of a
256x256 one.

The LZSS is the same CTRFLzss used for the archive's ENC2 chunks, so `enc2`
decodes it. Chunks are concatenated in order to form the full pixel buffer.

Usage:
    python image.py <file.cb> <entry> [out.png]
    python image.py <file.cb> --all <out-dir>
"""
import os, struct, sys

from kitae.core.cab import Cab
from kitae.core.enc2 import decompress


class TrfImage:
    def __init__(self, data):
        i = data.find(b"IBUF")
        if i < 0:
            raise ValueError("no IBUF chunk")
        self.payload_size = struct.unpack_from("<I", data, i + 4)[0]
        h = i + 8
        self.width, self.height = struct.unpack_from("<HH", data, h + 4)
        self.pitch = struct.unpack_from("<H", data, h + 8)[0]
        self.flags = struct.unpack_from("<I", data, h + 12)[0]
        self.rmask, self.gmask, self.bmask = struct.unpack_from("<3I", data, h + 20)
        self.abits, self.rbits, self.gbits, self.bbits = data[h + 32:h + 36]
        self.data = data
        self.body = h + 36

    @property
    def bpp(self):
        return self.pitch * 8 // self.width if self.width else 16

    def raw(self):
        """Concatenate every compressed chunk into the full pixel buffer."""
        out = bytearray()
        pos = self.body
        d = self.data
        while pos + 12 <= len(d):
            if d[pos:pos + 4] != b"LZSS":
                nxt = d.find(b"LZSS", pos)
                if nxt < 0:
                    break
                pos = nxt
                continue
            size, usize = struct.unpack_from("<II", d, pos + 4)
            out += decompress(d[pos + 12:pos + 8 + size], usize)
            pos += 8 + size
        return bytes(out)

    def to_image(self):
        """Unpack to RGBA using the channel masks in the header.

        Backgrounds are RGB565 (f800/07e0/001f, no alpha); character sprites are
        ARGB1555 (7c00/03e0/001f with the top bit as a 1-bit alpha).
        """
        from PIL import Image
        import array

        raw = self.raw()
        need = self.width * self.height * self.bpp // 8
        if len(raw) < need:
            raw = raw + b"\x00" * (need - len(raw))
        raw = raw[:need]

        if self.bpp == 32:
            return Image.frombytes("RGBA", (self.width, self.height), raw,
                                   "raw", "BGRA")
        if self.bpp != 16:
            raise NotImplementedError(f"{self.bpp}bpp")

        px = array.array("H")
        px.frombytes(raw)
        if sys.byteorder != "little":
            px.byteswap()

        amask = (~(self.rmask | self.gmask | self.bmask)) & 0xFFFF

        def channel(mask):
            if not mask:
                return 0, 0
            shift = (mask & -mask).bit_length() - 1
            return shift, mask >> shift

        rs, rmax = channel(self.rmask)
        gs, gmax = channel(self.gmask)
        bs, bmax = channel(self.bmask)
        as_, amax = channel(amask)

        # per-channel lookup tables keep the pixel loop cheap
        rlut = bytes(v * 255 // rmax for v in range(rmax + 1)) if rmax else b"\0"
        glut = bytes(v * 255 // gmax for v in range(gmax + 1)) if gmax else b"\0"
        blut = bytes(v * 255 // bmax for v in range(bmax + 1)) if bmax else b"\0"
        # 알파도 마스크 비트수대로 스케일한다 — ARGB1555 는 1비트(이진),
        # ARGB4444 는 4비트(16단계 그라디언트). 예전엔 무조건 이진이라
        # 4444 라벨의 그라디언트 알파가 뭉개졌다.
        alut = bytes(v * 255 // amax for v in range(amax + 1)) if amax else b"\0"

        out = bytearray(len(px) * 4)
        rm, gm, bm, am = self.rmask, self.gmask, self.bmask, amask
        for i, v in enumerate(px):
            o = i * 4
            out[o] = rlut[(v & rm) >> rs]
            out[o + 1] = glut[(v & gm) >> gs]
            out[o + 2] = blut[(v & bm) >> bs]
            out[o + 3] = 255 if not am else alut[(v & am) >> as_]
        return Image.frombytes("RGBA", (self.width, self.height), bytes(out))


def _find(objs, cls):
    for o in objs:
        if o.cls == cls:
            return o
        got = _find(o.children, cls)
        if got:
            return got
    return None


def _pictures(payload):
    """CTRFPictures 를 그림 리스트로 분해.

    구조:  u32 count,  그림마다 [u16 hdr, u16 nblit, u16 w, u16 h, u32 pad]
    (12바이트 헤더) 다음에 nblit 개의 20바이트 blit 레코드.  다음 그림은
    `pos + 12 + nblit*20` 에서 시작한다.  옛 코드는 count 를 무시하고 첫 그림만
    읽어 여러 줄짜리 문구(예: soz_001 = 4줄)의 둘째 줄부터가 통째로 빠졌다.
    """
    out = []
    if len(payload) < 4:
        return out
    count = struct.unpack_from("<I", payload, 0)[0]
    pos = 4
    for _ in range(max(count, 1)):
        if pos + 12 > len(payload):
            break
        _hdr, nblit, w, h = struct.unpack_from("<HHHH", payload, pos)
        # w,h 뒤 4바이트 = 픽처의 화면 offset (i16 x, i16 y). blit dst 는 이
        # offset 기준 상대좌표다 — 무시하면(0,0 에 붙이면) 라벨/점이 어긋난다.
        ox, oy = struct.unpack_from("<hh", payload, pos + 8)
        bstart = pos + 12
        blits = []
        for i in range(nblit):
            o = bstart + i * 20
            if o + 20 > len(payload):
                break
            tex = struct.unpack_from("<I", payload, o)[0]
            src = struct.unpack_from("<4H", payload, o + 4)
            dst = struct.unpack_from("<4H", payload, o + 12)
            blits.append((tex, src, dst))
        out.append((w, h, ox, oy, blits))
        pos = bstart + nblit * 20
    return out


def _render_picture(texes, cw, ch, ox, oy, blits):
    """한 픽처를 `cw×ch` 캔버스에 렌더. blit 은 픽처 offset `(ox,oy)` 기준이라
    최종 위치 = `(ox+dx, oy+dy)`. 그래서 픽처들을 (0,0) 에 겹치면 바로 합쳐진다.
    """
    from PIL import Image
    canvas = Image.new("RGBA", (max(1, cw), max(1, ch)), (0, 0, 0, 0))
    for tex, (sx0, sy0, sx1, sy1), (dx0, dy0, dx1, dy1) in blits:
        if tex >= len(texes):
            continue
        part = texes[tex].crop((sx0, sy0, sx1 + 1, sy1 + 1))
        tgt = (max(1, dx1 - dx0 + 1), max(1, dy1 - dy0 + 1))
        if part.size != tgt:
            part = part.resize(tgt)
        canvas.alpha_composite(part, (ox + dx0, oy + dy0))
    return canvas


def pictures(cab, set_name):
    """Render each picture of a `<name>.SET` → list of images, all on one common
    canvas and each placed at its own `(ox,oy)` offset. So overlaying (alpha) the
    returned images at (0,0) reconstructs the full picture — the layers (e.g.
    soz_068 = base + dots + labels) line up because the offset is baked in.
    """
    from kitae.core.clss import parse
    root, objs = parse(cab.read(set_name))
    tex_obj, pic_obj = _find(objs, "CTRFTexture"), _find(objs, "CTRFPictures")
    if tex_obj is None or pic_obj is None:
        raise ValueError(f"{set_name}: no CTRFTexture/CTRFPictures")

    names = [s.decode("cp932", "replace")
             for s in tex_obj.payload[4:].split(b"\x00")
             if s and s.lower().endswith(b".dds")]
    texes = [TrfImage(cab.read(n)).to_image() for n in names]

    pics = _pictures(pic_obj.payload)
    if not pics:
        raise ValueError(f"{set_name}: no pictures")
    # 공통 캔버스: 헤더 w/h 의 최대(대개 화면 크기). 이상값은 무시.
    ws = [w for (w, h, ox, oy, b) in pics if 0 < w <= 2048]
    hs = [h for (w, h, ox, oy, b) in pics if 0 < h <= 2048]
    cw = max(ws) if ws else 640
    ch = max(hs) if hs else 480
    return [_render_picture(texes, cw, ch, ox, oy, blits)
            for (w, h, ox, oy, blits) in pics]


def compose(cab, set_name):
    """Single flattened image for a `<name>.SET` — all pictures overlaid at their
    offsets (base + dots + labels …). Use `pictures()` to keep the layers apart.
    """
    from PIL import Image
    rendered = pictures(cab, set_name)
    if len(rendered) == 1:
        return rendered[0]
    canvas = Image.new("RGBA", rendered[0].size, (0, 0, 0, 0))
    for im in rendered:
        canvas.alpha_composite(im)
    return canvas


# ---------------------------------------------------------------- recompose
# 조각 배치 예외 규칙. 일부 셋(예: soz-068)은 CTRFPictures 의 blit de-pack 이
# 아니라, 여러 텍스처 조각을 캔버스에 그대로 이어붙여야 완성된다(게임 로더가
# 런타임에 조립하는 모양 — .SET 에 그 배치가 없다). 자동 추론이 위험하므로
# (type-lettering README 의 recompose 원칙: 눈검증 후 데이터로 고정) 셋별로
# 손으로 확인한 move 스펙을 여기 둔다.
#   move = (텍스처명, (sx, sy, w, h) 소스 크롭, (dx, dy) 캔버스 위치)
RECOMPOSE = {
    "soz-068": {  # 스스키노 라벨 지도 — 타일 3장을 이어붙인다(가로 + t2 분할)
        "canvas": (620, 465),
        "moves": [
            ("soz-068_00.dds", (0, 0, 256, 256), (0, 0)),
            ("soz-068_01.dds", (0, 0, 256, 256), (256, 0)),
            ("soz-068_02.dds", (0, 0, 128, 128), (512, 0)),      # t2 좌상 → 우상
            ("soz-068_02.dds", (128, 0, 128, 128), (512, 128)),  # t2 우상 → 우하
            ("soz-068_02.dds", (0, 128, 256, 128), (0, 256)),    # t2 아래 → 좌하
        ],
    },
}


def recompose(cab, key):
    """RECOMPOSE 예외 규칙대로 텍스처 조각을 이어붙인 완성 이미지."""
    from PIL import Image
    spec = RECOMPOSE[key]
    cw, ch = spec["canvas"]
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for name, (sx, sy, w, h), (dx, dy) in spec["moves"]:
        tex = TrfImage(cab.read(name)).to_image().convert("RGBA")
        canvas.alpha_composite(tex.crop((sx, sy, sx + w, sy + h)), (dx, dy))
    return canvas


def save_set(cab, set_name, out_dir):
    """Save a `.SET` as PNG(s) into `out_dir`. One picture → `<base>.png`;
    several → `<base>_00.png`, `<base>_01.png`, … (kept separate, not stacked,
    since the pictures are independent overlays). Returns the paths written.

    A set listed in RECOMPOSE is assembled by its move spec into one image
    (`<base>_00.png`) instead of the CTRFPictures de-pack.
    """
    base = set_name.rsplit(".", 1)[0]
    if base in RECOMPOSE:
        p = os.path.join(out_dir, base + "_00.png")
        recompose(cab, base).save(p)
        return [p]
    imgs = pictures(cab, set_name)
    written = []
    if len(imgs) == 1:
        p = os.path.join(out_dir, base + ".png")
        imgs[0].save(p)
        written.append(p)
    else:
        for i, im in enumerate(imgs):
            p = os.path.join(out_dir, f"{base}_{i:02d}.png")
            im.save(p)
            written.append(p)
    return written


def main():
    cab = Cab(sys.argv[1])
    if sys.argv[2] == "--set":
        img = compose(cab, sys.argv[3])
        dst = sys.argv[4] if len(sys.argv) > 4 else "out.png"
        img.save(dst)
        print(f"{img.size[0]}x{img.size[1]} -> {dst}")
        return
    if sys.argv[2] == "--sets":
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        ok = fail = 0
        for nm in cab.names:
            if not nm.lower().endswith(".set"):
                continue
            try:
                ok += len(save_set(cab, nm, out))
            except Exception as e:
                fail += 1
                if fail <= 5:
                    print(f"  FAIL {nm}: {e}")
        print(f"{ok} pictures saved, {fail} sets failed -> {out}")
        return
    if sys.argv[2] == "--all":
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        ok = fail = 0
        for nm in cab.names:
            if not nm.lower().endswith(".dds"):
                continue
            try:
                img = TrfImage(cab.read(nm)).to_image()
                img.save(os.path.join(out, nm.rsplit(".", 1)[0] + ".png"))
                ok += 1
            except Exception as e:
                fail += 1
                if fail <= 5:
                    print(f"  FAIL {nm}: {e}")
        print(f"{ok} images written, {fail} failed -> {out}")
        return
    im = TrfImage(cab.read(sys.argv[2]))
    print(f"{im.width}x{im.height} pitch={im.pitch} bpp={im.bpp} "
          f"masks={im.rmask:#x}/{im.gmask:#x}/{im.bmask:#x} "
          f"bits={im.abits}/{im.rbits}/{im.gbits}/{im.bbits}")
    dst = sys.argv[3] if len(sys.argv) > 3 else "out.png"
    im.to_image().save(dst)
    print("->", dst)


if __name__ == "__main__":
    main()
