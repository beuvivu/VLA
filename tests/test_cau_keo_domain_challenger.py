from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cau_keo_domain_challenger import (
    ALL_DOMAIN_FEATURES,
    CAP50_FEATURES,
    DOMAIN_FEATURE_GROUPS,
    PARTNER_FEATURES,
    POSITIVE_SKILL_EPS,
    _make_fold_plan,
    _make_folds,
    _positive_pair,
    _predict_proba_allowlisted,
    _trust_from_skill,
    augment_domain_features,
)


def _base_frame(anchor: str = "2026-09-01") -> pd.DataFrame:
    nums = np.arange(100, dtype=int)
    return pd.DataFrame(
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


def test_domain_feature_groups_are_six_unique_nonempty_families() -> None:
    assert set(DOMAIN_FEATURE_GROUPS) == {
        "partner",
        "cap_50",
        "bo",
        "bong",
        "cham",
        "tong",
    }
    assert all(DOMAIN_FEATURE_GROUPS.values())
    assert len(ALL_DOMAIN_FEATURES) == len(set(ALL_DOMAIN_FEATURES))
    assert set(PARTNER_FEATURES).isdisjoint(CAP50_FEATURES)


def test_augment_domain_features_respects_partner_cap50_bo_bong_cham_tong() -> None:
    out = augment_domain_features(_base_frame()).set_index("number")

    # Canonical partner is lộn/reverse: 12 <-> 21; doubles remain themselves.
    assert out.loc[12, "partner"] == "21"
    assert out.loc[0, "partner"] == "00"
    assert int(out.loc[12, "partner_freq_30d"]) == 21

    # Cặp-50 is a separate partition. Kép 00 pairs with bóng dương 55.
    assert out.loc[0, "cap50_partner"] == "55"
    assert out.loc[0, "cap50_pair_kind"] == "kep_bong"
    assert int(out.loc[0, "cap50_is_kep_bong"]) == 1
    assert np.isclose(
        float(out.loc[0, "cap50_pair_freq_30_mean"]), (0 + 55) / 2
    )

    # A non-double cặp-50 partner coincides with reverse by definition.
    assert out.loc[12, "cap50_partner"] == "21"
    assert out.loc[12, "cap50_pair_kind"] == "reverse"

    # Bóng dương/âm use the canonical ontology.
    assert out.loc[0, "bong_duong_partner"] == "55"
    assert out.loc[0, "bong_am_partner"] == "77"
    assert int(out.loc[0, "bong_duong_freq_30d"]) == 55
    assert int(out.loc[0, "bong_am_freq_30d"]) == 77

    # Bộ 01 contains 01,06,10,15,51,56,60,65.
    expected_bo_mean = np.mean([1, 6, 10, 15, 51, 56, 60, 65])
    assert np.isclose(float(out.loc[1, "bo_freq_30d_mean"]), expected_bo_mean)
    assert int(out.loc[1, "bo_family_size"]) == 8

    all_hit = _base_frame()
    all_hit["hit_today"] = 1
    all_hit_out = augment_domain_features(all_hit)
    assert np.allclose(all_hit_out["cham_hit_today_rate"], 1.0)
    assert np.allclose(all_hit_out["tong_hit_today_rate"], 1.0)


def test_domain_augmentation_preserves_row_order_and_same_anchor_isolation() -> None:
    older = _base_frame("2026-08-31")
    newer = _base_frame("2026-09-01")
    newer["freq_30d"] = newer["freq_30d"] + 1000
    frame = pd.concat([newer, older], ignore_index=True)
    out = augment_domain_features(frame)
    assert out.index.equals(frame.index)
    latest = out[out["anchor_date"] == "2026-09-01"].set_index("number")
    past = out[out["anchor_date"] == "2026-08-31"].set_index("number")
    assert int(latest.loc[12, "partner_freq_30d"]) == 1021
    assert int(past.loc[12, "partner_freq_30d"]) == 21


def test_four_walk_forward_folds_are_strictly_chronological() -> None:
    days = pd.date_range("2025-01-01", periods=300, freq="D")
    folds = _make_folds(pd.DatetimeIndex(days))
    assert len(folds) == 4
    for fold in folds:
        assert fold.calib_start < fold.val_start
        if fold.val_end is not None:
            assert fold.val_start < fold.val_end
    assert (
        folds[0].val_start
        < folds[1].val_start
        < folds[2].val_start
        < folds[3].val_start
    )


def test_fold_plan_reuses_one_training_sample_for_all_challengers() -> None:
    days = pd.date_range("2025-01-01", periods=300, freq="D")
    frame = pd.DataFrame(
        {
            "anchor_date": np.repeat(days, 100),
            "number": np.tile(np.arange(100), len(days)),
        }
    )
    y = np.zeros(len(frame), dtype=int)
    for d in range(len(days)):
        y[d * 100 + d % 100] = 1
    fold = _make_folds(pd.DatetimeIndex(days))[0]
    a = _make_fold_plan(frame, y, fold=fold, mode="de")
    b = _make_fold_plan(frame, y, fold=fold, mode="de")
    assert a.seed == b.seed
    assert a.sample_signature == b.sample_signature
    assert np.array_equal(a.train_keep, b.train_keep)
    assert not np.any(a.train_mask & a.calib_mask)
    assert not np.any(a.train_mask & a.val_mask)
    assert not np.any(a.calib_mask & a.val_mask)


def test_production_gate_requires_strictly_positive_both_metrics() -> None:
    eps = POSITIVE_SKILL_EPS
    assert eps == 0.0
    assert _positive_pair(0.001, 0.002) is True
    assert _positive_pair(0.001, 0.0) is False
    assert _positive_pair(-0.01, 0.02) is False
    assert _trust_from_skill(-0.01, 0.02) == 0.0
    assert 0.0 < _trust_from_skill(0.02, 0.01) <= 0.30


def test_rejected_feature_extreme_values_cannot_change_allowlisted_inference() -> None:
    class SumModel:
        def predict_proba(self, x: np.ndarray) -> np.ndarray:
            z = np.clip(x.sum(axis=1) / 10.0, 0.0, 1.0)
            return np.column_stack([1.0 - z, z])

    frame = pd.DataFrame(
        {
            "approved": [1.0, 2.0, 3.0],
            "rejected": [0.0, 0.0, 0.0],
        }
    )
    before = _predict_proba_allowlisted(SumModel(), frame, ["approved"])
    frame["rejected"] = [1e9, -1e9, 1e12]
    after = _predict_proba_allowlisted(SumModel(), frame, ["approved"])
    assert np.array_equal(before, after)
