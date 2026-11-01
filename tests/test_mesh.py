"""Direct plate meshes: closed, exact size, and the same shape as the curves."""
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from curvepress.config import PlateConfig
from curvepress.curves import sample_segments, cubic_segments, signed_area
from curvepress.exporter import _mesh_stats, _read_binary_stl
from curvepress.mesh import build_plate_mesh, mesh_volume, write_binary_stl
from curvepress.pipeline import analyze_image


def _art() -> bytes:
    image = Image.new("RGB", (360, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 30, 200, 200), fill="black")
    draw.ellipse((80, 80, 150, 150), fill="white")       # a hole
    draw.ellipse((102, 102, 128, 128), fill="black")     # an island inside the hole
    draw.rectangle((230, 40, 330, 200), fill=(40, 40, 40))
    draw.line((230, 220, 330, 220), fill="black", width=4)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


@pytest.mark.parametrize("style", ["woodcut", "line_art", "poster", "halftone", "color_layers"])
def test_every_style_meshes_closed_and_exact(tmp_path, style):
    config = PlateConfig.from_dict({"style": style, "width_mm": 60, "height_mm": 40, "color_count": 2})
    result = analyze_image(_art(), config, tmp_path, defer_proof=True)
    for layer in result.layers:
        vertices, triangles = build_plate_mesh(layer, config)
        stats = _mesh_stats(vertices, triangles)
        assert stats["mesh_boundary_edges"] == 0
        assert stats["mesh_nonmanifold_edges"] == 0
        size = vertices.max(0) - vertices.min(0)
        np.testing.assert_allclose(size, [60, 40, config.base_height_mm + config.relief_height_mm], atol=1e-4)
        # Volume = base slab + curve area x relief height (area from dense curve samples).
        area = 0.0
        for region in layer.regions:
            area += abs(signed_area(sample_segments(cubic_segments(region.outer), 24)))
            area -= sum(abs(signed_area(sample_segments(cubic_segments(h), 24))) for h in region.holes)
        expected = 60 * 40 * config.base_height_mm + area * config.relief_height_mm
        assert mesh_volume(vertices, triangles) == pytest.approx(expected, rel=2e-3)


def test_island_inside_hole_is_raised(tmp_path):
    config = PlateConfig.from_dict({"style": "poster", "width_mm": 60, "height_mm": 40, "mirror_for_print": False})
    result = analyze_image(_art(), config, tmp_path, defer_proof=True)
    vertices, triangles = build_plate_mesh(result.layers[0], config)
    top = config.base_height_mm + config.relief_height_mm
    # The tiny island at the centre of the ring must reach the top surface.
    island = vertices[(np.abs(vertices[:, 2] - top) < 1e-6)]
    x0, y0 = 115 / 360 * 60, 40 - 115 / 240 * 40  # image centre of the island -> plate mm
    near = np.hypot(island[:, 0] - x0, island[:, 1] - y0) < 2.5
    assert near.any()


def test_stl_round_trip(tmp_path):
    config = PlateConfig.from_dict({"style": "poster", "width_mm": 60, "height_mm": 40})
    result = analyze_image(_art(), config, tmp_path, defer_proof=True)
    vertices, triangles = build_plate_mesh(result.layers[0], config)
    path = Path(tmp_path) / "plate.stl"
    write_binary_stl(path, vertices, triangles)
    v2, t2 = _read_binary_stl(path)
    assert len(t2) == len(triangles)
    assert mesh_volume(v2, t2) == pytest.approx(mesh_volume(vertices, triangles), rel=1e-6)
    assert _mesh_stats(v2, t2)["mesh_boundary_edges"] == 0
