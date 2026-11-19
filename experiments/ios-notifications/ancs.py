"""
ancs.py - lets Buddy receive the iPhone's notifications over Bluetooth (Apple's ANCS service).

It works by itself in the background (Bluetooth events), so the face loop never waits for it.
  ancs.start()        turn it on (safe to call even if Bluetooth fails)
  ancs.inbox          list of (app, title, message) that arrived and have not been picked up yet
  ancs.connected      True while the iPhone is connected and sharing notifications
The iPhone is paired once (see ancstest.py); its keys are kept in bonds.json so it reconnects by itself later.
"""
import bluetooth, json

ANCS = bluetooth.UUID("7905F431-B5CE-4E99-A40F-4B1E122D00D0")
NOTIF_SRC = bluetooth.UUID("9FBF120D-6301-42D9-8C58-25E699A21DBD")
CTRL_PT = bluetooth.UUID("69D1D8F3-45E1-49A8-9821-9BBDFDAAD9D9")
DATA_SRC = bluetooth.UUID("22EAC6E9-24D6-4BB5-BE44-B36ACE7C7BFB")
ANCS_LE = bytes((0xD0, 0x00, 0x2D, 0x12, 0x1E, 0x4B, 0x0F, 0xA4, 0x99, 0x4E, 0xCE, 0xB5, 0x31, 0xF4, 0x05, 0x79))

inbox = []
connected = [False]
stage = [0]                # 0 waiting, 1 iPhone connected, 2 paired (encrypted), 3 ANCS found, 4 parts found, 5 linked, -1 pairing failed, -2 ANCS missing
active = [False]
_ble = [None]
_conn = [None]
_chars = {}
_steps = []
_asm = [b""]
_secrets = {}

# the short friendly names of common apps (anything else shows its last word, in capitals)
NAMES = {"net.whatsapp.WhatsApp": "WHATSAPP", "com.apple.MobileSMS": "MESSAGES", "com.burbn.instagram": "INSTAGRAM",
         "com.apple.mobilephone": "PHONE", "com.apple.mobilemail": "MAIL", "ph.telegra.Telegraph": "TELEGRAM",
         "com.atebits.Tweetie2": "X", "com.zhiliaoapp.musically": "TIKTOK", "com.google.ios.youtube": "YOUTUBE",
         "com.apple.facetime": "FACETIME", "com.apple.reminders": "REMINDERS", "com.apple.mobilecal": "CALENDAR",
         "com.facebook.Messenger": "MESSENGER", "com.google.Gmail": "GMAIL", "com.snapchat.Snapchat": "SNAPCHAT"}

# Buddy's font has only plain letters: accents become the plain letter, emoji and the rest are dropped.
_FOLD = {"á": "a", "à": "a", "ä": "a", "â": "a", "é": "e", "è": "e", "ë": "e", "ê": "e", "í": "i", "ì": "i", "ï": "i", "î": "i",
         "ó": "o", "ò": "o", "ö": "o", "ô": "o", "ú": "u", "ù": "u", "ü": "u", "û": "u", "ñ": "n", "ç": "c",
         "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N", "Ü": "U", "¿": "?", "¡": "!", "’": "'", "‘": "'",
         "“": '"', "”": '"', "…": "...", "–": "-", "—": "-"}


def plain(s):
    out = ""
    for ch in s:
        if ch in _FOLD:
            out += _FOLD[ch]
        elif " " <= ch <= "~":
            out += ch
        elif ch == "\n":
            out += " "
    return out


def friendly(app):
    n = NAMES.get(app)
    if n:
        return n
    return plain(app.split(".")[-1]).upper()[:14] or "APP"


try:
    with open("bonds.json") as f:
        for k, v in json.load(f).items():
            t, key = k.split(":")
            _secrets[(int(t), bytes.fromhex(key))] = bytes.fromhex(v)
except Exception:
    pass


