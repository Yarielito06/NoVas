"""
ui.py - Buddy's clean, minimal pages (the clock, in the style of a smartwatch).

Text is drawn from smooth 4-bit font bitmaps (ui_font.bin, made from the open font Hanken Grotesk by
ui_tools/make_font.py), blended into the screen like the eyes, so letters have soft edges instead of chunky pixels.
The time comes from the board's own clock chip (PCF85063, I2C address 0x51), which keeps counting while the battery is in.
"""
import array
import framebuf
import micropython
from machine import I2C, Pin
from time import ticks_ms, ticks_diff
import config

RTC_ADDR = 0x51
DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def rgb(r, g, b):
    c = ((int(r) & 0xF8) << 8) | ((int(g) & 0xFC) << 3) | (int(b) >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


WHITE = rgb(246, 247, 250)
GREY = rgb(128, 134, 142)
DIM = rgb(36, 40, 46)
GREEN = rgb(24, 255, 110)

_p = array.array("i", [0] * 8)
_fonts = [None, None]          # the font bitmaps (loaded when the page opens) and the glyph tables
_i2c = [None]
_t = [0, None]                 # when the time was last read, and what it was


@micropython.viper
def blit4(buf: ptr16, g: ptr8, p: ptr32):
    """Blend one 4-bit glyph into the screen. p: 0 x, 1 y, 2 width, 3 height, 4 colour, 5 screen width, 6 screen height, 7 offset."""
    x0 = p[0]
    y0 = p[1]
    w = p[2]
    h = p[3]
    color = p[4]
    sw = p[5]
    sh = p[6]
    off = p[7]
    spread = 0x07E0F81F
    c = ((color & 255) << 8) | ((color >> 8) & 255)
    wide = (c | (c << 16)) & spread
    r = 0
    while r < h:
        y = y0 + r
        if y >= 0 and y < sh:
            col = 0
            while col < w:
                x = x0 + col
                if x >= 0 and x < sw:
                    idx = r * w + col
                    b = g[off + (idx >> 1)]
                    a = b & 15
                    if (idx & 1) == 0:
                        a = b >> 4
                    if a:
                        cover = (a * 137) >> 6
                        if cover >= 32:
                            buf[y * sw + x] = color
                        else:
                            q = buf[y * sw + x]
                            q = ((q & 255) << 8) | ((q >> 8) & 255)
                            q = (q | (q << 16)) & spread
                            q = (q + (((wide - q) * cover) >> 5)) & spread
                            q = (q | (q >> 16)) & 0xFFFF
                            buf[y * sw + x] = ((q & 255) << 8) | ((q >> 8) & 255)
                col += 1
        r += 1


def load():
    """Read the font bitmaps into memory (about 24 KB), only while the smooth clock page is on screen."""
    if config.UI_STYLE == "pixel":
        return
    if _fonts[0] is None:
        import uifont
        with open("ui_font.bin", "rb") as f:
            _fonts[0] = f.read()
        _fonts[1] = {"TIME": uifont.TIME, "TEXT": uifont.TEXT, "SMALL": uifont.SMALL}


def unload():
    _fonts[0] = None
    _fonts[1] = None
    import sys
    sys.modules.pop("uifont", None)


def width(font, s):
    tab = _fonts[1][font]
    n = 0
    for ch in s:
        e = tab.get(ch)
        if e:
            n += e[5]
    return n


def text(lcd, font, s, x, base, color):
    """Draw s with its baseline at row `base`, starting at column x."""
    tab = _fonts[1][font]
    data = _fonts[0]
    p = _p
    p[4] = color
    p[5] = lcd.width
    p[6] = lcd.height
    for ch in s:
        e = tab.get(ch)
        if not e:
            continue
        if e[1]:
            p[0] = x + e[3]
            p[1] = base + e[4]
            p[2] = e[1]
            p[3] = e[2]
            p[7] = e[0]
            blit4(lcd.buffer, data, p)
        x += e[5]
    return x


def text_centre(lcd, font, s, cx, base, color):
    text(lcd, font, s, cx - width(font, s) // 2, base, color)


# ---- the clock chip ----
def _bus():
    if _i2c[0] is None:
        _i2c[0] = I2C(0, sda=Pin(11), scl=Pin(10), freq=400000)
    return _i2c[0]


def _bcd(n):
    return ((n // 10) << 4) | (n % 10)


def _dec(b):
    return (b >> 4) * 10 + (b & 15)


def set_time(year, month, day, hour, minute, second, weekday):
    """Set the clock chip. weekday: 0 = Sunday ... 6 = Saturday."""
    d = bytes((_bcd(second), _bcd(minute), _bcd(hour), _bcd(day), weekday, _bcd(month), _bcd(year % 100)))
    _bus().writeto_mem(RTC_ADDR, 0x04, d)


def read_time():
    """(hour, minute, second, weekday, day, month, year) or None if the chip lost its time."""
    now = ticks_ms()
    if _t[1] is not None and ticks_diff(now, _t[0]) < 250:
        return _t[1]
    try:
        d = _bus().readfrom_mem(RTC_ADDR, 0x04, 7)
    except OSError:
        return _t[1]
    if d[0] & 0x80:                       # the "clock stopped" flag: the time is not trustworthy
        _t[0], _t[1] = now, None
        return None
    r = (_dec(d[2] & 0x3F), _dec(d[1] & 0x7F), _dec(d[0] & 0x7F), d[4] & 7, _dec(d[3] & 0x3F), _dec(d[5] & 0x1F), 2000 + _dec(d[6]))
    _t[0], _t[1] = now, r
    return r


def clock_smooth(lcd, dx, now):
    """The smooth clock page: one big thin time, the date under it, and a hair-thin line that fills once a minute."""
    lcd.fill(0)
    t = read_time()
    cx = 140 + dx
    if t is None:
        text_centre(lcd, "TEXT", "Clock not set", cx, 80, GREY)
        dots(lcd, dx, 0, 2)
        return
    h, m, s, wd, day, mon, year = t
    pm = h >= 12
    if not config.CLOCK_24H:
        h = h % 12
        if h == 0:
            h = 12
    hs = "%d" % h if not config.CLOCK_24H else "%02d" % h
    ms = "%02d" % m
    # the time, centred as a whole
    total = width("TIME", hs) + width("TIME", ":") + width("TIME", ms)
    x = cx - total // 2
    base = 88
    x = text(lcd, "TIME", hs, x, base, WHITE)
    cw = width("TIME", ":")
    text(lcd, "TIME", ":", x, base - 2, GREEN if (s & 1) == 0 else rgb(14, 120, 52))      # the colon breathes once a second
    x += cw
    text(lcd, "TIME", ms, x, base, WHITE)
    if not config.CLOCK_24H:
        text(lcd, "SMALL", "PM" if pm else "AM", cx + total // 2 - 22, 26, GREY)
    # the date
    text_centre(lcd, "TEXT", "%s, %d %s" % (DAYS[wd % 7], day, MONTHS[(mon - 1) % 12]), cx, 122, GREY)
    # seconds: a thin line, filled in green
    x0, x1 = 60 + dx, 220 + dx
    lcd.fill_rect(x0, 138, x1 - x0, 2, DIM)
    lcd.fill_rect(x0, 138, max(2, (x1 - x0) * (s + 1) // 60), 2, GREEN)
    dots(lcd, dx, 0, 2)


def dots(lcd, dx, index, total):
    """Page dots, small and round-ish: the current page is bright."""
    x = 140 - (total * 12 - 4) // 2 + dx
    for i in range(total):
        c = GREEN if i == index else DIM
        lcd.fill_rect(x + i * 12, 153, 4, 4, c)


# ---------------------------------------------------------------------------------------------
# Pixel style: the same chunky 6-pixel blocks as the pixel eyes. Letters are the board's built-in
# 8 x 8 font, blown up so every dot of a letter is a square block.
# ---------------------------------------------------------------------------------------------
def ptext(lcd, s, x, y, scale, color):
    """Draw s in block letters. Each dot of the 8 x 8 font becomes a scale x scale square; neighbours are merged into runs."""
    n = len(s)
    if not n:
        return
    w = n * 8
    t = framebuf.FrameBuffer(bytearray(w), w, 8, framebuf.MONO_HLSB)
    t.text(s, 0, 0, 1)
    for py in range(8):
        px = 0
        while px < w:
            if t.pixel(px, py):
                st = px
                while px < w and t.pixel(px, py):
                    px += 1
                lcd.fill_rect(x + st * scale, y + py * scale, (px - st) * scale, scale, color)
            else:
                px += 1


def pdots(lcd, dx, index, total):
    """Page dots as little blocks."""
    x = 140 - (total * 12 - 6) // 2 + dx
    for i in range(total):
        if i == index:
            lcd.fill_rect(x + i * 12, 152, 6, 6, GREEN)
        else:
            lcd.fill_rect(x + i * 12, 152, 6, 6, DIM)


def clock_px(lcd, dx, now):
    """The pixel clock: big block digits, the date, and a bar of little blocks that fills once a minute."""
    lcd.fill(0)
    t = read_time()
    if t is None:
        ptext(lcd, "CLOCK NOT SET", 20 + dx, 66, 2, GREY)
        pdots(lcd, dx, 0, 2)
        return
    h, m, s, wd, day, mon, year = t
    suffix = ""
    if not config.CLOCK_24H:
        suffix = "PM" if h >= 12 else "AM"
        h = h % 12
        if h == 0:
            h = 12
    hs = "%02d" % h if config.CLOCK_24H else "%2d" % h
    base = 20 + dx
    ptext(lcd, hs, base, 22, 6, WHITE)
    ptext(lcd, ":", base + 96, 22, 6, GREEN if (s & 1) == 0 else rgb(14, 120, 52))
    ptext(lcd, "%02d" % m, base + 144, 22, 6, WHITE)
    if suffix:
        ptext(lcd, suffix, 232 + dx, 2, 2, GREY)
    ptext(lcd, "%s %d %s" % (DAYS[wd % 7][:3].upper(), day, MONTHS[(mon - 1) % 12][:3].upper()), 20 + dx, 84, 3, GREY)
    # the seconds: 30 little blocks
    lit = (s + 1) // 2
    for i in range(30):
        c = GREEN if i < lit else DIM
        lcd.fill_rect(20 + dx + i * 8, 122, 6, 6, c)
    pdots(lcd, dx, 0, 2)


def battery(lcd, dx, pct, v, usb, charging, now):
    """The pixel battery page, on the same 6-pixel grid as the eyes."""
    lcd.fill(0)
    low = rgb(255, 190, 60)
    red = rgb(255, 80, 70)
    frame = rgb(150, 200, 170)
    soft = rgb(90, 150, 115)
    full = 100 if usb and not charging else pct
    if usb and v >= 4.25:
        full = 100
    lit = (full + 9) // 10
    color = GREEN if full > 30 else (low if full > 12 else red)
    if charging and (now // 600) % 4 == 3:
        ptext(lcd, "BATTERY", 20 + dx, 4, 2, soft)
    else:
        ptext(lcd, "CHARGING" if charging else "BATTERY", 20 + dx, 4, 2, GREEN if charging else soft)
    ptext(lcd, "%.2fV" % v, 184 + dx, 4, 2, soft)
    # the battery: a block outline with cut corners, a tip, and ten segments
    x0, y0, w, h, t = 20 + dx, 24, 204, 60, 6
    lcd.fill_rect(x0 + t, y0, w - 2 * t, t, frame)
    lcd.fill_rect(x0 + t, y0 + h - t, w - 2 * t, t, frame)
    lcd.fill_rect(x0, y0 + t, t, h - 2 * t, frame)
    lcd.fill_rect(x0 + w - t, y0 + t, t, h - 2 * t, frame)
    lcd.fill_rect(x0 + w, y0 + 18, 6, 24, frame)
    for k in range(10):
        c = DIM
        if k < lit:
            c = color
        elif k == lit and charging and (now // 350) % 2 == 0:
            c = color
        lcd.fill_rect(x0 + 12 + k * 18, y0 + 12, 12, 36, c)
    label = "USB" if (usb and not charging and v >= 4.25) else "%d%%" % full
    ptext(lcd, label, 20 + dx, 96, 6, WHITE)
    pdots(lcd, dx, 1, 2)


def clock(lcd, dx, now):
    if config.UI_STYLE == "pixel":
        clock_px(lcd, dx, now)
    else:
        clock_smooth(lcd, dx, now)
