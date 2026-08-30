from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .config import PlateConfig
from .curves import contour_regions, curve_counts, regions_svg
from .image_pipeline import (
    composite_preview,
    correct_illumination,
    fit_on_plate,
    load_image,
    make_masks,
    mask_preview,
)
from .models import AnalysisResult, PlateLayer


def _save_curve_preview(layers: list[PlateLayer], config: PlateConfig) -> Image.Image:
    ppm = config.analysis_ppm
    width, height = int(round(config.width_mm * ppm)), int(round(config.height_mm * ppm))
    image = Image.new("RGB", (width, height), (43, 58, 48))
    draw = ImageDraw.Draw(image)
    single_layer = len(layers) == 1
    for layer in reversed(layers):
        color = (238, 174, 54) if single_layer else tuple(
            int(layer.color_hex[i : i + 2], 16) for i in (1, 3, 5)
        )
        for region in layer.regions:
            outer = [(round(x * ppm), round(y * ppm)) for x, y in region.outer]
            draw.polygon(outer, fill=color)
            for hole in region.holes:
                draw.polygon([(round(x * ppm), round(y * ppm)) for x, y in hole], fill=(43, 58, 48))
    return image


def analyze_image(
    data: bytes,
    raw_config: PlateConfig | dict,
    output_root: Path | None = None,
) -> AnalysisResult:
    config = (
        raw_config.resolved()
        if isinstance(raw_config, PlateConfig)
        else PlateConfig.from_dict(raw_config)
    )
    source_original = load_image(data)
    source, content_box = fit_on_plate(source_original, config)
    corrected = correct_illumination(source, config.contrast)
    mask_layers, cleanup_reports = make_masks(corrected, config, content_box)

    layers: list[PlateLayer] = []
    all_metrics = []
    for (name, color, mask), cleanup in zip(mask_layers, cleanup_reports):
        regions = contour_regions(mask, config)
        if not regions:
            continue
        svg = regions_svg(regions, config, fill=color, title=f"CurvePress {name}")
        counts = curve_counts(regions)
        all_metrics.append({"name": name, **cleanup, **counts, "fill_ratio": float(np.mean(mask))})
        layers.append(PlateLayer(name=name, color_hex=color, mask=mask, regions=regions, svg=svg))
    if not layers:
        raise ValueError("curve fitting produced no valid regions")

    job_id = uuid.uuid4().hex[:12]
    base = output_root or Path(tempfile.gettempdir()) / "curvepress-jobs"
    directory = base / job_id
    directory.mkdir(parents=True, exist_ok=True)

    print_preview = composite_preview([(layer.name, layer.color_hex, layer.mask) for layer in layers])
    curve_preview = _save_curve_preview(layers, config)
    source.save(directory / "source.png")
    corrected.save(directory / "corrected.png")
    print_preview.save(directory / "print-preview.png")
    curve_preview.save(directory / "curve-preview.png")
    for layer in layers:
        mask_preview(layer.mask, layer.color_hex).save(directory / f"{layer.name}-mask.png")
        (directory / f"{layer.name}.svg").write_text(layer.svg, encoding="utf-8")

    total_segments = sum(item["bezier_segments"] for item in all_metrics)
    warnings = []
    for item in all_metrics:
        if item["fragile_fraction"] > 0.22:
            warnings.append(f"{item['name']}: fine-detail risk is high; use Arachne or lower detail")
        if item["fill_ratio"] > 0.72:
            warnings.append(f"{item['name']}: ink coverage is high; roll a very thin film")
    metrics = {
        "job_id": job_id,
        "plate_mm": [config.width_mm, config.height_mm],
        "base_height_mm": config.base_height_mm,
        "relief_height_mm": config.relief_height_mm,
        "total_height_mm": config.base_height_mm + config.relief_height_mm,
        "mirrored_for_print": config.mirror_for_print,
        "layers": all_metrics,
        "total_bezier_segments": total_segments,
        "auto_settings": config.public_dict(),
    }
    (directory / "analysis.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return AnalysisResult(
        job_id=job_id,
        source=source,
        corrected=corrected,
        layers=layers,
        print_preview=print_preview,
        curve_preview=curve_preview,
        metrics=metrics,
        warnings=warnings,
        directory=directory,
    )