def _save():
    with open("bonds.json", "w") as f:
        json.dump({"%d:%s" % (t, k.hex()): v.hex() for (t, k), v in _secrets.items()}, f)


def _advertise():
    ble = _ble[0]
    name = b"NoVas"
    adv = bytes((2, 0x01, 0x06)) + bytes((17, 0x15)) + ANCS_LE
    resp = bytes((len(name) + 1, 0x09)) + name
    ble.gap_advertise(500000, adv, resp_data=resp, connectable=True)      # every half second: gentle on the battery


def _next():
    if not _steps:
        return
    kind, a, b = _steps.pop(0)
    if kind == "chars":
        _ble[0].gattc_discover_characteristics(_conn[0], a, b)
    else:
        _ble[0].gattc_write(_conn[0], a + 1, b"\x01\x00", 1)               # switch notifications on


def _parse(buf):
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
    return out if len(out) >= 3 else None


def _irq(event, data):
    ble = _ble[0]
    if event == 1:
        _conn[0] = data[0]
        _steps.clear()
        stage[0] = 1
        try:
            ble.gap_pair(_conn[0])
        except Exception:
            pass
    elif event == 2:
        _conn[0] = None
        connected[0] = False
        stage[0] = 0
        _advertise()
    elif event == 28:
        c, enc, auth, bonded, ks = data
        if enc:
            stage[0] = 2
            ble.gattc_discover_services(c, ANCS)
        else:
            stage[0] = -1
    elif event == 9:
        c, s, e, u = data
        if u == ANCS:
            _steps.append(("chars", s, e))
            stage[0] = 3
    elif event == 10:
        if _steps:
            _next()
        else:
            stage[0] = -2
    elif event == 11:
        c, d, v, p, u = data
        if u == NOTIF_SRC:
            _chars["n"] = v
        elif u == CTRL_PT:
            _chars["c"] = v
        elif u == DATA_SRC:
            _chars["d"] = v
    elif event == 12:
        if "d" in _chars and "n" in _chars and "c" in _chars:
            stage[0] = 4
            _steps.append(("sub", _chars["d"], 0))
            _steps.append(("sub", _chars["n"], 0))
            _next()
    elif event == 17:
        c, h, st = data
        if _steps:
            _next()
        elif st == 0 and h == _chars.get("n", -5) + 1:
            connected[0] = True
            stage[0] = 5
    elif event == 18:
        c, h, d = data
        d = bytes(d)
        if h == _chars.get("n"):
            if len(d) >= 8 and d[0] == 0 and not (d[1] & 0x04):             # a NEW notification (not an old one)
                _asm[0] = b""
                ble.gattc_write(c, _chars["c"], bytes((0,)) + d[4:8] + bytes((0,)) + bytes((1, 40, 0)) + bytes((3, 90, 0)), 1)
        elif h == _chars.get("d"):
            _asm[0] += d
            r = _parse(_asm[0])
            if r:
                _asm[0] = b""
                if len(inbox) < 6:
                    inbox.append((friendly(r.get(0, "")), plain(r.get(1, "")).strip(), plain(r.get(3, "")).strip()))
    elif event == 29:
        t, idx, key = data
        if key is None:
            items = [(k, v) for k, v in _secrets.items() if k[0] == t]
            return items[idx][1] if idx < len(items) else None
        return _secrets.get((t, bytes(key)))
    elif event == 30:
        t, key, val = data
        if val is None:
            _secrets.pop((t, bytes(key)), None)
        else:
            _secrets[(t, bytes(key))] = bytes(val)
        _save()
        return True


def start():
    """Turn Bluetooth on and wait for the iPhone. Returns True if it started."""
    try:
        ble = bluetooth.BLE()
        _ble[0] = ble
        ble.active(True)
        ble.config(gap_name="NoVas")
        ble.config(bond=True, le_secure=True, mitm=False, io=3)
        ble.irq(_irq)
        _advertise()
        active[0] = True
        return True
    except Exception:
        active[0] = False
        return False
