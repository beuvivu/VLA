from __future__ import annotations

"""Single source of truth for the XSMB draw structure and its derived constants.

Before this module the prize layout (``FIELD_WIDTHS``) was re-declared in five
places (``path_models``, ``ml_features``, ``excel_export``, ``validate_data``,
``dtos``) and the digit-stream builder in three.  The copies happened to agree,
but nothing enforced that: a single edit to the prize structure would have
silently desynchronised the ML feature space from the path engine.

Everything that depends on "how an XSMB draw is shaped" now derives from
``FIELD_WIDTHS`` here.
"""

from typing import Final

import numpy as np
import pandas as pd

# (field name, zero-padded width) in canonical display order.
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

#: Number of two-digit lô tô values produced by one draw (one per prize field).
LOTO_DRAWS_PER_DAY: Final[int] = len(FIELD_WIDTHS)

#: Total positional digits in the flattened "rawdata" stream.
TOTAL_DIGITS: Final[int] = sum(width for _, width in FIELD_WIDTHS)

#: Uniform per-number probability for a single two-digit slot.
UNIFORM_TWO_DIGIT_RATE: Final[float] = 1.0 / 100.0

#: P(a given number 00..99 appears at least once in a draw) under independence.
#: Previously hardcoded as the literal ``1.0 - (0.99 ** 27)`` in two places.
LOTO_BASELINE_RATE: Final[float] = 1.0 - (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY

#: P(the special prize's last two digits equal a given number) under uniformity.
DE_BASELINE_RATE: Final[float] = UNIFORM_TWO_DIGIT_RATE


def baseline_rate(mode: str) -> float:
    """Return the no-information hit probability for ``mode``."""
    if mode == "de":
        return DE_BASELINE_RATE
    if mode == "loto":
        return LOTO_BASELINE_RATE
    raise ValueError("mode must be 'loto' or 'de'")


def build_position_labels() -> list[str]:
    """``['special.d0', ..., 'prize7_4.d1']`` — stable positional identifiers."""
    return [f"{field}.d{k}" for field, width in FIELD_WIDTHS for k in range(width)]


def raw_digit_matrix(df_raw: pd.DataFrame) -> np.ndarray:
    """Flatten every prize of every draw into a ``(n_days, TOTAL_DIGITS)`` digit array.

    Replaces the per-row ``iterrows`` + ``str().zfill()`` builders.  Digits are
    extracted arithmetically (``value // 10**k % 10``) instead of via string
    formatting, so the whole history is produced in a handful of vectorised
    operations rather than one Python call per draw.

    The output is ``uint8`` with values in ``0..9``, matching the old builders
    bit for bit.
    """
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
        # Left-to-right digit order, matching zfill(width).
        for k in range(width):
            power = 10 ** (width - 1 - k)
            out[:, offset + k] = (values // power % 10).astype(np.uint8)
        offset += width
    return out


def position_pairs(n_positions: int) -> tuple[np.ndarray, np.ndarray]:
    """Unique ordered index pairs ``i < j`` over the digit stream."""
    i, j = np.triu_indices(int(n_positions), k=1)
    return i.astype(np.int16), j.astype(np.int16)


def reverse_indices() -> np.ndarray:
    """``idx[x]`` is the digit-reversed partner of ``x`` (``12 -> 21``)."""
    numbers = np.arange(100, dtype=np.int16)
    return (10 * (numbers % 10) + numbers // 10).astype(np.int16)


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Consolidates three byte-identical private copies (``association_rules``,
    ``crosslag_positional_lab``, ``strategy_lab``).

    NOTE ON INDEPENDENCE: ``trials`` must be independent Bernoulli draws.  When
    a rule selects several numbers on the same draw day, those picks share the
    day's realised outcome and are *not* independent; aggregate to one
    observation per day (or use a day-block bootstrap) before calling this.
    """
    n = int(trials)
    if n <= 0:
        return float("nan"), float("nan")
    k = int(successes)
    if not 0 <= k <= n:
        raise ValueError("successes must be within 0..trials")
    p = k / n
    denominator = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * np.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return float((centre - margin) / denominator), float((centre + margin) / denominator)
