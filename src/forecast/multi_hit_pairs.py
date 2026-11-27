from __future__ import annotations

import numpy as np

N_NUMBERS = 100
N_PAIRS = N_NUMBERS * (N_NUMBERS - 1) // 2
WINDOW = 100
TOP_K = 5
MAX_PER_NUMBER = 2
TIE_SEED = 20261013
FROZEN_AT = "2026-10-12"

PAIR_A, PAIR_B = np.triu_indices(N_NUMBERS, k=1)


def base_rate(per_draw: int = 27) -> float:
    return float(1 - 2 * 0.99 ** per_draw + 0.98 ** per_draw)


def tie_keys(t: int) -> np.ndarray:
    return np.random.default_rng([TIE_SEED, t]).permutation(N_PAIRS)


def pick_pairs(together: np.ndarray, last: np.ndarray, t: int, k: int = TOP_K,
               max_per_number: int = MAX_PER_NUMBER) -> list[int]:
    order = np.lexsort((tie_keys(t), -last, -together))
    used = np.zeros(N_NUMBERS, dtype=int)
    chosen: list[int] = []
    for i in order:
        a, b = PAIR_A[i], PAIR_B[i]
        if used[a] >= max_per_number or used[b] >= max_per_number:
            continue
        chosen.append(int(i))
        used[a] += 1
        used[b] += 1
        if len(chosen) == k:
            break
    return chosen


def walk_forward(present: np.ndarray, window: int = WINDOW, k: int = TOP_K,
                 max_per_number: int = MAX_PER_NUMBER) -> dict:
    present = np.asarray(present, dtype=bool)
    total = len(present)
    if total < window:
        raise ValueError(f"cần ít nhất {window} kỳ, có {total}")
    as_int = present.astype(np.int32)
    co = np.zeros((N_NUMBERS, N_NUMBERS), dtype=np.int32)
    last = np.full((N_NUMBERS, N_NUMBERS), -1, dtype=np.int64)
    for s in range(window):
        both = np.outer(as_int[s], as_int[s])
        co += both
        last[both.astype(bool)] = s
    picks, hits, expected = [], [], []
    for t in range(window, total + 1):
        together, recency = co[PAIR_A, PAIR_B], last[PAIR_A, PAIR_B]
        chosen = pick_pairs(together, recency, t, k, max_per_number)
        picks.append(chosen)
        if t == total:
            break
        row = present[t]
        hits.append(int((row[PAIR_A[chosen]] & row[PAIR_B[chosen]]).sum()))
        d = int(row.sum())
        expected.append(k * d * (d - 1) / 2 / N_PAIRS)
        both = np.outer(as_int[t], as_int[t])
        co += both
        last[both.astype(bool)] = t
        co -= np.outer(as_int[t - window], as_int[t - window])
    final = picks[-1]
    return {
        "rows": list(range(window, total)),
        "picks": np.asarray(picks, dtype=int),
        "hits": np.asarray(hits, dtype=int),
        "expected": np.asarray(expected, dtype=float),
        "together": [int(co[PAIR_A[i], PAIR_B[i]]) for i in final],
        "last": [int(last[PAIR_A[i], PAIR_B[i]]) for i in final],
    }


def pair_label(i: int) -> list[str]:
    return [f"{int(PAIR_A[i]):02d}", f"{int(PAIR_B[i]):02d}"]
