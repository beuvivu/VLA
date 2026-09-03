from __future__ import annotations

import numpy as np
import pandas as pd

from cau_keo_domain_challenger import (
    DomainGateConfig,
    _downsample_relative_indices,
    _make_folds,
    _positive_pair,
    _predict_gated_probabilities,
    _trust_from_skill,
)
from cau_keo_feature_groups import (
    ALL_DOMAIN_FEATURES,
    DOMAIN_FEATURE_GROUPS,
    TONG_FEATURES,
    augment_domain_features,
)
from cau_keo_ml import FEATURE_COLS


def _base_frame(anchor: str = "2026-09-01") -> pd.DataFrame:
    nums = np.arange(100, dtype=int)
    frame = pd.DataFrame(
        {
            "anchor_date": [anchor] * 100,
            "predict_for_date": ["2026-09-02"] * 100,
            "mode": ["loto"] * 100,
            "number": nums,
            "number_str": [f"{n:02d}" for n in nums],
            "freq_7d": nums % 8,
            "freq_30d": nums,
            "freq_90d": nums * 2,
            "freq_365d": nums * 3,
            "gap": 100 - nums,
            "hit_today": (nums % 7 == 0).astype(int),
            "path_support": nums * 0.5,
        }
    )
    for col in FEATURE_COLS:
        if col not in frame.columns:
            frame[col] = 0.0
    return frame


def test_domain_feature_groups_are_six_unique_nonempty_families() -> None:
    assert list(DOMAIN_FEATURE_GROUPS) == [
        "partner",
        "cap_50",
        "bo",
        "bong",
        "cham",
        "tong",
    ]
    assert all(DOMAIN_FEATURE_GROUPS.values())
    assert len(ALL_DOMAIN_FEATURES) == len(set(ALL_DOMAIN_FEATURES))
    assert set(DOMAIN_FEATURE_GROUPS["partner"]).isdisjoint(
        DOMAIN_FEATURE_GROUPS["cap_50"]
    )


def test_augment_domain_features_respects_canonical_semantics() -> None:
    out = augment_domain_features(_base_frame()).set_index("number")

    assert out.loc[0, "cap50_partner"] == "55"
    assert out.loc[0, "cap50_pair_kind"] == "kep_bong"
    assert int(out.loc[0, "cap50_partner_freq_30d"]) == 55
    assert int(out.loc[0, "cap50_is_kep_bong"]) == 1

    assert out.loc[12, "cap50_partner"] == "21"
    assert out.loc[12, "cap50_pair_kind"] == "reverse"
    assert int(out.loc[12, "cap50_partner_freq_30d"]) == 21

    assert out.loc[0, "bong_duong_partner"] == "55"
    assert out.loc[0, "bong_am_partner"] == "77"
    assert int(out.loc[0, "bong_duong_freq_30d"]) == 55
    assert int(out.loc[0, "bong_am_freq_30d"]) == 77

    expected_bo_mean = np.mean([1, 6, 10, 15, 51, 56, 60, 65])
    assert np.isclose(float(out.loc[1, "bo_freq_30d_mean"]), expected_bo_mean)
    assert int(out.loc[1, "bo_family_size"]) == 8

    all_hit = _base_frame()
    all_hit["hit_today"] = 1
    all_hit_out = augment_domain_features(all_hit)
    assert np.allclose(all_hit_out["cham_hit_today_rate"], 1.0)
    assert np.allclose(all_hit_out["tong_hit_today_rate"], 1.0)


def test_domain_augmentation_preserves_row_order_and_has_no_cross_anchor_mixing() -> None:
    a = _base_frame("2026-08-31")
    b = _base_frame("2026-09-01")
    b["freq_30d"] = b["freq_30d"] + 1000
    frame = pd.concat([b, a], ignore_index=True)
    out = augment_domain_features(frame)
    assert out.index.equals(frame.index)
    newer = out[pd.to_datetime(out["anchor_date"]).dt.date == pd.Timestamp("2026-09-01").date()].set_index("number")
    older = out[pd.to_datetime(out["anchor_date"]).dt.date == pd.Timestamp("2026-08-31").date()].set_index("number")
    assert int(newer.loc[0, "cap50_partner_freq_30d"]) == 1055
    assert int(older.loc[0, "cap50_partner_freq_30d"]) == 55


def test_four_walk_forward_folds_are_strictly_chronological() -> None:
    days = pd.date_range("2025-01-01", periods=300, freq="D")
    folds = _make_folds(pd.DatetimeIndex(days), DomainGateConfig())
    assert len(folds) == 4
    for fold in folds:
        assert fold.calib_start < fold.val_start
        if fold.val_end is not None:
            assert fold.val_start < fold.val_end
    assert folds[0].val_start < folds[1].val_start < folds[2].val_start < folds[3].val_start


def test_controlled_downsampling_is_deterministic_for_same_fold_seed() -> None:
    y = np.array([1] * 20 + [0] * 500, dtype=int)
    a = _downsample_relative_indices(y, neg_ratio=8, seed=20260921)
    b = _downsample_relative_indices(y, neg_ratio=8, seed=20260921)
    c = _downsample_relative_indices(y, neg_ratio=8, seed=20260922)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_production_gate_requires_both_metrics_to_have_positive_skill() -> None:
    assert _positive_pair(0.001, 0.002) is True
    assert _positive_pair(0.001, 0.0) is False
    assert _positive_pair(-0.01, 0.02) is False
    assert _trust_from_skill(-0.01, 0.02) == 0.0
    assert 0.05 <= _trust_from_skill(0.02, 0.01) <= 0.30


class _ArrayModel:
    def predict_proba(self, values: np.ndarray) -> np.ndarray:
        score = 0.15 + 0.10 * np.tanh(values.astype(float).sum(axis=1) / 1000.0)
        score = np.clip(score, 1e-6, 1.0 - 1e-6)
        return np.column_stack([1.0 - score, score])


def test_rejected_feature_extremes_cannot_change_production_prediction() -> None:
    frame = augment_domain_features(_base_frame()).reset_index(drop=True)
    production_features = list(FEATURE_COLS) + list(DOMAIN_FEATURE_GROUPS["partner"])
    model = _ArrayModel()

    _, _, before = _predict_gated_probabilities(
        frame,
        baseline_model=model,
        challenger_model=model,
        production_features=production_features,
        trust=0.20,
    )
    mutated = frame.copy()
    for col in TONG_FEATURES:
        mutated[col] = 1e9
    _, _, after = _predict_gated_probabilities(
        mutated,
        baseline_model=model,
        challenger_model=model,
        production_features=production_features,
        trust=0.20,
    )
    assert np.allclose(before, after, atol=0.0, rtol=0.0)
