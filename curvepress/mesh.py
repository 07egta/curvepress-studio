"""Direct, watertight plate meshes for 3MF / STL.

The mesh is built from exactly the same cubic Bezier chain that is written to
SVG and STEP, so every format describes one shape.  Building it directly takes
well under a second even for detailed artwork, whereas tessellating the CAD
solid took minutes, and it keeps working for dense halftones where STEP is
deliberately not produced.

Topology (all vertices shared, so the mesh is closed and 2-manifold):

* plate bottom and four sides,
* the floor at ``base`` height: the plate rectangle minus every region, plus
  the inside of every region hole (minus any regions nested in that hole),
* each region's flat top at ``base + relief`` with its holes,
* a vertical wall for every outer and hole loop.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import PlateConfig
from .curves import cubic_segments, signed_area
from .models import PlateLayer

try:  # small compiled dependency; a clear message beats an ImportError deep in export
    import mapbox_earcut as _earcut
except Exception:  # pragma: no cover - exercised only on broken installs
    _earcut = None


class MeshUnavailable(RuntimeError):
    pass


def _flatten(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Adaptive polyline through a closed Bezier chain (no repeated end point)."""
    segments = cubic_segments(points)
    if not len(segments):
        return np.empty((0, 2))
    p0, p1, p2, p3 = (segments[:, i, :] for i in range(4))
    # Standard flatness bound for a cubic: chord error <= 3/4 * max second difference / n^2.
    d1 = np.hypot(*(p0 - 2 * p1 + p2).T)
    d2 = np.hypot(*(p1 - 2 * p2 + p3).T)
    steps = np.ceil(np.sqrt(0.75 * np.maximum(d1, d2) / max(tolerance, 1e-6))).astype(int)
    steps = np.clip(steps, 1, 32)
    out = []
    for value in np.unique(steps):
        index = np.nonzero(steps == value)[0]
        t = np.arange(value) / value
        u = 1 - t
        basis = np.stack((u**3, 3 * u * u * t, 3 * u * t * t, t**3), axis=1)
        pts = np.einsum("sk,nkd->nsd", basis, segments[index])
        out.append((index, pts))
    ordered = [None] * len(segments)
    for index, pts in out:
        for row, seg in zip(index.tolist(), pts):
            ordered[row] = seg
    poly = np.vstack(ordered)
    # Drop exact duplicates (zero-length joins) that would create degenerate walls.
    keep = np.hypot(*(poly - np.roll(poly, 1, axis=0)).T) > 1e-7
    return poly[keep]


def flatten_tolerance(config: PlateConfig) -> float:
    """Largest allowed gap (mm) between a Bezier curve and its straight-edged mesh approximation.

    A tenth of a nozzle width or finer, so tiny round dots and fine curves do not turn into
    visible polygons or lose area in the STL/3MF.
    """
    return max(0.006, min(0.02, config.curve_tolerance_mm * 0.2))


