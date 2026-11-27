from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd

from core.calendar_alignment import calendar_lag_pairs
from ensemble.hierarchical_pooling import (
    MAX_PRIOR_STRENGTH,
    dersimonian_laird_tau2,
    fit_shrinkage_to_prior,
)
from core.path_models import (
    PathParams,
    build_daily_targets,
    enumerate_position_pairs,
    get_scope_indices,
)
from core.xsmb_domain import TOTAL_DIGITS, baseline_rate, raw_digit_matrix

Mode = Literal["loto", "de"]
FilterKind = Literal["stable", "active"]

STREAK_BUCKETS = 9


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
    p_post: float = float("nan")
    streak_shift: float = 0.0


@dataclass(frozen=True)
class BridgeEvidence:

    mode: str
    scope: str
    lag_max: int
    rules: int
    trials: int
    base_rate: float
    variance_ratio: float
    rule_prior_strength: float
    rule_shrinkage: float
    streak_hits: tuple[int, ...]
    streak_trials: tuple[int, ...]
    streak_between_variance: float
    streak_posterior: tuple[float, ...]

    @property
    def rules_fully_pooled(self) -> bool:
        return self.rule_prior_strength >= MAX_PRIOR_STRENGTH

    @property
    def streaks_fully_pooled(self) -> bool:
        return self.streak_between_variance <= 0.0

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "scope": self.scope,
            "lag_max": self.lag_max,
            "rules": self.rules,
            "trials": self.trials,
            "base_rate": self.base_rate,
            "variance_ratio": self.variance_ratio,
            "rule_prior_strength": self.rule_prior_strength,
            "rule_shrinkage": self.rule_shrinkage,
            "rules_fully_pooled": self.rules_fully_pooled,
            "streak_buckets": STREAK_BUCKETS,
            "streak_hits": list(self.streak_hits),
            "streak_trials": list(self.streak_trials),
            "streak_between_variance": self.streak_between_variance,
            "streaks_fully_pooled": self.streaks_fully_pooled,
            "streak_posterior": list(self.streak_posterior),
        }


def _resolve_anchor_index(dates: list[date], anchor_date: date | None) -> int:
    if anchor_date is None:
        return len(dates) - 1
    try:
        return dates.index(anchor_date)
    except ValueError as exc:
        raise ValueError(f"anchor_date {anchor_date} not found in dataset") from exc


