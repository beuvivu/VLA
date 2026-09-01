from __future__ import annotations

"""Availability-aware helpers for ensemble component probability artifacts.

A missing or malformed component must never be represented as a legitimate
all-zero probability vector.  That representation silently contaminates both
walk-forward weight learning and the production blend.  These helpers keep
availability explicit and only normalize/weight components that really exist.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from ensemble_utils import EnsembleWeights, normalize_distribution

Mode = Literal["loto", "de"]
COMPONENT_KEYS = ("ml", "cau", "stat", "active", "stable")


@dataclass(frozen=True)
class ComponentVector:
    prob: np.ndarray
    available: bool
    reason: str


def probability_component(df: pd.DataFrame, *, mode: Mode) -> ComponentVector:
    """Validate one full 00..99 probability artifact.

    Missing, partial, duplicate, non-finite, out-of-range, or all-zero artifacts
    are unavailable.  For De, a valid vector is normalized to a categorical
    distribution.  For Loto, Bernoulli marginals are kept as-is.
    """
    missing = np.full(100, np.nan, dtype=np.float64)
    if df is None or df.empty:
        return ComponentVector(missing, False, "missing_or_empty")
    if "number" not in df.columns or "prob" not in df.columns:
        return ComponentVector(missing, False, "missing_number_or_prob_column")

    numbers = pd.to_numeric(df["number"], errors="coerce")
    probs = pd.to_numeric(df["prob"], errors="coerce")
    valid_rows = numbers.notna() & probs.notna()
    if int(valid_rows.sum()) != 100:
        return ComponentVector(missing, False, "not_exactly_100_numeric_rows")

    n = numbers.loc[valid_rows].astype(int).to_numpy()
    p = probs.loc[valid_rows].astype(float).to_numpy()
    if len(np.unique(n)) != 100 or set(n.tolist()) != set(range(100)):
        return ComponentVector(missing, False, "number_universe_not_00_99")
    if not np.isfinite(p).all() or np.any((p < 0.0) | (p > 1.0)):
        return ComponentVector(missing, False, "probability_out_of_range_or_nonfinite")

    order = np.argsort(n)
    p = p[order]
    if float(np.sum(p)) <= 0.0:
        return ComponentVector(missing, False, "all_zero_probability_vector")

    if mode == "de":
        p = normalize_distribution(p)
    return ComponentVector(np.asarray(p, dtype=np.float64), True, "ok")


def availability_from_history_day(sub: pd.DataFrame) -> dict[str, bool]:
    """Resolve component availability for one 100-row history day.

    New history rows carry explicit ``has_*`` flags.  Older rows are accepted
    only when their probability column is complete, finite, in range, and has
    positive total mass; this prevents legacy all-zero placeholders from being
    mistaken for real model output.
    """
    out: dict[str, bool] = {}
    if len(sub) != 100:
        return {key: False for key in COMPONENT_KEYS}

    for key in COMPONENT_KEYS:
        p_col = f"p_{key}"
        has_col = f"has_{key}"
        if p_col not in sub.columns:
            out[key] = False
            continue
        values = pd.to_numeric(sub[p_col], errors="coerce").to_numpy(dtype=float)
        valid = (
            values.shape == (100,)
            and np.isfinite(values).all()
            and np.all((values >= 0.0) & (values <= 1.0))
            and float(values.sum()) > 0.0
        )
        if has_col in sub.columns:
            flags = sub[has_col].fillna(False).astype(bool).to_numpy()
            valid = valid and bool(flags.all())
        out[key] = bool(valid)
    return out


def renormalize_available_weights(
    weights: EnsembleWeights, available: dict[str, bool]
) -> EnsembleWeights:
    """Renormalize configured weights over components that are actually present."""
    raw = np.array(
        [weights.w_ml, weights.w_cau, weights.w_stat, weights.w_active, weights.w_stable],
        dtype=float,
    )
    mask = np.array([bool(available.get(key, False)) for key in COMPONENT_KEYS], dtype=float)
    effective = raw * mask
    total = float(effective.sum())
    if total <= 0.0:
        raise ValueError("No valid ensemble component is available")
    effective /= total
    return EnsembleWeights(
        w_ml=float(effective[0]),
        w_cau=float(effective[1]),
        w_stat=float(effective[2]),
        w_active=float(effective[3]),
        w_stable=float(effective[4]),
    )
