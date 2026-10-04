from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml_train import _recency_weights, _time_splits


def test_recency_weights_accept_series_and_favor_recent_rows() -> None:
    dates = pd.Series(pd.date_range("2026-01-01", periods=5, freq="D"))
    weights = _recency_weights(dates, half_life_days=2.0)
    assert len(weights) == 5
    assert np.all(np.diff(weights) > 0)
    assert np.isclose(weights.mean(), 1.0)


def test_temporal_split_has_untouched_final_validation_block() -> None:
    days = pd.date_range("2025-01-01", periods=200, freq="D")
    cal, select, val = _time_splits(days)
    assert cal < select < val < days[-1]
    assert (days >= val).sum() == 45


def test_a_model_without_validated_skill_gets_no_trust() -> None:
    """Không có kỹ năng thẩm định thì thành phần ML phát đúng tỉ lệ nền.

    Sàn 0,35 cũ trộn 35% mô hình thô ngay cả khi kỹ năng bằng 0; walk-forward
    997 kỳ đo nó làm LOTO kém hằng số (z = −2,40).
    """
    from ml_train import model_trust

    assert model_trust(0.0, 0.0) == 0.0
    assert model_trust(-0.01, 0.02) == 0.0  # kém hơn trong hai thước đo quyết định
    assert model_trust(0.02, -0.001) == 0.0
    assert model_trust(0.01, 0.02) == pytest.approx(0.2)
    assert model_trust(0.05, 0.08) == 1.0
    grid = [model_trust(s, s) for s in (0.0, 0.001, 0.01, 0.03, 0.06)]
    assert grid == sorted(grid)


def test_ml_rankings_stay_meaningful_when_every_probability_is_the_baseline() -> None:
    from ml_predict import rank_predictions

    # trust = 0: mọi prob bằng nền; xác suất thô tăng theo số nên thứ tự chỉ
    # theo prob (hoặc theo chỉ mục) sẽ đặt 00 lên đầu thay vì 99.
    df = pd.DataFrame({"number": [f"{i:02d}" for i in range(100)], "prob": 0.27,
                       "raw_model_prob": [0.2 + i / 1000 for i in range(100)]})
    ranked = rank_predictions(df)
    assert ranked["number"].head(3).tolist() == ["99", "98", "97"]
    # prob vẫn là tiêu chí chính.
    df.loc[5, "prob"] = 0.30
    assert rank_predictions(df)["number"].iloc[0] == "05"


def test_ml_predictions_record_which_trust_policy_produced_them(tmp_path, monkeypatch) -> None:
    """Tệp dự báo ghi phiên bản luật trust, để trang bằng chứng nhận ra tệp cũ."""
    import sys

    import ml_predict
    from ml_train import TRUST_POLICY_VERSION

    pack = {"features": ["f"], "model": object(), "model_trust": 0.0, "baseline_prob": 0.27,
            "quality_pass": False, "trust_policy_version": TRUST_POLICY_VERSION}
    monkeypatch.setattr(ml_predict, "_latest_data_date", lambda: "2026-10-03")
    monkeypatch.setattr(ml_predict, "_load_or_train_model", lambda *a, **k: pack)
    monkeypatch.setattr(ml_predict, "build_features_for_prediction",
                        lambda **k: ("2026-10-03", pd.DataFrame({"f": range(100)})))
    monkeypatch.setattr(ml_predict, "predict_with_feature_allowlist",
                        lambda model, X, cols: np.linspace(0.2, 0.3, 100))
    monkeypatch.setattr(sys, "argv", ["ml_predict.py", "--out-dir", str(tmp_path), "--models-dir", str(tmp_path)])
    ml_predict.main()
    for mode in ("loto", "de"):
        frame = pd.read_csv(tmp_path / f"predict_next_{mode}_ml_all.csv")
        assert set(frame["trust_policy_version"]) == {TRUST_POLICY_VERSION}
        assert (frame["model_trust"] == 0.0).all()