def _streak_walk(
    hit_matrix: np.ndarray, *, buckets: int, rule_hits: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n_rows = hit_matrix.shape[0] if hit_matrix.ndim == 2 else 0
    n_rules = hit_matrix.shape[1] if hit_matrix.ndim == 2 else 0
    row_hits = np.zeros((n_rows, max(buckets, 0)), dtype=np.int64)
    row_trials = np.zeros((n_rows, max(buckets, 0)), dtype=np.int64)
    row_rate = np.zeros((n_rows, max(buckets, 0)), dtype=np.float64)
    if hit_matrix.size == 0:
        z = np.zeros(n_rules, dtype=np.int16)
        return z, z.copy(), row_hits, row_trials, row_rate

    cur = np.zeros(n_rules, dtype=np.int16)
    max_streak = np.zeros(n_rules, dtype=np.int16)
    cap = buckets - 1
    n_trials = float(n_rows)
    for t, row in enumerate(hit_matrix):
        if buckets > 0:
            group = np.minimum(cur, cap)
            row_trials[t] = np.bincount(group, minlength=buckets)
            row_hits[t] = np.bincount(group, weights=row, minlength=buckets)
            if rule_hits is not None:
                own = (rule_hits - cur - row) / np.maximum(n_trials - cur - 1.0, 1.0)
                row_rate[t] = np.bincount(group, weights=own, minlength=buckets)
        cur += 1
        cur *= row
        np.maximum(max_streak, cur, out=max_streak)
    return max_streak, cur, row_hits, row_trials, row_rate


def _select_rule_indices(
    *,
    p_mean: np.ndarray,
    hits: np.ndarray,
    max_streak: np.ndarray,
    current_streak: np.ndarray,
    params: PathParams,
    mode: Mode,
) -> np.ndarray:
    eligible = (current_streak >= params.min_current_streak) | (max_streak >= params.min_max_streak)
    idx = np.flatnonzero(eligible)
    if idx.size == 0:
        idx = np.arange(len(p_mean), dtype=np.int32)

    cap = int(params.top_rules_per_lag)
    if cap <= 0 or idx.size <= cap:
        return idx

    baseline = baseline_rate(mode)
    lift = np.log(np.clip(p_mean[idx] / max(baseline, 1e-9), 1e-6, 1e6))
    hits_vs_best = hits[idx] / np.maximum(1.0, hits[idx].max(initial=1))
    score = (
        lift
        + 0.10 * np.minimum(current_streak[idx], 10)
        + 0.025 * np.minimum(max_streak[idx], 20)
        + 0.08 * np.sqrt(np.clip(hits_vs_best, 0.0, 1.0))
    )
    order = np.argsort(-score, kind="stable")[:cap]
    return idx[order]


@dataclass
class PreparedPathHistory:

    dates: list[date]
    date_index: pd.DatetimeIndex
    raw_matrix: np.ndarray
    target_loto: np.ndarray
    target_de: np.ndarray
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
    df_raw = df_raw.sort_values("date", kind="stable").reset_index(drop=True)
    df_2digits = df_2digits.sort_values("date", kind="stable").reset_index(drop=True)
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
    anchor_date: date | None = None,
    scope: str = "all",
    prepared: PreparedPathHistory | None = None,
) -> tuple[list[PathStats], dict[date, np.ndarray], list[date]]:
    stats, raw_by_date, dates, _ = fit_paths_with_evidence(
        df_raw=df_raw,
        df_2digits=df_2digits,
        params=params,
        mode=mode,
        anchor_date=anchor_date,
        scope=scope,
        prepared=prepared,
    )
    return stats, raw_by_date, dates


def fit_paths_with_evidence(
    *,
    df_raw: pd.DataFrame | None = None,
    df_2digits: pd.DataFrame | None = None,
    params: PathParams,
    mode: Mode,
    anchor_date: date | None = None,
    scope: str = "all",
    prepared: PreparedPathHistory | None = None,
) -> tuple[list[PathStats], dict[date, np.ndarray], list[date], BridgeEvidence | None]:
    if prepared is None:
        if df_raw is None or df_2digits is None:
            raise ValueError("provide either prepared=... or df_raw and df_2digits")
        prepared = prepare_path_history(df_raw, df_2digits)

    dates = prepared.dates
    if not dates:
        return [], {}, [], None

    raw_matrix = prepared.raw_matrix
    raw_digits = list(raw_matrix)
    p_count = raw_matrix.shape[1]

    allowed = np.zeros(p_count, dtype=bool)
    allowed[np.asarray(get_scope_indices(scope), dtype=int)] = True
    i_all, j_all = enumerate_position_pairs(p_count)
    pair_mask = allowed[i_all] & allowed[j_all]
    i_idx = i_all[pair_mask]
    j_idx = j_all[pair_mask]

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

    fitted_lags: list[tuple] = []
    day_hits = np.zeros((idx_end - idx_start + 1, STREAK_BUCKETS), dtype=np.int64)
    day_trials = np.zeros_like(day_hits)
    day_expected = np.zeros(day_hits.shape, dtype=np.float64)
    for lag in range(1, params.lag_max + 1):
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
            offsets = (target_idx.astype(np.int32)[:, None] * 100) + nums
            hit_matrix = target_loto.reshape(-1)[offsets]
        else:
            hit_matrix = nums == target_de[target_idx, None]

        trials = int(hit_matrix.shape[0])
        hits = hit_matrix.sum(axis=0, dtype=np.int32)
        max_streak, current_streak, row_hits, row_trials, row_expected = _streak_walk(
            hit_matrix, buckets=STREAK_BUCKETS, rule_hits=hits
        )
        day_hits[target_idx - idx_start] += row_hits
        day_trials[target_idx - idx_start] += row_trials
        day_expected[target_idx - idx_start] += row_expected
        p_mean = (hits + params.alpha) / (trials + params.alpha + params.beta)

        selected = _select_rule_indices(
            p_mean=p_mean,
            hits=hits,
            max_streak=max_streak,
            current_streak=current_streak,
            params=params,
            mode=mode,
        )
        fitted_lags.append((lag, trials, hits, p_mean, max_streak, current_streak, selected))

    evidence = _bridge_evidence(
        fitted_lags, day_hits, day_trials, day_expected, mode=mode, scope=scope
    )
    stats: list[PathStats] = []
    for lag, trials, hits, p_mean, max_streak, current_streak, selected in fitted_lags:
        center = evidence.base_rate
        keep = trials / (trials + evidence.rule_prior_strength)
        for k in selected:
            group = min(int(current_streak[k]), STREAK_BUCKETS - 1)
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
                    p_post=center + keep * (float(hits[k]) / trials - center),
                    streak_shift=evidence.streak_posterior[group] - evidence.base_rate,
                )
            )

    raw_by_date = {dates[i]: raw_digits[i] for i in range(anchor_idx + 1)}
    return stats, raw_by_date, dates[: anchor_idx + 1], evidence


