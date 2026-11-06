from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .calibrate import calibration_config_from_request, write_calibration
from .config import PlateConfig, STYLES
from .exporter import CadUnavailable, cad_available, export_analysis, export_meshes
from .pipeline import analyze_image


def _config_from_args(args: argparse.Namespace) -> PlateConfig:
    return PlateConfig(
        width_mm=args.width,
        height_mm=args.height,
        nozzle_mm=args.nozzle,
        layer_height_mm=args.layer_height,
        base_height_mm=args.base,
        relief_height_mm=args.relief,
        style=args.style,
        detail=args.detail,
        contrast=args.contrast,
        color_count=args.colors,
        invert=args.invert,
        mirror_for_print=not args.no_mirror,
        title=args.title or Path(args.image).stem,
        halftone_pitch_mm=args.dot_pitch,
        remove_scan_frame=not args.keep_scan_frame,
        trap_mm=args.trap,
        minimum_width_mm=args.min_width,
    ).resolved()


def _step_failure(exc: BaseException) -> bool:
    """True when STEP/CAD failed after the printable mesh was already valid."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, CadUnavailable):
            return True
        text = str(current)
        if "OpenCascade is not installed" in text or text.startswith("STEP export failed"):
            return True
        current = current.__cause__ or current.__context__
    return False


def convert_command(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = _config_from_args(args)
    result = analyze_image(Path(args.image).read_bytes(), config, output)
    reports: list[dict] = []
    step_warning = None
    if not args.svg_only:
        if cad_available():
            try:
                reports = export_analysis(result, config)
            except Exception as exc:
                if not _step_failure(exc):
                    raise
                export_meshes(result, config)
                step_warning = (
                    f"STEP was not written ({exc}). 3MF and STL were still written; "
                    "those are the files to slice."
                )
        else:
            export_meshes(result, config)
            step_warning = (
                "OpenCascade is not installed, so STEP was not written. "
                "3MF and STL are in the output folder and are what the slicer needs. "
                "Install the CAD extra for STEP: pip install -e '.[cad]'"
            )
    summary = {
        "job": result.job_id,
        "directory": str(result.directory),
        "warnings": result.warnings,
        "step_warning": step_warning,
        "metrics": result.metrics,
        "exports": reports,
        "meshes": sorted(path.name for path in result.directory.glob("*.stl")),
    }
    if step_warning:
        print(step_warning, file=sys.stderr)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def calibrate_command(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    config = calibration_config_from_request(
        {
            "nozzle_mm": args.nozzle,
            "layer_height_mm": args.layer_height,
            "base_height_mm": args.base,
            "relief_height_mm": args.relief,
        }
    )
    written = write_calibration(output, config)
    summary = {
        "directory": str(output),
        "files": written["files"],
        "bounds_mm": written["bounds_mm"],
        "bars_mm": written["bars_mm"],
        "gaps_mm": written["gaps_mm"],
        "mesh": written["mesh"],
        "note": "Not mirrored. Open CALIBRATION.md, then slice the 3MF or STL.",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def serve_command(args: argparse.Namespace) -> int:
    from .web import serve

    serve(args.host, args.port, Path(args.output).resolve(), open_browser=not args.no_browser)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="curvepress",
        description="Convert images into curve-based printable relief plates.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("convert", help="analyze and export one image")
    convert.add_argument("image")
    convert.add_argument("-o", "--output", default="curvepress-output")
    convert.add_argument("--style", choices=sorted(STYLES), default="woodcut")
    convert.add_argument("--width", type=float, default=139.0)
    convert.add_argument("--height", type=float, default=83.0)
    convert.add_argument("--nozzle", type=float, default=0.40)
    convert.add_argument("--layer-height", type=float, default=0.20)
    convert.add_argument("--base", type=float)
    convert.add_argument("--relief", type=float)
    convert.add_argument("--detail", type=float, default=0.68)
    convert.add_argument("--contrast", type=float, default=0.55)
    convert.add_argument("--colors", type=int, default=3)
    convert.add_argument("--trap", type=float, default=0.20, help="colour plates: spread lighter inks this many mm under darker ones (0 = off)")
    convert.add_argument("--title")
    convert.add_argument("--invert", action="store_true")
    convert.add_argument("--no-mirror", action="store_true")
    convert.add_argument("--svg-only", action="store_true")
    convert.add_argument("--dot-pitch", type=float, default=1.7, help="halftone dot spacing in mm")
    convert.add_argument("--min-width", type=float, default=None, help="minimum raised line width in mm (default: from the nozzle)")
    convert.add_argument("--keep-scan-frame", action="store_true", help="preserve the full source image edges")
    convert.set_defaults(func=convert_command)

    calibrate = sub.add_parser("calibrate", help="write a nozzle test strip (STL, 3MF, SVG)")
    calibrate.add_argument("-o", "--output", default="curvepress-output/nozzle-test")
    calibrate.add_argument("--nozzle", type=float, default=0.40)
    calibrate.add_argument("--layer-height", type=float, default=0.20)
    calibrate.add_argument("--base", type=float)
    calibrate.add_argument("--relief", type=float)
    calibrate.set_defaults(func=calibrate_command)

    server = sub.add_parser("serve", help="open the local CurvePress Studio UI")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("-o", "--output", default="curvepress-output")
    server.add_argument(
        "--no-browser",
        action="store_true",
        help="start the local server without opening a browser window",
    )
    server.set_defaults(func=serve_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


