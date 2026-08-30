from __future__ import annotations

import argparse
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from lottery import Lottery
from ml_features import FeatureParams, build_features_for_prediction
from ml_train import FEATURE_SCHEMA_VERSION, train_one

logger = logging.getLogger(__name__)


def _fmt2(n: int) -> str:
    return f"{n:02d}"


def _latest_data_date() -> str:
    lot = Lottery()
    lot.load()
    df = lot.get_2_digits_data()
    if df.empty:
        raise RuntimeError("No historical data available for ML prediction.")
    return str(pd.to_datetime(df["date"]).max().date())


def _load_or_train_model(
    mode: str,
    models_dir: Path,
    *,
    window_days: int,
    latest_data_date: str,
) -> dict:
    """Load a current model; retrain on new data or incompatible feature schema."""
    model_path = models_dir / f"ml_{mode}.joblib"
    retrain_reason = ""
    pack: dict | None = None

    if model_path.exists():
        try:
            pack = joblib.load(model_path)
        except (AttributeError, ModuleNotFoundError, ValueError) as exc:
            retrain_reason = f"stale serialization: {exc}"
    else:
        retrain_reason = "model file missing"

    if pack is not None:
        if int(pack.get("feature_schema_version", 0)) != FEATURE_SCHEMA_VERSION:
            retrain_reason = "feature schema changed"
        elif str(pack.get("trained_through_date", "")) != latest_data_date:
            retrain_reason = (
                f"new draw available ({pack.get('trained_through_date')} -> {latest_data_date})"
            )
        elif int(pack.get("window_days", window_days)) != int(window_days):
            retrain_reason = "training window changed"

    if retrain_reason:
        logger.info("Retraining %s base ML: %s", mode, retrain_reason)
        model_path.unlink(missing_ok=True)
        train_one(mode, models_dir, window_days=window_days)
        pack = joblib.load(model_path)

    if pack is None:
        raise RuntimeError(f"Could not load or train {mode} model")
    return pack


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="18:35")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--out-dir", default="data/ml")
    ap.add_argument("--window-days", type=int, default=2000)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    models_dir = Path(args.models_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = _latest_data_date()

    for mode in ["loto", "de"]:
        pack = _load_or_train_model(
            mode,
            models_dir,
            window_days=args.window_days,
            latest_data_date=latest,
        )
        feature_cols = pack["features"]
        model = pack["model"]

        last_date, X_pred = build_features_for_prediction(mode=mode, params=FeatureParams())
        next_date = (pd.to_datetime(last_date) + pd.Timedelta(days=1)).date()

        Xf = X_pred[feature_cols].astype(np.float32).to_numpy()
        raw_proba = model.predict_proba(Xf)[:, 1]
        trust = float(np.clip(pack.get("model_trust", 1.0), 0.0, 1.0))
        baseline_prob = float(pack.get("baseline_prob", np.mean(raw_proba)))
        proba = trust * raw_proba + (1.0 - trust) * baseline_prob

        # Đề is exactly one of 100 classes; normalize after conservative shrinkage.
        if mode == "de":
            s = float(proba.sum())
            if s > 0:
                proba = proba / s

        df = pd.DataFrame(
            {
                "predict_for_date": [str(next_date)] * 100,
                "number": [_fmt2(i) for i in range(100)],
                "prob": proba,
                "raw_model_prob": raw_proba,
                "model_trust": trust,
                "quality_pass": bool(pack.get("quality_pass", True)),
            }
        ).sort_values("prob", ascending=False)

        top = df.head(args.top).reset_index(drop=True)
        top["prob_percent"] = (top["prob"] * 100.0).round(3)

        df.to_csv(out_dir / f"predict_next_{mode}_ml_all.csv", index=False)
        top.to_csv(out_dir / f"predict_next_{mode}_ml_top{args.top}.csv", index=False)

        print(
            f"[OK] {mode} -> predictions for {next_date}; "
            f"trained_through={latest} trust={trust:.3f}"
        )
        print(top)


if __name__ == "__main__":
    main()
