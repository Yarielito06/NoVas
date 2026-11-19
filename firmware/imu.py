"""
imu.py - the motion sensor (QMI8658C, I2C address 0x6B, on the same two wires as the touch chip).
We only use the accelerometer: it feels gravity (so we know which way is down) and shakes.
The numbers come out in g (1.0 = ordinary gravity).
"""
from machine import I2C, Pin
import struct

ADDRESS = 0x6B


class IMU:
    def __init__(self, i2c=None):
        self.i2c = i2c or I2C(0, sda=Pin(11), scl=Pin(10), freq=400000)
        if self.i2c.readfrom_mem(ADDRESS, 0x00, 1)[0] != 0x05:      # "who am I" check
            raise OSError("motion sensor not found")
        w = self.i2c.writeto_mem
        w(ADDRESS, 0x02, b"\x40")      # CTRL1: read several values in one go
        w(ADDRESS, 0x03, b"\x26")      # CTRL2: accelerometer +-8 g, 125 readings a second
        w(ADDRESS, 0x06, b"\x01")      # CTRL5: smooth the readings a little
        w(ADDRESS, 0x08, b"\x01")      # CTRL7: accelerometer on, gyroscope off (saves battery)

    def read(self):
        """Return (x, y, z) in g, in the sensor's own directions."""
        d = self.i2c.readfrom_mem(ADDRESS, 0x35, 6)
        x, y, z = struct.unpack("<hhh", d)
        return x / 4096, y / 4096, z / 4096

    def power_down(self):
        self.i2c.writeto_mem(ADDRESS, 0x08, b"\x00")

    def power_up(self):
        self.i2c.writeto_mem(ADDRESS, 0x08, b"\x01")
