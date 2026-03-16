"""Audio signal processing nodes for strix."""

from src.processing.processing_nodes import (
    BufferSplitterNode,
    ClippingDetectorNode,
    DCRemovalNode,
    GainNode,
    HighPassFilterNode,
    MonoConversionNode,
    NormalizationNode,
    RMSCalculatorNode,
)

__all__ = [
    "MonoConversionNode",
    "HighPassFilterNode",
    "GainNode",
    "BufferSplitterNode",
    "RMSCalculatorNode",
    "DCRemovalNode",
    "NormalizationNode",
    "ClippingDetectorNode",
]
