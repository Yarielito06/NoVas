"""
ancstest.py - TEST ONLY: can Buddy receive iPhone notifications (Apple's ANCS service)?

How to use (iPhone):
  1. Run this on the board. The screen says "PAIR ME".
  2. On the iPhone open the free app "nRF Connect" (or LightBlue), find "NoVas" and tap Connect.
  3. The iPhone asks to PAIR: accept. The screen then says "paired".
  4. iPhone Settings > Bluetooth > NoVas (the little i) > turn on "Share System Notifications".
  5. Send yourself a notification: the app, title and message appear on Buddy's screen.
Pairing keys are saved in bonds.json, so later it reconnects by itself.
"""
import bluetooth, json, struct, framebuf
from time import ticks_ms, ticks_diff, sleep_ms
from lcd_s3 import LCD

ANCS = bluetooth.UUID("7905F431-B5CE-4E99-A40F-4B1E122D00D0")
NOTIF_SRC = bluetooth.UUID("9FBF120D-6301-42D9-8C58-25E699A21DBD")
CTRL_PT = bluetooth.UUID("69D1D8F3-45E1-49A8-9821-9BBDFDAAD9D9")
DATA_SRC = bluetooth.UUID("22EAC6E9-24D6-4BB5-BE44-B36ACE7C7BFB")
ANCS_LE = bytes((0xD0, 0x00, 0x2D, 0x12, 0x1E, 0x4B, 0x0F, 0xA4, 0x99, 0x4E, 0xCE, 0xB5, 0x31, 0xF4, 0x05, 0x79))

lcd = LCD(top=40, height=160)
GREEN = 0x07F0 if False else (((24 >> 3) << 11) | ((255 >> 2) << 5) | (110 >> 3))
GREY = (((90 >> 3) << 11) | ((150 >> 2) << 5) | (115 >> 3))
WHITE = 0xFFFF


def text(s, x, y, scale, color):
    if not s:
        return
    t =framebuf.FrameBuffer(bytearray(len(s) * 8), len(s) * 8, 8, framebuf.MONO_HLSB)
    t.text(s, 0, 0, 1)
    for py in range(8):
        for px in range(len(s) * 8):
            if t.pixel(px, py):
                lcd.fill_rect(x + px * scale, y + py * scale, scale, scale, color)


status = ["starting"]
last = ["", "", ""]          # app, title, message


def draw():
    lcd.fill(0)
    text("NOTIFY TEST", 8, 6, 2, GREY)
    text(status[0][:22], 8, 30, 2, GREEN)
    text(last[0][:22], 8, 62, 2, WHITE)
    text(last[1][:22], 8, 86, 2, GREEN)
    text(last[2][:22], 8, 110, 2, WHITE)
    text(last[2][22:44], 8, 130, 2, WHITE)
    lcd.show()


def say(s):
    status[0] = s
    print("STATUS:", s)
    draw()


# ---- pairing keys, kept in a file so a restart does not forget the iPhone
_secrets = {}
try:
    with open("bonds.json") as f:
        for k, v in json.load(f).items():
            t, key = k.split(":")
            _secrets[(int(t), bytes.fromhex(key))] = bytes.fromhex(v)
except Exception:
    pass


def save_secrets():
    with open("bonds.json", "w") as f:
        json.dump({"%d:%s" % (t, k.hex()): v.hex() for (t, k), v in _secrets.items()}, f)


ble = bluetooth.BLE()
conn = [None]
chars = {}                   # name -> value handle
steps = []                   # things still to do after pairing, one at a time
asm = [b"", 0]               # data source reassembly: bytes so far, uid
ASK = (0, 1, 3)              # app id, title, message


def advertise():
    name = b"NoVas"
    adv = bytes((2, 0x01, 0x06)) + bytes((17, 0x15)) + ANCS_LE
    resp = bytes((len(name) + 1, 0x09)) + name
    ble.gap_advertise(100000, adv, resp_data=resp, connectable=True)


