"""A small print-test plate: find out what *your* printer can reproduce.

Fine lines, narrow gaps, dots and holes in known sizes are raised on one plate,
so a single 10-minute print tells you the smallest feature that comes out
clean with your nozzle, layer height and slicer settings.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from .config import PlateConfig
from .exporter import _mesh_stats, _write_3mf
from .mesh import write_binary_stl
from .tiles import _need_shapely, mesh_from_solid

WIDTH_MM, HEIGHT_MM = 70.0, 60.0
LINE_WIDTHS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5)
GAPS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8)
DOTS = (0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0)
HOLES = (0.4, 0.6, 0.8)


def build_plate_solid():
    """Raised area of the test plate in plate millimetres (x right, y up)."""
    _need_shapely()
    from shapely.geometry import Point, box
    from shapely.ops import unary_union

    parts = []
    # Row 1 (top): single lines, thinnest on the left.
    x = 6.0
    for width in LINE_WIDTHS:
        parts.append(box(x, 40, x + width, 56))
        x += width + 3.0
    # Row 2: two 1 mm bars with a gap of known size between them.
    x = 6.0
    for gap in GAPS:
        parts.append(box(x, 22, x + 1.0, 36))
        parts.append(box(x + 1.0 + gap, 22, x + 2.0 + gap, 36))
        x += 2.0 + gap + 5.0
    # Row 3: dots, and small squares with a hole.
    x = 6.0
    for diameter in DOTS:
        parts.append(Point(x + diameter / 2, 10).buffer(diameter / 2, 24))
        x += diameter + 3.5
    x += 2.0
    holes = []
    for diameter in HOLES:
        parts.append(box(x, 4, x + 5.0, 16))
        holes.append(Point(x + 2.5, 10).buffer(diameter / 2, 24))
        x += 5.0 + 3.0
    return unary_union(parts).difference(unary_union(holes))


def write_test_plate(directory: Path, config: PlateConfig) -> list[Path]:
    """STL, 3MF and a legend; returns the written files."""
    directory.mkdir(parents=True, exist_ok=True)
    base, top = config.base_height_mm, config.base_height_mm + config.relief_height_mm
    vertices, triangles = mesh_from_solid(build_plate_solid(), WIDTH_MM, HEIGHT_MM, base, top)
    stats = _mesh_stats(vertices, triangles)
    if stats["mesh_boundary_edges"] or stats["mesh_nonmanifold_edges"]:
        raise RuntimeError(f"test plate mesh is not closed: {stats}")
    stl, mf, legend = (directory / name for name in ("curvepress_test_plate.stl", "curvepress_test_plate.3mf", "TEST_PLATE.md"))
    write_binary_stl(stl, vertices, triangles)
    _write_3mf(mf, vertices, triangles)
    legend.write_text(_legend(config), encoding="utf-8")
    return [stl, mf, legend]


def write_test_plate_zip(path: Path, config: PlateConfig) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as temporary:
        files = write_test_plate(Path(temporary), config)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in files:
                archive.write(item, item.name)


def _legend(config: PlateConfig) -> str:
    total = config.base_height_mm + config.relief_height_mm
    fmt = lambda values: ", ".join(f"{v:g}" for v in values)  # noqa: E731
    return f"""# テスト板 / Test plate

{WIDTH_MM:g} × {HEIGHT_MM:g} mm、厚み {total:.1f} mm（土台 {config.base_height_mm:g} + 凸 {config.relief_height_mm:g}）。
ノズル {config.nozzle_mm:g} mm・積層 {config.layer_height_mm:g} mm の設定で作った板です。**ふだんの版と同じスライサー設定で印刷してください。**
向きは反転なし（読めるのは印刷面を上から見たとき）。

## 読み方（上から順に）

1. **上段：細い線**（左から {fmt(LINE_WIDTHS)} mm）。最後まで途切れず、高さがそろって立つ一番細い線が、あなたのプリンタの「最小の線の太さ」です。
2. **中段：すき間**（1 mmの棒2本のあいだが左から {fmt(GAPS)} mm）。すき間がふさがらず見える一番狭いものが「最小のすき間」です。
3. **下段：点と穴**（点の直径 {fmt(DOTS)} mm、ブロック中央の穴 {fmt(HOLES)} mm）。点が丸く立ち、穴が抜けている一番小さいものを確認します。

## 結果の使いかた

- 線が出ない・すき間がふさがるときは、スライサーの「XY寸法補正」を0.05 mmずつ変えて、同じ板をもう一度印刷します。
- 版の線を、見つけた最小の線の太さより細くしないでください（アプリの「細部」を下げる、または絵を単純にする）。
- 結果の小さい順に、ノズルを 0.2 / 0.4 mm と変えて比べると、細密な絵に向くかどうかが分かります。

---

# English

{WIDTH_MM:g} x {HEIGHT_MM:g} mm, {total:.1f} mm thick. Print it with the same slicer profile as your real plates (nozzle {config.nozzle_mm:g} mm, layers {config.layer_height_mm:g} mm). Not mirrored: it reads correctly seen from above.

1. **Top row - lines** ({fmt(LINE_WIDTHS)} mm, left to right): the thinnest line that stands unbroken at full height is your minimum line width.
2. **Middle row - gaps** (between two 1 mm bars: {fmt(GAPS)} mm): the narrowest gap that stays open is your minimum gap.
3. **Bottom row - dots and holes** (dots {fmt(DOTS)} mm, holes in the blocks {fmt(HOLES)} mm): check the smallest dot that is round and the smallest hole that is open.

If lines vanish or gaps close, change the slicer's XY size compensation in 0.05 mm steps and print the plate again. Keep your artwork's lines and gaps above the sizes you found.
"""
