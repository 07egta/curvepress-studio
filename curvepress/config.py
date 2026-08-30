from __future__ import annotations

from dataclasses import asdict, dataclass
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
    title: str = "curvepress_plate"

    @staticmethod
    def _layer_round(value: float, layer: float) -> float:
        return round(max(layer, round(value / layer) * layer), 4)

    def resolved(self) -> "PlateConfig":
        if self.style not in STYLES:
            raise ValueError(f"unknown style: {self.style}")
        if not (20 <= self.width_mm <= 256 and 20 <= self.height_mm <= 256):
            raise ValueError("plate dimensions must be between 20 and 256 mm")
        if not (0.2 <= self.nozzle_mm <= 1.2):
            raise ValueError("nozzle diameter must be between 0.2 and 1.2 mm")
        if not (0.05 <= self.layer_height_mm <= 0.5):
            raise ValueError("layer height must be between 0.05 and 0.5 mm")

        data = asdict(self)
        layer = self.layer_height_mm
        data["base_height_mm"] = self.base_height_mm or self._layer_round(
            max(0.80, self.nozzle_mm * 2.0), layer
        )
        data["relief_height_mm"] = self.relief_height_mm or self._layer_round(
            max(1.00, self.nozzle_mm * 3.0), layer
        )
        data["edge_margin_mm"] = self.edge_margin_mm or max(2.00, self.nozzle_mm * 5.0)
        data["minimum_width_mm"] = self.minimum_width_mm or max(0.50, self.nozzle_mm * 1.25)
        data["minimum_gap_mm"] = self.minimum_gap_mm or max(0.50, self.nozzle_mm * 1.25)
        data["minimum_component_mm2"] = self.minimum_component_mm2 or (
            data["minimum_width_mm"] * 1.35
        ) ** 2
        # Tolerance scales with the nozzle but remains well below the printable line width.
        data["curve_tolerance_mm"] = self.curve_tolerance_mm or max(
            0.055, min(0.18, self.nozzle_mm * (0.18 + 0.18 * (1.0 - self.detail)))
        )
        data["analysis_ppm"] = int(max(4, min(12, self.analysis_ppm)))
        data["detail"] = float(max(0.0, min(1.0, self.detail)))
        data["contrast"] = float(max(0.0, min(1.0, self.contrast)))
        data["color_count"] = int(max(2, min(6, self.color_count)))
        data["title"] = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.title)[:80]
        return PlateConfig(**data)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PlateConfig":
        allowed = cls.__dataclass_fields__.keys()
        values = {key: value for key, value in raw.items() if key in allowed}
        for key in (
            "base_height_mm", "relief_height_mm", "edge_margin_mm", "minimum_width_mm",
            "minimum_gap_mm", "minimum_component_mm2", "curve_tolerance_mm",
        ):
            if values.get(key) in ("", None, "auto"):
                values[key] = None
        return cls(**values).resolved()

    def public_dict(self) -> dict[str, Any]:
        return asdict(self.resolved())

