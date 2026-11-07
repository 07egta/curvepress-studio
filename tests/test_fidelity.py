"""Fidelity regressions: where the plate puts an edge, and how stable it is across resolutions."""
import io

import numpy as np
from PIL import Image, ImageDraw

from curvepress.config import PlateConfig
from curvepress.curves import contour_regions
from curvepress.image_pipeline import choose_ppm
from curvepress.pipeline import analyze_image


def test_contour_edges_land_on_the_pixel_grid_not_half_a_pixel_off():
    for ppm in (6, 9, 12):
        config = PlateConfig(width_mm=100, height_mm=60, analysis_ppm=ppm).resolved()
        mask = np.zeros((60 * ppm, 100 * ppm), bool)
        mask[10 * ppm:20 * ppm, 20 * ppm:50 * ppm] = True  # exactly x 20..50 mm, y 10..20 mm
        outer = contour_regions(mask, config)[0].outer
        assert abs(outer[:, 0].min() - 20) < 0.02 and abs(outer[:, 0].max() - 50) < 0.02
        assert abs(outer[:, 1].min() - 10) < 0.02 and abs(outer[:, 1].max() - 20) < 0.02


def test_auto_resolution_follows_the_source_and_respects_the_budget():
    config = PlateConfig(width_mm=100, height_mm=60).resolved()
    assert choose_ppm(Image.new("RGB", (400, 240)), config) == 6          # small source: never below 6
    assert choose_ppm(Image.new("RGB", (3000, 1800)), config) == 12       # sharp source: up to 12
    huge = PlateConfig(width_mm=256, height_mm=256).resolved()
    assert 6 <= choose_ppm(Image.new("RGB", (6000, 6000)), huge) <= 9     # big plate: pixel budget
    assert choose_ppm(Image.new("RGB", (3000, 1800)), PlateConfig(analysis_ppm=7).resolved()) == 7


def test_plate_matches_a_drawn_shape_to_a_fraction_of_a_pixel(tmp_path):
    ppm_source = 20
    image = Image.new("RGB", (96 * ppm_source, 56 * ppm_source), "white")  # 2 mm margin all round on 100 x 60
    ImageDraw.Draw(image).rectangle((20 * ppm_source, 10 * ppm_source, 60 * ppm_source - 1, 30 * ppm_source - 1), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    config = PlateConfig(width_mm=100, height_mm=60, style="poster", remove_scan_frame=False).resolved()
    result = analyze_image(buffer.getvalue(), config, tmp_path, defer_proof=True)
    assert result.metrics["resolution"]["px_per_mm"] == 12
    outer = result.layers[0].regions[0].outer
    # source rectangle spans 20..60 mm and 10..30 mm of the 96 x 56 mm artwork, offset by the 2 mm margin
    assert abs(outer[:, 0].min() - 22) < 0.12 and abs(outer[:, 0].max() - 62) < 0.12
    assert abs(outer[:, 1].min() - 12) < 0.12 and abs(outer[:, 1].max() - 32) < 0.12


def test_thin_lines_are_not_inflated_at_high_resolution(tmp_path):
    """A global dilation used to widen every edge by 0.08 mm per side at 12 px/mm."""
    widths = {}
    for ppm in (6, 12):
        image = Image.new("RGB", (720, 400), "white")
        ImageDraw.Draw(image).rectangle((100, 100, 100 + 59, 180), fill="black")  # 59 px = 2.95 mm at 20 px/mm
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        config = PlateConfig(width_mm=40, height_mm=24, style="poster", analysis_ppm=ppm, remove_scan_frame=False, edge_margin_mm=2).resolved()
        outer = analyze_image(buffer.getvalue(), config, tmp_path, defer_proof=True).layers[0].regions[0].outer
        widths[ppm] = outer[:, 0].max() - outer[:, 0].min()
    assert abs(widths[6] - widths[12]) < 0.1
