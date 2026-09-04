from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, timedelta
from numbers import Integral, Real
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd

from calibration import CalibParams, apply_calibration
from ensemble_components import COMPONENT_KEYS, probability_component, renormalize_available_weights
from ensemble_utils import EnsembleWeights, clip01, normalize_distribution
from meta_predictor import META_SCHEMA_VERSION, blend_predictions, predict_meta

Mode = Literal["loto", "de"]


@dataclass
class Picks:
    mode: str
    anchor_date: str
    target_date: str
    weights: dict
    effective_weights: dict
    component_availability: dict
    component_reasons: dict
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
    data_dir: Path, mode: Mode, anchor: date
) -> tuple[dict[str, np.ndarray], dict[str, bool], dict[str, str]]:
    target = anchor + timedelta(days=1)
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

    frames = {
        "ml": _read_prob_file(data_dir / "ml" / f"predict_next_{mode}_ml_all.csv"),
        "cau": _read_prob_file(data_dir / "ai_ml" / f"cau_keo_{mode}_all.csv"),
        "stat": _read_prob_file(
            data_dir / "statistical_signal" / f"predict_next_{mode}_stat_all.csv"
        ),
        "active": df_a,
        "stable": df_s,
    }
    components = {
        key: probability_component(
            frame,
            mode=mode,
            expected_target_date=target,
            expected_anchor_date=anchor,
        )
        for key, frame in frames.items()
    }
    available = {key: bool(component.available) for key, component in components.items()}
    reasons = {key: component.reason for key, component in components.items()}
    vectors = {
        key: (
            component.prob
            if component.available
            else np.zeros(100, dtype=np.float64)
        )
        for key, component in components.items()
    }
    return vectors, available, reasons


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
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
        w = j.get("weights", {})
        schema_version = j.get("schema_version")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, Integral)
            or schema_version < 5
            or "w_stat" not in w
        ):
            return default
        return EnsembleWeights(
            w_ml=float(w.get("w_ml", default.w_ml)),
            w_cau=float(w.get("w_cau", default.w_cau)),
            w_stat=float(w.get("w_stat", default.w_stat)),
            w_active=float(w.get("w_active", default.w_active)),
            w_stable=float(w.get("w_stable", default.w_stable)),
        ).normalized()
    except (AttributeError, TypeError, ValueError):
        return default


def _load_calibration(data_dir: Path, mode: str) -> CalibParams:
    f = data_dir / "ensemble" / f"calibration_{mode}.json"
    if not f.exists():
        return CalibParams(mode=mode)
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
        schema_version = j.get("schema_version")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, Integral)
            or schema_version < 5
        ):
            return CalibParams(mode=mode)
        p = j.get("params") or {}
        return CalibParams(
            mode=mode,
            a=float(p.get("a", 1.0)),
            b=float(p.get("b", 0.0)),
            temperature=float(p.get("temperature", 1.0)),
        )
    except (AttributeError, TypeError, ValueError):
        return CalibParams(mode=mode)


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
    except (AttributeError, EOFError, ImportError, OSError, ValueError) as exc:
        fallback["reason"] = f"stacked model load failed: {exc}"
        return linear_prob.copy(), 0.0, fallback

    if not isinstance(pack, dict):
        fallback["reason"] = "stacked model pack has invalid type"
        return linear_prob.copy(), 0.0, fallback
    schema_version = pack.get("schema_version")
    trust_value = pack.get("meta_trust")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, Integral)
        or isinstance(trust_value, bool)
        or not isinstance(trust_value, Real)
    ):
        fallback["reason"] = "stacked model metadata is invalid"
        return linear_prob.copy(), 0.0, fallback
    trust_value = float(trust_value)
    if schema_version != META_SCHEMA_VERSION:
        fallback["reason"] = "stacked model schema mismatch"
        return linear_prob.copy(), 0.0, fallback
    if str(pack.get("mode")) != mode:
        fallback["reason"] = "stacked model mode mismatch"
        return linear_prob.copy(), 0.0, fallback

    if not np.isfinite(trust_value) or not 0.0 <= trust_value <= 0.40:
        fallback["reason"] = "stacked model trust is outside [0, 0.40]"
        return linear_prob.copy(), 0.0, fallback
    quality_value = pack.get("quality_pass", False)
    if not isinstance(quality_value, bool):
        fallback["reason"] = "stacked model quality gate is invalid"
        return linear_prob.copy(), 0.0, fallback
    trust = trust_value
    quality_pass = quality_value
    if not quality_pass or trust <= 0:
        return linear_prob.copy(), 0.0, {
            "active": False,
            "trust": 0.0,
            "quality_pass": quality_pass,
            "reason": "validation gate rejected stacked challenger",
            "validation_logloss": pack.get("validation_logloss"),
            "baseline_validation_logloss": pack.get("baseline_validation_logloss"),
            "logloss_skill": pack.get("logloss_skill"),
        }
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


