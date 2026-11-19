"""
main.py - Buddy's brain. MicroPython runs this file automatically on boot.

Everything happens in one loop that repeats forever:
  1. check the touch screen
  2. decide how Buddy feels
  3. update + draw the face
  4. send the picture to the screen
"""

import gc
import os
from machine import Pin, WDT, lightsleep, freq
freq(240000000)          # run the chip at full speed: smoother animation (uses a bit more battery)
Pin(42, Pin.OUT, value=0)   # buzzer driver off (Waveshare: keep this low or the regulator warms up)
Pin(41, Pin.OUT, value=1)   # SYS_EN: keeps the battery power ON after the PWR button is released (needed to run on battery only)
from lcd_s3 import LCD

# Create the screen FIRST, because it needs one big block of memory and
# loading other code first chops memory into smaller pieces.
# We only keep rows 40..200 (the face area): 280 x 160 x 2 = 90 KB. The top and bottom just stay background color.
gc.collect()             # gc = "garbage collector": frees unused memory
lcd = LCD(top=40, height=160)  # the screen (also our framebuffer): 280 x 160 band

# Next the drawing tables, while memory is still in big clean pieces. face.py
# is large, and turning it into code chops memory up.
import pen
gc.collect()

import random
from time import ticks_ms, ticks_diff, sleep_ms
import config
if config.EYE_STYLE == "pixel":
    from face_px import PixelFace as Face     # the chunky pixel eyes (60 frames a second)
else:
    from face import Face                      # the default smooth eyes
from touch import Touch
import overlay
import ui
from sound import Sound
import config
try:
    from imu import IMU
    imu = IMU()
except Exception:
    imu = None                 # no motion sensor? Buddy still works, just without motion tricks

# ---- How Buddy behaves (play with these numbers!) ----
HOLD_START_MS = 250     # holding longer than this starts the build-up
HOLD_BOOM_MS = 1300     # how long the build-up lasts before... boom!
LONELY_AFTER_MS = 35000  # ignored for 12 s -> sad and lonely
SLEEPY_AFTER_MS = 60000  # ignored for 24 s -> tired
ASLEEP_AFTER_MS = 85000  # ignored for 45 s -> falls asleep
SCREEN_OFF_AFTER_MS = 125000  # ignored for 1 min -> screen turns off to save battery
BATTERY_HOLD_MS = 600    # keep a finger on the screen this long to see the battery
FRAME_MS = 16            # target frame time; the board now needs about 18 ms, so it simply runs as fast as it can (about 55 frames a second)
JOYFUL_AFTER_MS = 2500   # stroke this long and Buddy gets joyful
TAP_GAP_MS = 450         # taps closer together than this count as pestering
TAPS_TO_DIZZY = 4        # this many in a row makes Buddy dizzy
PET_DISTANCE = 45        # finger must slide this many pixels to count as petting
FLICK_MS = 450           # a quick slide up or down, faster than this...
LOW_BATTERY_PCT = 15     # below this, Buddy gets tired and shows the battery by itself
DIM_AFTER_MS = 105000     # screen dims a little before it turns off
SHAKE_JOLTS = 4          # this many jolts within 1.5 s = shaken
CALM_NEEDED_MS = 700     # a shake only counts if Buddy was held still for this long just before it
SHAKE_COOLDOWN_MS = 8000 # after a decision, shaking is ignored for this long
SHAKE_STRENGTH = 0.4     # how big a sudden change in the motion reading counts as a jolt (in g)
FLICK_DISTANCE = 70      # ...and at least this long, asks Buddy yes or no

face = Face(lcd)
touch = Touch()
sound = Sound()
dev_mode = 'dev' in os.listdir()    # while developing we never light-sleep, so the USB cable keeps working

# Safety net: if anything ever freezes, the chip restarts itself after 8 s and Buddy wakes up again.
# (While developing, create an empty file called 'dev' on the board to switch this off.)
wdt = WDT(timeout=8000) if 'dev' not in os.listdir() else None

