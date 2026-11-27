from __future__ import annotations

import numpy as np

MAX_PER_TAIL = 3


def diversified_order(
    probabilities: np.ndarray, k: int, *, max_per_tail: int = MAX_PER_TAIL
) -> list[int]:
    probs = np.asarray(probabilities, dtype=float)
    if max_per_tail < 1:
        raise ValueError("max_per_tail phải ≥ 1")
    order = np.lexsort((np.arange(len(probs)), -probs))
    chosen: list[int] = []
    per_tail = [0] * 10
    for n in order:
        if len(chosen) == k:
            return chosen
        tail = int(n) % 10
        if per_tail[tail] < max_per_tail:
            chosen.append(int(n))
            per_tail[tail] += 1
    for n in order:
        if len(chosen) == k:
            break
        if int(n) not in chosen:
            chosen.append(int(n))
    return chosen
