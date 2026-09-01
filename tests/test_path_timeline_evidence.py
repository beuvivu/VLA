from __future__ import annotations

import pandas as pd

from path_models import FIELD_WIDTHS
from path_timeline_evidence import build_timeline_table


def _raw_rows() -> pd.DataFrame:
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    specials = [12000, 12012, 34034]
    rows = []
    for d, special in zip(dates, specials):
        row = {"date": d}
        for field, _width in FIELD_WIDTHS:
            row[field] = 0
        row["special"] = special
        rows.append(row)
    return pd.DataFrame(rows)


def _two_from_raw(raw: pd.DataFrame) -> pd.DataFrame:
    out = raw.copy()
    for field, _width in FIELD_WIDTHS:
        out[field] = out[field].astype(int) % 100
    return out


def test_timeline_uses_only_base_date_digits_and_scores_target_date() -> None:
    raw = _raw_rows()
    two = _two_from_raw(raw)
    positions = pd.DataFrame(
        [
            {
                "rule_kind": "active",
                "lag_days": 1,
                "pos_i_index": 0,
                "pos_j_index": 1,
                "pos_i_code": "special.d0",
                "pos_j_code": "special.d1",
                "path_line": "L1 test",
                "rule_score": 10,
                "p_mean": 0.25,
                "current_streak": 2,
                "max_streak": 4,
                "predict_for_date": "2026-01-04",
            }
        ]
    )

    out = build_timeline_table(raw, two, positions, mode="de", recent=20)
    assert len(out) == 1
    row = out.iloc[0]
    assert '"target_date": "2026-01-02"' in row["timeline_recent_json"]
    assert '"candidate": "12"' in row["timeline_recent_json"]
    assert row["timeline_trials"] == 2
    assert row["timeline_hits"] == 1
    assert row["predicts_next"] == "34"
