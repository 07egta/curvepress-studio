"""CurvePress Studio — images to curve-based printable relief plates."""

from .config import PlateConfig
from .pipeline import analyze_image

__all__ = ["PlateConfig", "analyze_image"]
__version__ = "0.1.1"

