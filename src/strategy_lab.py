from __future__ import annotations

"""Standardized walk-forward laboratory for deterministic strategy families.

Legacy repositories contained many individually named "cầu" rules. This module
preserves the useful idea -- a common evaluation contract -- while preventing
those rules from silently entering production. Every strategy is compared on
number-level trials against a training-only marginal baseline, with chronological
holdout, FDR correction, agreement curves and diversity diagnostics.

All row offsets are interpreted as calendar days only after the two-digit and
sparse histories pass strict daily-contiguity and date-axis equality checks.
"""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal

import numpy as np
import pandas as pd
from scipy import stats

from calendar_alignment import require_daily_contiguous
from lottery import Lottery
from number_reference import (
    bo,
    bong,
    dan_cham,
    dan_dau,
    dan_duoi,
    dan_tong_mod10,
    kep_bang,
    kep_lech,
    reverse,
    sat_kep,
)
from research_diagnostics import bh_fdr

Mode = Literal["loto", "de"]


@dataclass(frozen=True)
class StrategyContext:
    values: np.ndarray  # (days, 27) two-digit prize endings
    presence: np.ndarray  # (days, 100) bool


PredictFn = Callable[[StrategyContext, int], set[int]]


@dataclass(frozen=True)
class Strategy:
    name: str
    category: str
    predict: PredictFn
    description: str


def _as_int_set(values) -> set[int]:
    return {int(v) for v in values}


def _rev_num(n: int) -> int:
    return int(reverse(n))


def _bong_num(n: int) -> int:
    return int(bong(n))


def _special(ctx: StrategyContext, t: int) -> int:
    return int(ctx.values[t, 0])


def _special_repeat(ctx: StrategyContext, t: int) -> set[int]:
    return {_special(ctx, t)}


def _special_reverse(ctx: StrategyContext, t: int) -> set[int]:
    return {_rev_num(_special(ctx, t))}


def _special_bong(ctx: StrategyContext, t: int) -> set[int]:
    return {_bong_num(_special(ctx, t))}


def _special_bo(ctx: StrategyContext, t: int) -> set[int]:
    return _as_int_set(bo(_special(ctx, t)))


