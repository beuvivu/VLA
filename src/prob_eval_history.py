from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ensemble_components import probability_component
from ensemble_utils import (
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
)


def _latest_fully_labeled_day(df: pd.DataFrame) -> str | None:
    required = {"target_date", "number", "y"}
    if not required.issubset(df.columns):
        return None

    valid_days: list[str] = []
    for day, sub in df.groupby("target_date", sort=True):
        if len(sub) != 100 or not sub["y"].notna().all():
            continue
        numbers = pd.to_numeric(sub["number"], errors="coerce")
        y = pd.to_numeric(sub["y"], errors="coerce")
        if numbers.isna().any() or y.isna().any():
            continue
        n = numbers.to_numpy(dtype=float)
        if not np.all(np.isfinite(n)) or not np.all(n == np.floor(n)):
            continue
        if set(numbers.astype(int).tolist()) != set(range(100)):
            continue
        yi = y.to_numpy(dtype=float)
        if not np.all(np.isin(yi, [0.0, 1.0])):
            continue
        valid_days.append(str(day))
    return valid_days[-1] if valid_days else None


def _load_exact_emitted_prediction(
    predict_dir: Path,
    *,
    mode: str,
    target_date: str,
) -> np.ndarray | None:
    """Load the exact ensemble artifact that was emitted for ``target_date``.

    Historical evaluation must never reconstruct a prediction using today's
    weights, a reduced component subset, or a different calibration contract.
    If the exact artifact was not retained, the honest result is "not evaluable".
    """
    pred_file = predict_dir / f"predict_next_{mode}_all_{target_date}.csv"
    if not pred_file.exists() or pred_file.stat().st_size == 0:
        return None

    pred = pd.read_csv(pred_file)
    component = probability_component(
        pred,
        mode=mode,  # type: ignore[arg-type]
        expected_target_date=target_date,
    )
    if not component.available:
        print(
            f"[SKIP] exact emitted prediction artifact is invalid for {mode} "
            f"{target_date}: {component.reason}"
        )
        return None
    return component.prob


def evaluate_latest_emitted(
    *,
    mode: str,
    history_path: Path,
    predict_dir: Path,
) -> dict[str, object] | None:
    if not history_path.exists() or history_path.stat().st_size == 0:
        return None

    df = pd.read_csv(history_path)
    tdate = _latest_fully_labeled_day(df)
    if tdate is None:
        return None

    p = _load_exact_emitted_prediction(
        predict_dir,
        mode=mode,
        target_date=tdate,
    )
    if p is None:
        return None

    sub = df[df["target_date"].astype(str) == tdate].copy()
    sub["number"] = pd.to_numeric(sub["number"], errors="raise").astype(int)
    sub.sort_values("number", inplace=True)
    y = pd.to_numeric(sub["y"], errors="raise").astype(int).to_numpy()

    if mode == "de":
        if int(y.sum()) != 1:
            print(
                f"[SKIP] invalid De label contract for {tdate}: "
                f"expected exactly one positive label, got {int(y.sum())}"
            )
            return None
        y_idx = int(np.argmax(y))
        ll = categorical_logloss(p, y_idx)
        br = categorical_brier(p, y_idx)
    else:
        ll = bernoulli_logloss(p, y)
        br = bernoulli_brier(p, y)

    return {
        "mode": mode,
        "target_date": tdate,
        "logloss": float(ll),
        "brier": float(br),
        "evaluation_source": "exact_emitted_prediction_artifact",
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Append honest metrics for the latest retained emitted ensemble prediction."
    )
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--history-dir", default="data/history")
    ap.add_argument("--predict-dir", default="data/predict")
    ap.add_argument("--out", default="data/prob_eval/ensemble_history.csv")
    args = ap.parse_args()

    hist_path = Path(args.history_dir) / f"pred_{args.mode}.csv"
    if not hist_path.exists():
        print("[SKIP] history not found:", hist_path)
        return

    row = evaluate_latest_emitted(
        mode=args.mode,
        history_path=hist_path,
        predict_dir=Path(args.predict_dir),
    )
    if row is None:
        print(
            f"[SKIP] no exact evaluable emitted prediction for {args.mode}; "
            "historical ensemble metrics are never reconstructed from components"
        )
        return

    row["updated_at_utc"] = (
        datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    new_row = pd.DataFrame([row])
    if out.exists() and out.stat().st_size > 0:
        old = pd.read_csv(out)
        old = old[
            (old["mode"].astype(str) != str(row["mode"]))
            | (old["target_date"].astype(str) != str(row["target_date"]))
        ]
        result = pd.concat([old, new_row], ignore_index=True)
    else:
        result = new_row
    result.sort_values(["mode", "target_date"], inplace=True)
    result.to_csv(out, index=False)
    print(
        f"[OK] exact emitted ensemble metrics {row['mode']} {row['target_date']}: "
        f"logloss={row['logloss']:.6f} brier={row['brier']:.6f} -> {out}"
    )


if __name__ == "__main__":
    main()
