from __future__ import annotations

import pandas as pd

from cau_keo_ml import _add_ai_judgement, _bong_number, _score_band


def test_bong_number_modulo_5_transform_preserves_two_digit_range() -> None:
    assert _bong_number(0) == 55
    assert _bong_number(49) == 94
    assert _bong_number(95) == 40


def test_score_band_thresholds() -> None:
    assert _score_band(80) == "very_high"
    assert _score_band(60) == "high"
    assert _score_band(40) == "medium"
    assert _score_band(10) == "low"


def test_ai_judgement_adds_reason_and_probability_alias() -> None:
    df = pd.DataFrame(
        {
            "number_str": ["00", "01", "02"],
            "number": [0, 1, 2],
            "ml_prob_raw": [0.3, 0.1, 0.2],
            "path_support": [100, 20, 50],
            "cond_de_rate": [0.4, 0.05, 0.2],
            "cond_loto_max_rate": [0.35, 0.1, 0.2],
            "same_weekday_freq_364": [5, 0, 3],
            "reverse_hit_today": [1, 0, 0],
            "is_reverse_prev_special": [0, 0, 0],
            "is_bong_prev_special": [0, 0, 1],
            "cham_overlap_prev_special": [1, 0, 1],
            "gap": [8, 1, 4],
            "freq_30d": [9, 2, 5],
            "freq_7d": [3, 0, 1],
            "trend_7_vs_30": [1.5, -0.2, 0.5],
        }
    )
    out = _add_ai_judgement(df, mode="de")
    assert "cau_score" in out.columns
    assert "primary_reason" in out.columns
    assert "prob" in out.columns
    assert abs(float(out["prob"].sum()) - 1.0) < 1e-9
    assert out.iloc[0]["number_str"] == "00"
