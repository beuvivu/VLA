from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Optional

import numpy as np
import pandas as pd

from calendar_alignment import calendar_lag_pairs
from path_models import (
    PathParams,
    build_daily_targets,
    enumerate_position_pairs,
    get_scope_indices,
)
from xsmb_domain import TOTAL_DIGITS, baseline_rate, raw_digit_matrix

Mode = Literal["loto", "de"]
FilterKind = Literal["stable", "active"]


@dataclass
class PathStats:
    lag: int
    i: int
    j: int
    trials: int
    hits: int
    p_mean: float
    max_streak: int
    current_streak: int
    special_touch: int
    special_both: int


def _resolve_anchor_index(dates: list[date], anchor_date: Optional[date]) -> int:
    if anchor_date is None:
        return len(dates) - 1
    try:
        return dates.index(anchor_date)
    except ValueError as exc:
        raise ValueError(f"anchor_date {anchor_date} not found in dataset") from exc


def _streak_stats(hit_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Max/current streaks for shape (trials, rules).

    The recurrence is inherently sequential, but it does not need to allocate.
    ``np.where(row, cur + 1, 0).astype(...)`` built three temporary arrays of
    ``n_rules`` elements on every one of the ``trials`` iterations.  Doing the
    same arithmetic in place is ~7x faster and bit-identical.
    """
    if hit_matrix.size == 0:
        n_rules = hit_matrix.shape[1] if hit_matrix.ndim == 2 else 0
        z = np.zeros(n_rules, dtype=np.int16)
        return z, z.copy()

    n_rules = hit_matrix.shape[1]
    cur = np.zeros(n_rules, dtype=np.int16)
    max_streak = np.zeros(n_rules, dtype=np.int16)
    for row in hit_matrix:
        cur += 1
        cur *= row  # bool -> 0/1: resets every rule that missed
        np.maximum(max_streak, cur, out=max_streak)
    return max_streak, cur


def _select_rule_indices(
    *,
    p_mean: np.ndarray,
    hits: np.ndarray,
    max_streak: np.ndarray,
    current_streak: np.ndarray,
    params: PathParams,
    mode: Mode,
) -> np.ndarray:
    """Keep only statistically relevant path rules for a lag.

    The legacy implementation retained every position pair for every lag, even
    though only active/stable rules are used downstream.  Keeping a bounded set
    prevents quadratic repository/runtime growth while preserving the strongest
    rules under both current-streak and historical-streak criteria.
    """
    eligible = (current_streak >= params.min_current_streak) | (max_streak >= params.min_max_streak)
    idx = np.flatnonzero(eligible)
    if idx.size == 0:
        idx = np.arange(len(p_mean), dtype=np.int32)

    cap = int(params.top_rules_per_lag)
    if cap <= 0 or idx.size <= cap:
        return idx

    baseline = baseline_rate(mode)
    lift = np.log(np.clip(p_mean[idx] / max(baseline, 1e-9), 1e-6, 1e6))
    # NOTE: despite the name this is hits normalised by the best rule's hits,
    # not a rate.  Kept as-is to preserve the existing ranking; renamed so the
    # next reader is not misled into treating it as a probability.
    hits_vs_best = hits[idx] / np.maximum(1.0, hits[idx].max(initial=1))
    score = (
        lift
        + 0.10 * np.minimum(current_streak[idx], 10)
        + 0.025 * np.minimum(max_streak[idx], 20)
        + 0.08 * np.sqrt(np.clip(hits_vs_best, 0.0, 1.0))
    )
    keep_local = np.argpartition(score, -cap)[-cap:]
    return idx[keep_local[np.argsort(score[keep_local])[::-1]]]


def selection_shrinkage_strength(n_screened: int, n_kept: int, base: float = 6.0) -> float:
    """Extra prior weight needed because ``p_mean`` was *selected*, not observed.

    ``_select_rule_indices`` keeps the top ``n_kept`` of ``n_screened`` rules
    using a score that is monotone in the in-sample hit rate.  The surviving
    ``p_mean`` values are therefore order statistics from the upper tail, not
    unbiased estimates: the winner's curse inflates them by roughly the tail
    quantile of the sampling noise.  With ~5,600 rules screened per lag and 300
    kept, that is a real bias, and the previous fixed ``prior_strength = 6.0``
    (about 5% of a rule's own ``min_trials = 60`` evidence) does not touch it.

    We scale the prior by ``sqrt(2 * ln(screened / kept))`` — the standard
    Gaussian-maximum growth rate — so heavier screening shrinks harder toward
    the baseline.  No screening (``kept >= screened``) leaves ``base``
    unchanged, preserving current behaviour where selection did not occur.
    """
    screened = max(int(n_screened), 1)
    kept = max(int(n_kept), 1)
    if kept >= screened:
        return float(base)
    return float(base) * float(np.sqrt(1.0 + 2.0 * np.log(screened / kept)))


@dataclass
class PreparedPathHistory:
    """Scope-independent tensors derived once from a full history.

    ``fit_paths`` rebuilt all of this on every call: the digit matrix, the
    per-day target sets, and the ``days x pairs`` number table.  None of it
    depends on the anchor date, so a walk-forward backtest that calls
    ``fit_paths`` once per day was paying for the same work hundreds of times.
    ``prepare_path_history`` computes it once; ``fit_paths(prepared=...)``
    reuses it and slices to the anchor.

    Slicing (not rebuilding) is leakage-safe because every consumer is bounded
    by ``anchor_idx``: target rows are filtered to ``<= anchor_idx`` and each
    rule's base row is strictly earlier still.  ``raw_by_date`` is truncated at
    the anchor so no caller can reach a future draw.
    """

    dates: list[date]
    date_index: pd.DatetimeIndex
    raw_matrix: np.ndarray
    target_loto: np.ndarray
    target_de: np.ndarray
    # lag -> (source_idx, target_idx); filled lazily and shared across anchors.
    lag_pairs: dict[int, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)

    def pairs_for_lag(self, lag: int) -> tuple[np.ndarray, np.ndarray]:
        key = int(lag)
        cached = self.lag_pairs.get(key)
        if cached is None:
            cached = calendar_lag_pairs(self.date_index, key)
            self.lag_pairs[key] = cached
        return cached


def prepare_path_history(
    df_raw: pd.DataFrame, df_2digits: pd.DataFrame
) -> PreparedPathHistory:
    df_raw = df_raw.sort_values("date").reset_index(drop=True)
    df_2digits = df_2digits.sort_values("date").reset_index(drop=True)
    dates, targets_loto, targets_de = build_daily_targets(df_2digits)
    if not dates:
        return PreparedPathHistory(
            dates=[],
            date_index=pd.DatetimeIndex([]),
            raw_matrix=np.zeros((0, TOTAL_DIGITS), dtype=np.uint8),
            target_loto=np.zeros((0, 100), dtype=bool),
            target_de=np.zeros(0, dtype=np.uint8),
        )
    target_loto = np.zeros((len(dates), 100), dtype=bool)
    for t, hitset in enumerate(targets_loto):
        if hitset:
            target_loto[t, np.fromiter(hitset, dtype=np.int16, count=len(hitset))] = True
    return PreparedPathHistory(
        dates=dates,
        date_index=pd.DatetimeIndex(pd.to_datetime(pd.Series(dates))),
        raw_matrix=raw_digit_matrix(df_raw),
        target_loto=target_loto,
        target_de=np.asarray(targets_de, dtype=np.uint8),
    )


def fit_paths(
    *,
    df_raw: pd.DataFrame | None = None,
    df_2digits: pd.DataFrame | None = None,
    params: PathParams,
    mode: Mode,
    anchor_date: Optional[date] = None,
    scope: str = "all",
    prepared: PreparedPathHistory | None = None,
) -> tuple[list[PathStats], dict[date, np.ndarray], list[date]]:
    """Fit path rules using history up to ``anchor_date`` (inclusive).

    The implementation precomputes every position-pair number once per draw,
    then evaluates each lag with vectorized target lookups.  This is materially
    faster than recomputing all pair numbers inside the day×lag loop.

    Pass ``prepared`` (from ``prepare_path_history``) to reuse the invariant
    tensors across many anchor dates — this is what makes a walk-forward
    backtest affordable.
    """
    if prepared is None:
        if df_raw is None or df_2digits is None:
            raise ValueError("provide either prepared=... or df_raw and df_2digits")
        prepared = prepare_path_history(df_raw, df_2digits)

    dates = prepared.dates
    if not dates:
        return [], {}, []

    raw_matrix = prepared.raw_matrix
    raw_digits = list(raw_matrix)
    p_count = raw_matrix.shape[1]

    allowed = np.zeros(p_count, dtype=bool)
    allowed[np.asarray(get_scope_indices(scope), dtype=int)] = True
    i_all, j_all = enumerate_position_pairs(p_count)
    pair_mask = allowed[i_all] & allowed[j_all]
    i_idx = i_all[pair_mask]
    j_idx = j_all[pair_mask]

    # days × rules, each entry is the 00..99 number generated by the two positions.
    pair_nums = (10 * raw_matrix[:, i_idx] + raw_matrix[:, j_idx]).astype(np.uint8, copy=False)

    target_loto = prepared.target_loto
    target_de = prepared.target_de

    special_mask = np.zeros(p_count, dtype=bool)
    special_mask[np.asarray(get_scope_indices("special_only"), dtype=int)] = True
    special_touch = (special_mask[i_idx] | special_mask[j_idx]).astype(np.int8)
    special_both = (special_mask[i_idx] & special_mask[j_idx]).astype(np.int8)

    anchor_idx = _resolve_anchor_index(dates, anchor_date)
    idx_end = anchor_idx
    idx_start = max(0, anchor_idx - params.window_days + 1)

    stats: list[PathStats] = []
    for lag in range(1, params.lag_max + 1):
        # CRITICAL: ``lag`` must mean the same thing here as it does at
        # prediction time.  ``predict_from_fitted_paths_full`` resolves a rule's
        # base draw with ``next_date - timedelta(days=lag)`` — a *calendar* lag —
        # while this loop previously used ``target_idx - lag``, a *row* lag.
        # The two agree only while the history has no missing dates.  Because
        # ``Lottery.fetch`` deliberately refuses to write a draw when sources
        # disagree, gaps are an expected state, and every gap silently shifted
        # training rules off the draws they are scored against at serve time.
        # ``calendar_lag_pairs`` makes both sides calendar-exact.
        source_all, target_all = prepared.pairs_for_lag(lag)
        if source_all.size == 0:
            continue
        in_window = (target_all >= idx_start) & (target_all <= idx_end)
        target_idx = target_all[in_window]
        base_idx = source_all[in_window]
        if target_idx.size == 0:
            continue
        nums = pair_nums[base_idx]

        if mode == "loto":
            # ``take_along_axis`` needs an intp index array, i.e. a 64-bit copy
            # of the whole (days x rules) table on every lag.  Flat int32
            # offsets into the raveled target matrix give the same booleans for
            # half the memory traffic (~2x faster).
            offsets = (target_idx.astype(np.int32)[:, None] * 100) + nums
            hit_matrix = target_loto.reshape(-1)[offsets]
        else:
            hit_matrix = nums == target_de[target_idx, None]

        trials = int(hit_matrix.shape[0])
        hits = hit_matrix.sum(axis=0, dtype=np.int32)
        max_streak, current_streak = _streak_stats(hit_matrix)
        p_mean = (hits + params.alpha) / (trials + params.alpha + params.beta)

        selected = _select_rule_indices(
            p_mean=p_mean,
            hits=hits,
            max_streak=max_streak,
            current_streak=current_streak,
            params=params,
            mode=mode,
        )
        for k in selected:
            stats.append(
                PathStats(
                    lag=lag,
                    i=int(i_idx[k]),
                    j=int(j_idx[k]),
                    trials=trials,
                    hits=int(hits[k]),
                    p_mean=float(p_mean[k]),
                    max_streak=int(max_streak[k]),
                    current_streak=int(current_streak[k]),
                    special_touch=int(special_touch[k]),
                    special_both=int(special_both[k]),
                )
            )

    # Truncated at the anchor: with a shared PreparedPathHistory the arrays
    # span the whole dataset, and the prediction step looks rules up by date.
    raw_by_date = {dates[i]: raw_digits[i] for i in range(anchor_idx + 1)}
    return stats, raw_by_date, dates[: anchor_idx + 1]


def _filter_paths(stats: list[PathStats], params: PathParams, kind: FilterKind) -> list[PathStats]:
    stats = [s for s in stats if s.trials >= params.min_trials]
    if kind == "active":
        return [s for s in stats if s.current_streak >= params.min_current_streak]
    return [s for s in stats if s.max_streak >= params.min_max_streak]


def paths_to_dataframe(stats: list[PathStats]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "lag": s.lag,
                "i": s.i,
                "j": s.j,
                "trials": s.trials,
                "hits": s.hits,
                "p_mean": s.p_mean,
                "max_streak": s.max_streak,
                "current_streak": s.current_streak,
                "special_touch": s.special_touch,
                "special_both": s.special_both,
            }
            for s in stats
        ]
    )


def _empty_prediction(mode: Mode = "loto") -> pd.DataFrame:
    """No eligible rule: fall back to the mode's no-information baseline.

    This used to return an all-zero vector.  For ``mode="de"`` that is not a
    probability distribution at all, and the case is not hypothetical: the
    default ``min_current_streak=3`` is structurally unreachable for ĐB (a rule
    would need three consecutive exact 1-in-100 hits), so ``kind="active"`` +
    ``mode="de"`` returned zeros on every single run.  ``prob_eval`` consumed
    that vector directly and scored a log-loss of ~27.6 per day against it.
    Returning the baseline keeps the contract "this is always a usable
    probability vector"; callers that need to know evidence was absent should
    read ``support_paths_count``, which stays 0.
    """
    base = baseline_rate(mode)
    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=np.int32),
            "prob": np.full(100, base, dtype=np.float64),
            "support_paths_count": np.zeros(100, dtype=np.int32),
            "evidence_weight": np.zeros(100, dtype=np.float64),
            "prior_strength": np.zeros(100, dtype=np.float64),
        }
    )


def predict_from_fitted_paths_full(
    *,
    stats: list[PathStats],
    raw_by_date: dict[date, np.ndarray],
    dates: list[date],
    params: PathParams,
    kind: FilterKind,
    mode: Mode = "loto",
    anchor_date: Optional[date] = None,
    scope: str = "all",
    bias_special_touch: float = 1.0,
    bias_special_both: float = 1.0,
) -> pd.DataFrame:
    """Return calibrated-style path evidence for all 00..99 values.

    Path rules are highly correlated because many share digits, lags and source
    draws.  Multiplying their complements (legacy noisy-OR) incorrectly treats
    them as independent and quickly drives probabilities to 1.0.  We instead use
    a reliability-weighted mean and Bayesian shrinkage toward the mode baseline.
    This keeps path output numerically stable and better suited for ensembles.
    """
    if not dates:
        return _empty_prediction(mode)
    if anchor_date is None:
        anchor_date = dates[-1]

    df_stats = paths_to_dataframe(stats)
    if df_stats.empty:
        return _empty_prediction(mode)

    eligible = pd.to_numeric(df_stats["trials"], errors="coerce").fillna(0).astype(int) >= params.min_trials
    if kind == "active":
        eligible &= pd.to_numeric(df_stats["current_streak"], errors="coerce").fillna(0).astype(int) >= params.min_current_streak
    else:
        eligible &= pd.to_numeric(df_stats["max_streak"], errors="coerce").fillna(0).astype(int) >= params.min_max_streak
    paths = df_stats.loc[eligible].copy()
    if paths.empty:
        return _empty_prediction(mode)

    # Resolve every rule's firing number with array lookups instead of one
    # ``iterrows`` step per rule (thousands of rules per call, and this runs
    # once per backtest day).
    next_date = anchor_date + timedelta(days=1)
    lags = paths["lag"].astype(int).to_numpy()
    i_arr = paths["i"].astype(int).to_numpy()
    j_arr = paths["j"].astype(int).to_numpy()

    unique_lags = np.unique(lags)
    digits_by_lag: dict[int, np.ndarray | None] = {
        int(lag): raw_by_date.get(next_date - timedelta(days=int(lag)))
        for lag in unique_lags
    }
    next_numbers = np.full(len(paths), -1, dtype=np.int16)
    for lag, digits in digits_by_lag.items():
        if digits is None:
            continue  # base draw missing from history: rule cannot fire today
        rows = lags == lag
        digits = np.asarray(digits)
        next_numbers[rows] = (
            10 * digits[i_arr[rows]].astype(np.int16) + digits[j_arr[rows]].astype(np.int16)
        )
    paths["next_number"] = next_numbers
    paths = paths[(paths["next_number"] >= 0) & (paths["next_number"] < 100)].copy()
    if paths.empty:
        return _empty_prediction(mode)

    p = paths["p_mean"].astype(float).to_numpy()
    if scope in {"near_special", "special_only"}:
        touched = paths["special_touch"].astype(bool).to_numpy()
        both = paths["special_both"].astype(bool).to_numpy()
        p = np.where(both, p * float(bias_special_both), np.where(touched, p * float(bias_special_touch), p))
    p = np.clip(p, 1e-6, 1 - 1e-6)

    trials = paths["trials"].astype(float).to_numpy()
    reliability = trials / (trials + 120.0)
    if kind == "active":
        streak = np.minimum(paths["current_streak"].astype(float).to_numpy(), 8.0)
        streak_weight = 1.0 + 0.05 * streak
    else:
        streak = np.minimum(paths["max_streak"].astype(float).to_numpy(), 15.0)
        streak_weight = 1.0 + 0.02 * streak
    weights = reliability * streak_weight

    nums = paths["next_number"].astype(int).to_numpy()
    support = np.bincount(nums, minlength=100).astype(np.int32)
    weight_sum = np.bincount(nums, weights=weights, minlength=100).astype(np.float64)
    weighted_p = np.bincount(nums, weights=weights * p, minlength=100).astype(np.float64)

    baseline = baseline_rate(mode)
    # Selection-aware shrinkage: ``p_mean`` reaching this point survived a
    # top-``top_rules_per_lag``-of-all-pairs screen inside ``fit_paths``, so it
    # carries winner's-curse bias.  See ``selection_shrinkage_strength``.
    n_pairs_screened = len(enumerate_position_pairs(TOTAL_DIGITS)[0])
    prior_strength = selection_shrinkage_strength(
        n_screened=n_pairs_screened, n_kept=int(params.top_rules_per_lag)
    )
    prob = (weighted_p + prior_strength * baseline) / (weight_sum + prior_strength)
    prob = np.where(support > 0, prob, baseline)
    if mode == "de":
        prob = prob / max(float(prob.sum()), 1e-12)

    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=np.int32),
            "prob": prob,
            "support_paths_count": support,
            "evidence_weight": weight_sum,
            # Effective sample size behind each number's estimate, so downstream
            # tables can show that a 25.1% and a 24.6% are not distinguishable.
            "prior_strength": prior_strength,
        }
    )


def predict_from_fitted_paths(
    *,
    stats: list[PathStats],
    raw_by_date: dict[date, np.ndarray],
    dates: list[date],
    params: PathParams,
    kind: FilterKind,
    mode: Mode = "loto",
    top_numbers: int = 20,
    anchor_date: Optional[date] = None,
    scope: str = "all",
    bias_special_touch: float = 1.0,
    bias_special_both: float = 1.0,
) -> pd.DataFrame:
    out = predict_from_fitted_paths_full(
        stats=stats,
        raw_by_date=raw_by_date,
        dates=dates,
        params=params,
        kind=kind,
        mode=mode,
        anchor_date=anchor_date,
        scope=scope,
        bias_special_touch=bias_special_touch,
        bias_special_both=bias_special_both,
    )
    out = out[out["support_paths_count"] > 0].sort_values(
        ["prob", "evidence_weight", "support_paths_count"], ascending=[False, False, False]
    )
    return out.head(top_numbers).reset_index(drop=True)


def predict_next_day_full(
    *,
    df_raw: pd.DataFrame,
    df_2digits: pd.DataFrame,
    params: PathParams,
    mode: Mode,
    kind: FilterKind,
    top_numbers: int = 20,
    anchor_date: Optional[date] = None,
    scope: str = "all",
    bias_special_touch: float = 1.0,
    bias_special_both: float = 1.0,
) -> pd.DataFrame:
    stats, raw_by_date, dates = fit_paths(
        df_raw=df_raw, df_2digits=df_2digits, params=params, mode=mode, anchor_date=anchor_date, scope=scope
    )
    return predict_from_fitted_paths_full(
        stats=stats,
        raw_by_date=raw_by_date,
        dates=dates,
        params=params,
        kind=kind,
        mode=mode,
        anchor_date=anchor_date,
        scope=scope,
        bias_special_touch=bias_special_touch,
        bias_special_both=bias_special_both,
    )


def predict_next_day(
    *,
    df_raw: pd.DataFrame,
    df_2digits: pd.DataFrame,
    params: PathParams,
    mode: Mode,
    kind: FilterKind,
    top_numbers: int = 20,
    anchor_date: Optional[date] = None,
    scope: str = "all",
    bias_special_touch: float = 1.0,
    bias_special_both: float = 1.0,
) -> pd.DataFrame:
    stats, raw_by_date, dates = fit_paths(
        df_raw=df_raw, df_2digits=df_2digits, params=params, mode=mode, anchor_date=anchor_date, scope=scope
    )
    return predict_from_fitted_paths(
        stats=stats,
        raw_by_date=raw_by_date,
        dates=dates,
        params=params,
        kind=kind,
        mode=mode,
        top_numbers=top_numbers,
        anchor_date=anchor_date,
        scope=scope,
        bias_special_touch=bias_special_touch,
        bias_special_both=bias_special_both,
    )
