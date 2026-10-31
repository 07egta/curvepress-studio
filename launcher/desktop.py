"""Entry point for the self-contained Windows application."""
from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from curvepress import __version__
from curvepress.config import PlateConfig
from curvepress.exporter import _load_occ, export_analysis
from curvepress.pipeline import analyze_image
from curvepress.web import STATIC_ROOT, serve


def self_test() -> None:
    from PIL import Image, ImageDraw

    _load_occ()
    assert (STATIC_ROOT / 'index.html').is_file()
    assert (STATIC_ROOT / 'examples' / 'hokusai-great-wave.jpg').is_file()
    raw = io.BytesIO()
    image = Image.new('RGB', (100, 80), 'white')
    ImageDraw.Draw(image).ellipse((20, 20, 70, 60), fill='black')
    image.save(raw, 'PNG')
    with tempfile.TemporaryDirectory() as directory:
        config = PlateConfig(width_mm=30, height_mm=24, style='poster', analysis_ppm=4).resolved()
        result = analyze_image(raw.getvalue(), config, Path(directory))
        reports = export_analysis(result, config)
        assert reports[0]['step_solids'] == 1
        assert reports[0]['mesh_boundary_edges'] == 0
        assert reports[0]['mesh_nonmanifold_edges'] == 0
    print(json.dumps({'ok': True, 'version': __version__, 'cad_round_trip': True}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    url = f'http://127.0.0.1:{args.port}'
    try:
        with urlopen(url + '/api/health', timeout=1) as response:
            existing = json.load(response)
        if existing.get('ok') and existing.get('version') == __version__:
            if not args.no_browser:
                webbrowser.open(url)
            return
    except (OSError, ValueError):
        pass
    output = args.output or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CurvePress Studio' / 'output'
    serve(port=args.port, output_root=output, open_browser=not args.no_browser)


if __name__ == '__main__':
    main()
