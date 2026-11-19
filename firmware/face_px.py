"""
face_px.py - the PIXEL eyes. Same Buddy (same moods, blinks, looks, springs), but every eye is built from
chunky square blocks on a grid, like a retro game.

What makes them look finished:
  * a soft one-block GLOW around each eye (a very dark green halo),
  * lit-from-the-top-left shading: a lighter rim on the top left, a darker rim on the bottom right,
  * a one-block SHADOW under the eyelid edge and above the smiling cheek, so the lid reads as a real lid,
  * a tone-on-tone pupil with two sparkles (one big block, one small).

How it stays fast:
  * the shapes are drawn by one small machine-code routine (pxeye), block row by block row;
  * if nothing changed since the last frame, nothing is drawn or sent to the screen at all.

Turn it on with EYE_STYLE = "pixel" in config.py (the default smooth eyes are EYE_STYLE = "classic").
"""
import array
import math
import micropython
import face as F
from face import Face

G = 6                       # the size of one block, in screen pixels
OX = 140 % G                # the grid is lined up so the middle of the screen is on a block edge
Q = 24                      # a change smaller than this (1/16 pixel units: 1.5 px) does not count as "changed"
P = array.array("i", [0] * 40)


def cell(x):
    """The block column a pixel x falls in (rounded to the nearest block edge)."""
    return int((x - OX) / G + 100.5) - 100


def shade(c, k):
    """Colour c (in the screen's own format) made k times as bright."""
    c = ((c & 255) << 8) | (c >> 8)
    r = int(((c >> 11) & 31) * k)
    g = int(((c >> 5) & 63) * k)
    b = int((c & 31) * k)
    c = (min(r, 31) << 11) | (min(g, 63) << 5) | min(b, 31)
    return ((c & 255) << 8) | (c >> 8)


def tint(c, k):
    """Colour c mixed k of the way toward white."""
    c = ((c & 255) << 8) | (c >> 8)
    r = (c >> 11) & 31
    g = (c >> 5) & 63
    b = c & 31
    r = int(r + (31 - r) * k)
    g = int(g + (63 - g) * k)
    b = int(b + (31 - b) * k)
    c = (r << 11) | (g << 5) | b
    return ((c & 255) << 8) | (c >> 8)


@micropython.viper
def fillblk(buf: ptr16, x: int, y: int, w: int, h: int, color: int, sw: int, sh: int):
    """Fill a rectangle that starts on an even column with an even width: two pixels per store."""
    if x < 0:
        w += x
        x = 0
    if x + w > sw:
        w = sw - x
    if w <= 0:
        return
    b32 = ptr32(buf)
    both = (color & 0xFFFF) | ((color & 0xFFFF) << 16)
    n = w >> 1
    r = 0
    while r < h:
        yy = y + r
        if yy >= 0 and yy < sh:
            k = (yy * sw + x) >> 1
            e = k + n
            while k < e:
                b32[k] = both
                k += 1
        r += 1


