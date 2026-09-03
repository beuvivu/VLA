from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import cau_keo_ml
from cau_keo_feature_groups import ALL_DOMAIN_FEATURES, augment_domain_features
from cau_keo_ml import FEATURE_COLS, CauKeoConfig
from ml_features import FIELD_WIDTHS


class _FakeLottery:
    def __init__(self, raw: pd.DataFrame, two_digits: pd.DataFrame) -> None:
        self.raw = raw
        self.two_digits = two_digits

    def load(self) -> None:
        return None

    def get_raw_data(self) -> pd.DataFrame:
        return self.raw.copy()

    def get_2_digits_data(self) -> pd.DataFrame:
        return self.two_digits.copy()


def _history(days: int = 90) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    rows: list[dict[str, object]] = []
    for offset, day in enumerate(dates):
        row: dict[str, object] = {"date": day}
        for position, (field, width) in enumerate(FIELD_WIDTHS):
            row[field] = int(
                (offset * 97 + position * 31 + offset * position) % (10**width)
            )
        rows.append(row)
    raw = pd.DataFrame(rows)
    two_digits = raw.copy()
    for field, _width in FIELD_WIDTHS:
        two_digits[field] = two_digits[field].astype(int) % 100
    return raw, two_digits


def _build(
    monkeypatch: pytest.MonkeyPatch,
    raw: pd.DataFrame,
    two_digits: pd.DataFrame,
    mode: str,
) -> pd.DataFrame:
    fake = _FakeLottery(raw, two_digits)
    monkeypatch.setattr(cau_keo_ml, "Lottery", lambda: fake)
    frame, target = cau_keo_ml.build_cau_keo_feature_frame(
        mode,  # type: ignore[arg-type]
        include_target=True,
        config=CauKeoConfig(
            min_history_days=20,
            lag_max_for_path_support=3,
            window_days=2_000,
            top=10,
        ),
    )
    assert target is not None
    return augment_domain_features(frame)


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_future_result_mutation_cannot_change_earlier_domain_features(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    raw, two_digits = _history()
    cutoff = pd.Timestamp("2026-02-25")
    before = _build(monkeypatch, raw, two_digits, mode)

    mutated_raw = raw.copy()
    future = pd.to_datetime(mutated_raw["date"]) > cutoff
    for position, (field, width) in enumerate(FIELD_WIDTHS):
        replacement = int((10**width - 1) - position) % (10**width)
        mutated_raw.loc[future, field] = replacement
    mutated_two_digits = mutated_raw.copy()
    for field, _width in FIELD_WIDTHS:
        mutated_two_digits[field] = mutated_two_digits[field].astype(int) % 100

    after = _build(monkeypatch, mutated_raw, mutated_two_digits, mode)
    columns = ["anchor_date", "number", *FEATURE_COLS, *ALL_DOMAIN_FEATURES]
    left = before[pd.to_datetime(before["anchor_date"]) <= cutoff][columns]
    right = after[pd.to_datetime(after["anchor_date"]) <= cutoff][columns]
    left = left.sort_values(["anchor_date", "number"]).reset_index(drop=True)
    right = right.sort_values(["anchor_date", "number"]).reset_index(drop=True)

    pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=True)
