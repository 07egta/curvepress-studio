from __future__ import annotations

import math
from html import escape

import contourpy
import numpy as np
from scipy import ndimage

from .config import PlateConfig
from .models import CurveRegion


def signed_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _distance_to_line(points: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    dx, dy = float(end[0] - start[0]), float(end[1] - start[1])
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return np.hypot(points[:, 0] - start[0], points[:, 1] - start[1])
    return np.abs(dx * (start[1] - points[:, 1]) - (start[0] - points[:, 0]) * dy) / length


def rdp(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Ramer-Douglas-Peucker with an explicit stack (same result as recursion)."""
    count = len(points)
    if count <= 2:
        return points
    keep = np.zeros(count, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, count - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        distances = _distance_to_line(points[first + 1 : last], points[first], points[last])
        index = int(np.argmax(distances))
        if distances[index] > tolerance:
            split = first + 1 + index
            keep[split] = True
            stack.append((first, split))
            stack.append((split, last))
    return points[keep]


def simplify_closed(points: np.ndarray, tolerance: float) -> np.ndarray | None:
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) > 1 and np.linalg.norm(pts[0] - pts[-1]) < 1e-9:
        pts = pts[:-1]
    if len(pts) < 4:
        return None
    # Rotate the seam to the point furthest from the centroid; this avoids a seam in flat areas.
    centroid = np.mean(pts, axis=0)
    seam = int(np.argmax(np.linalg.norm(pts - centroid, axis=1)))
    pts = np.roll(pts, -seam, axis=0)
    open_points = np.vstack((pts, pts[0]))
    simplified = rdp(open_points, tolerance)
    if len(simplified) > 1 and np.linalg.norm(simplified[0] - simplified[-1]) < 1e-9:
        simplified = simplified[:-1]
    if len(simplified) < 4 or abs(signed_area(simplified)) < tolerance**2:
        return None
    return simplified


def contour_regions(mask: np.ndarray, config: PlateConfig) -> list[CurveRegion]:
    field = ndimage.gaussian_filter(
        mask.astype(np.float64),
        sigma=max(0.42, config.curve_tolerance_mm * config.analysis_ppm * 0.35),
    )
    x = np.linspace(0.0, config.width_mm, mask.shape[1])
    y = np.linspace(0.0, config.height_mm, mask.shape[0])
    generator = contourpy.contour_generator(x=x, y=y, z=field, fill_type="OuterOffset")
    point_sets, offset_sets = generator.filled(0.50, 1.10)
    regions: list[CurveRegion] = []
    for points, offsets in zip(point_sets, offset_sets):
        paths = [points[start:end] for start, end in zip(offsets[:-1], offsets[1:])]
        if not paths:
            continue
        outer = simplify_closed(paths[0], config.curve_tolerance_mm)
        if outer is None:
            continue
        holes = []
        for path in paths[1:]:
            hole = simplify_closed(path, config.curve_tolerance_mm)
            if hole is not None:
                holes.append(hole)
        regions.append(CurveRegion(outer=outer, holes=holes))
    return regions


def cubic_segments(points: np.ndarray, corner_fraction: float = 0.24) -> np.ndarray:
    """Return a closed, shape-preserving chain of cubic Bezier segments.

    A free Catmull-Rom conversion can overshoot a traced boundary and create a
    self-intersection that looks harmless in a raster preview but is invalid as
    a CAD face.  CurvePress instead rounds each polygon corner inside the local
    ``previous/current/next`` triangle, then joins successive corners along the
    original edge.  The rounded part is a quadratic Bezier elevated exactly to
    cubic form; the joins are cubic collinear segments.  This keeps every
    control polygon local, is C1-continuous at the joins, and gives SVG and STEP
    the same four-pole representation.

    Returns an ``(n, 4, 2)`` array; iterating it yields ``(p0, c1, c2, p3)``.
    """
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:
        return np.empty((0, 4, 2))
    # Contour extraction can occasionally leave duplicate neighbours.  CAD
    # kernels reject the resulting zero-length edge, so remove them here.
    keep = np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1) > 1e-9
    pts = pts[keep]
    if len(pts) < 3:
        return np.empty((0, 4, 2))
    fraction = float(np.clip(corner_fraction, 0.05, 0.45))
    previous = np.roll(pts, 1, axis=0)
    following = np.roll(pts, -1, axis=0)
    starts = pts + fraction * (previous - pts)
    ends = pts + fraction * (following - pts)

    # Straight join from the previous corner's end to this corner's start.
    line_start = np.roll(ends, 1, axis=0)
    line_end = starts
    delta = line_end - line_start
    has_line = np.hypot(delta[:, 0], delta[:, 1]) > 1e-9
    lines = np.stack(
        (line_start, line_start + delta / 3.0, line_start + 2.0 * delta / 3.0, line_end), axis=1
    )
    # Rounded corner: exact degree elevation of quadratic (start, point, end).
    corners = np.stack(
        (starts, starts + (pts - starts) * (2.0 / 3.0), ends + (pts - ends) * (2.0 / 3.0), ends), axis=1
    )
    # Interleave [line_i?, corner_i] in order.
    merged = np.empty((len(pts) * 2, 4, 2), dtype=np.float64)
    merged[0::2] = lines
    merged[1::2] = corners
    order = np.ones(len(pts) * 2, dtype=bool)
    order[0::2] = has_line
    return merged[order]


def sample_segments(segments: np.ndarray, steps: int = 8) -> np.ndarray:
    """Points along a cubic chain, vectorised (no per-segment Python loop)."""
    segments = np.asarray(segments, dtype=np.float64)
    if not len(segments):
        return np.empty((0, 2))
    t = np.linspace(0.0, 1.0, steps + 1)[:-1]
    u = 1.0 - t
    basis = np.stack((u**3, 3 * u * u * t, 3 * u * t * t, t**3), axis=1)  # (steps, 4)
    return np.einsum("sk,nkd->nsd", basis, segments).reshape(-1, 2)


def _fmt(values: np.ndarray) -> list[str]:
    return [f"{v:.4f}" for v in values.ravel().tolist()]


def path_d(points: np.ndarray) -> str:
    segments = cubic_segments(points)
    if not len(segments):
        return ""
    first = _fmt(segments[0, 0])
    controls = _fmt(segments[:, 1:, :])
    commands = [f"M {first[0]} {first[1]}"]
    for index in range(len(segments)):
        c = controls[index * 6 : index * 6 + 6]
        commands.append(f"C {c[0]} {c[1]} {c[2]} {c[3]} {c[4]} {c[5]}")
    commands.append("Z")
    return " ".join(commands)


def regions_svg(
    regions: list[CurveRegion], config: PlateConfig, *, fill: str = "#111827", title: str = "CurvePress plate"
) -> str:
    paths = []
    for region in regions:
        combined = [path_d(region.outer)] + [path_d(hole) for hole in region.holes]
        paths.append(f'<path d="{" ".join(combined)}"/>')
    transform = f'translate({config.width_mm:.4f} 0) scale(-1 1)' if config.mirror_for_print else ""
    if transform:
        group_open = (
            f'<g transform="{transform}" fill="{escape(fill)}" fill-rule="evenodd">'
        )
    else:
        group_open = f'<g fill="{escape(fill)}" fill-rule="evenodd">'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{config.width_mm}mm" height="{config.height_mm}mm" '
        f'viewBox="0 0 {config.width_mm} {config.height_mm}">\n'
        f'<title>{escape(title)}</title>\n'
        f'{group_open}\n' + "\n".join(paths) + "\n</g>\n</svg>\n"
    )


def curve_counts(regions: list[CurveRegion]) -> dict[str, int]:
    paths = [region.outer for region in regions]
    paths.extend(hole for region in regions for hole in region.holes)
    return {
        "regions": len(regions),
        "holes": sum(len(region.holes) for region in regions),
        "bezier_paths": len(paths),
        "bezier_segments": int(sum(len(cubic_segments(path)) for path in paths)),
    }