@micropython.viper
def cellcol(p: ptr32, xc: int, yc: int, crow: int, v: int) -> int:
    """The colour of one block of the eye (0 = nothing here). (xc, yc) is the middle of the block, crow the eye's middle on this row, v how far down the eye this row is."""
    one = 4096 * 4096
    erx = p[6]
    col = 0
    u = (xc - crow) * 4096 // erx
    q = u * u + v * v
    inside = 0
    if q < one:
        inside = 1
        col = p[25]
        if p[30]:
            if q >= 12800000:                              # the one-block rim: lit from the top left
                s = v + (u >> 1)
                if s < -1100:
                    col = p[27]
                elif s > 1100:
                    col = p[28]
            elif v < -2300:                                # the body has three tones, like a little cel-shaded ball
                col = p[33]
            elif v > 1700:
                col = p[34]
    elif p[29] and q < 21500000:                          # the glow, one block thick
        col = p[29]
    if col:
        if p[9]:
            lu = (xc - p[10]) * 4096 // p[12]
            lv = (yc - p[11]) * 4096 // p[13]
            if lv > -9000 and lv < 9000:
                lq = lu * lu + lv * lv
                if lq < one:
                    col = 0
                elif inside and p[31] and lq < 19800000:   # a block of shadow under the lid's edge
                    col = p[28]
        if col and p[14]:
            ku = (xc - p[15]) * 4096 // p[17]
            kv = (yc - p[16]) * 4096 // p[18]
            if kv > -9000 and kv < 9000:
                kq = ku * ku + kv * kv
                if kq < one:
                    col = 0
                elif inside and p[31] and kq < 19800000:
                    col = p[28]
        if col and inside and p[19]:
            pu = (xc - p[20] - ((p[24] * (yc - p[21])) >> 8)) * 4096 // p[22]
            pv = (yc - p[21]) * 4096 // p[23]
            if pv > -4900 and pv < 4900:
                pq = pu * pu + pv * pv
                if pq < one:
                    col = p[26]
                    if pq < 4800000:                       # a darker core in the middle of the pupil
                        col = p[32]
    return col


