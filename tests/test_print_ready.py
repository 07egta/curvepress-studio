"""Minimum stroke width, mesh export without CAD, and the nozzle test strip."""
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from curvepress.calibrate import (
    PLATE_H,
    PLATE_W,
    build_calibration_layer,
    calibration_config_from_request,
    write_calibration,
)
from curvepress.cli import main
from curvepress.config import PlateConfig
from curvepress.curves import contour_regions, cubic_segments, sample_segments
from curvepress.physical import _close_narrow_gaps, _enforce_minimum_width, apply_printability


def _config(**overrides) -> PlateConfig:
    values = dict(
        width_mm=40,
        height_mm=20,
        analysis_ppm=6,
        edge_margin_mm=0,
        minimum_width_mm=0.5,
        minimum_gap_mm=0.5,
        style="poster",
    )
    values.update(overrides)
    return PlateConfig(**values).resolved()


def _png() -> bytes:
    image = Image.new("RGB", (80, 60), "white")
    ImageDraw.Draw(image).rectangle((18, 16, 62, 44), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


class TestMinimumWidth:
    def test_hairline_grows_to_minimum_and_curve_keeps_it(self):
        config = _config()
        mask = np.zeros((120, 240), dtype=bool)
        mask[60, 30:210] = True
        cleaned, _ = apply_printability(mask, config)
        rows = np.where(cleaned[:, 120])[0]
        assert rows.max() - rows.min() + 1 >= 3
        regions = contour_regions(cleaned, config)
        assert len(regions) == 1
        points = sample_segments(cubic_segments(regions[0].outer), 16)
        assert points[:, 1].max() - points[:, 1].min() >= config.minimum_width_mm * 0.9

    def test_minimum_gap_stays_open_and_narrower_gap_closes(self):
        config = _config()
        kept = np.zeros((80, 120), dtype=bool)
        kept[30:33, 10:110] = True
        kept[36:39, 10:110] = True
        opened, _ = apply_printability(kept, config)
        assert not opened[33:36, 60].any()
        assert opened[31, 60] and opened[37, 60]

        closed = np.zeros((80, 120), dtype=bool)
        closed[30:33, 10:110] = True
        closed[35:38, 10:110] = True
        filled, _ = apply_printability(closed, config)
        assert filled[33, 60] and filled[34, 60]

    def test_solids_and_open_paper_are_not_inflated(self):
        config = _config()
        square = np.zeros((80, 80), dtype=bool)
        square[20:60, 20:60] = True
        np.testing.assert_array_equal(square, _close_narrow_gaps(square, config))
        rect = np.zeros((100, 120), dtype=bool)
        rect[20:80, 20:100] = True
        np.testing.assert_array_equal(rect, _enforce_minimum_width(rect, config))

    def test_wider_minimum_gap_closes_what_a_single_closing_misses(self):
        # Four pixels is 0.67 mm at 6 px/mm, under a 0.8 mm gap but beyond the
        # one-pixel binary closing. Halftone sets close_narrow_gaps=False.
        config = _config(minimum_gap_mm=0.8)
        mask = np.zeros((80, 120), dtype=bool)
        mask[30:34, 10:110] = True
        mask[38:42, 10:110] = True
        fused, _ = apply_printability(mask, config)
        kept, _ = apply_printability(mask, config, close_narrow_gaps=False)
        assert fused[34:38, 60].all()
        assert not kept[34:38, 60].any()
        assert kept[31, 60] and kept[39, 60]


class TestCalibration:
    def test_strip_is_closed_exact_and_not_mirrored(self, tmp_path: Path):
        config = calibration_config_from_request({"nozzle_mm": "0.4", "layer_height_mm": 0.2})
        assert config.mirror_for_print is False
        assert (config.width_mm, config.height_mm) == (PLATE_W, PLATE_H)
        written = write_calibration(tmp_path, config)
        assert written["mesh"]["mesh_boundary_edges"] == 0
        assert written["mesh"]["mesh_nonmanifold_edges"] == 0
        assert written["bounds_mm"] == [PLATE_W, PLATE_H, config.base_height_mm + config.relief_height_mm]
        guide = (tmp_path / "CALIBRATION.md").read_text(encoding="utf-8")
        assert "0.4" in guide and "do not mirror" in guide.lower()
        assert (tmp_path / "nozzle_test_ink.stl").stat().st_size > 1000
        assert (tmp_path / "nozzle_test_ink.3mf").read_bytes().startswith(b"PK")

        layer, _ = build_calibration_layer(config)
        from curvepress.mesh import build_plate_mesh

        vertices, _ = build_plate_mesh(layer, config)
        top = config.base_height_mm + config.relief_height_mm
        bar = vertices[
            (np.abs(vertices[:, 2] - top) < 1e-3)
            & (vertices[:, 0] > 40)
            & (vertices[:, 0] < 90)
            & (vertices[:, 1] > 87.3)
            & (vertices[:, 1] < 88.3)
        ]
        assert len(bar)
        assert bar[:, 1].max() - bar[:, 1].min() == pytest.approx(0.40, abs=0.03)

    def test_cli_writes_the_strip(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        output = tmp_path / "strip"
        assert main(["calibrate", "-o", str(output), "--nozzle", "0.4", "--layer-height", "0.2"]) == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["bars_mm"][0] == 0.4
        assert (output / "nozzle_test_ink.3mf").is_file()
        guide = (output / "CALIBRATION.md").read_text(encoding="utf-8")
        assert "Do not mirror" in guide
        assert "反転" in guide


class TestCliMeshExport:
    def test_convert_writes_stl_without_step(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        image = tmp_path / "art.png"
        image.write_bytes(_png())
        output = tmp_path / "out"
        assert main([
            "convert", str(image), "--style", "poster", "--width", "40", "--height", "30",
            "--title", "demo", "-o", str(output),
        ]) == 0
        captured = capsys.readouterr()
        summary = json.loads(captured.out)
        directory = Path(summary["directory"])
        stl = list(directory.glob("*.stl"))
        assert stl and stl[0].stat().st_size > 200
        assert list(directory.glob("*.3mf"))
        assert (directory / "PRINT_GUIDE.md").is_file()
        assert summary["meshes"]
        if summary["step_warning"]:
            assert "3MF" in summary["step_warning"]
            assert not list(directory.glob("*.step"))

    def test_step_failure_still_publishes_meshes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
        image = tmp_path / "art.png"
        image.write_bytes(_png())
        monkeypatch.setattr("curvepress.cli.cad_available", lambda: True)

        def fail(result, config):
            raise RuntimeError("STEP export failed: face invalid")

        monkeypatch.setattr("curvepress.cli.export_analysis", fail)
        assert main(["convert", str(image), "--style", "poster", "--width", "36", "--height", "28", "-o", str(tmp_path / "out")]) == 0
        summary = json.loads(capsys.readouterr().out)
        assert "STEP was not written" in summary["step_warning"]
        assert list(Path(summary["directory"]).glob("*.stl"))

    def test_svg_only_skips_meshes(self, tmp_path: Path):
        image = tmp_path / "art.png"
        image.write_bytes(_png())
        output = tmp_path / "out"
        assert main(["convert", str(image), "--svg-only", "--width", "36", "--height", "28", "-o", str(output)]) == 0
        assert not list(output.rglob("*.stl"))
