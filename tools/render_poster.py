"""
Draw clean pictures of NoVas (no camera, no 3D software): the real case outline, the real window, and the real faces
that were captured from the board's screen (docs/images/faces/*.png).

    pip install pillow numpy fonts font-hanken-grotesk
    python tools/render_poster.py            -> docs/images/novas-hero.png and docs/images/novas-faces.png
"""
import os, math, json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import font_hanken_grotesk as hg

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "..", "docs", "images")
FONTS = os.path.join(os.path.dirname(hg.__file__), "files")

# the case (millimetres, from hardware/generate_case.py): a diamond with slightly concave sides, rounded tips
TIP = 41.6                 # how far the tips reach from the middle
WIN_W, WIN_H, WIN_R = 39.8, 31.8, 5.0
HOLE_Y, HOLE_R = -(TIP - 8.0), 3.25         # the keyring hole (up is negative y here)
CASE = (31, 33, 37)
SS = 3                      # draw 3x bigger, then shrink: smooth edges


def case_mask(ppm, pad):
    """The case outline as a smooth 0..255 mask, ppm pixels per millimetre. The outline was cut from the real STL (tools/case_outline.json)."""
    pts = json.load(open(os.path.join(HERE, "case_outline.json")))["outline"]
    n = int((TIP + pad) * 2 * ppm) | 1
    c = n / 2
    poly = [(c + x * ppm, c - y * ppm) for x, y in pts]          # the file has y up; pictures have y down
    m = Image.new("L", (n, n), 0)
    ImageDraw.Draw(m).polygon(poly, fill=255)
    return m.filter(ImageFilter.GaussianBlur(ppm * 0.22))


def rounded(w, h, r, fill=255):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill)
    return m


