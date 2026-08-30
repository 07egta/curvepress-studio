from __future__ import annotations

import base64
import json
import mimetypes
import threading
import traceback
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import PlateConfig
from .exporter import export_analysis
from .models import AnalysisResult
from .pipeline import analyze_image


STATIC_ROOT = Path(__file__).with_name("static")
JOBS: dict[str, AnalysisResult] = {}
EXPORTS: dict[str, dict] = {}
LOCK = threading.Lock()
OUTPUT_ROOT = Path("curvepress-output").resolve()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _artifact_url(job_id: str, name: str) -> str:
    return f"/api/artifact/{job_id}/{name}"


def _analysis_payload(result: AnalysisResult) -> dict:
    return {
        "job_id": result.job_id,
        "metrics": result.metrics,
        "warnings": result.warnings,
        "previews": {
            "source": _artifact_url(result.job_id, "source.png"),
            "corrected": _artifact_url(result.job_id, "corrected.png"),
            "print": _artifact_url(result.job_id, "print-preview.png"),
            "curves": _artifact_url(result.job_id, "curve-preview.png"),
        },
        "layers": [
            {
                "name": layer.name,
                "color": layer.color_hex,
                "mask": _artifact_url(result.job_id, f"{layer.name}-mask.png"),
                "svg": _artifact_url(result.job_id, f"{layer.name}.svg"),
            }
            for layer in result.layers
        ],
    }


def _bundle(result: AnalysisResult) -> Path:
    path = result.directory / f"CurvePress_{result.job_id}.zip"
    names = [
        item
        for item in result.directory.iterdir()
        if item.is_file() and item != path and item.suffix.lower() in {
            ".png", ".svg", ".step", ".stl", ".3mf", ".json"
        }
    ]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(names):
            archive.write(item, item.name)
    return path


def _run_export(job_id: str, config: PlateConfig) -> None:
    try:
        with LOCK:
            result = JOBS[job_id]
            EXPORTS[job_id] = {"state": "running", "message": "Building CAD solids…"}
        reports = export_analysis(result, config)
        bundle = _bundle(result)
        files = []
        for report in reports:
            files.extend(report["files"])
        files.append(bundle.name)
        with LOCK:
            EXPORTS[job_id] = {
                "state": "done",
                "message": "STEP read-back and closed-mesh checks passed.",
                "reports": reports,
                "files": [
                    {"name": name, "url": _artifact_url(job_id, name)} for name in sorted(set(files))
                ],
            }
    except Exception as exc:
        with LOCK:
            EXPORTS[job_id] = {
                "state": "error",
                "message": str(exc),
                "detail": traceback.format_exc(limit=4),
            }


class CurvePressHandler(BaseHTTPRequestHandler):
    server_version = "CurvePress/0.1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[CurvePress] {self.address_string()} {fmt % args}")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 44 * 1024 * 1024:
            raise ValueError("request is empty or exceeds 44 MB")
        return json.loads(self.rfile.read(length))

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path == "/api/health":
            self._json(200, {"ok": True, "version": "0.1.1"})
            return
        if path.startswith("/api/export/"):
            job_id = path.rsplit("/", 1)[-1]
            with LOCK:
                state = EXPORTS.get(job_id, {"state": "idle"})
            self._json(200, state)
            return
        if path.startswith("/api/artifact/"):
            parts = path.split("/", 4)
            if len(parts) != 5:
                self._json(404, {"error": "artifact not found"})
                return
            _, _, _, job_id, name = parts
            with LOCK:
                result = JOBS.get(job_id)
            if result is None or Path(name).name != name:
                self._json(404, {"error": "artifact not found"})
                return
            file_path = result.directory / name
            if not file_path.is_file():
                self._json(404, {"error": "artifact not found"})
                return
            mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self._send(200, file_path.read_bytes(), mime)
            return
        if path in {"/", "/index.html"}:
            file_path = STATIC_ROOT / "index.html"
        else:
            file_path = STATIC_ROOT / path.lstrip("/")
        if file_path.is_file() and STATIC_ROOT in file_path.resolve().parents:
            mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self._send(200, file_path.read_bytes(), mime)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/analyze":
                data_url = str(payload.get("image", ""))
                if "," not in data_url:
                    raise ValueError("image data URL is missing")
                header, encoded = data_url.split(",", 1)
                if ";base64" not in header:
                    raise ValueError("image must use base64 data URL encoding")
                image_data = base64.b64decode(encoded, validate=True)
                config = PlateConfig.from_dict(payload.get("config", {}))
                result = analyze_image(image_data, config, OUTPUT_ROOT / "jobs")
                with LOCK:
                    JOBS[result.job_id] = result
                    EXPORTS[result.job_id] = {"state": "idle"}
                self._json(200, _analysis_payload(result))
                return
            if path == "/api/export":
                job_id = str(payload.get("job_id", ""))
                with LOCK:
                    result = JOBS.get(job_id)
                    current = EXPORTS.get(job_id, {})
                if result is None:
                    raise ValueError("analyze an image before export")
                if current.get("state") == "running":
                    self._json(202, current)
                    return
                config = PlateConfig.from_dict(result.metrics["auto_settings"])
                thread = threading.Thread(target=_run_export, args=(job_id, config), daemon=True)
                thread.start()
                self._json(202, {"state": "queued"})
                return
            self._json(404, {"error": "not found"})
        except Exception as exc:
            self._json(400, {"error": str(exc)})


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    output_root: Path | None = None,
    *,
    open_browser: bool = True,
) -> None:
    global OUTPUT_ROOT
    OUTPUT_ROOT = (output_root or Path("curvepress-output")).resolve()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), CurvePressHandler)
    url = f"http://{host}:{port}"
    print(f"CurvePress Studio is running at {url}")
    if open_browser and host in {"127.0.0.1", "localhost"}:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping CurvePress Studio.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()

