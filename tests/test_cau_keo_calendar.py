from __future__ import annotations

import pandas as pd
import pytest

import cau_keo_ml
from cau_keo_ml import CauKeoConfig, build_cau_keo_feature_frame


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


def _frames(dates: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    dt = pd.to_datetime(dates)
    # The calendar guards execute before raw path-digit extraction.  Still use
    # realistic prize-column names so the fixture documents the expected shape.
    data: dict[str, object] = {
        "date": dt,
        "special": [10000 + i for i in range(len(dt))],
        "prize1": [20000 + i for i in range(len(dt))],
    }
    for j in range(1, 3):
        data[f"prize2_{j}"] = [30000 + 10 * j + i for i in range(len(dt))]
    for j in range(1, 7):
        data[f"prize3_{j}"] = [40000 + 10 * j + i for i in range(len(dt))]
    for j in range(1, 5):
        data[f"prize4_{j}"] = [1000 + 10 * j + i for i in range(len(dt))]
    for j in range(1, 7):
        data[f"prize5_{j}"] = [2000 + 10 * j + i for i in range(len(dt))]
    for j in range(1, 4):
        data[f"prize6_{j}"] = [100 + 10 * j + i for i in range(len(dt))]
    for j in range(1, 5):
        data[f"prize7_{j}"] = [10 + j + i for i in range(len(dt))]
    raw = pd.DataFrame(data)
    two = raw.copy()
    value_cols = [c for c in two.columns if c != "date"]
    two[value_cols] = two[value_cols] % 100
    return raw, two


def _install_fake(monkeypatch: pytest.MonkeyPatch, raw: pd.DataFrame, two: pd.DataFrame) -> None:
    monkeypatch.setattr(cau_keo_ml, "Lottery", lambda: _FakeLottery(raw, two))


def test_cau_keo_rejects_missing_calendar_day(monkeypatch: pytest.MonkeyPatch) -> None:
    raw, two = _frames(["2026-08-01", "2026-08-02", "2026-08-04", "2026-08-05"])
    _install_fake(monkeypatch, raw, two)
    with pytest.raises(ValueError, match="requires contiguous calendar days"):
        build_cau_keo_feature_frame(
            "loto",
            include_target=False,
            config=CauKeoConfig(min_history_days=1),
        )


def test_cau_keo_rejects_raw_two_date_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    raw, two = _frames(["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"])
    raw["date"] = pd.date_range("2026-08-02", periods=4, freq="D")
    _install_fake(monkeypatch, raw, two)
    with pytest.raises(ValueError, match="not date-aligned"):
        build_cau_keo_feature_frame(
            "de",
            include_target=False,
            config=CauKeoConfig(min_history_days=1),
        )


def test_cau_keo_rejects_duplicate_calendar_date(monkeypatch: pytest.MonkeyPatch) -> None:
    raw, two = _frames(["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"])
    raw.loc[3, "date"] = pd.Timestamp("2026-08-03")
    two.loc[3, "date"] = pd.Timestamp("2026-08-03")
    _install_fake(monkeypatch, raw, two)
    with pytest.raises(ValueError, match="duplicates"):
        build_cau_keo_feature_frame(
            "loto",
            include_target=False,
            config=CauKeoConfig(min_history_days=1),
        )
