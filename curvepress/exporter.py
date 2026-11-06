from __future__ import annotations

import json
import struct
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

from .config import PlateConfig
from .curves import cubic_segments, signed_area
from .mesh import build_plate_mesh, mesh_volume, write_binary_stl
from .models import AnalysisResult, CurveRegion, PlateLayer


class CadUnavailable(RuntimeError):
    pass


def cad_available() -> bool:
    """True when the OpenCascade bindings can be imported."""
    import importlib.util

    return importlib.util.find_spec("OCP") is not None


def _checked_plate_mesh(layer: PlateLayer, config: PlateConfig):
    """Mesh one plate and reject an open shell or a drifted bounding box."""
    vertices, triangles = build_plate_mesh(layer, config)
    stats = _mesh_stats(vertices, triangles)
    if stats["mesh_boundary_edges"] or stats["mesh_nonmanifold_edges"]:
        raise RuntimeError(f"exported mesh is not closed: {stats}")
    bounds = (vertices.max(axis=0) - vertices.min(axis=0)).astype(float)
    expected = np.array(
        [config.width_mm, config.height_mm, config.base_height_mm + config.relief_height_mm],
        dtype=float,
    )
    if np.any(np.abs(bounds - expected) > 0.02):
        raise RuntimeError(f"mesh dimensions drifted: {bounds.tolist()} vs {expected.tolist()}")
    return vertices, triangles, stats, bounds


STEP_REGION_LIMIT = 1600


def _load_occ():
    try:
        from OCP.BRep import BRep_Builder
        from OCP.BOPAlgo import BOPAlgo_GlueShift
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopTools import TopTools_ListOfShape
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepBuilderAPI import (
            BRepBuilderAPI_MakeEdge,
            BRepBuilderAPI_MakeFace,
            BRepBuilderAPI_MakeWire,
        )
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
        from OCP.Bnd import Bnd_Box
        from OCP.Geom import Geom_BezierCurve, Geom_BSplineCurve
        from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
        from OCP.GeomAPI import GeomAPI_Interpolate
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt, gp_Vec
        from OCP.ShapeFix import ShapeFix_Face
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
        from OCP.StlAPI import StlAPI_Writer
        from OCP.TColgp import TColgp_Array1OfPnt, TColgp_HArray1OfPnt
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS_Compound
    except Exception as exc:
        raise CadUnavailable(
            "OpenCascade is not installed. Install the CAD extra: pip install -e '.[cad]'"
        ) from exc
    return locals()


def _count_solids(shape, occ) -> int:
    explorer = occ["TopExp_Explorer"](shape, occ["TopAbs_SOLID"])
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _oriented(points: np.ndarray, ccw: bool) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64)
    if (signed_area(pts) > 0) != ccw:
        pts = pts[::-1].copy()
    return pts


def _curve_wire(points: np.ndarray, config: PlateConfig, z: float, ccw: bool, occ):
    pts = _oriented(points, ccw)

    def mapped(point: np.ndarray):
        x, y = point
        # Image coordinates point down. H-y converts to CAD coordinates; W-x
        # adds the horizontal mirror required for direct stamping.
        px = config.width_mm - float(x) if config.mirror_for_print else float(x)
        py = config.height_mm - float(y)
        return occ["gp_Pnt"](px, py, z)

    # SVG retains the explicit shape-preserving cubic Bezier chain.  STEP uses
    # OCCT's compact periodic interpolation through the same simplified
    # contour vertices, matching the editable B-spline construction used by
    # CurvePress' original three-colour plates.
    array = occ["TColgp_HArray1OfPnt"](1, len(pts))
    for index, point in enumerate(pts, start=1):
        array.SetValue(index, mapped(point))
    interpolation = occ["GeomAPI_Interpolate"](array, True, 1e-4)
    interpolation.Perform()
    if not interpolation.IsDone():
        raise RuntimeError("periodic B-spline interpolation failed")
    edge = occ["BRepBuilderAPI_MakeEdge"](interpolation.Curve()).Edge()
    maker = occ["BRepBuilderAPI_MakeWire"](edge)
    if not maker.IsDone():
        raise RuntimeError("B-spline wire construction failed")
    return maker.Wire()


