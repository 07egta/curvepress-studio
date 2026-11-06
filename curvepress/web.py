from __future__ import annotations

import base64
import json
import mimetypes
import threading
import traceback
import webbrowser
import zipfile
import hashlib
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import __version__
from .config import PlateConfig
from .calibrate import calibration_config_from_request, calibration_zip
from .exporter import cad_available, export_analysis, export_meshes
from .models import AnalysisResult
from .pipeline import analyze_image, write_proof


STATIC_ROOT = Path(__file__).with_name("static")
JOBS: dict[str, AnalysisResult] = {}
EXPORTS: dict[str, dict] = {}
LOCK = threading.Lock()
CAD_LOCK = threading.Lock()
MAX_JOBS = 12
# Recently uploaded images, so re-tuning a style does not resend megabytes.
IMAGES: "OrderedDict[str, bytes]" = OrderedDict()
MAX_IMAGES = 6
# Set when a job's deferred proof + ZIP bundle are on disk.
FINISHED: dict[str, threading.Event] = {}
SLOW_ARTIFACTS = {"proof-preview.png"}
OUTPUT_ROOT = Path("curvepress-output").resolve()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _artifact_url(job_id: str, name: str) -> str:
    return f"/api/artifact/{job_id}/{name}"


def _title(result: AnalysisResult) -> str:
    return str(result.metrics.get("auto_settings", {}).get("title") or "curvepress_plate")


def _analysis_payload(result: AnalysisResult) -> dict:
    return {
        "job_id": result.job_id,
        "bundle": _artifact_url(result.job_id, f"CurvePress_{result.job_id}.zip"),
        "metrics": result.metrics,
        "warnings": result.warnings,
        "previews": {
            "source": _artifact_url(result.job_id, "source.png"),
            "corrected": _artifact_url(result.job_id, "corrected.png"),
            "print": _artifact_url(result.job_id, "print-preview.png"),
            "curves": _artifact_url(result.job_id, "curve-preview.png"),
            "proof": _artifact_url(result.job_id, "proof-preview.png"),
        },
        "guide": _artifact_url(result.job_id, "PRINT_GUIDE.md"),
        "layers": [
            {
                "name": layer.name,
                "color": layer.color_hex,
                "mask": _artifact_url(result.job_id, f"{layer.name}-mask.png"),
                "svg": _artifact_url(result.job_id, f"{layer.name}.svg"),
                "height": _artifact_url(result.job_id, f"{layer.name}-height.png"),
                "stl": _artifact_url(result.job_id, f"{_title(result)}_{layer.name}.stl"),
                "3mf": _artifact_url(result.job_id, f"{_title(result)}_{layer.name}.3mf"),
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
            ".png", ".svg", ".step", ".stl", ".3mf", ".json", ".md"
        }
    ]
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(names):
            archive.write(item, item.name)
    temporary.replace(path)
    return path


def _finish_job(result: AnalysisResult, config: PlateConfig, done: threading.Event) -> None:
    try:
        try:
            export_meshes(result, config)
        except Exception:
            traceback.print_exc()
        write_proof(result.layers, config, result.directory)
        _bundle(result)
    except Exception:  # a missing proof must never break the plate itself
        traceback.print_exc()
    finally:
        done.set()


def _remember_image(data: bytes) -> str:
    image_id = hashlib.sha256(data).hexdigest()[:24]
    with LOCK:
        IMAGES[image_id] = data
        IMAGES.move_to_end(image_id)
        while len(IMAGES) > MAX_IMAGES:
            IMAGES.popitem(last=False)
    return image_id


def _run_export(job_id: str, config: PlateConfig) -> None:
    try:
        with CAD_LOCK:
            with LOCK:
                result = JOBS[job_id]
                EXPORTS[job_id] = {"state": "running", "message": "Building CAD solids…"}
            reports = export_analysis(result, config)
        with LOCK:
            done = FINISHED.get(job_id)
        if done is not None:
            done.wait(timeout=120)  # include the proof in the final ZIP
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
    server_version = f"CurvePress/{__version__}"

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
        if self.headers.get_content_type() != "application/json":
            raise ValueError("request must use application/json")
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            raise ValueError("cross-origin requests are not allowed")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("request must be a JSON object")
        return data

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path == "/api/health":
            self._json(200, {"ok": True, "version": __version__, "cad_available": cad_available()})
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
            if name in SLOW_ARTIFACTS or name.endswith((".zip", ".stl", ".3mf")):
                with LOCK:
                    done = FINISHED.get(job_id)
                if done is not None:
                    done.wait(timeout=120)
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
                image_id = str(payload.get("image_id", ""))
                with LOCK:
                    image_data = IMAGES.get(image_id) if image_id else None
                if image_data is None:
                    data_url = str(payload.get("image", ""))
                    if "," not in data_url:
                        if image_id:
                            raise LookupError("image_expired")
                        raise ValueError("image data URL is missing")
                    header, encoded = data_url.split(",", 1)
                    if ";base64" not in header:
                        raise ValueError("image must use base64 data URL encoding")
                    image_data = base64.b64decode(encoded, validate=True)
                image_id = _remember_image(image_data)
                config = PlateConfig.from_dict(payload.get("config", {}))
                result = analyze_image(image_data, config, OUTPUT_ROOT / "jobs", defer_proof=True)
                done = threading.Event()
                with LOCK:
                    while len(JOBS) >= MAX_JOBS:
                        expired = next((key for key in JOBS if EXPORTS.get(key, {}).get("state") not in {"queued", "running"}), None)
                        if expired is None:
                            raise ValueError("Too many exports are active; wait for an export to finish")
                        JOBS.pop(expired)
                        EXPORTS.pop(expired, None)
                        FINISHED.pop(expired, None)
                    JOBS[result.job_id] = result
                    EXPORTS[result.job_id] = {"state": "idle"}
                    FINISHED[result.job_id] = done
                threading.Thread(target=_finish_job, args=(result, config, done), daemon=True).start()
                self._json(200, {**_analysis_payload(result), "image_id": image_id})
                return
            if path == "/api/calibrate":
                raw = payload.get("config", {})
                blob = calibration_zip(calibration_config_from_request(raw if isinstance(raw, dict) else {}))
                self._send(200, blob, "application/zip")
                return
            if path == "/api/export":
                job_id = str(payload.get("job_id", ""))
                with LOCK:
                    result = JOBS.get(job_id)
                    if result is None:
                        raise ValueError("analyze an image before export")
                    current = EXPORTS.get(job_id, {})
                    if current.get("state") in {"queued", "running", "done"}:
                        self._json(202, current)
                        return
                    config = PlateConfig.from_dict(result.metrics["auto_settings"])
                    EXPORTS[job_id] = {"state": "queued", "message": "Waiting for CAD export…"}
                thread = threading.Thread(target=_run_export, args=(job_id, config), daemon=True)
                try:
                    thread.start()
                except Exception:
                    with LOCK:
                        EXPORTS[job_id] = {"state": "error", "message": "Could not start export; retry."}
                    raise
                self._json(202, {"state": "queued"})
                return
            self._json(404, {"error": "not found"})
        except LookupError as exc:
            self._json(409, {"error": str(exc)})
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


