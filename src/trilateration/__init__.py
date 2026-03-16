"""Trilateration package for strix parliaments.

Provides TDOA-based acoustic source localization from a fleet of strix nodes.
"""

from src.trilateration.engine import TrilaterationEngine
from src.trilateration.models import Detection, TriangulationResult
from src.trilateration.server import TrilaterationServer

__all__ = [
    "TrilaterationEngine",
    "TrilaterationServer",
    "Detection",
    "TriangulationResult",
]
