"""Đặc trưng soi cầu kinh điển, số hóa thành ma trận cho mô hình học máy."""

from features.base import (
    FeatureContext,
    FeatureExtractor,
    FeatureMatrix,
    validate_block,
)
from features.double_hit import DoubleHitBridgeExtractor
from features.geometric import GeometricBridgeExtractor, pascal_reduce
from features.pattern_memory import PatternMemoryExtractor
from features.registry import FeatureRegistry
from features.special_set import DAN_SIZES, SpecialSetExtractor, touches

__all__ = [
    "DAN_SIZES",
    "DoubleHitBridgeExtractor",
    "FeatureContext",
    "FeatureExtractor",
    "FeatureMatrix",
    "FeatureRegistry",
    "GeometricBridgeExtractor",
    "PatternMemoryExtractor",
    "SpecialSetExtractor",
    "default_registry",
    "pascal_reduce",
    "touches",
    "validate_block",
]


def default_registry() -> FeatureRegistry:
    """Sổ đăng ký với đủ bốn extractor trong đặc tả."""
    registry = FeatureRegistry()
    registry.register(GeometricBridgeExtractor())
    registry.register(DoubleHitBridgeExtractor())
    registry.register(PatternMemoryExtractor())
    registry.register(SpecialSetExtractor())
    return registry
