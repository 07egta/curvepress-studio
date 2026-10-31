from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

from .config import PlateConfig
from .physical import apply_printability, registration_mask


PALETTE = ["#101820", "#174a7e", "#43a6c6", "#e56b4a", "#e3b341", "#6d597a"]


def load_image(data: bytes) -> Image.Image:
    if len(data) > 30 * 1024 * 1024:
        raise ValueError("image is larger than the 30 MB safety limit")
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if getattr(image, "is_animated", False):
        image.seek(0)
    image = image.convert("RGBA")
    background = Image.new("RGBA", image.size, "white")
    background.alpha_composite(image)
    return background.convert("RGB")


def _paper_crop(image: Image.Image) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"))
    gray = np.mean(rgb, axis=2)
    background = gray > np.percentile(gray, 88)
    foreground = ~ndimage.binary_opening(background, iterations=2)
    labels, count = ndimage.label(foreground)
    if count == 0:
        return image
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    label_id = int(np.argmax(sizes))
    ys, xs = np.where(labels == label_id)
    if not len(xs):
        return image
    # Crop only when a clear photographed border exists; otherwise preserve the full composition.
    coverage = sizes[label_id] / foreground.size
    if coverage < 0.15:
        cropped = image
    else:
        pad = max(2, int(round(min(image.size) * 0.006)))
        box = (
            max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
            min(image.width, int(xs.max()) + pad + 1), min(image.height, int(ys.max()) + pad + 1),
        )
        cropped = image.crop(box)

    # Scans and photographed prints often contain a dark rectangular frame.
    # A conservative inner trim prevents that frame becoming a raised ink border.
    trim_x = int(round(cropped.width * 0.014))
    trim_y = int(round(cropped.height * 0.018))
    if cropped.width - 2 * trim_x >= 32 and cropped.height - 2 * trim_y >= 32:
        cropped = cropped.crop((trim_x, trim_y, cropped.width - trim_x, cropped.height - trim_y))
    return cropped


def fit_on_plate(image: Image.Image, config: PlateConfig) -> tuple[Image.Image, tuple[int, int, int, int]]:
    nx = int(round(config.width_mm * config.analysis_ppm))
    ny = int(round(config.height_mm * config.analysis_ppm))
    margin = int(round(config.edge_margin_mm * config.analysis_ppm))
    # Multi-colour plates reserve a band along the bottom edge for kento marks
    # so the registration stops never touch the artwork.
    band = (
        int(round(config.registration_band_mm * config.analysis_ppm))
        if config.uses_registration()
        else 0
    )
    max_w = max(8, nx - 2 * margin)
    max_h = max(8, ny - 2 * margin - band)
    source = _paper_crop(image)
    scale = min(max_w / source.width, max_h / source.height)
    fitted = source.resize(
        (max(1, int(round(source.width * scale))), max(1, int(round(source.height * scale)))),
        Image.Resampling.LANCZOS,
    )
    x0 = (nx - fitted.width) // 2
    y0 = (ny - band - fitted.height) // 2
    canvas = Image.new("RGB", (nx, ny), "white")
    canvas.paste(fitted, (x0, y0))
    return canvas, (x0, y0, x0 + fitted.width, y0 + fitted.height)


def correct_illumination(image: Image.Image, contrast: float) -> Image.Image:
    source = np.asarray(image.convert("RGB"), dtype=np.float64)
    paper = np.percentile(source.reshape(-1, 3), 96.0, axis=0)
    neutral = source * (float(np.mean(paper)) / np.maximum(paper, 1.0))

    sigma = max(9.0, min(source.shape[:2]) * 0.045)
    field = ndimage.gaussian_filter(neutral, sigma=(sigma, sigma, 0.0))
    target = np.percentile(field.reshape(-1, 3), 62.0, axis=0)
    flat = neutral / np.maximum(field, 18.0) * target
    balanced = neutral * (0.72 - 0.20 * contrast) + flat * (0.28 + 0.20 * contrast)

    luminance = 0.2126 * balanced[..., 0] + 0.7152 * balanced[..., 1] + 0.0722 * balanced[..., 2]
    fine = ndimage.gaussian_filter(luminance, sigma=1.8)
    broad = ndimage.gaussian_filter(luminance, sigma=9.0)
    enhanced = luminance + (0.45 + 0.75 * contrast) * (luminance - fine) + 0.22 * (luminance - broad)
    ratio = enhanced / np.maximum(luminance, 8.0)
    corrected = balanced * ratio[..., None]
    lo, hi = np.percentile(corrected, (0.5, 99.5), axis=(0, 1))
    corrected = (corrected - lo) / np.maximum(hi - lo, 1.0)
    return Image.fromarray(np.clip(7.0 + corrected * 243.0, 0, 255).astype(np.uint8))


