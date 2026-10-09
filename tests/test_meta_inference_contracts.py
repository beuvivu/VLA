from __future__ import annotations

import json
import pickle
import sys
from datetime import date

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier

import meta_predictor as meta
import predict_nextday_2d as predictor
from ensemble_components import COMPONENT_POLICY, policy_column
from ensemble_utils import anchor_loto_level
from xsmb_domain import LOTO_BASELINE_RATE


def _history() -> pd.DataFrame:
    frame = pd.DataFrame({"target_date": ["2026-01-01"] * 100, "number": range(100)})
    frame["y"] = 0
    frame.loc[0, "y"] = 1
    for key in ("ml", "cau", "stat", "active", "stable"):
        frame[f"p_{key}"] = 0.01
        frame[f"has_{key}"] = True
    frame[policy_column("cau")] = COMPONENT_POLICY["cau"]
    return frame


@pytest.mark.parametrize("defect", ["flag", "zeros", "negative", "duplicate", "infinite_label", "fractional_label"])
def test_invalid_component_history_never_matures(defect: str) -> None:
    frame = _history()
    if defect == "flag":
        frame["has_ml"] = False
    elif defect == "zeros":
        frame["p_ml"] = 0.0
    elif defect == "negative":
        frame.loc[0, "p_ml"] = -0.1
    elif defect == "duplicate":
        frame.loc[0, "number"] = 1
    elif defect == "infinite_label":
        frame["y"] = frame["y"].astype(float)
        frame.loc[0, "y"] = np.inf
    else:
        frame["y"] = frame["y"].astype(float)
        frame.loc[0, "y"] = 0.5
    assert meta._complete_days_for_components(frame, ["p_ml"], 100) == []


@pytest.mark.parametrize("positives", [0, 2])
def test_de_history_requires_one_winner(positives: int) -> None:
    frame = _history()
    frame["y"] = 0
    frame.loc[:positives - 1, "y"] = 1
    assert meta._complete_days_for_components(frame, ["p_ml"], 100, mode="de") == []


