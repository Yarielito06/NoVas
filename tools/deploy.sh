#!/bin/sh
# Compile the big files and copy NoVas's program onto the board.
#   ./tools/deploy.sh                 (finds the board by itself)
#   ./tools/deploy.sh /dev/ttyACM0    (or name the port)
# Needs:  pip install mpremote mpy-cross==1.24.1.post3     (the board runs MicroPython v1.24.1)
set -e
cd "$(dirname "$0")/../firmware"
PORT="${1:-auto}"
MP="mpremote connect $PORT"

# These files are big, so they are turned into compact .mpy files first (they also load faster and use less memory).
for f in face face_px pen overlay ui uifont; do
    mpy-cross -march=xtensawin "$f.py" -o "$f.mpy"
done

$MP fs cp main.py :main.py
$MP fs cp buddy.py :buddy.py
$MP fs cp config.py :config.py
$MP fs cp lcd_s3.py :lcd_s3.py
$MP fs cp touch.py :touch.py
$MP fs cp imu.py :imu.py
$MP fs cp sound.py :sound.py
$MP fs cp ui_font.bin :ui_font.bin
for f in face face_px pen overlay ui uifont; do
    $MP fs cp "$f.mpy" ":$f.mpy"
done
rm -f *.mpy
echo "Done. Restarting NoVas..."
$MP reset
