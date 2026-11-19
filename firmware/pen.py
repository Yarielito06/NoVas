"""
pen.py - draws smooth shapes straight into the screen's memory.

The built-in framebuf shapes have stair-step edges: each pixel is either on
or off. Here, edge pixels get a mix of the shape color and whatever is behind
them, depending on how much of that pixel the shape covers. That's called
anti-aliasing, and it's what makes curves look like clean lines.

Positions are also "fixed point": whole numbers worth 1/256 of a pixel. So a
shape can sit between two pixels, and slow movement glides instead of stepping.

This runs for every edge pixel of every frame, so it needs to be fast. The
@micropython.viper line compiles the function to real machine code, which is
why it only uses whole numbers and reads its settings from one small array.
"""

import array
import math
import micropython

STEPS = 2048

# How wide a shape is at each height, from its middle (1.0) to its tip (0.0).
ROUND = array.array("H", bytes(2 * (STEPS + 1)))
POINT = array.array("H", bytes(2 * (STEPS + 1)))
for i in range(STEPS + 1):
    ROUND[i] = int(65535 * math.sqrt(1 - (i / STEPS) ** 2))
    POINT[i] = int(65535 * (1 - i / STEPS))

# Dividing is slow, so these are ready-made answers: FADE[n] is 65536 * 256
# divided by a width of n * 32 (in 1/256 pixel), used to fade across an edge.
FADE = array.array("I", bytes(4 * 1024))
for i in range(1024):
    FADE[i] = 16777216 // (i * 32 + 16)


@micropython.viper
def fill_span(buf: ptr16, p: ptr32):
    """Fill pixels x = p[14] .. p[15] - 1 of row p[13] with the colour p[4], clipped to the screen.
    (The big drawing function is split in small pieces, because this chip's compiler can't
    handle one huge function.)"""
    row = p[13]
    x = p[14]
    stop = p[15]
    color = p[4]
    screen_w = p[6]
    if x < 0:
        x = 0
    if stop > screen_w:
        stop = screen_w
    if x < stop and ((row + x) & 1):
        buf[row + x] = color                    # one pixel to line up with a 32-bit word
        x += 1
    both = (color & 0xFFFF) | ((color & 0xFFFF) << 16)
    b32 = ptr32(buf)
    while x + 4 <= stop:                         # four pixels per step, two words at a time
        w = (row + x) >> 1
        b32[w] = both
        b32[w + 1] = both
        x += 4
    while x < stop:
        buf[row + x] = color
        x += 1


@micropython.viper
def edge_span(buf: ptr16, p: ptr32, fade: ptr32):
    """The soft edge of one side of one row: fade from the shape's colour into what is behind it.
    Reads: p[13] row, p[14] first x, p[15] stop x, p[16] side (0 left, 1 right), p[17] outer half-width,
    p[18] fade step, p[19] how much of the row is filled."""
    cx = p[0]
    color = p[4]
    screen_w = p[6]
    row = p[13]
    x = p[14]
    stop = p[15]
    side = p[16]
    outer = p[17]
    step = p[18]
    height = p[19]
    spread = 0x07E0F81F
    c = ((color & 255) << 8) | ((color >> 8) & 255)
    wide = (c | (c << 16)) & spread
    while x < stop:
        if x >= 0 and x < screen_w:
            middle = (x << 8) + 128
            if side == 0:
                depth = middle - (cx - outer) + 128
            else:
                depth = (cx + outer) - middle + 128
            cover = (depth * step) >> 16
            if cover > 256:
                cover = 256
            cover = (cover * height) >> 13   # now 0 to 32
            if cover >= 32:
                buf[row + x] = color
            elif cover > 0:
                q = buf[row + x]
                q = ((q & 255) << 8) | ((q >> 8) & 255)
                q = (q | (q << 16)) & spread
                q = (q + (((wide - q) * cover) >> 5)) & spread
                q = (q | (q >> 16)) & 0xFFFF
                buf[row + x] = ((q & 255) << 8) | ((q >> 8) & 255)
        x += 1


