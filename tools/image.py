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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cab import Cab
from enc2 import decompress


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

        out = bytearray(len(px) * 4)
        rm, gm, bm, am = self.rmask, self.gmask, self.bmask, amask
        for i, v in enumerate(px):
            o = i * 4
            out[o] = rlut[(v & rm) >> rs]
            out[o + 1] = glut[(v & gm) >> gs]
            out[o + 2] = blut[(v & bm) >> bs]
            out[o + 3] = 255 if not am else (255 if (v & am) else 0)
        return Image.frombytes("RGBA", (self.width, self.height), bytes(out))


def _find(objs, cls):
    for o in objs:
        if o.cls == cls:
            return o
        got = _find(o.children, cls)
        if got:
            return got
    return None


def compose(cab, set_name):
    """Build the full picture described by a `<name>.SET`."""
    from PIL import Image
    from clss import parse
    root, objs = parse(cab.read(set_name))
    tex_obj, pic_obj = _find(objs, "CTRFTexture"), _find(objs, "CTRFPictures")
    if tex_obj is None or pic_obj is None:
        raise ValueError(f"{set_name}: no CTRFTexture/CTRFPictures")

    names = [s.decode("cp932", "replace")
             for s in tex_obj.payload[4:].split(b"\x00")
             if s and s.lower().endswith(b".dds")]
    texes = [TrfImage(cab.read(n)).to_image() for n in names]

    p = pic_obj.payload
    hdr, nblit = struct.unpack_from("<HH", p, 4)
    width, height = struct.unpack_from("<HH", p, 8)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for i in range(nblit):
        o = hdr + i * 20
        tex = struct.unpack_from("<I", p, o)[0]
        sx0, sy0, sx1, sy1 = struct.unpack_from("<4H", p, o + 4)
        dx0, dy0, dx1, dy1 = struct.unpack_from("<4H", p, o + 12)
        if tex >= len(texes):
            continue
        part = texes[tex].crop((sx0, sy0, sx1 + 1, sy1 + 1))
        if part.size != (dx1 - dx0 + 1, dy1 - dy0 + 1):
            part = part.resize((dx1 - dx0 + 1, dy1 - dy0 + 1))
        canvas.paste(part, (dx0, dy0))
    return canvas


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
                compose(cab, nm).save(  # noqa: E501
                    os.path.join(out, nm.rsplit(".", 1)[0] + ".png"))
                ok += 1
            except Exception as e:
                fail += 1
                if fail <= 5:
                    print(f"  FAIL {nm}: {e}")
        print(f"{ok} pictures composed, {fail} failed -> {out}")
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
