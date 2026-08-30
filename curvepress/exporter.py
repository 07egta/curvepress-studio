from __future__ import annotations

import json
import struct
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

from .config import PlateConfig
from .curves import cubic_segments, signed_area
from .models import AnalysisResult, CurveRegion, PlateLayer


class CadUnavailable(RuntimeError):
    pass


def _load_occ():
    try:
        from OCP.BRep import BRep_Builder
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
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
        from OCP.Geom import Geom_BezierCurve
        from OCP.GeomAPI import GeomAPI_Interpolate
        from OCP.gp import gp_Pnt, gp_Vec
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


def _face_for_region(
    region: CurveRegion,
    config: PlateConfig,
    z: float,
    occ,
    *,
    safe_bezier: bool,
):
    wire_builder = _bezier_wire if safe_bezier else _curve_wire
    face_maker = occ["BRepBuilderAPI_MakeFace"](
        wire_builder(region.outer, config, z, True, occ),
        True,
    )
    for hole in region.holes:
        face_maker.Add(wire_builder(hole, config, z, False, occ))
    if not face_maker.IsDone():
        return None
    face = face_maker.Face()
    return face if occ["BRepCheck_Analyzer"](face).IsValid() else None


def _make_relief(region: CurveRegion, config: PlateConfig, overlap: float, occ):
    z = config.base_height_mm - overlap
    face = _face_for_region(region, config, z, occ, safe_bezier=False)
    if face is None:
        face = _face_for_region(region, config, z, occ, safe_bezier=True)
    if face is None:
        raise RuntimeError("artwork face is invalid after B-spline and safe-Bezier fitting")
    solid = occ["BRepPrimAPI_MakePrism"](
        face, occ["gp_Vec"](0.0, 0.0, config.relief_height_mm + overlap)
    ).Shape()
    if not occ["BRepCheck_Analyzer"](solid).IsValid():
        raise RuntimeError("extruded artwork is invalid")
    return solid


def _compound(shapes, occ):
    result = occ["TopoDS_Compound"]()
    builder = occ["BRep_Builder"]()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def build_occ_solid(layer: PlateLayer, config: PlateConfig):
    occ = _load_occ()
    if len(layer.regions) > 1600:
        raise RuntimeError(
            "This layer has more than 1,600 separate regions. STEP is intentionally blocked "
            "to avoid a huge, fragile CAD file; use 3MF/STL or increase cleanup."
        )
    overlap = min(0.03, config.layer_height_mm * 0.10)
    reliefs = []
    for index, region in enumerate(layer.regions, start=1):
        try:
            reliefs.append(_make_relief(region, config, overlap, occ))
        except Exception as exc:
            raise RuntimeError(f"region {index}/{len(layer.regions)}: {exc}") from exc
    base = occ["BRepPrimAPI_MakeBox"](
        config.width_mm, config.height_mm, config.base_height_mm
    ).Shape()
    fuse = occ["BRepAlgoAPI_Fuse"](base, _compound(reliefs, occ))
    fuse.SetFuzzyValue(0.01)
    if hasattr(fuse, "SetRunParallel"):
        fuse.SetRunParallel(True)
    fuse.Build()
    if not fuse.IsDone() or fuse.Shape().IsNull():
        raise RuntimeError("OpenCascade boolean fuse failed")
    control_vertices = sum(
        len(region.outer) + sum(len(hole) for hole in region.holes)
        for region in layer.regions
    )
    # Unifying thousands of already smooth curve edges can dominate runtime
    # without changing print geometry.  Keep it for ordinary designs and skip
    # it for dense engravings; STEP read-back validation still applies to both.
    if hasattr(fuse, "SimplifyResult") and control_vertices <= 2_500:
        fuse.SimplifyResult(True, True)
    shape = fuse.Shape()
    if not occ["BRepCheck_Analyzer"](shape).IsValid() or _count_solids(shape, occ) != 1:
        raise RuntimeError("result is not one valid CAD solid")
    return shape, occ


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
    count = struct.unpack_from("<I", raw, 80)[0]
    expected = 84 + count * 50
    if len(raw) != expected:
        raise RuntimeError("expected binary STL from OpenCascade")
    vertex_map: dict[tuple[float, float, float], int] = {}
    vertices: list[tuple[float, float, float]] = []
    triangles = np.empty((count, 3), dtype=np.uint32)
    offset = 84
    for face in range(count):
        values = struct.unpack_from("<12fH", raw, offset)
        offset += 50
        for corner in range(3):
            point = tuple(round(float(v), 6) for v in values[3 + corner * 3 : 6 + corner * 3])
            if point not in vertex_map:
                vertex_map[point] = len(vertices)
                vertices.append(point)
            triangles[face, corner] = vertex_map[point]
    return np.asarray(vertices, dtype=np.float32), triangles


