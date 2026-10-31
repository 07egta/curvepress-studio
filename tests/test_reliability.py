"""Regression coverage for settings, orientation, cleanup, and real CAD export."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from curvepress.config import PlateConfig
from curvepress.exporter import export_analysis
from curvepress.image_pipeline import correct_illumination, load_image
from curvepress.physical import _component_cleanup, _fill_tiny_holes, apply_printability
from curvepress.pipeline import analyze_image


def artwork():
    image = Image.new('RGBA', (240, 160), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 20, 108, 135), fill='black')
    draw.ellipse((43, 50, 88, 100), fill='white')
    draw.ellipse((144, 52, 216, 124), fill='#0047b0')
    return image


def encoded(image):
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


class ReliabilityTests(unittest.TestCase):
    def test_numeric_strings_from_browser_and_zero_margin(self):
        config = PlateConfig.from_dict({'base_height_mm': '1.0', 'relief_height_mm': '0.8', 'edge_margin_mm': 0})
        self.assertEqual(config.base_height_mm, 1.0)
        self.assertEqual(config.relief_height_mm, 0.8)
        mask, _ = apply_printability(np.ones((60, 80), dtype=bool), config)
        self.assertTrue(mask.any())

    def test_reject_invalid_settings_before_processing(self):
        for values in (
            {'base_height_mm': -1}, {'base_height_mm': 0}, {'relief_height_mm': float('nan')},
            {'curve_tolerance_mm': float('inf')}, {'edge_margin_mm': 50},
            {'halftone_pitch_mm': -1}, {'halftone_min_dot_mm': 2}, {'title': None},
            {'analysis_ppm': 'oops'}, {'mirror_for_print': 'false'}, {'width_mm': True},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                PlateConfig.from_dict(values)
        with self.assertRaises(ValueError):
            PlateConfig.from_dict([])

    def test_transparency_and_uniform_white_do_not_become_black(self):
        image = load_image(encoded(artwork()))
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        corrected = np.asarray(correct_illumination(Image.new('RGB', (80, 60), 'white'), .55))
        self.assertGreater(float(corrected.mean()), 240)
        with self.assertRaisesRegex(ValueError, 'no printable artwork'):
            analyze_image(encoded(Image.new('RGB', (80, 60), 'white')), PlateConfig())

    def test_degenerate_color_palette_and_seed_validation(self):
        from curvepress.image_pipeline import _kmeans_palette
        palette, labels = _kmeans_palette(np.full((16, 20, 3), 255, dtype=np.uint8), 4, 7)
        self.assertEqual(labels.shape, (16, 20))
        self.assertTrue(np.all(palette == 255))
        with self.assertRaisesRegex(ValueError, 'no printable artwork'):
            analyze_image(encoded(Image.new('RGB', (80, 60), 'white')), PlateConfig(style='color_layers'))
        with self.assertRaises(ValueError):
            PlateConfig(proof_seed=-1).resolved()
        with self.assertRaises(ValueError):
            PlateConfig(registration_marks='false').resolved()

    def test_lookup_cleanup_matches_full_canvas_reference(self):
        rng = np.random.default_rng(42)
        mask = ndimage.binary_dilation(rng.random((143, 191)) > .98)
        config = PlateConfig(analysis_ppm=6).resolved()
        labels, count = ndimage.label(mask)
        sizes = np.bincount(labels.ravel())
        expected = np.zeros_like(mask)
        for label in range(1, count + 1):
            ys, xs = np.where(labels == label)
            diagonal = np.hypot(np.ptp(xs), np.ptp(ys)) / config.analysis_ppm
            if sizes[label] >= config.minimum_component_mm2 * config.analysis_ppm**2 or diagonal >= config.minimum_width_mm * 3:
                expected[labels == label] = True
        np.testing.assert_array_equal(_component_cleanup(mask, config), expected)
        inverse = ~mask
        labels, count = ndimage.label(inverse)
        sizes = np.bincount(labels.ravel())
        border = set(labels[0]) | set(labels[-1]) | set(labels[:, 0]) | set(labels[:, -1])
        expected = mask.copy()
        for label in range(1, count + 1):
            if label not in border and sizes[label] < (config.minimum_gap_mm * .85 * config.analysis_ppm)**2:
                expected[labels == label] = True
        np.testing.assert_array_equal(_fill_tiny_holes(mask, config), expected)

    def test_print_orientation_tracks_mirror_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = [analyze_image(encoded(artwork()), PlateConfig(width_mm=50, height_mm=35, style='poster', mirror_for_print=flag), Path(tmp)) for flag in (True, False)]
            np.testing.assert_array_equal(np.asarray(results[0].print_preview)[:, ::-1], results[1].print_preview)
            np.testing.assert_array_equal(np.asarray(results[0].curve_preview)[:, ::-1], results[1].curve_preview)
            proofs = [np.asarray(Image.open(result.directory / 'proof-preview.png')) for result in results]
            np.testing.assert_array_equal(proofs[0][:, ::-1], proofs[1])

    def test_failed_export_does_not_publish_partial_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = PlateConfig(width_mm=40, height_mm=30, style='poster')
            result = analyze_image(encoded(artwork()), config, Path(tmp))

            def fail(layer, cfg, directory):
                (directory / 'invalid.stl').write_text('partial')
                raise RuntimeError('simulated CAD failure')

            with patch('curvepress.exporter.export_layer', side_effect=fail), self.assertRaises(RuntimeError):
                export_analysis(result, config)
            self.assertFalse((result.directory / 'invalid.stl').exists())
            self.assertFalse(list(result.directory.glob('.export-*')))

    def test_all_styles_export_closed_meshes_with_holes(self):
        try:
            import OCP  # noqa: F401
        except ImportError:
            self.skipTest('CAD extra is not installed')
        with tempfile.TemporaryDirectory() as tmp:
            for style in ('poster', 'woodcut', 'line_art', 'halftone', 'color_layers'):
                with self.subTest(style=style):
                    config = PlateConfig(width_mm=32, height_mm=24, analysis_ppm=4, style=style, color_count=3).resolved()
                    result = analyze_image(encoded(artwork()), config, Path(tmp))
                    reports = export_analysis(result, config)
                    self.assertTrue(reports)
                    if style == 'poster':
                        self.assertGreater(reports[0]['holes'], 0)
                    for report in reports:
                        self.assertEqual(report['step_solids'], 1)
                        self.assertEqual(report['mesh_boundary_edges'], 0)
                        self.assertEqual(report['mesh_nonmanifold_edges'], 0)
                        np.testing.assert_allclose(report['read_back_mesh_bounds_mm'], [32, 24, 2], atol=.02)
                        for name in report['files']:
                            self.assertTrue((result.directory / name).is_file())
                        validation = json.loads((result.directory / report['files'][-1]).read_text())
                        self.assertTrue(validation['step_read_back'])
