"""Turn a board capture (made by capture_gallery.py: run-length coded screen pictures) into one contact-sheet PNG.
   python tools/sheet.py gallery.txt gallery.png 4"""
import base64, sys, numpy as np
from PIL import Image, ImageDraw
src, out = sys.argv[1], sys.argv[2]
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 3
imgs = {}; order = []; cur = None; data = []
for l in open(src).read().splitlines():
    if l.startswith("BEGIN"): cur = l.split()[1]; data = []; order.append(cur)
    elif l == "END": imgs[cur] = b"".join(base64.b64decode(x) for x in data)
    elif cur and l and not l.startswith(("Trace", " ", "Attr")): data.append(l)
tiles = []
for k in order:
    if k not in imgs: continue
    raw = np.frombuffer(imgs[k], dtype=np.uint8).reshape(-1, 4)
    vals = raw[:, 0].astype(np.uint32) | (raw[:, 1].astype(np.uint32) << 8)
    runs = raw[:, 2].astype(np.uint32) | (raw[:, 3].astype(np.uint32) << 8)
    v = np.repeat(vals, runs)[:160 * 280].reshape(160, 280)
    v = ((v & 255) << 8) | (v >> 8)
    img = np.stack([((v >> 11) & 31) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3], -1).astype(np.uint8)
    im = Image.fromarray(img); ImageDraw.Draw(im).text((4, 2), k, fill=(150, 150, 150))
    tiles.append(np.array(im))
while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
rows = [np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)]
Image.fromarray(np.concatenate(rows, axis=0)).save(out)
print(len(order), "pictures")
