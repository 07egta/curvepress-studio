# Research notes (2026-11-05)

What was checked on the web before adding trapping and the print guide, and what each source contributed.

| Topic | Finding | Source |
|---|---|---|
| Trapping | The lighter colour spreads under the darker one because distortion of a light colour is less visible; typical trap 0.08-0.16 mm in offset, more by 1.5-2x next to black. Hand printing is looser, so CurvePress defaults to 0.20 mm. | [Trap (printing), Wikipedia](https://en.wikipedia.org/wiki/Trap_(printing)) |
| Reduction/colour order | Print light to dark; registration is the recurring pain point (jigs for block and paper). | [The reduction print, mkaz.com](https://mkaz.com/ink/the-reduction-print/) |
| 3D-printed plates | Plain PLA, ironing on the top layer, optional 400-800 grit sanding, water-based ink cleaned with soap and a toothbrush; fine lines are the known weak point, simple designs work best. | [3D printed printing plates, rasterweb.net](https://rasterweb.net/raster/2024/01/28/3d-printed-printing-plates/) |
| Small raised detail | A community test found 0.15 mm XY size compensation improved resolution on a 0.4 mm nozzle; stamps must be mirrored. | [Prusa forum: tiny letter stamp](https://forum.prusa3d.com/forum/original-prusa-i3-mk3s-mk3-how-do-i-print-this-printing-help/tiny-letter-stamp-possible-and-how-to-configure-at-best) |
| Type-high | 0.918 in (about 23.32 mm); printers raise thinner blocks with chipboard/card shims, building up rather than grinding down, and checking with calipers. | [Briar Press: Mounting lino at type height](https://briarpress.org/18316) |
| Computer-aided woodblock | Vector contours keep line and shape definition intact when producing relief blocks by additive or laser methods. | [UWE Bristol research output](https://uwe-repository.worktribe.com/output/829350/an-exploration-of-alternative-computer-aided-methods-for-multi-colour-woodblock-printing) |

## Added in 0.3.2

- Plate tiling for beds smaller than the artwork (usable bed = bed size minus 4 mm for skirt/purge).
- A printed test plate for finding a printer's minimum line, gap, dot and hole size. It follows the community advice that fine lines are the weak point of 3D-printed plates and that the XY size compensation should be tuned per printer.

## Not adopted yet

- Reduction-print carve guides (one block, stage-by-stage carving) - useful for hand carving, not needed for separate printed plates.
- Interlocking keys between tiles (tiles are butt-joined on a backing board).

## Fidelity measurements (0.3.3)

Ground truth: a 120 x 80 mm drawing (rings 0.6-1.4 mm, 0.6 mm radiating lines, a sharp star, dots 0.6-3 mm, serif text) rendered at 20 px/mm. The plate is rasterised at 20 px/mm and compared with the drawing (intersection over union).

| Poster mode | 0.3.2 (6 px/mm) | 0.3.3 (auto = 12 px/mm) |
|---|---|---|
| IoU | 0.906 | 0.948 |
| Differing area | 9.4 % | 5.3 % |

Geometry alone (perfect binarisation, then contours + curve fitting): 0.899 with the old pixel convention, 0.924 with pixel centres, up to 0.96 with a sub-pixel grey field and half the simplification tolerance. Sub-pixel grey contours are not implemented yet.
