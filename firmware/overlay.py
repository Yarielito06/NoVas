"""
overlay.py - the battery readout Buddy shows while you hold the screen.

Battery voltage comes in on GPIO1 through a 200K / 100K divider on the board, so: volts = pin volts x 3.
Plugged into USB the charger holds that point at about 4.3 V whatever the battery does, so we show "USB"
instead of a percentage then. On battery alone we turn the voltage into a percentage with a typical
single-cell LiPo curve (this is only a good guess; we can calibrate it later).
"""
import framebuf
from machine import Pin, ADC
from time import ticks_ms, ticks_diff
from face import rgb

_adc = ADC(Pin(1), atten=ADC.ATTN_11DB)
charging = [False]                       # set by buddy.py when it notices the charger
_last = [0, 4.0, 100, False]           # when we last measured, volts, percent, on usb?

# volts -> percent, a typical LiPo discharge curve
_CURVE = ((4.20, 100), (4.10, 90), (4.00, 80), (3.92, 68), (3.85, 55), (3.79, 42), (3.73, 30), (3.67, 20), (3.58, 10), (3.45, 4), (3.30, 0))


def pct_of(v):
    """Battery percent for a voltage (the typical LiPo curve)."""
    if v >= _CURVE[0][0]:
        return 100
    if v <= _CURVE[-1][0]:
        return 0
    for i in range(len(_CURVE) - 1):
        hi_v, hi_p = _CURVE[i]
        lo_v, lo_p = _CURVE[i + 1]
        if v >= lo_v:
            return int(lo_p + (v - lo_v) * (hi_p - lo_p) / (hi_v - lo_v))
    return 0


def read():
    """Return (volts, percent, usb). Cached for a quarter of a second."""
    now = ticks_ms()
    if ticks_diff(now, _last[0]) > 250 or _last[0] == 0:
        uv = 0
        for _ in range(16):
            uv += _adc.read_uv()
        v = uv / 16 / 1000000 * 3
        pct = pct_of(v)
        _last[0] = now or 1
        _last[1] = v
        _last[2] = pct
        _last[3] = v >= 4.25 or charging[0]
    return _last[1], _last[2], _last[3]


def _text(fb, s, x, y, scale, color):
    """Draw big text: the built-in 8 x 8 letters, each pixel blown up to scale x scale."""
    t = framebuf.FrameBuffer(bytearray(len(s) * 8), len(s) * 8, 8, framebuf.MONO_HLSB)
    t.text(s, 0, 0, 1)
    for py in range(8):
        for px in range(len(s) * 8):
            if t.pixel(px, py):
                fb.fill_rect(x + px * scale, y + py * scale, scale, scale, color)


BOLT = ("....XXX.", "...XXX..", "..XXX...", ".XXXXXX.", "..XXXX..", "...XX...", "..XX....", ".X......")


def _pixels(fb, rows, x, y, scale, color):
    """Draw a small bitmap given as strings: every X becomes a square block (that is the pixel-art look)."""
    for ry in range(len(rows)):
        row = rows[ry]
        for rx in range(len(row)):
            if row[rx] == "X":
                fb.fill_rect(x + rx * scale, y + ry * scale, scale, scale, color)


def dots(lcd, dx, index, total):
    """Page dots at the bottom: little squares, the current page is bright and bigger."""
    ink = rgb(24, 255, 110)
    soft = rgb(40, 90, 62)
    x = 140 - (total * 12 - 4) // 2 + dx
    for i in range(total):
        if i == index:
            lcd.fill_rect(x + i * 12 - 1, 153, 6, 6, ink)
        else:
            lcd.fill_rect(x + i * 12, 154, 4, 4, soft)


