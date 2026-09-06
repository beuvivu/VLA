"""Kiểm thử bộ kiểm định cấu trúc và phân tích công suất.

Nguyên tắc chung của tệp này: một phép kiểm chỉ có giá trị nếu nó *phân biệt
được* hai trường hợp. Vì vậy mỗi thống kê được kiểm hai chiều — phải im lặng
trên dữ liệu ngẫu nhiên và phải kêu lên trên dữ liệu có cấu trúc cấy sẵn.
Kiểm một chiều thôi thì một hàm trả hằng số cũng qua được.
"""

from __future__ import annotations

import numpy as np
import pytest

from randomness_battery import (
    NUMBER_SPACE,
    dispersion_index,
    gap_distribution_distance,
    hot_number_persistence,
    lag1_mutual_information,
    marginal_chi_square,
    minimum_detectable_lift,
    monte_carlo_test,
    run_battery,
    simulate_draws,
    spectral_peak,
    weekday_effect,
)
from xsmb_domain import LOTO_DRAWS_PER_DAY


@pytest.fixture(scope="module")
def fair_counts() -> np.ndarray:
    return simulate_draws(240, np.random.default_rng(7))


def biased_counts(n_days: int, *, favoured: range, seed: int = 11) -> np.ndarray:
    """Chuỗi có một nhóm con được ưu ái, dùng làm đối chứng dương."""
    rng = np.random.default_rng(seed)
    weights = np.ones(NUMBER_SPACE)
    weights[favoured] = 4.0
    weights /= weights.sum()
    counts = np.zeros((n_days, NUMBER_SPACE), dtype=np.int16)
    for day in range(n_days):
        drawn = rng.choice(NUMBER_SPACE, size=LOTO_DRAWS_PER_DAY, p=weights)
        np.add.at(counts[day], drawn, 1)
    return counts


class TestSimulator:
    def test_every_day_draws_exactly_the_domain_count(self) -> None:
        counts = simulate_draws(50, np.random.default_rng(0))
        assert counts.shape == (50, NUMBER_SPACE)
        assert np.all(counts.sum(axis=1) == LOTO_DRAWS_PER_DAY)

    def test_draws_are_with_replacement(self) -> None:
        """Miền cho phép hai giải trùng con, nên phải có kỳ đếm ≥ 2."""
        counts = simulate_draws(400, np.random.default_rng(3))
        assert counts.max() >= 2

    def test_same_seed_reproduces(self) -> None:
        a = simulate_draws(30, np.random.default_rng(5))
        b = simulate_draws(30, np.random.default_rng(5))
        assert np.array_equal(a, b)


