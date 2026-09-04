from __future__ import annotations

import argparse
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from calendar_alignment import consecutive_next_pairs
from lottery import Lottery
from path_models import build_daily_targets


@dataclass(frozen=True)
class MarkovChain:
    states: tuple[int, ...]
    transition_counts: np.ndarray
    transition_probabilities: np.ndarray
    outgoing_counts: np.ndarray
    alpha: float


def build_markov_chain(
    observations: Sequence[int],
    *,
    alpha: float = 1.0,
    states: Sequence[int] = tuple(range(100)),
) -> MarkovChain:
    """Fit an exclusive-state first-order Markov chain with additive smoothing.

    This implements ``(count(i,j)+alpha)/(count(i,*)+alpha*|S|)``.  It is a
    statistical estimator, not evidence that lottery states are predictively
    Markovian; it must be compared with marginal and rolling baselines OOS.
    """
    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, Real)
        or not np.isfinite(alpha)
        or alpha < 0.0
    ):
        raise ValueError("alpha must be finite and >= 0")
    state_values = tuple(states)
    if any(
        isinstance(state, bool) or not isinstance(state, Integral)
        for state in state_values
    ):
        raise ValueError("states must contain only integers")
    state_space = tuple(int(state) for state in state_values)
    if not state_space or len(state_space) != len(set(state_space)):
        raise ValueError("states must be a non-empty unique sequence")
    index = {state: i for i, state in enumerate(state_space)}
    observed_values = tuple(observations)
    if any(
        isinstance(value, bool) or not isinstance(value, Integral)
        for value in observed_values
    ):
        raise ValueError("observations must contain only integers")
    sequence = [int(value) for value in observed_values]
    unknown = sorted(set(sequence) - set(state_space))
    if unknown:
        raise ValueError(f"observations contain states outside state space: {unknown[:10]}")

    counts = np.zeros((len(state_space), len(state_space)), dtype=np.int64)
    for previous, current in zip(sequence[:-1], sequence[1:], strict=True):
        counts[index[previous], index[current]] += 1
    outgoing = counts.sum(axis=1, dtype=np.int64)
    denominator = outgoing[:, None] + alpha * len(state_space)
    probabilities = np.divide(
        counts + alpha,
        denominator,
        out=np.zeros_like(counts, dtype=float),
        where=denominator > 0.0,
    )
    return MarkovChain(
        states=state_space,
        transition_counts=counts,
        transition_probabilities=probabilities,
        outgoing_counts=outgoing,
        alpha=float(alpha),
    )


def compute_markov_for_loto(df_2d: pd.DataFrame, alpha: float = 1.0, beta: float = 1.0) -> pd.DataFrame:
    """Estimate same-number next-calendar-day transition probabilities.

    For each number x in 00..99:
      p_hit_given_hit = P(hit_t=1 | hit_{t-1 calendar day}=1)
      p_hit_given_miss = P(hit_t=1 | hit_{t-1 calendar day}=0)

    Missing dates are skipped rather than collapsing a multi-day jump into a
    one-day Markov transition. Probabilities use Beta smoothing.
    """
    if (
        isinstance(alpha, bool)
        or isinstance(beta, bool)
        or not isinstance(alpha, Real)
        or not isinstance(beta, Real)
        or not np.isfinite(alpha)
        or not np.isfinite(beta)
        or alpha < 0.0
        or beta < 0.0
    ):
        raise ValueError("alpha and beta must be finite and >= 0")
    if alpha + beta <= 0.0:
        raise ValueError("alpha + beta must be > 0")
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    dates, loto_targets, _ = build_daily_targets(df_2d)
    n = len(loto_targets)
    if n < 2:
        return pd.DataFrame()

    hit = np.zeros((n, 100), dtype=bool)
    for t, nums in enumerate(loto_targets):
        if nums:
            hit[t, np.fromiter((int(x) for x in nums), dtype=np.int16)] = True

    source_idx, target_idx = consecutive_next_pairs(dates)
    if source_idx.size == 0:
        return pd.DataFrame()

    prev_hit = hit[source_idx]
    curr_hit = hit[target_idx]

    prev1_total = prev_hit.sum(axis=0, dtype=np.int32)
    prev0_total = (~prev_hit).sum(axis=0, dtype=np.int32)
    prev1_curr1 = (prev_hit & curr_hit).sum(axis=0, dtype=np.int32)
    prev0_curr1 = ((~prev_hit) & curr_hit).sum(axis=0, dtype=np.int32)

    p11 = (prev1_curr1 + alpha) / (prev1_total + alpha + beta)
    p01 = (prev0_curr1 + alpha) / (prev0_total + alpha + beta)

    df = pd.DataFrame(
        {
            "number": np.arange(100, dtype=np.int32),
            "calendar_transition_days": int(source_idx.size),
            "prev1_total": prev1_total,
            "prev1_curr1": prev1_curr1,
            "p_hit_given_hit": p11,
            "prev0_total": prev0_total,
            "prev0_curr1": prev0_curr1,
            "p_hit_given_miss": p01,
            "lift": p11 / np.maximum(p01, 1e-9),
        }
    ).sort_values(["lift", "p_hit_given_hit"], ascending=[False, False])

    return df.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="data/markov/markov_loto.csv")
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--beta", type=float, default=1.0)
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    df_2d = lot.get_2_digits_data()
    if df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = compute_markov_for_loto(df_2d, alpha=args.alpha, beta=args.beta)
    df.to_csv(out_path, index=False)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
