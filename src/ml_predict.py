from __future__ import annotations

import argparse
import logging
from numbers import Integral, Real
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from lottery import Lottery
from ml_features import FeatureParams, build_features_for_prediction
from ml_train import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, train_one
from ml_validation import predict_with_feature_allowlist

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


def _model_pack_issue(
    pack: object,
    *,
    window_days: int,
    latest_data_date: str,
) -> str | None:
    """Return why a base-model pack is unsafe/stale, or ``None`` if usable."""
    if not isinstance(pack, dict):
        return "invalid model-pack type"
    if pack.get("features") != FEATURE_COLUMNS:
        return "production feature allowlist changed"
    if not callable(getattr(pack.get("model"), "predict_proba", None)):
        return "model object is missing predict_proba"
    schema_version = pack.get("feature_schema_version")
    pack_window_days = pack.get("window_days")
    trust_value = pack.get("model_trust")
    baseline_value = pack.get("baseline_prob")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, Integral)
        or isinstance(pack_window_days, bool)
        or not isinstance(pack_window_days, Integral)
        or isinstance(trust_value, bool)
        or not isinstance(trust_value, Real)
        or isinstance(baseline_value, bool)
        or not isinstance(baseline_value, Real)
    ):
        return "invalid model-pack metadata"
    trust = float(trust_value)
    baseline_probability = float(baseline_value)
    if not np.isfinite([trust, baseline_probability]).all():
        return "non-finite model-pack metadata"
    if not 0.0 <= trust <= 1.0 or not 0.0 <= baseline_probability <= 1.0:
        return "model-pack probabilities outside [0, 1]"
    if schema_version != FEATURE_SCHEMA_VERSION:
        return "feature schema changed"
    if str(pack.get("trained_through_date", "")) != latest_data_date:
        return (
            f"new draw available ({pack.get('trained_through_date')}"
            f" -> {latest_data_date})"
        )
    if pack_window_days != window_days:
        return "training window changed"
    return None


def _load_or_train_model(
    mode: str,
    models_dir: Path,
    *,
    window_days: int,
    latest_data_date: str,
) -> dict:
    """Load a current model; retrain on new data or incompatible feature schema."""
    if mode not in {"loto", "de"}:
        raise ValueError("mode must be 'loto' or 'de'")
    if (
        isinstance(window_days, bool)
        or not isinstance(window_days, Integral)
        or window_days <= 0
    ):
        raise ValueError("window_days must be a positive integer")
    model_path = models_dir / f"ml_{mode}.joblib"
    retrain_reason = ""
    pack: dict | None = None

    if model_path.exists():
        try:
            pack = joblib.load(model_path)
        except (AttributeError, EOFError, ImportError, OSError, ValueError) as exc:
            retrain_reason = f"stale serialization: {exc}"
    else:
        retrain_reason = "model file missing"

    if pack is not None:
        retrain_reason = _model_pack_issue(
            pack,
            window_days=window_days,
            latest_data_date=latest_data_date,
        ) or ""

    if retrain_reason:
        logger.info("Retraining %s base ML: %s", mode, retrain_reason)
        model_path.unlink(missing_ok=True)
        train_one(mode, models_dir, window_days=window_days)
        try:
            pack = joblib.load(model_path)
        except (AttributeError, EOFError, ImportError, OSError, ValueError) as exc:
            raise RuntimeError(f"Could not load retrained {mode} model") from exc

    final_issue = _model_pack_issue(
        pack,
        window_days=window_days,
        latest_data_date=latest_data_date,
    )
    if final_issue or not isinstance(pack, dict):
        raise RuntimeError(f"Could not load or train {mode} model: {final_issue}")
    return pack


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="18:35")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--out-dir", default="data/ml")
    ap.add_argument("--window-days", type=int, default=2000)
    args = ap.parse_args()

    if not 1 <= args.top <= 100:
        ap.error("--top must be between 1 and 100")
    if args.window_days <= 0:
        ap.error("--window-days must be > 0")

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

        raw_proba = predict_with_feature_allowlist(model, X_pred, feature_cols)
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
