from __future__ import annotations

import numpy as np
from scipy import ndimage

from .config import PlateConfig


def _remove_scan_frame(
    mask: np.ndarray,
    config: PlateConfig,
    content_box: tuple[int, int, int, int] | None,
) -> np.ndarray:
    """Clear a sub-millimetre band exactly at the placed image boundary.

    A scan or photograph whose edge is darker than the plate background tends
    to become an unintended rectangular relief.  The placement box is known,
    so there is no need to guess from long lines (which could erase a mast,
    horizon, or calligraphy stroke).  Only the boundary itself is cleared.
    """
    if content_box is None:
        return mask
    result = mask.copy()
    height, width = result.shape
    x0, y0, x1, y1 = content_box
    band = max(1, int(round(config.pixels_per_mm * 0.80)))
    x0, x1 = max(0, x0), min(width, x1)
    y0, y1 = max(0, y0), min(height, y1)
    result[max(0, y0 - band) : min(height, y0 + band + 1), x0:x1] = False
    result[max(0, y1 - band - 1) : min(height, y1 + band), x0:x1] = False
    result[y0:y1, max(0, x0 - band) : min(width, x0 + band + 1)] = False
    result[y0:y1, max(0, x1 - band - 1) : min(width, x1 + band)] = False
    return result


def _component_cleanup(mask: np.ndarray, config: PlateConfig) -> np.ndarray:
    labels, count = ndimage.label(mask)
    if count == 0:
        return mask
    sizes = np.bincount(labels.ravel())
    threshold = config.minimum_component_mm2 * config.pixels_per_mm**2
    keep_labels = sizes >= threshold
    keep_labels[0] = False
    # Bounding boxes give the same diagonal without rescanning the full image
    # once for each of the thousands of halftone dots.
    for label_id, box in enumerate(ndimage.find_objects(labels), start=1):
        if box is None or keep_labels[label_id]:
            continue
        y, x = box
        diagonal_mm = float(np.hypot(x.stop - x.start - 1, y.stop - y.start - 1)) / config.pixels_per_mm
        keep_labels[label_id] = diagonal_mm >= config.minimum_width_mm * 3.0
    return keep_labels[labels]


def _fill_tiny_holes(mask: np.ndarray, config: PlateConfig) -> np.ndarray:
    inverse = ~mask
    labels, count = ndimage.label(inverse)
    if count == 0:
        return mask
    sizes = np.bincount(labels.ravel())
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    threshold = (config.minimum_gap_mm * 0.85 * config.pixels_per_mm) ** 2
    fill = sizes < threshold
    fill[list(border_labels)] = False
    fill[0] = False
    return mask | fill[labels]


