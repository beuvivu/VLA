from __future__ import annotations

import json

import numpy as np
import pytest

from ensemble.calibration import (
    DEFAULT_SELECTION_HOLDOUT,
    MIN_SELECTION_DAYS,
    CalibParams,
    apply_calibration,
    select_calibration,
)

BASE_RATE = 0.2377


def _labels(days: int, rng: np.random.Generator, rate: float = BASE_RATE) -> np.ndarray:
    return (rng.random((days, 100)) < rate).astype(float)


def test_a_systematically_biased_forecast_gets_calibrated() -> None:
    rng = np.random.default_rng(0)
    days = 300
    probs = np.clip(rng.normal(0.45, 0.05, size=(days, 100)), 0.01, 0.99)
    params, audit = select_calibration("loto", probs, _labels(days, rng))

    assert audit.selected
    assert audit.chosen != "identity", audit.describe()
    assert audit.brier_by_candidate["identity"] > audit.brier_by_candidate[audit.chosen]
    assert params.mode == "loto"


def test_an_already_calibrated_forecast_is_left_alone() -> None:
    rng = np.random.default_rng(1)
    days = 400
    per_number = rng.uniform(0.20, 0.28, size=100)
    probs = np.tile(per_number, (days, 1))
    labels = (rng.random((days, 100)) < per_number[None, :]).astype(float)

    _params, audit = select_calibration("loto", probs, labels)
    assert audit.selected
    assert audit.chosen == "identity", audit.describe()


def test_a_short_window_refuses_to_choose_and_says_so() -> None:
    rng = np.random.default_rng(2)
    days = MIN_SELECTION_DAYS - 1
    probs = np.full((days, 100), 0.3)
    params, audit = select_calibration("loto", probs, _labels(days, rng))

    assert audit.selected is False
    assert audit.chosen == "identity"
    assert audit.brier_by_candidate == {}
    assert "Không chọn được" in audit.describe()
    assert params.uses_isotonic is False


def test_the_holdout_slice_is_taken_from_the_END_of_the_window() -> None:
    rng = np.random.default_rng(3)
    days = 400
    split = int(round(days * (1.0 - DEFAULT_SELECTION_HOLDOUT)))
    probs = np.full((days, 100), 0.45)
    labels = np.empty((days, 100))
    labels[:split] = (rng.random((split, 100)) < BASE_RATE).astype(float)
    labels[split:] = (rng.random((days - split, 100)) < 0.45).astype(float)

    _params, audit = select_calibration("loto", probs, labels)

    assert audit.selected
    assert audit.fit_days == split
    assert audit.holdout_days == days - split
    assert audit.chosen == "identity", audit.describe()
    assert audit.brier_by_candidate["identity"] < audit.brier_by_candidate["parametric"]


def test_de_mode_keeps_a_proper_distribution_after_selection() -> None:
    rng = np.random.default_rng(4)
    days = 200
    probs = rng.dirichlet(np.full(100, 8.0), size=days)
    labels = np.zeros((days, 100))
    labels[np.arange(days), rng.integers(0, 100, size=days)] = 1.0

    params, audit = select_calibration("de", probs, labels)
    assert audit.selected
    out = apply_calibration("de", probs[0], params)
    assert float(out.sum()) == pytest.approx(1.0)


def test_isotonic_parameters_survive_a_json_round_trip() -> None:
    original = CalibParams(
        mode="loto",
        isotonic_x=(0.0, 0.25, 0.5, 1.0),
        isotonic_y=(0.0, 0.1, 0.3, 0.9),
    )
    restored = CalibParams(**json.loads(json.dumps(original.as_dict())))
    assert restored == original

    probe = np.array([0.0, 0.125, 0.5, 1.0])
    np.testing.assert_allclose(
        apply_calibration("loto", probe, original),
        apply_calibration("loto", probe, restored),
    )


def test_a_calibration_file_without_isotonic_keys_still_loads() -> None:
    legacy = {"mode": "loto", "a": 1.2, "b": -0.3, "temperature": 1.0}
    params = CalibParams(**legacy)
    assert params.uses_isotonic is False
    assert params.as_dict() == legacy


@pytest.mark.parametrize(
    "knots",
    [
        {"isotonic_x": (1.0, 0.0), "isotonic_y": (0.0, 1.0)},
        {"isotonic_x": (0.0, 1.0), "isotonic_y": (1.0, 0.0)},
        {"isotonic_x": (0.0, 1.0), "isotonic_y": (0.0, 2.0)},
        {"isotonic_x": (0.0, 1.0), "isotonic_y": (0.0,)},
        {"isotonic_x": (0.0, float("nan")), "isotonic_y": (0.0, 1.0)},
    ],
)
def test_malformed_isotonic_knots_are_refused(knots: dict) -> None:
    with pytest.raises(ValueError):
        CalibParams(mode="loto", **knots)


def test_isotonic_replaces_the_parametric_map_rather_than_stacking() -> None:
    stacked = CalibParams(
        mode="loto", a=3.0, b=2.0,
        isotonic_x=(0.0, 1.0), isotonic_y=(0.0, 1.0),
    )
    probe = np.array([0.1, 0.4, 0.9])
    np.testing.assert_allclose(apply_calibration("loto", probe, stacked), probe, atol=1e-6)


@pytest.mark.parametrize("fraction", [0.0, 0.9, -0.1])
def test_an_invalid_holdout_fraction_is_refused(fraction: float) -> None:
    rng = np.random.default_rng(5)
    probs = np.full((200, 100), 0.3)
    with pytest.raises(ValueError, match="holdout_fraction"):
        select_calibration("loto", probs, _labels(200, rng), holdout_fraction=fraction)


def test_the_default_holdout_leaves_most_of_the_window_for_fitting() -> None:
    assert 0.2 <= DEFAULT_SELECTION_HOLDOUT <= 0.35
