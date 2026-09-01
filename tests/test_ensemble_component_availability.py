from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ensemble_components import (
    availability_from_history_day,
    probability_component,
    renormalize_available_weights,
)
from ensemble_utils import EnsembleWeights
from learn_ensemble_weights import _select_recent_complete_days
from record_pred_history import _sanitize_history


def _frame(value: float = 0.2) -> pd.DataFrame:
    return pd.DataFrame({"number": np.arange(100), "prob": np.full(100, value)})


def test_missing_or_zero_component_is_unavailable() -> None:
    missing = probability_component(pd.DataFrame(columns=["number", "prob"]), mode="loto")
    zero = probability_component(_frame(0.0), mode="loto")
    assert not missing.available
    assert not zero.available
    assert np.isnan(missing.prob).all()
    assert zero.reason == "all_zero_probability_vector"


def test_stale_dated_component_is_unavailable() -> None:
    frame = _frame(0.2)
    frame["predict_for_date"] = "2026-08-31"
    stale = probability_component(
        frame,
        mode="loto",
        expected_target_date="2026-09-01",
    )
    assert stale.available is False
    assert stale.reason == "stale_predict_for_date"


def test_de_component_is_normalized_only_when_valid() -> None:
    comp = probability_component(_frame(0.2), mode="de")
    assert comp.available
    assert np.isclose(comp.prob.sum(), 1.0)


def test_available_weights_are_renormalized_without_missing_component() -> None:
    base = EnsembleWeights(w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125)
    effective = renormalize_available_weights(
        base,
        {"ml": True, "cau": False, "stat": True, "active": True, "stable": True},
    )
    assert effective.w_cau == 0.0
    assert np.isclose(sum(effective.as_dict().values()), 1.0)
    assert effective.w_ml > base.w_ml


def test_no_available_component_fails_loudly() -> None:
    base = EnsembleWeights(w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125)
    with pytest.raises(ValueError, match="No valid ensemble component"):
        renormalize_available_weights(base, {k: False for k in ["ml", "cau", "stat", "active", "stable"]})


def _history_day(day: str, *, zero_component: str | None = None, explicit_flags: bool = False) -> pd.DataFrame:
    y = np.zeros(100, dtype=int)
    y[0] = 1
    data: dict[str, object] = {
        "target_date": [day] * 100,
        "number": np.arange(100),
        "y": y,
    }
    for key in ["ml", "cau", "stat", "active", "stable"]:
        p = np.full(100, 0.2, dtype=float)
        if key == zero_component:
            p[:] = 0.0
        data[f"p_{key}"] = p
        if explicit_flags:
            data[f"has_{key}"] = [key != zero_component] * 100
    return pd.DataFrame(data)


def test_legacy_all_zero_placeholder_is_rejected_by_weight_learner() -> None:
    good = _history_day("2026-08-01")
    bad = _history_day("2026-08-02", zero_component="cau")
    df = pd.concat([good, bad], ignore_index=True)
    assert _select_recent_complete_days(df, 180) == ["2026-08-01"]


def test_history_sanitizer_migrates_old_zero_placeholder() -> None:
    old = _history_day("2026-08-02", zero_component="cau")
    clean = _sanitize_history(old)
    assert clean["has_ml"].all()
    assert not clean["has_cau"].any()
    assert clean["p_cau"].isna().all()


def test_explicit_string_false_availability_is_not_truthy() -> None:
    sub = _history_day("2026-08-01")
    for key in ["ml", "cau", "stat", "active", "stable"]:
        sub[f"has_{key}"] = "True"
    sub["has_stat"] = "False"
    available = availability_from_history_day(sub)
    assert available["ml"] is True
    assert available["stat"] is False
