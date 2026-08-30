# Printing and Test-Print Guide

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