def grayscale(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64) / 255.0
    return np.clip(0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2], 0.0, 1.0)


def otsu_threshold(gray: np.ndarray) -> float:
    values = np.clip((gray * 255).astype(np.uint8), 0, 255)
    hist = np.bincount(values.ravel(), minlength=256).astype(np.float64)
    probability = hist / max(1.0, hist.sum())
    omega = np.cumsum(probability)
    mu = np.cumsum(probability * np.arange(256))
    mu_total = mu[-1]
    between = (mu_total * omega - mu) ** 2 / np.maximum(omega * (1.0 - omega), 1e-12)
    return float(np.argmax(between) / 255.0)


def sauvola_threshold(gray: np.ndarray, config: PlateConfig) -> np.ndarray:
    window_mm = 2.6 + 3.2 * (1.0 - config.detail)
    window = max(7, int(round(window_mm * config.analysis_ppm)))
    if window % 2 == 0:
        window += 1
    mean = ndimage.uniform_filter(gray, size=window, mode="reflect")
    square_mean = ndimage.uniform_filter(gray * gray, size=window, mode="reflect")
    std = np.sqrt(np.maximum(0.0, square_mean - mean * mean))
    k = 0.14 + 0.18 * config.contrast
    return mean * (1.0 + k * (std / 0.50 - 1.0))


def _woodcut_mask(corrected: Image.Image, config: PlateConfig) -> np.ndarray:
    gray = grayscale(corrected)
    global_t = otsu_threshold(gray)
    mass_t = global_t * (0.92 + 0.09 * config.contrast)
    masses = gray < mass_t
    local = gray < sauvola_threshold(gray, config)

    gx = ndimage.sobel(gray, axis=1)
    gy = ndimage.sobel(gray, axis=0)
    gradient = np.hypot(gx, gy)
    edge_level = np.percentile(gradient, 78 + 12 * (1.0 - config.detail))
    edges = (gradient > edge_level) & (gray < 0.91)
    edges = ndimage.binary_dilation(edges, iterations=1)

    # Dark masses give visual weight; local threshold and gradients recover faded linework.
    mask = masses | (local & (gray < 0.82 + 0.08 * config.detail)) | edges
    return mask


def _line_mask(corrected: Image.Image, config: PlateConfig) -> np.ndarray:
    gray = grayscale(corrected)
    threshold = sauvola_threshold(gray, config)
    return gray < threshold * (0.98 + 0.04 * config.contrast)


def _poster_mask(corrected: Image.Image, config: PlateConfig) -> np.ndarray:
    gray = grayscale(corrected)
    threshold = otsu_threshold(gray) + (config.contrast - 0.5) * 0.16
    return gray < np.clip(threshold, 0.12, 0.90)