class TestStatisticsDiscriminate:
    """Mỗi thống kê phải tách được chuỗi có cấu trúc khỏi chuỗi ngẫu nhiên."""

    def test_chi_square_rises_under_a_biased_urn(self, fair_counts: np.ndarray) -> None:
        biased = biased_counts(240, favoured=range(0, 10))
        assert marginal_chi_square(biased) > 10 * marginal_chi_square(fair_counts)

    def test_chi_square_near_degrees_of_freedom_when_fair(self, fair_counts: np.ndarray) -> None:
        assert 50.0 < marginal_chi_square(fair_counts) < 160.0

    def test_mutual_information_rises_when_yesterday_is_copied(self) -> None:
        """Cấy phụ thuộc trực tiếp: một phần hôm nay lặp lại hôm qua.

        Ngưỡng đặt ở 1.4× chứ không phải 2×, và đó là điều đáng ghi lại: thống
        kê này lấy trung bình trên cả 10 000 cặp con, nên ngay cả khi ép 20 con
        của hôm qua chắc chắn về lại hôm nay — một mức phụ thuộc mạnh hơn bất
        cứ thứ gì có thể tồn tại thật — nó cũng chỉ nhích lên khoảng 1.65×. Độ
        nhạy thấp đó là lý do một giá trị z dương nhỏ trên dữ liệu thật tương
        ứng với hiệu ứng gần như bằng không.
        """
        rng = np.random.default_rng(13)
        counts = simulate_draws(240, rng)
        copied = counts.copy()
        for day in range(1, copied.shape[0]):
            carried = np.flatnonzero(counts[day - 1] > 0)[:20]
            copied[day, carried] = 1
        assert lag1_mutual_information(copied) > 1.4 * lag1_mutual_information(counts)

    def test_mutual_information_test_rejects_planted_carryover(self) -> None:
        """Điều thật sự quan trọng: phép kiểm hoàn chỉnh có bác bỏ được không."""
        rng = np.random.default_rng(67)
        counts = simulate_draws(200, rng)
        for day in range(1, counts.shape[0]):
            counts[day, np.flatnonzero(counts[day - 1] > 0)[:20]] = 1
        result = monte_carlo_test(
            "bạc nhớ cấy sẵn",
            "?",
            lag1_mutual_information,
            counts,
            simulations=100,
            seed=67,
            two_sided=False,
        )
        assert result.p_value < 0.05

    def test_hot_number_persistence_rises_under_a_biased_urn(self, fair_counts: np.ndarray) -> None:
        biased = biased_counts(240, favoured=range(0, 20))
        assert hot_number_persistence(biased) > 0.5
        assert abs(hot_number_persistence(fair_counts)) < 0.4

    def test_spectral_peak_rises_under_an_injected_cycle(self) -> None:
        counts = simulate_draws(240, np.random.default_rng(17))
        cyclic = counts.copy()
        cyclic[::7] = 0
        cyclic[::7, :LOTO_DRAWS_PER_DAY] = 1
        assert spectral_peak(cyclic) > 3 * spectral_peak(counts)

    def test_weekday_effect_rises_when_one_weekday_differs(self) -> None:
        counts = simulate_draws(240, np.random.default_rng(19))
        skewed = counts.copy()
        skewed[::7] = 0
        skewed[::7, :LOTO_DRAWS_PER_DAY] = 1
        assert weekday_effect(skewed) > weekday_effect(counts) + 3.0

    def test_dispersion_index_rises_when_days_clump(self) -> None:
        counts = simulate_draws(240, np.random.default_rng(23))
        clumped = counts.copy()
        clumped[::2] = 0
        clumped[::2, :5] = 5  # rất ít con phân biệt vào ngày chẵn
        assert dispersion_index(clumped) > 5 * dispersion_index(counts)


class TestGapDistribution:
    """Phép kiểm khoảng cách từng hỏng vì scipy giả định biến liên tục."""

    def test_statistic_is_not_constant(self) -> None:
        """Hồi quy: bản cũ trả đúng ``p`` với mọi chuỗi nên vô dụng.

        Phân phối rỗng có độ lệch chuẩn bằng 0 thì mọi giá trị p đều bằng 1 —
        phép kiểm không bao giờ bác bỏ được gì.
        """
        rng = np.random.default_rng(29)
        values = [gap_distribution_distance(simulate_draws(200, rng)) for _ in range(5)]
        assert np.std(values, ddof=1) > 0.0
        assert len({round(v, 12) for v in values}) == len(values)

    def test_fair_series_sits_close_to_geometric(self, fair_counts: np.ndarray) -> None:
        assert gap_distribution_distance(fair_counts) < 0.05

    def test_rises_when_gaps_are_forced_regular(self) -> None:
        """Chuỗi 'điểm rơi' hoàn hảo: mọi con về đúng mỗi 4 ngày."""
        counts = np.zeros((200, NUMBER_SPACE), dtype=np.int16)
        counts[::4] = 1
        assert gap_distribution_distance(counts) > 0.5

    def test_returns_zero_when_too_few_gaps(self) -> None:
        assert gap_distribution_distance(np.zeros((3, NUMBER_SPACE), dtype=np.int16)) == 0.0


