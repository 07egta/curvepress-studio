import unittest

from curvepress.config import PlateConfig


class ConfigTests(unittest.TestCase):
    def test_a1_mini_defaults_are_layer_aligned(self):
        config = PlateConfig().resolved()
        self.assertEqual(config.base_height_mm, 0.8)
        self.assertEqual(config.relief_height_mm, 1.2)
        self.assertEqual(config.minimum_width_mm, 0.5)
        self.assertEqual(config.minimum_gap_mm, 0.5)
        self.assertEqual(config.edge_margin_mm, 2.0)
        self.assertAlmostEqual(config.base_height_mm % config.layer_height_mm, 0.0, places=6)

    def test_nozzle_scales_physical_constraints(self):
        config = PlateConfig(nozzle_mm=0.8, layer_height_mm=0.2).resolved()
        self.assertEqual(config.base_height_mm, 1.6)
        self.assertEqual(config.relief_height_mm, 2.4)
        self.assertEqual(config.minimum_width_mm, 1.0)
        self.assertEqual(config.edge_margin_mm, 4.0)

    def test_invalid_style_is_rejected(self):
        with self.assertRaises(ValueError):
            PlateConfig(style="unknown").resolved()


if __name__ == "__main__":
    unittest.main()


