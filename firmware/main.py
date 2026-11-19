"""
main.py - starts Buddy and keeps a crash note.
buddy.py is the real program (it runs forever). If it ever stops with an error, the error is written to
crash.log on the board and the chip restarts, so Buddy never just freezes.
"""
import sys
import machine

try:
    import buddy
except Exception as e:
    try:
        with open("crash.log", "w") as f:
            f.write("reset cause before: %s\n" % machine.reset_cause())
            sys.print_exception(e, f)
    except Exception:
        pass
    machine.reset()
