import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from curvepress.config import PlateConfig
from curvepress.image_pipeline import otsu_threshold
from curvepress.pipeline import analyze_image


def sample_png() -> bytes:
    image = Image.new("RGB", (420, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((35, 35, 190, 215), fill="#172f42")
    draw.rounded_rectangle((230, 60, 385, 205), radius=35, fill="#568da8")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class PipelineTests(unittest.TestCase):
    def test_otsu_separates_two_tones(self):
        values = np.hstack((np.full((30, 20), 0.15), np.full((30, 20), 0.85)))
        threshold = otsu_threshold(values)
        self.assertGreaterEqual(threshold, 0.14)
        self.assertLess(threshold, 0.85)

    def test_all_presets_produce_preview_or_color_layers(self):
        for style in ("woodcut", "line_art", "poster", "halftone", "color_layers"):
            with self.subTest(style=style), tempfile.TemporaryDirectory() as directory:
                result = analyze_image(
                    sample_png(),
                    PlateConfig(width_mm=70, height_mm=45, style=style, analysis_ppm=4),
                    Path(directory),
                )
                self.assertTrue(result.layers)
                self.assertTrue((result.directory / "print-preview.png").is_file())
                self.assertTrue(all(" C " in layer.svg for layer in result.layers))
                self.assertEqual(result.print_preview.size, (280, 180))

    def test_artwork_stays_inside_physical_margin(self):
        with tempfile.TemporaryDirectory() as directory:
            config = PlateConfig(width_mm=70, height_mm=45, style="poster", analysis_ppm=4).resolved()
            result = analyze_image(sample_png(), config, Path(directory))
            mask = result.layers[0].mask
            margin = round(config.edge_margin_mm * config.analysis_ppm)
            self.assertFalse(mask[:margin].any())
            self.assertFalse(mask[-margin:].any())
            self.assertFalse(mask[:, :margin].any())
            self.assertFalse(mask[:, -margin:].any())


if __name__ == "__main__":
    unittest.main()