last_touch = ticks_ms()  # when you last touched Buddy
pressing = False         # is a finger on the screen right now?
press_start = 0
got_love = False         # did this press already trigger hearts?
focusing = 0.0           # how far the hold build-up has got (0 to 1)
pet_start = 0            # when the current stroke began
last_tap = 0             # when the last tap landed
taps = 0                 # how many quick taps in a row
start_x = start_y = 0    # where the finger landed
last_x = last_y = 0      # where the finger was last frame
slid = 0                 # how far the finger has slid during this press
petting = False          # is this press a stroke rather than a tap?
screen_on = True         # False while Buddy is saving battery
prev_mood = face.mood    # to play a sound when the mood changes
last_m = None            # previous motion reading
last_act = ""
prev_m = None
calm_start = 0
calm_len = 0
calm_end = 0
shake_ok = False
jolt_last = 0
shake_block = 0          # no shake decisions before this time (right after waking or deciding)
page_kind = 1            # which page: 1 = clock, 0 = battery
page_state = 0          # 0 = face, 1 = battery page sliding in / showing, 2 = sliding out
page_t = 0               # when the slide started
page_open_at = 0
SWIPE_DISTANCE = 70      # a quick slide to the LEFT at least this long opens the battery page
rest_v = 0.0             # the battery voltage when nothing is plugged in (to spot the charger)
was_plugged = False       # (with no battery, plugging in the cable IS the power-on, so a cable at start-up counts as plugging in)
plug_peak = 0.0
plug_next = ticks_ms() + 4500       # after the wake-up animation
tilt_ref_x = tilt_ref_y = 0.0   # the tilt Buddy is getting used to
tilt_since = ticks_ms()
tilt_hold = 7000                 # how long it keeps looking that way (5 to 10 s, random each time)
gaze_gain = 0.0                  # 1 = looking where it tilts, 0 = looking ahead
last_move = ticks_ms()   # when the device last moved
last_tap_mood = ""
jolts = []               # times of recent hard jolts
motion_tick = 0
tilt_x = tilt_y = 0.0    # gravity along the screen's right / down directions (in g)
upside = False
still_since = ticks_ms()
low_next = ticks_ms() + 5000   # when to next check for a low battery
overlay_until = 0
dimmed = False
think_at = ticks_ms() + 20000   # next time Buddy may think or wink on its own


def read_motion():
    """Read the motion sensor. Returns (x, y, z) in screen directions, or None."""
    if not imu:
        return None
    try:
        raw = imu.read()
    except OSError:
        return None
    (ax, sx), (ay, sy), (az, sz) = config.AXES
    return raw[ax] * sx, raw[ay] * sy, raw[az] * sz


def screen_off():
    lcd.write_cmd(0x28)        # tell the screen chip to stop showing anything
    lcd.backlight.value(0)     # the backlight uses the most battery, so turn it off


def screen_wake():
    lcd.write_cmd(0x29)        # screen chip: start showing again
    lcd.backlight.value(1)
    sound.play("wake")


# (no print here: with no computer plugged in, writing to the USB console can freeze the program)

