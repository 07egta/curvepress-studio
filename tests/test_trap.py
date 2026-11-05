import tempfile
import unittest
from pathlib import Path

import numpy as np

from curvepress.config import PlateConfig
from curvepress.guide import TYPE_HIGH_MM, build_guide, type_high_shim_mm
from curvepress.physical import apply_trapping


class TrapTests(unittest.TestCase):
    def setUp(self):
        self.config = PlateConfig(trap_mm=0.2).resolved()
        self.dark = np.zeros((60, 60), bool)
        self.dark[:, 30:] = True
        self.light = np.zeros((60, 60), bool)
        self.light[:, 10:30] = True

    def test_light_plate_grows_only_under_the_dark_plate(self):
        masks = [self.dark.copy(), self.light.copy()]
        added = apply_trapping(masks, self.config)
        self.assertGreater(added[1], 0)
        row = np.nonzero(masks[1][30])[0]
        self.assertEqual(row.min(), 10)  # bare paper side did not move
        self.assertGreater(row.max(), 29)  # tucked under the dark plate
        self.assertTrue(np.array_equal(masks[0], self.dark))  # darkest is untouched
        self.assertFalse(np.any(masks[1] & ~(self.light | self.dark)))

    def test_zero_trap_and_single_plate_change_nothing(self):
        masks = [self.dark.copy(), self.light.copy()]
        apply_trapping(masks, PlateConfig(trap_mm=0.0).resolved())
        self.assertTrue(np.array_equal(masks[1], self.light))
        single = [self.dark.copy()]
        self.assertEqual(apply_trapping(single, self.config), [0.0])

    def test_trap_range_is_validated(self):
        with self.assertRaises(ValueError):
            PlateConfig(trap_mm=3).resolved()


class GuideTests(unittest.TestCase):
    def test_type_high_shim(self):
        self.assertAlmostEqual(type_high_shim_mm(2.0), round(TYPE_HIGH_MM - 2.0, 2))
        self.assertEqual(type_high_shim_mm(30.0), 0.0)

    def test_guide_reflects_the_plate(self):
        config = PlateConfig(style="color_layers", trap_mm=0.2).resolved()
        text = build_guide(config, ["plate_1", "plate_2", "plate_3"])
        self.assertIn("plate_3 → plate_2 → plate_1", text)
        self.assertIn("アイロニング", text)
        self.assertIn("23.32", text)
        mirrored = build_guide(PlateConfig(mirror_for_print=False).resolved(), ["ink"])
        self.assertIn("X方向に反転", mirrored)


if __name__ == "__main__":
    unittest.main()
