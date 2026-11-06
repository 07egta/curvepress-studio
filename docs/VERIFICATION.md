# Verification

## 0.3.2

`pytest` covers three print-path fixes: a one-pixel stroke is thickened to the minimum line width without closing a gap that already meets the minimum; `curvepress convert` writes STL and 3MF when OpenCascade is missing and when STEP generation raises; `curvepress calibrate` writes a closed 120 × 96 mm mesh whose 0.40 mm bar measures 0.40 mm. These checks do not replace printing the strip on a machine.

# Version 0.2.0 verification

Verified in the development environment on 2026-10-31 with Python 3.12 and OpenCascade 7.8.1.1. These checks do not replace an actual ink-and-paper test print.

## Reproducible automated checks

```sh
python -m pip install -e '.[cad,dev]'
python -m pytest
python -m ruff check curvepress tests launcher/desktop.py scripts
```

The suite checks every style with a real STEP write/read cycle and direct STL/3MF meshing (closed, exact size, volume equal to the curve area within 0.2 %), including a hole in a raised region. It checks one connected CAD solid, closed mesh edges, non-manifold edges, output dimensions and file existence. HTTP tests exercise analysis ZIP downloads, malformed requests, path traversal, and 12 concurrent requests for the same export (one CAD worker).

## Browser checks

A local Chromium/Playwright session exercised transparent SVG upload, custom base and relief values, analyze, actual CAD export, repeated export, settings invalidation, stale analysis responses, and a 390 px viewport. Browser JavaScript reported no errors. Sample JPEGs are supplied by the repository; their inclusion in the wheel is verified separately by CI.

## Raster performance sample

A single 834 × 498 px constant-tone image, default 139 × 83 mm plate, 6 px/mm analysis, and 1.7 mm dot spacing was run through the old and new functions in the same process. Outputs were compared pixel-for-pixel.

| Stage | Before | After | Ratio |
| --- | ---: | ---: | ---: |
| Halftone rasterization | 1.2964 s | 0.1001 s | 13.0× |
| Component cleanup | 4.1583 s | 0.0057 s | 730.8× |

This is one development-environment sample. Ratios depend on image size, dot count and machine; they do not describe total image-analysis time or CAD boolean/export time.

## Distribution checks

CI tests base Python behavior on Windows, macOS and Linux with Python 3.11 and 3.12, runs CAD integration on Linux, and verifies that the wheel includes the UI and Hokusai sample. The separate Windows portable workflow builds the frozen executable, runs its CAD self-test, and uploads a ZIP only when that self-test succeeds. Check the workflow result for the exact commit before using an artifact.

## Remaining physical and platform verification

Physical ink transfer, paper/ink choice, adhesion, dimensional accuracy after printing, and the unsigned Windows app's behavior on the user's own PC must be checked on that hardware. Automatic tiling is not implemented. STEP has a 1,600-region-per-layer limit (3MF/STL do not); increase halftone spacing or reduce detail if STEP is needed for dense images.
