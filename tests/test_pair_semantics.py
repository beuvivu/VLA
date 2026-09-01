from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from normalize_pair_artifacts import annotate_pair_frame


def test_same_draw_pair_is_labeled_as_statistical_cooccurrence() -> None:
    raw = pd.DataFrame(
        [
            {"a": 7, "b": 70, "cooccurrence_days": 12},
            {"a": 55, "b": 98, "cooccurrence_days": 8},
        ]
    )
    out = annotate_pair_frame(
        raw, a_col="a", b_col="b", pair_kind="same_draw_cooccurrence"
    )
    assert set(out["pair_kind"]) == {"same_draw_cooccurrence"}
    assert out.loc[0, "canonical_pair_key"] == "07-70"
    assert bool(out.loc[0, "reverse_related"]) is True
    assert bool(out.loc[1, "reverse_related"]) is False
    assert out.loc[0, "a_str"] == "07"
    assert out.loc[0, "b_str"] == "70"


def test_reversal_artifact_relation_metadata() -> None:
    raw = pd.DataFrame([{"pair": "38-83", "a": 38, "b": 83, "days": 10}])
    out = annotate_pair_frame(
        raw, a_col="a", b_col="b", pair_kind="reverse_pair_same_draw"
    )
    row = out.iloc[0]
    assert row["pair"] == "38-83"
    assert bool(row["reverse_related"]) is True
    assert bool(row["same_bo_family"]) is True
    assert "reverse" in row["relation_tags"]


def test_pair_key_preserves_leading_zero_text() -> None:
    raw = pd.DataFrame([{"x": 7, "y": 9, "count": 3}])
    out = annotate_pair_frame(
        raw, a_col="x", b_col="y", pair_kind="same_draw_cooccurrence"
    )
    assert out.iloc[0]["canonical_pair_key"] == "07-09"
    assert out.iloc[0]["a_str"] == "07"
    assert out.iloc[0]["b_str"] == "09"
