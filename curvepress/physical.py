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
    keep_labels = sizes >= threshold
    keep_labels[0] = False
    # Bounding boxes give the same diagonal without rescanning the full image
    # once for each of the thousands of halftone dots.
    for label_id, box in enumerate(ndimage.find_objects(labels), start=1):
        if box is None or keep_labels[label_id]:
            continue
        y, x = box
        diagonal_mm = float(np.hypot(x.stop - x.start - 1, y.stop - y.start - 1)) / config.analysis_ppm
        keep_labels[label_id] = diagonal_mm >= config.minimum_width_mm * 3.0
    return keep_labels[labels]


def _fill_tiny_holes(mask: np.ndarray, config: PlateConfig) -> np.ndarray:
    inverse = ~mask
    labels, count = ndimage.label(inverse)
    if count == 0:
        return mask
    sizes = np.bincount(labels.ravel())
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    threshold = (config.minimum_gap_mm * 0.85 * config.analysis_ppm) ** 2
    fill = sizes < threshold
    fill[list(border_labels)] = False
    fill[0] = False
    return mask | fill[labels]


def _stroke_radius_px(width_mm: float, ppm: float) -> float:
    """Medial distance-transform value for a stroke ``width_mm`` wide.

    A one-pixel stroke has EDT 1 and a geometric width of one pixel, because
    the cell boundary sits halfway to the next pixel. A stroke of N pixels
    therefore has medial EDT ``N/2 + 0.5``.
    """
    return float(width_mm) * float(ppm) / 2.0 + 0.5


def _local_thickness(mask: np.ndarray, max_radius: float) -> np.ndarray:
    """Largest disk radius, capped at ``max_radius``, that covers each pixel.

    Radii are the same units as ``distance_transform_edt`` (pixel centers).
    Pixels thicker than ``max_radius`` are reported as ``max_radius``.
    """
    thickness = np.zeros(mask.shape, dtype=np.float64)
    if max_radius <= 0 or not np.any(mask):
        return thickness
    inner = ndimage.distance_transform_edt(mask)
    steps = int(np.ceil(float(max_radius) * 2.0))
    for step in range(1, steps + 1):
        radius = min(float(max_radius), step / 2.0)
        seeds = inner >= radius - 1e-6
        if not np.any(seeds):
            break
        dist = ndimage.distance_transform_edt(~seeds)
        thickness[dist <= radius + 1e-6] = radius
        if radius >= float(max_radius) - 1e-9:
            break
    return thickness


def _close_narrow_gaps(mask: np.ndarray, config: PlateConfig) -> np.ndarray:
    """Fill gaps narrower than ``minimum_gap_mm``.

    A white line the nozzle cannot leave open is closed here. Open paper and
    gaps that already meet the minimum are left alone, including the concave
    corner of an L, which still belongs to a wide white region.
    """
    if not np.any(mask) or np.all(mask):
        return mask
    limit = _stroke_radius_px(config.minimum_gap_mm, config.analysis_ppm)
    if limit <= 0.5:
        return mask
    thickness = _local_thickness(~mask, limit)
    narrow = (~mask) & (thickness < limit - 1e-6)
    if not np.any(narrow):
        return mask
    return mask | narrow


def _enforce_minimum_width(mask: np.ndarray, config: PlateConfig) -> np.ndarray:
    """Thicken only strokes thinner than ``minimum_width_mm``.

    Large solid areas are not inflated. Growth stops at a gap that is already
    only ``minimum_gap_mm`` wide, so a thin line beside a kept white channel
    gets thicker on the open side and does not seal the channel.
    """
    if not np.any(mask):
        return mask
    ppm = float(config.analysis_ppm)
    target = _stroke_radius_px(config.minimum_width_mm, ppm)
    gap_limit = _stroke_radius_px(config.minimum_gap_mm, ppm)
    thickness = _local_thickness(mask, target)
    deficit = np.zeros(mask.shape, dtype=np.float64)
    deficit[mask] = np.clip(target - thickness[mask], 0.0, None)
    if not np.any(deficit > 0.05):
        return mask
    dist_out, indices = ndimage.distance_transform_edt(~mask, return_indices=True)
    near_def = deficit[indices[0], indices[1]]
    allowed = np.clip(_local_thickness(~mask, gap_limit + target) - gap_limit, 0.0, None)
    paint = (~mask) & (dist_out <= near_def + 1e-6) & (dist_out <= allowed + 1e-6)
    return mask | paint


def apply_printability(
    mask: np.ndarray,
    config: PlateConfig,
    content_box: tuple[int, int, int, int] | None = None,
    *,
    close_narrow_gaps: bool = True,
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
    if close_narrow_gaps:
        result = _close_narrow_gaps(result, config)
    result = _enforce_minimum_width(result, config)

    margin = int(round(config.edge_margin_mm * config.analysis_ppm))
    margin = min(margin, result.shape[0] // 4, result.shape[1] // 4)
    if margin:
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
    radius = max(1.0, config.trap_mm * config.analysis_ppm)
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
    ppm = config.analysis_ppm
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

