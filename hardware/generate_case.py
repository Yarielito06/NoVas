"""
NoVas case generator (final design: update 28).

Builds the 3D-printable case for the Waveshare ESP32-S3-Touch-LCD-1.69 + an 800 mAh LiPo battery (42.6 x 29.7 x 6.0 mm):
a one-piece rounded 4-pointed "diamond" shell with a flat front window and a keyring ear on top, plus a BACK DOOR that
clicks into the shell with two flexible hooks (no screws, no glue). It writes:
    stl/novas_shell.stl   the case
    stl/novas_doorB.stl   back door, 0.12 mm gap (snug)
    stl/novas_doorC.stl   back door, 0.18 mm gap (a little looser)
    stl/novas_test_frame.stl   a small test frame to try the fit
The shape is a signed-distance field (numpy) turned into a mesh with marching cubes (scikit-image).
Run:   python generate_case.py        (see requirements.txt)
Coordinates: x = right, y = up (keyring = top), z = depth (0 = the flat front). All sizes are in millimetres.
"""
import math, os, sys, time
from functools import reduce
import numpy as np
import trimesh
from skimage import measure

here = os.path.dirname(os.path.abspath(__file__))
H = 0.3                                        # voxel size (mm)
GLASS_W, GLASS_H = 41.13, 33.13
CAV_W, CAV_H, CAV_R = 41.45, 33.45, 5.7
WIN_W, WIN_H, WIN_R = 39.8, 31.8, 5.0     # update 24: window 0.8 mm bigger each way so no edge of the screen is hidden (lip left on the glass 0.66 / 0.6 mm)
FW, SKIN = 1.2, 2.0
BOARD_T = 8.15                             # measured 8.04 mm + a little slack
BAT = {"800": (42.57, 29.68, 5.95), "370": (36.05, 25.5, 4.08)}   # 800 mAh: measured 42.57 x 29.68 x 5.95 mm
BAT_GAP = 0.4
BAT_POCKET_EXTRA = 0.7      # update 17: battery pocket 0.7 mm bigger than the battery (was 0.5, a bit tight in the fit test)
CABLE_ROOM = 4.3                           # extra height ABOVE the battery so its 53.5 mm cable can lie flat under the door (set to 0 if the cable is shortened)
KEY_R = 3.25
USB_W, USB_Z0, USB_R = 13.0, 2.2, 3.0        # charging groove sized from the measured plug (9.01 x 3.58 mm) with lots of room: 13 mm wide, floor 2.2 mm from the front        # rounded charging groove on the back: width, floor depth, corner radius
BTN_D, SW_Y = 6.0, 15.2                       # switch height (z) and the board's top edge (y)   <- GUESSES, check on the real board
BUTTONS = []                                    # no buttons: the shoulders are solid (touch screen only)   # name, u of the switch, angle from straight-up, +1 = exits on the left shoulder / -1 = right
CH_R, CB_R, ROD_R, COL_R, NOSE_R = 1.95, 2.7, 1.7, 2.4, 1.15   # channel, counterbore, plunger rod, collar, nose radii
# screw-free back door: an inlaid plate with 6 little snap beads that click into grooves in the ring around it
PLATE_W, PLATE_H, PLATE_R = 47.0, 39.0, 10.0
SKIRT_D = 2.0                                  # update 25: the door gets a 2 mm deep SKIRT (plug) that goes down into a deeper socket, so the grip is 3.2 mm tall instead of 1.2 mm
PLATE_GAP = 0.12                               # gap between the door and the ring
BEAD_H, GROOVE_H = 0.45, 0.60                  # snap bead height (E 0.38 / S 0.45 / F 0.52) and groove depth
BEAD_WIN_SHORT = [(-30, -18, -9, 9), (18, 30, -9, 9), (-17, -7.5, -25, -12), (7.5, 17, -25, -12), (-16, -5, 12, 25), (5, 16, 12, 25)]
BEAD_WIN_LONG = [(-30, -18, -17, 17), (18, 30, -17, 17), (-17, -8, -25, -12), (8, 17, -25, -12), (-17, 17, 12, 25)]   # snap beads along whole edges: much more holding area, bigger and easier to print
BEAD_WIN = BEAD_WIN_LONG                                # the shell's grooves are cut for the long windows (the short-bead doors still fit in them)
# shape
L, S_EXP = 47.5, 0.93              # diamond size and how concave the sides are (1.0 = straight, lower = more concave)
SIG = 0.17                          # rounding of the tips (bigger = fatter, softer tips)
RV, RT, PW = 32.0, L, 1.0            # (kept so older scripts still import; the outline is the diamond below)
T_EAR, T_TIP, T_BOT = 6.5, 11.5, 6.0           # ear, side tips, bottom (USB) tip: full-length point but thin at the back
RT_BOT = L
D1, D2 = 4.0, 11.0                            # taper zone, measured from the pocket wall
A_B, R_F, Z_KNIFE = 10.0, 2.5, 2.5
DOME, A_F = 0.0, 12.0                          # update 19: the FRONT is a soft dome too: the middle stands 1.2 mm proud of the rim, blending over 12 mm
Z_RIM = Z_KNIFE + DOME                         # the rim (equator) moved back by the dome height, so the case is NOT thicker
PIN_R, PIN_D = 1.2, 2.8                        # alignment: round holes (2.0 mm) in BOTH halves; push a 5 mm piece of 1.75 mm filament in as a dowel
PINS = [(34.0, 0.0), (-34.0, 0.0), (0.0, -33.0)]
RIM_T = 1.0                                   # the very edge is a 1 mm rounded band, not a razor edge
EDGE_R = 0.9                                  # rounding radius of the cut edges (window, keyring hole, charging groove) and the door seam            # back rim width, front rim radius, height of the rim edge
CROWN, R_CROWN = 1.0, 26.0                    # the back is gently domed, not flat             # back rim width, front rim radius, height of the rim edge


