from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from curvepress.config import PlateConfig
from curvepress.image_pipeline import _color_masks, fit_on_plate
from curvepress.physical import registration_mask
from curvepress.pipeline import analyze_image

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "hokusai-great-wave.jpg"


def _two_color_png() -> bytes:
    image = Image.new("RGB", (400, 260), (245, 236, 214))  # warm paper
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 180, 220), fill=(20, 45, 90))     # navy
    draw.ellipse((220, 60, 360, 200), fill=(200, 70, 50))      # vermilion
    import io

    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_color_plates_use_real_colours_and_skip_paper():
    config = PlateConfig(style="color_layers", color_count=2).resolved()
    image = Image.open(__import__("io").BytesIO(_two_color_png())).convert("RGB")
    fitted, box = fit_on_plate(image, config)
    layers = _color_masks(fitted, config, box)
    assert len(layers) == 2
    colors = [np.array([int(c[i : i + 2], 16) for i in (1, 3, 5)]) for _, c, _ in layers]
    # One plate is blue-dominant, the other red-dominant; neither is paper beige.
    assert any(c[2] > c[0] + 30 for c in colors)
    assert any(c[0] > c[2] + 60 for c in colors)
    for _, _, mask in layers:
        x0, y0, x1, y1 = box
        outside = mask.copy()
        outside[y0:y1, x0:x1] = False
        assert not outside.any(), "plates must never ink the padding around the artwork"


def test_registration_marks_are_identical_on_every_plate(tmp_path):
    result = analyze_image(_two_color_png(), {"style": "color_layers", "color_count": 2}, tmp_path)
    config = PlateConfig(style="color_layers", color_count=2).resolved()
    kento = registration_mask(result.layers[0].mask.shape, config)
    assert kento.any()
    for layer in result.layers:
        assert np.all(layer.mask[kento]), f"{layer.name} is missing its kento marks"
    assert result.metrics["registration_marks"] is True


def test_registration_band_keeps_art_clear_of_kento():
    config = PlateConfig(style="color_layers").resolved()
    image = Image.new("RGB", (1000, 300), "black")
    _, (x0, y0, x1, y1) = fit_on_plate(image, config)
    kento = registration_mask((int(config.height_mm * config.analysis_ppm), int(config.width_mm * config.analysis_ppm)), config)
    assert not kento[y0:y1, x0:x1].any()


def test_single_plate_has_no_kento(tmp_path):
    result = analyze_image(EXAMPLE.read_bytes(), {"style": "woodcut"}, tmp_path)
    assert result.metrics["registration_marks"] is False


def test_proof_and_heightmaps_are_written(tmp_path):
    result = analyze_image(EXAMPLE.read_bytes(), {"style": "woodcut"}, tmp_path)
    proof = Image.open(result.directory / "proof-preview.png")
    assert proof.size == (result.source.width * 2, result.source.height * 2)
    height = Image.open(result.directory / f"{result.layers[0].name}-height.png")
    assert height.mode == "L" and height.size == result.source.size
    # Mirrored like the CAD plate: the heightmap equals the flipped mask.
    h = np.asarray(height) > 127
    assert (h == result.layers[0].mask[:, ::-1]).mean() > 0.97


def test_kento_plates_export_to_exact_size(tmp_path):
    import pytest

    exporter = pytest.importorskip("curvepress.exporter")
    try:
        exporter._load_occ()
    except exporter.CadUnavailable:
        pytest.skip("OpenCascade not installed")
    cfg = {"style": "color_layers", "color_count": 2}
    result = analyze_image(_two_color_png(), cfg, tmp_path)
    for report in exporter.export_analysis(result, cfg):
        assert report["step_valid"] and report["mesh_boundary_edges"] == 0
        assert max(abs(a - b) for a, b in zip(report["read_back_mesh_bounds_mm"], report["dimensions_mm"])) < 0.2
