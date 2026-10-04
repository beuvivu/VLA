"""Neo mức tổng xác suất LOTO của tổ hợp: ``Σp = 100·nền``.

Mỗi kỳ có 27 giải, nên số con khác nhau về có kỳ vọng ``100·(1 − 0,99²⁷)``.
Walk-forward 1 000 kỳ đo hai nhánh cầu vị trí thổi tổng lên 24,49 và 26,47, và
tổ hợp trọng số mặc định kém dự báo hằng số z = −3,33 chỉ vì sai mức.
"""

from __future__ import annotations

import inspect
import json
import sys

import numpy as np
import pandas as pd
import pytest

import feature_attribution
import learn_ensemble_weights
import meta_predictor
import model_quality
import predict_nextday_2d
from ensemble_utils import anchor_loto_level, finalize_blend, floor_distribution
from xsmb_domain import LOTO_BASELINE_RATE

EXPECTED_SUM = 100 * LOTO_BASELINE_RATE


def test_anchor_sets_the_expected_distinct_count_and_keeps_every_ratio() -> None:
    raw = np.linspace(0.20, 0.32, 100)  # tổng 26 — thổi mức như nhánh stable
    out = anchor_loto_level(raw)
    assert out.sum() == pytest.approx(EXPECTED_SUM, abs=1e-12)
    np.testing.assert_allclose(out / out[0], raw / raw[0], rtol=1e-12)
    np.testing.assert_array_equal(np.argsort(out), np.argsort(raw))
    # Mức thấp cũng được nâng lên: sai mức theo chiều nào cũng là sai.
    assert anchor_loto_level(raw * 0.5).sum() == pytest.approx(EXPECTED_SUM, abs=1e-12)


def test_anchor_works_row_by_row_and_gives_an_empty_row_the_base_rate() -> None:
    rows = np.vstack([np.full(100, 0.30), np.zeros(100), np.linspace(0.1, 0.3, 100)])
    out = anchor_loto_level(rows)
    np.testing.assert_allclose(out.sum(axis=1), EXPECTED_SUM, atol=1e-12)
    np.testing.assert_allclose(out[1], LOTO_BASELINE_RATE)


@pytest.mark.parametrize(
    "raw",
    [
        np.r_[1.0, np.zeros(99)],  # hợp lệ với probability_component, dồn hết vào một con
        np.r_[0.9, np.full(99, 0.05)],  # nhân lên thì con đầu vượt 1
        np.r_[np.zeros(50), np.full(50, 0.3)],  # nửa số bằng 0
    ],
    ids=["one-hot", "one-dominant", "half-zero"],
)
def test_bounding_never_breaks_the_promised_sum(raw: np.ndarray) -> None:
    """Chặn biên sau khi nhân không được âm thầm phá tổng: ``[1, 0, …]`` từng ra 1,0001."""
    out = anchor_loto_level(raw)
    assert out.sum() == pytest.approx(EXPECTED_SUM, abs=1e-9)
    assert out.min() >= 1e-6 and out.max() <= 1 - 1e-6
    order = np.argsort(raw, kind="stable")
    assert np.all(np.diff(out[order]) >= -1e-15)  # thứ hạng giữ (không nghiêm ở chỗ chạm biên)
    np.testing.assert_allclose(anchor_loto_level(np.vstack([raw, raw]))[1], out)


def test_finalize_blend_is_the_floor_for_de_and_the_anchor_for_loto() -> None:
    raw = np.linspace(0.0, 0.02, 100)
    np.testing.assert_array_equal(finalize_blend(raw, "de"), floor_distribution(raw))
    np.testing.assert_array_equal(finalize_blend(raw * 20, "loto"), anchor_loto_level(raw * 20))
    with pytest.raises(ValueError):
        finalize_blend(raw, "xien")


def test_published_loto_forecast_carries_the_expected_distinct_count(tmp_path, monkeypatch) -> None:
    data, output = tmp_path / "data", tmp_path / "out"
    data.mkdir()
    pd.DataFrame({"date": ["2026-01-01"]}).to_csv(data / "xsmb.csv", index=False)
    levels = {
        "ml/predict_next_loto_ml_all.csv": 0.236,
        "ai_ml/cau_keo_loto_all.csv": 0.236,
        "statistical_signal/predict_next_loto_stat_all.csv": 0.237,
        "path_ui/predict_next_loto_active_2026-01-01_all.csv": 0.245,
        "path_ui/predict_next_loto_stable_2026-01-01_all.csv": 0.265,
    }
    for relative, level in levels.items():
        path = data / relative
        path.parent.mkdir(exist_ok=True)
        prob = np.full(100, level)
        prob[7] += 0.02  # một con nổi lên để thấy thứ hạng được giữ
        pd.DataFrame({"number": range(100), "prob": prob, "target_date": "2026-01-02"}).to_csv(path, index=False)
    monkeypatch.setattr(sys, "argv", ["predict_nextday_2d.py", "--mode", "loto", "--data-dir", str(data),
                                      "--models-dir", str(tmp_path / "models"), "--out-dir", str(output)])
    predict_nextday_2d.main()
    picks = json.loads((output / "picks_loto.json").read_text())
    assert all(picks["component_availability"].values())
    published = pd.read_csv(output / "predict_next_loto_all_2026-01-02.csv")
    assert published["prob"].sum() == pytest.approx(EXPECTED_SUM, abs=1e-9)
    assert int(published.iloc[0]["number"]) == 7


@pytest.mark.parametrize(
    "module",
    [predict_nextday_2d, learn_ensemble_weights, meta_predictor, model_quality, feature_attribution],
    ids=lambda m: m.__name__,
)
def test_every_scorer_of_the_blend_uses_the_production_finalizer(module) -> None:
    """Bộ học trọng số, tầng xếp chồng, trang Chất lượng và bảng đóng góp phải
    chấm ĐÚNG vector xuất bản — tự chép phép chốt là để chúng trôi khỏi nhau."""
    source = inspect.getsource(module)
    assert "finalize_blend(" in source
    assert 'floor_distribution(raw) if mode == "de" else clip01' not in source
    assert 'if mode == "de" else clip01(' not in source
