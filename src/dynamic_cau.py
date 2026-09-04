from __future__ import annotations

"""Semantic, chronological positional-pattern research engine.

The engine reproduces deterministic transformations that are publicly visible
on Vietnamese lottery-analysis pages.  It does not claim that a historical
streak predicts the next draw.  Pattern selection and evaluation on the same
period is explicitly labelled as selection-bias risk.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

import pandas as pd

from calendar_alignment import normalize_dates
from number_reference import bo

TargetType = Literal["loto", "loto_2_nhay", "de", "special"]
Transformation = Literal["concat", "reverse_concat", "reverse_pair", "bo"]

TARGET_TYPES = frozenset({"loto", "loto_2_nhay", "de", "special"})
TRANSFORMATIONS = frozenset({"concat", "reverse_concat", "reverse_pair", "bo"})

PRIZE_LAYOUT: dict[str, tuple[int, int]] = {
    "special": (1, 5),
    "prize1": (1, 5),
    "prize2": (2, 5),
    "prize3": (6, 5),
    "prize4": (4, 4),
    "prize5": (6, 4),
    "prize6": (3, 3),
    "prize7": (4, 2),
}


@dataclass(frozen=True, order=True)
class PositionRef:
    prize_name: str
    result_index: int
    digit_index: int

    def __post_init__(self) -> None:
        if self.prize_name not in PRIZE_LAYOUT:
            raise ValueError(f"unknown prize: {self.prize_name}")
        count, width = PRIZE_LAYOUT[self.prize_name]
        if not 0 <= self.result_index < count:
            raise ValueError(f"result_index outside {self.prize_name} layout")
        if not 0 <= self.digit_index < width:
            raise ValueError(f"digit_index outside {self.prize_name} width")

    @property
    def column_name(self) -> str:
        count, _ = PRIZE_LAYOUT[self.prize_name]
        if count == 1:
            return self.prize_name
        return f"{self.prize_name}_{self.result_index + 1}"

    @property
    def identifier(self) -> str:
        return f"{self.prize_name}[{self.result_index}].digit[{self.digit_index}]"


@dataclass(frozen=True)
class NormalizedDraw:
    date: pd.Timestamp
    digits: Mapping[PositionRef, int]
    loto_counts: tuple[int, ...]
    special_2d: int

    def __post_init__(self) -> None:
        normalized = pd.Timestamp(self.date).normalize()
        if pd.isna(normalized):
            raise ValueError("draw date must be valid")
        if len(self.loto_counts) != 100 or any(count < 0 for count in self.loto_counts):
            raise ValueError("loto_counts must contain 100 non-negative counts")
        if not 0 <= int(self.special_2d) <= 99:
            raise ValueError("special_2d must be in 00..99")
        if any(not 0 <= int(digit) <= 9 for digit in self.digits.values()):
            raise ValueError("position digits must be in 0..9")
        object.__setattr__(self, "date", normalized)
        object.__setattr__(self, "digits", MappingProxyType(dict(self.digits)))


@dataclass(frozen=True)
class PatternSpec:
    source_a: PositionRef
    source_b: PositionRef
    transformation: Transformation = "concat"

    @property
    def identifier(self) -> str:
        return f"{self.transformation}:{self.source_a.identifier}+{self.source_b.identifier}"


@dataclass(frozen=True)
class PatternEvidence:
    pattern_identifier: str
    source_positions: tuple[PositionRef, PositionRef]
    transformation: Transformation
    target_type: TargetType
    predicted_numbers: tuple[int, ...]
    active_run_length: int
    longest_run_length: int
    historical_support: int
    successes: int
    failures: int
    confidence: float
    smoothed_confidence: float
    coverage: float
    at_least_one_successes: int
    at_least_two_successes: int
    exact_occurrence_counts: Mapping[int, int]
    last_successful_dates: tuple[str, ...]


@dataclass(frozen=True)
class PatternSearchResult:
    patterns: tuple[PatternEvidence, ...]
    search_space_size: int
    total_hypotheses_searched: int
    surviving_hypotheses: int
    eligible_target_dates: int
    pattern_selection_bias_risk: bool
    selection_warning: str


def all_source_positions() -> tuple[PositionRef, ...]:
    return tuple(
        PositionRef(prize, result, digit)
        for prize, (count, width) in PRIZE_LAYOUT.items()
        for result in range(count)
        for digit in range(width)
    )


def _column_value(row: pd.Series, position: PositionRef) -> int:
    if position.column_name not in row.index:
        raise ValueError(f"raw history missing prize column {position.column_name}")
    value = int(row[position.column_name])
    _, width = PRIZE_LAYOUT[position.prize_name]
    if not 0 <= value < 10**width:
        raise ValueError(f"{position.column_name} value {value} does not fit width {width}")
    return value


def normalize_raw_draws(raw_history: pd.DataFrame) -> tuple[NormalizedDraw, ...]:
    """Convert canonical raw prize rows into immutable semantic draws."""
    if "date" not in raw_history.columns:
        raise ValueError("raw history must contain date")
    work = raw_history.copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise").dt.normalize()
    work = work.sort_values("date").reset_index(drop=True)
    normalize_dates(work["date"])
    positions = all_source_positions()
    draws: list[NormalizedDraw] = []
    for _, row in work.iterrows():
        digits: dict[PositionRef, int] = {}
        values: list[int] = []
        for prize, (count, width) in PRIZE_LAYOUT.items():
            for result_index in range(count):
                base_position = PositionRef(prize, result_index, 0)
                value = _column_value(row, base_position)
                values.append(value)
                text = str(value).zfill(width)
                for digit_index, token in enumerate(text):
                    digits[PositionRef(prize, result_index, digit_index)] = int(token)
        counts = [0] * 100
        for value in values:
            counts[value % 100] += 1
        draws.append(
            NormalizedDraw(
                date=pd.Timestamp(row["date"]),
                digits=digits,
                loto_counts=tuple(counts),
                special_2d=values[0] % 100,
            )
        )
    return tuple(draws)


def _normalize_draw_sequence(
    history: pd.DataFrame | Sequence[NormalizedDraw],
    *,
    as_of_date: object | None = None,
) -> tuple[NormalizedDraw, ...]:
    if isinstance(history, pd.DataFrame):
        draws = normalize_raw_draws(history)
    else:
        draws = tuple(sorted(history, key=lambda draw: draw.date))
    normalize_dates([draw.date for draw in draws])
    if as_of_date is not None:
        cutoff = pd.Timestamp(as_of_date).normalize()
        if pd.isna(cutoff):
            raise ValueError("as_of_date must be valid")
        draws = tuple(draw for draw in draws if draw.date < cutoff)
    return draws


def transform_digits(transformation: Transformation, digit_a: int, digit_b: int) -> tuple[int, ...]:
    if not 0 <= int(digit_a) <= 9 or not 0 <= int(digit_b) <= 9:
        raise ValueError("source digits must be in 0..9")
    a, b = int(digit_a), int(digit_b)
    forward = 10 * a + b
    if transformation == "concat":
        return (forward,)
    if transformation == "reverse_concat":
        return (10 * b + a,)
    if transformation == "reverse_pair":
        return tuple(sorted({forward, 10 * b + a}))
    if transformation == "bo":
        return tuple(sorted(int(number) for number in bo(forward)))
    raise ValueError(f"unknown transformation: {transformation}")


def _criterion(target_type: TargetType, count: int) -> bool:
    if target_type == "loto_2_nhay":
        return count >= 2
    return count >= 1


def _runs(hits: list[bool], dates: list[pd.Timestamp]) -> tuple[int, int]:
    active = 0
    previous: pd.Timestamp | None = None
    for hit, date in zip(reversed(hits), reversed(dates), strict=True):
        if previous is not None and previous - date != pd.Timedelta(days=1):
            break
        if not hit:
            break
        active += 1
        previous = date

    longest = current = 0
    previous = None
    for hit, date in zip(hits, dates, strict=True):
        consecutive = previous is None or date - previous == pd.Timedelta(days=1)
        current = current + 1 if hit and consecutive else (1 if hit else 0)
        longest = max(longest, current)
        previous = date
    return active, longest


def evaluate_pattern(
    history: pd.DataFrame | Sequence[NormalizedDraw],
    pattern: PatternSpec,
    *,
    target_type: TargetType = "loto",
    as_of_date: object | None = None,
) -> PatternEvidence:
    """Evaluate one lag-one pattern on exact consecutive calendar draws."""
    if target_type not in TARGET_TYPES:
        raise ValueError(f"unknown target_type: {target_type}")
    draws = _normalize_draw_sequence(history, as_of_date=as_of_date)
    by_date = {draw.date: draw for draw in draws}
    target_dates: list[pd.Timestamp] = []
    hits: list[bool] = []
    occurrence_counts: list[int] = []
    success_dates: list[str] = []
    latest_predictions: tuple[int, ...] = ()

    for target in draws:
        source = by_date.get(target.date - pd.Timedelta(days=1))
        if source is None:
            continue
        try:
            a = source.digits[pattern.source_a]
            b = source.digits[pattern.source_b]
        except KeyError as exc:
            raise ValueError(f"draw missing source position: {exc.args[0]}") from exc
        candidates = transform_digits(pattern.transformation, a, b)
        if target_type in {"de", "special"}:
            count = int(target.special_2d in candidates)
        else:
            # Two-nháy means at least one individually predicted number occurs
            # at least twice; counts from different candidates are not pooled.
            count = max((target.loto_counts[number] for number in candidates), default=0)
        hit = _criterion(target_type, count)
        target_dates.append(target.date)
        hits.append(hit)
        occurrence_counts.append(count)
        if hit:
            success_dates.append(target.date.date().isoformat())

    if draws:
        latest = draws[-1]
        if pattern.source_a in latest.digits and pattern.source_b in latest.digits:
            latest_predictions = transform_digits(
                pattern.transformation,
                latest.digits[pattern.source_a],
                latest.digits[pattern.source_b],
            )

    support = len(hits)
    successes = sum(hits)
    active, longest = _runs(hits, target_dates)
    # A stale earlier streak is not active when the newest draw cannot be
    # evaluated because its exact preceding calendar draw is missing.
    if not target_dates or not draws or target_dates[-1] != draws[-1].date:
        active = 0
    histogram = {count: occurrence_counts.count(count) for count in sorted(set(occurrence_counts))}
    return PatternEvidence(
        pattern_identifier=pattern.identifier,
        source_positions=(pattern.source_a, pattern.source_b),
        transformation=pattern.transformation,
        target_type=target_type,
        predicted_numbers=latest_predictions,
        active_run_length=active,
        longest_run_length=longest,
        historical_support=support,
        successes=successes,
        failures=support - successes,
        confidence=successes / support if support else 0.0,
        smoothed_confidence=(successes + 1.0) / (support + 2.0),
        coverage=support / max(len(draws) - 1, 1),
        at_least_one_successes=sum(count >= 1 for count in occurrence_counts),
        at_least_two_successes=sum(count >= 2 for count in occurrence_counts),
        exact_occurrence_counts=MappingProxyType(histogram),
        last_successful_dates=tuple(success_dates[-10:]),
    )


def find_running_patterns(
    history: pd.DataFrame | Sequence[NormalizedDraw],
    days_count: int,
    *,
    source_positions: Sequence[PositionRef] | None = None,
    transformations: Sequence[Transformation] = ("concat", "reverse_pair"),
    target_type: TargetType = "loto",
    as_of_date: object | None = None,
    minimum_support: int = 10,
    max_hypotheses: int = 50_000,
    max_results: int | None = None,
) -> PatternSearchResult:
    """Find patterns currently successful for at least ``days_count`` draws."""
    if days_count < 1:
        raise ValueError("days_count must be >= 1")
    if minimum_support < 1:
        raise ValueError("minimum_support must be >= 1")
    if max_hypotheses < 1:
        raise ValueError("max_hypotheses must be >= 1")
    positions = tuple(
        dict.fromkeys(all_source_positions() if source_positions is None else source_positions)
    )
    if not positions:
        raise ValueError("source_positions must not be empty")
    transforms = tuple(dict.fromkeys(transformations))
    if not transforms:
        raise ValueError("transformations must not be empty")
    unknown_transforms = sorted(set(transforms) - TRANSFORMATIONS)
    if unknown_transforms:
        raise ValueError(f"unknown transformations: {unknown_transforms}")
    if target_type not in TARGET_TYPES:
        raise ValueError(f"unknown target_type: {target_type}")
    search_space = len(positions) * len(positions) * len(transforms)
    if search_space > max_hypotheses:
        raise ValueError(
            f"pattern search space {search_space} exceeds max_hypotheses={max_hypotheses}"
        )

    draws = _normalize_draw_sequence(history, as_of_date=as_of_date)
    draw_dates = {item.date for item in draws}
    eligible = sum(draw.date - pd.Timedelta(days=1) in draw_dates for draw in draws)
    surviving: list[PatternEvidence] = []
    searched = 0
    for transformation in transforms:
        for source_a in positions:
            for source_b in positions:
                searched += 1
                evidence = evaluate_pattern(
                    draws,
                    PatternSpec(source_a, source_b, transformation),
                    target_type=target_type,
                )
                if (
                    evidence.historical_support >= minimum_support
                    and evidence.active_run_length >= days_count
                ):
                    surviving.append(evidence)
    surviving.sort(
        key=lambda item: (
            -item.active_run_length,
            -item.historical_support,
            -item.smoothed_confidence,
            item.pattern_identifier,
        )
    )
    surviving_count = len(surviving)
    if max_results is not None:
        if max_results < 1:
            raise ValueError("max_results must be >= 1 when provided")
        surviving = surviving[:max_results]
    return PatternSearchResult(
        patterns=tuple(surviving),
        search_space_size=search_space,
        total_hypotheses_searched=searched,
        surviving_hypotheses=surviving_count,
        eligible_target_dates=eligible,
        pattern_selection_bias_risk=searched > 1,
        selection_warning=(
            "PATTERN_SELECTION_BIAS_RISK: this historical search is pattern discovery, "
            "not proof of future predictive skill. Validate selected rules on untouched "
            "future dates."
        ),
    )