def _pack() -> dict:
    columns = ["p_ml", "p_active", "p_stable"]
    features = meta.meta_feature_columns(columns)
    model = DummyClassifier(strategy="prior").fit(
        np.zeros((10, len(features))), [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    )
    return {
        "schema_version": meta.META_SCHEMA_VERSION,
        "mode": "loto",
        "model": model,
        "features": features,
        "component_cols": columns,
        "quality_pass": True,
        "meta_trust": 0.15,
        "trained_through_target_date": "2026-01-01",
    }


@pytest.mark.parametrize("last_day", [None, 0, 12345, "not-a-date", "2026-01-02", "2026-01-03"])
def test_meta_rejects_missing_or_nonpast_training_date(last_day: object) -> None:
    pack = _pack()
    pack["trained_through_target_date"] = last_day
    vector = np.full(100, 0.1)
    with pytest.raises(ValueError, match="date|ngày|thời"):
        meta.predict_meta(pack, "loto", "2026-01-02", *(vector for _ in range(5)))


def test_past_model_predicts_with_its_available_tier() -> None:
    vector = np.full(100, 0.1)
    absent = np.zeros(100)
    prediction = meta.predict_meta(_pack(), "loto", "2026-01-02", vector, absent, absent, vector, vector)
    np.testing.assert_allclose(prediction, 0.2)
    assert prediction.sum() == pytest.approx(20.0)


def test_production_uses_three_component_model_when_unused_components_are_missing(tmp_path, monkeypatch) -> None:
    data = tmp_path / "data"
    models = tmp_path / "models"
    output = tmp_path / "output"
    data.mkdir()
    models.mkdir()
    pd.DataFrame({"date": ["2026-01-01"]}).to_csv(data / "xsmb.csv", index=False)
    for relative in ("ml/predict_next_loto_ml_all.csv", "path_ui/predict_next_loto_active_2026-01-01_all.csv", "path_ui/predict_next_loto_stable_2026-01-01_all.csv"):
        path = data / relative
        path.parent.mkdir(exist_ok=True)
        pd.DataFrame({"number": range(100), "prob": 0.1, "target_date": "2026-01-02"}).to_csv(path, index=False)
    joblib.dump(_pack(), models / "meta_loto.joblib")
    monkeypatch.setattr(sys, "argv", ["predict_nextday_2d.py", "--mode", "loto", "--data-dir", str(data), "--models-dir", str(models), "--out-dir", str(output)])
    predictor.main()
    picks = json.loads((output / "picks_loto.json").read_text())
    assert picks["meta"]["active"] is True
    assert picks["calibration"]["active"] is False
    published = pd.read_csv(output / "predict_next_loto_all_2026-01-02.csv")
    # Tổ hợp tuyến tính được neo tổng về 100·nền trước khi trộn 15% mô hình
    # xếp chồng (phát đúng tỉ lệ tiên nghiệm 0,2 của bộ phân loại giả).
    np.testing.assert_allclose(published["prob"], 0.85 * LOTO_BASELINE_RATE + 0.15 * 0.2)


def test_required_component_missing_keeps_linear_forecast(tmp_path) -> None:
    joblib.dump(_pack(), tmp_path / "meta_loto.joblib")
    vector = np.full(100, 0.1)
    prediction, trust, info = predictor._meta_prediction(
        tmp_path, "loto", date(2026, 1, 2), vector, vector, vector, vector, vector,
        vector, available={"ml": True, "active": False, "stable": True},
    )
    np.testing.assert_array_equal(prediction, vector)
    assert trust == 0.0
    assert info["active"] is False


@pytest.mark.parametrize("error", [None, pickle.UnpicklingError("private-pack-contents")])
def test_corrupt_meta_serialization_keeps_linear_vector_without_private_reason(tmp_path, monkeypatch, error):
    (tmp_path / "meta_loto.joblib").write_bytes(b"not-a-valid-joblib")
    if error is not None:
        def invalid_load(*args):
            raise error

        monkeypatch.setattr(joblib, "load", invalid_load)
    vector = np.full(100, 0.2)
    prediction, trust, info = predictor._meta_prediction(
        tmp_path, "loto", date(2026, 1, 2), *([vector] * 6)
    )
    np.testing.assert_array_equal(prediction, vector)
    assert trust == 0.0 and info["active"] is False
    assert "private-pack-contents" not in info["reason"]


def test_meta_baseline_replays_default_weights_and_categorical_floor() -> None:
    rows = []
    for day in range(1, 13):
        frame = _history()
        frame["target_date"] = f"2026-01-{day:02d}"
        for index, key in enumerate(("ml", "cau", "stat", "active", "stable")):
            frame[f"p_{key}"] = 0.0
            frame.loc[index, f"p_{key}"] = 1.0
        rows.append(frame)
    history = pd.concat(rows, ignore_index=True)
    prediction, _, _ = meta._baseline_validation(
        history, [f"2026-01-{day:02d}" for day in range(1, 11)],
        ["2026-01-11", "2026-01-12"], "de", meta.COMPONENT_COLS, 45,
    )
    # Mười kỳ chưa đủ học trọng số: mặc định 0,25/0,30/0,20/0,125/0,125;
    # production dành 5% khối lượng cho phân phối đều trước hiệu chuẩn.
    expected = np.full(100, 0.0005)
    expected[:5] = [0.238, 0.2855, 0.1905, 0.11925, 0.11925]
    np.testing.assert_allclose(prediction, np.tile(expected, (2, 1)), rtol=1e-12)


def test_meta_baseline_respects_each_validation_days_available_components() -> None:
    frame = _history()
    frame["p_ml"] = 0.1
    frame.loc[0, "p_ml"] = 0.3
    frame["p_active"] = 0.2
    frame.loc[1, "p_active"] = 0.4
    frame["p_stable"] = 0.24
    frame["has_cau"] = False
    frame["has_stat"] = False
    frame["p_cau"] = 0.0
    frame["p_stat"] = 0.0
    train = frame.copy()
    frame["target_date"] = "2026-01-02"
    history = pd.concat([train, frame], ignore_index=True)
    prediction, _, _ = meta._baseline_validation(
        history, ["2026-01-01"], ["2026-01-02"], "loto",
        ["p_ml", "p_active", "p_stable"], 45,
    )
    # Trọng số mặc định có hiệu lực là 0,50/0,25/0,25, không phải 1/3: con 00
    # nhận 0,26, con 01 nhận 0,21, còn lại 0,16 — rồi neo tổng về 100·nền. Với
    # 1/3, con 00 và 01 bằng nhau nên tỉ lệ giữa chúng phân biệt hai cách.
    expected = np.full(100, 0.16)
    expected[:2] = [0.26, 0.21]
    np.testing.assert_allclose(prediction, anchor_loto_level(expected)[None, :], rtol=1e-12)
