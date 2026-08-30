from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import PlateConfig, STYLES
from .exporter import CadUnavailable, export_analysis
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
    ).resolved()


def convert_command(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = _config_from_args(args)
    result = analyze_image(Path(args.image).read_bytes(), config, output)
    reports: list[dict] = []
    if not args.svg_only:
        try:
            reports = export_analysis(result, config)
        except CadUnavailable as exc:
            raise SystemExit(f"{exc}\nUse --svg-only if you do not need STEP/3MF/STL.") from exc
    summary = {
        "job": result.job_id,
        "directory": str(result.directory),
        "warnings": result.warnings,
        "metrics": result.metrics,
        "exports": reports,
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
    convert.add_argument("--title")
    convert.add_argument("--invert", action="store_true")
    convert.add_argument("--no-mirror", action="store_true")
    convert.add_argument("--svg-only", action="store_true")
    convert.set_defaults(func=convert_command)

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