def _point_in_polygon(point: np.ndarray, polygon: np.ndarray) -> bool:
    x, y = float(point[0]), float(point[1])
    xs, ys = polygon[:, 0], polygon[:, 1]
    xn, yn = np.roll(xs, -1), np.roll(ys, -1)
    crosses = (ys > y) != (yn > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_cross = xs + (y - ys) * (xn - xs) / (yn - ys)
    return bool(np.count_nonzero(crosses & (x < x_cross)) % 2)


@dataclass
class _Builder:
    vertices: list[np.ndarray] = field(default_factory=list)
    triangles: list[np.ndarray] = field(default_factory=list)
    count: int = 0

    def add(self, xyz: np.ndarray) -> np.ndarray:
        index = np.arange(self.count, self.count + len(xyz), dtype=np.int64)
        self.vertices.append(np.asarray(xyz, dtype=np.float64))
        self.count += len(xyz)
        return index

    def face(self, rings: list[np.ndarray], ring_ids: list[np.ndarray], up: bool) -> None:
        """Triangulate a planar polygon (first ring outer, others holes)."""
        coords = np.vstack(rings).astype(np.float64)
        ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
        local = _earcut.triangulate_float64(coords, ends).astype(np.int64).reshape(-1, 3)
        if not len(local):
            raise RuntimeError("polygon triangulation produced no triangles")
        ids = np.concatenate(ring_ids)[local]
        a, b, c = coords[local[:, 0]], coords[local[:, 1]], coords[local[:, 2]]
        cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        flip = (cross < 0) if up else (cross > 0)
        ids[flip] = ids[flip][:, ::-1]
        self.triangles.append(ids)

    def wall(self, low: np.ndarray, high: np.ndarray) -> None:
        """Quads between two rings; ring order decides which side faces out."""
        a0, b0 = low, np.roll(low, -1)
        a1, b1 = high, np.roll(high, -1)
        self.triangles.append(np.stack((a0, b0, b1), axis=1))
        self.triangles.append(np.stack((a0, b1, a1), axis=1))


def build_plate_mesh(layer: PlateLayer, config: PlateConfig) -> tuple[np.ndarray, np.ndarray]:
    if _earcut is None:
        raise MeshUnavailable("mapbox_earcut is not installed: pip install mapbox_earcut")
    width, height = config.width_mm, config.height_mm
    base, top = config.base_height_mm, config.base_height_mm + config.relief_height_mm
    tolerance = flatten_tolerance(config)

    def mapped(poly: np.ndarray) -> np.ndarray:
        x = width - poly[:, 0] if config.mirror_for_print else poly[:, 0]
        return np.column_stack((x, height - poly[:, 1]))

    def oriented(poly: np.ndarray, ccw: bool) -> np.ndarray:
        return poly if (signed_area(poly) > 0) == ccw else poly[::-1].copy()

    regions = []
    for region in layer.regions:
        outer = _flatten(region.outer, tolerance)
        if len(outer) < 3:
            continue
        holes = [h for h in (_flatten(hole, tolerance) for hole in region.holes) if len(h) >= 3]
        regions.append((
            oriented(mapped(outer), True),
            [oriented(mapped(h), False) for h in holes],
        ))
    if not regions:
        raise RuntimeError("no printable regions to mesh")

    mesh = _Builder()
    z = lambda poly, level: np.column_stack((poly, np.full(len(poly), level)))  # noqa: E731

    # Plate box: bottom corners and the four floor-level corners.
    rect = np.array([[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]])
    rect_low = mesh.add(z(rect, 0.0))
    rect_high = mesh.add(z(rect, base))
    mesh.face([rect], [rect_low], up=False)
    mesh.wall(rect_low, rect_high)  # rect is CCW, so this faces outward

    # Every loop gets a ring at floor height and one at the top.
    floor_ids, top_ids = [], []
    for outer, holes in regions:
        rings = [outer, *holes]
        floor_ids.append([mesh.add(z(r, base)) for r in rings])
        top_ids.append([mesh.add(z(r, top)) for r in rings])
        for low, high in zip(floor_ids[-1], top_ids[-1]):
            mesh.wall(low, high)
        mesh.face(rings, top_ids[-1], up=True)

    # Nesting: which hole (if any) directly contains each region?
    hole_list = [
        (r_index, h_index, holes[h_index], abs(signed_area(holes[h_index])))
        for r_index, (_, holes) in enumerate(regions)
        for h_index in range(len(holes))
    ]
    parent: list[tuple[int, int] | None] = [None] * len(regions)
    if hole_list:
        boxes = np.array([[r[:, 0].min(), r[:, 1].min(), r[:, 0].max(), r[:, 1].max()]
                          for _, _, r, _ in hole_list])
        areas = np.array([item[3] for item in hole_list])
        owners = np.array([item[0] for item in hole_list])
        probes = np.array([outer[0] for outer, _ in regions])
        for r_index, (px, py) in enumerate(probes.tolist()):
            hit = np.nonzero(
                (boxes[:, 0] <= px) & (px <= boxes[:, 2]) & (boxes[:, 1] <= py) & (py <= boxes[:, 3])
                & (owners != r_index)
            )[0]
            for k in hit[np.argsort(areas[hit])].tolist():  # smallest containing hole wins
                if _point_in_polygon(probes[r_index], hole_list[k][2]):
                    parent[r_index] = (hole_list[k][0], hole_list[k][1])
                    break

    children: dict[tuple[int, int] | None, list[int]] = {}
    for r_index, key in enumerate(parent):
        children.setdefault(key, []).append(r_index)

    # Floor of the plate: rectangle minus top-level regions.
    top_level = children.get(None, [])
    mesh.face(
        [rect, *[regions[i][0][::-1] for i in top_level]],
        [rect_high, *[floor_ids[i][0][::-1] for i in top_level]],
        up=True,
    )
    # Floor inside each hole, minus the islands standing in it.
    for r_index, (_, holes) in enumerate(regions):
        for h_index, hole in enumerate(holes):
            inner = children.get((r_index, h_index), [])
            mesh.face(
                [hole[::-1], *[regions[i][0][::-1] for i in inner]],
                [floor_ids[r_index][1 + h_index][::-1], *[floor_ids[i][0][::-1] for i in inner]],
                up=True,
            )

    vertices = np.vstack(mesh.vertices).astype(np.float32)
    triangles = np.vstack(mesh.triangles).astype(np.uint32)
    return vertices, triangles


def write_binary_stl(path: Path, vertices: np.ndarray, triangles: np.ndarray) -> None:
    tri = vertices[triangles.astype(np.int64)].astype(np.float32)
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    normal = np.where(length > 0, normal / np.maximum(length, 1e-12), 0).astype(np.float32)
    record = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    record["n"] = normal
    record["v"] = tri
    with open(path, "wb") as handle:
        handle.write(b"CurvePress relief plate".ljust(80, b" "))
        handle.write(struct.pack("<I", len(tri)))
        handle.write(record.tobytes())


def mesh_volume(vertices: np.ndarray, triangles: np.ndarray) -> float:
    v = vertices.astype(np.float64)[triangles.astype(np.int64)]
    return float(np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0)


__all__ = ["MeshUnavailable", "build_plate_mesh", "flatten_tolerance", "write_binary_stl", "mesh_volume", "math"]
