"""
lcd_s3.py - screen for the Waveshare ESP32-S3-Touch-LCD-1.69 (ST7789V2, 240 x 280), used by Buddy.

Same idea as the old round screen: we keep a framebuffer for just a BAND of rows (where the face is),
draw into it, and send only the rows that changed. The screen is turned sideways: 280 wide x 240 high.
If Buddy appears upside down, change ROTATION to "landscape180" (and flip the touch the same way in touch.py).
"""
import framebuf
from machine import Pin, SPI, PWM
from time import sleep_ms

ROTATION = "landscape"
MADCTL = {"landscape": 0x70, "landscape180": 0xA0}

W, H_FULL = 280, 240
SPI_HZ = 80_000_000             # screen data speed (if you ever see noise or flicker, try 60_000_000 again)
X_OFF = 20                      # the 240 x 280 glass sits 20 columns into the chip's 240 x 320 memory


class Backlight:
    """Looks like a Pin (value(0/1)) but can also dim."""
    def __init__(self, pin):
        self.pwm = PWM(Pin(pin), freq=2000, duty_u16=0)

    def value(self, v):
        self.pwm.duty_u16(65535 if v else 0)

    def percent(self, p):
        self.pwm.duty_u16(int(65535 * max(0, min(100, p)) / 100))


class LCD(framebuf.FrameBuffer):
    def __init__(self, top=40, height=160):
        self.width = W
        self.height = height            # rows in our band
        self.top = top                  # which screen row the band starts at
        self.spi = SPI(2, baudrate=SPI_HZ, polarity=0, phase=0, sck=Pin(6), mosi=Pin(7))
        self.dc = Pin(4, Pin.OUT, value=0)
        self.cs = Pin(5, Pin.OUT, value=1)
        self.rst = Pin(8, Pin.OUT, value=1)
        self.backlight = Backlight(15)
        self.buffer = bytearray(self.width * self.height * 2)
        self.view = memoryview(self.buffer)
        self.rows = bytearray(4)
        super().__init__(self.buffer, self.width, self.height, framebuf.RGB565)
        self._init()
        self.clear_all(0)
        self.backlight.value(1)

    def write_cmd(self, c, data=None):
        self.cs(0); self.dc(0); self.spi.write(bytes([c])); self.dc(1)
        if data:
            self.spi.write(data)
        self.cs(1)

    def _init(self):
        self.rst(1); sleep_ms(10); self.rst(0); sleep_ms(20); self.rst(1); sleep_ms(120)
        w = self.write_cmd
        w(0x11); sleep_ms(120)
        w(0x36, bytes([MADCTL[ROTATION]]))
        w(0x3A, b"\x05")
        w(0xB2, b"\x0C\x0C\x00\x33\x33"); w(0xB7, b"\x35"); w(0xBB, b"\x32"); w(0xC2, b"\x01")
        w(0xC3, b"\x15"); w(0xC4, b"\x20"); w(0xC6, b"\x0F"); w(0xD0, b"\xA4\xA1"); w(0xD6, b"\xA1")
        w(0xE0, b"\xF0\x00\x04\x04\x04\x05\x29\x33\x3E\x38\x12\x12\x28\x30")
        w(0xE1, b"\xF0\x07\x0A\x0D\x0B\x07\x28\x33\x3E\x36\x14\x14\x29\x32")
        w(0x21)
        w(0x29); sleep_ms(20)
        # columns stay the same for every frame: 20 .. 299
        w(0x2A, bytes([0, X_OFF, (X_OFF + W - 1) >> 8, (X_OFF + W - 1) & 255]))

    def clear_all(self, color):
        """Paint the whole screen one colour (row by row, so no big buffer is needed)."""
        row = bytearray(W * 2)
        lo, hi = color & 0xFF, color >> 8
        for i in range(0, len(row), 2):
            row[i] = lo; row[i + 1] = hi
        self.write_cmd(0x2B, bytes([0, 0, 0, H_FULL - 1]))
        self.cs(0); self.dc(0); self.spi.write(b"\x2C"); self.dc(1)
        for _ in range(H_FULL):
            self.spi.write(row)
        self.cs(1)

    def show_rows(self, y0, y1):
        """Send only rows y0..y1 of our band (the slowest part of a frame is sending pixels)."""
        rows = self.rows
        first = self.top + y0
        last = self.top + y1 - 1
        rows[0] = first >> 8; rows[1] = first & 255; rows[2] = last >> 8; rows[3] = last & 255
        self.cs(0); self.dc(0); self.spi.write(b"\x2B"); self.dc(1); self.spi.write(rows)
        self.dc(0); self.spi.write(b"\x2C"); self.dc(1)
        self.spi.write(self.view[y0 * self.width * 2:y1 * self.width * 2])
        self.cs(1)

    def show(self):
        self.show_rows(0, self.height)
