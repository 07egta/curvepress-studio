"""A short, plate-specific printing guide written next to every export.

The numbers come from the plate that was just generated (layer-aligned heights,
mirroring, plate count, trap width) combined with community practice for 3D
printed relief plates; see ``docs/RESEARCH.md`` for the sources.
"""
from __future__ import annotations

from .config import PlateConfig
from .tiles import plan_tiles

TYPE_HIGH_MM = 23.32  # 0.918 in, the usual letterpress type height


def type_high_shim_mm(total_height_mm: float) -> float:
    """Build-up still needed under the plate to reach type-high (never negative)."""
    return round(max(0.0, TYPE_HIGH_MM - total_height_mm), 2)


def build_guide(config: PlateConfig, plate_names: list[str]) -> str:
    total = config.base_height_mm + config.relief_height_mm
    plates = len(plate_names)
    multi = plates > 1
    shim = type_high_shim_mm(total)
    tiles = plan_tiles(config)
    cols, rows = len({t.col for t in tiles}), len({t.row for t in tiles})
    order_ja = " → ".join(reversed(plate_names))
    ja = [
        "# 印刷ガイド / Printing guide",
        "",
        f"この版専用のメモです。サイズ {config.width_mm:g} × {config.height_mm:g} mm、"
        f"厚み {total:.1f} mm（土台 {config.base_height_mm:g} + 凸 {config.relief_height_mm:g}）、版 {plates} 枚。",
        "",
        "## スライサー設定",
        "",
        f"- 積層ピッチ {config.layer_height_mm:g} mm、ノズル {config.nozzle_mm:g} mm。土台と凸の高さは積層ピッチの整数倍にそろえてあります。",
        "- 素材はPLA。壁4周・天面5層・サポートなし・**天面アイロニングON**（凸の面がなめらかになり、インクののりが良くなります）。",
        "- 細い線がつぶれる／太る場合は「XY寸法補正」を0.05 mmずつ変えて試作（0.4 mmノズルで0.15 mmが効いたという報告があります）。",
        "- 向き：土台を下、絵を上。",
        (
            "- 左右反転済みのデータです。**スライサー側では反転しないでください**（刷ると正しい向きになります）。"
            if config.mirror_for_print
            else "- 反転していないデータです。刷って正しい向きにするには、スライサーでX方向に反転してください。"
        ),
        "- 印刷後、気になる凸のざらつきは400〜800番のヤスリで1分以内に軽くならす程度で十分です。",
        "",
        "## 刷るとき",
        "",
        "- 水性インクなら、石けんとお湯＋歯ブラシで洗えます（溝に残りやすいので念入りに）。",
        "- 全体がうすいときは、インクを足すより、圧力を均一にして薄く2回ローラーを転がすほうが効きます。",
    ]
    if multi:
        ja += [
            "",
            "## 多色刷り",
            "",
            f"- 刷る順番は **明るい色 → 暗い色**：{order_ja}",
            "- 見当（けんとう）：各版の右下の「かぎ」(L字)と左下の「ひきつけ」(直線)に、紙の角と下辺を当てて位置を決めます。見当の凸は刷り上がりには出ません。",
            (
                f"- トラッピング：明るい色の版を、暗い色の下に約{max(1 / config.pixels_per_mm, config.trap_mm):.2f} mm広げてあります。"
                "紙の側には広がらないので絵は変わらず、見当が少しズレても白い隙間が出にくくなります。"
                if config.trap_mm > 0
                else "- トラッピングはオフです。見当がズレると色の境目に白い隙間が出ます。"
            ),
        ]
    if len(tiles) > 1:
        ja += [
            "",
            "## 分割して印刷（タイル）",
            "",
            f"- ベッド {config.bed_mm:g} mm に収まるよう、各版を横{cols}×縦{rows}＝{len(tiles)}枚に切ってあります。ファイル名の `r行c列` は、刷る面を上から見たときの位置（r1c1が左上）です。",
            "- 平らな台紙（MDF・アクリル・厚いチップボード）に、すき間なく突き合わせて貼ります。切り口は平らなので、定規を当てて端をそろえてください。",
            "- 各タイルは同じ厚み・同じ向き（反転済み）で出力しています。",
        ]
    ja += [
        "",
        "## 活版（type-high）で使うとき",
        "",
        f"活版の標準の高さ（type-high）は 0.918 in ＝ {TYPE_HIGH_MM} mm です。この版は {total:.1f} mm なので、"
        + (f"台紙や厚紙で約 **{shim} mm** かさ上げすると届きます。" if shim > 0 else "すでに type-high 以上です。")
        + "削るより足すほうが簡単です。ノギスで測りながら、チップボードなどを貼って調整してください。お使いの活字・レールの高さに合わせるのが基準です。",
    ]
    en = [
        "",
        "---",
        "",
        "## English",
        "",
        f"Plate {config.width_mm:g} × {config.height_mm:g} mm, {total:.1f} mm thick "
        f"({config.base_height_mm:g} base + {config.relief_height_mm:g} relief), {plates} plate(s).",
        "",
        "**Slicer** - PLA, "
        f"{config.layer_height_mm:g} mm layers / {config.nozzle_mm:g} mm nozzle (base and relief are layer-aligned), 4 walls, 5 top layers, no supports, **top-surface ironing on**. "
        "If fine lines fill in or thin out, step XY size compensation by 0.05 mm (a community report found 0.15 mm helped on a 0.4 mm nozzle). Print base-down.",
        "",
        (
            "**Mirroring** - the data is already mirrored; do not mirror again in the slicer."
            if config.mirror_for_print
            else "**Mirroring** - the data is not mirrored; mirror along X in the slicer so the print reads correctly."
        ),
        "",
        "**Printing** - water-based ink washes off with soap, hot water and a toothbrush. If a print is faint, even out the pressure and roll two thin coats rather than adding ink.",
    ]
    if multi:
        en += [
            "",
            f"**Colour order** - lightest to darkest: {' -> '.join(reversed(plate_names))}. Push the paper corner and bottom edge against the kagi (L) and hikitsuke (bar) registration ridges; they do not print.",
            (
                f"**Trapping** - lighter plates are spread about {max(1 / config.pixels_per_mm, config.trap_mm):.2f} mm under the darker plates. "
                "The spread never reaches bare paper, so the picture is unchanged but small misregistration will not leave white gaps."
                if config.trap_mm > 0
                else "**Trapping** - off; misregistration will show white gaps at colour borders."
            ),
        ]
    if len(tiles) > 1:
        en += [
            "",
            f"**Tiles** - to fit the {config.bed_mm:g} mm bed each plate is cut into {cols} x {rows} = {len(tiles)} tiles. "
            "`rNcM` in the file name is the position seen from above (r1c1 = top left). Butt them edge to edge on a flat backing board (MDF, acrylic, thick chipboard) and square the edges with a ruler.",
        ]
    en += [
        "",
        f"**Letterpress** - type-high is 0.918 in = {TYPE_HIGH_MM} mm. This plate is {total:.1f} mm, so "
        + (f"add about {shim} mm of chipboard or card underneath." if shim > 0 else "it already meets type-high.")
        + " Build up rather than grind down, and check with calipers against your own type and rails.",
        "",
    ]
    return "\n".join(ja + en)
