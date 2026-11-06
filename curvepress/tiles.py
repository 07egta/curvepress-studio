"""Split a plate into tiles that fit a printer bed, and build closed meshes from planar geometry.

``mesh_from_solid`` is a second, geometry-based mesh builder.  It takes the raised
area as a shapely (multi)polygon inside a rectangle, so a region that touches or
crosses the rectangle edge (which happens at every tile cut) is handled exactly.
All vertices are welded on a 1 micron grid, which keeps every mesh closed and
2-manifold.  The test plate uses it too.
"""
from __future__ import annotations

import math
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import PlateConfig
from .mesh import MeshUnavailable, _flatten
from .models import PlateLayer

try:
    import shapely
    from shapely.geometry import Polygon, box as _box
    from shapely.geometry.polygon import orient
except Exception:  # pragma: no cover - exercised only on broken installs
    shapely = None

GRID = 1_000_000  # coordinates are welded on a 1 micron grid
CLEARANCE_MM = 4.0  # purge line / skirt room kept free on the bed


@dataclass(frozen=True)
class Tile:
    row: int  # 1 = top of the plate as seen from above
    col: int  # 1 = left
    x0: float
    x1: float
    y0: float
    y1: float

    @property
    def name(self) -> str:
        return f"r{self.row}c{self.col}"


def plan_tiles(config: PlateConfig) -> list[Tile]:
    """One tile per bed-sized piece; a single tile means no splitting is needed."""
    width, height = config.width_mm, config.height_mm
    if config.bed_mm <= 0:
        return [Tile(1, 1, 0.0, width, 0.0, height)]
    usable = max(10.0, config.bed_mm - CLEARANCE_MM)
    cols = max(1, math.ceil(width / usable - 1e-9))
    rows = max(1, math.ceil(height / usable - 1e-9))
    tiles = []
    for row in range(rows):
        for col in range(cols):
            # plate y grows upward in the mesh, so row 1 is the highest slice
            y1 = height - row * height / rows
            tiles.append(Tile(row + 1, col + 1, col * width / cols, (col + 1) * width / cols,
                              y1 - height / rows, y1))
    return tiles


def _need_shapely() -> None:
    if shapely is None:
        raise MeshUnavailable("shapely is not installed: pip install shapely")
    if not hasattr(shapely, "constrained_delaunay_triangles"):
        raise MeshUnavailable("shapely >= 2.1 is required: pip install -U shapely")


def layer_solid(layer: PlateLayer, config: PlateConfig):
    """The raised area of a plate as shapely geometry in plate millimetres (x right, y up)."""
    _need_shapely()
    width, height = config.width_mm, config.height_mm
    tolerance = max(0.012, min(0.04, config.curve_tolerance_mm * 0.35))

    def mapped(poly: np.ndarray) -> np.ndarray:
        x = width - poly[:, 0] if config.mirror_for_print else poly[:, 0]
        return np.column_stack((x, height - poly[:, 1]))

    polygons = []
    for region in layer.regions:
        outer = _flatten(region.outer, tolerance)
        if len(outer) < 3:
            continue
        holes = [h for h in (_flatten(hole, tolerance) for hole in region.holes) if len(h) >= 3]
        polygon = Polygon(mapped(outer), [mapped(h) for h in holes])
        if not polygon.is_valid:
            polygon = shapely.make_valid(polygon)
        polygons.append(polygon)
    if not polygons:
        raise RuntimeError("no printable regions to mesh")
    return shapely.union_all(polygons)


def _polygons(geometry) -> list:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    parts = getattr(geometry, "geoms", [])
    out = []
    for part in parts:
        out.extend(_polygons(part))
    return out


def _rings(polygon) -> list[np.ndarray]:
    """Integer micron rings (no repeated end point); the exterior first."""
    polygon = orient(polygon, 1.0)
    rings = [np.rint(np.asarray(r.coords)[:-1] * GRID).astype(np.int64) for r in (polygon.exterior, *polygon.interiors)]
    return [r for r in rings if len(r) >= 3]