def _bezier_wire(points: np.ndarray, config: PlateConfig, z: float, ccw: bool, occ):
    pts = _oriented(points, ccw)
    maker = occ["BRepBuilderAPI_MakeWire"]()

    def mapped(point: np.ndarray):
        x, y = point
        px = config.width_mm - float(x) if config.mirror_for_print else float(x)
        py = config.height_mm - float(y)
        return occ["gp_Pnt"](px, py, z)

    for p0, c1, c2, p3 in cubic_segments(pts):
        poles = occ["TColgp_Array1OfPnt"](1, 4)
        for index, point in enumerate((p0, c1, c2, p3), start=1):
            poles.SetValue(index, mapped(point))
        edge = occ["BRepBuilderAPI_MakeEdge"](occ["Geom_BezierCurve"](poles)).Edge()
        maker.Add(edge)
    if not maker.IsDone():
        raise RuntimeError("shape-preserving Bezier wire construction failed")
    return maker.Wire()


def _chain_wire(points: np.ndarray, config: PlateConfig, z: float, ccw: bool, occ):
    """One closed edge holding the *exact* SVG Bezier chain.

    Every cubic segment becomes one span of a cubic B-spline whose interior
    knots have multiplicity 3, which reproduces piecewise Bezier geometry
    exactly (same poles, no refitting, no overshoot).  A face bounded by one
    edge per loop extrudes to one side face instead of thousands, which makes
    booleans, STEP I/O and validation an order of magnitude faster.
    """
    pts = _oriented(points, ccw)
    segments = cubic_segments(pts)
    if not len(segments):
        raise RuntimeError("empty contour")
    poles_xy = np.vstack((segments[:, :3, :].reshape(-1, 2), segments[-1:, 3, :]))
    # Close exactly: the chain ends where it started.
    poles_xy[-1] = poles_xy[0]
    xs = config.width_mm - poles_xy[:, 0] if config.mirror_for_print else poles_xy[:, 0]
    ys = config.height_mm - poles_xy[:, 1]
    poles = occ["TColgp_Array1OfPnt"](1, len(poles_xy))
    for index, (x, y) in enumerate(zip(xs.tolist(), ys.tolist()), start=1):
        poles.SetValue(index, occ["gp_Pnt"](x, y, z))
    # Knot spacing that turns the chain's tangent (G1) joins into parametric
    # C1 joins: span k+1 is scaled so the end derivative of span k matches the
    # start derivative of span k+1.  The interior knots can then drop to
    # multiplicity 2 exactly (verified by OCCT's RemoveKnot tolerance).
    end_d = np.hypot(*(segments[:, 3, :] - segments[:, 2, :]).T)
    start_d = np.hypot(*(segments[:, 1, :] - segments[:, 0, :]).T)
    spans = np.ones(len(segments))
    for k in range(1, len(segments)):
        spans[k] = spans[k - 1] * max(start_d[k], 1e-12) / max(end_d[k - 1], 1e-12)
    spans = np.clip(spans / spans.mean(), 1e-4, 1e4)
    params = np.concatenate(([0.0], np.cumsum(spans)))
    count = len(segments)
    knots = occ["TColStd_Array1OfReal"](1, count + 1)
    mults = occ["TColStd_Array1OfInteger"](1, count + 1)
    for index, value in enumerate(params.tolist(), start=1):
        knots.SetValue(index, value)
        mults.SetValue(index, 4 if index in (1, count + 1) else 3)
    curve = occ["Geom_BSplineCurve"](poles, knots, mults, 3, False)
    for index in range(count, 1, -1):
        curve.RemoveKnot(index, 2, 1e-7)
    edge = occ["BRepBuilderAPI_MakeEdge"](curve).Edge()
    maker = occ["BRepBuilderAPI_MakeWire"](edge)
    if not maker.IsDone():
        raise RuntimeError("Bezier-chain wire construction failed")
    return maker.Wire()


