"""Nozzle test strip: exact lines, gaps, a solid pad and an open window.

Print this before an artwork plate. It is not mirrored, so the embossed
numbers read correctly on the plastic. The thinnest solid line is the minimum
line width to type into CurvePress; the narrowest open groove is the finest
white gap this nozzle can keep.
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import PlateConfig
from .curves import regions_svg
from .exporter import _checked_plate_mesh, _write_3mf
from .guide import type_high_shim_mm
from .mesh import write_binary_stl
from .models import CurveRegion, PlateLayer

PLATE_W = 120.0
PLATE_H = 96.0
LINE_WIDTHS_MM = (0.40, 0.50, 0.60, 0.80, 1.00, 1.20, 1.60)
GAP_WIDTHS_MM = (0.40, 0.50, 0.60, 0.80, 1.00, 1.20)

# Seven-segment digits. Segments stay a fraction of a millimetre apart so the
# mesh walls do not touch; a 0.4 mm nozzle still prints them as one glyph.
_SEGMENTS = {
    "0": "abcedf",
    "1": "bc",
    "2": "abged",
    "3": "abgcd",
    "4": "fgbc",
    "5": "afgcd",
    "6": "afgecd",
    "7": "abc",
    "8": "abcdefg",
    "9": "abfgcd",
}


@dataclass(frozen=True)
class StripGeometry:
    """Rectangles are ``(x0, y0, x1, y1)`` in image millimetres, y downward."""

    bars: tuple[tuple[float, tuple[float, float, float, float]], ...]
    gaps: tuple[tuple[float, float], ...]  # (gap mm, x of the groove centre)
    solids: tuple[tuple[float, float, float, float], ...]
    window_outer: tuple[float, float, float, float]
    window_hole: tuple[float, float, float, float]
    regions: tuple[CurveRegion, ...]


def _box(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float] | None:
    if x1 - x0 < 0.2 or y1 - y0 < 0.2:
        return None
    return (float(x0), float(y0), float(x1), float(y1))


def _digit_boxes(
    char: str, x: float, y: float, width: float, height: float, stroke: float, gap: float = 0.16
) -> list[tuple[float, float, float, float]]:
    if char == ".":
        size = stroke * 0.9
        dot = _box(x, y + height - size * 1.35, x + size, y + height - size * 0.2)
        return [dot] if dot else []
    names = _SEGMENTS.get(char)
    if not names:
        return []
    boxes: list[tuple[float, float, float, float]] = []
    mid = y + height / 2.0
    horizontal = {
        "a": (y, y + stroke),
        "g": (mid - stroke / 2.0, mid + stroke / 2.0),
        "d": (y + height - stroke, y + height),
    }
    vertical = {
        "f": (y + stroke + gap, mid - gap),
        "b": (y + stroke + gap, mid - gap),
        "e": (mid + gap, y + height - stroke - gap),
        "c": (mid + gap, y + height - stroke - gap),
    }
    for name in names:
        if name in horizontal:
            y0, y1 = horizontal[name]
            made = _box(x + stroke + gap, y0, x + width - stroke - gap, y1)
        elif name in {"f", "e"}:
            y0, y1 = vertical[name]
            made = _box(x, y0, x + stroke, y1)
        else:
            y0, y1 = vertical[name]
            made = _box(x + width - stroke, y0, x + width, y1)
        if made:
            boxes.append(made)
    return boxes


def _text_boxes(
    text: str,
    x: float,
    y: float,
    *,
    digit_w: float,
    digit_h: float,
    stroke: float,
    char_gap: float,
) -> tuple[list[tuple[float, float, float, float]], float]:
    boxes: list[tuple[float, float, float, float]] = []
    cursor = x
    end = x
    for char in text:
        if char == ".":
            glyph = _digit_boxes(".", cursor, y, digit_w, digit_h, stroke)
            advance = stroke + char_gap * 0.55
        else:
            glyph = _digit_boxes(char, cursor, y, digit_w, digit_h, stroke)
            advance = digit_w + char_gap
        boxes.extend(glyph)
        if glyph:
            end = max(end, max(box[2] for box in glyph))
        cursor += advance
    return boxes, end


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float], pad: float = 0.05) -> bool:
    return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad


def _require_separated(boxes: list[tuple[float, float, float, float]]) -> None:
    for index, box in enumerate(boxes):
        for other in boxes[index + 1 :]:
            if _overlaps(box, other):
                raise RuntimeError(f"calibration geometry overlaps: {box} and {other}")


def build_strip_geometry() -> StripGeometry:
    """Lay out the strip. Coordinates are millimetres, origin at the top-left."""
    solids: list[tuple[float, float, float, float]] = []
    bars: list[tuple[float, tuple[float, float, float, float]]] = []
    bar_x0, bar_x1 = 18.0, 112.0
    pitch = 6.6
    for index, width in enumerate(LINE_WIDTHS_MM):
        y = 8.0 + index * pitch
        bar = (bar_x0, y, bar_x1, y + width)
        bars.append((width, bar))
        solids.append(bar)
        label_y = (y + width / 2.0) - 2.5
        glyphs, _ = _text_boxes(
            f"{width:.1f}", 4.0, label_y, digit_w=3.0, digit_h=5.0, stroke=0.70, char_gap=0.42
        )
        solids.extend(glyphs)

    gap_y0, gap_y1 = 56.0, 68.0
    block_w = 8.0
    x = 18.0
    gaps: list[tuple[float, float]] = []
    blocks: list[tuple[float, float, float, float]] = []
    for width in GAP_WIDTHS_MM:
        block = (x, gap_y0, x + block_w, gap_y1)
        blocks.append(block)
        groove = x + block_w + width / 2.0
        gaps.append((width, groove))
        x += block_w + width
    blocks.append((x, gap_y0, x + block_w, gap_y1))
    solids.extend(blocks)
    for width, groove in gaps:
        glyphs, end = _text_boxes(
            f"{width:.1f}",
            groove - 3.3,
            69.3,
            digit_w=2.45,
            digit_h=4.1,
            stroke=0.62,
            char_gap=0.36,
        )
        # Keep the label centred on the groove after measuring it.
        if glyphs:
            shift = groove - (glyphs[0][0] + end) / 2.0
            glyphs = [(a + shift, b, c + shift, d) for a, b, c, d in glyphs]
        solids.extend(glyphs)

    pad = (18.0, 78.0, 64.0, 92.0)
    window_outer = (70.0, 78.0, 112.0, 92.0)
    window_hole = (75.0, 82.0, 107.0, 88.0)
    solids.append(pad)
    _require_separated(solids + [window_outer])
    for box in solids + [window_outer, window_hole]:
        if box[0] < 2 or box[1] < 2 or box[2] > PLATE_W - 2 or box[3] > PLATE_H - 2:
            raise RuntimeError(f"calibration feature leaves the plate: {box}")
    if not (
        window_hole[0] > window_outer[0]
        and window_hole[1] > window_outer[1]
        and window_hole[2] < window_outer[2]
        and window_hole[3] < window_outer[3]
    ):
        raise RuntimeError("calibration window hole is not inside its frame")

    def ring(box: tuple[float, float, float, float]) -> np.ndarray:
        x0, y0, x1, y1 = box
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)

    regions = [CurveRegion(outer=ring(box)) for box in solids]
    regions.append(CurveRegion(outer=ring(window_outer), holes=[ring(window_hole)]))
    return StripGeometry(
        bars=tuple(bars),
        gaps=tuple(gaps),
        solids=tuple(solids),
        window_outer=window_outer,
        window_hole=window_hole,
        regions=tuple(regions),
    )


def calibration_config_from_request(raw: dict | None) -> PlateConfig:
    """Plate profile for the strip. Artwork size and style from ``raw`` are ignored."""
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ValueError("config must be an object")
    picked: dict[str, object] = {}
    for key in ("nozzle_mm", "layer_height_mm", "base_height_mm", "relief_height_mm"):
        if key in raw and raw[key] not in (None, "", "auto"):
            picked[key] = raw[key]
    return PlateConfig(
        width_mm=PLATE_W,
        height_mm=PLATE_H,
        style="poster",
        mirror_for_print=False,
        remove_scan_frame=False,
        registration_marks=False,
        title="nozzle_test",
        edge_margin_mm=2.0,
        **picked,  # type: ignore[arg-type]
    ).resolved()


def _manual(config: PlateConfig, geometry: StripGeometry) -> str:
    total = config.base_height_mm + config.relief_height_mm
    shim = type_high_shim_mm(total)
    lines = "、".join(f"{width:.1f}" for width in LINE_WIDTHS_MM)
    gaps = "、".join(f"{width:.1f}" for width in GAP_WIDTHS_MM)
    ja = [
        "# ノズル確認用の試し版",
        "",
        "作品の版を刷る前に、この版を印刷してください。データは左右反転していません。"
        "数字はプラスチックの上でそのまま読めます。スライサーで反転しないでください。",
        "",
        f"- サイズ {config.width_mm:g} × {config.height_mm:g} × {total:.1f} mm"
        f"（土台 {config.base_height_mm:g} + 凸 {config.relief_height_mm:g}）",
        f"- ノズル {config.nozzle_mm:g} mm、積層 {config.layer_height_mm:g} mm、PLA、壁4、天面5、サポートなし、天面アイロニングON、土台を下。",
        f"- 線の太さ（上から）: {lines} mm",
        f"- 溝の幅（左から）: {gaps} mm",
        "- 途切れずに残ったいちばん細い線を、CurvePressの「最小の線幅」に入れて版を作り直します。",
        "- 埋まった溝は、その幅の白い隙間がこのノズルでは残りません。",
        "- 左下の平らな面はインクを載せる面です。右下の穴は開いたまま、壁が割れないことを確認します。",
        (
            f"- 活版の type-high（23.32 mm）まであと約 {shim:g} mm です。試し版では足さなくて構いません。"
            if shim > 0
            else "- 厚みは type-high 以上です。"
        ),
        "",
        "0.5 mm が途切れて 0.8 mm が残るのは、失敗ではなくこのプリンターの結果です。",
    ]
    en = [
        "---",
        "",
        "## English",
        "",
        "Print this plate before an artwork plate. The file is not mirrored: the numbers should read correctly on the plastic. Do not mirror it in the slicer.",
        "",
        f"Size {config.width_mm:g} × {config.height_mm:g} × {total:.1f} mm "
        f"(base {config.base_height_mm:g} + relief {config.relief_height_mm:g}). "
        f"Nozzle {config.nozzle_mm:g} mm, layers {config.layer_height_mm:g} mm, PLA, 4 walls, 5 top layers, no supports, top-surface ironing on, base down.",
        "",
        f"Raised lines, top to bottom: {', '.join(f'{width:.1f}' for width in LINE_WIDTHS_MM)} mm. "
        "The thinnest line that stays solid and stuck to the base is your minimum line width. "
        "In CurvePress open More settings, set Min. line width to that number, and make the artwork plate again.",
        "",
        f"Grooves, left to right: {', '.join(f'{width:.1f}' for width in GAP_WIDTHS_MM)} mm. "
        "A groove that fills in will fill in on the artwork too.",
        "",
        "Bottom left is a solid pad (the ink-bearing face). Bottom right is a frame with a hole; the hole should stay open and the walls should not split.",
        "",
        "A 0.5 mm line that breaks while 0.8 mm survives is a useful result, not a failed plate. "
        f"There are {len(geometry.bars)} lines and {len(geometry.gaps)} grooves.",
        "",
        (
            f"Letterpress type-high is 23.32 mm; this plate would need about {shim:g} mm of packing. The test strip does not."
            if shim > 0
            else "This plate is already at least type-high."
        ),
        "",
    ]
    return "\n".join(ja + en)


def build_calibration_layer(config: PlateConfig) -> tuple[PlateLayer, StripGeometry]:
    geometry = build_strip_geometry()
    svg = regions_svg(geometry.regions, config, fill="#111827", title="CurvePress nozzle test")
    layer = PlateLayer(
        name="ink",
        color_hex="#111827",
        mask=np.zeros((2, 2), dtype=bool),
        regions=list(geometry.regions),
        svg=svg,
    )
    return layer, geometry


def write_calibration(directory: Path, config: PlateConfig) -> dict:
    """Write STL, 3MF, SVG and CALIBRATION.md into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    config = config.resolved()
    layer, geometry = build_calibration_layer(config)
    vertices, triangles, stats, bounds = _checked_plate_mesh(layer, config)
    stem = f"{config.title}_{layer.name}"
    files = {
        "stl": directory / f"{stem}.stl",
        "3mf": directory / f"{stem}.3mf",
        "svg": directory / f"{stem}.svg",
        "guide": directory / "CALIBRATION.md",
    }
    write_binary_stl(files["stl"], vertices, triangles)
    _write_3mf(files["3mf"], vertices, triangles)
    files["svg"].write_text(layer.svg, encoding="utf-8")
    files["guide"].write_text(_manual(config, geometry), encoding="utf-8")
    return {
        "files": [path.name for path in files.values()],
        "paths": {key: str(path) for key, path in files.items()},
        "mesh": stats,
        "bounds_mm": bounds.tolist(),
        "bars_mm": [width for width, _ in geometry.bars],
        "gaps_mm": [width for width, _ in geometry.gaps],
        "geometry": geometry,
    }


def calibration_zip(config: PlateConfig) -> bytes:
    with tempfile.TemporaryDirectory(prefix="curvepress-cal-") as temporary:
        written = write_calibration(Path(temporary), config)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in written["files"]:
                archive.write(Path(temporary) / name, name)
        return buffer.getvalue()
