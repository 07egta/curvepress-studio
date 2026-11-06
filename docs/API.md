# Local API

The CurvePress Studio API is intended for local use on `127.0.0.1`. It does not provide authentication or defenses for exposure to the public internet.

## `GET /api/health`

Returns `{"ok": true, "version": "0.3.2", "cad_available": false}`. `cad_available` is true only when the OpenCascade extra is installed. 3MF and STL do not need it.

## `POST /api/analyze`

Send `image` (data URL) or, to re-tune without re-uploading, the `image_id` returned by a previous call. An unknown `image_id` returns 409 `image_expired`; resend the image. The response also carries `metrics.notes` (`code`, `layer`, `n`) for translated warnings.


```json
{
  "image": "data:image/png;base64,...",
  "config": {
    "style": "woodcut",
    "width_mm": 139,
    "height_mm": 83,
    "nozzle_mm": 0.4,
    "layer_height_mm": 0.2,
    "detail": 0.68,
    "contrast": 0.55,
    "mirror_for_print": true,
    "minimum_width_mm": null
  }
}
```

Use Content-Type: application/json. Returns preview URLs, per-plate SVG files, an immediately downloadable analysis ZIP (`bundle`), physical and curve metrics, and warnings. Numeric strings are accepted for number settings; booleans must be JSON booleans.

## `POST /api/calibrate`

Builds a nozzle test strip from the printer settings and returns a ZIP (`nozzle_test_ink.stl`, `nozzle_test_ink.3mf`, `nozzle_test_ink.svg`, `CALIBRATION.md`). Artwork size and style in `config` are ignored. The plate is 120 × 96 mm and is not mirrored.

```json
{"config": {"nozzle_mm": 0.4, "layer_height_mm": 0.2, "base_height_mm": null, "relief_height_mm": null}}
```

## `POST /api/export`

```json
{"job_id": "returned-job-id"}
```

Queues background generation of STEP (plus refreshed 3MF/STL) and validation JSON. 3MF/STL for every plate are already available from `/api/analyze` (`layers[].stl`, `layers[].3mf`). Repeated requests for a queued, running, or completed job reuse that export. CAD work is serialized; files appear only after the complete set passes validation.

## `GET /api/export/{job_id}`

Returns `idle`, `queued`, `running`, `done`, or `error`. The `done` response includes download URLs.

## `GET /api/artifact/{job_id}/{filename}`

Returns a generated preview, SVG, CAD file, or validation result.



The server retains the 12 most recent inactive analyses in memory. Files remain in the output directory after eviction or server restart, but artifact URLs require an in-memory job. Active exports are not evicted.
