# Local API

The CurvePress Studio API is intended for local use on `127.0.0.1`. It does not provide authentication or defenses for exposure to the public internet.

## `POST /api/analyze`

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
    "mirror_for_print": true
  }
}
```

Returns preview URLs, per-plate SVG files, physical and curve metrics, and warnings.

## `POST /api/export`

```json
{"job_id": "returned-job-id"}
```

Starts background generation of STEP/3MF/STL files and validation JSON.

## `GET /api/export/{job_id}`

Returns `idle`, `queued`, `running`, `done`, or `error`. The `done` response includes download URLs.

## `GET /api/artifact/{job_id}/{filename}`

Returns a generated preview, SVG, CAD file, or validation result.

