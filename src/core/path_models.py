from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from numbers import Integral, Real

import numpy as np
import pandas as pd

from core.xsmb_domain import FIELD_WIDTHS as XSMB_FIELD_WIDTHS


FIELD_WIDTHS = XSMB_FIELD_WIDTHS

_POSITION_LABELS: list[str] | None = None
_SCOPE_INDICES: dict[str, list[int]] | None = None


def _build_position_labels() -> list[str]:
    labels: list[str] = []
    for field, width in FIELD_WIDTHS:
        for k in range(width):
            labels.append(f"{field}.d{k}")
    return labels


def get_position_labels() -> list[str]:
    global _POSITION_LABELS
    if _POSITION_LABELS is None:
        _POSITION_LABELS = _build_position_labels()
    return _POSITION_LABELS


def index_to_label(idx: int) -> str:
    labels = get_position_labels()
    if idx < 0 or idx >= len(labels):
        return f"pos{idx}"
    return labels[idx]


def get_scope_indices(scope: str) -> list[int]:
    global _SCOPE_INDICES
    if _SCOPE_INDICES is None:
        labels = get_position_labels()
        special_idx = [i for i, lab in enumerate(labels) if lab.startswith("special.")]
        near = [i for i, lab in enumerate(labels) if lab.startswith("special.") or lab.startswith("prize1.") or lab.startswith("prize2_")]
        _SCOPE_INDICES = {
            "all": list(range(len(labels))),
            "near_special": near,
            "special_only": special_idx,
        }
    if scope not in _SCOPE_INDICES:
        raise ValueError(f"Unknown scope: {scope}. Use one of {list(_SCOPE_INDICES.keys())}")
    return _SCOPE_INDICES[scope]


def build_rawdata_digits_from_row(row: pd.Series) -> np.ndarray:
    parts: list[str] = []
    for field, width in FIELD_WIDTHS:
        v = int(row[field])
        parts.append(str(v).zfill(width))
    s = "".join(parts)
    return np.fromiter((ord(ch) - 48 for ch in s), dtype=np.uint8)


def enumerate_position_pairs(P: int) -> tuple[np.ndarray, np.ndarray]:
    I, J = np.triu_indices(P, k=1)
    return I.astype(np.int16), J.astype(np.int16)


def build_daily_targets(df_2digits: pd.DataFrame) -> tuple[list[date], list[set[int]], list[int]]:
    dates: list[date] = [d.to_pydatetime().date() for d in pd.to_datetime(df_2digits["date"])]
    cols = [c for c in df_2digits.columns if c != "date"]

    values = df_2digits[cols].to_numpy(dtype=np.int64, copy=False) % 100
    special = (df_2digits["special"].to_numpy(dtype=np.int64, copy=False) % 100)

    loto_targets: list[set[int]] = [set(row.tolist()) for row in values]
    de_targets: list[int] = special.tolist()

    return dates, loto_targets, de_targets


@dataclass(frozen=True)
class PathParams:
    lag_max: int = 30
    window_days: int = 365

    alpha: float = 1.0
    beta: float = 1.0

    min_trials: int = 60

    min_max_streak: int = 3
    min_current_streak: int = 3

    top_rules_per_lag: int = 300

    def __post_init__(self) -> None:
        positive_integer_fields = (
            "lag_max",
            "window_days",
            "min_trials",
            "top_rules_per_lag",
        )
        nonnegative_integer_fields = ("min_max_streak", "min_current_streak")
        for name in positive_integer_fields:
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        for name in nonnegative_integer_fields:
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer")
        if (
            isinstance(self.alpha, bool)
            or not isinstance(self.alpha, Real)
            or not np.isfinite(self.alpha)
            or self.alpha < 0.0
        ):
            raise ValueError("alpha must be finite and >= 0")
        if (
            isinstance(self.beta, bool)
            or not isinstance(self.beta, Real)
            or not np.isfinite(self.beta)
            or self.beta < 0.0
        ):
            raise ValueError("beta must be finite and >= 0")
