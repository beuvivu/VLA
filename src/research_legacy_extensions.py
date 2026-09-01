from __future__ import annotations

"""Research-only extensions preserved from the final legacy repository audit.

These diagnostics deliberately remain outside the production probability ensemble.
They recover useful descriptive/falsification capabilities that were present in the
legacy ``xoso`` repository but not exposed with equivalent semantics in VLA:

- calendar-day number and pair recency/gap evidence for Loto and De;
- De weekday profiles;
- per-number next-day transition independence tests with FDR control;
- per-number Loto presence ACF with Bartlett screening bands;
- full-special KS uniformity and Ljung-Box aggregate dependence diagnostics;
- cumulative coverage / coupon-collector context.

Nothing in this module is a betting rule or an automatic predictor weight.
"""

import argparse
import json
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

from lottery import Lottery
from research_diagnostics import bh_fdr

Mode = Literal["loto", "de"]


def _sorted_dates(df: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(df["date"]).dt.normalize())


def _presence_matrix(two: pd.DataFrame, mode: Mode) -> np.ndarray:
    if mode == "de":
        de = (two["special"].to_numpy(dtype=int) % 100).astype(int)
        out = np.zeros((len(two), 100), dtype=bool)
        out[np.arange(len(two)), de] = True
        return out

    values = two.drop(columns=["date"]).to_numpy(dtype=int) % 100
    out = np.zeros((len(two), 100), dtype=bool)
    for i, row in enumerate(values):
        out[i, np.unique(row)] = True
    return out


def _gap_metrics(hit_dates: pd.DatetimeIndex, all_dates: pd.DatetimeIndex) -> dict[str, float | int | None]:
    """Return explicitly labelled calendar-gap metrics.

    ``completed_interval_*`` is the distance in calendar days between hit dates.
    ``max_observed_absence_days`` counts days with no hit, including left/right
    boundary segments. This makes the old ``max_gap`` semantics explicit instead
    of mixing completed cycles with boundary-censored absences.
    """
    if len(all_dates) == 0:
        return {
            "current_absence_days": None,
            "mean_completed_interval_days": None,
            "median_completed_interval_days": None,
            "max_completed_interval_days": None,
            "max_observed_absence_days": None,
        }
    if len(hit_dates) == 0:
        span = int((all_dates[-1] - all_dates[0]).days) + 1
        return {
            "current_absence_days": span,
            "mean_completed_interval_days": None,
            "median_completed_interval_days": None,
            "max_completed_interval_days": None,
            "max_observed_absence_days": span,
        }

    current = int((all_dates[-1] - hit_dates[-1]).days)
    leading = int((hit_dates[0] - all_dates[0]).days)
    if len(hit_dates) >= 2:
        intervals = np.asarray((hit_dates[1:] - hit_dates[:-1]).days, dtype=float)
        absence_between = np.maximum(intervals - 1.0, 0.0)
        mean_interval = float(intervals.mean())
        median_interval = float(np.median(intervals))
        max_interval = int(intervals.max())
        max_between = int(absence_between.max())
    else:
        mean_interval = median_interval = None
        max_interval = None
        max_between = 0

    return {
        "current_absence_days": current,
        "mean_completed_interval_days": mean_interval,
        "median_completed_interval_days": median_interval,
        "max_completed_interval_days": max_interval,
        "max_observed_absence_days": max(leading, current, max_between),
    }


def number_recency_calendar(
    two: pd.DataFrame, *, mode: Mode, recent_dates: int = 8
) -> pd.DataFrame:
    dates = _sorted_dates(two)
    hit = _presence_matrix(two, mode)
    rows: list[dict[str, object]] = []

    for number in range(100):
        idx = np.flatnonzero(hit[:, number])
        hdates = pd.DatetimeIndex(dates[idx]) if idx.size else pd.DatetimeIndex([])
        metrics = _gap_metrics(hdates, dates)
        current = metrics["current_absence_days"]
        mean_int = metrics["mean_completed_interval_days"]
        max_obs = metrics["max_observed_absence_days"]

        rows.append(
            {
                "mode": mode,
                "number": number,
                "number_str": f"{number:02d}",
                "hit_days": int(idx.size),
                "last_date": hdates[-1].date().isoformat() if len(hdates) else None,
                **metrics,
                "current_to_mean_interval": (
                    float(current) / float(mean_int)
                    if current is not None and mean_int not in (None, 0)
                    else None
                ),
                "current_to_max_observed_absence": (
                    float(current) / float(max_obs)
                    if current is not None and max_obs not in (None, 0)
                    else None
                ),
                "recent_dates": json.dumps(
                    [d.date().isoformat() for d in hdates[-recent_dates:][::-1]],
                    ensure_ascii=False,
                ),
            }
        )

    out = pd.DataFrame(rows)
    out["absence_rank"] = (
        pd.to_numeric(out["current_absence_days"], errors="coerce")
        .rank(method="min", ascending=False)
        .astype("Int64")
    )
    return out.sort_values(
        ["current_absence_days", "hit_days"], ascending=[False, True], ignore_index=True
    )