@micropython.viper
def shape(buf: ptr16, widths: ptr16, p: ptr32, fade: ptr32):
    """Draw one shape. p holds: x, y, half-width, half-height (all 1/256 pixel),
    color, scale, screen width, screen height, first row, last row, and the
    half-width, half-height and scale of a middle part already filled in.
    p[13..19] are scratch values handed to the small helper functions above."""
    cx = p[0]
    cy = p[1]
    rx = p[2]
    ry = p[3]
    scale = p[5]
    screen_w = p[6]
    first = p[8]
    last = p[9]
    done_rx = p[10]
    done_ry = p[11]
    done_scale = p[12]
    shear = p[20]

    y = (cy - ry) >> 8
    y_end = ((cy + ry) >> 8) + 1
    if y < first:
        y = first
    if y_end > last:
        y_end = last

    while y < y_end:
        top = (y << 8) - cy          # this pixel row, measured from the middle
        cxr = cx + (((top + 128) * shear) >> 8)     # a tilted eye: every row slides sideways a little more
        p[0] = cxr
        bottom = top + 256
        if top > 0:
            near = top
            far = bottom
        elif bottom < 0:
            near = 0 - bottom
            far = 0 - top
        else:
            near = 0
            far = 0 - top
            if bottom > far:
                far = bottom

        if near < ry:
            # The shape's half-width at the near and far side of this row.
            outer = (rx * widths[(near * scale) >> 16]) >> 16
            inner = 0
            if far < ry:
                inner = (rx * widths[(far * scale) >> 16]) >> 16
            height = ry - near       # how much of this row the shape fills
            if height > 256:
                height = 256

            p[13] = y * screen_w
            left_solid = (cxr - inner + 255) >> 8
            right_solid = (cxr + inner) >> 8

            # The solid part of the row, skipping any middle already filled.
            if height == 256:
                gap_left = right_solid
                gap_right = right_solid
                if near < done_ry:
                    done = (done_rx * widths[(near * done_scale) >> 16]) >> 16
                    gap_left = (cxr - done) >> 8
                    gap_right = ((cxr + done) >> 8) + 1
                p[14] = left_solid
                p[15] = gap_left
                fill_span(buf, p)
                p[14] = gap_right
                p[15] = right_solid
                fill_span(buf, p)
            else:
                left_solid = (cxr + 128) >> 8
                right_solid = left_solid

            # The soft edges: fade across the pixels between inner and outer.
            span = outer - inner + 256
            p[17] = outer
            p[18] = fade[span >> 5]
            p[19] = height
            p[16] = 0
            p[14] = (cxr - outer) >> 8
            p[15] = left_solid
            edge_span(buf, p, fade)
            p[16] = 1
            p[14] = right_solid
            p[15] = ((cxr + outer) >> 8) + 1
            edge_span(buf, p, fade)
        y += 1


# Square roots, ready-made: ROOT[i] is the square root of i * 16.
ROOT = array.array("H", bytes(2 * 4096))
for i in range(4096):
    ROOT[i] = int(math.sqrt(i * 16))


@micropython.viper
def line_pixels(buf: ptr16, p: ptr32, root: ptr16):
    """The pixel loop of lines() for one row. p[2] thickness, p[3] colour, p[5] screen width, and the
    scratch values p[8] row, p[9] first x, p[10] stop x, p[11..12] line start, p[13..14] line direction, p[15] along."""
    r = p[2]
    color = p[3]
    screen_w = p[5]
    y = p[8]
    x = p[9]
    stop = p[10]
    ax = p[11]
    ay = p[12]
    dx = p[13]
    dy = p[14]
    along = p[15]
    spread = 0x07E0F81F
    c = ((color & 255) << 8) | ((color >> 8) & 255)
    wide = (c | (c << 16)) & spread
    py = (y << 4) + 8
    while x < stop:
        px = (x << 4) + 8
        # The closest point on the line to this pixel.
        t = (((px - ax) * dx + (py - ay) * dy) >> 4) * along >> 16
        if t < 0:
            t = 0
        if t > 256:
            t = 256
        ex = px - (ax + ((dx * t) >> 8))
        ey = py - (ay + ((dy * t) >> 8))
        far = (ex * ex + ey * ey) >> 4
        if far < 4096:
            # Fade from full to nothing across one pixel at the edge.
            cover = (r + 8 - root[far]) << 1      # 0 to 32
            if cover >= 32:
                buf[y * screen_w + x] = color
            elif cover > 0:
                q = buf[y * screen_w + x]
                q = ((q & 255) << 8) | ((q >> 8) & 255)
                q = (q | (q << 16)) & spread
                q = (q + (((wide - q) * cover) >> 5)) & spread
                q = (q | (q >> 16)) & 0xFFFF
                buf[y * screen_w + x] = ((q & 255) << 8) | ((q >> 8) & 255)
        x += 1


