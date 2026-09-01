from __future__ import annotations

import numpy as np
import pandas as pd

from descriptive_extensions import build_head_table, build_number_recency
from number_reference import (
    BONG,
    all_bo,
    bo,
    bong,
    dan_cham,
    dan_tong_mod10,
    kep_bang,
    kep_lech,
    normalize_two_digit,
    reverse,
)
from research_diagnostics import bh_fdr, build_report
from research_firewall import evaluate_mode
from strategy_lab import evaluate_lab, registry


def _synthetic(days: int = 420, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    values = rng.integers(0, 100, size=(days, 27), dtype=np.int16)
    cols = ["special", "prize1"] + [f"prize_x_{i}" for i in range(25)]
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    two = pd.DataFrame(values, columns=cols)
    two.insert(0, "date", dates)

    sparse_values = np.zeros((days, 100), dtype=np.int16)
    for i, row in enumerate(values):
        sparse_values[i] = np.bincount(row.astype(int), minlength=100)
    sparse = pd.DataFrame(sparse_values, columns=list(range(100)))
    sparse.insert(0, "date", dates)
    return two, sparse


def test_number_reference_invariants() -> None:
    assert normalize_two_digit(7) == "07"
    assert reverse(reverse("07")) == "07"
    for d in range(10):
        assert BONG[BONG[d]] == d
    for n in range(100):
        s = f"{n:02d}"
        assert bong(bong(s)) == s
        assert s in bo(s)
    assert all(len(dan_cham(d)) == 19 for d in range(10))
    assert all(len(dan_tong_mod10(d)) == 10 for d in range(10))
    assert len(kep_bang()) == 10
    assert len(kep_lech()) == 10
    assert 0 < len(all_bo()) < 100


def test_descriptive_extensions_shape() -> None:
    two, _ = _synthetic(days=60)
    head = build_head_table(two, lookback_days=30)
    assert len(head) == 100
    assert int(head["count"].sum()) == 30 * 27
    recency = build_number_recency(two, mode="loto")
    assert len(recency) == 100
    assert set(recency["number"]) == set(range(100))


def test_bh_fdr_is_monotone_after_sorting() -> None:
    p = np.array([0.04, 0.001, 0.2, 0.03, 0.8])
    q = bh_fdr(p)
    order = np.argsort(p)
    assert np.all(np.diff(q[order]) >= -1e-12)
    assert np.all((q >= 0) & (q <= 1))


def test_scientific_diagnostics_runs_on_synthetic_data() -> None:
    two, sparse = _synthetic(days=420)
    report, acf = build_report(two, sparse, permutations=15, seed=11, max_lag=5)
    assert report["draw_days"] == 420
    assert len(report["primary_tests"]) == 5
    assert 0 <= report["de_entropy_ratio"] <= 1
    assert 0 <= report["all_prize_entropy_ratio"] <= 1
    assert list(acf["lag"]) == [1, 2, 3, 4, 5]


def test_research_firewall_has_full_position_family() -> None:
    two, sparse = _synthetic(days=420)
    table, report = evaluate_mode(
        two,
        sparse,
        mode="loto",
        permutations=15,
        seed=17,
        max_reality_days=180,
    )
    assert len(table) == 27 * 27 * 2
    assert report["hypotheses"] == 27 * 27 * 2
    assert set(table["rule"]) == {"tail_tail", "head_tail"}
    assert table["train_q_value_fdr"].between(0, 1).all()
    assert 0 <= report["reality_check"]["p_value"] <= 1


def test_strategy_lab_standardizes_registry_and_holdout() -> None:
    two, sparse = _synthetic(days=360)
    table, agreement, diversity = evaluate_lab(two, sparse, mode="loto", warmup=60)
    assert len(registry()) == 20
    assert len(table) == 20
    assert set(table["strategy"]) == {s.name for s in registry()}
    assert not agreement.empty
    assert set(agreement["min_votes"]).issubset({1, 2, 3, 4, 5})
    assert len(diversity) == 20 * 19 // 2
