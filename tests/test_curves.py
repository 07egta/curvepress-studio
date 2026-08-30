import unittest

import numpy as np

from curvepress.config import PlateConfig
from curvepress.curves import cubic_segments, path_d, regions_svg
from curvepress.models import CurveRegion


class CurveTests(unittest.TestCase):
    def setUp(self):
        self.square = np.array([[3.0, 3.0], [27.0, 3.0], [27.0, 17.0], [3.0, 17.0]])

    def test_bezier_chain_is_closed_and_continuous(self):
        segments = cubic_segments(self.square)
        self.assertGreaterEqual(len(segments), 8)
        for current, following in zip(segments, segments[1:] + segments[:1]):
            np.testing.assert_allclose(current[3], following[0], atol=1e-10)

    def test_svg_uses_cubic_paths_and_print_mirror(self):
        config = PlateConfig(width_mm=30, height_mm=20, style="poster").resolved()
        svg = regions_svg([CurveRegion(self.square)], config)
        self.assertIn(" C ", path_d(self.square))
        self.assertIn("scale(-1 1)", svg)
        self.assertIn('fill-rule="evenodd"', svg)

    def test_controls_stay_in_local_coordinate_range(self):
        # A square's rounded controls must not overshoot its bounding box.
        controls = np.vstack([np.vstack(segment) for segment in cubic_segments(self.square)])
        self.assertGreaterEqual(float(controls[:, 0].min()), 3.0)
        self.assertLessEqual(float(controls[:, 0].max()), 27.0)
        self.assertGreaterEqual(float(controls[:, 1].min()), 3.0)
        self.assertLessEqual(float(controls[:, 1].max()), 17.0)


if __name__ == "__main__":
    unittest.main()


