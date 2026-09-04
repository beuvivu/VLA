from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from candidate_scoring import ScoringConfig, ScoringWeights, rank_candidates


def _history() -> pd.DataFrame:
    frame = pd.DataFrame(0, index=np.arange(8), columns=["date", *range(100)])
    frame["date"] = pd.date_range("2026-03-01", periods=8, freq="D")
    frame.loc[:5, 12] = 1
    frame.loc[0, 34] = 1
    return frame


def test_candidate_scores_are_deterministic_and_not_probabilities() -> None:
    config = ScoringConfig(lookback_days=6, minimum_history=3)
    first = rank_candidates(_history(), "2026-03-07", "loto", config)
    second = rank_candidates(_history(), "2026-03-07", "loto", config)

    assert [(item.number, item.score) for item in first] == [
        (item.number, item.score) for item in second
    ]
    assert first[0].number == 12
    assert 0.0 <= first[0].score <= 1.0
    assert any("not a calibrated probability" in line for line in first[0].explanation)


def test_configurable_weights_and_missing_components() -> None:
    weights = ScoringWeights(
        frequency=0,
        gap=0,
        recency=0,
        ema=0,
        cycle=0,
        conditional=0,
        pattern=1,
    )
    config = ScoringConfig(
        minimum_history=1,
        weights=weights,
        pattern_scores={7: 1.0},
    )
    ranked = rank_candidates(_history(), "2026-03-07", "loto", config)

    assert ranked[0].number == 7
    assert ranked[0].score == 1.0
    missing = next(item for item in ranked if item.number == 8)
    assert missing.score == 0.0
    assert missing.component_scores["pattern"] is None
    assert any("missing optional components" in line for line in missing.explanation)


def test_scoring_configuration_rejects_magic_or_invalid_weights() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ScoringWeights(frequency=0, recency=0, ema=0)
    with pytest.raises(ValueError, match="lookback_days"):
        ScoringConfig(lookback_days=0)
    with pytest.raises(ValueError, match="invalid pattern_scores"):
        ScoringConfig(pattern_scores={7: 1.1})


def test_optional_scores_are_canonicalized_to_two_digit_number_keys() -> None:
    config = ScoringConfig(pattern_scores={"07": 0.8})

    assert dict(config.pattern_scores) == {7: 0.8}


def test_future_mutation_does_not_change_prior_candidate_scores() -> None:
    history = _history()
    cutoff = "2026-03-07"
    before = rank_candidates(history, cutoff, "loto")
    mutated = history.copy()
    mutated.loc[mutated["date"] >= pd.Timestamp(cutoff), list(range(100))] = 20
    after = rank_candidates(mutated, cutoff, "loto")

    assert [(item.number, item.score) for item in before] == [
        (item.number, item.score) for item in after
    ]
