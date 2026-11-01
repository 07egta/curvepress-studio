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
        segments = list(segments)
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


    def test_vectorised_chain_matches_reference(self):
        # Reference: the original per-corner loop.
        rng = np.random.default_rng(3)
        angle = np.sort(rng.uniform(0, 2 * np.pi, 40))
        pts = np.c_[np.cos(angle), np.sin(angle)] * rng.uniform(5, 9, 40)[:, None]
        f = 0.24
        ref = []
        starts = [p + f * (pts[i - 1] - p) for i, p in enumerate(pts)]
        ends = [p + f * (pts[(i + 1) % len(pts)] - p) for i, p in enumerate(pts)]
        for i, p in enumerate(pts):
            a, b = ends[i - 1], starts[i]
            if np.linalg.norm(b - a) > 1e-9:
                ref.append((a, a + (b - a) / 3, a + 2 * (b - a) / 3, b))
            ref.append((starts[i], starts[i] + (p - starts[i]) * 2 / 3, ends[i] + (p - ends[i]) * 2 / 3, ends[i]))
        np.testing.assert_allclose(cubic_segments(pts), np.array(ref), atol=1e-12)

    def test_iterative_rdp_matches_recursive(self):
        from curvepress.curves import _distance_to_line, rdp

        def recursive(points, tol):
            if len(points) <= 2:
                return points
            d = _distance_to_line(points[1:-1], points[0], points[-1])
            i = int(np.argmax(d)) + 1
            if d[i - 1] <= tol:
                return points[[0, -1]]
            return np.vstack((recursive(points[: i + 1], tol)[:-1], recursive(points[i:], tol)))

        rng = np.random.default_rng(5)
        walk = np.cumsum(rng.normal(size=(500, 2)), axis=0)
        for tol in (0.1, 0.8, 3.0):
            np.testing.assert_array_equal(rdp(walk, tol), recursive(walk, tol))


if __name__ == "__main__":
    unittest.main()