def next_step():
    if not steps:
        return
    kind, a, b = steps.pop(0)
    if kind == "chars":
        ble.gattc_discover_characteristics(conn[0], a, b)
    elif kind == "sub":
        ble.gattc_write(conn[0], a + 1, b"\x01\x00", 1)       # turn on notifications (the 'switch' sits just after the value)


def parse_data(buf):
    """Data source answer: command(1) uid(4) then attributes: id(1) length(2) value. Returns dict or None if not complete."""
    if len(buf) < 5:
        return None
    i = 5
    out = {}
    while i + 3 <= len(buf):
        aid = buf[i]
        ln = buf[i + 1] | (buf[i + 2] << 8)
        if i + 3 + ln > len(buf):
            return None
        out[aid] = bytes(buf[i + 3:i + 3 + ln]).decode("utf-8", "ignore")
        i += 3 + ln
    return out if len(out) >= len(ASK) else None


def irq(event, data):
    if event == 1:                                     # connected
        conn[0] = data[0]
        steps.clear()
        say("connected")
        try:
            ble.gap_pair(conn[0])
        except Exception as e:
            print("pair err", e)
    elif event == 2:                                   # disconnected
        conn[0] = None
        say("PAIR ME")
        advertise()
    elif event == 28:                                  # encryption changed
        c, enc, auth, bonded, ks = data
        print("encryption", enc, auth, bonded)
        if enc:
            say("paired, looking")
            ble.gattc_discover_services(c, ANCS)
        else:
            say("pairing failed")
    elif event == 9:                                   # service found
        c, s, e, u = data
        if u == ANCS:
            steps.append(("chars", s, e))
    elif event == 10:                                  # service search done
        if steps:
            next_step()
        else:
            say("no ANCS: turn on Share")
    elif event == 11:                                  # characteristic found
        c, d, v, p, u = data
        if u == NOTIF_SRC:
            chars["n"] = v
        elif u == CTRL_PT:
            chars["c"] = v
        elif u == DATA_SRC:
            chars["d"] = v
    elif event == 12:                                  # characteristics done
        if "d" in chars and "n" in chars and "c" in chars:
            steps.append(("sub", chars["d"], 0))
            steps.append(("sub", chars["n"], 0))
            next_step()
        else:
            say("ANCS parts missing")
    elif event == 17:                                  # a write finished
        c, h, st = data
        print("write done", h, st)
        if steps:
            next_step()
        elif st == 0 and h == chars.get("n", 0) + 1:
            say("READY: send a note")
        elif st != 0:
            say("write err %d" % st)
    elif event == 18:                                  # a notification arrived
        c, h, d = data
        d = bytes(d)
        if h == chars.get("n"):                        # notification source: something happened
            if len(d) >= 8 and d[0] == 0 and not (d[1] & 0x04):     # a NEW one (not an old one that was already there)
                uid = d[4:8]
                asm[0] = b""
                req = bytes((0,)) + uid + bytes((0,)) + bytes((1, 40, 0)) + bytes((3, 80, 0))
                ble.gattc_write(c, chars["c"], req, 1)
        elif h == chars.get("d"):                      # data source: the details, maybe in pieces
            asm[0] += d
            r = parse_data(asm[0])
            if r:
                last[0] = r.get(0, "")
                last[1] = r.get(1, "")
                last[2] = r.get(3, "")
                print("NOTIFICATION:", last)
                draw()
    elif event == 29:                                  # the stack asks for a saved key
        t, idx, key = data
        if key is None:
            items = [(k, v) for k, v in _secrets.items() if k[0] == t]
            if idx < len(items):
                return items[idx][1]
            return None
        return _secrets.get((t, bytes(key)))
    elif event == 30:                                  # the stack wants a key saved
        t, key, val = data
        if val is None:
            _secrets.pop((t, bytes(key)), None)
        else:
            _secrets[(t, bytes(key))] = bytes(val)
        save_secrets()
        return True


ble.active(True)
ble.config(gap_name="NoVas")
ble.config(bond=True, le_secure=True, mitm=False, io=3)
ble.irq(irq)
say("PAIR ME")
advertise()
print("advertising as NoVas. Connect with nRF Connect, accept pairing, then Share System Notifications.")
while True:
    sleep_ms(500)
