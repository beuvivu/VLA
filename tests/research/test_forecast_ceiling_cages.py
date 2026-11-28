from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.xsmb_domain import FIELD_WIDTHS

ROOT = Path(__file__).resolve().parents[2]


def _script():
    path = ROOT / "scripts" / "research" / "audit_forecast_ceiling.py"
    spec = importlib.util.spec_from_file_location("audit_forecast_ceiling", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _history(days: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = {"date": pd.date_range("2022-01-01", periods=days).strftime("%Y-%m-%d")}
    for name, width in FIELD_WIDTHS:
        frame[name] = [f"{value:0{width}d}" for value in rng.integers(0, 10**width, size=days)]
    return pd.DataFrame(frame)


def test_cage_counts_pool_every_prize_by_place_value() -> None:
    audit = _script()
    frame = pd.DataFrame({"date": ["2024-01-01"], **{name: ["7" * width] for name, width in FIELD_WIDTHS}})
    frame["special"] = ["12345"]
    table = audit.cage_counts(frame)
    assert table.sum(axis=1).tolist() == [27, 27, 23, 20, 10]
    assert table[0, 5] == 1 and table[0, 7] == 26
    assert table[4, 1] == 1 and table[4, 7] == 9
    frame["prize7_1"] = ["3"]
    assert audit.cage_counts(frame)[1, 0] == 1


def test_a_fair_history_has_no_flagged_quarter_and_uniform_p_values() -> None:
    audit = _script()
    report = audit.cage_windows(_history(1095, seed=1))
    assert report["cells"] == 12 * 5
    assert report["q_below_005"] == 0 and report["min_p_bonferroni"] > 0.05
    assert report["uniformity_ks_p"] > 0.01
    assert report["expected_below_001"] == pytest.approx(0.6)


def test_a_quarter_with_one_overdrawn_units_digit_is_flagged_after_correction() -> None:
    audit = _script()
    raw = _history(1095, seed=2)
    rng = np.random.default_rng(3)
    in_quarter = raw["date"].str.startswith(("2023-04", "2023-05", "2023-06"))
    for name, _width in FIELD_WIDTHS:
        swap = in_quarter & (rng.random(len(raw)) < 0.06)
        raw.loc[swap, name] = raw.loc[swap, name].str[:-1] + "2"
    report = audit.cage_windows(raw)
    worst = report["most_extreme"][0]
    assert (worst["quarter"], worst["cage"]) == ("2023Q2", "đơn vị")
    assert worst["q_value"] < 0.05 and report["q_below_005"] >= 1 and report["min_p_bonferroni"] < 0.05
    assert int(np.argmax(worst["counts"])) == 2
    others = [row for row in report["most_extreme"] if row["quarter"] == "2023Q2" and row["cage"] != "đơn vị"]
    assert all(row["q_value"] > 0.05 for row in others)


def test_short_quarters_are_skipped_and_an_empty_history_reports_no_cells() -> None:
    audit = _script()
    assert audit.cage_windows(_history(20, seed=4)) == {"cells": 0}
    report = audit.cage_windows(_history(100, seed=5))
    assert report["cells"] == 5


def test_the_committed_report_carries_the_scan_of_the_committed_history() -> None:
    audit = _script()
    import json

    saved = json.loads((ROOT / "data" / "research" / "model_overhaul" / "forecast_ceiling.json").read_text("utf-8"))
    raw = pd.read_csv(ROOT / "data" / "xsmb.csv", dtype=str).sort_values("date", kind="stable").head(saved["draws"])
    fresh = audit.cage_windows(raw)
    assert fresh["cells"] == saved["cage_windows"]["cells"]
    assert fresh["min_p"] == pytest.approx(saved["cage_windows"]["min_p"], rel=1e-9)
    assert fresh["most_extreme"][0]["counts"] == saved["cage_windows"]["most_extreme"][0]["counts"]