while True:
    if wdt:
        wdt.feed()
    now = ticks_ms()
    frame_start = now
    finger = touch.read()

    # ---- charger: plugging it in plays the charging animation ----
    # Measured on this board: the charger lifts the battery reading by about 0.045 V (4.09 -> 4.14).
    if ticks_diff(now, plug_next) > 0:
        plug_next = now + 400
        v, pct, usb = overlay.read()
        if rest_v == 0.0:
            rest_v = v
        if was_plugged:
            plugged = v > plug_peak - 0.03 and v > rest_v - 0.01     # still on the charger until the reading drops
            if plugged and v > plug_peak:
                plug_peak = v
        else:
            if v < rest_v:
                rest_v = v                            # the resting level follows the lowest reading
            else:
                rest_v += 0.0004                      # and creeps up very slowly
            plugged = usb or (v - rest_v) > 0.025
            if plugged:
                plug_peak = v
        if plugged and not was_plugged:
            if not screen_on:
                screen_wake()
                screen_on = True
                dimmed = False
                lcd.backlight.percent(100)
            last_touch = now
            pressing = False
            page_state = 0
            face.charge_start(1.0 if v >= 4.25 else overlay.pct_of(v - 0.045) / 100)
        was_plugged = plugged
        overlay.charging[0] = plugged
        face.charge_sign = 0 if not plugged else (2 if (v >= 4.25 or overlay.pct_of(v - 0.045) >= 97) else 1)

    if not screen_on:
        m = read_motion()          # while napping we look every time (about 20 times a second)
        moved = False
        if m is not None:
            if last_m is not None:
                moved = (abs(m[0] - last_m[0]) + abs(m[1] - last_m[1]) + abs(m[2] - last_m[2])) > 0.3
            last_m = m
        if not finger and not moved:
            # Deep nap: skip all drawing and only check for a touch or a movement a few times a second.
            if dev_mode:
                sleep_ms(40)
            else:
                lightsleep(40)
            continue
        # A touch (or being picked up) wakes the screen.
        screen_wake()
        screen_on = True
        dimmed = False
        lcd.backlight.percent(100)
        last_touch = ticks_ms()
        if moved and not finger:
            face.set_mood("surprised", 1200)

    # ---- motion: read the sensor every frame (a shake is quick, so it must not be missed) ----
    motion_tick += 1
    m = read_motion()
    if m:
        tilt_x, tilt_y = m[0], m[1]
        mag = (m[0] ** 2 + m[1] ** 2 + m[2] ** 2) ** 0.5
        if abs(mag - 1.0) > 0.12:
            face.excite(0.004)                             # being carried or handled makes Buddy livelier
            last_move = now
        # A jolt = the reading changed a lot since last frame (that is what shaking does, back and forth).
        hit = False
        change = 0.0
        if prev_m is not None:
            change = abs(m[0] - prev_m[0]) + abs(m[1] - prev_m[1]) + abs(m[2] - prev_m[2])
            hit = change > SHAKE_STRENGTH and ticks_diff(now, jolt_last) > 90
        prev_m = m
        # Keep track of calm moments. A deliberate shake starts from stillness (you hold Buddy, then shake).
        # A keychain swinging in a bag is never still, so it can never start a decision.
        if change < 0.18:
            if calm_start == 0:
                calm_start = now or 1
        elif calm_start:
            calm_len = ticks_diff(now, calm_start)
            calm_end = now
            calm_start = 0
        if hit:
            jolt_last = now
            last_touch = now
            if face.mood in ("sleepy", "asleep") and not face.phase:
                face.wake()                                # asleep: a shake only wakes Buddy up
                jolts.clear()
                shake_block = now + 1800
            elif ticks_diff(now, shake_block) > 0:
                if not jolts:
                    shake_ok = calm_len >= CALM_NEEDED_MS and ticks_diff(now, calm_end) < 900
                if shake_ok:
                    jolts.append(now)
        while jolts and ticks_diff(now, jolts[0]) > 1500:
            jolts.pop(0)
        if (len(jolts) >= SHAKE_JOLTS and not face.phase and not face.water_on
                and ticks_diff(now, shake_block) > 0):
            jolts.clear()
            shake_block = now + SHAKE_COOLDOWN_MS
            face.decide()                                  # awake and shaken: Buddy decides yes or no!
        # upside down: the "down" direction of the screen points up
        flipped = tilt_y < -0.75
        if flipped and not upside and not pressing and not face.phase:
            face.set_mood("surprised", 1500)
            last_touch = now
        upside = flipped
        if abs(tilt_x) > 0.3 or abs(tilt_y) > 0.3:
            still_since = now

    if dimmed and ticks_diff(now, last_touch) < DIM_AFTER_MS:
        dimmed = False
        lcd.backlight.percent(100)

    # ---- the battery page (swipe left to open, swipe right or tap to close) ----
    if page_state:
        slide = min(1.0, ticks_diff(now, page_t) / 260)
        ease = slide * slide * (3 - 2 * slide)
        dx = int(280 * (1 - ease)) if page_state == 1 else int(280 * ease)
        if page_kind == 1:
            ui.load()
            ui.clock(lcd, dx, now)
        else:
            v, pct, usb = overlay.read()
            if usb and v < 4.25:
                pct = overlay.pct_of(v - 0.045)
            if config.UI_STYLE == "pixel":
                ui.battery(lcd, dx, pct, v, usb, overlay.charging[0], now)
            else:
                overlay.page(lcd, dx, pct, v, usb, overlay.charging[0], now)
        lcd.show_rows(0, 160)
        face.row0, face.row1 = 0, 160
        face.new0, face.new1 = 0, 160
        if page_state == 2 and slide >= 1.0:
            page_state = 0
            ui.unload()                               # free the font memory
            last_touch = now
            face.set_mood("happy", 1200)
        elif page_state == 1:
            if finger:
                if not pressing:
                    pressing = True
                    start_x, start_y = finger
                    press_start = now
                last_x, last_y = finger
            elif pressing:
                pressing = False
                ddx = last_x - start_x
                if page_kind == 1 and ddx < -50 and abs(last_y - start_y) < -ddx * 0.7:
                    page_kind = 0                                               # swipe left again: the battery page
                    page_t = now
                    page_open_at = now
                elif page_kind == 0 and ddx > 50:
                    page_kind = 1                                               # swipe right on the battery: back to the clock
                    page_t = now
                    page_open_at = now
                elif ddx > 50 or abs(ddx) < 25:                                 # swipe right on the clock, or a tap: back to Buddy
                    page_state = 2
                    page_t = now
            if ticks_diff(now, page_open_at) > 12000 and page_state == 1:      # nobody touched: go back by itself
                page_state = 2
                page_t = now
        last_touch = now
        rest = FRAME_MS - ticks_diff(ticks_ms(), frame_start)
        if rest > 0:
            sleep_ms(rest)
        continue

    if face.phase or face.water_on:
        # Buddy is busy deciding, so touches don't count until it's done.
        pressing = False
        face.finger_x = -999
        last_touch = now

    elif finger:
        x, y = finger
        if not pressing:
            # Finger just landed.
            pressing = True
            press_start = now
            got_love = False
            petting = False
            focusing = 0.0
            slid = 0
            last_x, last_y = x, y
            start_x, start_y = x, y
            taps = taps + 1 if ticks_diff(now, last_tap) < TAP_GAP_MS else 1
            last_tap = now
            face.poke()                           # a little bounce
            face.excite(0.12)
            sound.play("tap")
            if face.mood in ("sad", "sleepy", "asleep"):
                face.wake()                       # you're back!
                taps = 0
            elif face.mood in ("grumpy", "angry"):
                face.set_mood("angry", 2500)      # don't poke a grumpy Buddy
            elif taps >= TAPS_TO_DIZZY:
                face.set_mood("dizzy", 2200)      # too many pokes!
                taps = 0
            elif taps == 2:
                face.set_mood("excited", 1800)    # double tap
        ease = min(1.0, ticks_diff(now, press_start) / 600)           # the eyes ease into following
        ease = ease * ease * (3 - 2 * ease)
        face.look_at(140 + (x - 140) * ease, 120 + (y - 120) * ease)   # follow your finger
        face.finger_x = x                          # (the eye under the finger swells)

        # A sliding finger is a stroke, and Buddy loves that.
        slid += abs(x - last_x) + abs(y - last_y)
        last_x, last_y = x, y
        if slid > PET_DISTANCE and not petting and not got_love:
            petting = True
            pet_start = now
            face.focus(0)
        if petting:
            if ticks_diff(now, pet_start) > JOYFUL_AFTER_MS:
                face.set_mood("joyful", 1500)
            else:
                face.set_mood("happy", 1200)
        elif not got_love and face.mood in ("normal", "happy", "shy"):
            # Holding still: Buddy focuses harder and harder, then boom.
            held = ticks_diff(now, press_start) - HOLD_START_MS
            if held > 0:
                focusing = held / HOLD_BOOM_MS
                face.focus(min(1.0, focusing))
                if focusing >= 1:
                    face.boom()
                    got_love = True
        last_touch = now

    elif pressing:
        # Finger just lifted.
        pressing = False
        face.finger_x = -999
        face.focus(0)
        down = abs(last_y - start_y)
        if (ticks_diff(now, press_start) < 900 and (start_x - last_x) > SWIPE_DISTANCE
                and down < (start_x - last_x) * 0.7):
            page_state = 1                            # a swipe to the left: show the clock (swipe again for the battery)
            page_kind = 1
            page_t = now
            page_open_at = now
            pressing = False
            petting = False
            face.set_mood("normal")
            continue
        if False:
            pass                                  # (swiping up/down no longer asks yes or no: shaking does that now)
        elif focusing > 0.3 and not got_love:
            face.set_mood("sad", 900)             # aww, you let go too soon
        elif not got_love and not petting and face.mood in ("normal", "happy", "shy"):
            # A quick tap. Mostly happy, sometimes bashful.
            # A quick tap gets a different answer than last time (so it never feels like a recording).
            choice = random.choice([c for c in ("happy", "shy", "wink", "perk") if c != last_tap_mood])
            last_tap_mood = choice
            if choice == "wink":
                face.blink(320, random.choice((-1, 1)))
            elif choice == "perk":
                face.begin("perk")
            else:
                face.set_mood(choice, 2000)

    else:
        # Nobody is touching. Get bored over time.
        idle = ticks_diff(now, last_touch)
        g = (tilt_x * tilt_x + tilt_y * tilt_y) ** 0.5
        # Buddy looks where the tilt points, but gets used to it: if the tilt stays the same for
        # 5-10 s (bag hanging at an angle), the eyes drift back to the middle. A new tilt gets a new look.
        if abs(tilt_x - tilt_ref_x) + abs(tilt_y - tilt_ref_y) > 0.3:
            tilt_ref_x, tilt_ref_y = tilt_x, tilt_y
            tilt_since = now
            tilt_hold = random.randint(5000, 10000)
        want = 1.0 if (g > 0.2 and ticks_diff(now, tilt_since) < tilt_hold) else 0.0
        gaze_gain += (want - gaze_gain) * (0.25 if want else 0.04)    # looks quickly, relaxes slowly
        if gaze_gain > 0.03 and not face.phase and face.mood in ("normal", "happy", "thinking"):
            # Tilting: the eyes look toward where "down" is, in ANY direction (a full circle),
            # and look further the more it is tilted.
            s = max(0.0, min(0.7, (g - 0.2) / 0.5)) * gaze_gain        # never more than 70% of the way, like lilguy
            g = max(g, 0.01)
            face.target_x = tilt_x / g * 20 * s
            face.target_y = tilt_y / g * 14 * s
            face.hold_until = now + 400            # stops the random wandering while tilted
        if idle > DIM_AFTER_MS and not dimmed:
            dimmed = True
            lcd.backlight.percent(25)
        if idle > SCREEN_OFF_AFTER_MS:
            screen_off()
            screen_on = False
            continue
        elif idle > ASLEEP_AFTER_MS:
            face.set_mood("asleep")
        elif idle > SLEEPY_AFTER_MS and face.mood in ("normal", "sad"):
            face.set_mood("sleepy")
        elif idle > LONELY_AFTER_MS and face.mood == "normal":
            face.set_mood("sad")

    # low battery: Buddy gets tired and shows the battery by itself (checked every 2 minutes)
    if screen_on and not pressing and ticks_diff(now, low_next) > 0:
        low_next = now + 120000
        v, pct, usb = overlay.read()
        if not usb and pct <= LOW_BATTERY_PCT and v > 2.5:
            page_state = 1                  # the battery page opens by itself
            page_kind = 0
            page_t = now
            page_open_at = now
            sound.play("low")
    # how lively Buddy likes to be: carried around = more, left alone for a long time = calmer
    if ticks_diff(now, last_move) < 20000:
        face.energy_base = 0.62
    elif ticks_diff(now, last_move) > 60000 and ticks_diff(now, last_touch) > 40000:
        face.energy_base = 0.25
    else:
        face.energy_base = 0.45
    face.update()
    face.draw()
    face.show()
    if face.mood != prev_mood:
        prev_mood = face.mood
        sound.play(prev_mood)
    sound.update()

    # Even frame spacing looks smoother than simply going as fast as possible.
    rest = FRAME_MS - ticks_diff(ticks_ms(), frame_start)
    if rest > 0:
        sleep_ms(rest)
