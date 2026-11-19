"""
face.py - draws Buddy's face and animates it.

How drawing works here:
  The screen driver gives us a "framebuffer": a big chunk of memory with
  one spot per pixel (240 x 240). We draw shapes INTO that memory, and
  then lcd.show() sends the whole picture to the screen at once.

Why the eyes feel alive:
  1. Springs. Nothing jumps to a new value. Eyes are pulled toward a target
     like a weight on a spring, so they overshoot a little and settle.
  2. Layers move separately. The eye moves, and the pupil follows slightly
     late and travels further. That lag reads as "soft and real".
  3. Random timing. Buddy picks a small behaviour (glance, stare, tilt...)
     and waits a random time before the next one, so there's no pattern.
  4. Weight. Bodies squash when they land and stretch when they fly, they dip
     before they jump, and each emotion moves at its own speed.
  5. Moods are just numbers. "Happy" is the cheeks pushing up, "angry" is
     slanted eyelids and a red tint. They blend, so moods melt into each other.
"""

import math
import random
import array
import os
from time import ticks_ms, ticks_diff, ticks_add
from pen import Pen, ROUND


def rgb(r, g, b):
    """Turn normal 0-255 red/green/blue into the screen's color format.

    The screen uses 16-bit color (RGB565): 5 bits red, 6 green, 5 blue.
    It also wants the two bytes in the opposite order, so we swap them.
    """
    r, g, b = int(r), int(g), int(b)
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


# ---- Colors (change these to restyle Buddy!) ----
GLINT = rgb(214, 255, 226)      # the tiny shine on each eye
# How much each eye leans: positive = the tops lean toward each other ( / \\ ), kind and a little curious;
# negative = the tops lean apart ( \\ / ), cross. (Taken from how lilguy's eyes never stand perfectly upright.)
TILT = {"normal": -0.09, "happy": -0.06, "joyful": -0.03, "excited": -0.05, "love": -0.06, "shy": -0.08, "surprised": 0.0,
        "sad": 0.10, "angry": -0.16, "grumpy": -0.12, "dizzy": -0.04, "sleepy": -0.07, "thinking": -0.08}
# The pupil shape for each mood: (width, height) as a multiple of the normal pupil.
# Big soft circles when excited or sad, a small dot when surprised, a tall slit when cross.
PSTYLE = {"normal": (1.1, 1.0), "happy": (1.0, 0.95), "joyful": (1.05, 1.0), "excited": (1.3, 1.2), "love": (1.0, 1.0),
          "shy": (1.0, 1.0), "surprised": (0.5, 0.55), "sad": (1.22, 1.2), "angry": (0.4, 1.1), "grumpy": (0.55, 1.05),
          "dizzy": (0.85, 0.85), "sleepy": (1.0, 0.9), "thinking": (0.7, 0.8)}
BELL = ("...XX...", "..XXXX..", "..XXXX..", ".XXXXXX.", ".XXXXXX.", "XXXXXXXX", "........", "...XX...")
HEART_PIXELS = (".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X...")   # the pixel heart
FILL_S = 0.0                  # charging animation: seconds the energy takes to fill up
HOLD_S = 4.0                  # ...and how long it stays showing the level
SPARK = rgb(190, 255, 215)    # light energy sparks inside the charging eyes
BG = rgb(0, 0, 0)             # pure black, so the eyes seem to float
HEART = rgb(255, 70, 140)     # pupils turn into these when Buddy is in love

GREEN = (24, 255, 110)        # Buddy's eye color: always this green, in every mood
LIME = GREEN
SUNNY = GREEN
ROSE = GREEN
BLUE = GREEN
RED = GREEN
SPIN_COLORS = (GREEN, GREEN, GREEN, GREEN)  # flash through these while deciding
MOON = GREEN

# ---- Sizes and positions, in SCREEN pixels (the center is 140, 120 on the sideways 280 x 240 screen) ----
# We only redraw a band of the screen (see main.py), so when drawing we
# subtract self.top to turn a screen row into a row inside that band.
CX = 140                      # the screen is now 280 wide (turned sideways)
EYE_Y = 116                   # eyes sit in the middle
EYE_GAP = 57                  # distance from center to each eye (wider: the screen is wider)
EYE_RX, EYE_RY = 48, 58       # eye half-width / half-height: a little wider than tall (horizontal ovals)
PUPIL_RX, PUPIL_RY = 22, 29   # pupil half-width / half-height
RIGHT_EYE = 0.93              # the right eye is a touch smaller, for character

# ---- What each mood does to the face ----
# size:  how big the eyes are       open:  1 = open, 0 = closed
# lid:   upper eyelid coming down   cheek: lower lid pushing up (a smile)
# pupil: pupil size                 slant: + angry brows, - sad brows
# down:  how far Buddy looks down   color: eye color
#              size  open lid   cheek pupil slant down color
MOODS = {
    "normal":    (1.00, 1.0, 0.00, 0.00, 1.00, 0.0, 0.0, LIME),
    "happy":     (1.05, 1.0, 0.00, 0.50, 1.00, 0.0, -2.0, LIME),
    "joyful":    (1.10, 1.0, 0.00, 0.74, 0.90, 0.0, -4.0, SUNNY),
    "excited":   (1.13, 1.0, 0.00, 0.10, 1.25, 0.0, -2.0, SUNNY),
    "love":      (1.06, 1.0, 0.00, 0.00, 1.00, 0.0, 0.0, LIME),
    "shy":       (0.94, 1.0, 0.12, 0.30, 1.05, 0.0, 8.0, ROSE),
    "surprised": (1.15, 1.0, 0.00, 0.00, 0.55, 0.0, -2.0, LIME),
    "sad":       (1.08, 1.0, 0.34, 0.00, 1.26, -1.5, 11.0, BLUE),
    "angry":     (0.98, 1.0, 0.36, 0.00, 0.68, 1.35, 1.0, RED),
    "grumpy":    (0.98, 1.0, 0.34, 0.00, 0.85, 0.6, 2.0, LIME),
    "dizzy":     (1.02, 1.0, 0.00, 0.00, 0.80, 0.0, 0.0, LIME),
    "yes":       (1.10, 1.0, 0.00, 0.00, 1.00, 0.0, 0.0, LIME),
    "no":        (1.02, 1.0, 0.10, 0.00, 1.00, 0.6, 0.0, RED),
    "spin":      (1.05, 1.0, 0.00, 0.00, 0.80, 0.0, 0.0, LIME),
    "tension":   (1.00, 1.0, 0.16, 0.00, 0.90, 0.0, 0.0, LIME),
    "sleepy":    (0.98, 1.0, 0.56, 0.00, 1.00, 0.0, 6.0, LIME),
    "asleep":    (0.97, 0.0, 0.00, 0.00, 1.00, 0.0, 5.0, MOON),
    "thinking":  (0.98, 1.0, 0.20, 0.00, 0.85, 0.0, -6.0, LIME),
}

# How each mood moves: speed (1 = normal) and bounciness (lower = more wobble).
# Anything not listed uses NORMAL_PACE.
NORMAL_PACE = (1.0, 0.72)       # a calm, natural speed with only a little bounce
PACE = {
    "sleepy": (0.5, 0.9),        # slow and heavy
    "asleep": (0.4, 1.0),
    "sad": (0.6, 0.85),          # droopy, no bounce
    "shy": (0.8, 0.7),
    "grumpy": (0.8, 0.8),
    "angry": (1.1, 0.8),         # sharp and stiff
    "joyful": (1.05, 0.6),       # springy
    "excited": (1.15, 0.58),     # lively but not frantic
}

