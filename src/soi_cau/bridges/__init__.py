"""Quét cầu tọa độ ghép chéo ngày, kèm cổng kiểm định bắt buộc."""

from soi_cau.bridges.scanner import (
    NUMBER_SPACE,
    SHADOW_KINDS,
    TARGET_TYPES,
    TRANSFORMATIONS,
    BridgeScanner,
    BridgeScanResult,
    CrossDayPatternSpec,
    DigitTensor,
    apply_shadow,
    default_lag_pairs,
    shadow_table,
    target_baseline_rate,
)

__all__ = [
    "NUMBER_SPACE",
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
