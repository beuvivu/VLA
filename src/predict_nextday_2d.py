from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from calibration import CalibParams, apply_calibration
from ensemble_utils import EnsembleWeights, clip01, ensure_full_probs, normalize_distribution


Mode = Literal["loto", "de"]


@dataclass
class Picks:
    mode: str
    anchor_date: str
    target_date: str
    weights: dict
    calibration: dict
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


def _load_probs(data_dir: Path, mode: str, anchor: date) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    path_ui = data_dir / "path_ui"
    df_a = _read_prob_file(path_ui / f"predict_next_{mode}_active_{anchor.isoformat()}_all.csv")
    df_s = _read_prob_file(path_ui / f"predict_next_{mode}_stable_{anchor.isoformat()}_all.csv")

    # fallback to sparse (top-N) if full tables missing
    if df_a.empty:
        df_a = _read_prob_file(path_ui / f"predict_next_{mode}_active_{anchor.isoformat()}.csv")
    if df_s.empty:
        df_s = _read_prob_file(path_ui / f"predict_next_{mode}_stable_{anchor.isoformat()}.csv")

    ml_f = data_dir / "ml" / f"predict_next_{mode}_ml_all.csv"
    df_m = _read_prob_file(ml_f)
    cau_f = data_dir / "ai_ml" / f"cau_keo_{mode}_all.csv"
    df_c = _read_prob_file(cau_f)
    stat_f = data_dir / "statistical_signal" / f"predict_next_{mode}_stat_all.csv"
    df_t = _read_prob_file(stat_f)

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
    default = EnsembleWeights(w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125)
    f = data_dir / "ensemble" / f"weights_{mode}.json"
    if not f.exists():
        return default
    j = json.loads(f.read_text(encoding="utf-8"))
    w = j.get("weights", {})
    if "w_stat" not in w or int(j.get("schema_version", 0)) < 5:
        # Migration path: older histories did not contain the empirical-Bayes
        # statistical component. Use conservative diversified defaults until
        # enough schema-v5 walk-forward history accumulates.
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
    p = (j.get("params") or {})
    return CalibParams(
        mode=mode,
        a=float(p.get("a", 1.0)),
        b=float(p.get("b", 0.0)),
        temperature=float(p.get("temperature", 1.0)),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Next-day 2-digit picks (Top4/8/10) using auto-learned ensemble weights.")
    ap.add_argument("--mode", choices=["loto", "de"], default="loto")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="data/predict")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    anchor = _latest_anchor_date(data_dir / "xsmb.csv")
    target = anchor + timedelta(days=1)

    w = _load_weights(data_dir, args.mode)
    calib = _load_calibration(data_dir, args.mode)
    p_m, p_c, p_t, p_a, p_s = _load_probs(data_dir, args.mode, anchor)

    component_matrix = np.vstack([p_m, p_c, p_t, p_a, p_s])
    p = w.w_ml * p_m + w.w_cau * p_c + w.w_stat * p_t + w.w_active * p_a + w.w_stable * p_s

    if args.mode == "de":
        p = normalize_distribution(p)
        p = clip01(p, eps=1e-12)
    else:
        p = clip01(p, eps=1e-6)

    # calibration improves probability quality (LogLoss)
    p = apply_calibration(args.mode, p, calib)

    disagreement = np.std(component_matrix, axis=0)
    component_min = np.min(component_matrix, axis=0)
    component_max = np.max(component_matrix, axis=0)
    df_all = pd.DataFrame({
        "number": np.arange(100, dtype=int),
        "prob": p,
        "component_disagreement": disagreement,
        "component_min": component_min,
        "component_max": component_max,
    })
    df_all["number_str"] = df_all["number"].apply(lambda x: f"{int(x):02d}")
    q33, q67 = np.quantile(disagreement, [0.33, 0.67])
    df_all["agreement_tier"] = np.where(disagreement <= q33, "high", np.where(disagreement <= q67, "medium", "low"))
    df_all = df_all.sort_values("prob", ascending=False).reset_index(drop=True)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df_all.to_csv(out_dir / f"predict_next_{args.mode}_all_{target.isoformat()}.csv", index=False)
    df_all.head(4).to_csv(out_dir / f"predict_next_{args.mode}_top4_{target.isoformat()}.csv", index=False)
    df_all.head(8).to_csv(out_dir / f"predict_next_{args.mode}_top8_{target.isoformat()}.csv", index=False)
    df_all.head(10).to_csv(out_dir / f"predict_next_{args.mode}_top10_{target.isoformat()}.csv", index=False)

    picks = Picks(
        mode=args.mode,
        anchor_date=anchor.isoformat(),
        target_date=target.isoformat(),
        weights=w.as_dict(),
        calibration=calib.as_dict(),
        top4=df_all.head(4)["number_str"].tolist(),
        top8=df_all.head(8)["number_str"].tolist(),
        top10=df_all.head(10)["number_str"].tolist(),
    )
    (out_dir / f"picks_{args.mode}.json").write_text(json.dumps(picks.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] picks ready: mode={args.mode} target={target}")
    print("weights:", picks.weights)
    print("calibration:", picks.calibration)
    print("top4:", picks.top4)
    print("top8:", picks.top8)
    print("top10:", picks.top10)


if __name__ == "__main__":
    main()
