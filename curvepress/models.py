from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(slots=True)
class CurveRegion:
    outer: np.ndarray
    holes: list[np.ndarray] = field(default_factory=list)


@dataclass(slots=True)
class PlateLayer:
    name: str
    color_hex: str
    mask: np.ndarray
    regions: list[CurveRegion]
    svg: str


@dataclass(slots=True)
class AnalysisResult:
    job_id: str
    source: Image.Image
    corrected: Image.Image
    layers: list[PlateLayer]
    print_preview: Image.Image
    curve_preview: Image.Image
    metrics: dict
    warnings: list[str]
    directory: Path