@micropython.viper
def lines(buf: ptr16, segments: ptr32, p: ptr32, root: ptr16):
    """Draw thick round-ended lines with soft edges. All positions here are in
    1/16 of a pixel. p holds: x, y, thickness, color, segment count, screen
    width, screen height. Slower than shape(), so it's for pictures that stay
    still, like the finished word."""
    ox = p[0]
    oy = p[1]
    r = p[2]
    color = p[3]
    count = p[4]
    screen_w = p[5]
    screen_h = p[6]

    spread = 0x07E0F81F
    c = ((color & 255) << 8) | ((color >> 8) & 255)
    wide = (c | (c << 16)) & spread
    reach = r + 16

    n = 0
    while n < count:
        ax = segments[n * 4] + ox
        ay = segments[n * 4 + 1] + oy
        bx = segments[n * 4 + 2] + ox
        by = segments[n * 4 + 3] + oy
        dx = bx - ax
        dy = by - ay
        length = dx * dx + dy * dy
        if length < 1:
            length = 1
        # Dividing is slow, so do it once here instead of for every pixel.
        along = 268435456 // length

        # How far sideways the line reaches on one row of pixels.
        wide_x = dx
        if wide_x < 0:
            wide_x = 0 - wide_x
        tall_y = dy
        if tall_y < 0:
            tall_y = 0 - tall_y
        slope = 0
        if tall_y * 2 >= wide_x:
            slope = (wide_x << 8) // tall_y
        window = (reach * (256 + slope)) >> 8

        # Only look at pixels near this line.
        x0 = ax
        x1 = bx
        if bx < ax:
            x0 = bx
            x1 = ax
        y0 = ay
        y1 = by
        if by < ay:
            y0 = by
            y1 = ay
        left = (x0 - reach) >> 4
        right = ((x1 + reach) >> 4) + 1
        y = (y0 - reach) >> 4
        bottom = ((y1 + reach) >> 4) + 1
        if left < 0:
            left = 0
        if right > screen_w:
            right = screen_w
        if y < 0:
            y = 0
        if bottom > screen_h:
            bottom = screen_h

        while y < bottom:
            py = (y << 4) + 8
            x = left
            stop = right
            if slope or wide_x == 0:
                # Steep enough to skip straight to the pixels near the line.
                along_y = py - ay
                if along_y < 0:
                    along_y = 0
                if along_y > tall_y:
                    along_y = tall_y
                if dy < 0:
                    along_y = py - ay
                    if along_y > 0:
                        along_y = 0
                    if along_y < 0 - tall_y:
                        along_y = 0 - tall_y
                    along_y = 0 - along_y
                shift = (along_y * slope) >> 8
                if dx < 0:
                    shift = 0 - shift
                near_x = ax + shift
                x = (near_x - window) >> 4
                stop = ((near_x + window) >> 4) + 1
                if x < left:
                    x = left
                if stop > right:
                    stop = right
            p[8] = y
            p[9] = x
            p[10] = stop
            p[11] = ax
            p[12] = ay
            p[13] = dx
            p[14] = dy
            p[15] = along
            line_pixels(buf, p, root)
            y += 1
        n += 1


class Pen:
    def __init__(self, fb):
        self.fb = fb
        self.buf = fb.buffer
        self.p = array.array("i", [0] * 24)
        self.p[6] = fb.width
        self.p[7] = fb.height
        self.q = array.array("i", [0, 0, 0, 0, 0, fb.width, fb.height] + [0] * 12)
        self.height = fb.height

    def stroke(self, segments, x, y, thickness, color):
        """Smooth thick lines. segments is x0, y0, x1, y1... in 1/16 pixel."""
        q = self.q
        q[0] = int(x * 16)
        q[1] = int(y * 16)
        q[2] = int(thickness * 16)
        q[3] = color
        q[4] = len(segments) // 4
        lines(self.buf, segments, q, ROOT)

    def ellipse(self, x, y, rx, ry, color, first=0, last=None, tilt=0.0):
        """A smooth oval. Sizes and positions can be fractions of a pixel.
        first and last limit the rows drawn, when only a slice is needed."""
        inset = 0
        if tilt == 0.0 and rx > 10 and ry > 10:
            # The built-in oval is much quicker, so let it fill the middle.
            # We only need to do the outer few pixels ourselves.
            self.fb.ellipse(int(x + 0.5), int(y + 0.5), int(rx) - 2, int(ry) - 2, color, True)
            inset = 5
        self.draw(ROUND, x, y, rx, ry, color, first, self.height if last is None else last, inset, tilt)

    def point(self, x, y, half_width, height, color):
        """A smooth triangle pointing down, like the bottom of a heart."""
        top = max(0, int(y))
        self.draw(POINT, x, y, half_width, height, color, top, self.height)

    def draw(self, widths, x, y, rx, ry, color, first, last, inset=0, tilt=0.0):
        rx = int(rx * 256)
        ry = int(ry * 256)
        if rx < 1 or ry < 1:
            return
        p = self.p
        p[0] = int(x * 256)
        p[1] = int(y * 256)
        p[20] = int(tilt * 256)                # a tilted eye: how far each row slides sideways per row
        p[2] = rx
        p[3] = ry
        p[4] = color
        p[5] = (STEPS << 16) // ry
        p[8] = first
        p[9] = last
        p[10] = rx - inset * 256 if inset else 0
        p[11] = ry - inset * 256 if inset else 0
        p[12] = (STEPS << 16) // p[11] if inset else 0
        shape(self.buf, widths, p, FADE)