def mesh_from_solid(solid, width: float, height: float, base: float, top: float) -> tuple[np.ndarray, np.ndarray]:
    """Closed prism mesh: bottom at z=0, floor at ``base``, raised ``solid`` at ``top``.

    ``solid`` must lie inside the rectangle ``[0, width] x [0, height]``.
    """
    _need_shapely()
    w_i, h_i = int(round(width * GRID)), int(round(height * GRID))
    frame = _box(0, 0, w_i / GRID, h_i / GRID)
    solid = shapely.set_precision(solid.intersection(frame), 1 / GRID)
    solid = shapely.set_precision(solid.simplify(0), 1 / GRID)
    floor = shapely.set_precision(frame.difference(solid), 1 / GRID)
    raised = [p for p in _polygons(solid) if p.area > 1e-8]
    flat = [p for p in _polygons(floor) if p.area > 1e-8]
    if not raised and not flat:
        raise RuntimeError("tile is empty")

    stride = h_i + 1
    big = (w_i + 1) * stride

    def key(xy: np.ndarray, level: int) -> np.ndarray:
        return level * big + xy[:, 0] * stride + xy[:, 1]

    def on_edge(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return ((a[:, 0] == 0) & (b[:, 0] == 0)) | ((a[:, 0] == w_i) & (b[:, 0] == w_i)) | \
               ((a[:, 1] == 0) & (b[:, 1] == 0)) | ((a[:, 1] == h_i) & (b[:, 1] == h_i))

    tris: list[np.ndarray] = []
    perimeter: set[tuple[int, int]] = {(0, 0), (w_i, 0), (w_i, h_i), (0, h_i)}

    def face(polygon, level: int) -> None:
        # Constrained Delaunay keeps every ring vertex and never emits zero-area slivers
        # (ear clipping does when vertices of different rings are collinear, e.g. a row of bars).
        parts = shapely.get_parts(shapely.constrained_delaunay_triangles(polygon))
        if not len(parts):
            raise RuntimeError("polygon triangulation produced no triangles")
        corners = shapely.get_coordinates(parts).reshape(-1, 4, 2)[:, :3, :]
        ints = np.rint(corners * GRID).astype(np.int64)
        a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
        cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        keys = (level * big + ints[:, :, 0] * stride + ints[:, :, 1])
        keys[cross < 0] = keys[cross < 0][:, ::-1]
        tris.append(keys)

    def quad(a: np.ndarray, b: np.ndarray, low_level: int, high_level: int) -> None:
        a0, b0, a1, b1 = key(a, low_level), key(b, low_level), key(a, high_level), key(b, high_level)
        tris.append(np.stack((a0, b0, b1), axis=1))
        tris.append(np.stack((a0, b1, a1), axis=1))

    def wall(ring: np.ndarray, low_level: int, high_level: int, only_edge: bool) -> None:
        nxt = np.roll(ring, -1, axis=0)
        edge = on_edge(ring, nxt)
        for x, y in np.vstack((ring[edge], nxt[edge])).tolist():
            perimeter.add((x, y))
        pick = edge if only_edge else np.ones(len(ring), bool)
        quad(ring[pick], nxt[pick], low_level, high_level)
        if not only_edge and edge.any():
            # Raised area on the outer rectangle: also a wall down to the bottom, split at the
            # floor level so it meets the floor's own wall without a T-junction.
            quad(ring[edge], nxt[edge], 0, low_level)

    for polygon in raised:
        face(polygon, 2)
        for ring in _rings(polygon):
            wall(ring, 1, 2, only_edge=False)
    for polygon in flat:
        face(polygon, 1)
        for ring in _rings(polygon):
            wall(ring, 0, 1, only_edge=True)

    # Bottom: a fan around an interior point keeps every perimeter node in the mesh.
    def along(p: tuple[int, int]) -> int:
        x, y = p
        if y == 0:
            return x
        if x == w_i:
            return w_i + y
        if y == h_i:
            return w_i + h_i + (w_i - x)
        return 2 * w_i + h_i + (h_i - y)

    ring = np.array(sorted(perimeter, key=along), dtype=np.int64)
    centre = np.array([[w_i // 2, h_i // 2]], dtype=np.int64)
    nxt = np.roll(ring, -1, axis=0)
    c_key = np.full(len(ring), key(centre, 0)[0])
    tris.append(np.stack((c_key, key(nxt, 0), key(ring, 0)), axis=1))  # reversed so it faces down

    keys = np.vstack(tris)
    unique, inverse = np.unique(keys.ravel(), return_inverse=True)
    level = unique // big
    rest = unique % big
    z_levels = np.array([0.0, base, top])
    vertices = np.column_stack((rest // stride / GRID, rest % stride / GRID, z_levels[level])).astype(np.float32)
    return vertices, inverse.reshape(-1, 3).astype(np.uint32)


def build_tile_mesh(solid, tile: Tile, config: PlateConfig) -> tuple[np.ndarray, np.ndarray]:
    base, top = config.base_height_mm, config.base_height_mm + config.relief_height_mm
    window = _box(tile.x0, tile.y0, tile.x1, tile.y1)
    local = shapely.affinity.translate(solid.intersection(window), -tile.x0, -tile.y0)
    return mesh_from_solid(local, tile.x1 - tile.x0, tile.y1 - tile.y0, base, top)


def write_zip(path: Path, files: list[Path]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in files:
            archive.write(item, item.name)
    temporary.replace(path)
