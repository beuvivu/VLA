from __future__ import annotations


import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from ensemble.ensemble_components import COMPONENT_POLICY, policy_column
from ensemble.ensemble_utils import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    EnsembleWeights,
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    finalize_blend,
    floor_distribution,
)
from ensemble.learn_ensemble_weights import (
    COMPONENT_COLS,
    MIN_RELATIVE_GAIN,
    MIN_VALIDATION_DAYS,
    PRIOR_VECTOR,
    _blend,
    _daily_scores,
    _promotion_verdict,
    _weight_vector,
    learn_with_holdout,
)

LOTO_RATE = 23.7657 / 100.0
SRC = Path(__file__).resolve().parents[2] / "src"


def _synthetic(
    mode: str, days: int, *, signal: float, seed: int
) -> tuple[dict[str, np.ndarray], np.ndarray, list[str]]:
    rng = np.random.default_rng(seed)
    day_list = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(days)]

    if mode == "loto":
        y = (rng.random((days, 100)) < LOTO_RATE).astype(float)
        arrays = {
            c: np.clip(LOTO_RATE + 0.02 * rng.standard_normal((days, 100)), 0.01, 0.99)
            for c in COMPONENT_COLS
        }
        arrays["p_cau"] = np.clip(arrays["p_cau"] + signal * (y - LOTO_RATE), 0.01, 0.99)
        return arrays, y, day_list

    winners = rng.integers(0, 100, size=days)
    y = np.zeros((days, 100), dtype=float)
    y[np.arange(days), winners] = 1.0
    arrays = {}
    for column in COMPONENT_COLS:
        base = np.full((days, 100), 0.01) + 0.002 * rng.standard_normal((days, 100))
        arrays[column] = np.clip(base, 1e-4, None)
    arrays["p_cau"][np.arange(days), winners] += signal
    for column in COMPONENT_COLS:
        arrays[column] /= arrays[column].sum(axis=1, keepdims=True)
    return arrays, y, day_list


def _mean_logloss(mode: str, arrays: dict[str, np.ndarray], y: np.ndarray, w: EnsembleWeights) -> float:
    return float(np.mean(_daily_scores(mode, _blend(arrays, _weight_vector(w)), y)[0]))


def _slice(arrays: dict[str, np.ndarray], sl: slice) -> dict[str, np.ndarray]:
    return {c: arrays[c][sl] for c in COMPONENT_COLS}


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_daily_scores_match_a_straight_reference(mode: str) -> None:
    arrays, y, _ = _synthetic(mode, 12, signal=0.3, seed=7)
    p_blend = _blend(arrays, PRIOR_VECTOR)
    logloss, brier = _daily_scores(mode, p_blend, y)

    if mode == "de":
        y_idx = np.argmax(y, axis=1)
        ref_ll = [categorical_logloss(floor_distribution(p_blend[i]), int(y_idx[i])) for i in range(len(y))]
        ref_br = [categorical_brier(floor_distribution(p_blend[i]), int(y_idx[i])) for i in range(len(y))]
    else:
        p_final = [finalize_blend(p_blend[i], mode) for i in range(len(y))]
        ref_ll = [bernoulli_logloss(p_final[i], y[i]) for i in range(len(y))]
        ref_br = [bernoulli_brier(p_final[i], y[i]) for i in range(len(y))]

    np.testing.assert_allclose(logloss, ref_ll, rtol=0, atol=1e-12)
    np.testing.assert_allclose(brier, ref_br, rtol=0, atol=1e-12)


def test_de_scoring_uses_the_floor_the_prediction_path_uses() -> None:
    p = np.zeros((1, 100))
    p[0, 0] = 1.0
    y = np.zeros((1, 100))
    y[0, 50] = 1.0

    logloss = _daily_scores("de", p, y)[0][0]
    assert logloss == pytest.approx(-np.log(0.05 / 100.0), rel=1e-12)
    assert logloss < 10.0


def test_the_optimizer_prior_is_the_documented_default() -> None:
    np.testing.assert_allclose(PRIOR_VECTOR, _weight_vector(DEFAULT_ENSEMBLE_WEIGHTS))


