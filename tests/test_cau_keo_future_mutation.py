from __future__ import annotations

import pandas as pd
import pytest

import cau_keo_ml
from cau_keo_feature_groups import ALL_DOMAIN_FEATURES, augment_domain_features
from cau_keo_ml import FEATURE_COLS, CauKeoConfig, build_cau_keo_feature_frame
from ml_features import FIELD_WIDTHS


class _FakeLottery:
    def __init__(self, raw: pd.DataFrame, two: pd.DataFrame) -> None:
        self._raw = raw
        self._two = two

    def load(self) -> None:
        return None

    def get_raw_data(self) -> pd.DataFrame:
        return self._raw.copy()

    def get_2_digits_data(self) -> pd.DataFrame:
        return self._two.copy()


def _history(days: int = 90) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    data: dict[str, object] = {"date": dates}
    for position, (field, width) in enumerate(FIELD_WIDTHS):
        modulus = 10**width
        base = (position + 1) * 977
        data[field] = [int((base + 131 * i + 17 * position) % modulus) for i in range(days)]
    raw = pd.DataFrame(data)
    two = raw.copy()
    value_cols = [c for c in two.columns if c != "date"]
    two[value_cols] = two[value_cols] % 100
    return raw, two


def _mutate_strict_future(raw: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    changed = raw.copy()
    mask = pd.to_datetime(changed["date"]) > cutoff
    for position, (field, width) in enumerate(FIELD_WIDTHS):
        modulus = 10**width
        changed.loc[mask, field] = (
            changed.loc[mask, field].astype(int) + 123 + 19 * position
        ) % modulus
    two = changed.copy()
    value_cols = [c for c in two.columns if c != "date"]
    two[value_cols] = two[value_cols] % 100
    return changed, two


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_future_result_mutation_cannot_change_earlier_features(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    raw, two = _history()
    holder = {"raw": raw, "two": two}
    monkeypatch.setattr(
        cau_keo_ml,
        "Lottery",
        lambda: _FakeLottery(holder["raw"], holder["two"]),
    )
    config = CauKeoConfig(min_history_days=5, window_days=0, lag_max_for_path_support=12)

    before, _ = build_cau_keo_feature_frame(
        mode, include_target=True, config=config  # type: ignore[arg-type]
    )
    before = augment_domain_features(before)

    cutoff = pd.Timestamp("2026-02-25")
    future_raw, future_two = _mutate_strict_future(raw, cutoff)
    holder["raw"] = future_raw
    holder["two"] = future_two

    after, _ = build_cau_keo_feature_frame(
        mode, include_target=True, config=config  # type: ignore[arg-type]
    )
    after = augment_domain_features(after)

    columns = ["anchor_date", "number", *FEATURE_COLS, *ALL_DOMAIN_FEATURES]
    left = before[pd.to_datetime(before["anchor_date"]) <= cutoff][columns]
    right = after[pd.to_datetime(after["anchor_date"]) <= cutoff][columns]
    left = left.sort_values(["anchor_date", "number"]).reset_index(drop=True)
    right = right.sort_values(["anchor_date", "number"]).reset_index(drop=True)

    pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=True)
