from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from calibration import learn_calibration
from ensemble_utils import (
    EnsembleWeights,
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    clip01,
    normalize_distribution,
    weight_grid,
)

COMPONENT_COLS = ["p_ml", "p_cau", "p_stat", "p_active", "p_stable"]


def _select_recent_complete_days(df: pd.DataFrame, window_days: int) -> list[str]:
    required = ["y", *COMPONENT_COLS]
    if any(c not in df.columns for c in required):
        return []
    by_day = df.groupby("target_date")[required].apply(lambda g: bool(g.notna().all().all()) and len(g) == 100)
    days = sorted([str(d) for d, ok in by_day.items() if bool(ok)])
    return days if window_days <= 0 else days[-window_days:]


def _day_weights(days: list[str], half_life_days: int) -> np.ndarray:
    if half_life_days <= 0:
        return np.ones(len(days), dtype=float)
    age = np.arange(len(days) - 1, -1, -1, dtype=float)
    lam = np.log(2.0) / float(half_life_days)
    w = np.exp(-lam * age)
    return w / np.mean(w)


def _optimize_weights_continuous(
    mode: str,
    P_ml: np.ndarray,
    P_cau: np.ndarray,
    P_stat: np.ndarray,
    P_a: np.ndarray,
    P_s: np.ndarray,
    Y: np.ndarray,
    w_day: np.ndarray,
) -> tuple[EnsembleWeights, float, float]:
    """Optimize five non-negative weights on the simplex using recent LogLoss."""
    try:
        from scipy.optimize import minimize
    except Exception:  # pragma: no cover
        minimize = None

    d_count = P_ml.shape[0]

    def eval_scores(w: np.ndarray) -> tuple[float, float]:
        w = np.clip(w, 0.0, 1.0)
        total = float(np.sum(w))
        prior = np.array([0.25, 0.30, 0.20, 0.125, 0.125], dtype=float)
        w = prior if total <= 0 else w / total
        p_blend = w[0] * P_ml + w[1] * P_cau + w[2] * P_stat + w[3] * P_a + w[4] * P_s

        if mode == "de":
            y_idx = np.argmax(Y, axis=1).astype(int)
            ll_list: list[float] = []
            br_list: list[float] = []
            for i in range(d_count):
                p = clip01(normalize_distribution(p_blend[i]), eps=1e-12)
                ll_list.append(categorical_logloss(p, int(y_idx[i])))
                br_list.append(categorical_brier(p, int(y_idx[i])))
            return float(np.average(ll_list, weights=w_day)), float(np.average(br_list, weights=w_day))

        p_clip = clip01(p_blend, eps=1e-6)
        ll = float(np.average([bernoulli_logloss(p_clip[i], Y[i]) for i in range(d_count)], weights=w_day))
        br = float(np.average([bernoulli_brier(p_clip[i], Y[i]) for i in range(d_count)], weights=w_day))
        return ll, br

    if minimize is None:
        best_w: EnsembleWeights | None = None
        best_ll, best_br = float("inf"), float("inf")
        for w in weight_grid(step=0.10):
            arr = np.array([w.w_ml, w.w_cau, w.w_stat, w.w_active, w.w_stable], dtype=float)
            ll, br = eval_scores(arr)
            if ll < best_ll - 1e-9 or (abs(ll - best_ll) <= 1e-9 and br < best_br):
                best_w, best_ll, best_br = w, ll, br
        assert best_w is not None
        return best_w.normalized(), best_ll, best_br

    prior = np.array([0.25, 0.30, 0.20, 0.125, 0.125], dtype=float)

    def obj(x: np.ndarray) -> float:
        ll = eval_scores(x)[0]
        # Shrink learned weights toward a diversified prior.  With short rolling
        # history this materially reduces optimizer noise/weight collapse.
        penalty = 0.025 * float(np.square(x - prior).sum())
        return ll + penalty

    constraints = ({"type": "eq", "fun": lambda x: np.sum(x) - 1.0},)
    bounds = [(0.0, 0.60)] * 5
    x0 = prior.copy()
    res = minimize(obj, x0=x0, bounds=bounds, constraints=constraints, method="SLSQP", options={"maxiter": 250})
    x = res.x if res.success else x0
    x = np.clip(x, 0.0, 1.0)
    x = x / max(float(x.sum()), 1e-12)
    ll, br = eval_scores(x)
    return EnsembleWeights(w_ml=float(x[0]), w_cau=float(x[1]), w_stat=float(x[2]), w_active=float(x[3]), w_stable=float(x[4])), ll, br


def main() -> None:
    ap = argparse.ArgumentParser(description="Learn five-component ensemble weights from labeled walk-forward history.")
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--history-dir", default="data/history")
    ap.add_argument("--out-dir", default="data/ensemble")
    ap.add_argument("--window-days", type=int, default=180)
    ap.add_argument("--min-days", type=int, default=20)
    ap.add_argument("--half-life-days", type=int, default=45)
    args = ap.parse_args()

    hist = Path(args.history_dir) / f"pred_{args.mode}.csv"
    if not hist.exists():
        print(f"[SKIP] history not found: {hist}")
        return
    df = pd.read_csv(hist)
    days = _select_recent_complete_days(df, args.window_days)
    if len(days) < args.min_days:
        print(f"[SKIP] five-component labeled history not mature: {len(days)} < {args.min_days}; keeping current/default weights")
        return

    df = df[df["target_date"].astype(str).isin(days)].copy()
    day_list = sorted(df["target_date"].astype(str).unique())
    d_count = len(day_list)
    arrays = {c: np.zeros((d_count, 100), dtype=np.float64) for c in COMPONENT_COLS}
    y = np.zeros((d_count, 100), dtype=np.float64)

    for i, d in enumerate(day_list):
        sub = df[df["target_date"].astype(str) == d].sort_values("number")
        for c in COMPONENT_COLS:
            arrays[c][i] = sub[c].astype(float).to_numpy()
        y[i] = sub["y"].astype(int).to_numpy()

    w_day = _day_weights(day_list, args.half_life_days)
    best_w, best_ll, best_br = _optimize_weights_continuous(
        args.mode, arrays["p_ml"], arrays["p_cau"], arrays["p_stat"], arrays["p_active"], arrays["p_stable"], y, w_day
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    weights_path = out_dir / f"weights_{args.mode}.json"
    payload = {
        "schema_version": 5,
        "mode": args.mode,
        "learned_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window_days": args.window_days,
        "half_life_days": args.half_life_days,
        "days_used": day_list,
        "metric": {"logloss": float(best_ll), "brier": float(best_br)},
        "weights": best_w.as_dict(),
    }
    weights_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] learned five-component weights for {args.mode} -> {weights_path}")

    p_blend = (
        best_w.w_ml * arrays["p_ml"]
        + best_w.w_cau * arrays["p_cau"]
        + best_w.w_stat * arrays["p_stat"]
        + best_w.w_active * arrays["p_active"]
        + best_w.w_stable * arrays["p_stable"]
    )
    calib = learn_calibration(args.mode, p_blend, y, sample_weight_by_day=w_day)
    calib_path = out_dir / f"calibration_{args.mode}.json"
    calib_payload = {
        "schema_version": 5,
        "mode": args.mode,
        "learned_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window_days": args.window_days,
        "half_life_days": args.half_life_days,
        "params": calib.as_dict(),
    }
    calib_path.write_text(json.dumps(calib_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] calibration -> {calib_path}")


if __name__ == "__main__":
    main()