@pytest.mark.parametrize(
    ("mode", "signal", "seed"),
    [("loto", 0.45, 11), ("de", 0.06, 11)],
    ids=["loto", "de"],
)
def test_it_recovers_an_injected_signal_and_generalizes(mode: str, signal: float, seed: int) -> None:
    arrays, y, day_list = _synthetic(mode, 60, signal=signal, seed=seed)
    fit, holdout = slice(0, 40), slice(40, 60)

    learned, audit = learn_with_holdout(
        mode, _slice(arrays, fit), y[fit], day_list[:40], 45, DEFAULT_ENSEMBLE_WEIGHTS
    )

    assert audit.promoted, f"cổng từ chối một tín hiệu có thật: {audit.describe()}"
    assert learned.as_dict() != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    assert learned.w_cau > 0.5, f"khối lượng không dồn về p_cau: {learned.as_dict()}"

    out_arrays, out_y = _slice(arrays, holdout), y[holdout]
    learned_ll = _mean_logloss(mode, out_arrays, out_y, learned)
    default_ll = _mean_logloss(mode, out_arrays, out_y, DEFAULT_ENSEMBLE_WEIGHTS)
    assert learned_ll < default_ll, (
        f"đề bạt rồi mà lát thứ ba vẫn tệ hơn mặc định: {learned_ll:.6f} >= {default_ll:.6f}"
    )


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_the_promoted_weights_beat_the_default_on_unseen_days_across_seeds(mode: str) -> None:
    signal = 0.45 if mode == "loto" else 0.06
    promotions = 0
    for seed in range(20, 32):
        arrays, y, day_list = _synthetic(mode, 60, signal=signal, seed=seed)
        learned, audit = learn_with_holdout(
            mode, _slice(arrays, slice(0, 40)), y[:40], day_list[:40], 45, DEFAULT_ENSEMBLE_WEIGHTS
        )
        if not audit.promoted:
            continue
        promotions += 1
        out = _slice(arrays, slice(40, 60))
        assert _mean_logloss(mode, out, y[40:], learned) < _mean_logloss(
            mode, out, y[40:], DEFAULT_ENSEMBLE_WEIGHTS
        ), f"hạt {seed}: đề bạt mà ngoài mẫu vẫn tệ hơn mặc định"

    assert promotions >= 8, f"chỉ đề bạt {promotions}/12 lần trên tín hiệu có thật"


@pytest.mark.parametrize(
    ("mode", "days", "min_refusals"),
    [("loto", 40, 24), ("de", 20, 22)],
    ids=["loto", "de"],
)
def test_pure_noise_is_not_promoted(mode: str, days: int, min_refusals: int) -> None:
    refusals = 0
    for seed in range(40, 64):
        arrays, y, day_list = _synthetic(mode, days, signal=0.0, seed=seed)
        learned, audit = learn_with_holdout(
            mode, arrays, y, day_list, 45, DEFAULT_ENSEMBLE_WEIGHTS
        )
        if audit.promoted:
            continue
        refusals += 1
        assert learned.as_dict() == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()

    assert refusals >= min_refusals, f"chỉ từ chối {refusals}/24 lần trên nhiễu thuần"


def test_an_overfit_incumbent_is_reverted_not_kept() -> None:
    overfit = EnsembleWeights(w_ml=0.2813, w_cau=0.367, w_stat=0.0, w_active=0.0235, w_stable=0.3282)
    arrays, y, day_list = _synthetic("de", 40, signal=0.0, seed=99)

    learned, audit = learn_with_holdout("de", arrays, y, day_list, 45, overfit)

    assert not audit.promoted
    assert audit.baseline == "mac_dinh"
    assert learned.as_dict() == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    assert learned.as_dict() != overfit.as_dict()


def test_a_validation_window_below_the_minimum_changes_nothing() -> None:
    in_force = EnsembleWeights(w_ml=0.5, w_cau=0.5, w_stat=0.0, w_active=0.0, w_stable=0.0)
    days = int(np.ceil(MIN_VALIDATION_DAYS / 0.4)) - 2
    arrays, y, day_list = _synthetic("loto", days, signal=0.9, seed=5)

    learned, audit = learn_with_holdout("loto", arrays, y, day_list, 45, in_force)

    assert audit.validation_days < MIN_VALIDATION_DAYS
    assert not audit.promoted
    assert learned.as_dict() == in_force.as_dict()
    assert learned.as_dict() != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()


