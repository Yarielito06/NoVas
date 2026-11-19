"""Make the clean fonts Buddy's clock page uses: 4-bit anti-aliased glyph bitmaps from an open-licence font (Hanken Grotesk, SIL OFL).
Outputs ../firmware/ui_font.bin (all pixels) and ../firmware/uifont.py (where each glyph is)."""
import font_hanken_grotesk as hg, os, sys   # pip install pillow fonts font-hanken-grotesk
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "firmware")
files = os.path.join(os.path.dirname(hg.__file__), "files")
SETS = [
    ("TIME", "HankenGrotesk-Light.otf", 92, "0123456789:", True),     # big thin clock digits (fixed width so they never jiggle)
    ("TEXT", "HankenGrotesk-Medium.otf", 21, "".join(chr(c) for c in range(32, 127)), False),
    ("SMALL", "HankenGrotesk-Medium.otf", 15, "".join(chr(c) for c in range(32, 127)), False),
]
blob = bytearray()
index = {}
for name, fn, size, chars, fixed in SETS:
    font = ImageFont.truetype(os.path.join(files, fn), size)
    asc, desc = font.getmetrics()
    adv_fixed = max(font.getlength(c) for c in "0123456789") if fixed else 0
    entries = {}
    for ch in chars:
        adv = font.getlength(ch)
        im = Image.new("L", (size * 2, size * 2), 0)
        d = ImageDraw.Draw(im)
        d.text((size // 2, size), ch, font=font, fill=255, anchor="ls")     # baseline at y = size
        bb = im.getbbox()
        if bb is None:
            entries[ch] = (0, 0, 0, 0, 0, int(round(adv)))
            continue
        x0, y0, x1, y1 = bb
        w, h = x1 - x0, y1 - y0
        xoff = x0 - size // 2                 # pixels from the pen position to the glyph's left edge
        yoff = y0 - size                      # pixels from the baseline up (negative = above)
        a = int(round(adv_fixed)) if (fixed and ch.isdigit()) else int(round(adv))
        if fixed and ch.isdigit():
            xoff += (a - int(round(adv))) // 2
        crop = im.crop(bb)
        px = list(crop.getdata())
        packed = bytearray()
        for i in range(0, len(px), 2):
            hi = px[i] >> 4
            lo = (px[i + 1] >> 4) if i + 1 < len(px) else 0
            packed.append((hi << 4) | lo)
        entries[ch] = (len(blob), w, h, xoff, yoff, a)
        blob += packed
    index[name] = (asc, entries)
open(os.path.join(OUT, "ui_font.bin"), "wb").write(blob)
with open(os.path.join(OUT, "uifont.py"), "w") as f:
    f.write('"""uifont.py - where each glyph sits in ui_font.bin (made by tools/make_font.py): char: (offset, w, h, xoff, yoff, advance)."""\n')
    for name, (asc, entries) in index.items():
        f.write("%s = {\n" % name)
        for ch, e in entries.items():
            f.write("    %r: %r,\n" % (ch, e))
        f.write("}\n")
print("bytes", len(blob), {k: len(v[1]) for k, v in index.items()})
e = index["TIME"][1]
print("time digit sample", e["0"], e[":"])
