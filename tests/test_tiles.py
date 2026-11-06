import tempfile
from dataclasses import replace
import unittest
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Point, box

from curvepress.config import PlateConfig
from curvepress.exporter import _mesh_stats, build_closed_mesh, export_layer, export_meshes
from curvepress.mesh import mesh_volume
from curvepress.pipeline import analyze_image
from curvepress.testplate import GAPS, LINE_WIDTHS, build_plate_solid, write_test_plate
from curvepress.tiles import mesh_from_solid, plan_tiles


def closed(vertices, triangles):
    stats = _mesh_stats(vertices, triangles)
    return stats["mesh_boundary_edges"] == 0 and stats["mesh_nonmanifold_edges"] == 0


class PlanTests(unittest.TestCase):
    def test_no_bed_means_one_tile(self):
        self.assertEqual(len(plan_tiles(PlateConfig(width_mm=250, height_mm=200).resolved())), 1)

    def test_tiles_cover_the_plate_and_fit_the_bed(self):
        config = PlateConfig(width_mm=256, height_mm=180, bed_mm=180).resolved()
        tiles = plan_tiles(config)
        self.assertEqual((len({t.col for t in tiles}), len({t.row for t in tiles})), (2, 2))
        self.assertAlmostEqual(sum((t.x1 - t.x0) * (t.y1 - t.y0) for t in tiles), 256 * 180)
        self.assertTrue(all(t.x1 - t.x0 <= 176 + 1e-9 and t.y1 - t.y0 <= 176 + 1e-9 for t in tiles))
        self.assertEqual(tiles[0].name, "r1c1")
        self.assertGreater(tiles[0].y1, tiles[-1].y1)  # r1 is the top row

    def test_plate_that_fits_is_not_split(self):
        self.assertEqual(len(plan_tiles(PlateConfig(width_mm=150, height_mm=100, bed_mm=180).resolved())), 1)

    def test_bed_range_is_validated(self):
        with self.assertRaises(ValueError):
            PlateConfig(bed_mm=20).resolved()


class MeshTests(unittest.TestCase):
    def test_random_shapes_crossing_the_edges_stay_closed_with_exact_volume(self):
        rng = np.random.default_rng(7)
        for _ in range(40):
            solid = None
            for _ in range(10):
                disc = Point(rng.uniform(-3, 23), rng.uniform(-3, 15)).buffer(rng.uniform(0.5, 4), 8)
                solid = disc if solid is None else solid.union(disc)
            solid = solid.difference(Point(10, 6).buffer(1.5)).union(box(2, 3, 5, 3.3)).union(box(2, 4, 5, 4.3))
            vertices, triangles = mesh_from_solid(solid, 20, 12, 1.0, 2.0)
            expected = 20 * 12 + solid.intersection(box(0, 0, 20, 12)).area
            self.assertTrue(closed(vertices, triangles))
            self.assertAlmostEqual(mesh_volume(vertices, triangles), expected, delta=expected * 1e-3)


class TileExportTests(unittest.TestCase):
    def analyzed(self, directory, **settings):
        image = Image.new("RGB", (200, 120), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((30, 20, 170, 100), fill="black")
        draw.rectangle((90, 5, 110, 115), fill="white")
        config = PlateConfig(style="poster", width_mm=100, height_mm=60, base_height_mm=1.0, relief_height_mm=0.8, **settings).resolved()
        path = Path(directory) / "in.png"
        image.save(path)
        return analyze_image(path.read_bytes(), config, Path(directory) / "out"), config

    def test_tiles_add_up_to_the_whole_plate(self):
        with tempfile.TemporaryDirectory() as temp:
            result, whole = self.analyzed(temp)
            vertices, triangles = build_closed_mesh(result.layers[0], whole)
            reference = mesh_volume(vertices, triangles)
            tiled = replace(whole, bed_mm=60.0).resolved()
            report = export_layer(result.layers[0], tiled, Path(temp) / "out")
            self.assertEqual(report["tiles"], 4)  # 100 and 60 mm against a 56 mm usable bed -> 2 x 2
            self.assertAlmostEqual(report["mesh_volume_mm3"], reference, delta=reference * 0.005)
            names = report["files"]
            self.assertEqual(sum(n.endswith(".stl") for n in names), 4)
            with zipfile.ZipFile(Path(temp) / "out" / next(n for n in names if n.endswith("_stl_tiles.zip"))) as archive:
                self.assertEqual(len(archive.namelist()), 4)

    def test_export_meshes_writes_tiles_when_a_bed_is_set(self):
        with tempfile.TemporaryDirectory() as temp:
            result, whole = self.analyzed(temp)
            tiled = replace(whole, bed_mm=60.0).resolved()
            names = export_meshes(result, tiled)
            self.assertTrue(any(n.endswith("_3mf_tiles.zip") for n in names))
            self.assertTrue(any(n.endswith("_r2c2.stl") for n in names))


class TestPlateTests(unittest.TestCase):
    def test_plate_is_written_and_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            files = write_test_plate(Path(temp), PlateConfig().resolved())
            self.assertEqual({f.suffix for f in files}, {".stl", ".3mf", ".md"})
            self.assertIn("0.2", files[-1].read_text(encoding="utf-8"))

    def test_every_gap_and_line_is_present_in_the_geometry(self):
        solid = build_plate_solid()
        widths = sorted(round(g.bounds[2] - g.bounds[0], 3) for g in solid.geoms if g.bounds[3] - g.bounds[1] > 15 and g.bounds[1] > 39)
        self.assertEqual(widths, sorted(LINE_WIDTHS))
        row2 = sorted(g.bounds[0] for g in solid.geoms if 21 < g.bounds[1] < 23)
        gaps = [round(b - a - 1.0, 3) for a, b in zip(row2[0::2], row2[1::2])] if len(row2) == 12 else []
        self.assertEqual(gaps, sorted(GAPS))


if __name__ == "__main__":
    unittest.main()
