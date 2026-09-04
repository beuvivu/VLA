from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cau_keo_domain_challenger import (
    ALL_DOMAIN_FEATURES,
    DOMAIN_FEATURE_GROUPS,
    POSITIVE_SKILL_EPS,
    _make_folds,
    _positive_pair,
    _trust_from_skill,
    augment_domain_features,
    walk_forward_ablation,
)
from cau_keo_feature_groups import DOMAIN_FEATURE_SPECS
from ml_validation import evaluate_predictions


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


def test_domain_feature_groups_are_unique_and_nonempty() -> None:
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
    assert set(DOMAIN_FEATURE_SPECS) == set(DOMAIN_FEATURE_GROUPS)
    assert all(not spec.default_enabled for spec in DOMAIN_FEATURE_SPECS.values())
    assert all(
        spec.temporal_requirement == "same_anchor_only"
        for spec in DOMAIN_FEATURE_SPECS.values()
    )


def test_augment_domain_features_respects_partner_bo_bong_cham_tong_semantics() -> None:
    out = augment_domain_features(_base_frame()).set_index("number")

    # 00 is paired with 55 in the 50-pair partition; this is the special kép-bóng case.
    assert out.loc[0, "cap50_partner"] == "55"
    assert out.loc[0, "cap50_pair_kind"] == "kep_bong"
    assert int(out.loc[0, "cap50_partner_freq_30d"]) == 55
    assert int(out.loc[0, "cap50_is_kep_bong"]) == 1

    # A non-double uses its reverse as 50-pair partner.
    assert out.loc[12, "cap50_partner"] == "21"
    assert out.loc[12, "cap50_pair_kind"] == "reverse"
    assert int(out.loc[12, "cap50_partner_freq_30d"]) == 21

    # Bóng dương/âm use the canonical ontology, not an inferred co-occurrence pair.
    assert out.loc[0, "bong_duong_partner"] == "55"
    assert out.loc[0, "bong_am_partner"] == "77"
    assert int(out.loc[0, "bong_duong_freq_30d"]) == 55
    assert int(out.loc[0, "bong_am_freq_30d"]) == 77

    # Bộ 01 contains 01,06,10,15,51,56,60,65; group means are same-anchor only.
    expected_bo_mean = np.mean([1, 6, 10, 15, 51, 56, 60, 65])
    assert np.isclose(float(out.loc[1, "bo_freq_30d_mean"]), expected_bo_mean)
    assert int(out.loc[1, "bo_family_size"]) == 8

    # Every chạm union has 19 numbers; every modulo-10 total has 10 numbers.
    # Constant-one hit inputs make the group rate exactly one for both structures.
    all_hit = _base_frame()
    all_hit["hit_today"] = 1
    all_hit_out = augment_domain_features(all_hit)
    assert np.allclose(all_hit_out["cham_hit_today_rate"], 1.0)
    assert np.allclose(all_hit_out["tong_hit_today_rate"], 1.0)


def test_domain_augmentation_preserves_row_order_and_has_no_cross_anchor_leakage() -> None:
    a = _base_frame("2026-08-31")
    b = _base_frame("2026-09-01")
    b["freq_30d"] = b["freq_30d"] + 1000
    frame = pd.concat([b, a], ignore_index=True)
    out = augment_domain_features(frame)
    assert out.index.equals(frame.index)
    first_anchor = out[out["anchor_date"] == "2026-09-01"].set_index("number")
    older_anchor = out[out["anchor_date"] == "2026-08-31"].set_index("number")
    assert int(first_anchor.loc[0, "cap50_partner_freq_30d"]) == 1055
    assert int(older_anchor.loc[0, "cap50_partner_freq_30d"]) == 55


def test_domain_augmentation_preserves_duplicate_index_labels() -> None:
    frame = _base_frame().sample(frac=1.0, random_state=7)
    frame.index = np.arange(len(frame)) % 11
    expected_index = frame.index.copy()

    out = augment_domain_features(frame)

    assert out.index.equals(expected_index)
    assert out["number"].tolist() == frame["number"].tolist()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: pd.concat([frame, frame.iloc[[0]]]), "Mỗi ngày neo"),
        (
            lambda frame: frame.assign(
                freq_30d=np.where(frame["number"].eq(0), np.inf, frame["freq_30d"])
            ),
            "không hữu hạn",
        ),
        (
            lambda frame: frame.assign(
                anchor_date=np.where(frame["number"].eq(0), None, frame["anchor_date"])
            ),
            "Ngày neo không được để trống",
        ),
    ],
)
def test_domain_augmentation_rejects_ambiguous_or_nonfinite_rows(
    mutation,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        augment_domain_features(mutation(_base_frame()))


def test_four_walk_forward_folds_are_strictly_chronological() -> None:
    days = pd.date_range("2025-01-01", periods=300, freq="D")
    folds = _make_folds(pd.DatetimeIndex(days))
    assert len(folds) == 4
    for fold in folds:
        assert fold.calib_start < fold.val_start
        if fold.val_end is not None:
            assert fold.val_start < fold.val_end
    assert folds[0].val_start < folds[1].val_start < folds[2].val_start < folds[3].val_start


def test_production_gate_requires_both_metrics_to_have_positive_skill() -> None:
    eps = POSITIVE_SKILL_EPS
    assert _positive_pair(eps * 2, eps * 3) is True
    assert _positive_pair(eps * 2, 0.0) is False
    assert _positive_pair(-0.01, 0.02) is False
    assert _trust_from_skill(-0.01, 0.02) == 0.0
    assert 0.05 <= _trust_from_skill(0.02, 0.01) <= 0.30


def test_ablation_reuses_one_seed_per_fold_and_fails_back_to_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cau_keo_domain_challenger as module

    days = pd.date_range("2025-01-01", periods=300, freq="D")
    frame = pd.DataFrame({"anchor_date": days})
    y = pd.Series((np.arange(len(days)) % 2).astype(int))
    calls: list[tuple[int, int]] = []

    def fake_fit(
        data: pd.DataFrame,
        target: np.ndarray,
        *,
        features: list[str],
        fold: object,
        mode: str,
        seed: int,
    ):
        del features, mode
        calls.append((fold.fold, seed))
        _, _, valid = module._fold_masks(data, fold)
        return evaluate_predictions(
            target[valid],
            np.full(int(valid.sum()), 0.5),
            data.loc[valid, "anchor_date"].to_numpy(),
        )

    monkeypatch.setattr(module, "_fit_fold", fake_fit)
    _, gate = walk_forward_ablation(frame, y, mode="loto")

    for fold in range(1, 5):
        assert {seed for called_fold, seed in calls if called_fold == fold} == {
            20260920 + fold
        }
    assert sum(called_fold == 4 for called_fold, _ in calls) == 1
    assert gate["domain_active"] is False
    assert gate["selected_features"] == list(module.FEATURE_COLS)
    assert gate["final_evaluation"]["holdout_consumed"] is False
    assert gate["final_evaluation"]["oos_dates"] == 0
    manifest = gate["feature_manifest"]
    assert manifest["promoted_groups"] == []
    assert manifest["production_features"] == list(module.FEATURE_COLS)
