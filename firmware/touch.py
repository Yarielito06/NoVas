"""
touch.py - reads your finger from the touch chip (CST816T) on the Waveshare 1.69 screen.
I2C: SDA = GPIO11, SCL = GPIO10, reset = GPIO13, address 0x15. The chip only answers after its reset pin is pulsed.
The chip reports the glass in its normal upright shape (x 0..239, y 0..279); we turn that to match the sideways picture.
"""
from machine import I2C, Pin
from time import sleep_ms
import lcd_s3

ADDRESS = 0x15
# If Buddy's eyes follow your finger the WRONG way, flip these.
FLIP_X = False
FLIP_Y = False


class Touch:
    def __init__(self):
        rst = Pin(13, Pin.OUT, value=1)
        sleep_ms(10); rst(0); sleep_ms(20); rst(1); sleep_ms(80)
        self.i2c = I2C(0, sda=Pin(11), scl=Pin(10), freq=400000)

    def read(self):
        """Return (x, y) of the finger on the 280 x 240 sideways screen, or None if nobody is touching."""
        try:
            data = self.i2c.readfrom_mem(ADDRESS, 0x01, 6)   # [gesture, finger count, x hi, x lo, y hi, y lo]
        except OSError:
            return None
        if data[1] == 0:
            return None
        rx = ((data[2] & 0x0F) << 8) | data[3]     # 0..239 across the short side
        ry = ((data[4] & 0x0F) << 8) | data[5]     # 0..279 along the long side
        if lcd_s3.ROTATION == "landscape":
            x, y = ry, 239 - rx
        else:
            x, y = 279 - ry, rx
        if FLIP_X:
            x = 279 - x
        if FLIP_Y:
            y = 239 - y
        return x, y