def pair_recency_calendar(
    two: pd.DataFrame, *, recent_dates: int = 6, min_count: int = 1
) -> pd.DataFrame:
    dates = _sorted_dates(two)
    hit = _presence_matrix(two, "loto")
    n_days = max(len(hit), 1)
    single = hit.sum(axis=0, dtype=int)
    pair_days: dict[tuple[int, int], list[int]] = {}

    for t in range(len(hit)):
        nums = np.flatnonzero(hit[t]).tolist()
        for a, b in combinations(nums, 2):
            pair_days.setdefault((int(a), int(b)), []).append(t)

    rows: list[dict[str, object]] = []
    for (a, b), idx_list in pair_days.items():
        if len(idx_list) < min_count:
            continue
        idx = np.asarray(idx_list, dtype=int)
        hdates = pd.DatetimeIndex(dates[idx])
        metrics = _gap_metrics(hdates, dates)
        pa = float(single[a]) / n_days
        pb = float(single[b]) / n_days
        support = len(idx_list) / n_days
        expected = pa * pb
        rows.append(
            {
                "a": a,
                "a_str": f"{a:02d}",
                "b": b,
                "b_str": f"{b:02d}",
                "cooccurrence_days": len(idx_list),
                "support": support,
                "independence_expected": expected,
                "lift": support / expected if expected > 0 else 0.0,
                "last_date": hdates[-1].date().isoformat(),
                **metrics,
                "recent_dates": json.dumps(
                    [d.date().isoformat() for d in hdates[-recent_dates:][::-1]],
                    ensure_ascii=False,
                ),
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["lift", "cooccurrence_days"], ascending=[False, False], ignore_index=True
    )


def de_weekday_profile(two: pd.DataFrame, *, prior_strength: float = 28.0) -> pd.DataFrame:
    dates = _sorted_dates(two)
    de = (two["special"].to_numpy(dtype=int) % 100).astype(int)
    overall = np.bincount(de, minlength=100).astype(float) / max(len(de), 1)
    rows: list[dict[str, object]] = []

    for weekday in range(7):
        mask = dates.weekday == weekday
        trials = int(mask.sum())
        counts = np.bincount(de[mask], minlength=100) if trials else np.zeros(100, dtype=int)
        raw_rate = counts / max(trials, 1)
        smoothed = (counts + prior_strength * overall) / (trials + prior_strength)
        for number in range(100):
            rows.append(
                {
                    "weekday": weekday,
                    "weekday_name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][weekday],
                    "number": number,
                    "number_str": f"{number:02d}",
                    "trials": trials,
                    "hits": int(counts[number]),
                    "rate": float(raw_rate[number]),
                    "overall_rate": float(overall[number]),
                    "lift_vs_overall": (
                        float(raw_rate[number] / overall[number])
                        if overall[number] > 0
                        else None
                    ),
                    "empirical_bayes_rate": float(smoothed[number]),
                }
            )
    return pd.DataFrame(rows)


def transition_independence_by_number(sparse: pd.DataFrame) -> pd.DataFrame:
    h = sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
    if len(h) < 3:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    pvals: list[float] = []

    for number in range(100):
        prev = h[:-1, number]
        nxt = h[1:, number]
        a = int(np.sum(prev & nxt))
        b = int(np.sum(prev & ~nxt))
        c = int(np.sum(~prev & nxt))
        d = int(np.sum(~prev & ~nxt))
        table = np.array([[a, b], [c, d]], dtype=int)
        p_hit = a / max(a + b, 1)
        p_abs = c / max(c + d, 1)
        if np.any(table.sum(axis=0) == 0) or np.any(table.sum(axis=1) == 0):
            p = 1.0
            method = "degenerate_no_variation"
        else:
            expected = stats.contingency.expected_freq(table)
            if np.any(expected < 5):
                _, p = stats.fisher_exact(table, alternative="two-sided")
                method = "fisher_exact"
            else:
                _, p, _, _ = stats.chi2_contingency(table, correction=False)
                method = "chi_square"
        pvals.append(float(p))
        rows.append(
            {
                "number": number,
                "number_str": f"{number:02d}",
                "prev_hit_next_hit": a,
                "prev_hit_next_miss": b,
                "prev_miss_next_hit": c,
                "prev_miss_next_miss": d,
                "p_next_given_hit": p_hit,
                "p_next_given_absent": p_abs,
                "effect": p_hit - p_abs,
                "lift": p_hit / p_abs if p_abs > 0 else None,
                "test": method,
                "p_value": float(p),
            }
        )

    out = pd.DataFrame(rows)
    out["q_value_fdr"] = bh_fdr(np.asarray(pvals, dtype=float))
    out["fdr_05"] = out["q_value_fdr"] <= 0.05
    return out.sort_values(
        ["fdr_05", "q_value_fdr", "effect"], ascending=[False, True, False], ignore_index=True
    )


def loto_acf_bartlett(
    sparse: pd.DataFrame, *, lags: tuple[int, ...] = (1, 2, 3, 7, 14, 30)
) -> pd.DataFrame:
    h = (sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0).astype(float)
    n = len(h)
    if n < 4:
        return pd.DataFrame()
    band = 1.96 / np.sqrt(n)
    rows: list[dict[str, object]] = []
    pvals: list[float] = []

    for number in range(100):
        x = h[:, number]
        for lag in lags:
            if lag <= 0 or lag >= n - 2:
                continue
            a, b = x[:-lag], x[lag:]
            if np.std(a) == 0 or np.std(b) == 0:
                r, p = 0.0, 1.0
            else:
                r, p = stats.pearsonr(a, b)
                if not np.isfinite(r) or not np.isfinite(p):
                    r, p = 0.0, 1.0
            pvals.append(float(p))
            rows.append(
                {
                    "number": number,
                    "number_str": f"{number:02d}",
                    "lag_days": lag,
                    "acf": float(r),
                    "bartlett_lower": -float(band),
                    "bartlett_upper": float(band),
                    "exceeds_bartlett": bool(abs(r) > band),
                    "p_value": float(p),
                }
            )

    out = pd.DataFrame(rows)
    out["q_value_fdr"] = bh_fdr(np.asarray(pvals, dtype=float))
    out["fdr_05"] = out["q_value_fdr"] <= 0.05
    return out.sort_values(
        ["fdr_05", "q_value_fdr", "exceeds_bartlett", "acf"],
        ascending=[False, True, False, False],
        ignore_index=True,
    )


def coverage_coupon_summary(sparse: pd.DataFrame) -> dict[str, object]:
    h = sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
    if len(h) == 0:
        return {}
    distinct_per_day = h.sum(axis=1)
    cumulative = np.logical_or.accumulate(h, axis=0)
    cum_counts = cumulative.sum(axis=1)
    first_full = np.flatnonzero(cum_counts == 100)
    harmonic_100 = float(np.sum(1.0 / np.arange(1, 101, dtype=float)))
    avg_distinct = float(distinct_per_day.mean())

    milestones: dict[str, int | None] = {}
    for target in (50, 75, 90, 95, 99, 100):
        idx = np.flatnonzero(cum_counts >= target)
        milestones[str(target)] = int(idx[0] + 1) if idx.size else None

    unseen = np.flatnonzero(~h.any(axis=0)).astype(int).tolist()
    return {
        "draw_days": int(len(h)),
        "average_distinct_loto_per_day": avg_distinct,
        "all_time_distinct_numbers": int(h.any(axis=0).sum()),
        "unseen_numbers": [f"{n:02d}" for n in unseen],
        "first_full_coverage_day_from_start": int(first_full[0] + 1) if first_full.size else None,
        "coverage_milestone_days_from_start": milestones,
        "coupon_collector_expected_days_approx": (
            float(100.0 * harmonic_100 / avg_distinct) if avg_distinct > 0 else None
        ),
        "coupon_note": (
            "Heuristic context only: 100*H_100/average distinct numbers per draw "
            "assumes simplified independent coupon sampling and is not a prediction model."
        ),
    }


def ks_special_uniformity(raw: pd.DataFrame) -> dict[str, object]:
    if raw.empty or "special" not in raw:
        return {"name": "ks_full_special_uniformity", "statistic": None, "p_value": None}
    x = raw["special"].to_numpy(dtype=float) / 100000.0
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return {"name": "ks_full_special_uniformity", "statistic": None, "p_value": None}
    d, p = stats.kstest(x, "uniform")
    return {
        "name": "ks_full_special_uniformity",
        "statistic": float(d),
        "p_value": float(p),
        "note": "H0: full five-digit special prize is Uniform[0,1) after scaling.",
    }


def ljung_box_even_tail_count(two: pd.DataFrame, *, lags: int = 10) -> dict[str, object]:
    values = two.drop(columns=["date"]).to_numpy(dtype=int) % 100
    series = ((values % 10) % 2 == 0).sum(axis=1).astype(float)
    n = len(series)
    max_lag = min(int(lags), n - 2)
    if n < 12 or max_lag < 1:
        return {"name": "ljung_box_even_tail_count", "statistic": None, "p_value": None}
    x = series - series.mean()
    denom = float(np.sum(x * x))
    if denom <= 0:
        return {
            "name": "ljung_box_even_tail_count",
            "statistic": 0.0,
            "p_value": 1.0,
            "lags": max_lag,
        }
    q = 0.0
    for lag in range(1, max_lag + 1):
        rho = float(np.sum(x[lag:] * x[:-lag]) / denom)
        q += rho * rho / (n - lag)
    q *= n * (n + 2)
    p = float(stats.chi2.sf(q, df=max_lag))
    return {
        "name": "ljung_box_even_tail_count",
        "statistic": float(q),
        "p_value": p,
        "lags": max_lag,
        "note": "H0: aggregate count of even-ending Loto entries has no serial autocorrelation through the tested lags.",
    }


def run_extensions(
    raw: pd.DataFrame,
    two: pd.DataFrame,
    sparse: pd.DataFrame,
    *,
    out_dir: Path | str = "data/research/legacy_extensions",
) -> dict[str, object]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rec_loto = number_recency_calendar(two, mode="loto")
    rec_de = number_recency_calendar(two, mode="de")
    pair = pair_recency_calendar(two)
    weekday = de_weekday_profile(two)
    transition = transition_independence_by_number(sparse)
    acf = loto_acf_bartlett(sparse)
    coverage = coverage_coupon_summary(sparse)
    ks = ks_special_uniformity(raw)
    ljung = ljung_box_even_tail_count(two)

    tables = {
        "number_recency_loto.csv": rec_loto,
        "number_recency_de.csv": rec_de,
        "pair_recency_loto.csv": pair,
        "de_weekday_profile.csv": weekday,
        "loto_transition_independence.csv": transition,
        "loto_acf_bartlett.csv": acf,
    }
    for name, table in tables.items():
        table.to_csv(out / name, index=False)

    randomness = {"ks_full_special": ks, "ljung_box_even_tail_count": ljung}
    (out / "randomness_extensions.json").write_text(
        json.dumps(randomness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "coverage_coupon.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "anchor_date": pd.to_datetime(two["date"]).max().date().isoformat(),
        "research_only": True,
        "rows": {name: int(len(table)) for name, table in tables.items()},
        "transition_fdr_05_count": int(transition["fdr_05"].sum()) if not transition.empty else 0,
        "acf_fdr_05_count": int(acf["fdr_05"].sum()) if not acf.empty else 0,
        "acf_bartlett_exceed_count": int(acf["exceeds_bartlett"].sum()) if not acf.empty else 0,
        "ks_full_special": ks,
        "ljung_box_even_tail_count": ljung,
        "coverage": coverage,
        "note": (
            "Recovered legacy descriptive/falsification capabilities. These artifacts do not "
            "alter production ML, path, statistical or ensemble weights."
        ),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate research-only legacy capability extensions.")
    ap.add_argument("--out-dir", default="data/research/legacy_extensions")
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    sparse = lot.get_sparse_data().sort_values("date").reset_index(drop=True)
    if raw.empty or two.empty or sparse.empty:
        raise SystemExit("No data loaded")

    manifest = run_extensions(raw, two, sparse, out_dir=args.out_dir)
    print(
        "[OK] legacy research extensions ->",
        args.out_dir,
        "anchor=",
        manifest.get("anchor_date"),
    )


if __name__ == "__main__":
    main()
