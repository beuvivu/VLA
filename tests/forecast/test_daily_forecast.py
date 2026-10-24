"""Thẻ dự báo chỉ nhận đúng kỳ và xác suất đã công bố nguyên vẹn."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ANCHOR = "2026-10-16"
TARGET = "2026-10-17"


def _fixture(root: Path, *, target: str = TARGET) -> dict[str, np.ndarray]:
    pred = root / "forecast" / "predict"
    pred.mkdir(parents=True)
    de = np.full(100, 0.008)
    de[[7, 3, 24, 8, 92]] = [0.08, 0.06, 0.04, 0.03, 0.03]
    # Sai số nhỏ hợp lệ vẫn phải được giữ, không chuẩn hoá lại khi hiển thị.
    de *= 1.0 + 5e-9
    loto = np.full(100, 0.2)
    loto[[7, 3, 24, 8, 92]] = [0.42, 0.41, 0.4, 0.39, 0.38]
    for mode, probabilities in (("de", de), ("loto", loto)):
        (pred / f"picks_{mode}.json").write_text(json.dumps({
            "anchor_date": ANCHOR, "target_date": target,
        }), encoding="utf-8")
        pd.DataFrame({"number": range(100), "prob": probabilities}).sample(
            frac=1, random_state=4
        ).to_csv(pred / f"predict_next_{mode}_all_{target}.csv", index=False)
    return {"de": de, "loto": loto}


def _load(root: Path, anchor: str = ANCHOR):
    from forecast.daily_forecast import load_daily_forecast

    return load_daily_forecast(root, anchor)


def test_loads_five_ranked_numbers_and_preserves_published_probabilities(tmp_path: Path) -> None:
    expected = _fixture(tmp_path)
    result = _load(tmp_path)
    assert result is not None
    assert (result["anchor_date"], result["target_date"]) == (ANCHOR, TARGET)
    for mode in ("de", "loto"):
        picks = result["groups"][mode]
        assert [pick["number"] for pick in picks] == ["07", "03", "24", "08", "92"]
        assert [pick["prob"] for pick in picks] == [expected[mode][n] for n in [7, 3, 24, 8, 92]]


def test_loto_keeps_at_most_three_numbers_per_tail_without_changing_probabilities(tmp_path: Path) -> None:
    _fixture(tmp_path)
    probs = np.full(100, 0.2)
    probs[[4, 14, 24, 34, 44, 0, 1]] = [0.4, 0.39, 0.38, 0.37, 0.36, 0.35, 0.34]
    pd.DataFrame({"number": range(100), "prob": probs}).to_csv(
        tmp_path / "forecast" / "predict" / f"predict_next_loto_all_{TARGET}.csv", index=False
    )
    result = _load(tmp_path)
    assert result is not None
    picks = result["groups"]["loto"]
    assert [p["number"] for p in picks] == ["04", "14", "24", "00", "01"]
    assert [p["prob"] for p in picks] == [0.4, 0.39, 0.38, 0.35, 0.34]


def test_next_draw_skips_non_draw_dates_from_the_supplied_data_directory(tmp_path: Path) -> None:
    _fixture(tmp_path, target="2026-10-19")
    (tmp_path / "non_draw_days.json").write_text(json.dumps({
        "ngay_khong_quay": ["2026-10-17", "2026-10-18"],
    }), encoding="utf-8")
    result = _load(tmp_path)
    assert result is not None and result["target_date"] == "2026-10-19"


@pytest.mark.parametrize("modes,key,value", [
    (("de",), "anchor_date", "2026-10-15"),
    (("de", "loto"), "anchor_date", "2026-10-15"),
    (("loto",), "target_date", "2026-10-18"),
    (("de", "loto"), "target_date", "2026-10-18"),
    (("de",), "anchor_date", None),
    (("loto",), "target_date", "../2026-10-17"),
])
def test_rejects_stale_or_mismatched_metadata(tmp_path: Path, modes, key, value) -> None:
    _fixture(tmp_path)
    for mode in modes:
        path = tmp_path / "forecast" / "predict" / f"picks_{mode}.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata[key] = value
        path.write_text(json.dumps(metadata), encoding="utf-8")
    assert _load(tmp_path) is None


@pytest.mark.parametrize("defect", [
    "missing_row", "extra_row", "duplicate", "fractional", "outside_universe",
    "number_nan", "negative", "over_one", "prob_nan", "prob_inf", "zero",
    "missing_column", "de_sum", "loto_sum", "stale_csv_target", "stale_csv_anchor",
])
def test_rejects_invalid_probability_artifacts(tmp_path: Path, defect: str) -> None:
    _fixture(tmp_path)
    mode = "loto" if defect == "loto_sum" else "de"
    path = tmp_path / "forecast" / "predict" / f"predict_next_{mode}_all_{TARGET}.csv"
    frame = pd.read_csv(path)
    if defect == "missing_row":
        frame = frame.iloc[:-1]
    elif defect == "extra_row":
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    elif defect == "duplicate":
        frame.loc[0, "number"] = frame.loc[1, "number"]
    elif defect in {"fractional", "outside_universe", "number_nan"}:
        frame["number"] = frame["number"].astype(float)
        frame.loc[0, "number"] = {"fractional": 0.5, "outside_universe": 100, "number_nan": np.nan}[defect]
    elif defect in {"negative", "over_one", "prob_nan", "prob_inf"}:
        frame.loc[0, "prob"] = {"negative": -0.01, "over_one": 1.01, "prob_nan": np.nan, "prob_inf": np.inf}[defect]
    elif defect in {"zero", "de_sum", "loto_sum"}:
        frame["prob"] = {"zero": 0.0, "de_sum": 0.02, "loto_sum": 0.5}[defect]
    elif defect == "missing_column":
        frame = frame.drop(columns="prob")
    else:
        frame["target_date" if defect == "stale_csv_target" else "anchor_date"] = "2026-10-15"
    frame.to_csv(path, index=False)
    assert _load(tmp_path) is None


@pytest.mark.parametrize("file,contents", [
    ("picks_de.json", None), ("picks_loto.json", "{"),
    ("picks_de.json", "[]"), ("picks_loto.json", "null"),
    (f"predict_next_de_all_{TARGET}.csv", None),
    (f"predict_next_loto_all_{TARGET}.csv", ""),
    (f"predict_next_loto_all_{TARGET}.csv", 'number,prob\n"broken'),
])
def test_missing_or_malformed_files_leave_the_card_pending(tmp_path: Path, file: str, contents) -> None:
    _fixture(tmp_path)
    path = tmp_path / "forecast" / "predict" / file
    if contents is None:
        path.unlink()
    else:
        path.write_text(contents, encoding="utf-8")
    assert _load(tmp_path) is None


@pytest.mark.parametrize("anchor", ["", "not-a-date", "2026-10-32", "2026-10-16T00:00:00"])
def test_invalid_displayed_anchor_leaves_the_card_pending(tmp_path: Path, anchor: str) -> None:
    _fixture(tmp_path)
    assert _load(tmp_path, anchor) is None
