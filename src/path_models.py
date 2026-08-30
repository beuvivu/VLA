from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

# Build a stable "rawdata digit stream" from ALL prizes each day.
# We reconstruct each field with zero-fill to keep positions stable.
# This makes "paths" reproducible even when source stores numbers as int.

FIELD_WIDTHS: List[Tuple[str, int]] = [
    ("special", 5),
    ("prize1", 5),
    ("prize2_1", 5),
    ("prize2_2", 5),
    ("prize3_1", 5),
    ("prize3_2", 5),
    ("prize3_3", 5),
    ("prize3_4", 5),
    ("prize3_5", 5),
    ("prize3_6", 5),
    ("prize4_1", 4),
    ("prize4_2", 4),
    ("prize4_3", 4),
    ("prize4_4", 4),
    ("prize5_1", 4),
    ("prize5_2", 4),
    ("prize5_3", 4),
    ("prize5_4", 4),
    ("prize5_5", 4),
    ("prize5_6", 4),
    ("prize6_1", 3),
    ("prize6_2", 3),
    ("prize6_3", 3),
    ("prize7_1", 2),
    ("prize7_2", 2),
    ("prize7_3", 2),
    ("prize7_4", 2),
]

# Precompute position metadata: index -> (field, digit_index_in_field)
_POSITION_LABELS: List[str] | None = None
_SCOPE_INDICES: Dict[str, List[int]] | None = None


def _build_position_labels() -> List[str]:
    labels: List[str] = []
    for field, width in FIELD_WIDTHS:
        # digit order: d0..d{width-1} (left->right)
        for k in range(width):
            labels.append(f"{field}.d{k}")
    return labels


def get_position_labels() -> List[str]:
    global _POSITION_LABELS
    if _POSITION_LABELS is None:
        _POSITION_LABELS = _build_position_labels()
    return _POSITION_LABELS


def index_to_label(idx: int) -> str:
    labels = get_position_labels()
    if idx < 0 or idx >= len(labels):
        return f"pos{idx}"
    return labels[idx]


def get_scope_indices(scope: str) -> List[int]:
    """Return allowed indices for a given scope.

    scope:
      - all: all digits from all prizes
      - near_special: digits from special + prize1 + prize2
      - special_only: digits from special only
    """
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
    """Flatten all prizes into a digit array (0..9) with stable positions."""
    parts: List[str] = []
    for field, width in FIELD_WIDTHS:
        v = int(row[field])
        parts.append(str(v).zfill(width))
    s = "".join(parts)
    return np.fromiter((ord(ch) - 48 for ch in s), dtype=np.uint8)


def enumerate_position_pairs(P: int) -> tuple[np.ndarray, np.ndarray]:
    """Unique pairs i<j."""
    I, J = np.triu_indices(P, k=1)
    return I.astype(np.int16), J.astype(np.int16)


def build_daily_targets(df_2digits: pd.DataFrame) -> tuple[list[date], list[set[int]], list[int]]:
    """Build day-level targets.

    - loto_targets[t]: set of 2-digit numbers appearing in that day (00..99)
    - de_targets[t]: 2-digit special (00..99)
    """
    dates: list[date] = [d.to_pydatetime().date() for d in pd.to_datetime(df_2digits["date"])]
    cols = [c for c in df_2digits.columns if c != "date"]

    loto_targets: list[set[int]] = []
    de_targets: list[int] = []

    for _, r in df_2digits.iterrows():
        vals = [int(r[c]) for c in cols]
        loto_targets.append(set(vals))
        de_targets.append(int(r["special"]) % 100)

    return dates, loto_targets, de_targets


@dataclass(frozen=True)
class PathParams:
    # Similar to website controls:
    # - "Biên ngày cầu chạy": anchor date (handled in run_path_ui)
    # - "Số ngày cầu chạy": window_days (training window) and display_days (UI)
    lag_max: int = 30
    window_days: int = 365

    # Bayesian smoothing for hit probability per day
    alpha: float = 1.0
    beta: float = 1.0

    # Ignore rules with too few trials
    min_trials: int = 60

    # Two streak filters:
    min_max_streak: int = 3        # ever had a 3+ hit streak
    min_current_streak: int = 3    # currently running 3+ hit streak up to anchor day

    # Cap per lag to keep runtime stable
    top_rules_per_lag: int = 300