def mn(*a): return reduce(np.minimum, a)
def smin(a, b, k):
    """Like min(a, b) but the crease between them is rounded with radius ~k (a soft intersection)."""
    h = np.maximum(k - np.abs(a - b), 0) / k
    return np.minimum(a, b) - h * h * k * 0.25
def smooth(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)
def sd_rr(x, y, w, h, r):
    qx, qy = np.abs(x) - (w / 2 - r), np.abs(y) - (h / 2 - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def _outline_radius(th):
    """Radius of the outline in direction th: a diamond with the tips on the axes, rounded by smoothing."""
    NF = 4096
    thf = np.linspace(0, 2 * np.pi, NF, endpoint=False)
    c, sn = np.abs(np.cos(thf)), np.abs(np.sin(thf))
    rf = L / (c ** S_EXP + sn ** S_EXP) ** (1.0 / S_EXP)
    kf = np.fft.rfftfreq(NF, d=2 * np.pi / NF) * 2 * np.pi
    rf = np.fft.irfft(np.fft.rfft(rf) * np.exp(-0.5 * (kf * SIG) ** 2), n=NF)
    return np.interp(np.mod(th, 2 * np.pi), np.append(thf, 2 * np.pi), np.append(rf, rf[0])), rf


def _tip_radius():
    return float(_outline_radius(np.array([0.0]))[1].max())


TIP_R = _tip_radius()                  # how far the points really reach after the rounding


def make_grid(TOT):
    xs = np.arange(-50.0, 50.0 + H / 2, H)
    zs = np.arange(-1.2, TOT + 1.2 + H / 2, H)
    return xs, zs


def plan_fields(xs):
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    th = np.arctan2(Y, X); r = np.hypot(X, Y)
    rb = _outline_radius(th)[0]
    F = rb - r
    gx, gy = np.gradient(F, H, H)
    delta = np.where(r < 12.0, F, F / np.maximum(np.hypot(gx, gy), 1e-6))   # distance to the outline (inside > 0); near the centre the gradient trick breaks, use F
    uc = sd_rr(X, Y, CAV_W, CAV_H, CAV_R)                              # distance from the pocket wall (outside > 0)
    tend = T_TIP + (T_EAR - T_TIP) * smooth((np.sin(th) - 0.3) / 0.6) + (T_BOT - T_TIP) * smooth((-np.sin(th) - 0.3) / 0.6)   # thin keyring ear as in update 5
    return X, Y, delta, uc, tend


def surfaces(TOT, delta, uc, tend, X=None, Y=None):
    E = 1 - smooth((uc - D1) / (D2 - D1))
    t_env = tend + (TOT - tend) * E
    d = np.clip(delta, 0, None)
    zf = (Z_KNIFE - RIM_T / 2) * (1 - np.sqrt(np.clip(1 - (1 - np.clip(d / R_F, 0, 1)) ** 2, 0, 1))) + DOME * (1 - smooth(d / A_F))
    ab = np.clip(d / A_B, 0, 1)
    zb = t_env - (t_env - (Z_RIM + RIM_T / 2)) * (1 - np.sqrt(np.clip(1 - (1 - ab) ** 2, 0, 1)))
    if X is not None:
        zb = zb - CROWN * E * np.minimum(np.hypot(X, Y) / R_CROWN, 1.0) ** 2
    return zf, zb, t_env


def build(name, bead_h=BEAD_H, bead_win=None, taper=0.0, gap=0.15):
    bead_win = BEAD_WIN if bead_win is None else bead_win
    bl, bw, bt = BAT[name]
    TOT = FW + BOARD_T + bt + BAT_GAP + CABLE_ROOM + SKIN
    H0 = TOT - SKIN + 0.0137                      # (a hair off the voxel layer so the mesh has no degenerate spots)
    xs, zs = make_grid(TOT)
    X, Y, delta, uc, tend = plan_fields(xs)
    zf, zb, t_env = surfaces(TOT, delta, uc, tend, X, Y)
    Z = zs[None, None, :]
    X3, Y3 = X[:, :, None], Y[:, :, None]
    body = np.minimum(np.minimum(Z - zf[:, :, None], zb[:, :, None] - Z), delta[:, :, None])
    CB_R = CAV_R
    # update 26: the pocket above the board is the UNION of the battery pocket and the board pocket, so the board can pass down to the front
    # (it used to hit the narrower battery pocket: those were the 'bumps' that stopped the screen from going in)
    cav = np.maximum(np.minimum(np.minimum(-sd_rr(X3, Y3, CAV_W, CAV_H, CAV_R), Z - FW), FW + BOARD_T - Z),
                     np.minimum(np.minimum(-(np.minimum(sd_rr(X3, Y3, bl + BAT_POCKET_EXTRA, bw + BAT_POCKET_EXTRA, 0.8), sd_rr(X3, Y3, CAV_W, CAV_H, CAV_R)) if name == "800" else sd_rr(X3, Y3, CAV_W, CAV_H, CB_R)), Z - (FW + BOARD_T)), TOT + 1 - Z))
    win = np.minimum(-sd_rr(X3, Y3, WIN_W, WIN_H, WIN_R), FW + 0.01 - Z)
    usb = np.minimum(-sd_rr(X3, Z - (USB_Z0 + 20.0), USB_W, 40.0, USB_R), -CAV_H / 2 + 0.5 - Y3)      # rounded groove, open to the back
    key = KEY_R - np.hypot(X3, Y3 - (TIP_R - 8.0))
    btn = np.full((1, 1, 1), -1.0); exits = []
    iz = int(np.argmin(np.abs(zs - BTN_D)))
    for (nm, u, phi, sg) in BUTTONS:
        dx, dy = sg * -math.sin(math.radians(phi)), math.cos(math.radians(phi))
        tw = (CAV_H / 2 - SW_Y) / dy                                   # where the channel meets the pocket wall
        t_exit = 0.0
        for t in np.arange(0, 60, 0.05):
            px, py = u + t * dx, SW_Y + t * dy
            if abs(px) >= xs[-1] or abs(py) >= xs[-1]: break
            if body[int(round((px - xs[0]) / H)), int(round((py - xs[0]) / H)), iz] > 0: t_exit = t
        wx, wy, wz = X3 - u, Y3 - SW_Y, Z - BTN_D
        tt = wx * dx + wy * dy
        perp = np.sqrt((wx - tt * dx) ** 2 + (wy - tt * dy) ** 2 + wz ** 2)
        ch = np.minimum(np.minimum(CH_R - perp, tt - 1.0), 70 - tt)
        cb = np.minimum(np.minimum(CB_R - perp, tt - (tw - 0.3)), (tw + 2.2) - tt)
        cx, cy = u + (t_exit + 3.0) * dx, SW_Y + (t_exit + 3.0) * dy
        dim = 3.6 - np.sqrt((X3 - cx) ** 2 + (Y3 - cy) ** 2 + (Z - BTN_D) ** 2)             # shallow round dimple around the button
        c = np.maximum(np.maximum(ch, cb), dim)
        btn = np.maximum(btn, c)
        exits.append(dict(name=nm, u=u, phi=phi, sg=sg, tw=tw, t_exit=t_exit, x=u + t_exit * dx, y=SW_Y + t_exit * dy))
    # ---- the snap-in back door (inlaid plate) and the ring around it
    sdp = sd_rr(X3, Y3, PLATE_W, PLATE_H, PLATE_R)                                   # < 0 inside the plate outline
    def wbox(w, grow=0.0):
        return np.minimum(np.minimum(X3 - (w[0] - grow), (w[1] + grow) - X3), np.minimum(Y3 - (w[2] - grow), (w[3] + grow) - Y3))
    seg_c = reduce(np.maximum, [wbox(w) for w in bead_win]); seg_g = reduce(np.maximum, [wbox(w, 0.6) for w in BEAD_WIN])
    zc = H0 + 1.0
    tooth_b = np.maximum(0.0, bead_h - np.abs(Z - zc)); tooth_g = np.maximum(0.0, GROOVE_H - np.abs(Z - zc))
    # update 21: the door edge is TAPERED. At its inner face it is 0.12 mm smaller than the opening (slides in easily); at its back face it is
    # 'taper' mm LARGER than the opening, so pushing it in wedges it tight all the way round (friction over the whole 160 mm edge).
    tz = np.clip((Z - (H0 - SKIRT_D)) / (SKIRT_D + 1.2), 0.0, 1.0)
    gap_z = gap + 0.0 * tz                                                          # update 28: no taper any more, the door is held by hooks
    door_core = smin(mn(body, Z - H0), -(sdp + gap_z), 0.5)
    pocket_out = np.minimum(sd_rr(X3, Y3, bl + BAT_POCKET_EXTRA + 0.8, bw + BAT_POCKET_EXTRA + 0.8, 1.0), sd_rr(X3, Y3, CAV_W + 0.8, CAV_H + 0.8, CAV_R + 0.4))          # > 0 outside the battery pocket (+0.4 mm margin)
    skirt = mn(-(sdp + gap_z), Z - (H0 - SKIRT_D), (H0 + 0.3) - Z, pocket_out)                         # the plug: only in the band round the pocket, never over the battery
    # ---- update 28: HOOKS (like the video). Two long flexible tabs on the long sides of the door, each with a small ramp-shaped hook that clicks into a groove in the shell.
    L_T, T_T, B_H = 6.3, 1.2, 0.5
    zt = H0 - L_T
    inpl = -(sdp + gap)
    xr = 12.6 - np.abs(X3)
    tt_ = Z - zt
    bz = np.where(tt_ < 1.2, B_H * np.clip(tt_ / 1.2, 0, 1), np.clip(B_H - (tt_ - 1.2) * 1.25, 0, B_H))
    tab = mn(inpl, T_T - inpl, xr, Z - zt, (H0 + 0.3) - Z, np.abs(Y3) - 13.0)
    hook = mn(-inpl, bz + inpl, xr, Z - zt, (zt + 1.8) - Z, np.abs(Y3) - 13.0)
    skirt = mn(skirt, np.maximum(np.abs(X3) - 13.4, 13.0 - np.abs(Y3)))
    deep = mn(-sdp, xr + 0.5, np.abs(Y3) - 13.0, Z - (zt - 0.3))
    gv = mn(xr + 0.4, sdp, (bz + 0.2) - sdp, Z - (zt - 0.05), (zt + 1.9) - Z, np.abs(Y3) - 13.0)
    socket = np.maximum(mn(-sdp, Z - (H0 - SKIRT_D)), deep)                                                              # the deeper socket in the shell for that plug
    bead = mn(body, Z - H0, tooth_b - (sdp + PLATE_GAP), sdp + PLATE_GAP + 0.05, seg_c)
    groove = mn(tooth_g - sdp, sdp, seg_g, Z - H0)
    # update 24: NO beads and NO grooves any more (the photos showed they print as thin, stringy, half-finished bits). The door holds by its tapered edge only.
    bead = np.full(body.shape, -1.0); groove = gv
    ring = smin(mn(body, Z - H0), sdp, 0.5)
    out_of_pocket = (-CAV_H / 2 + 0.3) - Y3                                   # how far outwards from the pocket wall
    bay = mn(X3 + 16.0, 16.0 - X3, Y3 + 22.8, out_of_pocket, Z - (FW + 2.0), (FW + BOARD_T + 0.9) - np.maximum(out_of_pocket - 2.5, 0.0) - Z)   # the roof slopes down at 45 degrees away from the pocket, so it prints without a bridge   # room for the battery plug + cable beside the USB-C
    core = mn(np.maximum(mn(body, H0 - Z), ring), -cav, -btn, -groove, -bay, -socket)
    shell = smin(smin(smin(core, -win, EDGE_R), -key, EDGE_R), -usb, EDGE_R)       # rounded window edge, keyring hole and charging groove
    cover = smin(mn(reduce(np.maximum, [door_core, bead, skirt, tab, hook]), -key), -usb, EDGE_R)
    # ---- update 19: split the shell at the rim into a thin domed FRONT PLATE and the BACK SHELL (joined with glue and 3 pins)
    ZS = Z_RIM + 0.0137
    holes_p = np.full(shell.shape, -1.0)
    holes_b = np.full(shell.shape, -1.0)
    for (px, py) in PINS:
        rr = np.hypot(X3 - px, Y3 - py)
        holes_p = np.maximum(holes_p, np.minimum(PIN_R - rr, np.minimum(Z - (ZS - PIN_D), ZS + 0.4 - Z)))
        holes_b = np.maximum(holes_b, np.minimum(PIN_R - rr, np.minimum(Z - (ZS - 0.4), ZS + PIN_D - Z)))
    plate = np.minimum(np.minimum(shell, ZS - Z), -holes_p)
    back = np.minimum(np.minimum(shell, Z - ZS), -holes_b)
    info = dict(exits=exits, name=name, TOT=TOT, H0=H0, ZS=ZS, xs=xs, zs=zs, delta=delta, zb=zb, zf=zf, body=body, shell=shell, plate=plate, back=back, cover=cover, cav=cav)
    # ----- checks (voxel counts; each voxel = H^3 mm3)
    vox = H ** 3
    gl = np.minimum(-sd_rr(X3, Y3, GLASS_W, GLASS_H, 5.2), np.minimum(Z - FW, FW + BOARD_T - Z))
    ba = mn(bl / 2 - np.abs(X3), bw / 2 - np.abs(Y3), Z - (FW + BOARD_T + BAT_GAP / 2), (FW + BOARD_T + BAT_GAP / 2 + bt) - Z)
    chk = {}
    chk["board touching shell (0 = ok)"] = round(float(((gl > 0) & (shell > 0)).sum() * vox), 2)
    chk["battery touching shell/cover (0 = ok)"] = round(float(((ba > 0) & ((shell > 0) | (cover > 0))).sum() * vox), 2)
    chk["door beads pressing into the ring (the snap, mm3)"] = round(float(((cover > 0) & (shell > 0)).sum() * vox), 2)
    ex = np.minimum(-sd_rr(X3, Y3, CAV_W + 2.0, CAV_H + 2.0, CAV_R + 1.0), np.minimum(Z - (FW - 1.0), H0 - 0.2 - Z))
    chk["pocket walls thinner than 1 mm (voxels outside body, 0 = ok)"] = int(((ex > 0) & (body < 0)).sum())
    kk = np.argmin(np.abs(zs - (H0 + 0.15)))
    cav_slice = cav[:, :, np.argmin(np.abs(zs - (H0 - 0.15)))] > 0
    chk["pocket opening not covered by the cover plate (0 = ok)"] = int((cav_slice & (cover[:, :, kk] <= 0)).sum())
    wall_top = (body[:, :, np.argmin(np.abs(zs - (H0 - 0.15)))] > 0) & ~cav_slice
    info["chk"] = chk
    return info


def plunger(e):
    """One printed button: nose (touches the switch) + collar (stops it falling out) + rod. Axis along +x, nose at x=0."""
    from manifold3d import Manifold
    tw, te = e['tw'], e['t_exit'] - 0.35
    parts = [Manifold.cylinder(tw + 0.95, NOSE_R, NOSE_R, 48),
             Manifold.cylinder(1.2, COL_R, COL_R, 64).translate((0, 0, tw + 0.9)),
             Manifold.cylinder(te - (tw + 2.0), ROD_R, ROD_R, 64).translate((0, 0, tw + 2.0))]
    m = parts[0] + parts[1] + parts[2]
    return m.rotate((0, 90, 0))


def to_mesh(vol, xs, zs, z_shift=0.0):
    verts, faces, _, _ = measure.marching_cubes(vol, level=0.0, spacing=(H, H, H), allow_degenerate=False)
    verts = verts + np.array([xs[0], xs[0], zs[0]])
    verts[:, 2] -= z_shift
    verts[:, 0] *= -1                                  # mirror so the printed part matches the front view
    faces = faces[:, ::-1]
    m = trimesh.Trimesh(verts, faces, process=True)
    m.update_faces(m.nondegenerate_faces()); m.remove_unreferenced_vertices()
    parts = [p for p in m.split(only_watertight=False) if len(p.faces) > 0.02 * len(m.faces)]      # drop dust-sized specks
    if len(parts) > 1:
        m = trimesh.util.concatenate(parts)
    if not m.is_watertight:
        trimesh.repair.fill_holes(m); m.remove_unreferenced_vertices()
    if m.is_watertight and m.volume < 0:
        m.invert()                                      # make sure the faces point OUT of the part (some slicers care)
    return m


def coupon():
    """A small test frame with the SAME socket as the real shell (47 x 39 opening, 3.2 mm tall walls, battery-pocket hole in the floor)."""
    from shapely.geometry import box
    def rr(w, h, r): return box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, 64)
    outer = rr(58.0, 50.0, 14.0)
    floor = outer.difference(rr(BAT["800"][0] + BAT_POCKET_EXTRA, BAT["800"][1] + BAT_POCKET_EXTRA, 0.8).union(rr(CAV_W, CAV_H, CAV_R)))
    wall = outer.difference(rr(PLATE_W, PLATE_H, PLATE_R))
    a = trimesh.creation.extrude_polygon(floor, 1.2)
    b = trimesh.creation.extrude_polygon(wall, SKIRT_D + 1.2); b.apply_translation((0, 0, 1.2))
    b.apply_translation((0, 0, -0.01))                  # overlap a hair so the two parts fuse
    m = trimesh.boolean.union([a, b], engine='manifold')
    return m


