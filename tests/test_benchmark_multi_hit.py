"""Giao thức của lượt thử thứ hai cho lô nhiều nháy (``src/multi_hit_benchmark.py``).

Kết luận "không chiến lược nào hơn chọn bừa" chỉ đáng tin khi chính phép đo đúng: không chiến
lược nào nhìn trước, phép so với chọn bừa có phân phối đúng, ứng viên được chọn KHÔNG nhìn giai
đoạn kiểm, và giao thức bắt được một tín hiệu cài sẵn. Mỗi phép kiểm dưới đây ghim một điều ấy.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture(scope="module")
def bench():
    import multi_hit_benchmark

    return multi_hit_benchmark


def _fair(n_draws: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, 100, size=(n_draws, 27))
    return draws, np.arange(n_draws) % 7


def test_every_strategy_reads_only_the_past(bench) -> None:
    """Đổi các kỳ từ t0 trở đi thì điểm của mọi hàng ≤ t0, ở MỌI chiến lược, không được đổi.

    t0 đúng bằng điểm khớp đầu tiên của hai mô hình học, nên một mô hình lỡ học cả nhãn của kỳ
    t0 (lệch một kỳ) cũng làm điểm ở hàng t0 đổi.
    """
    draws, weekdays = _fair(700, seed=1)
    t0 = bench.WARMUP + bench.REFIT_EVERY
    altered = draws.copy()
    altered[t0:] = np.random.default_rng(99).integers(0, 100, size=altered[t0:].shape)
    before = bench.strategy_scores(draws, weekdays)
    after = bench.strategy_scores(altered, weekdays)
    assert {"vip_v1", "logistic_all_features", "gbm_all_features"} <= set(before)
    for name in before:
        assert np.array_equal(before[name][: t0 + 1], after[name][: t0 + 1]), (
            f"{name}: điểm ở kỳ ≤ {t0} đổi khi chỉ các kỳ ≥ {t0} đổi — chiến lược đang nhìn trước"
        )
    learned = before["gbm_all_features"][bench.WARMUP + bench.REFIT_EVERY:]
    assert learned.std() > 0, "mô hình học phải thật sự chấm, không phải hàng hằng số"


def test_comparing_with_random_picks_has_the_right_spread(bench) -> None:
    """Điểm ngẫu nhiên trên lịch sử công bằng: z phải xấp xỉ N(0, 1) qua nhiều lần lặp."""
    zs = []
    for seed in range(300):
        draws, _ = _fair(200, seed)
        multi = (bench.counts_matrix(draws) >= 2).astype(float)
        scores = np.random.default_rng(10_000 + seed).random((201, 100))
        zs.append(bench.evaluate(scores, multi, range(0, 200)).z)
    zs = np.asarray(zs)
    assert abs(zs.mean()) < 0.2
    assert 0.85 < zs.std() < 1.15


def test_an_oracle_scores_every_available_hit(bench) -> None:
    draws, _ = _fair(300, seed=3)
    counts = bench.counts_matrix(draws)
    multi = (counts >= 2).astype(float)
    oracle = np.vstack([multi, np.zeros((1, 100))])
    score = bench.evaluate(oracle, multi, range(0, 300))
    assert score.hits == int(np.minimum(multi.sum(axis=1), bench.TOP_K).sum())
    assert score.z > 10


def test_the_candidate_is_chosen_on_the_development_period_only(bench) -> None:
    """Chiến lược A thắng ở giai đoạn phát triển rồi thua ở giai đoạn kiểm; B ngược lại. Ứng viên
    phải là A: chọn theo giai đoạn kiểm là rò rỉ và luôn "đạt"."""
    n_draws = 2000
    draws, weekdays = _fair(n_draws, seed=4)
    multi = np.vstack([(bench.counts_matrix(draws) >= 2).astype(float), np.zeros((1, 100))])
    noise = np.random.default_rng(5).random(multi.shape)
    split = n_draws - 500
    a = noise.copy()
    a[:split] += multi[:split]
    b = noise.copy()
    b[split:] += multi[split:]
    result = bench.run_protocol(draws, weekdays, holdout=500,
                                scores={"random": noise, "a": a, "b": b})
    assert result["candidate"] == "a"
    assert result["candidate_passes"] is False
    assert result["test_scores"]["b"].z > 10, "B thắng thật ở giai đoạn kiểm nhưng không được chọn"


def test_the_protocol_finds_a_planted_signal_and_confirms_it(bench) -> None:
    """Ba con được cài thêm ≥ 2 nháy với xác suất 3%/kỳ: giao thức phải chọn một chiến lược tần
    suất và đạt ở giai đoạn kiểm. Không bắt được thì kết luận "không có tín hiệu" vô nghĩa."""
    draws, weekdays = bench.planted_history(2000)
    result = bench.run_protocol(draws, weekdays, holdout=600, learned=False, include_vip=False)
    assert result["candidate_passes"] is True
    scores = bench.strategy_scores(draws, weekdays, learned=False, include_vip=False)
    picks = bench.top_k(scores[result["candidate"]][result["test"][0]:result["test"][1]])
    share = np.isin(picks, [7, 38, 68]).mean()
    assert share > 0.3, f"chỉ {share:.0%} lượt chọn rơi vào con được cài (chọn bừa: 3%)"


def test_a_fair_history_does_not_pass(bench) -> None:
    draws, weekdays = _fair(2000, seed=6)
    result = bench.run_protocol(draws, weekdays, holdout=600, learned=False, include_vip=False)
    assert result["candidate_passes"] is False


def test_positional_model_starts_at_the_binomial_base(bench) -> None:
    """Chưa có lịch sử thì mọi vị trí đều 1/100, nên P(≥ 2 nháy) phải đúng bằng mức nền."""
    draws, _ = _fair(10, seed=7)
    prob = bench._positional_multi_prob(draws, None)
    assert np.allclose(prob[0], bench.base_rate(), atol=1e-12)


def test_holm_adjustment(bench) -> None:
    adjusted = bench.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "b": 0.06, "c": 0.06})


def test_ties_are_not_broken_toward_small_numbers(bench) -> None:
    """Điểm hoà (vd. mọi con cùng 0 lần về) mà luôn chọn 00–04 thì chiến lược được lợi hay chịu
    thiệt theo riêng năm con ấy."""
    picks = bench.top_k(np.zeros((400, 100)))
    assert len(np.unique(picks)) > 80
