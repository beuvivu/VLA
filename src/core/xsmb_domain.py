from __future__ import annotations


from typing import Final

import numpy as np
import pandas as pd

FIELD_WIDTHS: Final[tuple[tuple[str, int], ...]] = (
    ("special", 5),
    ("prize1", 5),
    ("prize2_1", 5),
    ("prize2_2", 5),
    ("prize3_1", 5),
    ("prize3_2", 5),
    ("prize3_3", 5),
    ("prize3_4", 5),
    ("prize3_5", 5),
    ("prize3_6", 5),
    ("prize4_1", 4),
    ("prize4_2", 4),
    ("prize4_3", 4),
    ("prize4_4", 4),
    ("prize5_1", 4),
    ("prize5_2", 4),
    ("prize5_3", 4),
    ("prize5_4", 4),
    ("prize5_5", 4),
    ("prize5_6", 4),
    ("prize6_1", 3),
    ("prize6_2", 3),
    ("prize6_3", 3),
    ("prize7_1", 2),
    ("prize7_2", 2),
    ("prize7_3", 2),
    ("prize7_4", 2),
)

FIELD_WIDTH_MAP: Final[dict[str, int]] = dict(FIELD_WIDTHS)
PRIZE_FIELDS: Final[tuple[str, ...]] = tuple(name for name, _ in FIELD_WIDTHS)

PRIZE_GROUP_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    group: tuple(name for name in PRIZE_FIELDS if name.split("_")[0] == group)
    for group in dict.fromkeys(name.split("_")[0] for name in PRIZE_FIELDS)
}
PRIZE_GROUP_WIDTHS: Final[dict[str, int]] = {
    group: FIELD_WIDTH_MAP[fields[0]] for group, fields in PRIZE_GROUP_FIELDS.items()
}

LOTO_DRAWS_PER_DAY: Final[int] = len(FIELD_WIDTHS)

TOTAL_DIGITS: Final[int] = sum(width for _, width in FIELD_WIDTHS)

UNIFORM_TWO_DIGIT_RATE: Final[float] = 1.0 / 100.0

LOTO_BASELINE_RATE: Final[float] = 1.0 - (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY

DE_BASELINE_RATE: Final[float] = UNIFORM_TWO_DIGIT_RATE

PAIR_COOCCURRENCE_RATE: Final[float] = (
    1.0
    - 2.0 * (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY
    + (1.0 - 2.0 * UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY
)

PAIR_COUNT: Final[int] = 100 * 99 // 2


def pair_chance_maximum(
    n_draws: int,
    *,
    pair_count: int = PAIR_COUNT,
    rate: float = PAIR_COOCCURRENCE_RATE,
) -> tuple[float, tuple[int, int]]:
    if n_draws <= 0:
        return 0.0, (0, 0)

    from scipy.stats import binom

    ceiling = int(binom.ppf(1.0 - 1e-12, n_draws, rate)) + 20
    support = np.arange(ceiling + 1)
    cdf_max = binom.cdf(support, n_draws, rate) ** pair_count
    mean = float((1.0 - cdf_max).sum())
    low = int(support[np.searchsorted(cdf_max, 0.05)])
    high = int(support[np.searchsorted(cdf_max, 0.95)])
    return mean, (low, high)


def baseline_rate(mode: str) -> float:
    if mode == "de":
        return DE_BASELINE_RATE
    if mode == "loto":
        return LOTO_BASELINE_RATE
    raise ValueError("mode must be 'loto' or 'de'")


def build_position_labels() -> list[str]:
    return [f"{field}.d{k}" for field, width in FIELD_WIDTHS for k in range(width)]


def raw_digit_matrix(df_raw: pd.DataFrame) -> np.ndarray:
    missing = [name for name in PRIZE_FIELDS if name not in df_raw.columns]
    if missing:
        raise ValueError(f"raw history missing prize columns: {missing[:5]}")

    n = len(df_raw)
    out = np.empty((n, TOTAL_DIGITS), dtype=np.uint8)
    offset = 0
    for field, width in FIELD_WIDTHS:
        values = pd.to_numeric(df_raw[field], errors="raise").to_numpy(dtype=np.int64)
        if np.any(values < 0) or np.any(values >= 10**width):
            bad = int(values[(values < 0) | (values >= 10**width)][0])
            raise ValueError(f"{field}={bad} outside its {width}-digit range")
        for k in range(width):
            power = 10 ** (width - 1 - k)
            out[:, offset + k] = (values // power % 10).astype(np.uint8)
        offset += width
    return out


def position_pairs(n_positions: int) -> tuple[np.ndarray, np.ndarray]:
    i, j = np.triu_indices(int(n_positions), k=1)
    return i.astype(np.int16), j.astype(np.int16)


def reverse_indices() -> np.ndarray:
    numbers = np.arange(100, dtype=np.int16)
    return (10 * (numbers % 10) + numbers // 10).astype(np.int16)
