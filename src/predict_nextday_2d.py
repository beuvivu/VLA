from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd

from calibration import CalibParams, apply_calibration
from ensemble_utils import EnsembleWeights, clip01, ensure_full_probs, normalize_distribution
from meta_predictor import META_SCHEMA_VERSION, blend_predictions, predict_meta

Mode = Literal["loto", "de"]


@dataclass
class Picks:
    mode: str
    anchor_date: str
    target_date: str
    weights: dict
    calibration: dict
    meta: dict
    top4: list[str]
    top8: list[str]
    top10: list[str]


def _latest_anchor_date(xsmb_csv: Path) -> date:
    df = pd.read_csv(xsmb_csv)
    df["date"] = pd.to_datetime(df["date"])
    return df["date"].max().date()


def _read_prob_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["number", "prob"])
    return pd.read_csv(path)


def _load_probs(
    data_dir: Path, mode: str, anchor: date
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    path_ui = data_dir / "path_ui"
    df_a = _read_prob_file(
        path_ui / f"predict_next_{mode}_active_{anchor.isoformat()}_all.csv"
    )
    df_s = _read_prob_file(
        path_ui / f"predict_next_{mode}_stable_{anchor.isoformat()}_all.csv"
    )

    if df_a.empty:
        df_a = _read_prob_file(
            path_ui / f"predict_next_{mode}_active_{anchor.isoformat()}.csv"
        )
    if df_s.empty:
        df_s = _read_prob_file(
            path_ui / f"predict_next_{mode}_stable_{anchor.isoformat()}.csv"
        )

    df_m = _read_prob_file(data_dir / "ml" / f"predict_next_{mode}_ml_all.csv")
    df_c = _read_prob_file(data_dir / "ai_ml" / f"cau_keo_{mode}_all.csv")
    df_t = _read_prob_file(
        data_dir / "statistical_signal" / f"predict_next_{mode}_stat_all.csv"
    )

    p_a = ensure_full_probs(df_a)
    p_s = ensure_full_probs(df_s)
    p_m = ensure_full_probs(df_m)
    p_c = ensure_full_probs(df_c)
    p_t = ensure_full_probs(df_t)

    if mode == "de":
        p_a = normalize_distribution(p_a)
        p_s = normalize_distribution(p_s)
        p_m = normalize_distribution(p_m)
        p_c = normalize_distribution(p_c)
        p_t = normalize_distribution(p_t)

    return p_m, p_c, p_t, p_a, p_s


def _load_weights(data_dir: Path, mode: str) -> EnsembleWeights:
    default = EnsembleWeights(
        w_ml=0.25,
        w_cau=0.30,
        w_stat=0.20,
        w_active=0.125,
        w_stable=0.125,
    )
    f = data_dir / "ensemble" / f"weights_{mode}.json"
    if not f.exists():
        return default
    j = json.loads(f.read_text(encoding="utf-8"))
    w = j.get("weights", {})
    if "w_stat" not in w or int(j.get("schema_version", 0)) < 5:
        return default
    return EnsembleWeights(
        w_ml=float(w.get("w_ml", default.w_ml)),
        w_cau=float(w.get("w_cau", default.w_cau)),
        w_stat=float(w.get("w_stat", default.w_stat)),
        w_active=float(w.get("w_active", default.w_active)),
        w_stable=float(w.get("w_stable", default.w_stable)),
    ).normalized()


def _load_calibration(data_dir: Path, mode: str) -> CalibParams:
    f = data_dir / "ensemble" / f"calibration_{mode}.json"
    if not f.exists():
        return CalibParams(mode=mode)
    j = json.loads(f.read_text(encoding="utf-8"))
    if int(j.get("schema_version", 0)) < 5:
        return CalibParams(mode=mode)
    p = j.get("params") or {}
    return CalibParams(
        mode=mode,
        a=float(p.get("a", 1.0)),
        b=float(p.get("b", 0.0)),
        temperature=float(p.get("temperature", 1.0)),
    )


def _meta_prediction(
    models_dir: Path,
    mode: str,
    target: date,
    p_m: np.ndarray,
    p_c: np.ndarray,
    p_t: np.ndarray,
    p_a: np.ndarray,
    p_s: np.ndarray,
    linear_prob: np.ndarray,
) -> tuple[np.ndarray, float, dict]:
    model_path = models_dir / f"meta_{mode}.joblib"
    fallback = {
        "active": False,
        "trust": 0.0,
        "quality_pass": False,
        "reason": "stacked model unavailable",
    }
    if not model_path.exists():
        return linear_prob.copy(), 0.0, fallback

    try:
        pack = joblib.load(model_path)
    except (AttributeError, ModuleNotFoundError, ValueError) as exc:
        fallback["reason"] = f"stacked model load failed: {exc}"
        return linear_prob.copy(), 0.0, fallback

    if int(pack.get("schema_version", 0)) != META_SCHEMA_VERSION:
        fallback["reason"] = "stacked model schema mismatch"
        return linear_prob.copy(), 0.0, fallback
    if str(pack.get("mode")) != mode:
        fallback["reason"] = "stacked model mode mismatch"
        return linear_prob.copy(), 0.0, fallback

    trust = float(np.clip(pack.get("meta_trust", 0.0), 0.0, 0.40))
    quality_pass = bool(pack.get("quality_pass", False))
    try:
        p_meta = predict_meta(
            pack,
            mode,
            target.isoformat(),
            p_m,
            p_c,
            p_t,
            p_a,
            p_s,
        )
    except (KeyError, TypeError, ValueError) as exc:
        fallback["reason"] = f"stacked prediction failed: {exc}"
        return linear_prob.copy(), 0.0, fallback

    if not quality_pass or trust <= 0:
        reason = "validation gate rejected stacked challenger"
        return p_meta, 0.0, {
            "active": False,
            "trust": 0.0,
            "quality_pass": quality_pass,
            "reason": reason,
            "validation_logloss": pack.get("validation_logloss"),
            "baseline_validation_logloss": pack.get(
                "baseline_validation_logloss"
            ),
            "logloss_skill": pack.get("logloss_skill"),
        }

    return p_meta, trust, {
        "active": True,
        "trust": trust,
        "quality_pass": True,
        "reason": "validated stacked challenger blended into production",
        "candidate": (pack.get("selected_candidate") or {}).get("name"),
        "validation_logloss": pack.get("validation_logloss"),
        "baseline_validation_logloss": pack.get("baseline_validation_logloss"),
        "logloss_skill": pack.get("logloss_skill"),
        "brier_skill": pack.get("brier_skill"),
        "trained_through_target_date": pack.get("trained_through_target_date"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Next-day 2-digit picks using calibrated linear ensemble plus a "
            "validation-gated nonlinear stacked-ML challenger."
        )
    )
    ap.add_argument("--mode", choices=["loto", "de"], default="loto")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--out-dir", default="data/predict")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    models_dir = Path(args.models_dir)
    anchor = _latest_anchor_date(data_dir / "xsmb.csv")
    target = anchor + timedelta(days=1)

    weights = _load_weights(data_dir, args.mode)
    calib = _load_calibration(data_dir, args.mode)
    p_m, p_c, p_t, p_a, p_s = _load_probs(data_dir, args.mode, anchor)

    component_matrix = np.vstack([p_m, p_c, p_t, p_a, p_s])
    p_linear_raw = (
        weights.w_ml * p_m
        + weights.w_cau * p_c
        + weights.w_stat * p_t
        + weights.w_active * p_a
        + weights.w_stable * p_s
    )
    if args.mode == "de":
        p_linear_raw = clip01(normalize_distribution(p_linear_raw), eps=1e-12)
    else:
        p_linear_raw = clip01(p_linear_raw, eps=1e-6)

    p_linear = apply_calibration(args.mode, p_linear_raw, calib)
    p_meta, meta_trust, meta_info = _meta_prediction(
        models_dir,
        args.mode,
        target,
        p_m,
        p_c,
        p_t,
        p_a,
        p_s,
        p_linear,
    )
    p = blend_predictions(args.mode, p_linear, p_meta, meta_trust)

    disagreement = np.std(component_matrix, axis=0)
    component_min = np.min(component_matrix, axis=0)
    component_max = np.max(component_matrix, axis=0)
    meta_edge = p_meta - p_linear
    df_all = pd.DataFrame(
        {
            "number": np.arange(100, dtype=int),
            "prob": p,
            "linear_prob": p_linear,
            "meta_prob": p_meta,
            "meta_edge": meta_edge,
            "meta_trust": meta_trust,
            "meta_active": bool(meta_info.get("active", False)),
            "component_disagreement": disagreement,
            "component_min": component_min,
            "component_max": component_max,
        }
    )
    df_all["number_str"] = df_all["number"].map(lambda x: f"{int(x):02d}")
    q33, q67 = np.quantile(disagreement, [0.33, 0.67])
    df_all["agreement_tier"] = np.where(
        disagreement <= q33,
        "high",
        np.where(disagreement <= q67, "medium", "low"),
    )
    df_all = df_all.sort_values("prob", ascending=False).reset_index(drop=True)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df_all.to_csv(
        out_dir / f"predict_next_{args.mode}_all_{target.isoformat()}.csv",
        index=False,
    )
    for n in (4, 8, 10):
        df_all.head(n).to_csv(
            out_dir / f"predict_next_{args.mode}_top{n}_{target.isoformat()}.csv",
            index=False,
        )

    picks = Picks(
        mode=args.mode,
        anchor_date=anchor.isoformat(),
        target_date=target.isoformat(),
        weights=weights.as_dict(),
        calibration=calib.as_dict(),
        meta=meta_info,
        top4=df_all.head(4)["number_str"].tolist(),
        top8=df_all.head(8)["number_str"].tolist(),
        top10=df_all.head(10)["number_str"].tolist(),
    )
    (out_dir / f"picks_{args.mode}.json").write_text(
        json.dumps(picks.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] picks ready: mode={args.mode} target={target}")
    print("weights:", picks.weights)
    print("calibration:", picks.calibration)
    print("stacked ML:", picks.meta)
    print("top4:", picks.top4)
    print("top8:", picks.top8)
    print("top10:", picks.top10)


if __name__ == "__main__":
    main()
