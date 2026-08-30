from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ensemble_utils import bernoulli_brier, bernoulli_logloss, categorical_brier, categorical_logloss, clip01, normalize_distribution


def main() -> None:
    ap = argparse.ArgumentParser(description="Append ensemble evaluation metrics to a rolling history table.")
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--history-dir", default="data/history")
    ap.add_argument("--predict-dir", default="data/predict")
    ap.add_argument("--out", default="data/prob_eval/ensemble_history.csv")
    args = ap.parse_args()

    hist_path = Path(args.history_dir) / f"pred_{args.mode}.csv"
    if not hist_path.exists():
        print("[SKIP] history not found:", hist_path)
        return

    df = pd.read_csv(hist_path)
    if "y" not in df.columns:
        print("[SKIP] labels not found in history")
        return

    # Choose latest fully-labeled day
    by_day = df.groupby("target_date")["y"].apply(lambda s: s.notna().all())
    labeled_days = [d for d, ok in by_day.items() if bool(ok)]
    if not labeled_days:
        print("[SKIP] no labeled days yet")
        return
    tdate = sorted(labeled_days)[-1]

    # Load ensemble predictions created for that day if available; otherwise compute from stored components + current weights
    # Prefer the stored blended all file
    pred_file = Path(args.predict_dir) / f"predict_next_{args.mode}_all_{tdate}.csv"
    if pred_file.exists():
        pred = pd.read_csv(pred_file).sort_values("number")
        p = pred["prob"].astype(float).to_numpy()
        if args.mode == "de":
            p = normalize_distribution(p)
            p = clip01(p, eps=1e-12)
    else:
        # blend from components present in history for that day
        sub = df[df["target_date"] == tdate].sort_values("number")
        p = 0.4 * sub["p_ml"].astype(float).to_numpy() + 0.3 * sub["p_active"].astype(float).to_numpy() + 0.3 * sub["p_stable"].astype(float).to_numpy()
        if args.mode == "de":
            p = normalize_distribution(p)
            p = clip01(p, eps=1e-12)
        else:
            p = clip01(p, eps=1e-6)

    y = df[df["target_date"] == tdate].sort_values("number")["y"].astype(int).to_numpy()

    if args.mode == "de":
        y_idx = int(np.argmax(y))
        ll = categorical_logloss(p, y_idx)
        br = categorical_brier(p, y_idx)
    else:
        ll = bernoulli_logloss(p, y)
        br = bernoulli_brier(p, y)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([{"mode": args.mode, "target_date": tdate, "logloss": ll, "brier": br, "updated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")}])
    if out.exists():
        old = pd.read_csv(out)
        old = old[(old["mode"] != args.mode) | (old["target_date"] != tdate)]
        new = pd.concat([old, row], ignore_index=True)
    else:
        new = row
    new.sort_values(["mode", "target_date"], inplace=True)
    new.to_csv(out, index=False)
    print(f"[OK] appended metrics for {args.mode} {tdate}: logloss={ll:.6f} brier={br:.6f} -> {out}")


if __name__ == "__main__":
    main()