if __name__ == "__main__":
    outdir = os.path.join(here, "stl"); os.makedirs(outdir, exist_ok=True)
    t0 = time.time(); I = build("800")
    print(f"== 800 mAh ONE-PIECE, domed, no beads ==  thickness {I['TOT']:.1f} mm   ({time.time()-t0:.1f}s)")
    for k, v in I["chk"].items(): print("  ", k, ":", v)
    sh = to_mesh(I["shell"], I["xs"], I["zs"])
    sh.export(os.path.join(outdir, "novas_shell.stl"))
    print(f"   shell: {len(sh.faces)} triangles, watertight={sh.is_watertight}, size={np.round(sh.extents,1)}")
    for tag, gp in (("B", 0.12), ("C", 0.18)):
        I2 = build("800", gap=gp); m = to_mesh(I2["cover"], I2["xs"], I2["zs"], z_shift=I2["H0"])
        m.vertices[:, 2] -= m.vertices[:, 2].min()
        m.export(os.path.join(outdir, f"novas_door{tag}.stl"))
        print(f"   door {tag}: gap {gp} mm, watertight={m.is_watertight}, size={np.round(m.extents,2)}")
    c = coupon(); c.export(os.path.join(outdir, "novas_test_frame.stl"))
    print(f"   test frame: watertight={c.is_watertight}, size={np.round(c.extents,1)}")
    print("done")