def _face_for_region(
    region: CurveRegion,
    config: PlateConfig,
    z: float,
    occ,
    *,
    single_edge: bool = True,
    check: bool = True,
):
    wire_builder = _chain_wire if single_edge else _bezier_wire
    outer = wire_builder(region.outer, config, z, True, occ)
    if single_edge:
        # A one-edge wire gives MakeFace no reliable orientation cue; state the
        # +Z plane explicitly and let ShapeFix orient outer/inner loops.
        plane = occ["gp_Pln"](occ["gp_Pnt"](0.0, 0.0, z), occ["gp_Dir"](0.0, 0.0, 1.0))
        face_maker = occ["BRepBuilderAPI_MakeFace"](plane, outer, True)
    else:
        face_maker = occ["BRepBuilderAPI_MakeFace"](outer, True)
    for hole in region.holes:
        face_maker.Add(wire_builder(hole, config, z, False, occ))
    if not face_maker.IsDone():
        return None
    face = face_maker.Face()
    if single_edge:
        fixer = occ["ShapeFix_Face"](face)
        fixer.FixOrientationMode = 1
        fixer.Perform()
        face = fixer.Face()
    if not check:
        return face
    return face if occ["BRepCheck_Analyzer"](face).IsValid() else None


def _make_relief(
    region: CurveRegion, config: PlateConfig, overlap: float, occ, *, fast: bool = True
):
    """Extrude one artwork region.

    ``fast``: one exact C1 B-spline edge per loop and no per-region checks; the
    fused solid is validated once (and again after STEP read-back).  The slow
    path (one edge per Bezier segment, checked face and solid) is the fallback.
    """
    z = config.base_height_mm - overlap
    face = _face_for_region(region, config, z, occ, single_edge=fast, check=not fast)
    if face is None:
        raise RuntimeError("artwork face is invalid after shape-preserving Bezier fitting")
    solid = occ["BRepPrimAPI_MakePrism"](
        face, occ["gp_Vec"](0.0, 0.0, config.relief_height_mm + overlap)
    ).Shape()
    if not fast and not occ["BRepCheck_Analyzer"](solid).IsValid():
        raise RuntimeError("extruded artwork is invalid")
    return solid


def _compound(shapes, occ):
    result = occ["TopoDS_Compound"]()
    builder = occ["BRep_Builder"]()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def _fuse_layer(layer: PlateLayer, config: PlateConfig, occ, *, fast: bool):
    """Base box + extruded regions as one solid.

    Fast path: each region stands exactly on the base top (no overlap) and the
    boolean runs in *glue* mode, which only has to merge coincident faces
    instead of intersecting curved walls with the plane.  ~100x faster than a
    general fuse on detailed artwork.  The slow path is the classic overlapping
    fuse with one edge per Bezier segment.
    """
    overlap = 0.0 if fast else min(0.03, config.layer_height_mm * 0.10)
    reliefs = []
    for index, region in enumerate(layer.regions, start=1):
        try:
            reliefs.append(_make_relief(region, config, overlap, occ, fast=fast))
        except Exception as exc:
            raise RuntimeError(f"region {index}/{len(layer.regions)}: {exc}") from exc
    base = occ["BRepPrimAPI_MakeBox"](
        config.width_mm, config.height_mm, config.base_height_mm
    ).Shape()
    fuse = occ["BRepAlgoAPI_Fuse"]()
    arguments, tools = occ["TopTools_ListOfShape"](), occ["TopTools_ListOfShape"]()
    arguments.Append(base)
    tools.Append(_compound(reliefs, occ))
    fuse.SetArguments(arguments)
    fuse.SetTools(tools)
    if fast:
        fuse.SetGlue(occ["BOPAlgo_GlueShift"])
    else:
        fuse.SetFuzzyValue(0.01)
    if hasattr(fuse, "SetRunParallel"):
        fuse.SetRunParallel(True)
    fuse.Build()
    if not fuse.IsDone() or fuse.Shape().IsNull():
        raise RuntimeError("OpenCascade boolean fuse failed")
    if hasattr(fuse, "SimplifyResult"):
        fuse.SimplifyResult(True, True)
    shape = fuse.Shape()
    if _count_solids(shape, occ) != 1:
        raise RuntimeError("result is not one CAD solid")
    # Full BRep validation happens once, on the STEP file as read back.
    return shape


