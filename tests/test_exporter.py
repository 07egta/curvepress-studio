import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from curvepress.config import PlateConfig
from curvepress.exporter import _mesh_stats, _write_3mf, export_analysis
from curvepress.pipeline import analyze_image


class ExporterTests(unittest.TestCase):
    def test_mesh_edge_counter_and_3mf_container(self):
        vertices = np.array(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32
        )
        triangles = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.uint32)
        stats = _mesh_stats(vertices, triangles)
        self.assertEqual(stats["mesh_boundary_edges"], 0)
        self.assertEqual(stats["mesh_nonmanifold_edges"], 0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "tetra.3mf"
            _write_3mf(output, vertices, triangles)
            self.assertTrue(output.read_bytes().startswith(b"PK"))

    def test_optional_occ_round_trip(self):
        try:
            import OCP  # noqa: F401
        except ImportError:
            self.skipTest("CAD extra is not installed")
        image = Image.new("RGB", (260, 180), "white")
        ImageDraw.Draw(image).ellipse((55, 35, 205, 145), fill="black")
        raw = BytesIO()
        image.save(raw, format="PNG")
        with tempfile.TemporaryDirectory() as directory:
            config = PlateConfig(width_mm=50, height_mm=35, style="poster", analysis_ppm=4).resolved()
            result = analyze_image(raw.getvalue(), config, Path(directory))
            reports = export_analysis(result, config)
            self.assertEqual(reports[0]["step_solids"], 1)
            self.assertEqual(reports[0]["mesh_boundary_edges"], 0)
            self.assertEqual(reports[0]["mesh_nonmanifold_edges"], 0)
            self.assertEqual(reports[0]["read_back_mesh_bounds_mm"], [50.0, 35.0, 2.0])


if __name__ == "__main__":
    unittest.main()

