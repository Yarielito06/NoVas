# NoVas case

A one-piece, rounded 4-pointed "diamond" case with a flat front window and a keyring ear on top. The back door clicks in with two flexible hooks. No screws, no glue.

- Size: about 83 x 83 x 22 mm
- Fits: Waveshare ESP32-S3-Touch-LCD-1.69 + an 800 mAh LiPo (42.6 x 29.7 x 6.0 mm) with its cable laid flat
- The USB-C plug goes through a groove in the back; the battery plug has its own bay

## Files

| File | What it is |
|---|---|
| `stl/novas_shell.stl` | The case |
| `stl/novas_doorB.stl` | Back door, 0.12 mm gap: snug |
| `stl/novas_doorC.stl` | Back door, 0.18 mm gap: a little looser |
| `generate_case.py` | The program that makes the STL files above. Change a number, run it, and you get a new case |
| `print_settings/` | The Orca Slicer profile and filament I used |

## Printing

I printed these on a Flashforge Adventurer 5M with PETG, using Orca Slicer. Any printer that can do PETG should work.

1. Print the shell **front side down** (the flat window face on the bed) and the door **inner side down** (the flat side with the two hooks).
2. 0.16 mm layers, 4 walls, 30% gyroid infill, tree supports that touch only the build plate, support threshold 60 degrees. See `print_settings/process_tough_dome_supports.json` and `filament_petg_tough.json`.
3. Print one shell and one door. If you are not sure which door, print both: try **B** first, and use **C** if B is too tight.

### Take the support material out of the door

The door is printed upside down, so supports fill the space between its hooks. **Remove all of it** before fitting the door. If the door does not close with the board and battery inside, leftover support material in the pocket is the most likely reason (it fooled me for two prints).

### Fit it

Slide the board in from the back with the screen against the window. Lay the battery on top, cable flat beside it. Press the door straight in until the hooks click. To take it out, pry the door at the USB-C groove.

## Changing the design

```bash
pip install -r requirements.txt
python generate_case.py        # writes stl/*.stl (takes a minute)
```

The sizes of the board, the battery and the gaps are named constants at the top of `generate_case.py` (`BOARD_T`, `BAT`, `CABLE_ROOM`, `PLATE_GAP`, ...). The shape is a signed-distance field turned into a mesh with marching cubes. `stl/novas_test_frame.stl` is a small frame you can print first to check the fit of the door.

## Licence

The case designs and this generator are [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): copy them, change them, sell prints, just credit NoVas (https://github.com/Yarielito06/NoVas).
