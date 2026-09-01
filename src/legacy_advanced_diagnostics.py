from __future__ import annotations

"""Exact-semantic research diagnostics recovered from the legacy ``xoso`` repo.

The modern VLA research battery already contains stronger permutation/FDR tests,
but several legacy questions had distinct statistical semantics.  This module
preserves those questions explicitly without feeding any production predictor:

* aggregate 2x2 Loto repeat independence across number/day transitions;
* weekday x final digit of the full special prize (7x10 contingency table);
* ACF of the full five-digit special-prize value with a Bartlett screening band;
* rolling N-day 00..99 coverage with both the historical simple benchmark and a
  benchmark derived from empirical marginal hit probabilities.

These are falsification/descriptive diagnostics only.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from lottery import Lottery
from research_diagnostics import bh_fdr


def aggregate_transition_independence(sparse: pd.DataFrame) -> dict[str, object]:
    hit = sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
    if len(hit) < 3:
        return {"name": "aggregate_loto_transition_independence", "p_value": None}

    prev = hit[:-1].ravel()
    nxt = hit[1:].ravel()
    yy = int(np.sum(prev & nxt))
    yn = int(np.sum(prev & ~nxt))
    ny = int(np.sum(~prev & nxt))
    nn = int(np.sum(~prev & ~nxt))
    table = np.asarray([[yy, yn], [ny, nn]], dtype=int)

    if np.any(table.sum(axis=0) == 0) or np.any(table.sum(axis=1) == 0):
        statistic, p_value = 0.0, 1.0
        expected_min = 0.0
    else:
        statistic, p_value, _, expected = stats.chi2_contingency(table, correction=True)
        expected_min = float(np.min(expected))

    p_next_given_hit = yy / max(yy + yn, 1)
    p_next_given_absent = ny / max(ny + nn, 1)
    return {
        "name": "aggregate_loto_transition_independence",
        "table": {
            "prev_hit_next_hit": yy,
            "prev_hit_next_miss": yn,
            "prev_miss_next_hit": ny,
            "prev_miss_next_miss": nn,
        },
        "statistic": float(statistic),
        "p_value": float(p_value),
        "expected_min": expected_min,
        "p_next_given_hit": float(p_next_given_hit),
        "p_next_given_absent": float(p_next_given_absent),
        "effect": float(p_next_given_hit - p_next_given_absent),
        "lift": (
            float(p_next_given_hit / p_next_given_absent)
            if p_next_given_absent > 0
            else None
        ),
        "method": "2x2 chi-square with Yates continuity correction; all 00..99 transitions pooled",
    }


def weekday_special_tail_contingency(raw: pd.DataFrame) -> dict[str, object]:
    dates = pd.to_datetime(raw["date"])
    special = raw["special"].to_numpy(dtype=int)
    tails = special % 10
    weekdays = dates.dt.weekday.to_numpy(dtype=int)
    table = np.zeros((7, 10), dtype=int)
    np.add.at(table, (weekdays, tails), 1)
    keep = table.sum(axis=1) > 0
    if int(keep.sum()) < 2:
        return {
            "name": "weekday_vs_full_special_tail",
            "statistic": None,
            "p_value": None,
            "table": table.tolist(),
        }
    statistic, p_value, dof, expected = stats.chi2_contingency(table[keep])
    return {
        "name": "weekday_vs_full_special_tail",
        "statistic": float(statistic),
        "p_value": float(p_value),
        "dof": int(dof),
        "min_expected_cell": float(np.min(expected)),
        "table": table.tolist(),
        "weekday_order": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "tail_order": list(range(10)),
        "method": "Pearson chi-square contingency test",
    }


def full_special_acf(raw: pd.DataFrame, *, max_lag: int = 15) -> pd.DataFrame:
    x = raw["special"].to_numpy(dtype=float)
    n = len(x)
    if n < 8:
        return pd.DataFrame()
    band = 1.96 / np.sqrt(n)
    rows: list[dict[str, object]] = []
    p_values: list[float] = []
    for lag in range(1, max(1, int(max_lag)) + 1):
        if lag >= n - 2:
            break
        a = x[:-lag]
        b = x[lag:]
        if np.std(a) == 0 or np.std(b) == 0:
            corr, p_value = 0.0, 1.0
        else:
            corr, p_value = stats.pearsonr(a, b)
            if not np.isfinite(corr) or not np.isfinite(p_value):
                corr, p_value = 0.0, 1.0
        p_values.append(float(p_value))
        rows.append(
            {
                "lag_days": int(lag),
                "acf": float(corr),
                "bartlett_lower": -float(band),
                "bartlett_upper": float(band),
                "exceeds_bartlett": bool(abs(corr) > band),
                "p_value": float(p_value),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["q_value_fdr"] = bh_fdr(np.asarray(p_values, dtype=float))
        out["fdr_05"] = out["q_value_fdr"] <= 0.05
    return out


def rolling_coverage(
    sparse: pd.DataFrame,
    *,
    windows: tuple[int, ...] = (3, 7, 14, 30),
) -> pd.DataFrame:
    hit = sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
    n = len(hit)
    if n == 0:
        return pd.DataFrame()
    empirical_p = hit.mean(axis=0)
    rows: list[dict[str, object]] = []
    for window in sorted({int(w) for w in windows if int(w) > 0}):
        if n < window:
            continue
        observed = np.asarray(
            [int(hit[start : start + window].any(axis=0).sum()) for start in range(n - window + 1)],
            dtype=float,
        )
        # Exact historical benchmark from the legacy implementation.  It treats
        # the 27 prize endings as independent uniform draws and is retained only
        # for semantic comparability.
        legacy_expected = 100.0 * (1.0 - (99.0 / 100.0) ** (27 * window))
        empirical_expected = float(np.sum(1.0 - np.power(1.0 - empirical_p, window)))
        rows.append(
            {
                "window_days": window,
                "rolling_windows": int(len(observed)),
                "observed_mean_distinct": float(observed.mean()),
                "observed_std_distinct": float(observed.std(ddof=0)),
                "observed_min_distinct": int(observed.min()),
                "observed_max_distinct": int(observed.max()),
                "legacy_uniform_expected": float(legacy_expected),
                "empirical_marginal_expected": empirical_expected,
                "mean_minus_legacy_expected": float(observed.mean() - legacy_expected),
                "mean_minus_empirical_expected": float(observed.mean() - empirical_expected),
            }
        )
    return pd.DataFrame(rows)


def run(
    raw: pd.DataFrame,
    sparse: pd.DataFrame,
    *,
    out_dir: Path | str = "data/research/legacy_advanced",
    max_lag: int = 15,
    coverage_windows: tuple[int, ...] = (3, 7, 14, 30),
) -> dict[str, object]:
    raw = raw.sort_values("date").reset_index(drop=True)
    sparse = sparse.sort_values("date").reset_index(drop=True)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    transition = aggregate_transition_independence(sparse)
    weekday = weekday_special_tail_contingency(raw)
    acf = full_special_acf(raw, max_lag=max_lag)
    coverage = rolling_coverage(sparse, windows=coverage_windows)

    acf.to_csv(out / "full_special_acf.csv", index=False)
    coverage.to_csv(out / "rolling_coverage.csv", index=False)
    (out / "aggregate_transition.json").write_text(
        json.dumps(transition, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "weekday_special_tail.json").write_text(
        json.dumps(weekday, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "anchor_date": pd.to_datetime(raw["date"]).max().date().isoformat(),
        "research_only": True,
        "aggregate_transition": transition,
        "weekday_special_tail": weekday,
        "full_special_acf_rows": int(len(acf)),
        "full_special_acf_fdr_05": int(acf["fdr_05"].sum()) if not acf.empty else 0,
        "coverage_windows": coverage["window_days"].astype(int).tolist() if not coverage.empty else [],
        "note": "Exact legacy semantics preserved for research comparability; no production weights consume these artifacts.",
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _parse_windows(value: str) -> tuple[int, ...]:
    return tuple(sorted({int(x.strip()) for x in value.split(",") if x.strip() and int(x.strip()) > 0}))


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate exact-semantic legacy advanced diagnostics.")
    ap.add_argument("--out-dir", default="data/research/legacy_advanced")
    ap.add_argument("--max-lag", type=int, default=15)
    ap.add_argument("--coverage-windows", default="3,7,14,30")
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    sparse = lot.get_sparse_data().sort_values("date").reset_index(drop=True)
    if raw.empty or sparse.empty:
        raise SystemExit("No data loaded")
    manifest = run(
        raw,
        sparse,
        out_dir=args.out_dir,
        max_lag=max(1, int(args.max_lag)),
        coverage_windows=_parse_windows(args.coverage_windows),
    )
    print("[OK] exact legacy advanced diagnostics ->", args.out_dir, "anchor=", manifest["anchor_date"])


if __name__ == "__main__":
    main()
