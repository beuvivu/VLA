from __future__ import annotations

import numpy as np

import meta_predictor as meta


def _labels(days: int = 30) -> np.ndarray:
    labels = np.zeros((days, 100))
    labels[:, :24] = 1.0
    return labels


def test_one_lucky_draw_cannot_activate_stacked_model() -> None:
    labels = _labels()
    baseline = np.full_like(labels, 0.24)
    challenger = baseline.copy()
    challenger[0] = 0.27
    challenger[-1] = np.where(labels[-1], 0.9, 0.01)
    point_gate = meta.quality_gate(
        "loto", meta._evaluate("loto", challenger, labels),
        meta._evaluate("loto", baseline, labels), meta._evaluate("loto", baseline, labels),
    )
    assert point_gate["quality_pass"] is True
    gate = meta.holdout_quality_gate("loto", challenger, baseline, baseline, labels, 0.15)
    assert gate["quality_pass"] is False
    assert gate["linear_delta_ci95_high"] >= 0.0


def test_repeatable_signal_passes_the_actual_blend_gate() -> None:
    labels = _labels()
    baseline = np.full_like(labels, 0.24)
    challenger = np.where(labels, 0.8, 0.05)
    gate = meta.holdout_quality_gate("loto", challenger, baseline, baseline, labels, 0.15)
    assert gate["quality_pass"] is True
    assert gate["linear_delta_ci95_high"] < 0.0
    assert gate["constant_delta_ci95_high"] < 0.0
    assert 0.3 < gate["blend_logloss"] < 0.55


def test_good_meta_cannot_hide_a_bad_published_blend() -> None:
    labels = _labels()
    baseline = np.full_like(labels, 0.9)
    constant = np.full_like(labels, 0.24)
    challenger = np.where(labels, 0.8, 0.05)
    assert meta.quality_gate(
        "loto", meta._evaluate("loto", challenger, labels),
        meta._evaluate("loto", baseline, labels), meta._evaluate("loto", constant, labels),
    )["quality_pass"] is True
    gate = meta.holdout_quality_gate("loto", challenger, baseline, constant, labels, 0.4)
    assert gate["quality_pass"] is False
    assert gate["blend_constant_logloss_skill"] < 0.0


def test_de_holdout_uses_one_categorical_score_per_draw() -> None:
    labels = np.zeros((30, 100))
    labels[:, 42] = 1.0
    baseline = np.full_like(labels, 0.01)
    challenger = np.full_like(labels, 0.5 / 99)
    challenger[:, 42] = 0.5
    gate = meta.holdout_quality_gate("de", challenger, baseline, baseline, labels, 0.15)
    assert gate["quality_pass"] is True
    assert gate["holdout_days"] == 30
    assert gate["blend_logloss"] == np.log(1 / 0.0835)
