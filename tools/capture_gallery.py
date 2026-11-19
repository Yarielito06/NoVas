"""
Take pictures of NoVas's face straight from the board's screen memory (no camera needed).

    1. copy the firmware to the board (tools/deploy.sh), then:
    2. mpremote run tools/capture_gallery.py > gallery.txt
    3. python tools/sheet.py gallery.txt gallery.png 4        (turns the capture into one picture; needs: pip install pillow numpy)

It sets each mood in turn, freezes the random movement so every picture is steady, and prints the screen as run-length coded text.
"""
import gc, binascii, io
from machine import freq
freq(240000000)
from lcd_s3 import LCD
gc.collect()
lcd = LCD(top=40, height=160)
import pen
gc.collect()
from face_px import PixelFace
from time import sleep_ms
f = PixelFace(lcd)
def frames(n, d=6):
    for i in range(n):
        f.update(); f.draw(); f.show(); sleep_ms(d)
def cap(name):
    b = lcd.buffer
    n = len(b) // 2
    out = bytearray()
    prev = b[0] | (b[1] << 8); run = 1
    for k in range(1, n):
        v = b[2 * k] | (b[2 * k + 1] << 8)
        if v == prev and run < 65535:
            run += 1
        else:
            out += bytes((prev & 255, prev >> 8, run & 255, run >> 8))
            prev = v; run = 1
    out += bytes((prev & 255, prev >> 8, run & 255, run >> 8))
    print("BEGIN", name, len(out))
    for i in range(0, len(out), 600):
        print(binascii.b2a_base64(out[i:i+600]).decode().strip())
    print("END")
frames(300)
import sys
moods = ("normal", "happy", "excited", "love", "surprised", "angry", "sad", "shy", "sleepy", "thinking", "joyful", "grumpy")
def calm():
    f.todo = []
    f.blink_start = None
    f.blink_at = 10**9
    f.next_action = 10**9
    f.next_tiny = 10**9
    f.next_micro = 10**9
    f.next_pj = 10**9
    f.micro_tx = f.micro_ty = f.pj_tx = f.pj_ty = 0.0
    f.target_x = f.target_y = 0.0
    f.hop = f.hop_v = f.hop2 = f.hop2_v = 0.0
    f.eye_vx = f.eye_vy = 0.0
    f.tilt_target = 0.0
    f.mood_until = 0
    f.smile_target = 0.0
    f.squint_target = 0.0
    f.perk_target = 0.0
    f.dream_target = 0.0
for m in moods:
    f.set_mood(m, 0)
    for k in range(8):
        calm(); frames(50)
    cap(m)