def test_the_written_file_records_the_refusal(tmp_path: Path) -> None:
    days = [f"2026-{month:02d}-{d:02d}" for month in (3, 4) for d in range(1, 26)]
    rng = np.random.default_rng(3)
    rows = []
    for day in days:
        for number in range(100):
            rows.append(
                {
                    "target_date": day,
                    "number": number,
                    "y": float(rng.random() < LOTO_RATE),
                    **{c: float(rng.random() * 0.4 + 0.05) for c in COMPONENT_COLS},
                    policy_column("cau"): COMPONENT_POLICY["cau"],
                }
            )
    hist_dir = tmp_path / "evaluation" / "history"
    hist_dir.mkdir(parents=True)
    import pandas as pd

    pd.DataFrame(rows).to_csv(hist_dir / "pred_loto.csv", index=False)

    out_dir = tmp_path / "data" / "ensemble"
    subprocess.run(
        [
            sys.executable,
            str(SRC / "ensemble" / "learn_ensemble_weights.py"),
            "--mode", "loto",
            "--history-dir", str(hist_dir),
            "--out-dir", str(out_dir),
            "--window-days", "180",
            "--min-days", "20",
            "--half-life-days", "45",
        ],
        check=True,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True,
    )

    blob = json.loads((out_dir / "weights_loto.json").read_text(encoding="utf-8"))
    promotion = blob["promotion"]
    assert promotion["promoted"] is False
    assert promotion["baseline"] == "mac_dinh"
    assert promotion["validation_days"] >= MIN_VALIDATION_DAYS
    assert promotion["train_days"] > promotion["validation_days"]
    assert set(promotion["validation_logloss"]) == {"mac_dinh", "dang_hieu_luc", "ung_vien"}
    assert promotion["reason"]
    assert blob["weights"] == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()


def test_a_tiny_but_certain_gain_is_refused() -> None:
    promoted, reason = _promotion_verdict(1e-7, -1e-9)
    assert not promoted
    assert "sàn" in reason


def test_a_large_but_uncertain_gain_is_refused() -> None:
    promoted, reason = _promotion_verdict(0.20, 0.01)
    assert not promoted
    assert "KTC95" in reason


def test_a_gain_exactly_at_the_floor_with_a_clear_interval_is_promoted() -> None:
    assert _promotion_verdict(MIN_RELATIVE_GAIN, -0.01)[0]
    assert not _promotion_verdict(np.nextafter(MIN_RELATIVE_GAIN, 0.0), -0.01)[0]


def test_the_effect_size_floor_is_above_zero() -> None:
    assert MIN_RELATIVE_GAIN > 0.0


def test_the_fitting_slice_ends_before_the_validation_slice_begins() -> None:
    arrays, y, day_list = _synthetic("loto", 40, signal=0.45, seed=13)
    _, audit = learn_with_holdout("loto", arrays, y, day_list, 45, DEFAULT_ENSEMBLE_WEIGHTS)

    assert audit.train_days + audit.validation_days == len(day_list)
    assert audit.train_last_day == day_list[audit.train_days - 1]
    assert audit.validation_first_day == day_list[audit.train_days]
    assert audit.train_last_day < audit.validation_first_day


@pytest.mark.parametrize(
    "scramble",
    [
        lambda d: d[24:] + d[:24],
        lambda d: list(reversed(d)),
        lambda d: d[:20] + [d[20]] + d[20:-1],
    ],
    ids=["xoay vòng", "đảo ngược", "trùng lặp"],
)
def test_an_unsorted_day_list_is_refused_rather_than_leaked(scramble) -> None:
    arrays, y, day_list = _synthetic("loto", 40, signal=0.45, seed=13)

    with pytest.raises(ValueError, match="sắp tăng dần"):
        learn_with_holdout("loto", arrays, y, scramble(day_list), 45, DEFAULT_ENSEMBLE_WEIGHTS)