def _db_g1_cross(ctx: StrategyContext, t: int) -> set[int]:
    db = _special(ctx, t)
    g1 = int(ctx.values[t, 1])
    a = (db // 10) * 10 + (g1 % 10)
    return {a, _rev_num(a)}


def _touch_head(ctx: StrategyContext, t: int) -> set[int]:
    return _as_int_set(dan_cham(_special(ctx, t) // 10))


def _touch_tail(ctx: StrategyContext, t: int) -> set[int]:
    return _as_int_set(dan_cham(_special(ctx, t) % 10))


def _same_head(ctx: StrategyContext, t: int) -> set[int]:
    return _as_int_set(dan_dau(_special(ctx, t) // 10))


def _same_tail(ctx: StrategyContext, t: int) -> set[int]:
    return _as_int_set(dan_duoi(_special(ctx, t) % 10))


def _same_sum(ctx: StrategyContext, t: int) -> set[int]:
    db = _special(ctx, t)
    return _as_int_set(dan_tong_mod10((db // 10 + db % 10) % 10))


def _kep_family(ctx: StrategyContext, t: int) -> set[int]:
    del ctx, t
    return _as_int_set(kep_bang()) | _as_int_set(kep_lech())


def _sat_kep(ctx: StrategyContext, t: int) -> set[int]:
    del ctx, t
    return _as_int_set(sat_kep())


def _lo_roi(ctx: StrategyContext, t: int) -> set[int]:
    return set(np.flatnonzero(ctx.presence[t]).astype(int).tolist())


def _lo_reverse(ctx: StrategyContext, t: int) -> set[int]:
    return {_rev_num(int(n)) for n in np.flatnonzero(ctx.presence[t])}


def _hot(window: int, k: int) -> PredictFn:
    def predict(ctx: StrategyContext, t: int) -> set[int]:
        start = max(0, t - window + 1)
        counts = ctx.presence[start : t + 1].sum(axis=0)
        order = np.lexsort((np.arange(100), -counts))
        return set(order[:k].astype(int).tolist())

    return predict


def _cold(window: int, k: int) -> PredictFn:
    def predict(ctx: StrategyContext, t: int) -> set[int]:
        start = max(0, t - window + 1)
        counts = ctx.presence[start : t + 1].sum(axis=0)
        order = np.lexsort((np.arange(100), counts))
        return set(order[:k].astype(int).tolist())

    return predict


def _gan(k: int) -> PredictFn:
    """Top-k longest-absent numbers as of day ``t``.

    The scan-backwards-from-t implementation is O(t) per call and the lab calls
    it once per day, so the strategy alone was O(n^2) — ~12.5M inner steps on a
    5,000-day history.  "Index of the most recent hit at or before t" is a
    running maximum over the whole history, so it is computed once, lazily, and
    then read in O(1) per day.  Identical picks, including the lexsort tie-break.
    """
    cache: dict[int, np.ndarray] = {}

    def last_seen_matrix(ctx: StrategyContext) -> np.ndarray:
        key = id(ctx)
        cached = cache.get(key)
        if cached is None:
            index = np.arange(len(ctx.presence), dtype=np.int64)[:, None]
            cached = np.maximum.accumulate(
                np.where(ctx.presence, index, np.int64(-1)), axis=0
            )
            cache.clear()  # only the active context is worth holding
            cache[key] = cached
        return cached

    def predict(ctx: StrategyContext, t: int) -> set[int]:
        last = last_seen_matrix(ctx)[t]
        gaps = np.where(last >= 0, t - last, t + 1)
        order = np.lexsort((np.arange(100), -gaps))
        return set(order[:k].astype(int).tolist())

    return predict


def _position_plurality(rule: str) -> PredictFn:
    def predict(ctx: StrategyContext, t: int) -> set[int]:
        vals = ctx.values[t]
        tails = vals % 10
        heads = vals // 10
        if rule == "tail_tail":
            candidates = (tails[:, None] * 10 + tails[None, :]).ravel()
        else:
            candidates = (heads[:, None] * 10 + tails[None, :]).ravel()
        counts = np.bincount(candidates.astype(int), minlength=100)
        order = np.lexsort((np.arange(100), -counts))
        return set(order[:3].astype(int).tolist())

    return predict


def registry() -> list[Strategy]:
    return [
        Strategy("ĐB lặp lại", "special", _special_repeat, "Hai số cuối ĐB hôm nay."),
        Strategy("ĐB lộn", "special", _special_reverse, "Đảo hai số cuối ĐB."),
        Strategy("Bóng ĐB", "bong", _special_bong, "Bóng 0↔5,1↔6,2↔7,3↔8,4↔9."),
        Strategy("Bộ ĐB", "bong", _special_bo, "Họ số bóng/lộn của ĐB."),
        Strategy("Ghép ĐB×G1", "cross_prize", _db_g1_cross, "Đầu ĐB ghép đuôi G1 và số đảo."),
        Strategy("Chạm đầu ĐB", "touch", _touch_head, "Mọi số chứa chữ số đầu ĐB."),
        Strategy("Chạm đuôi ĐB", "touch", _touch_tail, "Mọi số chứa chữ số đuôi ĐB."),
        Strategy("Dàn đầu ĐB", "head_tail", _same_head, "10 số cùng đầu ĐB."),
        Strategy("Dàn đuôi ĐB", "head_tail", _same_tail, "10 số cùng đuôi ĐB."),
        Strategy("Dàn tổng ĐB", "sum", _same_sum, "10 số cùng tổng mod 10 với ĐB."),
        Strategy("Kép bằng + lệch", "kep", _kep_family, "Kép bằng và cặp bóng."),
        Strategy("Sát kép", "kep", _sat_kep, "Hai chữ số kề nhau."),
        Strategy("Lô rơi", "repeat", _lo_roi, "Toàn bộ số đã xuất hiện hôm nay."),
        Strategy("Lô lộn", "repeat", _lo_reverse, "Đảo toàn bộ số đã xuất hiện hôm nay."),
        Strategy("Hot 30d top5", "recency", _hot(30, 5), "5 số xuất hiện nhiều ngày nhất trong 30 ngày."),
        Strategy("Cold 30d top5", "recency", _cold(30, 5), "5 số xuất hiện ít ngày nhất trong 30 ngày."),
        Strategy("Hot 90d top5", "recency", _hot(90, 5), "5 số xuất hiện nhiều ngày nhất trong 90 ngày."),
        Strategy("Gan top5", "recency", _gan(5), "5 số lâu chưa xuất hiện nhất."),
        Strategy("Vị trí tail-tail plurality", "position", _position_plurality("tail_tail"), "Top3 số được nhiều cặp đuôi vị trí trỏ tới."),
        Strategy("Vị trí head-tail plurality", "position", _position_plurality("head_tail"), "Top3 số được nhiều cặp đầu-đuôi trỏ tới."),
    ]


def _baseline(target: np.ndarray, train_end: int, mode: Mode) -> np.ndarray:
    view = target[:train_end]
    counts = view.sum(axis=0, dtype=float)
    if mode == "de":
        prior = np.full(100, 0.01)
        strength = 100.0
    else:
        prior = np.full(100, float(view.mean()))
        strength = 50.0
    return (counts + strength * prior) / (len(view) + strength)


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return float((centre - margin) / denom), float((centre + margin) / denom)


def _evaluate_events(
    events: list[tuple[int, set[int]]],
    target: np.ndarray,
    baseline: np.ndarray,
) -> dict[str, float | int]:
    n_pred = 0
    hits = 0
    expected = 0.0
    variance = 0.0
    active_days = 0
    day_hits = 0
    for t, picks in events:
        if not picks:
            continue
        valid = np.array(sorted(n for n in picks if 0 <= n <= 99), dtype=int)
        if valid.size == 0:
            continue
        active_days += 1
        y = target[t, valid]
        p = baseline[valid]
        n_pred += int(valid.size)
        hits += int(y.sum())
        expected += float(p.sum())
        variance += float((p * (1.0 - p)).sum())
        day_hits += int(y.any())
    precision = hits / n_pred if n_pred else float("nan")
    base_rate = expected / n_pred if n_pred else float("nan")
    lift = precision / base_rate if n_pred and base_rate > 0 else float("nan")
    effect = precision - base_rate if n_pred else float("nan")
    if n_pred and variance > 0:
        z = (hits - 0.5 - expected) / np.sqrt(variance)
        p_value = float(stats.norm.sf(z))
    else:
        p_value = float("nan")
    ci_low, ci_high = _wilson(hits, n_pred)
    return {
        "active_days": active_days,
        "predicted_numbers": n_pred,
        "hits": hits,
        "precision": precision,
        "baseline_rate": base_rate,
        "lift": lift,
        "effect": effect,
        "p_value": p_value,
        "wilson_ci_low": ci_low,
        "wilson_ci_high": ci_high,
        "day_hit_rate": day_hits / active_days if active_days else float("nan"),
        "avg_picks_per_active_day": n_pred / active_days if active_days else 0.0,
    }


def _target_matrix(two: pd.DataFrame, sparse: pd.DataFrame, mode: Mode) -> np.ndarray:
    if mode == "loto":
        return sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
    de = (two["special"].to_numpy(dtype=int) % 100).astype(int)
    target = np.zeros((len(two), 100), dtype=bool)
    target[np.arange(len(two)), de] = True
    return target


def evaluate_lab(
    two: pd.DataFrame,
    sparse: pd.DataFrame,
    *,
    mode: Mode,
    warmup: int = 180,
    holdout_fraction: float = 0.25,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if two.empty or sparse.empty:
        raise ValueError("strategy lab requires non-empty two-digit and sparse histories")
    if "date" not in two.columns or "date" not in sparse.columns:
        raise ValueError("strategy lab histories must contain date columns")

    two_calendar = require_daily_contiguous(
        two["date"], context="strategy lab two-digit history"
    )
    sparse_calendar = require_daily_contiguous(
        sparse["date"], context="strategy lab sparse history"
    )
    if not two_calendar.equals(sparse_calendar):
        raise ValueError("strategy lab two-digit and sparse histories are not date-aligned")

    values = two.drop(columns=["date"]).to_numpy(dtype=int) % 100
    presence = sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
    if len(values) != len(presence):
        raise ValueError("strategy lab value/presence row count mismatch")

    ctx = StrategyContext(values=values, presence=presence)
    target = _target_matrix(two, sparse, mode)
    strategies = registry()
    last_source_day = len(two) - 2
    first = min(max(30, warmup), max(30, last_source_day - 30))
    split = first + int(
        (last_source_day - first + 1) * (1.0 - holdout_fraction)
    )
    split = min(max(first + 20, split), last_source_day - 10)
    baseline = _baseline(target, split + 1, mode)

    all_events: dict[str, list[tuple[int, set[int]]]] = {}
    masks: dict[str, np.ndarray] = {}
    rows: list[dict[str, object]] = []
    for strat in strategies:
        events: list[tuple[int, set[int]]] = []
        mask = np.zeros((len(two), 100), dtype=bool)
        for source_t in range(first, last_source_day + 1):
            picks = strat.predict(ctx, source_t)
            target_t = source_t + 1
            events.append((target_t, picks))
            if target_t >= split + 1:
                valid = [n for n in picks if 0 <= n <= 99]
                if valid:
                    mask[target_t, valid] = True
        all_events[strat.name] = events
        masks[strat.name] = mask
        full = _evaluate_events(events, target, baseline)
        hold = _evaluate_events(
            [(t, p) for t, p in events if t >= split + 1], target, baseline
        )
        rows.append(
            {
                "mode": mode,
                "strategy": strat.name,
                "category": strat.category,
                "description": strat.description,
                "warmup_days": first,
                "holdout_start_index": split + 1,
                "calendar_start": two_calendar[0].date().isoformat(),
                "calendar_end": two_calendar[-1].date().isoformat(),
                "calendar_contiguous": True,
                **{f"full_{k}": v for k, v in full.items()},
                **{f"holdout_{k}": v for k, v in hold.items()},
            }
        )

    table = pd.DataFrame(rows)
    q = bh_fdr(
        pd.to_numeric(table["holdout_p_value"], errors="coerce").to_numpy(dtype=float)
    )
    table["holdout_q_value_fdr"] = q
    min_effect = 0.005 if mode == "loto" else 0.0007
    table["research_gate_pass"] = (
        (table["holdout_q_value_fdr"] <= 0.05)
        & (table["holdout_lift"] >= 1.03)
        & (table["holdout_effect"] >= min_effect)
        & (table["holdout_predicted_numbers"] >= 100)
    )
    table = table.sort_values(
        ["research_gate_pass", "holdout_lift", "holdout_q_value_fdr"],
        ascending=[False, False, True],
        ignore_index=True,
    )

    # Agreement curve: only strategies that point to at most 10 numbers on a day
    # are allowed to contribute votes, reducing domination by broad dàn rules.
    agreement_rows: list[dict[str, object]] = []
    for k in range(1, 6):
        n_pred = hits = 0
        expected = 0.0
        days = 0
        for target_t in range(split + 1, len(two)):
            votes = np.zeros(100, dtype=int)
            for strat in strategies:
                events = all_events[strat.name]
                # Source index maps directly because calendar continuity is an
                # enforced invariant: first event predicts exactly first+1 day.
                pos = target_t - (first + 1)
                if 0 <= pos < len(events):
                    picks = events[pos][1]
                    if 0 < len(picks) <= 10:
                        votes[list(picks)] += 1
            chosen = np.flatnonzero(votes >= k)
            if chosen.size == 0:
                continue
            days += 1
            n_pred += int(chosen.size)
            hits += int(target[target_t, chosen].sum())
            expected += float(baseline[chosen].sum())
        precision = hits / n_pred if n_pred else float("nan")
        base_rate = expected / n_pred if n_pred else float("nan")
        agreement_rows.append(
            {
                "mode": mode,
                "min_votes": k,
                "active_days": days,
                "predicted_numbers": n_pred,
                "hits": hits,
                "precision": precision,
                "baseline_rate": base_rate,
                "lift": precision / base_rate
                if n_pred and base_rate > 0
                else float("nan"),
            }
        )
    agreement = pd.DataFrame(agreement_rows)

    # Pairwise prediction diversity over untouched holdout day-number cells.
    div_rows: list[dict[str, object]] = []
    names = [s.name for s in strategies]
    sl = slice(split + 1, len(two))
    for i, a in enumerate(names):
        x = masks[a][sl].ravel()
        for b in names[i + 1 :]:
            y = masks[b][sl].ravel()
            union = int(np.logical_or(x, y).sum())
            inter = int(np.logical_and(x, y).sum())
            jaccard = inter / union if union else 0.0
            if x.std() > 0 and y.std() > 0:
                corr = float(
                    np.corrcoef(x.astype(float), y.astype(float))[0, 1]
                )
            else:
                corr = 0.0
            div_rows.append(
                {
                    "mode": mode,
                    "strategy_a": a,
                    "strategy_b": b,
                    "jaccard": jaccard,
                    "phi_correlation": corr,
                }
            )
    diversity = pd.DataFrame(div_rows).sort_values(
        "phi_correlation", ascending=False, ignore_index=True
    )
    return table, agreement, diversity


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Standardized deterministic strategy research lab."
    )
    ap.add_argument("--out-dir", default="data/research")
    ap.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    ap.add_argument("--warmup", type=int, default=180)
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    sparse = lot.get_sparse_data().sort_values("date").reset_index(drop=True)
    if two.empty or sparse.empty:
        raise SystemExit("No data loaded")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    modes = ("loto", "de") if args.mode == "both" else (args.mode,)
    manifest: dict[str, object] = {
        "schema_version": 2,
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "anchor_date": pd.to_datetime(two["date"]).max().date().isoformat(),
        "strategy_count": len(registry()),
        "modes": {},
        "production_integration": False,
        "calendar_contract": "daily-contiguous and identical two-digit/sparse date axes",
    }
    for mode in modes:
        table, agreement, diversity = evaluate_lab(
            two,
            sparse,
            mode=mode,  # type: ignore[arg-type]
            warmup=max(30, args.warmup),
        )
        table.to_csv(out / f"strategy_lab_{mode}.csv", index=False)
        agreement.to_csv(out / f"strategy_agreement_{mode}.csv", index=False)
        diversity.to_csv(out / f"strategy_diversity_{mode}.csv", index=False)
        manifest["modes"][mode] = {  # type: ignore[index]
            "research_gate_pass_count": int(table["research_gate_pass"].sum()),
            "best_holdout_lift": float(
                pd.to_numeric(table["holdout_lift"], errors="coerce").max()
            ),
        }
    (out / "strategy_lab_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] strategy lab -> {out}")


if __name__ == "__main__":
    main()