@micropython.viper
def pxeye(buf: ptr16, p: ptr32):
    """Draw one pixel-block eye. All sizes are in 1/16 pixel. p: 0 block, 1 grid origin, 2 screen w, 3 screen h,
    4..8 eye (cx, cy, rx, ry, shear/256), 9..13 eyelid oval, 14..18 cheek oval, 19..24 pupil (on, cx, cy, rx, ry, shear/256),
    25 eye colour, 26 pupil colour, 27 light rim colour, 28 dark rim / shadow colour, 29 glow colour (0 = none), 30 rim shading on,
    31 lid/cheek shadow on, 32 pupil core colour, 33 top body tone, 34 bottom body tone."""
    G = p[0]
    ox = p[1]
    sw = p[2]
    sh = p[3]
    ecx = p[4]
    ecy = p[5]
    erx = p[6]
    ery = p[7]
    unit = 16 * G
    pad = ery // 6
    top = ecy - ery - pad
    j = 0
    if top > 0:
        j = top // unit
    j1 = (ecy + ery + pad) // unit + 1
    while j <= j1:
        y0 = j * G
        if y0 >= sh:
            break
        yc = y0 * 16 + 8 * G
        dy = yc - ecy
        v = dy * 4096 // ery
        if v > -4900 and v < 4900:
            crow = ecx + ((p[8] * dy) >> 8)
            first = crow - erx - erx // 6 - ox * 16
            i = 0
            if first > 0:
                i = first // unit
            last = (crow + erx + erx // 6 - ox * 16) // unit + 1
            run = -1
            rcol = 0
            while i <= last + 1:
                col = int(cellcol(p, (ox + i * G) * 16 + 8 * G, yc, crow, v))
                if col != rcol:
                    if rcol:
                        fillblk(buf, ox + run * G, y0, (i - run) * G, G, rcol, sw, sh)
                    run = i
                    rcol = col
                i += 1
        j += 1


# the pixel heart, as runs: (row, first block, number of blocks)
HEART_RUNS = ((0, 1, 2), (0, 4, 2), (1, 0, 7), (2, 0, 7), (3, 1, 5), (4, 2, 3), (5, 3, 1))


class PixelFace(Face):
    PAD = 10                    # the glow reaches a little past the eye

    def begin_frame(self):
        self.recs = []          # the eyes are only noted down now; drawn in after_eyes (once we know if anything changed)

    def eye(self, ex, ey, rx, ry, opened, side, eye_color, pupil_color, cover=0.0):
        h = ry * opened
        fb = self.fb
        p = array.array("i", P)             # a fresh copy for this eye
        p[0] = G
        p[1] = OX
        p[2] = fb.width
        p[3] = fb.height
        extra = None
        if h < 6:
            # closed: a moon shape (one oval with a second oval taken out of it)
            sleep = self.sleep
            thick = 3 + sleep * (13 + 4 * self.lungs + 4 * self.sigh)
            deep = 18 + 9 * sleep + 7 * self.dream
            y = ey - 8 - 4 * sleep
            p[4] = int(ex * 16); p[5] = int(y * 16); p[6] = int(rx * (0.86 + 0.08 * sleep) * 16); p[7] = int(deep * 16); p[8] = 0
            p[9] = 1; p[10] = int(ex * 16); p[11] = int((y - thick) * 16); p[12] = int(rx * (0.98 + 0.1 * sleep) * 16); p[13] = int(deep * 16)
            p[14] = 0
            p[19] = 0
            p[25] = self.closed_color
            p[28] = 0
            p[29] = 0
            p[30] = 0
            p[31] = 0
        else:
            lean = side * self.tilt_k * (1.0 + 0.3 * side * self.asym)
            lean += 0.07 * math.sin(self.t * 0.8 + side * 1.9 + self.asym) + 0.05 * math.sin(self.t * 1.7 + side * 0.6)
            size = self.pupil * (1 - 0.45 * self.focus_now) + self.pup_pulse
            pr = F.PUPIL_RX * size * rx / F.EYE_RX * self.pup_w
            ph = max(0.5, F.PUPIL_RY * size * h / F.EYE_RY * self.pup_h)
            qx = self.pup2_x if side > 0 else self.pup_x
            qy = self.pup2_y if side > 0 else self.pup_y
            px = ex + max(-rx + pr + 4, min(rx - pr - 4, qx - self.eye_x * 0.3))
            py = ey + max(-h + ph + 4, min(h - ph - 4, qy - self.eye_y * 0.3))
            px += lean * (py - ey) - side * 2.5
            marking = self.mark > 0.15
            loving = self.heart_size > 0.15

            # the eyelid: it follows the gaze, trails the movement, and a blink brings it to a hairline
            lid = self.lid + self.squint + 0.14 * self.focus_now + 0.011 * self.pup_y
            if cover > 0.0:
                lid += (0.97 - lid) * cover if lid < 0.97 else 0.0
            lid += 0.06 * min(1.0, abs(self.eye_vx) / 220)
            if lid < 0:
                lid = 0.0
            lag = max(-7.0, min(7.0, self.eye_vx * 0.03))
            lid_ry = h + 20
            lid_y = ey - h + h * 2 * lid - lid_ry
            cheek = self.cheek * max(0.0, 1.0 - max(0.0, self.pup_y) / 14.0)
            cheek_y = ey + h + 6 + h - h * 2 * cheek

            p[4] = int(ex * 16); p[5] = int(ey * 16); p[6] = int(rx * 16); p[7] = int(h * 16); p[8] = int(lean * 256)
            if lid > 0.02:
                p[9] = 1; p[10] = int((ex - side * self.slant * rx * 0.55 - lag) * 16); p[11] = int(lid_y * 16)
                p[12] = int(rx * 1.7 * 16); p[13] = int(lid_ry * 16)
            else:
                p[9] = 0
            if cheek > 0.02:
                p[14] = 1; p[15] = int(ex * 16); p[16] = int(cheek_y * 16); p[17] = int((rx + 16) * 16); p[18] = int((h + 6) * 16)
            else:
                p[14] = 0
            if marking or loving:
                p[19] = 0
            else:
                p[19] = 1; p[20] = int(px * 16); p[21] = int(py * 16); p[22] = int(pr * 16); p[23] = int(ph * 16); p[24] = int(lean * 0.8 * 256)
            p[25] = eye_color
            p[26] = pupil_color
            p[27] = tint(eye_color, 0.30)
            p[28] = shade(eye_color, 0.58)
            p[29] = shade(eye_color, 0.2)
            p[32] = shade(pupil_color, 0.55)
            p[33] = tint(eye_color, 0.12)
            p[34] = shade(eye_color, 0.9)
            calm = 1 if lid < 0.72 else 0                          # a nearly shut eye is just a bright line: no shading
            p[30] = calm
            p[31] = calm
            if marking:
                extra = (1, px, py, self.mark * h / ry, pupil_color)
            elif loving:
                beat = abs(math.sin(self.t * 4.2))
                extra = (2, px, py - 7 * h / ry, (13 + 4 * beat * beat) * self.heart_size * h / ry, 0)
            elif lid < 0.5 and cheek < 0.3:
                extra = (3, px, py, pr, ph)
        self.recs.append((p, extra))

    def after_eyes(self):
        recs = self.recs
        # what would be drawn, boiled down: a change smaller than 1.5 px (or a colour that stays the same) is not a change
        sig = 0
        for p, extra in recs:
            sig = hash((sig, tuple([p[k] // Q for k in range(4, 24)]), p[25], p[26], p[29], p[30], extra is not None and extra[0]))
        extras = (self.water_on or self.charge_sign or self.bell_n or self.bubbles or self.sparks or self.heart_size > 0.02
                  or self.mark > 0.02 or self.phase or (self.row0 == 0 and self.row1 >= self.fb.height))
        still = getattr(self, "still", 0) + 1
        if sig == getattr(self, "last_sig", None) and not extras and not getattr(self, "last_extras", True) and still < 30:
            self.still = still
            self.skip = True                      # nothing changed: draw and send nothing (but redraw every half second, to be safe)
            return
        self.still = 0
        self.skip = False
        self.last_sig = sig
        self.last_extras = bool(extras)
        fb = self.fb
        fb.fill_rect(0, self.row0, fb.width, self.row1 - self.row0, F.BG)           # wipe the last frame
        buf = fb.buffer
        for p, extra in recs:
            pxeye(buf, p)
            if extra:
                kind = extra[0]
                if kind == 1:
                    self.tick_or_cross(extra[1], extra[2], extra[3], extra[4])
                elif kind == 2:
                    self.heart(extra[1], extra[2], extra[3], F.HEART)
                else:
                    px, py, pr, ph = extra[1], extra[2], extra[3], extra[4]
                    # two sparkles: one big block up in the left of the pupil, one small one low on the right
                    fb.fill_rect(OX + cell(px - pr * 0.45) * G, int((py - ph * 0.5) / G) * G, G, G, F.GLINT)
                    fb.fill_rect(int(px + pr * 0.38) & ~1, int(py + ph * 0.38) & ~1, 4, 4, F.GLINT)

    def show(self):
        if self.skip:
            return
        Face.show(self)

    def heart(self, cx, cy, r, color):
        """A pixel heart whose blocks sit on an even grid."""
        c = int(0.55 * r / 2 + 0.5) * 2
        if c < 2:
            return
        fb = self.fb
        x0 = int(cx - 3.5 * c) & ~1
        y0 = int(cy - 0.9 * r) & ~1
        for row, start, n in HEART_RUNS:
            fb.fill_rect(x0 + start * c, y0 + row * c, n * c, c, color)

    def tick_or_cross(self, x, y, size, color):
        """The yes / no answer, drawn in blocks."""
        d = self.d
        shape = F.TICK if d.answer else F.CROSS
        t = max(G, int(F.MARK_WIDTH * size * 1.1))
        fb = self.fb
        for k in (0, 4):
            x0, y0, x1, y1 = shape[k] * size, shape[k + 1] * size, shape[k + 2] * size, shape[k + 3] * size
            n = int(max(abs(x1 - x0), abs(y1 - y0)) / (G * 0.6)) + 1
            for i in range(n + 1):
                px = x + x0 + (x1 - x0) * i / n
                py = y + y0 + (y1 - y0) * i / n
                fb.fill_rect(OX + cell(px) * G, int(py / G) * G, t, t, color)
