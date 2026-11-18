"""Thước đo dự báo dùng chung: mỗi công thức được đối chiếu với đáp án biết trước.

Hoà điểm là trường hợp thường gặp của tổ hợp XSMB (vector gần phẳng), nên phép kiểm trung tâm là
vét cạn MỌI cách xếp các phần tử hoà rồi so kỳ vọng — không tin một công thức chỉ vì nó trông đúng.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from evaluation.forecast_metrics import (
    auc_by_draw,
    by_period,
    calibration_error,
    chance_presence,
    chance_reciprocal_rank,
    cluster_bootstrap_ci,
    paired_sign_flip_p,
    rank_of_truth,
    top_k_mass,
    within_draw_permutation_p,
)


def _brute_force(scores: np.ndarray, weights: np.ndarray, truth: int, k: int) -> tuple[float, float, float]:
    """Trung bình trên mọi hoán vị phá hoà: (khối lượng Top-K, hạng, hạng nghịch đảo)."""
    n = len(scores)
    mass, rank, reciprocal, total = 0.0, 0.0, 0.0, 0
    for perm in itertools.permutations(range(n)):
        # ``perm`` là khoá phá hoà: điểm cao trước, hoà thì theo vị trí trong hoán vị.
        order = sorted(range(n), key=lambda i: (-scores[i], perm.index(i)))
        mass += sum(weights[i] for i in order[:k])
        position = order.index(truth) + 1
        rank += position
        reciprocal += 1.0 / position
        total += 1
    return mass / total, rank / total, reciprocal / total


@pytest.mark.parametrize(
    "scores",
    [
        [0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
        [0.5, 0.4, 0.4, 0.4, 0.1, 0.1],
        [0.9, 0.8, 0.7, 0.6, 0.5, 0.4],
        [0.2, 0.2, 0.7, 0.7, 0.2, 0.7],
    ],
)
def test_ties_are_shared_exactly_as_random_tie_breaking_would(scores: list[float]) -> None:
    s = np.array(scores)
    weights = np.array([1.0, 0.0, 2.0, 0.0, 1.0, 3.0])
    for k in (1, 2, 3, 5):
        for truth in range(6):
            mass, rank, reciprocal = _brute_force(s, weights, truth, k)
            assert top_k_mass(s[None], weights[None], k)[0] == pytest.approx(mass, abs=1e-12)
            got_rank, got_reciprocal = rank_of_truth(s[None], np.array([truth]))
            assert got_rank[0] == pytest.approx(rank, abs=1e-12)
            assert got_reciprocal[0] == pytest.approx(reciprocal, abs=1e-12)


def test_a_flat_forecast_scores_exactly_at_chance_on_every_ranking_metric() -> None:
    """Vector phẳng không được có kỹ năng xếp hạng — kể cả khi mọi con trúng đều là số nhỏ."""
    rng = np.random.default_rng(3)
    flat = np.full((50, 100), 0.2377)
    hits = np.zeros((50, 100))
    hits[:, :24] = 1.0  # xếp hoà "số nhỏ trước" sẽ cho Top-10 trúng 10/10
    truth = rng.integers(0, 100, size=50)
    assert top_k_mass(flat, hits, 10) == pytest.approx(np.full(50, 2.4))
    rank, reciprocal = rank_of_truth(flat, truth)
    assert rank == pytest.approx(np.full(50, 50.5))
    assert reciprocal == pytest.approx(np.full(50, chance_reciprocal_rank(100)))


def test_float_noise_between_cpus_does_not_break_a_tie() -> None:
    noisy = np.full((1, 100), 0.01)
    noisy[0, 7] += 3e-17
    hits = np.zeros((1, 100))
    hits[0, 7] = 1.0
    assert top_k_mass(noisy, hits, 10)[0] == pytest.approx(0.1)


def test_a_strict_ranking_matches_the_plain_count() -> None:
    rng = np.random.default_rng(11)
    scores = rng.permutation(100)[None].astype(float)
    hits = (rng.random((1, 100)) < 0.24).astype(float)
    order = np.argsort(-scores[0], kind="stable")
    assert top_k_mass(scores, hits, 10)[0] == hits[0, order[:10]].sum()
    truth = int(order[36])
    rank, reciprocal = rank_of_truth(scores, np.array([truth]))
    assert rank[0] == 37 and reciprocal[0] == pytest.approx(1 / 37)


def test_chance_levels_are_the_exact_fair_draw_values() -> None:
    assert chance_reciprocal_rank(100) == pytest.approx(sum(1 / r for r in range(1, 101)) / 100)
    assert chance_presence(27) == pytest.approx(1 - 0.99**27)
    assert chance_presence(18) == pytest.approx(1 - 0.99**18)
    # Vét cạn: 3 giải rút đều trên 4 số, hai số chỉ định trước.
    outcomes = list(itertools.product(range(4), repeat=3))
    exact = sum(1 for draw in outcomes if {0, 1} & set(draw)) / len(outcomes)
    assert chance_presence(3, size=4, picks=2) == pytest.approx(exact)


def test_chance_presence_matches_a_simulated_fair_draw() -> None:
    rng = np.random.default_rng(5)
    draws = rng.integers(0, 100, size=(200_000, 27))
    hit = (draws < 10).any(axis=1).mean()
    assert chance_presence(27, picks=10) == pytest.approx(hit, abs=3 * np.sqrt(0.06 * 0.94 / 200_000))


def test_calibration_error_is_the_weighted_gap_of_the_given_bins() -> None:
    rows = [
        {"count": 300, "predicted": 0.20, "observed": 0.23},
        {"count": 700, "predicted": 0.25, "observed": 0.24},
    ]
    out = calibration_error(rows)
    assert out["ece"] == pytest.approx(0.3 * 0.03 + 0.7 * 0.01)
    assert out["mce"] == pytest.approx(0.03)
    assert out["bins"] == 2 and out["observations"] == 1000
    assert calibration_error([{"count": 10, "predicted": 0.4, "observed": 0.4}])["ece"] == 0.0
    assert np.isnan(calibration_error([])["ece"])


def test_bootstrap_interval_is_reproducible_and_resamples_whole_draws() -> None:
    rng = np.random.default_rng(1)
    values = rng.normal(0.3, 1.0, size=400)
    first = cluster_bootstrap_ci(values, seed=9)
    assert first == cluster_bootstrap_ci(values, seed=9)
    assert first[0] < values.mean() < first[1]
    stderr = values.std(ddof=1) / 20
    assert first[1] - first[0] == pytest.approx(2 * 1.96 * stderr, rel=0.15)
    # Bốn bản sao của cùng một kỳ là MỘT quan sát: khai cụm thì khoảng không hẹp lại.
    repeated = np.repeat(values, 4)
    clustered = cluster_bootstrap_ci(repeated, clusters=np.repeat(np.arange(400), 4), seed=9)
    naive = cluster_bootstrap_ci(repeated, seed=9)
    assert clustered[1] - clustered[0] == pytest.approx(first[1] - first[0], rel=0.15)
    assert naive[1] - naive[0] < 0.65 * (clustered[1] - clustered[0])


def test_bootstrap_of_a_ratio_uses_the_ratio_of_means() -> None:
    rng = np.random.default_rng(2)
    pair = np.column_stack([rng.gamma(2.0, 1.0, 500), rng.gamma(2.0, 1.0, 500)])
    low, high = cluster_bootstrap_ci(pair, statistic=lambda rows: 1.0 - rows[:, 0].mean() / rows[:, 1].mean(), seed=4)
    assert low < 1.0 - pair[:, 0].mean() / pair[:, 1].mean() < high


def test_sign_flip_p_is_uniform_without_an_effect_and_small_with_one() -> None:
    rng = np.random.default_rng(8)
    null_p = np.array([paired_sign_flip_p(rng.normal(0, 1, 60), n_perm=400, seed=i) for i in range(400)])
    assert abs((null_p < 0.05).mean() - 0.05) < 0.03
    assert abs(np.median(null_p) - 0.5) < 0.08
    assert paired_sign_flip_p(rng.normal(0.8, 1, 60), n_perm=2000, seed=1) < 0.001
    assert paired_sign_flip_p(np.zeros(20)) == 1.0


def test_sign_flip_flips_a_whole_cluster_together() -> None:
    """Mười cụm, mỗi cụm một hiệu lặp 50 lần: chỉ có 10 quan sát độc lập."""
    effects = np.array([1.0, -0.6, 0.9, 0.4, -0.2, 0.7, 0.5, -0.4, 0.8, 0.3])
    d = np.repeat(effects, 50)
    clusters = np.repeat(np.arange(10), 50)
    assert paired_sign_flip_p(d, n_perm=4000, seed=2) < 0.001
    assert paired_sign_flip_p(d, clusters=clusters, n_perm=4000, seed=2) > 0.05


def test_by_period_groups_draws_by_calendar_month_and_iso_week() -> None:
    dates = ["2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03"]
    values = np.array([1.0, 3.0, 5.0, 7.0, 9.0])
    months = by_period(dates, values)
    assert [(m["period"], m["draws"], m["mean"]) for m in months] == [("2026-10", 2, 2.0), ("2026-11", 3, 7.0)]
    assert months[0]["stderr"] == pytest.approx(np.std([1.0, 3.0], ddof=1) / np.sqrt(2))
    weeks = by_period(dates, values, period="week")
    # 01-11-2026 là Chủ nhật: còn thuộc tuần ISO 44 cùng 30 và 31-10.
    assert [(w["period"], w["draws"]) for w in weeks] == [("2026-W44", 3), ("2026-W45", 2)]
    with pytest.raises(ValueError):
        by_period(dates, values[:2])


def test_invalid_inputs_are_rejected_instead_of_scored() -> None:
    with pytest.raises(ValueError):
        top_k_mass(np.ones((2, 5)), np.ones((2, 4)), 2)
    with pytest.raises(ValueError):
        top_k_mass(np.ones((2, 5)), np.ones((2, 5)), 6)
    with pytest.raises(ValueError):
        top_k_mass(np.array([[0.1, np.nan]]), np.ones((1, 2)), 1)
    with pytest.raises(ValueError):
        rank_of_truth(np.ones((2, 5)), np.array([0, 5]))
    with pytest.raises(ValueError):
        chance_presence(27, picks=101)


def _pairwise_auc(scores: np.ndarray, hits: np.ndarray) -> float:
    """Định nghĩa gốc, đếm từng cặp: P(điểm con về > điểm con không về) + ½·P(bằng nhau)."""
    wins = ties = pairs = 0
    for a in np.flatnonzero(hits):
        for b in np.flatnonzero(~hits):
            pairs += 1
            wins += scores[a] > scores[b]
            ties += scores[a] == scores[b]
    return (wins + 0.5 * ties) / pairs


def test_auc_matches_the_pairwise_definition_including_ties() -> None:
    rng = np.random.default_rng(13)
    scores = np.round(rng.random((6, 40)), 1)  # làm tròn một chữ số: rất nhiều khối hoà
    hits = rng.random((6, 40)) < 0.25
    hits[:, 0] = True
    got = auc_by_draw(scores, hits)
    for row in range(6):
        assert got[row] == pytest.approx(_pairwise_auc(scores[row], hits[row]), abs=1e-12)
    perfect = np.arange(10.0)[None]
    assert auc_by_draw(perfect, perfect > 6.5)[0] == 1.0
    assert auc_by_draw(perfect, perfect < 2.5)[0] == 0.0


def test_auc_of_a_flat_forecast_is_exactly_one_half_and_degenerate_draws_are_undefined() -> None:
    flat = np.full((3, 100), 0.2377)
    hits = np.zeros((3, 100), dtype=bool)
    hits[0, :24] = True
    hits[1, 60:] = True
    assert auc_by_draw(flat, hits)[:2] == pytest.approx([0.5, 0.5])
    assert np.isnan(auc_by_draw(flat, hits)[2])  # kỳ không có con nào về
    assert np.isnan(auc_by_draw(flat, np.ones((3, 100), dtype=bool))).all()
    with pytest.raises(ValueError):
        auc_by_draw(flat, hits[:, :50])


def test_within_draw_permutation_p_is_uniform_for_noise_and_small_for_a_real_ranking() -> None:
    def mean_auc(scores: np.ndarray, hits: np.ndarray) -> float:
        return float(np.nanmean(auc_by_draw(scores, hits)))

    rng = np.random.default_rng(14)
    null_p = []
    for trial in range(120):
        scores = rng.random((30, 100))
        hits = rng.random((30, 100)) < 0.24
        null_p.append(within_draw_permutation_p(scores, hits, mean_auc, n_perm=150, seed=trial))
    null_p = np.array(null_p)
    assert (null_p < 0.05).mean() < 0.12 and 0.3 < np.median(null_p) < 0.7
    informative = rng.random((30, 100))
    hits = rng.random((30, 100)) < 0.1 + 0.3 * informative  # điểm cao thì dễ về hơn
    assert within_draw_permutation_p(informative, hits, mean_auc, n_perm=500, seed=1) < 0.01
    # Xáo trong từng kỳ giữ nguyên số con về của kỳ ấy.
    seen = []
    within_draw_permutation_p(informative, hits, lambda s, h: seen.append(h.sum(axis=1).tolist()) or 0.0, n_perm=3)
    assert all(row == hits.sum(axis=1).tolist() for row in seen)
