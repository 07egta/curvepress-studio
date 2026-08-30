from __future__ import annotations

from dataclasses import dataclass
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
    delta = end - start
    length = float(np.linalg.norm(delta))
    if length < 1e-12:
        return np.linalg.norm(points - start, axis=1)
    return np.abs(delta[0] * (start[1] - points[:, 1]) - (start[0] - points[:, 0]) * delta[1]) / length


def rdp(points: np.ndarray, tolerance: float) -> np.ndarray:
    if len(points) <= 2:
        return points
    distances = _distance_to_line(points[1:-1], points[0], points[-1])
    if not len(distances):
        return points[[0, -1]]
    index = int(np.argmax(distances)) + 1
    if distances[index - 1] <= tolerance:
        return points[[0, -1]]
    left = rdp(points[: index + 1], tolerance)
    right = rdp(points[index:], tolerance)
    return np.vstack((left[:-1], right))


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


def cubic_segments(
    points: np.ndarray, corner_fraction: float = 0.24
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Return a closed, shape-preserving chain of cubic Bezier segments.

    A free Catmull-Rom conversion can overshoot a traced boundary and create a
    self-intersection that looks harmless in a raster preview but is invalid as
    a CAD face.  CurvePress instead rounds each polygon corner inside the local
    ``previous/current/next`` triangle, then joins successive corners along the
    original edge.  The rounded part is a quadratic Bezier elevated exactly to
    cubic form; the joins are cubic collinear segments.  This keeps every
    control polygon local, is C1-continuous at the joins, and gives SVG and STEP
    the same four-pole representation.
    """
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:
        return []
    # Contour extraction can occasionally leave duplicate neighbours.  CAD
    # kernels reject the resulting zero-length edge, so remove them here.
    keep = np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1) > 1e-9
    pts = pts[keep]
    if len(pts) < 3:
        return []
    fraction = float(np.clip(corner_fraction, 0.05, 0.45))
    starts = np.empty_like(pts)
    ends = np.empty_like(pts)
    for index, point in enumerate(pts):
        starts[index] = point + fraction * (pts[index - 1] - point)
        ends[index] = point + fraction * (pts[(index + 1) % len(pts)] - point)

    segments: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for index, point in enumerate(pts):
        line_start = ends[index - 1]
        line_end = starts[index]
        if np.linalg.norm(line_end - line_start) > 1e-9:
            delta = line_end - line_start
            segments.append(
                (line_start, line_start + delta / 3.0, line_start + 2.0 * delta / 3.0, line_end)
            )
        curve_start = starts[index]
        curve_end = ends[index]
        # Exact degree elevation of quadratic (start, point, end) to cubic.
        segments.append(
            (
                curve_start,
                curve_start + (point - curve_start) * (2.0 / 3.0),
                curve_end + (point - curve_end) * (2.0 / 3.0),
                curve_end,
            )
        )
    return segments


def path_d(points: np.ndarray) -> str:
    segments = cubic_segments(points)
    first = segments[0][0]
    commands = [f"M {first[0]:.4f} {first[1]:.4f}"]
    for _, c1, c2, end in segments:
        commands.append(
            f"C {c1[0]:.4f} {c1[1]:.4f} {c2[0]:.4f} {c2[1]:.4f} {end[0]:.4f} {end[1]:.4f}"
        )
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

