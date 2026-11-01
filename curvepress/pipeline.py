from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .config import PlateConfig
from .curves import contour_regions, cubic_segments, curve_counts, regions_svg, sample_segments
from .image_pipeline import (
    composite_preview,
    correct_illumination,
    fit_on_plate,
    load_image,
    make_masks,
    mask_preview,
)
from .models import AnalysisResult, PlateLayer
from .proof import make_heightmap, make_proof


def _save_curve_preview(layers: list[PlateLayer], config: PlateConfig) -> Image.Image:
    ppm = config.analysis_ppm
    width, height = int(round(config.width_mm * ppm)), int(round(config.height_mm * ppm))
    image = Image.new("RGB", (width, height), (43, 58, 48))
    draw = ImageDraw.Draw(image)
    single_layer = len(layers) == 1

    def sampled(points):
        return [tuple(p) for p in (sample_segments(cubic_segments(points)) * ppm).tolist()]

    for layer in reversed(layers):
        color = (238, 174, 54) if single_layer else tuple(
            int(layer.color_hex[i : i + 2], 16) for i in (1, 3, 5)
        )
        for region in layer.regions:
            draw.polygon(sampled(region.outer), fill=color)
            for hole in region.holes:
                draw.polygon(sampled(hole), fill=(43, 58, 48))
    return ImageOps.mirror(image) if config.mirror_for_print else image


def write_proof(layers: list[PlateLayer], config: PlateConfig, directory: Path) -> Path:
    path = directory / "proof-preview.png"
    temporary = directory / ".proof-preview.tmp.png"
    make_proof(layers, config).save(temporary, compress_level=1)
    temporary.replace(path)
    return path


def analyze_image(
    data: bytes,
    raw_config: PlateConfig | dict,
    output_root: Path | None = None,
    *,
    defer_proof: bool = False,
) -> AnalysisResult:
    """Analyse an image into printable plate layers.

    With ``defer_proof`` the (relatively slow) washi proof is not rendered
    here; call :func:`write_proof` later, e.g. from a background thread, so an
    interactive UI can show the plate immediately.
    """
    config = (
        raw_config.resolved()
        if isinstance(raw_config, PlateConfig)
        else PlateConfig.from_dict(raw_config)
    )
    source_original = load_image(data)
    source, content_box = fit_on_plate(source_original, config)
    corrected = correct_illumination(source, config.contrast)
    mask_layers, cleanup_reports = make_masks(corrected, config, content_box, source)

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
    if not config.mirror_for_print:
        print_preview = ImageOps.mirror(print_preview)
    curve_preview = _save_curve_preview(layers, config)
    source.save(directory / "source.png", compress_level=1)
    corrected.save(directory / "corrected.png", compress_level=1)
    print_preview.save(directory / "print-preview.png", compress_level=1)
    curve_preview.save(directory / "curve-preview.png", compress_level=1)
    if not defer_proof:
        write_proof(layers, config, directory)
    for layer in layers:
        mask_preview(layer.mask, layer.color_hex).save(directory / f"{layer.name}-mask.png", compress_level=1)
        (directory / f"{layer.name}.svg").write_text(layer.svg, encoding="utf-8")
        make_heightmap(layer, config).save(directory / f"{layer.name}-height.png", compress_level=1)

    total_segments = sum(item["bezier_segments"] for item in all_metrics)
    # ``notes`` are machine-readable (the UI translates them); ``warnings``
    # keeps the English sentences for the CLI and the JSON report.
    notes: list[dict] = []
    if max(config.width_mm, config.height_mm) > 180:
        notes.append({"code": "bed_a1mini", "text": "Plate exceeds the A1 mini 180 × 180 mm bed; use a larger printer or reduce the size."})
    for item in all_metrics:
        name = item["name"]
        if item["regions"] > 1600:
            notes.append({"code": "step_skipped", "layer": name, "n": item["regions"], "text": f"{name}: {item['regions']} regions exceed the STEP limit of 1,600; 3MF/STL/SVG are fine. Increase dot spacing or lower detail if you need STEP."})
        if item["fragile_fraction"] > 0.22:
            notes.append({"code": "fragile", "layer": name, "text": f"{name}: fine-detail risk is high; use Arachne or lower detail"})
        if item["fill_ratio"] > 0.72:
            notes.append({"code": "heavy_ink", "layer": name, "text": f"{name}: ink coverage is high; roll a very thin film"})
    warnings = [note["text"] for note in notes]
    metrics = {
        "job_id": job_id,
        "plate_mm": [config.width_mm, config.height_mm],
        "base_height_mm": config.base_height_mm,
        "relief_height_mm": config.relief_height_mm,
        "total_height_mm": config.base_height_mm + config.relief_height_mm,
        "mirrored_for_print": config.mirror_for_print,
        "registration_marks": config.uses_registration(),
        "notes": notes,
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