def _blend_linear(vectors: dict[str, np.ndarray], weights: EnsembleWeights) -> np.ndarray:
    return (
        weights.w_ml * vectors["ml"]
        + weights.w_cau * vectors["cau"]
        + weights.w_stat * vectors["stat"]
        + weights.w_active * vectors["active"]
        + weights.w_stable * vectors["stable"]
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Next-day 2-digit picks using an availability/date-aware calibrated "
            "linear ensemble plus a validation-gated nonlinear stacked-ML challenger."
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

    configured_weights = _load_weights(data_dir, args.mode)
    calib = _load_calibration(data_dir, args.mode)
    vectors, available, reasons = _load_probs(data_dir, args.mode, anchor)
    effective_weights = renormalize_available_weights(configured_weights, available)

    p_linear_raw = _blend_linear(vectors, effective_weights)
    if args.mode == "de":
        p_linear_raw = clip01(normalize_distribution(p_linear_raw), eps=1e-12)
    else:
        p_linear_raw = clip01(p_linear_raw, eps=1e-6)

    all_components_available = all(available.get(key, False) for key in COMPONENT_KEYS)
    if all_components_available:
        p_linear = apply_calibration(args.mode, p_linear_raw, calib)
        calibration_info = {
            **calib.as_dict(),
            "active": True,
            "reason": "calibration matches full five-component ensemble",
        }
        p_meta, meta_trust, meta_info = _meta_prediction(
            models_dir,
            args.mode,
            target,
            vectors["ml"],
            vectors["cau"],
            vectors["stat"],
            vectors["active"],
            vectors["stable"],
            p_linear,
        )
    else:
        p_linear = p_linear_raw
        calibration_info = {
            **calib.as_dict(),
            "active": False,
            "reason": "bypassed because one or more ensemble components are unavailable",
        }
        p_meta = p_linear.copy()
        meta_trust = 0.0
        meta_info = {
            "active": False,
            "trust": 0.0,
            "quality_pass": False,
            "reason": "stacked model requires all five ensemble components",
        }

    p = blend_predictions(args.mode, p_linear, p_meta, meta_trust)

    available_matrix = np.vstack(
        [vectors[key] for key in COMPONENT_KEYS if available.get(key, False)]
    )
    disagreement = np.std(available_matrix, axis=0)
    component_min = np.min(available_matrix, axis=0)
    component_max = np.max(available_matrix, axis=0)
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
            "component_count": int(sum(available.values())),
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
        weights=configured_weights.as_dict(),
        effective_weights=effective_weights.as_dict(),
        component_availability=available,
        component_reasons=reasons,
        calibration=calibration_info,
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
    print("configured weights:", picks.weights)
    print("effective weights:", picks.effective_weights)
    print("component availability:", picks.component_availability)
    print("component reasons:", picks.component_reasons)
    print("calibration:", picks.calibration)
    print("stacked ML:", picks.meta)
    print("top4:", picks.top4)
    print("top8:", picks.top8)
    print("top10:", picks.top10)


if __name__ == "__main__":
    main()
