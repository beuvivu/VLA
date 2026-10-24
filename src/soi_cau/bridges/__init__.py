"""Quét cầu tọa độ ghép chéo ngày, kèm cổng kiểm định bắt buộc."""

from soi_cau.bridges.scanner import BridgeScanner, BridgeScanResult, target_baseline_rate
from soi_cau.bridges.shadow import SHADOW_KINDS, apply_shadow, shadow_table
from soi_cau.bridges.spec import (
    TARGET_TYPES,
    TRANSFORMATIONS,
    CrossDayPatternSpec,
    default_lag_pairs,
)
from soi_cau.bridges.tensor import DigitTensor

__all__ = [
    "SHADOW_KINDS",
    "TARGET_TYPES",
    "TRANSFORMATIONS",
    "BridgeScanResult",
    "BridgeScanner",
    "CrossDayPatternSpec",
    "DigitTensor",
    "apply_shadow",
    "default_lag_pairs",
    "shadow_table",
    "target_baseline_rate",
]
