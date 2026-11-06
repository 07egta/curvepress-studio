# Printing and Test-Print Guide

## Print the nozzle strip first

CurvePress can draw lines thinner than a 0.4 mm nozzle will actually hold. Before an artwork plate, print the test strip and read the result:

```bash
curvepress calibrate -o output/nozzle-test
```

Open `output/nozzle-test/nozzle_test_ink.3mf` (or the `.stl`) in the slicer. The file is **not mirrored** — the embossed numbers should read correctly on the plastic. Do not mirror it again. `CALIBRATION.md` in that folder is the score sheet.

- Raised lines, top to bottom: 0.40, 0.50, 0.60, 0.80, 1.00, 1.20, 1.60 mm.
- Grooves, left to right: the same sizes except 1.60 mm.
- Bottom left is a solid ink pad. Bottom right is a frame with a hole.

The thinnest line that stays solid is your minimum line width. In the Studio, open **More settings** and set **Min. line width** to that number (or pass `--min-width` on the CLI), then make the artwork plate again. A groove that fills in will fill in on the artwork too.

Use the same nozzle, layer height, base and relief as the artwork plate. The Studio button **Download a nozzle test strip** uses the values currently on screen.

## Starting point: Bambu A1 mini / 0.4 mm nozzle

| Setting | Recommendation |
|---|---|
| Material | PLA |
| Layer height | 0.20 mm |
| Walls | 4 |
| Top layers | 5 |
| Wall generation | Arachne |
| Supports | None |
| Top-surface ironing | Enabled |
| Orientation | Base on the bed, artwork facing up |

The default plate is 0.8 mm base, 1.2 mm relief, and 2.0 mm total height. If a physical stamp looks faint, first improve roller consistency and pressure on the paper rather than adding more ink. If recessed areas become dirty, there is probably too much ink or the roller is too soft.

## Relief and orientation

- Inked artwork = raised flat faces
- Paper-colored areas = low faces
- **Mirror horizontally for printing** enabled = the plate data is mirrored and the stamped paper reads normally
- In the slicer, show only the layers near the top surface to inspect the artwork more easily

## Common failures

| Symptom | Try first |
|---|---|
| Lines break | Enable Arachne, lower detail slightly and regenerate, then check nozzle and layer height |
| The whole print looks faint | Use a hard flat surface, even out pressure, and roll a thin ink film twice |
| White areas become dirty | Use less ink, a firmer roller, or increase relief to 1.4–1.6 mm |
| The plate warps | Clean the bed, add a brim, or increase the base to 1.0–1.2 mm |
| Small islands peel off | Lower detail, increase minimum line width, and reduce print speed |

For use with food, skin, or fabric, verify the safety of the chosen material and ink separately.



## Colour plates: trapping and print order

- Print **lightest to darkest**. Every export includes `PRINT_GUIDE.md` with the exact order for your plates.
- Trapping (default 0.20 mm) spreads each lighter plate under the darker ones, so a little misregistration shows no white gap. Raise it (0.3-0.4 mm) for hand-held baren printing; set 0 for a registration jig you trust. The effective width cannot be finer than one analysis pixel (1/`analysis_ppm` mm).
- If fine lines fill in or thin out, change the slicer's XY size compensation in 0.05 mm steps.

## Letterpress (type-high)

Type-high is 0.918 in = 23.32 mm. A 2.0 mm plate needs about 21.3 mm of build-up (chipboard, card, or a printed base). Build up rather than grind down, and measure against your own type and rails.
