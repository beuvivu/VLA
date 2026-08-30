from __future__ import annotations

import pandas as pd

from build_statistics_dashboard import _evidence_payload, _matrix, _table


def test_modern_matrix_is_self_contained_and_complete() -> None:
    html = _matrix(
        pd.DataFrame({"number_str": ["00", "99"], "freq": [1, 3]}),
        title="Test matrix",
        subtitle="Self-contained",
        value_col="freq",
    )
    assert html.count("matrix-cell") == 100
    assert "<img" not in html
    assert "00" in html
    assert "99" in html


def test_table_ignores_missing_requested_columns() -> None:
    html = _table(
        pd.DataFrame({"number_str": ["01"], "freq": [2]}),
        title="Test table",
        columns=["number_str", "missing_col", "freq"],
        highlight_col="freq",
        zfill_cols={"number_str"},
    )
    assert "missing_col" not in html
    assert "01" in html
    assert "Tần suất" in html


def test_clickable_matrix_and_payload_include_position_evidence() -> None:
    html = _matrix(
        pd.DataFrame({"number_str": ["00"], "freq": [4]}),
        title="Clickable",
        subtitle="Evidence",
        value_col="freq",
        evidence_mode="loto",
    )
    assert "showNumberEvidence" in html
    assert "data-number='00'" in html
    assert "data-mode='loto'" in html

    payload = _evidence_payload(
        cau_loto=pd.DataFrame({"number_str": ["00"], "cau_score": ["42.5"], "prob_percent": ["12.3"]}),
        cau_de=pd.DataFrame(),
        explain_loto=pd.DataFrame(
            {
                "number_str": ["00"],
                "ai_cau_score": ["42.5"],
                "ai_prob_percent": ["12.3"],
                "path_lines_count": ["1"],
                "top_position_1": ["L1: Giải ĐB · số 1(0) + Giải nhất · số 2(0) → 00"],
            }
        ),
        explain_de=pd.DataFrame(),
        positions_loto=pd.DataFrame(
            {
                "number_str": ["00"],
                "rule_kind": ["active"],
                "lag_days": ["1"],
                "base_date": ["2026-08-11"],
                "pos_i_label": ["Giải ĐB · số 1"],
                "digit_i": ["0"],
                "pos_j_label": ["Giải nhất · số 2"],
                "digit_j": ["0"],
                "path_line": ["L1: Giải ĐB · số 1(0) + Giải nhất · số 2(0) → 00"],
                "p_mean": ["0.25"],
                "hits": ["10"],
                "trials": ["40"],
                "current_streak": ["3"],
                "max_streak": ["5"],
                "rule_score": ["55"],
                "reason": ["Cầu đang chạy"],
            }
        ),
        positions_de=pd.DataFrame(),
    )
    assert payload["loto"]["00"]["summary"]["ai_cau_score"] == "42.5"
    assert payload["loto"]["00"]["positions"][0]["pos_i_label"] == "Giải ĐB · số 1"
