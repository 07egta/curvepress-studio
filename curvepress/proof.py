"""Physical-looking previews: a pulled proof on washi paper and plate heightmaps.

The proof answers "what will the paper look like after I ink this plate and
rub it with a baren?"  It is intentionally an approximation, but it shows the
three things that surprise first-time printers:

* the print is the mirror of the plate (here: the original orientation),
* ink lies unevenly — denser at edges, lighter in the middle of big solids,
* multi-colour plates never register perfectly, so a fraction of a millimetre
  of drift is simulated per colour.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

from .config import PlateConfig
from .models import PlateLayer
from .physical import registration_mask

PAPER_RGB = np.array([246.0, 241.0, 228.0])
PROOF_SCALE = 2  # proof pixels per analysis pixel


def _washi(shape: tuple[int, int], rng: np.random.Generator) -> np.ndarray:
    """Warm paper with soft clouds and long kozo fibres, values ~0.9..1.03."""
    height, width = shape
    clouds = ndimage.gaussian_filter(rng.standard_normal(shape), sigma=max(6.0, width / 90))
    clouds /= max(1e-6, np.abs(clouds).max())
    grain = ndimage.gaussian_filter(rng.standard_normal(shape), sigma=0.7)
    grain /= max(1e-6, np.abs(grain).max())
    fibres = np.zeros(shape)
    count = int(width * height / 2600)
    for _ in range(count):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        angle = rng.uniform(0, np.pi)
        length = rng.uniform(12, 60) * PROOF_SCALE
        steps = int(length)
        xs = (x + np.cos(angle) * np.arange(steps) + np.cumsum(rng.normal(0, 0.25, steps))).astype(int)
        ys = (y + np.sin(angle) * np.arange(steps) + np.cumsum(rng.normal(0, 0.25, steps))).astype(int)
        ok = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        fibres[ys[ok], xs[ok]] += rng.uniform(0.4, 1.0)
    fibres = ndimage.gaussian_filter(fibres, sigma=0.6)
    fibres /= max(1e-6, fibres.max())
    return 1.0 + 0.025 * clouds + 0.018 * grain - 0.05 * fibres


def _ink_density(mask: np.ndarray, rng: np.random.Generator, ppm: float) -> np.ndarray:
    """Ink opacity 0..1 for one plate: bleed, baren mottling and edge pooling."""
    soft = ndimage.gaussian_filter(mask.astype(np.float64), sigma=0.55 * PROOF_SCALE)
    distance = ndimage.distance_transform_edt(mask) / ppm  # mm from the edge
    pooling = 0.10 * np.exp(-distance / 0.35)
    starve = 0.10 * np.clip((distance - 1.5) / 6.0, 0.0, 1.0)  # big solids print lighter
    mottle = ndimage.gaussian_filter(rng.standard_normal(mask.shape), sigma=2.2 * PROOF_SCALE)
    mottle /= max(1e-6, np.abs(mottle).max())
    speck = rng.random(mask.shape) < 0.005  # paper tooth that ink skips
    density = 0.86 + pooling - starve + 0.07 * mottle
    density[speck] *= 0.45
    return np.clip(soft * density, 0.0, 1.0)


def _raster_regions(layer: PlateLayer, config: PlateConfig, shape: tuple[int, int]) -> np.ndarray:
    """Rasterise the fitted curves (smoother than the analysis mask)."""
    from PIL import ImageDraw

    scale = config.analysis_ppm * PROOF_SCALE
    canvas = Image.new("1", (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(canvas)
    for region in layer.regions:
        draw.polygon([(float(x) * scale, float(y) * scale) for x, y in region.outer], fill=1)
        for hole in region.holes:
            draw.polygon([(float(x) * scale, float(y) * scale) for x, y in hole], fill=0)
    return np.array(canvas, dtype=bool)


def _hex_rgb(color: str) -> np.ndarray:
    return np.array([int(color[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float64)


def make_proof(layers: list[PlateLayer], config: PlateConfig) -> Image.Image:
    rng = np.random.default_rng(config.proof_seed)
    first = layers[0].mask
    shape = (first.shape[0] * PROOF_SCALE, first.shape[1] * PROOF_SCALE)
    ppm = config.analysis_ppm * PROOF_SCALE
    paper = _washi(shape, rng)[..., None] * PAPER_RGB
    out = paper.copy()
    multi = len(layers) > 1
    # Kento ridges are wiped clean before printing, so they never reach paper.
    kento = registration_mask(first.shape, config) if config.uses_registration() else None
    # Print lightest plate first, like a real colour run.
    for layer in reversed(layers):
        mask = _raster_regions(layer, config, shape)
        if kento is not None:
            mask &= ~ndimage.binary_dilation(
                np.kron(kento, np.ones((PROOF_SCALE, PROOF_SCALE), dtype=bool)), iterations=3
            )
        if multi:
            dx, dy = rng.normal(0.0, 0.18 * ppm, 2)
            mask = ndimage.shift(mask.astype(np.uint8), (dy, dx), order=0, mode="constant") > 0
        alpha = _ink_density(mask, rng, ppm)[..., None]
        ink = _hex_rgb(layer.color_hex) if multi else np.array([28.0, 30.0, 34.0])
        # Multiply-style blend: ink is a transparent film on paper.
        film = out * (ink / 255.0)
        out = out * (1.0 - alpha) + film * alpha * 1.04
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def make_heightmap(layer: PlateLayer, config: PlateConfig) -> Image.Image:
    """Grey heightmap of the physical plate (0 = base top, 255 = relief top).

    Mirrored exactly like the CAD output, so the 3D view shows the real plate.
    """
    mask = layer.mask
    if config.mirror_for_print:
        mask = mask[:, ::-1]
    # Tiny blur gives the WebGL height field crisp-but-not-aliased walls.
    smooth = ndimage.gaussian_filter(mask.astype(np.float64), sigma=0.45)
    return Image.fromarray(np.clip(smooth * 255.0, 0, 255).astype(np.uint8), mode="L")
