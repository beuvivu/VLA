from __future__ import annotations

import pandas as pd
import pytest

from dynamic_cau import (
    NormalizedDraw,
    PatternSpec,
    PositionRef,
    evaluate_pattern,
    find_running_patterns,
)

POSITION_A = PositionRef("special", 0, 0)
POSITION_B = PositionRef("special", 0, 1)
PATTERN = PatternSpec(POSITION_A, POSITION_B, "concat")


def _draw(date: str, *, occurrence_12: int = 0) -> NormalizedDraw:
    counts = [0] * 100
    counts[12] = occurrence_12
    return NormalizedDraw(
        date=pd.Timestamp(date),
        digits={POSITION_A: 1, POSITION_B: 2},
        loto_counts=tuple(counts),
        special_2d=12 if occurrence_12 else 99,
    )


def test_known_positional_pattern_runs_six_consecutive_dates() -> None:
    draws = [_draw("2026-01-01")]
    draws.extend(
        _draw(str(date.date()), occurrence_12=1)
        for date in pd.date_range("2026-01-02", periods=6, freq="D")
    )

    result = find_running_patterns(
        draws,
        6,
        source_positions=[POSITION_A, POSITION_B],
        transformations=["concat"],
        minimum_support=6,
    )
    matching = [item for item in result.patterns if item.pattern_identifier == PATTERN.identifier]

    assert len(matching) == 1
    evidence = matching[0]
    assert evidence.active_run_length == 6
    assert evidence.longest_run_length == 6
    assert evidence.historical_support == 6
    assert evidence.successes == 6
    assert evidence.failures == 0
    assert evidence.predicted_numbers == (12,)
    assert result.search_space_size == 4
    assert result.total_hypotheses_searched == 4
    assert result.pattern_selection_bias_risk is True


def test_broken_streak_preserves_longest_run_but_clears_active_run() -> None:
    draws = [_draw("2026-01-01")]
    draws.extend(
        _draw(str(date.date()), occurrence_12=1)
        for date in pd.date_range("2026-01-02", periods=6, freq="D")
    )
    draws.append(_draw("2026-01-08", occurrence_12=0))

    evidence = evaluate_pattern(draws, PATTERN)
    result = find_running_patterns(
        draws,
        1,
        source_positions=[POSITION_A],
        transformations=["concat"],
        minimum_support=1,
    )

    assert evidence.longest_run_length == 6
    assert evidence.active_run_length == 0
    assert not result.patterns


def test_two_nhay_is_distinct_from_one_or_more_occurrences() -> None:
    draws = [
        _draw("2026-01-01"),
        _draw("2026-01-02", occurrence_12=1),
        _draw("2026-01-03", occurrence_12=2),
        _draw("2026-01-04", occurrence_12=3),
    ]

    ordinary = evaluate_pattern(draws, PATTERN, target_type="loto")
    two_nhay = evaluate_pattern(draws, PATTERN, target_type="loto_2_nhay")

    assert ordinary.successes == 3
    assert two_nhay.successes == 2
    assert ordinary.at_least_one_successes == 3
    assert ordinary.at_least_two_successes == 2
    assert dict(ordinary.exact_occurrence_counts) == {1: 1, 2: 1, 3: 1}


def test_unsorted_input_is_normalized_but_duplicate_dates_are_rejected() -> None:
    draws = [
        _draw("2026-01-03", occurrence_12=1),
        _draw("2026-01-01"),
        _draw("2026-01-02", occurrence_12=1),
    ]
    evidence = evaluate_pattern(draws, PATTERN)
    assert evidence.historical_support == 2
    assert evidence.active_run_length == 2

    with pytest.raises(ValueError, match="duplicates"):
        evaluate_pattern([draws[0], draws[0]], PATTERN)


def test_insufficient_history_returns_no_running_pattern() -> None:
    result = find_running_patterns(
        [_draw("2026-01-01")],
        1,
        source_positions=[POSITION_A],
        transformations=["concat"],
        minimum_support=1,
    )
    assert result.eligible_target_dates == 0
    assert result.surviving_hypotheses == 0
    assert result.patterns == ()


def test_trailing_calendar_gap_clears_an_earlier_active_streak() -> None:
    draws = [
        _draw("2026-01-01"),
        _draw("2026-01-02", occurrence_12=1),
        _draw("2026-01-04", occurrence_12=1),
    ]

    evidence = evaluate_pattern(draws, PATTERN)

    assert evidence.historical_support == 1
    assert evidence.longest_run_length == 1
    assert evidence.active_run_length == 0


def test_result_limit_does_not_hide_total_surviving_hypotheses() -> None:
    draws = [_draw("2026-01-01")]
    draws.extend(
        _draw(str(date.date()), occurrence_12=1)
        for date in pd.date_range("2026-01-02", periods=3, freq="D")
    )

    result = find_running_patterns(
        draws,
        1,
        source_positions=[POSITION_A, POSITION_B],
        transformations=["reverse_pair"],
        minimum_support=1,
        max_results=1,
    )

    assert len(result.patterns) == 1
    assert result.surviving_hypotheses == 2


def test_future_mutation_cannot_change_pattern_evidence_before_cutoff() -> None:
    draws = [
        _draw("2026-01-01"),
        _draw("2026-01-02", occurrence_12=1),
        _draw("2026-01-03", occurrence_12=1),
        _draw("2026-01-04", occurrence_12=0),
    ]
    before = evaluate_pattern(draws, PATTERN, as_of_date="2026-01-04")
    mutated = [*draws[:3], _draw("2026-01-04", occurrence_12=20)]
    after = evaluate_pattern(mutated, PATTERN, as_of_date="2026-01-04")

    assert before == after