def _write_3mf(path: Path, vertices: np.ndarray, triangles: np.ndarray) -> None:
    vertex_xml = "".join(
        f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in vertices
    )
    triangle_xml = "".join(
        f'<triangle v1="{int(a)}" v2="{int(b)}" v3="{int(c)}"/>' for a, b, c in triangles
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
    edges: Counter[tuple[int, int]] = Counter()
    for a, b, c in triangles:
        edges[tuple(sorted((int(a), int(b))))] += 1
        edges[tuple(sorted((int(b), int(c))))] += 1
        edges[tuple(sorted((int(c), int(a))))] += 1
    return {
        "mesh_vertices": int(len(vertices)),
        "mesh_triangles": int(len(triangles)),
        "mesh_boundary_edges": int(sum(value == 1 for value in edges.values())),
        "mesh_nonmanifold_edges": int(sum(value > 2 for value in edges.values())),
    }


def export_layer(layer: PlateLayer, config: PlateConfig, directory: Path) -> dict:
    stem = f"{config.title}_{layer.name}"
    svg_path = directory / f"{stem}.svg"
    svg_path.write_text(layer.svg, encoding="utf-8")
    shape, occ = build_occ_solid(layer, config)
    step_path = directory / f"{stem}.step"
    loaded = _write_step_and_read(shape, step_path, occ)

    mesher = occ["BRepMesh_IncrementalMesh"](loaded, 0.055, False, 0.25, True)
    mesher.Perform()
    if not mesher.IsDone():
        raise RuntimeError("OpenCascade tessellation failed")
    stl_path = directory / f"{stem}.stl"
    stl_writer = occ["StlAPI_Writer"]()
    stl_writer.ASCIIMode = False
    if not stl_writer.Write(loaded, str(stl_path)):
        raise RuntimeError("STL export failed")
    vertices, triangles = _read_binary_stl(stl_path)
    three_mf_path = directory / f"{stem}.3mf"
    _write_3mf(three_mf_path, vertices, triangles)
    stats = _mesh_stats(vertices, triangles)
    if stats["mesh_boundary_edges"] or stats["mesh_nonmanifold_edges"]:
        raise RuntimeError(f"exported mesh is not closed: {stats}")
    # Validate the read-back STEP through the mesh produced from that loaded
    # solid.  OCCT's analytic Bnd_Box can conservatively overestimate the Z
    # range of joined splines even when every generated vertex is exactly on
    # the planar top/bottom faces.
    bounds = (vertices.max(axis=0) - vertices.min(axis=0)).astype(float).tolist()
    expected = [config.width_mm, config.height_mm, config.base_height_mm + config.relief_height_mm]
    # Bnd_Box includes per-edge interpolation tolerance. The STEP solid itself
    # uses the designed base dimensions; allow the accumulated display gap.
    if any(abs(a - b) > 0.20 for a, b in zip(bounds, expected)):
        raise RuntimeError(f"CAD dimensions drifted: {bounds} vs {expected}")
    report = {
        "layer": layer.name,
        "step_read_back": True,
        "step_valid": True,
        "step_solids": 1,
        "dimensions_mm": expected,
        "read_back_mesh_bounds_mm": bounds,
        "regions": len(layer.regions),
        "holes": sum(len(region.holes) for region in layer.regions),
        **stats,
        "files": [svg_path.name, step_path.name, three_mf_path.name, stl_path.name],
    }
    report_path = directory / f"{stem}_validation.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["files"].append(report_path.name)
    return report


def export_analysis(result: AnalysisResult, raw_config: PlateConfig | dict) -> list[dict]:
    config = (
        raw_config.resolved()
        if isinstance(raw_config, PlateConfig)
        else PlateConfig.from_dict(raw_config)
    )
    reports = []
    for layer in result.layers:
        reports.append(export_layer(layer, config, result.directory))
    return reports

