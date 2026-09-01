from __future__ import annotations

"""Chronological research lab for legacy cross-day positional rule families.

This closes a real semantic gap between the old ``xoso`` positional library and
VLA's current same-base-day path engine.  A rule may read digit A and digit B
from *different calendar days* before the target date, then apply one of the
legacy operators:

``concat``  AB -> one Loto number
``lon``     AB + BA -> a one/two-number Loto set
``bo``      bóng/reverse family of AB -> a 4/8-number Loto set
``cham``    digit A -> De contains A in either two-digit position
``tong``    (A+B) mod 10 -> final digit of De

Research safeguards:
- exact calendar-day lag lookup, so missing dates cannot silently become t-1;
- chronological train / validation / untouched holdout;
- shape-matched chance baselines for each rule/day;
- Benjamini-Hochberg FDR + Bonferroni across the full searched family;
- no automatic connection to production prediction weights.
"""

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

from lottery import Lottery
from number_reference import BONG, bo
from research_diagnostics import bh_fdr

Operator = Literal["concat", "lon", "bo", "cham", "tong"]


@dataclass(frozen=True)
class RuleSpec:
    op: Operator
    position_a: int
    position_b: int
    lag_a: int
    lag_b: int

    @property
    def name(self) -> str:
        if self.op == "cham":
            return f"cham:p{self.position_a}@t-{self.lag_a}"
        return (
            f"{self.op}:p{self.position_a}@t-{self.lag_a}"
            f"x p{self.position_b}@t-{self.lag_b}"
        )


def _position_columns(two: pd.DataFrame) -> list[str]:
    cols = [c for c in two.columns if c != "date"]
    if len(cols) != 27:
        raise ValueError(f"Expected 27 prize positions, got {len(cols)}")
    return cols


def _parse_lag_pairs(value: str) -> tuple[tuple[int, int], ...]:
    pairs: set[tuple[int, int]] = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        parts = token.replace(":", "-").split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid lag pair {token!r}; use e.g. 1-1,1-2")
        a, b = int(parts[0]), int(parts[1])
        if a < 1 or b < 1:
            raise ValueError("Cross-lag rules require lag >= 1")
        pairs.add((a, b))
    if not pairs:
        raise ValueError("At least one lag pair is required")
    return tuple(sorted(pairs))


def _parse_ops(value: str) -> tuple[Operator, ...]:
    allowed = {"concat", "lon", "bo", "cham", "tong"}
    ops = tuple(dict.fromkeys(x.strip() for x in value.split(",") if x.strip()))
    bad = [x for x in ops if x not in allowed]
    if bad:
        raise ValueError(f"Unknown operators: {bad}")
    if not ops:
        raise ValueError("At least one operator is required")
    return ops  # type: ignore[return-value]


def generate_rules(
    *,
    n_positions: int = 27,
    lag_pairs: tuple[tuple[int, int], ...] = ((1, 1), (1, 2)),
    ops: tuple[Operator, ...] = ("concat", "lon", "bo", "cham", "tong"),
) -> list[RuleSpec]:
    if n_positions < 1:
        return []
    rules: list[RuleSpec] = []
    unique_lag_a = sorted({a for a, _ in lag_pairs})
    for op in ops:
        if op == "cham":
            for lag in unique_lag_a:
                for i in range(n_positions):
                    rules.append(RuleSpec(op, i, -1, lag, -1))
            continue
        for lag_a, lag_b in lag_pairs:
            for i in range(n_positions):
                for j in range(n_positions):
                    # AB and BA are identical when the same digit is used from
                    # the same source day; avoid a redundant 'lon' hypothesis.
                    if op == "lon" and i == j and lag_a == lag_b:
                        continue
                    rules.append(RuleSpec(op, i, j, lag_a, lag_b))
    return rules


def payload_for_digits(op: Operator, a: int, b: int | None = None) -> tuple[int, ...]:
    if not 0 <= int(a) <= 9:
        raise ValueError("digit a must be 0..9")
    if op == "cham":
        return (int(a),)
    if b is None or not 0 <= int(b) <= 9:
        raise ValueError("digit b must be 0..9")
    a, b = int(a), int(b)
    ab = 10 * a + b
    if op == "concat":
        return (ab,)
    if op == "lon":
        return tuple(sorted({ab, 10 * b + a}))
    if op == "bo":
        return tuple(sorted(int(x) for x in bo(ab)))
    if op == "tong":
        return ((a + b) % 10,)
    raise ValueError(op)


