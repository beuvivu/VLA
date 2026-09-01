from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy_lab import evaluate_lab


def _frames(days: int = 120) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    data: dict[str, object] = {"date": dates}
    for j in range(27):
        data[f"p{j}"] = (np.arange(days) * (j + 3) + 7 * j) % 100
    two = pd.DataFrame(data)
    # The strategy lab requires the special prize as the first value column.
    two = two.rename(columns={"p0": "special", "p1": "prize1"})

    sparse = pd.DataFrame(0, index=np.arange(days), columns=["date", *range(100)])
    sparse["date"] = dates
    vals = two.drop(columns=["date"]).to_numpy(dtype=int) % 100
    for i, row in enumerate(vals):
        for n in np.unique(row):
            sparse.loc[i, int(n)] = 1
    return two, sparse


def test_strategy_lab_runs_only_on_verified_daily_calendar() -> None:
    two, sparse = _frames()
    table, agreement, diversity = evaluate_lab(
        two, sparse, mode="loto", warmup=30, holdout_fraction=0.25
    )
    assert len(table) == 20
    assert table["calendar_contiguous"].all()
    assert not agreement.empty
    assert len(diversity) == 20 * 19 // 2


def test_strategy_lab_rejects_missing_day() -> None:
    two, sparse = _frames()
    two = two.drop(index=60).reset_index(drop=True)
    sparse = sparse.drop(index=60).reset_index(drop=True)
    with pytest.raises(ValueError, match="requires contiguous calendar days"):
        evaluate_lab(two, sparse, mode="loto", warmup=30)


def test_strategy_lab_rejects_misaligned_date_axes() -> None:
    two, sparse = _frames()
    sparse.loc[60, "date"] = pd.Timestamp("2027-01-01")
    sparse = sparse.sort_values("date").reset_index(drop=True)
    with pytest.raises(ValueError):
        evaluate_lab(two, sparse, mode="de", warmup=30)