class TestMonteCarloCalibration:
    def test_p_value_is_never_zero(self) -> None:
        """Ước lượng (extreme+1)/(sims+1) không bao giờ khẳng định quá dữ liệu.

        Bình thiên lệch mạnh cho thống kê cao hơn mọi lần mô phỏng, nên tử số
        đếm được 0 — giá trị p rơi về sàn 1/(sims+1) chứ không phải 0. Trả về 0
        là khẳng định mạnh hơn mức số lần mô phỏng cho phép.
        """
        result = monte_carlo_test(
            "chi-square",
            "?",
            marginal_chi_square,
            biased_counts(120, favoured=range(0, 5), seed=31),
            simulations=50,
            seed=31,
            two_sided=False,
        )
        assert result.p_value == pytest.approx(1 / 51)
        assert result.p_value > 0.0

    def test_p_value_is_never_one_sided_zero_for_impossible_statistic(self) -> None:
        result = monte_carlo_test(
            "không bao giờ cực trị",
            "?",
            lambda counts: -1e9,
            simulate_draws(40, np.random.default_rng(37)),
            simulations=50,
            two_sided=False,
        )
        assert result.p_value == pytest.approx(1.0)

    def test_fair_data_is_not_flagged(self) -> None:
        """Đối chứng âm: chuỗi ngẫu nhiên không được bác bỏ ở mức 0.05."""
        result = monte_carlo_test(
            "chi-square",
            "?",
            marginal_chi_square,
            simulate_draws(150, np.random.default_rng(41)),
            simulations=200,
            seed=41,
            two_sided=False,
        )
        assert result.p_value > 0.05

    def test_planted_structure_is_flagged(self) -> None:
        """Đối chứng dương: bình có thiên lệch phải bị bác bỏ."""
        result = monte_carlo_test(
            "chi-square",
            "?",
            marginal_chi_square,
            biased_counts(150, favoured=range(0, 10), seed=43),
            simulations=200,
            seed=43,
            two_sided=False,
        )
        assert result.p_value < 0.01

    def test_z_score_is_zero_when_null_is_degenerate(self) -> None:
        result = monte_carlo_test(
            "hằng số",
            "?",
            lambda counts: 5.0,
            simulate_draws(20, np.random.default_rng(47)),
            simulations=20,
        )
        assert result.null_sd == 0.0
        assert result.z_score == 0.0


class TestBattery:
    def test_runs_every_declared_test(self, fair_counts: np.ndarray) -> None:
        results = run_battery(fair_counts, simulations=40, seed=53)
        assert len(results) == 7
        assert len({r.name for r in results}) == 7
        assert all(0.0 < r.p_value <= 1.0 for r in results)

    def test_describe_mentions_the_verdict(self, fair_counts: np.ndarray) -> None:
        results = run_battery(fair_counts, simulations=40, seed=59)
        assert any("ngẫu nhiên" in r.describe() for r in results)

    def test_is_reproducible_under_a_fixed_seed(self, fair_counts: np.ndarray) -> None:
        first = run_battery(fair_counts, simulations=40, seed=61)
        second = run_battery(fair_counts, simulations=40, seed=61)
        assert [r.p_value for r in first] == [r.p_value for r in second]


class TestPowerAnalysis:
    def test_more_days_detect_smaller_effects(self) -> None:
        small = minimum_detectable_lift(100, baseline=0.2377)
        large = minimum_detectable_lift(10_000, baseline=0.2377)
        assert large.detectable_lift < small.detectable_lift

    def test_scales_as_inverse_square_root_of_days(self) -> None:
        """Kiểm đúng dạng công thức, không chỉ đúng chiều."""
        a = minimum_detectable_lift(400, baseline=0.2377)
        b = minimum_detectable_lift(1600, baseline=0.2377)
        assert a.detectable_lift / b.detectable_lift == pytest.approx(2.0, rel=1e-9)

    def test_more_hypotheses_raise_the_bar(self) -> None:
        single = minimum_detectable_lift(391, baseline=0.2377, hypotheses=1)
        family = minimum_detectable_lift(391, baseline=0.2377, hypotheses=412_164)
        assert family.detectable_lift > single.detectable_lift

    def test_repository_history_needs_a_large_relative_lift(self) -> None:
        """Kết quả đóng khung mọi lựa chọn mô hình phía sau."""
        single = minimum_detectable_lift(391, baseline=0.23765728565289646, hypotheses=1)
        assert single.relative_lift > 0.20

    def test_rejects_a_baseline_outside_the_unit_interval(self) -> None:
        with pytest.raises(ValueError):
            minimum_detectable_lift(391, baseline=0.0)
        with pytest.raises(ValueError):
            minimum_detectable_lift(391, baseline=1.0)

    def test_rejects_a_non_positive_hypothesis_count(self) -> None:
        with pytest.raises(ValueError):
            minimum_detectable_lift(391, baseline=0.2377, hypotheses=0)