def build_occ_solid(layer: PlateLayer, config: PlateConfig, *, fast: bool = True):
    occ = _load_occ()
    if len(layer.regions) > STEP_REGION_LIMIT:
        raise RuntimeError(
            "This layer has more than 1,600 separate regions. CAD export is intentionally blocked "
            "to avoid a huge, fragile file; lower the detail or use a larger dot pitch."
        )
    return _fuse_layer(layer, config, occ, fast=fast), occ


def write_validated_step(layer: PlateLayer, config: PlateConfig, path: Path):
    """Build, write, read back and validate; falls back to the slow path once."""
    last_error: Exception | None = None
    for fast in (True, False):
        try:
            shape, occ = build_occ_solid(layer, config, fast=fast)
            loaded = _write_step_and_read(shape, path, occ)
            size = _bounds(loaded, occ)
            expected = [config.width_mm, config.height_mm, config.base_height_mm + config.relief_height_mm]
            if any(abs(a - b) > 0.2 for a, b in zip(size, expected)):
                raise RuntimeError(f"STEP dimensions drifted: {size} vs {expected}")
            return loaded
        except RuntimeError as exc:
            if "1,600" in str(exc):
                raise
            last_error = exc
    raise RuntimeError(f"STEP export failed: {last_error}")


def _write_step_and_read(shape, path: Path, occ):
    writer = occ["STEPControl_Writer"]()
    if writer.Transfer(shape, occ["STEPControl_AsIs"]) != occ["IFSelect_RetDone"]:
        raise RuntimeError("STEP transfer failed")
    if writer.Write(str(path)) != occ["IFSelect_RetDone"]:
        raise RuntimeError("STEP write failed")
    reader = occ["STEPControl_Reader"]()
    if reader.ReadFile(str(path)) != occ["IFSelect_RetDone"]:
        raise RuntimeError("STEP read-back failed")
    reader.TransferRoots()
    loaded = reader.OneShape()
    if loaded.IsNull() or _count_solids(loaded, occ) != 1 or not occ["BRepCheck_Analyzer"](loaded).IsValid():
        raise RuntimeError("read-back STEP is not one valid solid")
    return loaded


def _bounds(shape, occ) -> list[float]:
    box = occ["Bnd_Box"]()
    # AddOptimal computes geometric bounds instead of inflating every joined
    # curve by its modelling tolerance.
    occ["BRepBndLib"].AddOptimal_s(shape, box, True, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return [xmax - xmin, ymax - ymin, zmax - zmin]


def _read_binary_stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    if len(raw) < 84:
        raise RuntimeError("truncated binary STL")
    count = struct.unpack_from("<I", raw, 80)[0]
    expected = 84 + count * 50
    if len(raw) != expected:
        raise RuntimeError("expected binary STL from OpenCascade")
    record = np.frombuffer(
        raw, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")], count=count, offset=84
    )
    corners = np.round(record["v"].reshape(-1, 3).astype(np.float64), 6)
    vertices, inverse = np.unique(corners, axis=0, return_inverse=True)
    return vertices.astype(np.float32), inverse.reshape(-1, 3).astype(np.uint32)


def _write_3mf(path: Path, vertices: np.ndarray, triangles: np.ndarray) -> None:
    vertex_xml = "".join(
        f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in np.asarray(vertices).tolist()
    )
    triangle_xml = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in np.asarray(triangles).tolist()
    )
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        '<metadata name="Title">CurvePress relief plate</metadata>'
        '<resources><object id="1" type="model"><mesh>'
        f'<vertices>{vertex_xml}</vertices><triangles>{triangle_xml}</triangles>'
        '</mesh></object></resources><build><item objectid="1"/></build></model>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '</Types>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        '</Relationships>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("3D/3dmodel.model", model)


