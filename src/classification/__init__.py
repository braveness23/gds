"""Acoustic event classifier plugin interface for strix.

Implement AcousticClassifier to add custom event classification.
"""

from src.classification.base import AcousticClassifier, ClassificationResult, RuleBasedClassifier

__all__ = [
    "AcousticClassifier",
    "RuleBasedClassifier",
    "ClassificationResult",
]
