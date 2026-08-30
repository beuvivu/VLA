from __future__ import annotations

"""Multiple-testing-aware statistical diagnostics for XSMB.

This module deliberately separates *descriptive statistical anomaly* from
prediction.  It uses exact binomial tests, Benjamini-Hochberg FDR control and a
Beta-Binomial shrinkage posterior so that random extremes across 100 numbers are
less likely to be mislabeled as meaningful signals.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist
from scipy.stats import binomtest, chisquare

from lottery import Lottery, RepoPaths


def _bh_fdr(p_values: np.ndarray) -> np.ndarray:
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]
    q_ranked = ranked * n / np.arange(1, n + 1)
    q_ranked = np.minimum.accumulate(q_ranked[::-1])[::-1]
    q_ranked = np.clip(q_ranked, 0.0, 1.0)
    q = np.empty_like(q_ranked)
    q[order] = q_ranked
    return q


def _window_hit_matrix(mode: str, two: pd.DataFrame, sparse: pd.DataFrame, window_days: int) -> tuple[np.ndarray, float, pd.Timestamp, pd.Timestamp]:
    two = two.copy()
    sparse = sparse.copy()
    two["date"] = pd.to_datetime(two["date"])
    sparse["date"] = pd.to_datetime(sparse["date"])
    latest = two["date"].max()
    cutoff = latest - pd.Timedelta(days=max(1, window_days) - 1)
    two_w = two[two["date"] >= cutoff].reset_index(drop=True)
    sparse_w = sparse[sparse["date"] >= cutoff].reset_index(drop=True)

    if mode == "de":
        de = (two_w["special"].astype(int).to_numpy() % 100).astype(int)
        hit = np.zeros((len(two_w), 100), dtype=np.int8)
        hit[np.arange(len(two_w)), de] = 1
        baseline = 0.01
    else:
        hit = (sparse_w.drop(columns=["date"]).to_numpy(dtype=int) > 0).astype(np.int8)
        # Empirical grand rate is the right null for "is this number unusual vs
        # the field?" and automatically accounts for within-draw duplicates.
        baseline = float(hit.mean()) if hit.size else 0.0

    start = two_w["date"].min() if not two_w.empty else latest
    return hit, baseline, start, latest


def number_significance(mode: str, two: pd.DataFrame, sparse: pd.DataFrame, *, window_days: int, prior_strength: float = 40.0) -> pd.DataFrame:
    hit, baseline, start, latest = _window_hit_matrix(mode, two, sparse, window_days)
    n = int(hit.shape[0])
    if n == 0:
        return pd.DataFrame()

    k = hit.sum(axis=0).astype(int)
    rate = k / n
    variance = max(baseline * (1.0 - baseline), 1e-12)
    z = (rate - baseline) / np.sqrt(variance / n)
    p_values = np.array([binomtest(int(x), n, baseline, alternative="two-sided").pvalue for x in k])
    q_values = _bh_fdr(p_values)

    a0 = max(1e-6, baseline * prior_strength)
    b0 = max(1e-6, (1.0 - baseline) * prior_strength)
    post_a = a0 + k
    post_b = b0 + n - k
    post_mean = post_a / (post_a + post_b)
    ci_low = beta_dist.ppf(0.025, post_a, post_b)
    ci_high = beta_dist.ppf(0.975, post_a, post_b)

    lift = np.divide(rate, baseline, out=np.zeros_like(rate, dtype=float), where=baseline > 0)
    effect = rate - baseline
    evidence = -np.log10(np.clip(q_values, 1e-12, 1.0)) * np.minimum(np.abs(z) / 3.0, 1.0)

    out = pd.DataFrame(
        {
            "mode": mode,
            "window_days": window_days,
            "start_date": start.date().isoformat(),
            "end_date": latest.date().isoformat(),
            "number": np.arange(100, dtype=int),
            "number_str": [f"{i:02d}" for i in range(100)],
            "trials": n,
            "hits": k,
            "observed_rate": rate,
            "baseline_rate": baseline,
            "lift": lift,
            "effect": effect,
            "z_score": z,
            "p_value": p_values,
            "q_value_fdr": q_values,
            "posterior_mean": post_mean,
            "posterior_ci_low": ci_low,
            "posterior_ci_high": ci_high,
            "evidence_score": evidence,
            "fdr_05": q_values <= 0.05,
        }
    )
    return out.sort_values(["evidence_score", "q_value_fdr", "posterior_mean"], ascending=[False, True, False]).reset_index(drop=True)


def global_diagnostics(two: pd.DataFrame, sparse: pd.DataFrame, *, window_days: int = 365) -> dict:
    two = two.copy()
    two["date"] = pd.to_datetime(two["date"])
    latest = two["date"].max()
    cutoff = latest - pd.Timedelta(days=window_days - 1)
    two_w = two[two["date"] >= cutoff].reset_index(drop=True)
    if two_w.empty:
        return {}

    de = (two_w["special"].astype(int).to_numpy() % 100).astype(int)
    de_counts = np.bincount(de, minlength=100)
    chi_de = chisquare(de_counts)
    probs = de_counts / max(de_counts.sum(), 1)
    nz = probs[probs > 0]
    entropy = float(-(nz * np.log(nz)).sum())
    entropy_norm = entropy / np.log(100.0)

    all_vals = (two_w.drop(columns=["date"]).to_numpy(dtype=int) % 100).reshape(-1)
    all_counts = np.bincount(all_vals, minlength=100)
    chi_all = chisquare(all_counts)

    if len(de) > 2 and np.std(de[:-1]) > 0 and np.std(de[1:]) > 0:
        lag1_corr = float(np.corrcoef(de[:-1], de[1:])[0, 1])
    else:
        lag1_corr = 0.0

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window_days": window_days,
        "start_date": two_w["date"].min().date().isoformat(),
        "end_date": latest.date().isoformat(),
        "draw_days": int(len(two_w)),
        "de_uniform_chi2": float(chi_de.statistic),
        "de_uniform_p_value": float(chi_de.pvalue),
        "de_entropy_normalized": entropy_norm,
        "all_prizes_uniform_chi2": float(chi_all.statistic),
        "all_prizes_uniform_p_value": float(chi_all.pvalue),
        "de_lag1_numeric_corr": lag1_corr,
        "interpretation": "Diagnostics test historical deviations only; statistical significance is not evidence of future predictability.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="FDR/Bayesian statistical diagnostics for XSMB.")
    ap.add_argument("--windows", default="30,90,365", help="Comma-separated rolling windows.")
    ap.add_argument("--out-dir", default="data/significance")
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data()
    sparse = lot.get_sparse_data()
    if two.empty or sparse.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    windows = sorted({max(7, int(x.strip())) for x in args.windows.split(",") if x.strip()})

    for mode in ("loto", "de"):
        for window in windows:
            table = number_significance(mode, two, sparse, window_days=window)
            table.to_csv(out_dir / f"number_significance_{mode}_{window}d.csv", index=False)
            table.to_json(out_dir / f"number_significance_{mode}_{window}d.json", orient="records", indent=2)

    diag = global_diagnostics(two, sparse, window_days=max(windows))
    (out_dir / "global_diagnostics.json").write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] significance diagnostics -> {out_dir}")


if __name__ == "__main__":
    main()
