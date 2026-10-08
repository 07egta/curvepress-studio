"""Regression tests for local halftone drawing and scan-frame preservation."""

import math
import unittest

import numpy as np
from PIL import Image, ImageDraw

from curvepress.config import PlateConfig
from curvepress.image_pipeline import _halftone_mask, fit_on_plate, grayscale


def _reference_halftone(image: Image.Image, config: PlateConfig) -> np.ndarray:
    """Original full-canvas implementation, retained as a correctness oracle."""
    gray = grayscale(image)
    height, width = gray.shape
    pitch = max(4, int(round(config.halftone_pitch_mm * config.analysis_ppm)))
    min_radius = config.halftone_min_dot_mm * config.analysis_ppm * 0.5
    max_radius = min(config.halftone_max_dot_mm, config.halftone_pitch_mm * 0.96) * config.analysis_ppm * 0.5
    angle = math.radians(config.halftone_angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    cx, cy = width * 0.5, height * 0.5
    diagonal = int(math.ceil(math.hypot(width, height)))
    mask = np.zeros((height, width), dtype=bool)
    yy, xx = np.ogrid[:height, :width]

    for gy in range(-diagonal, diagonal + pitch, pitch):
        for gx in range(-diagonal, diagonal + pitch, pitch):
            x = cx + gx * cos_a - gy * sin_a
            y = cy + gx * sin_a + gy * cos_a
            ix, iy = int(round(x)), int(round(y))
            if ix < 0 or iy < 0 or ix >= width or iy >= height:
                continue
            tone = float(np.clip(1.0 - gray[iy, ix], 0.0, 1.0))
            if tone < 0.055:
                continue
            radius = min_radius + (max_radius - min_radius) * tone**0.72
            disk = (xx - x) ** 2 + (yy - y) ** 2 <= radius**2
            mask |= disk
    return mask


class ImageOptimizationTests(unittest.TestCase):
    def test_halftone_matches_original_at_multiple_angles_and_pitches(self):
        yy, xx = np.indices((49, 63))
        patterns = [
            np.clip(255 - xx * 4 + yy * 2, 0, 255).astype(np.uint8),
            np.where((xx + yy * 2) % 17 < 8, 32, 242).astype(np.uint8),
        ]
        for pixels in patterns:
            image = Image.fromarray(pixels, mode="L").convert("RGB")
            for angle in (0.0, 15.0, 67.0):
                for pitch in (1.2, 2.4):
                    with self.subTest(angle=angle, pitch=pitch):
                        config = PlateConfig(
                            style="halftone", analysis_ppm=4,
                            halftone_angle_deg=angle,
                            halftone_pitch_mm=pitch,
                        ).resolved()
                        expected = _reference_halftone(image, config)
                        actual = _halftone_mask(image, config)
                        np.testing.assert_array_equal(actual, expected)

    def test_halftone_white_image_has_no_dots(self):
        image = Image.new("RGB", (61, 47), "white")
        mask = _halftone_mask(image, PlateConfig(style="halftone").resolved())
        self.assertFalse(mask.any())

    def test_disabling_scan_frame_removal_keeps_full_source(self):
        image = Image.new("RGB", (91, 63), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 90, 62), outline="black", width=4)
        draw.line((2, 10, 75, 53), fill="blue", width=3)

        config = PlateConfig(
            width_mm=70, height_mm=45, analysis_ppm=4,
            remove_scan_frame=False,
        ).resolved()
        fitted, (x0, y0, x1, y1) = fit_on_plate(image, config)
        width, height = x1 - x0, y1 - y0
        expected = image.resize((width, height), Image.Resampling.LANCZOS)

        self.assertEqual(fitted.size, (280, 180))
        np.testing.assert_array_equal(
            np.asarray(fitted.crop((x0, y0, x1, y1))),
            np.asarray(expected),
        )


if __name__ == "__main__":
    unittest.main()
