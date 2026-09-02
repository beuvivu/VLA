from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cau_keo_ml
from cau_keo_domain_challenger import ALL_DOMAIN_FEATURES, augment_domain_features
from cau_keo_ml import FEATURE_COLS, CauKeoConfig
from ml_features import FIELD_WIDTHS


class _FakeLottery:
    def __init__(self, raw: pd.DataFrame, two: pd.DataFrame) -> None:
        self.raw = raw
        self.two = two

    def load(self) -> None:
        return None

    def get_raw_data(self) -> pd.DataFrame:
        return self.raw.copy()

    def get_2_digits_data(self) -> pd.DataFrame:
        return self.two.copy()


def _history(days: int = 90) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    raw_rows: list[dict[str, object]] = []
    for t, day in enumerate(dates):
        row: dict[str, object] = {"date": day}
        for j, (field, width) in enumerate(FIELD_WIDTHS):
            row[field] = int((t * 97 + j * 31 + t * j) % (10**width))
        raw_rows.append(row)
    raw = pd.DataFrame(raw_rows)
    two = raw.copy()
    for field, _width in FIELD_WIDTHS:
        two[field] = two[field].astype(int) % 100
    return raw, two


def _build(
    monkeypatch,
    raw: pd.DataFrame,
    two: pd.DataFrame,
) -> pd.DataFrame:
    fake = _FakeLottery(raw, two)
    monkeypatch.setattr(cau_keo_ml, "Lottery", lambda: fake)
    x, y = cau_keo_ml.build_cau_keo_feature_frame(
        "loto",
        include_target=True,
        config=CauKeoConfig(
            min_history_days=20,
            lag_max_for_path_support=3,
            window_days=2000,
            top=10,
        ),
    )
    assert y is not None
    return augment_domain_features(x)


def test_future_result_mutation_cannot_change_earlier_features(monkeypatch) -> None:
    raw, two = _history()
    cutoff = pd.Timestamp("2026-02-25")
    before = _build(monkeypatch, raw, two)

    mutated_raw = raw.copy()
    mutated_two = two.copy()
    future = pd.to_datetime(mutated_raw["date"]) > cutoff
    # Replace every future draw with deliberately extreme but width-valid values.
    for j, (field, width) in enumerate(FIELD_WIDTHS):
        replacement = int((10**width - 1) - j) % (10**width)
        mutated_raw.loc[future, field] = replacement
        mutated_two.loc[future, field] = replacement % 100

    after = _build(monkeypatch, mutated_raw, mutated_two)
    cols = ["anchor_date", "number", *FEATURE_COLS, *ALL_DOMAIN_FEATURES]
    left = before[pd.to_datetime(before["anchor_date"]) <= cutoff][cols].reset_index(
        drop=True
    )
    right = after[pd.to_datetime(after["anchor_date"]) <= cutoff][cols].reset_index(
        drop=True
    )
    pd.testing.assert_frame_equal(left, right, check_exact=True)