def streak_experience(
    day_hits: np.ndarray, day_trials: np.ndarray, expected: np.ndarray | None = None
) -> tuple[np.ndarray, float, float]:
    day_hits = np.asarray(day_hits, dtype=float)
    day_trials = np.asarray(day_trials, dtype=float)
    hits = day_hits.sum(axis=0)
    trials = day_trials.sum(axis=0)
    used = trials > 0
    if not used.any():
        raise ValueError("không có lượt chấm nào để học kinh nghiệm chuỗi")
    base = float(hits[used].sum() / trials[used].sum())
    if expected is None:
        expected = day_trials * base
    expected = np.asarray(expected, dtype=float)
    if expected.shape != day_hits.shape:
        raise ValueError("expected phải cùng hình với day_hits")
    safe_n = np.where(used, trials, 1.0)
    excess = np.where(used, (hits - expected.sum(axis=0)) / safe_n, 0.0)
    resid = (day_hits - expected) - day_trials * excess[None, :]
    clusters = (day_trials > 0).sum(axis=0)
    factor = np.divide(clusters, clusters - 1, out=np.ones_like(trials), where=clusters > 1)
    cluster_var = factor * (resid**2).sum(axis=0) / safe_n**2
    variances = np.maximum(cluster_var, base * (1.0 - base) / safe_n)
    reliable = used & (clusters >= 2)
    tau2 = dersimonian_laird_tau2(base + excess[reliable], variances[reliable])
    post = np.full(hits.size, base)
    post[reliable] = base + tau2 / (tau2 + variances[reliable]) * excess[reliable]
    return post, base, tau2


def _bridge_evidence(
    fitted_lags: list[tuple],
    day_hits: np.ndarray,
    day_trials: np.ndarray,
    day_expected: np.ndarray,
    *,
    mode: str,
    scope: str,
) -> BridgeEvidence | None:
    if not fitted_lags:
        return None
    succ = np.concatenate([f[2] for f in fitted_lags]).astype(float)
    n = np.concatenate([np.full(f[2].size, f[1], dtype=float) for f in fitted_lags])
    base = float(succ.sum() / n.sum())
    kappa = fit_shrinkage_to_prior(succ, n, base)
    harmonic_n = float(n.size / np.sum(1.0 / n))
    rates = succ / n
    binomial = float(np.mean(base * (1.0 - base) / n))
    observed = float(np.mean((rates - base) ** 2))

    exp_hits = day_hits.sum(axis=0)
    exp_trials = day_trials.sum(axis=0)
    streak_post, _, streak_tau2 = streak_experience(day_hits, day_trials, day_expected)
    return BridgeEvidence(
        mode=mode,
        scope=scope,
        lag_max=int(max(f[0] for f in fitted_lags)),
        rules=int(succ.size),
        trials=int(round(float(np.mean(n)))),
        base_rate=base,
        variance_ratio=observed / binomial if binomial > 0 else float("nan"),
        rule_prior_strength=float(kappa),
        rule_shrinkage=float(kappa / (kappa + harmonic_n)),
        streak_hits=tuple(int(v) for v in exp_hits),
        streak_trials=tuple(int(v) for v in exp_trials),
        streak_between_variance=float(streak_tau2),
        streak_posterior=tuple(float(v) for v in streak_post),
    )


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
                "p_post": s.p_post,
                "streak_shift": s.streak_shift,
            }
            for s in stats
        ]
    )


