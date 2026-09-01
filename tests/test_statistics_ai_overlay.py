from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from statistics_ai_overlay import (
    _validated_probability_frame,
    _weighted_score,
)


def _prediction(path: Path, *, target: str, value: float = 0.2) -> Path:
    pd.DataFrame(
        {
            "predict_for_date": [target] * 100,
            "number": np.arange(100),
            "prob": np.full(100, value, dtype=float),
        }
    ).to_csv(path, index=False)
    return path


def test_current_prediction_artifact_is_accepted(tmp_path: Path) -> None:
    path = _prediction(tmp_path / "pred.csv", target="2026-09-02")
    frame, reason = _validated_probability_frame(
        path, expected_target="2026-09-02"
    )
    assert reason == "ok"
    assert frame is not None
    assert frame["number"].astype(int).tolist() == list(range(100))


def test_stale_prediction_artifact_is_rejected(tmp_path: Path) -> None:
    path = _prediction(tmp_path / "pred.csv", target="2026-09-01")
    frame, reason = _validated_probability_frame(
        path, expected_target="2026-09-02"
    )
    assert frame is None
    assert reason == "stale_target:2026-09-01"


def test_undated_ambiguous_artifact_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "pred.csv"
    pd.DataFrame(
        {"number": np.arange(100), "prob": np.full(100, 0.2)}
    ).to_csv(path, index=False)
    frame, reason = _validated_probability_frame(
        path, expected_target="2026-09-02"
    )
    assert frame is None
    assert reason == "target_date_unverifiable"


def test_exact_date_stamped_filename_can_supply_target(tmp_path: Path) -> None:
    path = tmp_path / "predict_next_loto_all_2026-09-02.csv"
    pd.DataFrame(
        {"number": np.arange(100), "prob": np.full(100, 0.2)}
    ).to_csv(path, index=False)
    frame, reason = _validated_probability_frame(
        path,
        expected_target="2026-09-02",
        target_from_filename="2026-09-02",
    )
    assert frame is not None
    assert reason == "ok"


def test_missing_ml_weight_is_renormalized_not_zero_padded() -> None:
    factors = {
        "ml": np.zeros(100),
        "freq": np.full(100, 0.5),
        "gap": np.full(100, 0.25),
    }
    score = _weighted_score(
        factors,
        {"ml": 0.50, "freq": 0.30, "gap": 0.20},
        available={"ml": False, "freq": True, "gap": True},
    )
    expected = 100.0 * ((0.30 / 0.50) * 0.5 + (0.20 / 0.50) * 0.25)
    assert np.allclose(score, expected)