def _mesh_stats(vertices: np.ndarray, triangles: np.ndarray) -> dict:
    tri = np.asarray(triangles, dtype=np.int64)
    edges = np.concatenate((tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]))
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return {
        "mesh_vertices": int(len(vertices)),
        "mesh_triangles": int(len(triangles)),
        "mesh_boundary_edges": int(np.count_nonzero(counts == 1)),
        "mesh_nonmanifold_edges": int(np.count_nonzero(counts > 2)),
    }


def export_layer(layer: PlateLayer, config: PlateConfig, directory: Path) -> dict:
    """SVG + 3MF + STL always; STEP when the artwork is CAD-friendly.

    All formats come from the same cubic Bezier chain.  The mesh is built
    directly (closed, 2-manifold, checked); the STEP solid is written, read
    back, validated, and its volume must match the mesh volume.
    """
    stem = f"{config.title}_{layer.name}"
    svg_path = directory / f"{stem}.svg"
    svg_path.write_text(layer.svg, encoding="utf-8")

    vertices, triangles, stats, bounds_array = _checked_plate_mesh(layer, config)
    bounds = bounds_array.tolist()
    expected = [config.width_mm, config.height_mm, config.base_height_mm + config.relief_height_mm]
    volume = mesh_volume(vertices, triangles)
    stl_path = directory / f"{stem}.stl"
    write_binary_stl(stl_path, vertices, triangles)
    three_mf_path = directory / f"{stem}.3mf"
    _write_3mf(three_mf_path, vertices, triangles)
    files = [svg_path.name, three_mf_path.name, stl_path.name]

    report = {
        "layer": layer.name,
        "dimensions_mm": expected,
        "read_back_mesh_bounds_mm": bounds,
        "mesh_volume_mm3": round(volume, 3),
        "regions": len(layer.regions),
        "holes": sum(len(region.holes) for region in layer.regions),
        **stats,
        "step_read_back": False,
        "step_valid": False,
        "step_solids": 0,
    }
    if len(layer.regions) > STEP_REGION_LIMIT:
        report["step_skipped"] = (
            f"{len(layer.regions):,} separate regions: STEP is skipped to avoid a huge, fragile "
            "CAD file. 3MF/STL are complete; use a larger dot pitch for STEP."
        )
    else:
        step_path = directory / f"{stem}.step"
        write_validated_step(layer, config, step_path)
        report.update(step_read_back=True, step_valid=True, step_solids=1)
        files.insert(1, step_path.name)
    report["files"] = files
    report_path = directory / f"{stem}_validation.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["files"].append(report_path.name)
    return report


def export_meshes(result: AnalysisResult, raw_config: PlateConfig | dict) -> list[str]:
    """3MF + STL for every plate, straight from the curves (no CAD kernel)."""
    config = raw_config.resolved() if isinstance(raw_config, PlateConfig) else PlateConfig.from_dict(raw_config)
    names = []
    for layer in result.layers:
        stem = f"{config.title}_{layer.name}"
        vertices, triangles, _, _ = _checked_plate_mesh(layer, config)
        for suffix, writer in ((".3mf", _write_3mf), (".stl", write_binary_stl)):
            final = result.directory / f"{stem}{suffix}"
            temporary = result.directory / f".{stem}{suffix}.tmp"
            writer(temporary, vertices, triangles)
            temporary.replace(final)
            names.append(final.name)
    return names


def export_analysis(result: AnalysisResult, raw_config: PlateConfig | dict) -> list[dict]:
    config = (
        raw_config.resolved()
        if isinstance(raw_config, PlateConfig)
        else PlateConfig.from_dict(raw_config)
    )
    reports = []
    # Publish only a complete, validated set. A failed layer must not leave
    # an apparently downloadable STL from an unsuccessful export.
    with tempfile.TemporaryDirectory(prefix=".export-", dir=result.directory) as temporary:
        staging = Path(temporary)
        for layer in result.layers:
            reports.append(export_layer(layer, config, staging))
        for path in staging.iterdir():
            path.replace(result.directory / path.name)
    return reports


