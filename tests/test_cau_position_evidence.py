from __future__ import annotations

import pandas as pd

from cau_position_evidence import _pretty_position_label, _rule_score, _summary_text


def test_pretty_position_label_is_user_friendly() -> None:
    assert _pretty_position_label("special.d0") == "Giải ĐB · số 1"
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
    text = _summary_text("00", 42.0, 12.3, "ML xác suất cao", ["L1: Giải ĐB · số 1(0) + Giải nhất · số 2(0) → 00"], 1)
    assert "Số 00" in text
    assert "đường cầu" in text
