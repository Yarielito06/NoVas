"""config.py - small settings you may want to change (also used for the sensor directions)."""
# How the motion sensor's x, y, z become the SCREEN's directions (right, down, out of the screen).
# Each entry is (which sensor axis 0/1/2, sign +1/-1). We find the right values by tilting the device.
AXES = ((0, 1), (1, 1), (2, 1))

CLOCK_24H = True          # True: 14:30   False: 2:30 PM
EYE_STYLE = "pixel"        # "classic" = the smooth default eyes, "pixel" = chunky pixel eyes
UI_STYLE = "pixel"         # pages (clock, battery): "pixel" = chunky blocks like the pixel eyes, "smooth" = thin modern fonts
