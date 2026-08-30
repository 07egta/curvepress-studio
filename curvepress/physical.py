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
    band = max(1, int(round(config.analysis_ppm * 0.80)))
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
    threshold = config.minimum_component_mm2 * config.analysis_ppm**2
    keep = np.zeros_like(mask, dtype=bool)
    for label_id in range(1, count + 1):
        ys, xs = np.where(labels == label_id)
        if not len(xs):
            continue
        diagonal_mm = float(np.hypot(np.ptp(xs), np.ptp(ys))) / config.analysis_ppm
        # Long thin strokes are meaningful curves, not speckle noise.
        if sizes[label_id] >= threshold or diagonal_mm >= config.minimum_width_mm * 3.0:
            keep[labels == label_id] = True
    return keep


def _fill_tiny_holes(mask: np.ndarray, config: PlateConfig) -> np.ndarray:
    inverse = ~mask
    labels, count = ndimage.label(inverse)
    if count == 0:
        return mask
    sizes = np.bincount(labels.ravel())
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    threshold = (config.minimum_gap_mm * 0.85 * config.analysis_ppm) ** 2
    result = mask.copy()
    for label_id in range(1, count + 1):
        if label_id not in border_labels and sizes[label_id] < threshold:
            result[labels == label_id] = True
    return result


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
        iterations=1,
    )
    if config.remove_scan_frame:
        result = _remove_scan_frame(result, config, content_box)
    result = _component_cleanup(result, config)
    result = _fill_tiny_holes(result, config)

    target_px = config.minimum_width_mm * config.analysis_ppm
    thicken_iterations = max(0, int(np.floor((target_px - 3.0) / 2.0)))
    if thicken_iterations:
        result = ndimage.binary_dilation(result, iterations=thicken_iterations)

    margin = int(round(config.edge_margin_mm * config.analysis_ppm))
    margin = min(margin, result.shape[0] // 4, result.shape[1] // 4)
    result[:margin, :] = False
    result[-margin:, :] = False
    result[:, :margin] = False
    result[:, -margin:] = False

    distance = ndimage.distance_transform_edt(result) / config.analysis_ppm
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

