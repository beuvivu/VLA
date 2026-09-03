from __future__ import annotations

"""Falsification-oriented diagnostics for historical XSMB data.

The goal is not to manufacture predictive signals.  The battery asks whether
commonly claimed structure (weekday effects, serial dependence, lô-rơi effects,
frequency imbalance) survives tests that preserve important properties of the
observed draws.  Multiple p-values are FDR-adjusted before interpretation.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from lottery import Lottery


def bh_fdr(values: list[float] | np.ndarray) -> np.ndarray:
    p = np.asarray(values, dtype=float)
    out = np.full_like(p, np.nan, dtype=float)
    finite = np.isfinite(p)
    if not finite.any():
        return out
    pf = p[finite]
    order = np.argsort(pf)
    ranked = pf[order]
    q = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0.0, 1.0)
    restored = np.empty_like(q)
    restored[order] = q
    out[finite] = restored
    return out


def _runs_test(values: np.ndarray) -> tuple[float, float]:
    x = np.asarray(values, dtype=float)
    if len(x) < 20:
        return float("nan"), float("nan")
    med = np.median(x)
    signs = x[x != med] > med
    n1 = int(signs.sum())
    n2 = int((~signs).sum())
    n = n1 + n2
    if n < 10 or n1 == 0 or n2 == 0:
        return float("nan"), float("nan")
    runs = 1 + int(np.sum(signs[1:] != signs[:-1]))
    mean = 1.0 + 2.0 * n1 * n2 / n
    var = (2.0 * n1 * n2 * (2.0 * n1 * n2 - n)) / (n * n * (n - 1))
    if var <= 0:
        return float("nan"), float("nan")
    z = (runs - mean) / np.sqrt(var)
    return float(z), float(2.0 * stats.norm.sf(abs(z)))


def _entropy_ratio(counts: np.ndarray) -> float:
    c = np.asarray(counts, dtype=float)
    total = c.sum()
    if total <= 0:
        return float("nan")
    p = c / total
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum() / np.log2(len(c)))


def _weekday_test(dates: pd.Series, de_tail: np.ndarray, *, permutations: int, seed: int) -> dict:
    weekday = pd.to_datetime(dates).dt.weekday.to_numpy(dtype=int)
    table = np.zeros((7, 10), dtype=int)
    np.add.at(table, (weekday, de_tail % 10), 1)
    keep = table.sum(axis=1) > 0
    observed, asymptotic_p, _, expected = stats.chi2_contingency(table[keep], correction=False)

    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(max(1, permutations)):
        perm = rng.permutation(weekday)
        t = np.zeros((7, 10), dtype=int)
        np.add.at(t, (perm, de_tail % 10), 1)
        stat, _, _, _ = stats.chi2_contingency(t[t.sum(axis=1) > 0], correction=False)
        ge += int(stat >= observed - 1e-12)
    perm_p = (ge + 1) / (max(1, permutations) + 1)
    return {
        "statistic": float(observed),
        "p_value_asymptotic": float(asymptotic_p),
        "p_value_permutation": float(perm_p),
        "min_expected_cell": float(np.min(expected)),
        "method": "weekday labels permuted; DE tail distribution preserved",
    }


def _transition_repeat_test(hit: np.ndarray, *, permutations: int, seed: int) -> dict:
    h = np.asarray(hit, dtype=bool)
    if len(h) < 30:
        return {"effect": float("nan"), "p_value": float("nan")}
    prev = h[:-1]
    nxt = h[1:]

    def effect(a: np.ndarray, b: np.ndarray) -> float:
        yes = b[a]
        no = b[~a]
        if yes.size == 0 or no.size == 0:
            return float("nan")
        return float(yes.mean() - no.mean())

    observed = effect(prev, nxt)
    rng = np.random.default_rng(seed)
    # Circular shifts preserve each day's 100-number cross-sectional structure
    # and most of the target series' temporal texture while breaking t -> t+1.
    possible = np.arange(2, max(3, len(nxt) - 1))
    if len(possible) == 0:
        return {"effect": observed, "p_value": float("nan")}
    shifts = rng.choice(possible, size=max(1, permutations), replace=len(possible) < permutations)
    ge = 0
    null_effects: list[float] = []
    for shift in shifts:
        e = effect(prev, np.roll(nxt, int(shift), axis=0))
        null_effects.append(e)
        ge += int(abs(e) >= abs(observed) - 1e-12)
    p = (ge + 1) / (len(shifts) + 1)
    return {
        "effect": observed,
        "p_value": float(p),
        "null_mean": float(np.mean(null_effects)),
        "null_std": float(np.std(null_effects)),
        "method": "two-sided day-level circular-shift permutation",
    }


def _acf_scan(values: np.ndarray, *, max_lag: int) -> pd.DataFrame:
    x = np.asarray(values, dtype=float)
    rows: list[dict[str, float | int]] = []
    for lag in range(1, max(1, max_lag) + 1):
        if len(x) <= lag + 5:
            continue
        left = x[:-lag]
        right = x[lag:]
        if np.std(left) == 0 or np.std(right) == 0:
            corr, p = 0.0, 1.0
        else:
            corr, p = stats.pearsonr(left, right)
        rows.append({"lag": lag, "correlation": float(corr), "p_value": float(p)})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["q_value_fdr"] = bh_fdr(out["p_value"].to_numpy(dtype=float))
        out["fdr_05"] = out["q_value_fdr"] <= 0.05
    return out


def _coverage_summary(hit: np.ndarray, windows: tuple[int, ...] = (7, 14, 30)) -> list[dict[str, float | int]]:
    h = np.asarray(hit, dtype=bool)
    p = h.mean(axis=0)
    rows: list[dict[str, float | int]] = []
    for window in windows:
        if len(h) < window:
            continue
        observed = []
        for end in range(window, len(h) + 1):
            observed.append(int(h[end - window : end].any(axis=0).sum()))
        expected = float(np.sum(1.0 - np.power(1.0 - p, window)))
        rows.append(
            {
                "window_days": window,
                "observed_mean_distinct": float(np.mean(observed)),
                "observed_min_distinct": int(np.min(observed)),
                "observed_max_distinct": int(np.max(observed)),
                "expected_from_empirical_marginals": expected,
                "mean_minus_expected": float(np.mean(observed) - expected),
            }
        )
    return rows


def build_report(two: pd.DataFrame, sparse: pd.DataFrame, *, permutations: int = 127, seed: int = 20260901, max_lag: int = 14) -> tuple[dict, pd.DataFrame]:
    two = two.sort_values("date").reset_index(drop=True).copy()
    sparse = sparse.sort_values("date").reset_index(drop=True).copy()
    if len(two) != len(sparse):
        raise ValueError("2-digit and sparse data must have identical draw counts")

    de = (two["special"].to_numpy(dtype=int) % 100).astype(int)
    hit = (sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0)
    de_counts = np.bincount(de, minlength=100)
    all_counts = (sparse.drop(columns=["date"]).to_numpy(dtype=int)).sum(axis=0).astype(int)

    de_chi = stats.chisquare(de_counts)
    # For all-prize endings, expected counts are equal under exchangeability of
    # the 00..99 suffix labels; duplicates within a draw are retained.
    loto_chi = stats.chisquare(all_counts)
    runs_z, runs_p = _runs_test(de)
    weekday = _weekday_test(two["date"], de % 10, permutations=permutations, seed=seed)
    repeat = _transition_repeat_test(hit, permutations=permutations, seed=seed + 1)
    acf = _acf_scan(de, max_lag=max_lag)

    primary = [
        {"name": "de_suffix_uniformity", "statistic": float(de_chi.statistic), "p_value": float(de_chi.pvalue)},
        {"name": "all_prize_suffix_uniformity", "statistic": float(loto_chi.statistic), "p_value": float(loto_chi.pvalue)},
        {"name": "de_runs_independence", "statistic": runs_z, "p_value": runs_p},
        {"name": "weekday_vs_de_tail", "statistic": float(weekday["statistic"]), "p_value": float(weekday["p_value_permutation"])},
        {"name": "loto_repeat_dependency", "statistic": float(repeat["effect"]), "p_value": float(repeat["p_value"])},
    ]
    q = bh_fdr([float(row["p_value"]) for row in primary])
    for row, qv in zip(primary, q, strict=True):
        row["q_value_fdr"] = float(qv) if np.isfinite(qv) else None
        row["fdr_05"] = bool(np.isfinite(qv) and qv <= 0.05)

    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "start_date": pd.to_datetime(two["date"]).min().date().isoformat(),
        "end_date": pd.to_datetime(two["date"]).max().date().isoformat(),
        "draw_days": int(len(two)),
        "permutations": int(permutations),
        "primary_tests": primary,
        "de_entropy_ratio": _entropy_ratio(de_counts),
        "all_prize_entropy_ratio": _entropy_ratio(all_counts),
        "weekday_test": weekday,
        "loto_repeat_test": repeat,
        "coverage": _coverage_summary(hit),
        "acf_significant_lags_fdr05": acf.loc[acf.get("fdr_05", False) == True, "lag"].astype(int).tolist() if not acf.empty else [],  # noqa: E712
        "interpretation": (
            "These are historical falsification diagnostics. Failing to reject randomness does not prove randomness; "
            "rejecting a null does not by itself establish exploitable future predictability."
        ),
    }
    return report, acf


def main() -> None:
    ap = argparse.ArgumentParser(description="Randomness/dependence diagnostics with FDR and permutation tests.")
    ap.add_argument("--out-dir", default="data/research")
    ap.add_argument("--permutations", type=int, default=127)
    ap.add_argument("--max-lag", type=int, default=14)
    ap.add_argument("--seed", type=int, default=20260901)
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data()
    sparse = lot.get_sparse_data()
    if two.empty or sparse.empty:
        raise SystemExit("No data loaded")

    report, acf = build_report(
        two,
        sparse,
        permutations=max(15, args.permutations),
        seed=args.seed,
        max_lag=max(1, args.max_lag),
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scientific_diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    acf.to_csv(out / "de_acf_scan.csv", index=False)
    print(f"[OK] scientific diagnostics -> {out}")


if __name__ == "__main__":
    main()