def page(lcd, dx, pct, v, usb, charging, now):
    """The battery screen, in chunky pixel style. dx slides the whole page sideways (0 = in place).
    Everything is blocks: a battery made of 10 segments, big pixel digits, a pixel lightning bolt."""
    lcd.fill(0)
    ink = rgb(24, 255, 110)
    low = rgb(255, 190, 60)
    red = rgb(255, 80, 70)
    dim = rgb(14, 48, 30)
    frame = rgb(150, 200, 170)
    soft = rgb(90, 150, 115)
    full = 100 if usb and not charging else pct
    if usb and v >= 4.25:
        full = 100
    lit = (full + 9) // 10
    color = ink if full > 30 else (low if full > 12 else red)
    _text(lcd, "BATTERY", 20 + dx, 10, 2, soft)
    if charging:
        _pixels(lcd, BOLT, 238 + dx, 6, 3, ink if (now // 400) % 2 == 0 else soft)
    # the battery: a chunky outline with its corners cut off (pixel art), a tip, and 10 segments
    x0, y0, w, h, t = 20 + dx, 34, 196, 66, 6
    lcd.fill_rect(x0 + t, y0, w - 2 * t, t, frame)
    lcd.fill_rect(x0 + t, y0 + h - t, w - 2 * t, t, frame)
    lcd.fill_rect(x0, y0 + t, t, h - 2 * t, frame)
    lcd.fill_rect(x0 + w - t, y0 + t, t, h - 2 * t, frame)
    lcd.fill_rect(x0 + w, y0 + 18, 12, h - 36, frame)                   # the tip
    for s in range(10):
        sx = x0 + t + 5 + s * 18
        c = dim
        if s < lit:
            c = color
        elif s == lit and charging and (now // 350) % 2 == 0:
            c = color                                                   # the next segment blinks while charging
        lcd.fill_rect(sx, y0 + t + 4, 16, h - 2 * t - 8, c)
    # the number, big
    label = "USB" if (usb and not charging and v >= 4.25) else "%d%%" % full
    _text(lcd, label, 20 + dx, 112, 5, rgb(235, 245, 238))
    if charging:
        if (now // 600) % 4 != 3:
            _text(lcd, "CHARGING", 150 + dx, 114, 2, ink)
        _text(lcd, "%.2fV" % v, 150 + dx, 136, 2, soft)
    else:
        _text(lcd, "%.2fV" % v, 150 + dx, 126, 2, soft)
    dots(lcd, dx, 1, 2)


def draw(lcd, face):
    """Draw the battery at the bottom of the face band, and make sure those rows get sent to the screen."""
    v, pct, usb = read()
    white = rgb(235, 240, 245)
    green = rgb(90, 230, 120)
    amber = rgb(255, 190, 60)
    red = rgb(255, 80, 70)
    label = "CHG" if usb else "%d%%" % pct
    text_w = len(label) * 8 * 3
    total = 44 + 10 + text_w
    x0 = (lcd.width - total) // 2
    y0 = 131                                   # rows inside the face band (the band is 160 rows tall)
    bar = green if (usb or pct > 30) else (amber if pct > 12 else red)
    # rounded battery: an outline with the corners shaved off, a tip, and a fill bar
    lcd.rect(x0, y0 + 2, 40, 22, white)
    for cx, cy in ((x0, y0 + 2), (x0 + 39, y0 + 2), (x0, y0 + 23), (x0 + 39, y0 + 23)):
        lcd.pixel(cx, cy, 0)                                  # nibble each corner
    lcd.fill_rect(x0 + 40, y0 + 8, 4, 10, white)
    fill = 100 if usb else pct
    lcd.fill_rect(x0 + 3, y0 + 5, max(0, min(34, fill * 34 // 100)), 16, bar)
    if usb:                                                    # a lightning bolt while charging
        dark = rgb(20, 40, 25)
        lcd.line(x0 + 22, y0 + 5, x0 + 15, y0 + 14, dark)
        lcd.line(x0 + 15, y0 + 14, x0 + 24, y0 + 14, dark)
        lcd.line(x0 + 24, y0 + 14, x0 + 18, y0 + 21, dark)
    _text(lcd, label, x0 + 54, y0, 3, white)
    face.new0 = min(face.new0, y0 - 2)         # tell the face these rows changed
    face.new1 = max(face.new1, y0 + 28)
