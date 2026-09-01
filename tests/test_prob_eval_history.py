from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prob_eval_history import evaluate_latest_emitted


def _history(day: str, *, mode: str) -> pd.DataFrame:
    y = np.zeros(100, dtype=int)
    if mode == "de":
        y[17] = 1
    else:
        y[[1, 3, 8, 17, 42]] = 1
    return pd.DataFrame(
        {
            "target_date": [day] * 100,
            "number": np.arange(100),
            "y": y,
            # Deliberately include components that would have allowed the old
            # 40/30/30 reconstruction. The evaluator must ignore them.
            "p_ml": np.full(100, 0.2),
            "p_active": np.full(100, 0.2),
            "p_stable": np.full(100, 0.2),
        }
    )


def _prediction(day: str, *, mode: str) -> pd.DataFrame:
    if mode == "de":
        p = np.full(100, 0.005)
        p[17] = 0.505
        p = p / p.sum()
    else:
        p = np.full(100, 0.20)
        p[[1, 3, 8, 17, 42]] = 0.30
    return pd.DataFrame(
        {
            "target_date": [day] * 100,
            "number": np.arange(100),
            "prob": p,
        }
    )


def test_missing_exact_artifact_never_reconstructs_from_components(tmp_path: Path) -> None:
    day = "2026-08-31"
    history_path = tmp_path / "pred_loto.csv"
    _history(day, mode="loto").to_csv(history_path, index=False)
    result = evaluate_latest_emitted(
        mode="loto",
        history_path=history_path,
        predict_dir=tmp_path / "predict",
    )
    assert result is None


def test_exact_emitted_artifact_is_evaluated(tmp_path: Path) -> None:
    day = "2026-08-31"
    history_path = tmp_path / "pred_de.csv"
    predict_dir = tmp_path / "predict"
    predict_dir.mkdir()
    _history(day, mode="de").to_csv(history_path, index=False)
    _prediction(day, mode="de").to_csv(
        predict_dir / f"predict_next_de_all_{day}.csv", index=False
    )

    result = evaluate_latest_emitted(
        mode="de",
        history_path=history_path,
        predict_dir=predict_dir,
    )
    assert result is not None
    assert result["target_date"] == day
    assert result["evaluation_source"] == "exact_emitted_prediction_artifact"
    assert float(result["logloss"]) >= 0.0
    assert float(result["brier"]) >= 0.0


def test_stale_internal_target_date_invalidates_artifact(tmp_path: Path) -> None:
    day = "2026-08-31"
    history_path = tmp_path / "pred_loto.csv"
    predict_dir = tmp_path / "predict"
    predict_dir.mkdir()
    _history(day, mode="loto").to_csv(history_path, index=False)
    pred = _prediction("2026-08-30", mode="loto")
    pred.to_csv(predict_dir / f"predict_next_loto_all_{day}.csv", index=False)

    result = evaluate_latest_emitted(
        mode="loto",
        history_path=history_path,
        predict_dir=predict_dir,
    )
    assert result is None