def _halftone_mask(corrected: Image.Image, config: PlateConfig) -> np.ndarray:
    gray = grayscale(corrected)
    height, width = gray.shape
    pitch = max(4, int(round(config.halftone_pitch_mm * config.analysis_ppm)))
    min_radius = config.halftone_min_dot_mm * config.analysis_ppm * 0.5
    max_radius = min(config.halftone_max_dot_mm, config.halftone_pitch_mm * 0.96) * config.analysis_ppm * 0.5
    angle = math.radians(config.halftone_angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    cx, cy = width * 0.5, height * 0.5
    diagonal = int(math.ceil(math.hypot(width, height)))
    mask = np.zeros((height, width), dtype=bool)
    yy, xx = np.ogrid[:height, :width]

    for gy in range(-diagonal, diagonal + pitch, pitch):
        for gx in range(-diagonal, diagonal + pitch, pitch):
            x = cx + gx * cos_a - gy * sin_a
            y = cy + gx * sin_a + gy * cos_a
            ix, iy = int(round(x)), int(round(y))
            if ix < 0 or iy < 0 or ix >= width or iy >= height:
                continue
            tone = float(np.clip(1.0 - gray[iy, ix], 0.0, 1.0))
            if tone < 0.055:
                continue
            radius = min_radius + (max_radius - min_radius) * tone**0.72
            disk = (xx - x) ** 2 + (yy - y) ** 2 <= radius**2
            mask |= disk
    return mask


def _ink_color(rgb: np.ndarray) -> str:
    """Real artwork colour, nudged a little richer so it reads as printing ink."""
    rgb = rgb.astype(np.float64)
    gray = float(np.mean(rgb))
    rich = np.clip(gray + (rgb - gray) * 1.25, 0, 255) * 0.94
    return "#" + "".join(f"{int(round(v)):02x}" for v in rich)


def _to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0..255) to CIELAB, so clusters follow perceived colour differences."""
    c = rgb.astype(np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _kmeans_palette(pixels: np.ndarray, count: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """k-means++ in Lab on a pixel sample; returns RGB palette and a label image."""
    height, width = pixels.shape[:2]
    flat = pixels.reshape(-1, 3)
    lab = _to_lab(flat)
    rng = np.random.default_rng(seed)
    sample = lab[rng.choice(len(lab), size=min(len(lab), 24_000), replace=False)]
    centers = [sample[rng.integers(len(sample))]]
    for _ in range(1, count):
        d2 = np.min(((sample[:, None, :] - np.array(centers)[None]) ** 2).sum(-1), axis=1)
        centers.append(sample[rng.choice(len(sample), p=d2 / max(d2.sum(), 1e-9))])
    centers = np.array(centers)
    for _ in range(30):
        assign = np.argmin(((sample[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
        moved = np.array([
            sample[assign == k].mean(0) if np.any(assign == k) else centers[k] for k in range(count)
        ])
        if np.allclose(moved, centers, atol=0.05):
            break
        centers = moved
    labels = np.empty(len(lab), dtype=np.int32)
    for start in range(0, len(lab), 200_000):
        chunk = lab[start : start + 200_000]
        labels[start : start + 200_000] = np.argmin(((chunk[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
    palette = np.array([
        flat[labels == k].mean(0) if np.any(labels == k) else [255, 255, 255] for k in range(count)
    ]).clip(0, 255).astype(np.uint8)
    return palette, labels.reshape(height, width)


def _color_masks(
    image: Image.Image,
    config: PlateConfig,
    content_box: tuple[int, int, int, int] | None = None,
) -> list[tuple[str, str, np.ndarray]]:
    """Split the artwork into ``color_count`` ink plates plus untouched paper.

    Clustering runs on the real colours inside the artwork only (the white
    padding around it would otherwise steal a cluster), and one extra cluster
    is reserved for the paper so N colours really means N plates.
    """
    rgb = image.convert("RGB")
    full = np.asarray(rgb)
    if content_box is None:
        content_box = (0, 0, rgb.width, rgb.height)
    x0, y0, x1, y1 = content_box
    crop = rgb.crop(content_box)
    # A gentle blur keeps paper grain and JPEG noise from becoming speckle plates.
    smooth = Image.fromarray(
        ndimage.median_filter(np.asarray(crop), size=(3, 3, 1)).astype(np.uint8)
    )
    count = config.color_count + 1
    palette, labels_crop = _kmeans_palette(np.asarray(smooth), count, config.proof_seed)
    labels = np.full(full.shape[:2], -1, dtype=np.int32)
    labels[y0:y1, x0:x1] = labels_crop
    luminance = 0.2126 * palette[:, 0] + 0.7152 * palette[:, 1] + 0.0722 * palette[:, 2]
    order = [int(i) for i in np.argsort(luminance) if np.any(labels_crop == i)]
    paper = order[-1] if len(order) > 1 else None

    result = []
    for palette_id in order:
        if palette_id == paper:
            continue
        rank = len(result)
        result.append((f"plate_{rank + 1}", _ink_color(palette[palette_id]), labels == palette_id))
    return result


def make_masks(
    corrected: Image.Image,
    config: PlateConfig,
    content_box: tuple[int, int, int, int] | None = None,
    source: Image.Image | None = None,
) -> tuple[list[tuple[str, str, np.ndarray]], list[dict]]:
    if config.style == "color_layers":
        candidates = _color_masks(source if source is not None else corrected, config, content_box)
    else:
        generators = {
            "woodcut": _woodcut_mask,
            "line_art": _line_mask,
            "poster": _poster_mask,
            "halftone": _halftone_mask,
        }
        candidates = [("ink", "#111827", generators[config.style](corrected, config))]

    layers = []
    reports = []
    for name, color, mask in candidates:
        cleaned, report = apply_printability(
            mask ^ config.invert,
            config,
            content_box,
        )
        if np.count_nonzero(cleaned):
            if config.uses_registration():
                cleaned = cleaned | registration_mask(cleaned.shape, config)
            layers.append((name, color, cleaned))
            reports.append(report)
    if not layers:
        raise ValueError("no printable artwork remained; increase contrast or reduce cleanup")
    return layers, reports


def mask_preview(mask: np.ndarray, color: str = "#111827") -> Image.Image:
    rgb = np.full((*mask.shape, 3), [248, 244, 233], dtype=np.uint8)
    ink = np.array([int(color[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.uint8)
    rgb[mask] = ink
    return Image.fromarray(rgb)


def composite_preview(layers: list[tuple[str, str, np.ndarray]]) -> Image.Image:
    shape = layers[0][2].shape
    rgb = np.full((*shape, 3), [248, 244, 233], dtype=np.uint8)
    for _, color, mask in reversed(layers):
        ink = np.array([int(color[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.uint8)
        rgb[mask] = ink
    return Image.fromarray(rgb)