def apply_printability(
    mask: np.ndarray,
    config: PlateConfig,
    content_box: tuple[int, int, int, int] | None = None,
) -> tuple[np.ndarray, dict]:
    result = mask.astype(bool, copy=True)
    before_pixels = int(np.count_nonzero(result))

    # Close only sub-nozzle pinholes; avoid global opening because it breaks long arcs.
    result = ndimage.binary_closing(
        result,
        structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool),
        iterations=max(1, int(round(config.pixels_per_mm / 6.0))),  # same physical size at any resolution
    )
    if config.remove_scan_frame:
        result = _remove_scan_frame(result, config, content_box)
    result = _component_cleanup(result, config)
    result = _fill_tiny_holes(result, config)

    # Thin features are reported through ``fragile_fraction`` below rather than thickened: a
    # global dilation here used to grow every edge by a resolution-dependent amount (nothing at
    # 6 px/mm, 0.08 mm per side at 12 px/mm), which made the plate less faithful to the art.

    margin = int(round(config.edge_margin_mm * config.pixels_per_mm))
    margin = min(margin, result.shape[0] // 4, result.shape[1] // 4)
    if margin:
        result[:margin, :] = False
        result[-margin:, :] = False
        result[:, :margin] = False
        result[:, -margin:] = False

    distance = ndimage.distance_transform_edt(result) / config.pixels_per_mm
    fragile = result & (distance < config.nozzle_mm * 0.50)
    metrics = {
        "pixels_before": before_pixels,
        "pixels_after": int(np.count_nonzero(result)),
        "removed_fraction": float(
            max(0, before_pixels - np.count_nonzero(result)) / max(1, before_pixels)
        ),
        "fragile_fraction": float(np.count_nonzero(fragile) / max(1, np.count_nonzero(result))),
        "edge_clearance_mm": config.edge_margin_mm,
        "minimum_width_mm": config.minimum_width_mm,
        "minimum_gap_mm": config.minimum_gap_mm,
    }
    return result, metrics



def apply_trapping(masks: list[np.ndarray], config: PlateConfig) -> list[float]:
    """Spread each lighter colour plate a hair under the darker plates (in place).

    Hand printing never registers perfectly, and a sliver of bare paper between
    two colours is the most visible flaw.  Print shops fix it with a *trap*: the
    lighter colour is made slightly larger so it tucks beneath the darker one,
    where it is invisible.  ``masks`` must be ordered darkest first.  The spread
    only ever grows into area a darker plate covers, so the printed picture does
    not change and no ink creeps onto bare paper.

    Returns, per plate, the fraction of extra area that was added.
    """
    added = [0.0] * len(masks)
    if config.trap_mm <= 0 or len(masks) < 2:
        return added
    # One analysis pixel is the finest step the masks can express.
    radius = max(1.0, config.trap_mm * config.pixels_per_mm)
    darker = masks[0].copy()
    for index in range(1, len(masks)):
        mask = masks[index]
        if mask.any() and darker.any():
            distance = ndimage.distance_transform_edt(~mask)
            spread = (distance <= radius) & darker & ~mask
            if spread.any():
                added[index] = float(np.count_nonzero(spread)) / max(1, int(np.count_nonzero(mask)))
                masks[index] = mask | spread
        darker |= masks[index]
    return added


def registration_mask(shape: tuple[int, int], config: PlateConfig) -> np.ndarray:
    """Japanese woodblock kento marks, identical on every colour plate.

    * kagi-kento: an L-shaped corner stop at the bottom-right of the image.
    * hikitsuke-kento: a straight edge stop at the bottom-left.

    Both live in the reserved bottom band (see ``fit_on_plate``), so the paper's
    corner and bottom edge can be pushed against the same ridges for every
    colour.  Coordinates are in un-mirrored image space; the CAD mirror flips
    them together with the artwork, so all plates stay consistent.
    """
    height, width = shape
    ppm = config.pixels_per_mm
    mask = np.zeros(shape, dtype=bool)
    margin = config.edge_margin_mm
    band = config.registration_band_mm
    stroke = max(config.minimum_width_mm * 2.0, 1.2)
    # Bottom edge of the mark sits on the inside of the safety margin.
    y_bottom = config.height_mm - margin
    y_top = y_bottom - stroke
    arm = min(14.0, config.width_mm * 0.18)
    leg = max(stroke * 2.0, min(band - 1.0, 4.5))

    def box(x0: float, y0: float, x1: float, y1: float) -> None:
        a = int(round(max(0.0, x0) * ppm))
        b = int(round(min(config.width_mm, x1) * ppm))
        c = int(round(max(0.0, y0) * ppm))
        d = int(round(min(config.height_mm, y1) * ppm))
        mask[max(0, c) : min(height, d), max(0, a) : min(width, b)] = True

    right = config.width_mm - margin
    # kagi (L): horizontal arm + vertical leg rising into the band.
    box(right - arm, y_top, right, y_bottom)
    box(right - stroke, y_bottom - leg, right, y_bottom)
    # hikitsuke (straight bar).
    left = margin
    box(left, y_top, left + arm, y_bottom)
    return mask

