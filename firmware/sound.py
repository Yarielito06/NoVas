"""
sound.py - tiny chirps on the board's buzzer (GPIO42). One note at a time, played without stopping Buddy.
Keep SOUND_ON = False if you want Buddy silent. When nothing plays the pin goes back to LOW, as Waveshare asks.
"""
from machine import Pin, PWM
from time import ticks_ms, ticks_diff, ticks_add

SOUND_ON = False
VOLUME = 9000           # 0 .. 32768  (the buzzer is small, so a modest number is plenty)

TUNES = {
    "tap":       ((1760, 30),),
    "happy":     ((1318, 55), (1760, 90)),
    "joyful":    ((1568, 50), (1976, 50), (2349, 110)),
    "excited":   ((1760, 40), (2093, 40), (2637, 40), (3136, 100)),
    "shy":       ((988, 80), (784, 130)),
    "sad":       ((784, 160), (659, 160), (523, 280)),
    "sleepy":    ((523, 150), (440, 260)),
    "angry":     ((233, 130), (196, 220)),
    "dizzy":     ((880, 60), (740, 60), (880, 60), (740, 60), (880, 60), (740, 60)),
    "love":      ((1047, 70), (1319, 70), (1568, 70), (2093, 170)),
    "surprised": ((2093, 50), (0, 30), (2637, 100)),
    "wake":      ((659, 70), (784, 70), (1047, 130)),
    "yes":       ((1318, 70), (1760, 130)),
    "no":        ((392, 110), (294, 220)),
    "wink":      ((1568, 40), (2093, 70)),
    "hello":     ((523, 90), (659, 90), (784, 90), (1047, 180)),
    "low":       ((440, 120), (0, 80), (440, 120)),
}


class Sound:
    def __init__(self):
        self.pin = Pin(42, Pin.OUT, value=0)
        self.pwm = None
        self.queue = []
        self.until = 0

    def _silence(self):
        if self.pwm:
            self.pwm.deinit()
            self.pwm = None
        self.pin = Pin(42, Pin.OUT, value=0)

    def _next(self):
        if not self.queue:
            self._silence()
            self.until = 0
            return
        freq, ms = self.queue.pop(0)
        if freq:
            if self.pwm is None:
                self.pwm = PWM(Pin(42), freq=freq, duty_u16=VOLUME)
            else:
                self.pwm.freq(freq)
        else:
            self._silence()
        self.until = ticks_add(ticks_ms(), ms) or 1

    def play(self, name):
        if not SOUND_ON or name not in TUNES:
            return
        self.queue = list(TUNES[name])
        self._next()

    def update(self):
        """Call this every frame: it moves on to the next note when one is finished."""
        if self.until and ticks_diff(ticks_ms(), self.until) >= 0:
            self._next()