# When a timed mood ends, some flow into another instead of back to normal.
AFTER = {
    "dizzy": ("grumpy", 1500),   # poked until dizzy, then sulks
    "angry": ("grumpy", 1400),   # calms down slowly
    "love": ("shy", 2200),       # gets bashful after all that love
}

# These moods snap straight in, with no blink first.
NO_BLINK = ("surprised", "love", "asleep", "spin", "tension", "yes", "no")

# The answer replaces the pupils. Each is two lines: x0, y0, x1, y1 twice,
# in pixels from the middle of the pupil.
TICK = (-20, 2, -7, 16, -7, 16, 21, -17)
CROSS = (-16, -16, 16, 16, -16, 16, 16, -16)
MARK_WIDTH = 6.5

# The decision goes through these steps.
IDLE, SPINNING, HOLDING, SHOWING, ENDING = 0, 1, 2, 3, 4

# Things Buddy might do, and how likely each one is.
ACTIONS = (
    ("glance", 26), ("stare", 14), ("smile", 12), ("tilt", 30), ("dart", 9),
    ("sway", 8), ("peek", 8), ("around", 7), ("perk", 7), ("hop", 5),
    ("wink", 4), ("squint", 3), ("think", 6),
    ("scan", 7), ("double", 6), ("lookup", 6), ("flutter", 5), ("hoplook", 4),
)


# Lively actions are chosen more when Buddy has energy, quiet ones when it is calm.
LIVELY = ("dart", "around", "perk", "hop", "sway", "wink", "double", "flutter", "hoplook")
QUIET = ("stare", "squint", "smile", "tilt", "peek", "think", "scan", "lookup")


def spring(x, v, target, stiff, damp, dt):
    """One step of a spring: returns the new position and speed.

    stiff = how fast it moves. damp below 1 overshoots, 1 just stops.
    Dividing by the damping, instead of subtracting it, keeps the spring
    steady even on a slow frame. Subtracting can make it blow up.
    """
    v = (v + stiff * stiff * (target - x) * dt) / (1 + 2 * damp * stiff * dt)
    return x + v * dt, v


def blend(x, target, rate, dt):
    """Glide x toward target. A bigger rate gets there sooner."""
    return x + (target - x) * min(1.0, rate * dt)


def wait_ms(mean, low, high):
    """A random wait with no rhythm: mostly short, sometimes very long."""
    w = -mean * math.log(1.0 - random.random() * 0.999)
    return int(max(low, min(high, w)))


class Decision:
    """Everything the yes or no needs while it's happening."""

    def __init__(self):
        now = ticks_ms()
        self.end = now               # when this step finishes
        self.spin_start = now
        self.spin_ms = 1
        self.angle = 0.0
        self.tick = 0
        self.answer = False
        self.mark_v = 0.0
        self.lines = array.array("i", [0] * 8)  # the tick or cross, ready to draw