def _empty_prediction(mode: Mode = "loto") -> pd.DataFrame:
    base = baseline_rate(mode)
    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=np.int32),
            "prob": np.full(100, base, dtype=np.float64),
            "support_paths_count": np.zeros(100, dtype=np.int32),
            "evidence_weight": np.zeros(100, dtype=np.float64),
        }
    )


def rule_next_probability(
    paths: pd.DataFrame,
    *,
    kind: FilterKind,
    scope: str = "all",
    bias_special_touch: float = 1.0,
    bias_special_both: float = 1.0,
) -> np.ndarray:
    p = paths["p_post"].astype(float).to_numpy()
    if np.isnan(p).any():
        raise ValueError("đường cầu thiếu p_post: dựng lại bằng fit_paths")
    if kind == "active":
        p = p + paths["streak_shift"].astype(float).to_numpy()
    if scope in {"near_special", "special_only"}:
        touched = paths["special_touch"].astype(bool).to_numpy()
        both = paths["special_both"].astype(bool).to_numpy()
        p = np.where(both, p * float(bias_special_both), np.where(touched, p * float(bias_special_touch), p))
    return np.clip(p, 1e-6, 1 - 1e-6)


def predict_from_fitted_paths_full(
    *,
    stats: list[PathStats],
    raw_by_date: dict[date, np.ndarray],
    dates: list[date],
    params: PathParams,
    kind: FilterKind,
    mode: Mode = "loto",
    anchor_date: date | None = None,
    scope: str = "all",
    bias_special_touch: float = 1.0,
    bias_special_both: float = 1.0,
) -> pd.DataFrame:
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
            continue
        rows = lags == lag
        digits = np.asarray(digits)
        next_numbers[rows] = (
            10 * digits[i_arr[rows]].astype(np.int16) + digits[j_arr[rows]].astype(np.int16)
        )
    paths["next_number"] = next_numbers
    paths = paths[(paths["next_number"] >= 0) & (paths["next_number"] < 100)].copy()
    if paths.empty:
        return _empty_prediction(mode)

    p = rule_next_probability(
        paths,
        kind=kind,
        scope=scope,
        bias_special_touch=bias_special_touch,
        bias_special_both=bias_special_both,
    )

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
    prob = np.divide(weighted_p, weight_sum, out=np.full(100, baseline), where=weight_sum > 0)
    prob = np.where(support > 0, prob, baseline)
    if mode == "de":
        prob = prob / max(float(prob.sum()), 1e-12)

    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=np.int32),
            "prob": prob,
            "support_paths_count": support,
            "evidence_weight": weight_sum,
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
    anchor_date: date | None = None,
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
        ["prob", "evidence_weight", "support_paths_count"], ascending=[False, False, False], kind="stable"
    )
    return out.head(top_numbers).reset_index(drop=True)


def predict_next_day(
    *,
    df_raw: pd.DataFrame,
    df_2digits: pd.DataFrame,
    params: PathParams,
    mode: Mode,
    kind: FilterKind,
    top_numbers: int = 20,
    anchor_date: date | None = None,
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
