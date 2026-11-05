from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
from typing import Any


STYLES = {"woodcut", "line_art", "poster", "halftone", "color_layers"}


@dataclass(slots=True)
class PlateConfig:
    width_mm: float = 139.0
    height_mm: float = 83.0
    nozzle_mm: float = 0.40
    layer_height_mm: float = 0.20
    base_height_mm: float | None = None
    relief_height_mm: float | None = None
    edge_margin_mm: float | None = None
    minimum_width_mm: float | None = None
    minimum_gap_mm: float | None = None
    minimum_component_mm2: float | None = None
    curve_tolerance_mm: float | None = None
    analysis_ppm: int = 6
    style: str = "woodcut"
    detail: float = 0.68
    contrast: float = 0.55
    invert: bool = False
    mirror_for_print: bool = True
    remove_scan_frame: bool = True
    color_count: int = 3
    halftone_angle_deg: float = 15.0
    halftone_pitch_mm: float = 1.70
    halftone_min_dot_mm: float = 0.50
    halftone_max_dot_mm: float = 1.60
    registration_marks: bool = True
    registration_band_mm: float = 6.0
    trap_mm: float = 0.20
    proof_seed: int = 7
    title: str = "curvepress_plate"

    def uses_registration(self) -> bool:
        """Kento marks are only meaningful when several plates must line up."""
        return self.style == "color_layers" and self.registration_marks

    @staticmethod
    def _layer_round(value: float, layer: float) -> float:
        return round(max(layer, round(value / layer) * layer), 4)

    def resolved(self) -> "PlateConfig":
        data = asdict(self)
        optional = {
            "base_height_mm", "relief_height_mm", "edge_margin_mm", "minimum_width_mm",
            "minimum_gap_mm", "minimum_component_mm2", "curve_tolerance_mm",
        }
        flags = {"invert", "mirror_for_print", "remove_scan_frame", "registration_marks"}
        for field in fields(self):
            key, value = field.name, data[field.name]
            if key in {"title", "style"}:
                if not isinstance(value, str):
                    raise ValueError(f"{key} must be text")
                continue
            if key in flags:
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be true or false")
                continue
            if key in optional and value in (None, "", "auto"):
                data[key] = None
                continue
            try:
                if isinstance(value, bool):
                    raise ValueError
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{key} must be a finite number") from exc
            data[key] = number

        if data["style"] not in STYLES:
            raise ValueError(f"unknown style: {data['style']}")
        for key, low, high in (
            ("width_mm", 20, 256), ("height_mm", 20, 256), ("nozzle_mm", 0.2, 1.2),
            ("layer_height_mm", 0.05, 0.5), ("halftone_pitch_mm", 0.2, 20),
            ("halftone_min_dot_mm", 0.1, 20), ("halftone_max_dot_mm", 0.1, 20), ("trap_mm", 0.0, 1.0),
        ):
            if not low <= data[key] <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
        data["detail"] = max(0.0, min(1.0, data["detail"]))
        data["contrast"] = max(0.0, min(1.0, data["contrast"]))
        data["analysis_ppm"] = int(max(4, min(12, data["analysis_ppm"])))
        data["color_count"] = int(max(2, min(6, data["color_count"])))
        nozzle, layer = data["nozzle_mm"], data["layer_height_mm"]
        defaults = {
            "base_height_mm": max(0.8, nozzle * 2),
            "relief_height_mm": max(1.0, nozzle * 3),
            "edge_margin_mm": max(2.0, nozzle * 5),
            "minimum_width_mm": max(0.5, nozzle * 1.25),
            "minimum_gap_mm": max(0.5, nozzle * 1.25),
            "curve_tolerance_mm": max(0.055, min(0.18, nozzle * (0.36 - 0.18 * data["detail"]))),
        }
        for key, default in defaults.items():
            if data[key] is None:
                data[key] = default
        if data["minimum_component_mm2"] is None:
            data["minimum_component_mm2"] = (data["minimum_width_mm"] * 1.35) ** 2
        for key in optional:
            if data[key] < 0 or (key != "edge_margin_mm" and data[key] == 0):
                raise ValueError(f"{key} must be {'nonnegative' if key == 'edge_margin_mm' else 'positive'}")
        for key in ("base_height_mm", "relief_height_mm"):
            if data[key] > 20:
                raise ValueError(f"{key} must not exceed 20 mm")
            data[key] = self._layer_round(data[key], layer)
        if 2 * data["edge_margin_mm"] >= min(data["width_mm"], data["height_mm"]) - 2:
            raise ValueError("edge margin leaves less than 2 mm of artwork space")
        if data["halftone_min_dot_mm"] > min(data["halftone_max_dot_mm"], data["halftone_pitch_mm"] * 0.96):
            raise ValueError("halftone minimum dot must fit within the maximum dot and pitch")
        data["proof_seed"] = int(data["proof_seed"])
        if not 0 <= data["proof_seed"] < 2**32:
            raise ValueError("proof_seed must be between 0 and 2**32-1")
        data["registration_band_mm"] = max(4.0, min(14.0, data["registration_band_mm"]))
        if data["style"] == "color_layers" and data["registration_marks"] and 2 * data["edge_margin_mm"] + data["registration_band_mm"] >= data["height_mm"] - 2:
            raise ValueError("registration band leaves less than 2 mm of artwork space")
        data["title"] = "".join(c if c.isalnum() or c in "-_" else "_" for c in data["title"])[:80] or "curvepress_plate"
        return PlateConfig(**data)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PlateConfig":
        if not isinstance(raw, dict):
            raise ValueError("config must be an object")
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in raw.items() if key in allowed}).resolved()

    def public_dict(self) -> dict[str, Any]:
        return asdict(self.resolved())


