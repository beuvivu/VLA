from __future__ import annotations

import itertools

import numpy as np
import pytest
from scipy import stats

from core import regional_domain as rd
from core import xsmb_domain
from ingest import regional_lottery


def test_a_station_draw_has_eighteen_prizes_and_eighty_two_digits() -> None:
    assert rd.LOTO_DRAWS_PER_STATION == 18 == len(rd.SLOTS) == len(rd.SLOT_WIDTHS)
    assert rd.TOTAL_DIGITS == 82 == sum(count * width for _, count, width in rd.PRIZE_SPECS)
    assert rd.SLOTS[rd.SPECIAL_SLOT] == ("ĐB", 1) and rd.SLOT_WIDTHS[rd.SPECIAL_SLOT] == 6


def test_the_station_baseline_is_not_the_xsmb_baseline() -> None:
    assert rd.LOTO_BASELINE_RATE == pytest.approx(1 - 0.99**18)
    assert rd.baseline_rate("loto") == rd.LOTO_BASELINE_RATE and rd.baseline_rate("de") == 0.01
    assert xsmb_domain.LOTO_BASELINE_RATE - rd.LOTO_BASELINE_RATE == pytest.approx(0.0722, abs=1e-4)
    with pytest.raises(ValueError):
        rd.baseline_rate("xien")


def test_pair_cooccurrence_is_inclusion_exclusion_not_the_square_of_the_baseline() -> None:
    outcomes = list(itertools.product(range(4), repeat=3))
    both = sum(1 for o in outcomes if 0 in o and 1 in o) / len(outcomes)
    assert 1 - 2 * (3 / 4) ** 3 + (2 / 4) ** 3 == pytest.approx(both)
    assert rd.PAIR_COOCCURRENCE_RATE == pytest.approx(1 - 2 * 0.99**18 + 0.98**18)
    assert rd.PAIR_COOCCURRENCE_RATE < rd.LOTO_BASELINE_RATE**2


def test_nhay_distribution_is_the_exact_binomial() -> None:
    got = np.array(rd.nhay_distribution())
    assert got.sum() == pytest.approx(1.0)
    assert got == pytest.approx(stats.binom.pmf(np.arange(19), 18, 0.01))
    assert 1 - got[0] == pytest.approx(rd.LOTO_BASELINE_RATE)


def test_distinct_count_distribution_matches_exhaustive_enumeration() -> None:
    outcomes = list(itertools.product(range(4), repeat=3))
    exact = [sum(1 for o in outcomes if len(set(o)) == d) / len(outcomes) for d in range(4)]
    assert rd.distinct_count_distribution(slots=3, size=4) == pytest.approx(exact)


@pytest.mark.parametrize(("slots", "baseline"), [(18, rd.LOTO_BASELINE_RATE), (27, xsmb_domain.LOTO_BASELINE_RATE)])
def test_distinct_count_distribution_sums_to_one_with_the_right_mean(slots: int, baseline: float) -> None:
    pmf = np.array(rd.distinct_count_distribution(slots=slots))
    assert pmf.sum() == pytest.approx(1.0)
    assert (pmf * np.arange(len(pmf))).sum() == pytest.approx(100 * baseline)
    rng = np.random.default_rng(slots)
    simulated = np.array([len(set(row)) for row in rng.integers(0, 100, size=(40_000, slots))])
    assert (pmf * np.arange(len(pmf))).sum() == pytest.approx(simulated.mean(), abs=0.03)
    assert pmf[slots] == pytest.approx((simulated == slots).mean(), abs=0.01)


def test_every_printed_digit_belongs_to_the_cage_of_its_place_value() -> None:
    cages = np.array(rd.CAGE_OF_DIGIT)
    assert len(cages) == rd.TOTAL_DIGITS and rd.CAGES == 6 == len(rd.CAGE_NAMES)
    ends = np.cumsum(rd.SLOT_WIDTHS)
    assert (cages[ends - 1] == 0).all() and (cages[ends - 2] == 1).all()
    assert [int((cages == c).sum()) for c in range(6)] == [18, 18, 17, 16, 12, 1]
    start = ends[rd.SPECIAL_SLOT] - 6
    assert cages[start : ends[rd.SPECIAL_SLOT]].tolist() == [5, 4, 3, 2, 1, 0]


def test_the_collector_reads_the_same_prize_layout_object() -> None:
    assert regional_lottery.PRIZE_SPECS is rd.PRIZE_SPECS
    assert regional_lottery.REGIONS is rd.REGIONS
