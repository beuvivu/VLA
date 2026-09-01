from __future__ import annotations

"""Research firewall for large positional hypothesis searches.

A path family is allowed to look interesting only after it survives a chronology-
preserving evaluation protocol:

1. generate the full candidate family without looking at outcomes;
2. chronological train / validation / holdout split;
3. one-sided significance versus a training-only, number-specific baseline;
4. Benjamini-Hochberg FDR across every searched hypothesis;
5. validation and untouched holdout effect-size gates;
6. max-statistic circular-shift reality check for data snooping.

The output is a research audit.  It is not wired into production prediction
weights; future promotion must explicitly consume ``production_eligible``.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

from lottery import Lottery
from research_diagnostics import bh_fdr

Mode = Literal["loto", "de"]


def _candidate_family(two: pd.DataFrame) -> tuple[np.ndarray, list[dict[str, object]]]:
    cols = [c for c in two.columns if c != "date"]
    if len(cols) != 27:
        raise ValueError(f"Expected 27 prize positions, got {len(cols)}")
    values = two[cols].to_numpy(dtype=int) % 100
    tails = values % 10
    heads = values // 10
    p = len(cols)
    ii = np.repeat(np.arange(p), p)
    jj = np.tile(np.arange(p), p)

    tail2 = (tails[:-1, ii] * 10 + tails[:-1, jj]).astype(np.int16)
    head_tail = (heads[:-1, ii] * 10 + tails[:-1, jj]).astype(np.int16)
    candidates = np.concatenate([tail2, head_tail], axis=1)

    meta: list[dict[str, object]] = []
    for rule in ("tail_tail", "head_tail"):
        for i, j in zip(ii, jj):
            meta.append(
                {
                    "rule": rule,
                    "position_i": int(i),
                    "position_i_name": cols[int(i)],
                    "position_j": int(j),
                    "position_j_name": cols[int(j)],
                }
            )
    return candidates, meta


def _targets(two: pd.DataFrame, sparse: pd.DataFrame, mode: Mode) -> np.ndarray:
    if mode == "loto":
        return (sparse.drop(columns=["date"]).to_numpy(dtype=int)[1:] > 0)
    de = (two["special"].to_numpy(dtype=int)[1:] % 100).astype(int)
    out = np.zeros((len(de), 100), dtype=bool)
    out[np.arange(len(de)), de] = True
    return out


def _baseline_from_train(target: np.ndarray, *, mode: Mode) -> np.ndarray:
    counts = target.sum(axis=0, dtype=float)
    n = max(len(target), 1)
    if mode == "de":
        prior_mean = np.full(100, 0.01, dtype=float)
        prior_strength = 120.0
    else:
        grand = float(target.mean())
        prior_mean = np.full(100, grand, dtype=float)
        prior_strength = 60.0
    return (counts + prior_strength * prior_mean) / (n + prior_strength)


def _segment_metrics(candidates: np.ndarray, target: np.ndarray, baseline: np.ndarray) -> dict[str, np.ndarray]:
    if len(candidates) != len(target):
        raise ValueError("candidate/target length mismatch")
    n = len(target)
    row = np.arange(n)[:, None]
    hits_matrix = target[row, candidates]
    hits = hits_matrix.sum(axis=0, dtype=float)
    expected_prob = baseline[candidates]
    expected = expected_prob.sum(axis=0)
    variance = np.maximum((expected_prob * (1.0 - expected_prob)).sum(axis=0), 1e-9)
    precision = hits / max(n, 1)
    baseline_rate = expected / max(n, 1)
    effect = precision - baseline_rate
    lift = np.divide(precision, baseline_rate, out=np.ones_like(precision), where=baseline_rate > 0)
    z = (hits - 0.5 - expected) / np.sqrt(variance)
    p = stats.norm.sf(z)
    return {
        "hits": hits,
        "precision": precision,
        "baseline": baseline_rate,
        "effect": effect,
        "lift": lift,
        "z": z,
        "p": np.asarray(p, dtype=float),
    }


def _reality_check(
    candidates: np.ndarray,
    target: np.ndarray,
    baseline: np.ndarray,
    *,
    permutations: int,
    seed: int,
    max_days: int,
) -> dict[str, float | int]:
    n = min(len(target), max(120, int(max_days)))
    cand = candidates[-n:]
    tgt = target[-n:]
    row = np.arange(n)[:, None]
    baseline_rate = baseline[cand].mean(axis=0)
    observed_precision = tgt[row, cand].mean(axis=0)
    observed_max_skill = float(np.max(observed_precision - baseline_rate))

    if n < 30:
        return {
            "permutations": 0,
            "observed_max_skill": observed_max_skill,
            "p_value": float("nan"),
        }

    rng = np.random.default_rng(seed)
    valid_shifts = np.arange(5, max(6, n - 5))
    if valid_shifts.size == 0:
        return {
            "permutations": 0,
            "observed_max_skill": observed_max_skill,
            "p_value": float("nan"),
        }
    shifts = rng.choice(valid_shifts, size=max(1, permutations), replace=valid_shifts.size < permutations)
    null_max: list[float] = []
    ge = 0
    for shift in shifts:
        shifted = np.roll(tgt, int(shift), axis=0)
        precision = shifted[row, cand].mean(axis=0)
        max_skill = float(np.max(precision - baseline_rate))
        null_max.append(max_skill)
        ge += int(max_skill >= observed_max_skill - 1e-12)
    return {
        "permutations": int(len(shifts)),
        "observed_max_skill": observed_max_skill,
        "null_max_skill_mean": float(np.mean(null_max)),
        "null_max_skill_p95": float(np.quantile(null_max, 0.95)),
        "p_value": float((ge + 1) / (len(shifts) + 1)),
        "method": "max-statistic circular shift; preserves daily cross-sectional outcomes",
    }


def evaluate_mode(
    two: pd.DataFrame,
    sparse: pd.DataFrame,
    *,
    mode: Mode,
    train_frac: float = 0.60,
    validation_frac: float = 0.20,
    permutations: int = 63,
    seed: int = 20260901,
    max_reality_days: int = 1000,
) -> tuple[pd.DataFrame, dict]:
    candidates, meta = _candidate_family(two)
    target = _targets(two, sparse, mode)
    if len(candidates) != len(target):
        raise ValueError("Generated candidates are not aligned with next-day targets")

    n = len(target)
    train_end = max(60, int(n * train_frac))
    validation_end = max(train_end + 30, int(n * (train_frac + validation_frac)))
    validation_end = min(validation_end, n - 30)
    if train_end >= validation_end or validation_end >= n:
        raise ValueError("Insufficient history for chronological train/validation/holdout")

    baseline = _baseline_from_train(target[:train_end], mode=mode)
    tr = _segment_metrics(candidates[:train_end], target[:train_end], baseline)
    va = _segment_metrics(candidates[train_end:validation_end], target[train_end:validation_end], baseline)
    ho = _segment_metrics(candidates[validation_end:], target[validation_end:], baseline)
    q = bh_fdr(tr["p"])

    min_lift = 1.03
    min_effect = 0.004 if mode == "loto" else 0.0005
    eligible = (
        (q <= 0.05)
        & (tr["lift"] >= min_lift)
        & (va["lift"] >= min_lift)
        & (ho["lift"] >= min_lift)
        & (va["effect"] >= min_effect)
        & (ho["effect"] >= min_effect)
    )

    rows: list[dict[str, object]] = []
    for k, info in enumerate(meta):
        rows.append(
            {
                **info,
                "mode": mode,
                "train_days": train_end,
                "validation_days": validation_end - train_end,
                "holdout_days": n - validation_end,
                "train_precision": float(tr["precision"][k]),
                "train_baseline": float(tr["baseline"][k]),
                "train_lift": float(tr["lift"][k]),
                "train_effect": float(tr["effect"][k]),
                "train_p_value": float(tr["p"][k]),
                "train_q_value_fdr": float(q[k]),
                "validation_precision": float(va["precision"][k]),
                "validation_baseline": float(va["baseline"][k]),
                "validation_lift": float(va["lift"][k]),
                "validation_effect": float(va["effect"][k]),
                "holdout_precision": float(ho["precision"][k]),
                "holdout_baseline": float(ho["baseline"][k]),
                "holdout_lift": float(ho["lift"][k]),
                "holdout_effect": float(ho["effect"][k]),
                "production_eligible": bool(eligible[k]),
            }
        )

    table = pd.DataFrame(rows).sort_values(
        ["production_eligible", "holdout_lift", "validation_lift", "train_q_value_fdr"],
        ascending=[False, False, False, True],
        ignore_index=True,
    )
    reality = _reality_check(
        candidates[:train_end],
        target[:train_end],
        baseline,
        permutations=max(15, permutations),
        seed=seed,
        max_days=max_reality_days,
    )
    report = {
        "mode": mode,
        "hypotheses": int(len(meta)),
        "train_days": train_end,
        "validation_days": validation_end - train_end,
        "holdout_days": n - validation_end,
        "fdr_significant_train": int((q <= 0.05).sum()),
        "production_eligible_count": int(eligible.sum()),
        "minimum_lift_gate": min_lift,
        "minimum_effect_gate": min_effect,
        "reality_check": reality,
        "gate_pass": bool(eligible.any() and float(reality.get("p_value", 1.0)) <= 0.05),
        "note": (
            "No strategy is promoted automatically. gate_pass only means the searched family warrants further review; "
            "the production ensemble remains unchanged unless a separate validated promotion is implemented."
        ),
    }
    return table, report


def main() -> None:
    ap = argparse.ArgumentParser(description="Chronological multiple-testing/data-snooping firewall.")
    ap.add_argument("--out-dir", default="data/research")
    ap.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    ap.add_argument("--permutations", type=int, default=63)
    ap.add_argument("--seed", type=int, default=20260901)
    ap.add_argument("--max-reality-days", type=int, default=1000)
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
    reports: dict[str, object] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "anchor_date": pd.to_datetime(two["date"]).max().date().isoformat(),
        "modes": {},
    }
    for offset, mode in enumerate(modes):
        table, report = evaluate_mode(
            two,
            sparse,
            mode=mode,  # type: ignore[arg-type]
            permutations=max(15, args.permutations),
            seed=args.seed + offset,
            max_reality_days=max(120, args.max_reality_days),
        )
        table.to_csv(out / f"research_firewall_{mode}.csv", index=False)
        reports["modes"][mode] = report  # type: ignore[index]

    (out / "research_firewall_report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] research firewall -> {out}")


if __name__ == "__main__":
    main()