def novas(face_png, ppm):
    """One NoVas as an RGBA picture, ppm pixels per millimetre (before the 3x smoothing)."""
    ppm = ppm * SS
    pad = 3
    mask = case_mask(ppm, pad)
    n = mask.width
    c = n / 2
    # body: a soft diagonal light, like a matte print under a window
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    light = 1.0 - 0.55 * ((xx + yy) / (2 * n))
    base = np.array(CASE, np.float32)[None, None, :] * (0.78 + 0.62 * light[:, :, None])
    rng = np.random.default_rng(3)
    base += rng.normal(0, 1.6, (n, n, 1))                       # the tiny speckle of a printed surface
    body = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    # a thin lighter edge on the top left, like a rounded rim catching light
    edge = mask.filter(ImageFilter.GaussianBlur(ppm * 0.45))
    rim = Image.fromarray(np.clip((np.asarray(mask, np.float32) - np.asarray(edge, np.float32)) * 2.2 * light, 0, 255).astype(np.uint8))
    rim_img = Image.new("RGBA", (n, n), (255, 255, 255, 0))
    rim_img.putalpha(rim.point(lambda v: int(v * 0.55)))
    body = Image.alpha_composite(body, rim_img)
    # the window
    ww, wh = int(WIN_W * ppm), int(WIN_H * ppm)
    wx, wy = int(c - ww / 2), int(c - wh / 2)
    face = Image.open(face_png).convert("RGB")
    screen = Image.new("RGB", (280, 240), (0, 0, 0))
    screen.paste(face, (0, 40))
    screen = screen.crop((0, 8, 280, 232)).resize((ww, wh), Image.BICUBIC)
    glass = rounded(ww, wh, int(WIN_R * ppm))
    # a dark bezel a hair bigger than the glass, then the screen
    bez = rounded(ww + int(1.6 * ppm), wh + int(1.6 * ppm), int((WIN_R + 0.8) * ppm))
    black = Image.new("RGBA", bez.size, (6, 7, 8, 255))
    body.paste(black, (wx - int(0.8 * ppm), wy - int(0.8 * ppm)), bez)
    body.paste(screen, (wx, wy), glass)
    # a faint reflection across the glass
    refl = np.zeros((wh, ww), np.float32)
    gx, gy = np.meshgrid(np.linspace(0, 1, ww), np.linspace(0, 1, wh))
    refl = np.clip(1 - np.abs((gx * 0.9 + gy * 0.6) - 0.55) * 5.0, 0, 1) * 0.10
    rimg = Image.new("RGBA", (ww, wh), (255, 255, 255, 0))
    rimg.putalpha(Image.fromarray((refl * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(ppm)))
    lay = Image.new("RGBA", body.size, (0, 0, 0, 0))
    lay.paste(rimg, (wx, wy), glass)
    body = Image.alpha_composite(body, lay)
    # the keyring hole
    hx, hy = int(c), int(c + HOLE_Y * ppm)
    hole = Image.new("L", (n, n), 0)
    ImageDraw.Draw(hole).ellipse((hx - HOLE_R * ppm, hy - HOLE_R * ppm, hx + HOLE_R * ppm, hy + HOLE_R * ppm), fill=255)
    out_mask = Image.fromarray(np.minimum(np.asarray(mask), 255 - np.asarray(hole)).astype(np.uint8))
    body.putalpha(out_mask)
    return body.resize((n // SS, n // SS), Image.LANCZOS)


def shadow(img, ppm, offset=(0, 1.8), blur=2.4, alpha=0.22):
    a = img.split()[3]
    pad = int(blur * ppm * 4)
    sh = Image.new("L", (a.width + 2 * pad, a.height + 2 * pad), 0)
    sh.paste(a, (pad, pad))
    sh = sh.filter(ImageFilter.GaussianBlur(blur * ppm)).point(lambda v: int(v * alpha))
    layer = Image.new("RGBA", sh.size, (40, 36, 30, 0))
    layer.putalpha(sh)
    return layer, pad


def place(canvas, img, cx, cy, ppm):
    lay, pad = shadow(img, ppm)
    canvas.alpha_composite(lay, (int(cx - lay.width / 2 + 0.0), int(cy - lay.height / 2 + 1.8 * ppm)))
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def backdrop(w, h):
    yy = np.linspace(0, 1, h)[:, None]
    xx = np.linspace(0, 1, w)[None, :]
    top = np.array([246, 245, 242], np.float32)
    bot = np.array([229, 228, 224], np.float32)
    g = top[None, None, :] * (1 - yy[:, :, None]) + bot[None, None, :] * yy[:, :, None]
    vig = 1 - 0.05 * (((xx - 0.5) ** 2 + (yy - 0.5) ** 2) * 2)
    return Image.fromarray(np.clip(g * vig[:, :, None], 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def spaced(draw, text, cx, y, f, fill, tracking):
    w = sum(draw.textlength(ch, font=f) + tracking for ch in text) - tracking
    x = cx - w / 2
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + tracking


def hero():
    W, H, ppm = 2000, 1500, 13.0
    cv = backdrop(W, H)
    place(cv, novas(os.path.join(IMG, "faces", "normal.png"), ppm), W / 2, H / 2 - 60, ppm)
    d = ImageDraw.Draw(cv)
    spaced(d, "NoVas", W / 2, H - 250, font("HankenGrotesk-Light.otf", 84), (38, 40, 44), 14)
    spaced(d, "A  POCKET  FRIEND  WITH  A  FACE", W / 2, H - 140, font("HankenGrotesk-Medium.otf", 26), (140, 140, 136), 7)
    cv.convert("RGB").save(os.path.join(IMG, "novas-hero.png"))


def faces():
    moods = ["happy", "love", "normal", "sleepy", "angry"]
    W, H, ppm = 3000, 1000, 6.1
    cv = backdrop(W, H)
    d = ImageDraw.Draw(cv)
    gap = 560
    x0 = W / 2 - gap * (len(moods) - 1) / 2
    for i, m in enumerate(moods):
        cx = x0 + i * gap
        place(cv, novas(os.path.join(IMG, "faces", m + ".png"), ppm), cx, 480, ppm)
        spaced(d, m.upper(), cx, 810, font("HankenGrotesk-Medium.otf", 26), (132, 132, 128), 6)
    spaced(d, "NoVas", W / 2, 100, font("HankenGrotesk-Light.otf", 56), (38, 40, 44), 10)
    cv.convert("RGB").save(os.path.join(IMG, "novas-faces.png"))


if __name__ == "__main__":
    hero()
    faces()
    print("wrote docs/images/novas-hero.png and novas-faces.png")
