from __future__ import annotations

import pandas as pd
import pytest

from soi_cau.cau_position_evidence import _pretty_position_label, _rule_score, _summary_text


def test_pretty_position_label_is_user_friendly() -> None:
    assert _pretty_position_label("special.d0") == "Giải Đặc Biệt · số 1"
    assert _pretty_position_label("prize3_2.d4") == "Giải ba 2 · số 5"


def test_rule_score_and_summary_text_are_explainable() -> None:
    row = pd.Series(
        {
            "p_mean": 0.25,
            "hits": 20,
            "trials": 80,
            "current_streak": 3,
            "max_streak": 5,
            "special_touch": 1,
            "special_both": 0,
        }
    )
    assert _rule_score(row) > 0
    text = _summary_text("00", 42.0, 12.3, "ML xác suất cao", ["L1: Giải Đặc Biệt · số 1(0) + Giải nhất · số 2(0) → 00"], 1)
    assert "Số 00" in text
    assert "đường cầu" in text


def test_reason_prints_the_shrunk_next_draw_probability_not_the_in_sample_rate() -> None:
    from soi_cau.cau_position_evidence import _row_reason

    row = {"hits": 117, "trials": 361, "p_mean": 0.3242, "current_streak": 4, "max_streak": 6,
           "p_post": 0.2376, "streak_shift": 0.0010}
    active = _row_reason(pd.Series({**row, "rule_kind": "active"}))
    stable = _row_reason(pd.Series({**row, "rule_kind": "stable"}))
    assert active == ("Cầu đang chạy 4 nhịp; trúng 117/361 kỳ trong cửa sổ; dự báo kỳ tới 23,86% "
                      "theo kinh nghiệm mọi đường cầu.")
    assert stable == ("Cầu bền: chuỗi dài nhất 6; trúng 117/361 kỳ trong cửa sổ; dự báo kỳ tới 23,76% "
                      "theo kinh nghiệm mọi đường cầu.")
    assert "0.324" not in active and "32,4" not in active
    legacy = _row_reason(pd.Series({k: v for k, v in row.items() if k not in {"p_post", "streak_shift"}}
                                   | {"rule_kind": "stable"}))
    assert "dự báo" not in legacy


def test_next_probability_stays_a_probability_at_the_edges() -> None:
    from soi_cau.cau_position_evidence import _next_probability

    high = _next_probability(pd.Series({"p_post": 0.999, "streak_shift": 0.01, "rule_kind": "active"}))
    low = _next_probability(pd.Series({"p_post": 0.001, "streak_shift": -0.01, "rule_kind": "active"}))
    assert high == pytest.approx(1 - 1e-6)
    assert low == pytest.approx(1e-6)
    # Cầu bền không cộng kinh nghiệm chuỗi.
    assert _next_probability(pd.Series({"p_post": 0.3, "streak_shift": 0.5, "rule_kind": "stable"})) == 0.3