def _build_bo_candidates() -> tuple[np.ndarray, np.ndarray]:
    width = 8
    candidates = np.zeros((100, width), dtype=np.int16)
    valid = np.zeros((100, width), dtype=bool)
    for code in range(100):
        vals = np.asarray(payload_for_digits("bo", code // 10, code % 10), dtype=np.int16)
        candidates[code, : len(vals)] = vals
        valid[code, : len(vals)] = True
    return candidates, valid


_BO_CANDIDATES, _BO_VALID = _build_bo_candidates()
_BO_SIZE = _BO_VALID.sum(axis=1).astype(np.int16)


def _loto_base_table() -> np.ndarray:
    table = np.zeros((101, 101), dtype=float)
    for m in range(101):
        for k in range(101):
            if m <= 0 or k <= 0:
                table[m, k] = 0.0
            elif k >= 100 - m + 1:
                table[m, k] = 1.0
            else:
                table[m, k] = 1.0 - math.comb(100 - m, k) / math.comb(100, k)
    return table


_LOTO_BASE = _loto_base_table()


def _calendar_source_indices(dates: pd.DatetimeIndex, lag: int) -> np.ndarray:
    index = {pd.Timestamp(d).normalize(): i for i, d in enumerate(dates)}
    out = np.full(len(dates), -1, dtype=np.int32)
    delta = pd.Timedelta(days=int(lag))
    for t, d in enumerate(dates):
        out[t] = int(index.get(pd.Timestamp(d).normalize() - delta, -1))
    return out


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return float((center - margin) / denom), float((center + margin) / denom)


def _segment_metrics(hits: np.ndarray, base: np.ndarray) -> dict[str, float | int]:
    n = int(len(hits))
    if n == 0:
        return {
            "trials": 0,
            "hits": 0,
            "precision": float("nan"),
            "baseline": float("nan"),
            "lift": float("nan"),
            "effect": float("nan"),
            "p_value": float("nan"),
            "wilson_low": float("nan"),
            "wilson_high": float("nan"),
        }
    h = np.asarray(hits, dtype=bool)
    p = np.clip(np.asarray(base, dtype=float), 1e-9, 1.0 - 1e-9)
    k = int(h.sum())
    precision = k / n
    baseline = float(p.mean())
    expected = float(p.sum())
    variance = float(np.sum(p * (1.0 - p)))
    z = (k - 0.5 - expected) / math.sqrt(max(variance, 1e-12))
    p_value = float(stats.norm.sf(z))
    low, high = _wilson(k, n)
    return {
        "trials": n,
        "hits": k,
        "precision": float(precision),
        "baseline": baseline,
        "lift": float(precision / baseline) if baseline > 0 else float("nan"),
        "effect": float(precision - baseline),
        "p_value": p_value,
        "wilson_low": low,
        "wilson_high": high,
    }


def _rule_series(
    rule: RuleSpec,
    *,
    eval_idx: np.ndarray,
    tails: np.ndarray,
    source_index: dict[int, np.ndarray],
    loto_presence: np.ndarray,
    de_values: np.ndarray,
    distinct_loto: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    src_a = source_index[rule.lag_a][eval_idx]
    valid = src_a >= 0
    if rule.op != "cham":
        src_b = source_index[rule.lag_b][eval_idx]
        valid &= src_b >= 0
    target = eval_idx[valid]
    if target.size == 0:
        return target, np.zeros(0, dtype=bool), np.zeros(0, dtype=float)

    src_a = source_index[rule.lag_a][target]
    a = tails[src_a, rule.position_a]

    if rule.op == "cham":
        de = de_values[target]
        hits = ((de // 10) == a) | ((de % 10) == a)
        base = np.full(len(target), 0.19, dtype=float)
        return target, hits, base

    src_b = source_index[rule.lag_b][target]
    b = tails[src_b, rule.position_b]
    ab = (10 * a + b).astype(np.int16)

    if rule.op == "tong":
        candidate = (a + b) % 10
        hits = (de_values[target] % 10) == candidate
        base = np.full(len(target), 0.10, dtype=float)
        return target, hits, base

    row = np.arange(len(target))
    target_loto = loto_presence[target]
    if rule.op == "concat":
        hits = target_loto[row, ab]
        k = np.ones(len(target), dtype=np.int16)
    elif rule.op == "lon":
        ba = (10 * b + a).astype(np.int16)
        hits = target_loto[row, ab] | target_loto[row, ba]
        k = np.where(ab == ba, 1, 2).astype(np.int16)
    elif rule.op == "bo":
        candidates = _BO_CANDIDATES[ab]
        valid_candidates = _BO_VALID[ab]
        gathered = target_loto[row[:, None], candidates]
        hits = np.any(gathered & valid_candidates, axis=1)
        k = _BO_SIZE[ab]
    else:
        raise ValueError(rule.op)

    m = distinct_loto[target].astype(np.int16)
    base = _LOTO_BASE[m, k]
    return target, hits, base


def _next_payload(
    rule: RuleSpec,
    *,
    dates: pd.DatetimeIndex,
    tails: np.ndarray,
) -> tuple[str | None, str | None]:
    latest = pd.Timestamp(dates[-1]).normalize()
    target = latest + pd.Timedelta(days=1)
    lookup = {pd.Timestamp(d).normalize(): i for i, d in enumerate(dates)}
    ia = lookup.get(target - pd.Timedelta(days=rule.lag_a))
    if ia is None:
        return target.date().isoformat(), None
    a = int(tails[int(ia), rule.position_a])
    if rule.op == "cham":
        return target.date().isoformat(), json.dumps({"digit": a}, ensure_ascii=False)
    ib = lookup.get(target - pd.Timedelta(days=rule.lag_b))
    if ib is None:
        return target.date().isoformat(), None
    b = int(tails[int(ib), rule.position_b])
    payload = payload_for_digits(rule.op, a, b)
    return target.date().isoformat(), json.dumps(list(payload), ensure_ascii=False)


def evaluate_lab(
    two: pd.DataFrame,
    sparse: pd.DataFrame,
    *,
    lag_pairs: tuple[tuple[int, int], ...] = ((1, 1), (1, 2)),
    ops: tuple[Operator, ...] = ("concat", "lon", "bo", "cham", "tong"),
    warmup: int = 180,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
) -> tuple[pd.DataFrame, dict[str, object]]:
    two = two.sort_values("date").reset_index(drop=True).copy()
    sparse = sparse.sort_values("date").reset_index(drop=True).copy()
    if len(two) != len(sparse):
        raise ValueError("two-digit and sparse history must have identical row counts")
    if len(two) < 60:
        raise ValueError("At least 60 draws are required for cross-lag research")

    cols = _position_columns(two)
    dates = pd.DatetimeIndex(pd.to_datetime(two["date"]).dt.normalize())
    values = two[cols].to_numpy(dtype=int) % 100
    tails = (values % 10).astype(np.int8)
    de_values = (two["special"].to_numpy(dtype=int) % 100).astype(np.int16)
    loto_presence = sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
    distinct_loto = loto_presence.sum(axis=1).astype(np.int16)

    all_lags = sorted({x for pair in lag_pairs for x in pair})
    source_index = {lag: _calendar_source_indices(dates, lag) for lag in all_lags}

    # The rule itself has no fitted parameters, but we still reserve the early
    # history as warmup and split the evaluated targets chronologically.
    first_eval = min(max(max(all_lags), int(warmup)), max(max(all_lags), len(two) - 45))
    eval_idx = np.arange(first_eval, len(two), dtype=np.int32)
    if len(eval_idx) < 30:
        raise ValueError("Insufficient post-warmup history")
    train_n = max(10, int(len(eval_idx) * train_fraction))
    validation_n = max(5, int(len(eval_idx) * validation_fraction))
    if train_n + validation_n >= len(eval_idx):
        validation_n = max(5, len(eval_idx) - train_n - 5)
    train_cut = int(eval_idx[min(train_n, len(eval_idx) - 1)])
    validation_end_pos = min(train_n + validation_n, len(eval_idx) - 1)
    validation_cut = int(eval_idx[validation_end_pos])

    rules = generate_rules(n_positions=len(cols), lag_pairs=lag_pairs, ops=ops)
    rows: list[dict[str, object]] = []
    train_p: list[float] = []
    for rule in rules:
        target, hits, base = _rule_series(
            rule,
            eval_idx=eval_idx,
            tails=tails,
            source_index=source_index,
            loto_presence=loto_presence,
            de_values=de_values,
            distinct_loto=distinct_loto,
        )
        train_mask = target <= train_cut
        validation_mask = (target > train_cut) & (target <= validation_cut)
        holdout_mask = target > validation_cut
        tr = _segment_metrics(hits[train_mask], base[train_mask])
        va = _segment_metrics(hits[validation_mask], base[validation_mask])
        ho = _segment_metrics(hits[holdout_mask], base[holdout_mask])
        p = float(tr["p_value"])
        train_p.append(p)
        target_date, next_payload = _next_payload(rule, dates=dates, tails=tails)
        rows.append(
            {
                "rule": rule.name,
                "operator": rule.op,
                "position_a": rule.position_a,
                "position_a_name": cols[rule.position_a],
                "position_b": rule.position_b,
                "position_b_name": cols[rule.position_b] if rule.position_b >= 0 else "",
                "lag_a_days": rule.lag_a,
                "lag_b_days": rule.lag_b,
                "next_target_date": target_date,
                "next_payload": next_payload,
                **{f"train_{k}": v for k, v in tr.items()},
                **{f"validation_{k}": v for k, v in va.items()},
                **{f"holdout_{k}": v for k, v in ho.items()},
            }
        )

    table = pd.DataFrame(rows)
    q = bh_fdr(np.asarray(train_p, dtype=float))
    table["train_q_value_fdr"] = q
    table["train_bonferroni_p"] = np.minimum(1.0, np.asarray(train_p) * max(len(table), 1))
    table["research_gate_pass"] = (
        (table["train_q_value_fdr"] <= 0.05)
        & (pd.to_numeric(table["validation_lift"], errors="coerce") >= 1.03)
        & (pd.to_numeric(table["holdout_lift"], errors="coerce") >= 1.03)
        & (pd.to_numeric(table["validation_effect"], errors="coerce") > 0.0)
        & (pd.to_numeric(table["holdout_effect"], errors="coerce") > 0.0)
    )
    table["production_eligible"] = False
    table = table.sort_values(
        ["research_gate_pass", "holdout_lift", "validation_lift", "train_q_value_fdr"],
        ascending=[False, False, False, True],
        ignore_index=True,
    )

    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "anchor_date": dates[-1].date().isoformat(),
        "research_only": True,
        "production_wired": False,
        "positions": len(cols),
        "hypotheses": int(len(table)),
        "operators": list(ops),
        "lag_pairs": [list(x) for x in lag_pairs],
        "warmup_rows": int(first_eval),
        "train_end_date": dates[train_cut].date().isoformat(),
        "validation_end_date": dates[validation_cut].date().isoformat(),
        "holdout_days": int((eval_idx > validation_cut).sum()),
        "train_fdr_05_count": int((table["train_q_value_fdr"] <= 0.05).sum()),
        "train_bonferroni_05_count": int((table["train_bonferroni_p"] <= 0.05).sum()),
        "research_gate_pass_count": int(table["research_gate_pass"].sum()),
        "note": (
            "Cross-day positional rules remain research-only even when research_gate_pass is true. "
            "A separate preregistered validation/promotion process is required before any production use."
        ),
    }
    return table, report


def run(
    *,
    out_dir: Path | str = "data/research/crosslag_positional",
    lag_pairs: tuple[tuple[int, int], ...] = ((1, 1), (1, 2)),
    ops: tuple[Operator, ...] = ("concat", "lon", "bo", "cham", "tong"),
    warmup: int = 180,
) -> tuple[Path, Path]:
    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    sparse = lot.get_sparse_data().sort_values("date").reset_index(drop=True)
    if two.empty or sparse.empty:
        raise RuntimeError("No data loaded")
    table, report = evaluate_lab(two, sparse, lag_pairs=lag_pairs, ops=ops, warmup=warmup)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "crosslag_rules.csv"
    report_path = out / "report.json"
    table.to_csv(csv_path, index=False)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return csv_path, report_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-calendar-lag positional strategy research lab.")
    ap.add_argument("--out-dir", default="data/research/crosslag_positional")
    ap.add_argument("--lag-pairs", default="1-1,1-2")
    ap.add_argument("--operators", default="concat,lon,bo,cham,tong")
    ap.add_argument("--warmup", type=int, default=180)
    args = ap.parse_args()
    csv_path, report_path = run(
        out_dir=args.out_dir,
        lag_pairs=_parse_lag_pairs(args.lag_pairs),
        ops=_parse_ops(args.operators),
        warmup=max(30, int(args.warmup)),
    )
    print("[OK] cross-lag positional lab ->", csv_path, report_path)


if __name__ == "__main__":
    main()
