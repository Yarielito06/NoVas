"""
Set NoVas's clock from your computer's time.

    python tools/set_time.py            (needs: pip install mpremote)

The board has its own clock chip (PCF85063) that keeps counting while the battery stays plugged in.
It uses the time of the computer you run this on (your local time zone). There is no automatic daylight-saving change.
"""
import subprocess, sys, time

t = time.localtime()
weekday = (t.tm_wday + 1) % 7            # the chip counts Sunday = 0
code = "import ui; ui.set_time(%d,%d,%d,%d,%d,%d,%d); print(ui.read_time())" % (
    t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, weekday)
sys.exit(subprocess.call(["mpremote", "exec", code]))