class Face:
    def __init__(self, fb):
        self.fb = fb                 # the framebuffer we draw on (the lcd)
        self.pen = Pen(fb)           # draws smooth shapes on it
        self.top = fb.top            # which screen row our band starts at
        fb.clear_all(BG)             # paint the whole screen once
        now = ticks_ms()
        self.mood = "normal"
        self.mood_until = 0          # when the mood ends (0 = never)
        self.last_time = now
        self.t = 0.0                 # seconds since start, for slow drifting

        # Where Buddy wants to look, and where the eyes and pupils are now.
        self.target_x = 0.0
        self.target_y = 0.0
        self.eye_x = self.eye_y = self.eye_vx = self.eye_vy = 0.0
        self.pup_x = self.pup_y = self.pup_vx = self.pup_vy = 0.0
        self.pup2_x = self.pup2_y = self.pup2_vx = self.pup2_vy = 0.0   # the right pupil follows the left with its own delay (lilguy: every eye has its own lag)
        # The right eye follows the left a moment later, so they don't move
        # like one stiff object.
        self.eye2_x = self.eye2_y = self.eye2_vx = self.eye2_vy = 0.0
        self.pace, self.damp = NORMAL_PACE

        # Springy extras.
        self.size = 1.0
        self.size_v = 0.0
        self.hop = 0.0               # bounce up and down
        self.hop_v = 0.0
        self.hop2 = 0.0              # the right eye's bounce, a moment behind
        self.hop2_v = 0.0
        self.tilt = 0.0              # one eye higher than the other
        self.tilt_v = 0.0
        self.tilt_target = 0.0

        # Mood numbers, which glide toward the values in MOODS.
        self.open = 0.0              # starts closed: Buddy wakes up on boot
        self.tilt_k = -0.09           # how much the eyes lean (see TILT)
        self.asym = 0.0              # the two eyes are never exactly alike
        self.pup_w = 1.1             # pupil shape (see PSTYLE)
        self.pup_h = 1.0
        self.open2 = 0.0             # the right eye opens a moment after the left, like waking up
        self.kick = 1.0              # each look has its own speed: some lazy, some snappy (decays back to 1)
        self.lag_k = 30.0            # how quickly the right eye follows the left (random on every look)
        self.pj_x = self.pj_y = self.pj_tx = self.pj_ty = 0.0   # the pupils dart about on their own, a little
        self.next_pj = ticks_ms() + 600
        self.pup_pulse = 0.0         # the pupils swell for a moment when poked
        self.blink_max = 1.0         # 1 = a full blink, less = a half blink
        self.next_tiny = ticks_ms() + 4000   # a second, separate timer for tiny reactions
        self.finger_x = -999         # where a finger is touching (set by buddy.py); the eye under it swells
        self.swell_l = self.swell_r = 1.0
        self.lid = 0.0
        self.cheek = 0.0
        self.pupil = 1.0
        self.smile = 0.0             # short-lived, added on top of cheek
        self.smile_target = 0.0
        self.slant = 0.0
        self.down = 0.0
        self.red, self.green, self.blue = LIME
        self.shake = 0.0             # angry trembling
        self.focus_now = 0.0         # builds up while you hold your finger down
        self.focus_goal = 0.0
        self.heart_size = 0.0        # 0 = normal pupil, 1 = heart
        self.heart_v = 0.0
        self.sparks = []             # little hearts flying out: [x, y, vx, vy, life]
        self.next_beat = now         # bounces while joyful or excited
        self.shy_side = 1            # which way Buddy looks away
        self.sleep = 0.0             # 0 = awake, 1 = fast asleep
        self.lungs = 0.0             # 0 = breathed out, 1 = breathed in
        self.sigh = 0.0              # a deeper breath, every now and then
        self.dream = 0.0             # 1 = smiling in its sleep
        self.dream_target = 0.0
        self.next_dream = now
        self.bubbles = []            # dream bubbles: [x, y, life, wobble]
        self.next_bubble = now
        self.squint = 0.0            # short-lived, added on top of lid
        self.squint_target = 0.0
        self.perk = 0.0              # short-lived size boost
        self.perk_target = 0.0

        # Blinking. side: 0 = both eyes, -1 or 1 = a wink with one eye.
        self.blink_at = ticks_add(now, 1500)
        self.blink_start = None
        self.blink_len = 170
        self.blink_side = 0
        self.blink_again = False

        # Behaviours.
        self.next_action = ticks_add(now, 900)
        self.last_action = ""
        self.todo = []               # steps waiting to happen: (time, step, a, b)
        self.hold_until = now        # don't wander while being touched
        self.water_on = False        # the charging animation: the eyes fill up like glasses of water
        self.water = 0.0
        self.water_t = 0.0
        self.water_goal = 1.0
        self.burst_t = -99.0         # when the 'fully charged' flash started
        self.burst_done = False
        self.skip = False            # True: nothing changed this frame, so nothing is drawn or sent
        self.bell_n = 0              # notifications waiting: a small pixel bell in the corner
        self.charge_sign = 0         # small corner sign while plugged in: 0 none, 1 bolt (charging), 2 tick (charged)

        # Energy: 0 = drowsy and calm, 1 = bouncy. It slowly wanders by itself, jumps up when
        # you touch or move Buddy, and settles back to energy_base. It sets how often Buddy does things.
        self.energy = 0.45
        self.energy_base = 0.45
        self.energy_goal = 0.45
        self.next_mood_shift = ticks_add(now, 15000)
        self.recent = []             # the last few things Buddy did, so it won't repeat itself
        self.next_micro = now        # tiny eye jumps while looking at something
        self.micro_x = self.micro_y = 0.0
        self.micro_tx = self.micro_ty = 0.0

        # The yes or no decision. Its details live in their own small object,
        # because the more values Face holds, the slower every frame gets.
        self.phase = IDLE            # main.py checks this to ignore touches
        self.mark = 0.0              # 0 = normal pupil, 1 = tick or cross
        self.d = Decision()

        # Which rows were drawn last frame. Only these need wiping and sending.
        self.row0 = 0
        self.row1 = fb.height

        # Say hello when turned on: look around, spot you, smile.
        self.mood = "sleepy"          # starts drowsy, then wakes up
        self.plan(650, "wakeup")
        self.plan(1300, "look", -14.0, 0.0)
        self.plan(1950, "look", 12.0, 0.0)
        self.plan(2600, "look", 0.0, 0.0)
        self.plan(2900, "hop")
        self.plan(2950, "mood", 0)
        self.next_action = ticks_add(now, 5200)

    # ------------------------------------------------------------------
    # Things main.py can ask the face to do
    # ------------------------------------------------------------------

    def set_mood(self, mood, duration_ms=0):
        """Change mood. With a duration, it goes back to normal after."""
        if mood == self.mood and not duration_ms:
            return                   # main.py asks for this on every frame
        # A quick blink hides the change, like a real animal.
        if mood != self.mood and self.mood != "asleep" and mood not in NO_BLINK:
            self.blink(random.randint(110, 150))
        self.mood = mood
        self.mood_until = ticks_add(ticks_ms(), duration_ms) if duration_ms else 0
        self.tilt_target = 0.0
        self.shy_side = random.choice((-1, 1))
        self.asym = random.uniform(-1.0, 1.0)

    def look_at(self, x, y):
        """Look toward a point on the screen (like your finger)."""
        self.target_x = max(-20.0, min(20.0, (x - CX) / 4))
        self.target_y = max(-14.0, min(14.0, (y - 120) / 5))
        self.hold_until = ticks_add(ticks_ms(), 1200 + random.randint(0, 900))
        self.lag_k = random.uniform(18.0, 44.0)

    def poke(self):
        """A finger just landed: a little bounce."""
        self.hop_v -= 150.0
        self.pup_pulse = 0.3         # the pupils swell for a moment

    def jump(self, power):
        """A proper jump: a quick dip down first, then up."""
        self.hop_v += power * 0.3
        self.plan(70, "leap", power)

    def wake(self):
        """Touched while sad or sleeping: a little jump, then so pleased!"""
        self.set_mood("surprised", 450)
        self.plan(480, "mood", 1)

    def focus(self, amount):
        """Finger held down: 0 = relaxed, 1 = about to burst."""
        self.focus_goal = amount

    def boom(self):
        """The hold paid off: eyes pop, hearts fly everywhere."""
        self.focus_goal = 0.0
        self.focus_now = 0.0
        self.set_mood("love", 3000)
        self.size_v += 7.0
        self.hop_v -= 230.0
        self.burst()

    def decide(self):
        """Ask Buddy a yes or no question: spin, suspense, boom."""
        if self.phase:
            return
        # Cancelling the plans also cancels the steps that would undo them,
        # so put anything short-lived back to rest here.
        self.todo = []
        self.smile_target = self.squint_target = self.perk_target = 0.0
        self.tilt_target = self.dream_target = 0.0
        self.phase = SPINNING
        self.set_mood("spin")
        d = self.d
        d.spin_start = ticks_ms()
        d.spin_ms = random.randint(2000, 2900)
        d.angle = random.random() * 6.283
        d.tick = 0
        # A truly random bit from the chip's hardware, so it's a fair coin.
        d.answer = os.urandom(1)[0] & 1 == 1

    def deciding(self, now, dt):
        """Moves the decision along, one step at a time."""
        d = self.d
        if self.phase == SPINNING:
            done = ticks_diff(now, d.spin_start) / d.spin_ms
            left = max(0.0, 1.0 - done)
            # Fast at first, then slowing down like a prize wheel.
            d.angle += (24 * left * left + 2.6) * dt
            tick = int(d.angle / 1.571)
            if tick != d.tick:       # the wheel clicks past a peg
                d.tick = tick
                self.red, self.green, self.blue = SPIN_COLORS[tick % 4]
                self.hop_v -= 45.0
            if done >= 1:
                self.phase = HOLDING
                d.end = ticks_add(now, random.randint(550, 950))
                self.set_mood("tension")
                self.focus_goal = 1.0
        elif self.phase == HOLDING:
            if ticks_diff(now, d.end) > 0:
                self.phase = SHOWING
                d.end = ticks_add(now, 2600)
                self.focus_goal = 0.0
                self.focus_now = 0.0
                self.set_mood("yes" if d.answer else "no")
                d.mark_v = 5.0
                self.size_v += 6.0 if d.answer else 2.0
                self.hop_v -= 210.0 if d.answer else 90.0
                if d.answer:
                    self.burst()
                self.plan(320, "react")
        elif self.phase == SHOWING:
            if ticks_diff(now, d.end) > 0:
                self.phase = ENDING
        elif self.phase == ENDING and self.mark < 0.15:
            self.phase = IDLE
            self.mark = d.mark_v = 0.0
            self.set_mood("happy" if d.answer else "normal", 1800)
        target = 1.0 if self.phase == SHOWING else 0.0
        self.mark, d.mark_v = spring(self.mark, d.mark_v, target, 16, 0.45, dt)

    def react(self):
        """Backs up the answer: a big nod, or a firm shake of the head."""
        if self.d.answer:
            for i, y in enumerate((11.0, -6.0, 11.0, 0.0)):
                self.plan(i * 210, "look", 0.0, y)
        else:
            for i, x in enumerate((-15.0, 15.0, -11.0, 11.0, 0.0)):
                self.plan(i * 190, "look", x, 0.0)

    def burst(self):
        for i in range(5):
            angle = i * 1.257 + random.random() * 0.5
            speed = 90 + random.random() * 90
            self.sparks.append([140.0, 80.0, math.cos(angle) * speed,
                                math.sin(angle) * speed - 40, 1.0])

    def show(self):
        """Send only the rows that changed since the last frame."""
        lo = min(self.row0, self.new0)
        hi = max(self.row1, self.new1)
        self.fb.show_rows(lo, hi)
        self.row0, self.row1 = self.new0, self.new1

    # ------------------------------------------------------------------
    # Behaviours: Buddy's own little ideas
    # ------------------------------------------------------------------

    def plan(self, delay_ms, step, a=0.0, b=0.0):
        self.todo.append((ticks_add(ticks_ms(), delay_ms), step, a, b))

    def charge_start(self, level=1.0):
        """The charger was plugged in: the eyes empty, then fill up with energy."""
        self.todo = []
        self.phase = IDLE
        self.set_mood("normal")
        self.water_on = True
        self.set_mood("happy", 3800)
        self.water = 0.0
        self.water_goal = max(0.08, min(1.0, level))   # fills up to where the battery really is
        self.water_t = self.t
        self.burst_done = False
        self.target_x = self.target_y = 0.0

    def excite(self, amount):
        """Touch or movement: Buddy gets livelier for a while."""
        self.energy = min(1.0, self.energy + amount)

    def pick_action(self):
        """Pick something to do. Not any of the last three, and lively ones more when there is energy."""
        e = self.energy
        weights = []
        total = 0.0
        for name, weight in ACTIONS:
            if name in self.recent:
                w = 0.0
            elif name in LIVELY:
                w = weight * (0.25 + e * 1.5)
            elif name in QUIET:
                w = weight * (1.5 - e)
            else:
                w = weight
            weights.append(w)
            total += w
        roll = random.random() * total
        for i in range(len(ACTIONS)):
            roll -= weights[i]
            if roll <= 0:
                name = ACTIONS[i][0]
                break
        else:
            name = "glance"
        self.recent.append(name)
        if len(self.recent) > 3:
            self.recent.pop(0)
        return name

    def random_spot(self):
        """A random place to look, more often to the sides than up and down."""
        angle = random.random() * 6.283
        reach = 8 + random.random() * 12
        return math.cos(angle) * reach, math.sin(angle) * reach * 0.6

    def begin(self, name):
        self.last_action = name
        if name == "glance":
            x, y = self.random_spot()
            self.plan(0, "look", x, y)
            if random.random() < 0.22:      # eyes often blink as they move
                self.blink(random.randint(120, 170))
            if random.random() < 0.5:       # look back at you, or stay there
                self.plan(random.randint(500, 1900), "look", 0.0, 0.0)
        elif name == "stare":
            self.plan(0, "look", 0.0, 0.0)
            self.plan(0, "tilt", 0.0)
        elif name == "dart":
            when = 0
            for _ in range(random.randint(2, 3)):
                x, y = self.random_spot()
                self.plan(when, "look", x, y)
                when += random.randint(160, 420)
            self.plan(when + random.randint(200, 600), "look", 0.0, 0.0)
        elif name == "tilt":
            side = random.choice((-1, 1))
            self.plan(0, "tilt", side * (6 + random.random() * 8))      # a head-roll: one eye lower than the other (lilguy does this a lot)
            self.plan(random.randint(1800, 5200), "tilt", 0.0)
        elif name == "around":
            side = random.choice((-1, 1))
            self.plan(0, "look", side * 18.0, random.randint(-4, 4))
            self.plan(random.randint(450, 900), "look", -side * 18.0, random.randint(-4, 4))
            self.plan(random.randint(1100, 1800), "look", 0.0, 0.0)
        elif name == "perk":
            self.plan(0, "perk", 0.07)
            self.plan(random.randint(350, 800), "perk", 0.0)
        elif name == "smile":
            self.plan(0, "look", 0.0, 0.0)
            self.plan(0, "smile", 0.34)
            self.plan(random.randint(900, 2200), "smile", 0.0)
        elif name == "sway":
            side = random.choice((-1, 1))
            self.plan(0, "tilt", side * 7.0)
            self.plan(380, "tilt", -side * 7.0)
            self.plan(760, "tilt", side * 5.0)
            self.plan(1140, "tilt", 0.0)
        elif name == "peek":
            self.plan(0, "look", random.randint(-6, 6), 12.0)     # shy look down
            self.plan(random.randint(600, 1200), "look", 0.0, 0.0)  # and back to you
            self.plan(random.randint(1300, 1500), "smile", 0.25)
            self.plan(random.randint(1900, 2400), "smile", 0.0)
        elif name == "squint":
            self.plan(0, "squint", 0.34)
            self.plan(random.randint(600, 1400), "squint", 0.0)
        elif name == "hop":
            self.jump(120.0)
            if random.random() < 0.5:
                self.plan(random.randint(190, 260), "hop")
        elif name == "wink":
            self.blink(300, random.choice((-1, 1)))
        elif name == "scan":
            side = random.choice((-1, 1))
            self.plan(0, "look", -side * 17.0, random.randint(-3, 3))
            self.plan(random.randint(1000, 1500), "look", 0.0, random.randint(-5, 2))
            self.plan(random.randint(2200, 2800), "look", side * 17.0, random.randint(-3, 3))
            self.plan(random.randint(3600, 4400), "look", 0.0, 0.0)
        elif name == "double":
            x, y = self.random_spot()
            self.plan(0, "look", x, y)
            self.plan(random.randint(300, 420), "look", 0.0, 0.0)
            self.plan(random.randint(700, 900), "look", x * 0.9, y)
            self.plan(random.randint(1500, 2200), "look", 0.0, 0.0)
        elif name == "lookup":
            self.plan(0, "look", random.randint(-6, 6), -11.0)
            self.plan(0, "perk", 0.05)
            self.plan(random.randint(1000, 1500), "perk", 0.0)
            self.plan(random.randint(1400, 2000), "look", 0.0, 0.0)
        elif name == "flutter":
            self.plan(0, "blink", 700, 0)
            self.plan(880, "blink", 700, 0)
        elif name == "hoplook":
            self.jump(100.0)
            x, y = self.random_spot()
            self.plan(120, "look", x, y)
            self.plan(random.randint(900, 1500), "look", 0.0, 0.0)
        elif name == "think":
            self.plan(0, "look", random.choice((-1, 1)) * random.randint(6, 14), -12.0)
            self.set_mood("thinking", random.randint(1800, 3200))

    def run_step(self, step, a, b):
        if step == "look":
            # A big look starts with a tiny move the other way, like winding up.
            move = a - self.target_x
            if abs(move) > 9:
                self.eye_vx -= move * 6
            self.target_x, self.target_y = a, b
            self.kick = random.uniform(0.85, 1.7)
            self.lag_k = random.uniform(16.0, 44.0)     # each look, the two eyes follow with a different delay
        elif step == "blink":
            self.blink(int(a), int(b))
        elif step == "wakeup":
            self.set_mood("normal")
            self.blink(260)
        elif step == "tilt":
            self.tilt_target = a
        elif step == "perk":
            self.perk_target = a
        elif step == "squint":
            self.squint_target = a
        elif step == "smile":
            self.smile_target = a
        elif step == "dream":
            self.dream_target = a
        elif step == "mood":
            if not self.phase:
                self.set_mood("excited" if a else "happy", 1700 if a else 1500)
        elif step == "hop":
            self.jump(90.0)
        elif step == "react":
            self.react()
        elif step == "leap":
            self.hop_v -= a * 1.2

    def blink(self, length=800, side=0):
        length = max(length, 520 if side else 680)       # never a quick flick: a natural blink takes a moment
        if self.blink_start is None:
            self.blink_start = ticks_ms()
            self.blink_len = length
            self.blink_side = side

    def blink_amount(self, now, side):
        """How far the upper eyelid has come down during a blink (0 = open, 1 = shut).
        Frame by frame from lilguy's eyes: the eye does not shrink. A lid sweeps down from the top over it,
        leaving a thin smile-shaped sliver, holds for a moment, and lifts again. It shuts fast (about 100 ms),
        holds (70 to 450 ms), and opens more slowly (about 350 ms), easing out at the end."""
        if self.blink_start is None or (self.blink_side and self.blink_side != side):
            return 0.0
        L = self.blink_len
        t = ticks_diff(now, self.blink_start) - (12 if side > 0 else 0)     # the right eye is a hair behind
        if t <= 0 or t >= L:
            return 0.0
        mx = self.blink_max
        close = min(230.0, L * 0.3)
        opening = min(480.0, L * 0.58)
        hold = L - close - opening
        if hold < 0:
            hold = 0.0
        if t < close:
            p = t / close
            return mx * p * p * (3 - 2 * p)                  # the lid starts gently and snaps down
        if t < close + hold:
            return mx
        p = (t - close - hold) / opening
        if p > 1.0:
            return 0.0
        return mx * (1.0 - p * p * (3 - 2 * p))              # it lifts gently, speeds up a little, then eases to a stop

    # ------------------------------------------------------------------
    # update() = change the numbers. draw() = paint them. Kept separate
    # so the logic stays easy to read.
    # ------------------------------------------------------------------

    def update(self):
        now = ticks_ms()
        # Springs use real time, so the speed stays the same at any frame rate.
        raw = min(0.04, ticks_diff(now, self.last_time) / 1000)
        # Frame times wobble by a millisecond or two; averaging them keeps the motion from jittering.
        self.dt_avg = getattr(self, 'dt_avg', raw) * 0.85 + raw * 0.15
        dt = self.dt_avg
        self.last_time = now
        self.t += dt

        # A timed mood ran out? Back to normal.
        if self.mood_until and ticks_diff(now, self.mood_until) > 0:
            if self.mood in AFTER:
                self.set_mood(AFTER[self.mood][0], AFTER[self.mood][1])
            else:
                self.set_mood("normal")

        mood = self.mood
        awake = mood not in ("sleepy", "asleep") and not self.phase

        # Energy settles back toward its base; the base itself drifts every so often (a slow "mood of the hour").
        self.energy = blend(self.energy, self.energy_goal, 0.12, dt)
        if ticks_diff(now, self.next_mood_shift) > 0:
            self.energy_goal = max(0.1, min(0.95, self.energy_base + random.uniform(-0.3, 0.3)))
            self.next_mood_shift = ticks_add(now, random.randint(25000, 70000))

        # Run any planned steps whose time has come.
        i = 0
        while i < len(self.todo):
            when, step, a, b = self.todo[i]
            if ticks_diff(now, when) >= 0:
                self.todo.pop(i)
                self.run_step(step, a, b)
            else:
                i += 1

        # Time for a new idea?
        if (self.mood == "normal" and not self.todo
                and ticks_diff(now, self.next_action) > 0
                and ticks_diff(now, self.hold_until) > 0):
            self.begin(self.pick_action())
            # Low energy: long quiet stretches. High energy: more often. Now and then a long calm spell.
            mean = 9500 - 7000 * self.energy
            if random.random() < 0.18:
                mean *= 2.5
            self.next_action = ticks_add(now, wait_ms(mean, 1800, 26000))

        # Blinking at random. Sometimes a double, sometimes slow and dreamy.
        if self.blink_start is not None:
            if ticks_diff(now, self.blink_start) > self.blink_len + 20:
                self.blink_start = None
                self.blink_side = 0
                self.blink_max = 1.0
                if self.blink_again:
                    self.blink_again = False
                    self.blink_at = ticks_add(now, random.randint(180, 300))
        elif awake and ticks_diff(now, self.blink_at) > 0:
            roll = random.random()
            self.blink(random.randint(1250, 1450) if roll < 0.12 else random.randint(860, 980))
            self.blink_again = roll > 0.82
            self.blink_at = ticks_add(now, random.randint(3000, 5400) - int(600 * self.energy))     # about every 4 s, like lilguy
        elif self.mood == "sleepy" and ticks_diff(now, self.blink_at) > 0:
            self.blink(random.randint(900, 1200))
            self.blink_at = ticks_add(now, random.randint(1800, 4200))

        # A slow, wandering drift, so the eyes are never perfectly still.
        # These speeds don't line up, so the path doesn't repeat.
        t = self.t
        drift_x = 1.5 * math.sin(t * 0.73) + 0.9 * math.sin(t * 1.91 + 1.3)
        drift_y = 1.1 * math.sin(t * 0.57 + 2.1) + 0.7 * math.sin(t * 1.37)
        if self.mood in ("sleepy", "asleep"):
            self.target_x = blend(self.target_x, 0.0, 2.0, dt)
            self.target_y = blend(self.target_y, 5.0, 2.0, dt)
        # Eyes that are "looking" at something make tiny quick jumps, not a smooth wobble.
        if ticks_diff(now, self.next_micro) > 0:
            self.micro_tx = random.uniform(-1.8, 1.8)
            self.micro_ty = random.uniform(-1.2, 1.2)
            self.next_micro = ticks_add(now, random.randint(350, 1900))
        self.micro_x = blend(self.micro_x, self.micro_tx, 14.0, dt)
        self.micro_y = blend(self.micro_y, self.micro_ty, 14.0, dt)
        goal_x = self.target_x + drift_x * 0.6 + self.micro_x
        goal_y = self.target_y + drift_y * 0.6 + self.micro_y
        if self.mood == "dizzy":     # pupils go round and round, the head wobbles
            goal_x = 16 * math.cos(t * 9)
            goal_y = 12 * math.sin(t * 9)
            self.tilt_target = 7 * math.sin(t * 5)
        elif self.mood == "grumpy":  # looks away from you
            goal_x = 15.0
        elif mood == "angry":        # stares right at you
            goal_x = goal_y = 0.0
        elif mood == "sad":          # slowly looks around for you
            goal_x = 7 * math.sin(t * 0.6)
        elif mood == "shy":          # looks away, then sneaks a peek
            goal_x = self.shy_side * (3 if math.sin(t * 1.3) > 0.55 else 14)
        elif mood == "excited":      # can't keep still
            goal_x += 3 * math.sin(t * 13)
        elif mood == "joyful":       # happy little dance
            self.tilt_target = 6 * math.sin(t * 7)
        elif mood == "spin":         # the whole eye rolls a little too
            goal_x = 7 * math.cos(self.d.angle)
            goal_y = 5 * math.sin(self.d.angle)

        # Joyful and excited Buddy bounces, at a slightly uneven beat.
        if mood in ("joyful", "excited") and ticks_diff(now, self.next_beat) > 0:
            self.jump(130.0 if mood == "excited" else 95.0)
            self.next_beat = ticks_add(now, random.randint(230, 340) if mood == "excited"
                                       else random.randint(380, 520))

        # lilguy caps how far the eyes look (never past about 70% of the range) and eases into the end of it:
        # past a soft knee the extra distance counts for much less, so big looks glide instead of slamming.
        if mood == "normal" or mood == "happy":
            ax = abs(goal_x)
            if ax > 15.0:
                e = ax - 15.0
                goal_x = (goal_x / ax) * (15.0 + e * 0.5 / (1.0 + e / 9.0))
            ay = abs(goal_y)
            if ay > 9.0:
                e = ay - 9.0
                goal_y = (goal_y / ay) * (9.0 + e * 0.5 / (1.0 + e / 7.0))

        # While focusing, Buddy locks onto you and stops looking around.
        self.focus_now = blend(self.focus_now, self.focus_goal, 14.0, dt)
        goal_x *= 1 - self.focus_now
        goal_y *= 1 - self.focus_now

        # Blend every mood number toward the current mood.
        size, open_, lid, cheek, pupil, slant, down, color = MOODS[mood]
        cheek += self.smile
        goal_y += down
        self.open = blend(self.open, open_, 5.0, dt)
        self.open2 = blend(self.open2, open_, 3.4, dt)      # the right eye opens a little later
        self.tilt_k = blend(self.tilt_k, TILT.get(mood, 0.1), 5.0, dt)
        ps = PSTYLE.get(mood, (1.0, 1.0))
        self.pup_w = blend(self.pup_w, ps[0], 6.0, dt)
        self.pup_h = blend(self.pup_h, ps[1], 6.0, dt)
        self.lid = blend(self.lid, lid, 5.0, dt)
        self.cheek = blend(self.cheek, cheek, 11.0, dt)
        self.pupil = blend(self.pupil, pupil, 12.0, dt)
        self.slant = blend(self.slant, slant, 8.0, dt)
        self.red = blend(self.red, color[0], 6.0, dt)
        self.green = blend(self.green, color[1], 6.0, dt)
        self.blue = blend(self.blue, color[2], 6.0, dt)
        self.shake = blend(self.shake, 1.6 if mood == "angry" else 0.0, 12.0, dt)
        self.smile = blend(self.smile, self.smile_target, 8.0, dt)
        self.squint = blend(self.squint, self.squint_target, 9.0, dt)
        self.perk = blend(self.perk, self.perk_target, 10.0, dt)
        self.dreaming(now, dt)
        if self.phase:
            self.deciding(now, dt)

        if self.water_on:
            e = self.t - self.water_t
            if e < FILL_S:
                x = e / FILL_S
                self.water = self.water_goal * x * x * (3 - 2 * x)    # fills slowly, easing in and out
            elif e > FILL_S + HOLD_S:
                self.water_on = False
                self.set_mood("happy", 2400)
                self.jump(150.0)
            else:
                self.water = self.water_goal
                if self.water_goal >= 0.97 and not self.burst_done:
                    self.burst_done = True              # fully charged: a pop and a ring of light
                    self.burst_t = self.t
                    self.size_v += 8.0
                    self.hop_v -= 140.0

        # The eye under a finger swells a little, like it is leaning into the touch.
        fx = self.finger_x
        self.swell_l = blend(self.swell_l, 1.06 if (fx > -900 and fx < CX) else 1.0, 10.0, dt)
        self.swell_r = blend(self.swell_r, 1.06 if (fx >= CX) else 1.0, 10.0, dt)

        # A second timer, independent of the bigger actions: tiny reactions (a twitch, a squint, a little perk).
        if mood == "normal" and not self.phase and ticks_diff(now, self.next_tiny) > 0:
            self.next_tiny = ticks_add(now, random.randint(3000, 6500))
            pick = random.random()
            if pick < 0.4:
                self.eye_vx += random.choice((-1, 1)) * random.randint(40, 90)
            elif pick < 0.55:
                self.blink_max = 0.55              # a half blink (lilguy does these too)
                self.blink(random.randint(700, 820))
            elif pick < 0.75:
                self.plan(0, "squint", 0.12)
                self.plan(random.randint(250, 450), "squint", 0.0)
            else:
                self.plan(0, "perk", 0.03)
                self.plan(random.randint(220, 380), "perk", 0.0)

        # Each mood has its own speed and bounce, and they blend smoothly too.
        pace, damp = PACE.get(mood, NORMAL_PACE)
        self.pace = blend(self.pace, pace, 4.0, dt)
        self.damp = blend(self.damp, damp, 4.0, dt)
        self.kick = blend(self.kick, 1.0, 1.6, dt)
        quick = 26 * self.pace * self.kick
        loose = 18 * self.pace * self.kick
        damp = self.damp

        # The eye is quick. The pupil is a bit slower and looser.
        self.eye_x, self.eye_vx = spring(self.eye_x, self.eye_vx, goal_x * 0.8, quick, damp, dt)
        self.eye_y, self.eye_vy = spring(self.eye_y, self.eye_vy, goal_y * 0.8, quick, damp, dt)
        # The pupils move a lot more than the eyes: they lead the gaze, dart about by themselves,
        # and chase a finger hard (this is what makes lilguy's eyes feel so alive).
        if ticks_diff(now, self.next_pj) > 0:
            self.pj_tx = random.uniform(-7.0, 7.0)
            self.pj_ty = random.uniform(-5.0, 5.0)
            self.next_pj = ticks_add(now, random.randint(450, 1900))
        self.pj_x = blend(self.pj_x, self.pj_tx, 9.0, dt)
        self.pj_y = blend(self.pj_y, self.pj_ty, 9.0, dt)
        touching = self.finger_x > -900
        gain = 2.1 if touching else 1.7
        pstiff = 34.0 if touching else loose * 1.3
        self.pup_x, self.pup_vx = spring(self.pup_x, self.pup_vx, goal_x * gain + self.pj_x, pstiff, damp - 0.1, dt)
        self.pup_y, self.pup_vy = spring(self.pup_y, self.pup_vy, goal_y * gain + self.pj_y, pstiff, damp - 0.1, dt)
        self.pup_pulse = blend(self.pup_pulse, 0.0, 4.0, dt)
        self.pup2_x, self.pup2_vx = spring(self.pup2_x, self.pup2_vx, self.pup_x, self.lag_k * 1.5, 0.7, dt)
        self.pup2_y, self.pup2_vy = spring(self.pup2_y, self.pup2_vy, self.pup_y, self.lag_k * 1.5, 0.7, dt)
        if mood == "spin":           # pupils race around the rim, like a bingo ball
            self.pup_x = 19 * math.cos(self.d.angle)
            self.pup_y = 24 * math.sin(self.d.angle)
            self.pup2_x, self.pup2_y = self.pup_x, self.pup_y
        self.eye2_x, self.eye2_vx = spring(self.eye2_x, self.eye2_vx, self.eye_x, self.lag_k, 0.75, dt)
        self.eye2_y, self.eye2_vy = spring(self.eye2_y, self.eye2_vy, self.eye_y, self.lag_k, 0.75, dt)

        self.heart_size, self.heart_v = spring(self.heart_size, self.heart_v,
                                               1.0 if mood == "love" else 0.0, 16, 0.45, dt)

        # Flying hearts: they drift out, fall a little and fade away.
        for s in self.sparks:
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            s[3] += 150 * dt
            s[4] -= dt * 1.6
        if self.sparks and self.sparks[0][4] <= 0:
            self.sparks = []

        self.size, self.size_v = spring(self.size, self.size_v,
                                        size + self.perk - 0.07 * self.focus_now, 20, 0.42, dt)
        self.hop, self.hop_v = spring(self.hop, self.hop_v, 0.0, 17, 0.38, dt)
        self.hop2, self.hop2_v = spring(self.hop2, self.hop2_v, self.hop, 42, 0.75, dt)
        self.tilt, self.tilt_v = spring(self.tilt, self.tilt_v, self.tilt_target, 11, 0.7, dt)

    def dreaming(self, now, dt):
        """Breathing, dreams and bubbles while Buddy is asleep."""
        asleep = self.mood == "asleep"
        if not asleep and self.sleep < 0.01:
            # Wide awake: nothing here can show, so skip it all. Every sum in
            # Python leaves a little rubbish behind, and cleaning that up is
            # what causes the tiny stutters.
            self.sleep = self.dream = self.dream_target = 0.0
            self.bubbles = []
            return
        self.sleep = blend(self.sleep, 1.0 if asleep else 0.0, 3.0, dt)

        # Breathing in is quicker than breathing out, like a real sleeper.
        wave = 0.5 + 0.5 * math.sin(self.t * 1.35)
        self.lungs = wave * wave * (3 - 2 * wave)
        self.sigh = blend(self.sigh, 0.0, 0.8, dt)
        self.dream = blend(self.dream, self.dream_target, 2.5, dt)

        if asleep and ticks_diff(now, self.next_dream) > 0:
            roll = random.random()
            if roll < 0.4:           # eyes twitch, chasing something in a dream
                self.target_x = random.choice((-1, 1)) * (7 + random.random() * 6)
            elif roll < 0.72:        # a happy dream
                self.dream_target = 1.0
                self.plan(random.randint(1800, 3400), "dream", 0.0)
            else:                    # a long, contented sigh
                self.sigh = 1.0
            self.next_dream = ticks_add(now, wait_ms(3200, 1400, 8000))
        elif not asleep:
            self.dream_target = 0.0
            self.bubbles = []        # dreams pop the moment Buddy wakes

        # Dream bubbles drift up and fade away.
        if asleep and self.sleep > 0.7 and ticks_diff(now, self.next_bubble) > 0:
            self.bubbles.append([204.0 + random.random() * 18, 46.0, 1.0, random.random() * 6])
            self.next_bubble = ticks_add(now, random.randint(1500, 3600))
        for b in self.bubbles:
            b[1] -= 13 * dt
            b[2] -= 0.27 * dt
        if self.bubbles and self.bubbles[0][2] <= 0:
            self.bubbles.pop(0)

    PAD = 0                       # extra rows around the eyes that a style may draw into (glow)

    def begin_frame(self):
        fb = self.fb
        fb.fill_rect(0, self.row0, fb.width, self.row1 - self.row0, BG)  # wipe last frame

    def after_eyes(self):
        pass                      # (the pixel style uses this to skip frames that did not change)

    def draw(self):
        fb = self.fb
        self.begin_frame()                                                # (wipes last frame)
        now = ticks_ms()
        t = self.t

        # Soft breathing, plus a squash when the eyes move fast.
        breath = 1.0 + 0.012 * math.sin(t * 1.7)
        speed = min(1.0, (abs(self.eye_vx) + abs(self.eye_vy)) / 170)
        wide = self.size * (1.0 + 0.07 * speed)
        tall = self.size * breath * (1.0 - 0.06 * speed)

        # Stretch tall while flying, squash flat on landing. Getting wider as
        # it gets shorter keeps the eye feeling like one soft thing.
        stretch = min(1.0, abs(self.hop_v) / 320) * 0.09 - max(0.0, self.hop) * 0.03
        stretch = max(-0.14, min(0.12, stretch))
        tall *= 1.0 + stretch
        wide *= 1.0 - stretch * 0.7

        breathing = self.lungs + self.sigh * 0.7
        bob = -3.5 * breathing * self.sleep    # rises with each breath
        base_y = EYE_Y - self.top + self.eye_y + self.hop + bob

        # Angry shaking, and the tremble that builds while focusing.
        focus = self.focus_now
        jitter = self.shake * math.sin(t * 47) + focus * focus * 1.5 * math.sin(t * 61)

        eye_color = rgb(self.red, self.green, self.blue)
        pupil_color = rgb(self.red * 0.30, self.green * 0.60, self.blue * 0.42)   # tone-on-tone: a darker shade of the eye's own green

        # Closed eyes glow a little brighter on each breath in.
        glow = 1.0 - self.sleep * (0.3 - 0.27 * min(1.0, breathing))
        self.closed_color = rgb(self.red * glow, self.green * glow, self.blue * glow)

        low, high = 999, -999        # the rows the eyes cover this frame
        lag_x = self.eye2_x - self.eye_x
        lag_y = self.eye2_y - self.eye_y + self.hop2 - self.hop

        # side = -1 for the left eye, +1 for the right eye
        for side in (-1, 1):
            ex = CX + side * EYE_GAP + self.eye_x + jitter
            ey = base_y + side * (self.tilt + 2.2 * math.sin(t * 0.55) + 1.0 * math.sin(t * 1.3 + 1.0))   # a slow, constant head sway
            scale = 1.0
            if side > 0:
                scale = RIGHT_EYE
                ex += lag_x
                ey += lag_y
            sw = self.swell_l if side < 0 else self.swell_r
            # Perspective, like a head turning: the eye on the side Buddy looks toward narrows, the other widens.
            # (measured on lilguy: looking sideways narrows the near eye by about a third; looking up or down
            # flattens both eyes, so they turn into wide ovals)
            gx = max(-1.0, min(1.0, self.eye_x / 15.0))
            gy = abs(max(-1.0, min(1.0, self.eye_y / 10.0)))
            rx = EYE_RX * wide * scale * sw * (1.0 - 0.30 * gx * side) * (1.0 + 0.10 * gy)
            ry = EYE_RY * tall * scale * sw * (1.0 - 0.26 * gy) * (1.0 - 0.05 * abs(gx))
            opened = self.open if side < 0 else self.open2
            self.eye(ex, ey, rx, ry, opened, side, eye_color, pupil_color, self.blink_amount(now, side))
            reach = max(ry * opened, 36 if self.sleep > 0.02 else 16) + 5 + self.PAD
            if self.water_on:
                reach += ry * 0.5 + 4         # room for the ring of light
            low = min(low, int(ey - reach))
            high = max(high, int(ey + reach) + (14 if self.heart_size > 0.1 else 0))

        self.new0 = max(0, low)
        self.new1 = min(fb.height, high)
        self.after_eyes()
        if self.skip:
            return

        if self.water_on:
            # a small lightning bolt between the eyes, pulsing, so it clearly says "charging"
            bx = CX
            by = base_y
            k = 1.0 + 0.12 * math.sin(self.t * 5.0)
            pts = ((6, -13), (-5, 2), (0, 2), (-5, 14), (7, -2), (1, -2))
            poly = array.array("h", [0] * 12)
            for i in range(6):
                poly[2 * i] = int(pts[i][0] * k)
                poly[2 * i + 1] = int(pts[i][1] * k)
            fb.poly(int(bx), int(by), poly, SPARK, True)
        elif self.charge_sign:
            # a small quiet sign in the corner while the charger is in: a bolt = charging, a tick = charged
            self.new0 = 0
            c = rgb(self.red * 0.8, self.green * 0.8, self.blue * 0.8)
            if self.charge_sign == 1:
                poly = array.array("h", [3, -7, -3, 1, 0, 1, -3, 8, 4, -1, 1, -1])
                fb.poly(268, 14, poly, c, True)
            else:
                for o in (0, 1):
                    fb.line(262, 14 + o, 267, 19 + o, c)
                    fb.line(267, 19 + o, 276, 8 + o, c)

        if self.bell_n:
            self.new0 = 0
            bc = rgb(self.red * 0.8, self.green * 0.8, self.blue * 0.8)
            for ry in range(len(BELL)):
                for rx in range(8):
                    if BELL[ry][rx] == "X":
                        fb.fill_rect(8 + rx * 2, 6 + ry * 2, 2, 2, bc)

        for b in self.bubbles:
            self.bubble(b)

        self.draw_sparks()

    def draw_sparks(self):
        """Flying hearts can be anywhere, so the rows to send may grow."""
        for s in self.sparks:
            if s[4] > 0:
                self.heart(s[0], s[1], 2 + 5 * s[4], HEART)
                self.new0 = max(0, min(self.new0, int(s[1]) - 10))
                self.new1 = min(self.fb.height, max(self.new1, int(s[1]) + 22))

    # ------------------------------------------------------------------
    # Shape helpers. The pen draws smooth ovals and points (see pen.py),
    # and everything on screen is built from those.
    # ------------------------------------------------------------------

    def eye(self, ex, ey, rx, ry, opened, side, eye_color, pupil_color, cover=0.0):
        pen = self.pen
        h = ry * opened
        if h < 6:
            # Closed: an oval with most of it covered, leaving a moon shape.
            # A quick blink stays thin. Sleep makes it plump, and it fills out
            # on each breath. A happy dream curves it into a deeper smile.
            sleep = self.sleep
            thick = 3 + sleep * (13 + 4 * self.lungs + 4 * self.sigh)
            deep = 18 + 9 * sleep + 7 * self.dream
            y = ey - 8 - 4 * sleep
            pen.ellipse(ex, y, rx * (0.86 + 0.08 * sleep), deep, self.closed_color)
            pen.ellipse(ex, y - thick, rx * (0.98 + 0.1 * sleep), deep, BG)
            return

        lean = side * self.tilt_k * (1.0 + 0.3 * side * self.asym)      # each eye leans a little, and not quite the same
        # lilguy's eyes are never still: the lean of each eye keeps drifting, the two out of step with each other.
        lean += 0.07 * math.sin(self.t * 0.8 + side * 1.9 + self.asym) + 0.05 * math.sin(self.t * 1.7 + side * 0.6)
        pen.ellipse(ex, ey, rx, h, eye_color, 0, None, lean)

        # Pupil, or a heart when Buddy is in love.
        size = self.pupil * (1 - 0.45 * self.focus_now) + self.pup_pulse
        pr = PUPIL_RX * size * rx / EYE_RX * self.pup_w
        ph = PUPIL_RY * size * h / EYE_RY * self.pup_h
        qx = self.pup2_x if side > 0 else self.pup_x
        qy = self.pup2_y if side > 0 else self.pup_y
        px = ex + max(-rx + pr + 4, min(rx - pr - 4, qx - self.eye_x * 0.3))
        py = ey + max(-h + ph + 4, min(h - ph - 4, qy - self.eye_y * 0.3))
        px += lean * (py - ey) - side * 2.5          # sits along the lean of the eye, a little toward the nose
        if self.mark > 0.15:
            self.answer_mark(px, py, self.mark * h / ry, pupil_color)
        elif self.heart_size > 0.15:
            beat = abs(math.sin(self.t * 4.2))
            self.heart(px, py - 7 * h / ry, (13 + 4 * beat * beat) * self.heart_size * h / ry, HEART)
        else:
            pen.ellipse(px, py, pr, ph, pupil_color, 0, None, lean * 0.8)

        # Eyelid comes down from the top. Sliding it sideways tilts it into
        # an angry or a sad brow.
        # The upper lid follows the gaze: it drops a little when looking down and lifts when looking up.
        lid = self.lid + self.squint + 0.14 * self.focus_now + 0.011 * self.pup_y
        if cover > 0.0:
            lid += (0.97 - lid) * cover if lid < 0.97 else 0.0      # a blink: the lid comes down to a hairline
        # Fast sideways looks narrow the eye a little, and the lid trails behind the movement, like a real eyelid.
        lid += 0.06 * min(1.0, abs(self.eye_vx) / 220)
        if lid < 0:
            lid = 0.0
        lag = max(-7.0, min(7.0, self.eye_vx * 0.03))
        if lid > 0.02:
            lid_ry = h + 20
            lid_y = ey - h + h * 2 * lid - lid_ry
            # Only the rows over the eye matter, so skip the rest.
            pen.ellipse(ex - side * self.slant * rx * 0.55 - lag, lid_y, rx * 1.7, lid_ry, BG,
                        max(0, int(ey - h) - 2), int(lid_y + lid_ry) + 2)

        # Smiling cheek pushes up from below, leaving a happy curve.
        # The smiling cheek pulls back when Buddy looks down, so the pupil never vanishes behind it.
        cheek = self.cheek * max(0.0, 1.0 - max(0.0, self.pup_y) / 14.0)
        if cheek > 0.02:
            cheek_y = ey + h + 6 + h - h * 2 * cheek
            pen.ellipse(ex, cheek_y, rx + 16, h + 6, BG,
                        max(0, int(cheek_y - h - 6) - 1), min(self.fb.height, int(ey + h) + 3))

    def answer_mark(self, x, y, size, color):
        """The pupil becomes the answer: a tick for yes, a cross for no."""
        d = self.d
        shape = TICK if d.answer else CROSS
        lines = d.lines
        for i in range(8):
            lines[i] = int(shape[i] * size * 16)
        self.pen.stroke(lines, x, y, MARK_WIDTH * size, color)

    def bubble(self, b):
        """A sleeping 'Z' in chunky pixel blocks. It grows as it floats up and fades away."""
        x, y, life, wobble = b
        if life <= 0:
            return
        fade = min(1.0, life * 2.5) * min(1.0, (1 - life) * 6) * 0.8
        s = 2 + int(2.6 * (1 - life))                  # the size of each block: 2 .. 4 px
        x += 5 * math.sin(self.t * 1.1 + wobble)
        color = rgb(self.red * fade, self.green * fade, self.blue * fade)
        fb = self.fb
        x = int(x)
        y = int(y)
        fb.fill_rect(x, y, 5 * s, s, color)                         # top bar
        fb.fill_rect(x + 3 * s, y + s, s, s, color)                 # the diagonal, in steps
        fb.fill_rect(x + 2 * s, y + 2 * s, s, s, color)
        fb.fill_rect(x + s, y + 3 * s, s, s, color)
        fb.fill_rect(x, y + 4 * s, 5 * s, s, color)                 # bottom bar
        self.new0 = max(0, min(self.new0, y - 2))

    def heart(self, cx, cy, r, color):
        """A pixel-art heart: 7 x 6 chunky square blocks, scaled to size r."""
        fb = self.fb
        c = 0.55 * r                       # the size of one block
        if c < 1.0:
            return
        x0 = cx - 3.5 * c
        y0 = cy - 0.9 * r
        for row in range(6):
            line = HEART_PIXELS[row]
            ya = int(y0 + row * c + 0.5)
            yb = int(y0 + (row + 1) * c + 0.5)
            col = 0
            while col < 7:
                if line[col] == "X":
                    start = col
                    while col < 7 and line[col] == "X":
                        col += 1
                    fb.fill_rect(int(x0 + start * c + 0.5), ya, int((col - start) * c + 0.5), yb - ya, color)
                else:
                    col += 1
