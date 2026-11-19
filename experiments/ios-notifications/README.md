# iPhone notifications (experiment)

NoVas can receive an iPhone's notifications over Bluetooth Low Energy using Apple's ANCS service (the same one smartwatches use). It worked in a test: NoVas paired with an iPhone and showed the app name, sender and message.

I did **not** keep it in the main program: it needs about 34 KB of memory for the Bluetooth stack, and the board runs without its extra RAM enabled, so memory gets very tight next to the animation. It is here for anyone who wants to build on it, ideally on a build of MicroPython that has PSRAM enabled.

- `ancstest.py` runs on its own and prints the notification on the screen. Open a Bluetooth app (such as nRF Connect), connect to `NoVas`, accept pairing, then turn on *Share System Notifications* for it in iPhone Settings > Bluetooth.
- `ancs.py` is the background version: `ancs.start()`, then read `ancs.inbox`.

Start Bluetooth right after the screen buffer is created in `buddy.py`, before the other modules are loaded, or it may not find enough memory.
