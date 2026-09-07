"""Kiểm thử đấu trường mô hình.

Điều quan trọng nhất cần kiểm ở đây không phải là mô hình nào thắng — mà là
giao thức chấm điểm có trung thực không. Một đấu trường rò rỉ thời gian sẽ cho
mọi mô hình điểm cao và kết luận sẽ sai theo hướng lạc quan, đúng hướng mà
người ta muốn tin. Vì vậy phần lớn tệp này kiểm chính giao thức.
"""

from __future__ import annotations

import numpy as np
import pytest

from bridges.tensor import NUMBER_SPACE
from modeling.benchmark import (
    BASELINE_RATE,
    BetaBinomialShrinkage,
    ClusterRate,
    EmpiricalFrequency,
    GapHazard,
    HiddenMarkovRegime,
    MarkovChain,
    ShrinkageEnsemble,
    SupervisedModel,
    UniformBaseline,
    build_features,
    default_models,
    gradient_boosting,
    walk_forward,
)
from randomness_battery import simulate_draws
from xsmb_domain import LOTO_BASELINE_RATE, LOTO_DRAWS_PER_DAY


@pytest.fixture(scope="module")
def fair_counts() -> np.ndarray:
    return simulate_draws(200, np.random.default_rng(101))


def carryover_counts(n_days: int, *, carried: int = 12, seed: int = 103) -> np.ndarray:
    """Chuỗi cấy 'bạc nhớ' thuần thời gian, giữ nguyên tần suất biên.

    Hai cạm bẫy phải tránh khi cấy tín hiệu, và cả hai đều làm phép kiểm đo
    nhầm thứ khác:

    1. Chọn các con mang sang bằng ``k`` chỉ số đầu tiên thì các con nhỏ được
       ưu ái một cách hệ thống — tín hiệu trở thành thiên lệch *giữa các con*,
       một mô hình tần suất thuần túy cũng bắt được. Nên chọn ngẫu nhiên.
    2. Chỉ bật thêm con mà không tắt bớt thì tỉ lệ về *chung* tăng lên trên nền
       của miền — và mô hình tần suất lại bắt được, lần này chỉ vì nó học được
       mức nền mới. Nên mỗi lần bật một con của hôm qua thì tắt một con không
       thuộc hôm qua.

    Sau hai điều chỉnh đó, thông tin duy nhất cấy vào là *thứ tự thời gian*, và
    chỉ mô hình nhìn thứ tự mới khai thác được.
    """
    rng = np.random.default_rng(seed)
    counts = simulate_draws(n_days, rng)
    for day in range(1, n_days):
        yesterday = set(np.flatnonzero(counts[day - 1] > 0).tolist())
        today = set(np.flatnonzero(counts[day] > 0).tolist())
        to_turn_on = sorted(yesterday - today)
        to_turn_off = sorted(today - yesterday)
        size = min(carried, len(to_turn_on), len(to_turn_off))
        if size == 0:
            continue
        counts[day, rng.choice(to_turn_on, size=size, replace=False)] = 1
        counts[day, rng.choice(to_turn_off, size=size, replace=False)] = 0
    return counts


class TestBaselineIsTheDomainConstant:
    def test_baseline_matches_the_domain_definition(self) -> None:
        """Nền phải là hằng số của miền, không phải bản sao tính lại."""
        assert BASELINE_RATE == LOTO_BASELINE_RATE

    def test_baseline_model_is_constant_and_ignores_history(self, fair_counts: np.ndarray) -> None:
        model = UniformBaseline()
        first = model.predict_next(fair_counts[:50])
        second = model.predict_next(fair_counts[:150])
        assert np.allclose(first, BASELINE_RATE)
        assert np.array_equal(first, second)


class TestModelContract:
    @pytest.mark.parametrize("model", default_models(), ids=lambda m: m.name)
    def test_returns_one_probability_per_number(self, model, fair_counts) -> None:
        probabilities = model.predict_next(fair_counts)
        assert probabilities.shape == (NUMBER_SPACE,)
        assert np.all(probabilities > 0.0)
        assert np.all(probabilities < 1.0)

    @pytest.mark.parametrize("model", default_models(), ids=lambda m: m.name)
    def test_falls_back_to_baseline_on_short_history(self, model, fair_counts) -> None:
        """Không mô hình nào được phép nổ hay khai báo bừa khi thiếu dữ liệu."""
        probabilities = model.predict_next(fair_counts[:5])
        assert probabilities.shape == (NUMBER_SPACE,)
        assert np.all(np.isfinite(probabilities))


class TestNoTemporalLeakage:
    """Bất biến quan trọng nhất: không gì được nhìn thấy tương lai."""

    def test_features_ignore_the_day_being_predicted(self) -> None:
        counts = simulate_draws(120, np.random.default_rng(107))
        before = build_features(counts, 100)
        tampered = counts.copy()
        tampered[100] = 0
        tampered[100, :LOTO_DRAWS_PER_DAY] = 1
        after = build_features(tampered, 100)
        assert np.array_equal(before, after)

    def test_features_ignore_every_later_day(self) -> None:
        counts = simulate_draws(120, np.random.default_rng(109))
        before = build_features(counts, 100)
        tampered = counts.copy()
        tampered[100:] = np.roll(tampered[100:], 7, axis=1)
        assert np.array_equal(before, build_features(tampered, 100))

    @pytest.mark.parametrize("model", default_models(), ids=lambda m: m.name)
    def test_prediction_ignores_days_after_the_history_slice(self, model) -> None:
        counts = simulate_draws(150, np.random.default_rng(113))
        history = counts[:120]
        assert np.allclose(model.predict_next(history), model.predict_next(history.copy()))


class TestWalkForwardProtocol:
    def test_evaluates_every_day_after_warmup(self, fair_counts: np.ndarray) -> None:
        result = walk_forward(fair_counts, UniformBaseline(), warmup=120)
        assert result.days == fair_counts.shape[0] - 120

    def test_baseline_scores_exactly_zero_skill(self, fair_counts: np.ndarray) -> None:
        """Nền chấm chính nó phải ra đúng 0 — nếu không, thước đo bị lệch."""
        result = walk_forward(fair_counts, UniformBaseline(), warmup=120)
        assert result.logloss_skill == pytest.approx(0.0, abs=1e-12)
        assert result.brier_skill == pytest.approx(0.0, abs=1e-12)
        assert result.paired_t == 0.0

    def test_a_model_that_knows_the_answer_scores_high(self) -> None:
        """Đối chứng dương cho chính thước đo: kẻ gian lận phải được điểm cao.

        Nếu một mô hình nhìn trộm đáp án mà thước đo không thưởng, thì thước đo
        hỏng và mọi kết quả âm tính phía sau đều vô nghĩa.
        """
        counts = simulate_draws(160, np.random.default_rng(127))

        class Oracle:
            name, family = "kẻ gian lận", "oracle"

            def predict_next(self, history: np.ndarray) -> np.ndarray:
                day = history.shape[0]
                outcome = (counts[day] > 0).astype(float)
                return np.where(outcome > 0, 0.95, 0.05)

        result = walk_forward(counts, Oracle(), warmup=120)
        assert result.logloss_skill > 0.5
        assert result.paired_t > 10.0
        assert result.hit_at_27 > 20.0

    def test_detects_planted_carryover(self) -> None:
        """Đối chứng dương ở mức mô hình: Markov phải bắt được bạc nhớ cấy sẵn."""
        counts = carryover_counts(260)
        result = walk_forward(counts, MarkovChain(order=1, pooled=True), warmup=120)
        assert result.beats_baseline
        # Tín hiệu cấy vào là thuần thời gian, nên mô hình tần suất — vốn không
        # nhìn thứ tự ngày — phải KHÔNG bắt được. Nếu nó cũng vượt nền thì phép
        # cấy đã rò rỉ thiên lệch biên và phép kiểm đo nhầm thứ.
        frequency = walk_forward(counts, EmpiricalFrequency(), warmup=120)
        assert not frequency.beats_baseline

    def test_does_not_flag_fair_data(self, fair_counts: np.ndarray) -> None:
        """Đối chứng âm: trên chuỗi công bằng, Markov không được vượt nền."""
        result = walk_forward(fair_counts, MarkovChain(order=1, pooled=True), warmup=120)
        assert not result.beats_baseline

    def test_hit_at_27_baseline_is_the_random_pick_expectation(
        self, fair_counts: np.ndarray
    ) -> None:
        result = walk_forward(fair_counts, UniformBaseline(), warmup=120)
        assert result.baseline_hit_at_27 == pytest.approx(result.hit_at_27, rel=0.15)


class TestBetaBinomialShrinkage:
    def test_collapses_to_the_grand_mean_when_numbers_are_homogeneous(
        self, fair_counts: np.ndarray
    ) -> None:
        """Không có bằng chứng khác biệt thì phải co rút hết — đó là điểm mạnh."""
        probabilities = BetaBinomialShrinkage().predict_next(fair_counts)
        assert probabilities.std() < EmpiricalFrequency().predict_next(fair_counts).std()

    def test_keeps_differences_when_the_urn_is_genuinely_biased(self) -> None:
        rng = np.random.default_rng(131)
        weights = np.ones(NUMBER_SPACE)
        weights[:10] = 6.0
        weights /= weights.sum()
        counts = np.zeros((300, NUMBER_SPACE), dtype=np.int16)
        for day in range(300):
            np.add.at(counts[day], rng.choice(NUMBER_SPACE, LOTO_DRAWS_PER_DAY, p=weights), 1)
        probabilities = BetaBinomialShrinkage().predict_next(counts)
        assert probabilities[:10].mean() > probabilities[10:].mean() + 0.2


class TestGapHazard:
    def test_hazard_is_flat_on_memoryless_data(self, fair_counts: np.ndarray) -> None:
        """Chuỗi độc lập thì nguy cơ không phụ thuộc độ gan."""
        probabilities = GapHazard().predict_next(fair_counts)
        assert probabilities.max() - probabilities.min() < 0.10

    def test_hazard_rises_when_returns_are_forced_periodic(self) -> None:
        """Chu kỳ 4 ngày, lệch pha theo con, nên mỗi con đứng ở một mức gan.

        Phải lệch pha: nếu mọi con cùng pha thì đến lúc dự đoán tất cả nằm
        chung một ô gan và nhận cùng một xác suất, dù bảng nguy cơ có dốc đến
        đâu — phép kiểm khi đó đo pha chứ không đo độ dốc.
        """
        counts = np.zeros((200, NUMBER_SPACE), dtype=np.int16)
        for number in range(NUMBER_SPACE):
            counts[number % 4 :: 4, number] = 1
        probabilities = GapHazard().predict_next(counts)
        assert probabilities.max() - probabilities.min() > 0.10
        # Con 3 vừa về ở ngày cuối (gan 0); con 0 về lần cuối cách đây 3 ngày,
        # tức đúng lúc chu kỳ 4 ngày sắp lặp lại. Nguy cơ phải phản ánh điều đó.
        assert probabilities[0] > 0.9
        assert probabilities[3] < 0.1


class TestSupervisedModels:
    def test_refits_only_on_the_declared_cadence(self, fair_counts: np.ndarray) -> None:
        calls = {"n": 0}

        class Counting:
            def fit(self, x, y):
                calls["n"] += 1
                self._rate = float(y.mean())

            def predict_proba(self, x):
                p = np.full(x.shape[0], self._rate)
                return np.stack([1 - p, p], axis=1)

        model = SupervisedModel("đếm lần khớp", Counting, refit_every=10)
        for day in range(120, 160):
            model.predict_next(fair_counts[:day])
        assert calls["n"] == 4

    def test_gradient_boosting_is_deterministic(self, fair_counts: np.ndarray) -> None:
        a = gradient_boosting().predict_next(fair_counts)
        b = gradient_boosting().predict_next(fair_counts)
        assert np.allclose(a, b)


class TestUnsupervisedAndStateSpace:
    def test_cluster_model_shrinks_towards_baseline(self, fair_counts: np.ndarray) -> None:
        probabilities = ClusterRate(n_clusters=4).predict_next(fair_counts)
        assert abs(probabilities.mean() - BASELINE_RATE) < 0.05

    def test_hmm_stays_finite_and_near_baseline_on_fair_data(self, fair_counts: np.ndarray) -> None:
        probabilities = HiddenMarkovRegime().predict_next(fair_counts)
        assert np.all(np.isfinite(probabilities))
        assert abs(probabilities.mean() - BASELINE_RATE) < 0.05

    def test_hmm_does_not_underflow_on_a_long_series(self) -> None:
        """Tích 400 mật độ nhỏ sẽ về 0 nếu không làm việc trên thang log."""
        counts = simulate_draws(400, np.random.default_rng(137))
        assert np.all(np.isfinite(HiddenMarkovRegime().predict_next(counts)))


class TestCalibrationMetric:
    def test_a_perfectly_calibrated_model_scores_near_zero(self) -> None:
        counts = simulate_draws(200, np.random.default_rng(139))
        result = walk_forward(counts, UniformBaseline(), warmup=120)
        assert result.calibration_error < 0.02

    def test_a_miscalibrated_model_is_penalised(self) -> None:
        counts = simulate_draws(200, np.random.default_rng(149))

        class Overconfident:
            name, family = "quá tự tin", "broken"

            def predict_next(self, history: np.ndarray) -> np.ndarray:
                return np.full(NUMBER_SPACE, 0.75)

        result = walk_forward(counts, Overconfident(), warmup=120)
        assert result.calibration_error > 0.4
        assert result.logloss_skill < 0.0


class TestShrinkageEnsemble:
    """Kiến trúc đề xuất đứng hay đổ ở đúng một tính chất: mặc định là nền.

    Một chồng mô hình thông thường luôn phân bổ hết trọng số cho các thành
    phần, nên không diễn đạt nổi câu "không cái nào đáng tin". Ở đây nền là
    thành phần giữ phần còn lại, và hai lớp kiểm dưới đây khẳng định cả hai
    chiều: im lặng khi không có bằng chứng, chuyển trọng số khi có.
    """

    @staticmethod
    def cheap_components() -> list:
        return [BetaBinomialShrinkage(), MarkovChain(order=1, pooled=True), GapHazard()]

    def test_threshold_is_corrected_for_the_number_of_models(self) -> None:
        """Thử k mô hình thì ngưỡng phải cao hơn 1.96, nếu không sẽ dương giả."""
        one = ShrinkageEnsemble([UniformBaseline()])
        many = ShrinkageEnsemble([UniformBaseline()] * 8)
        assert one.threshold == pytest.approx(1.959964, abs=1e-5)
        assert many.threshold > 2.7

    def test_weights_always_form_a_distribution(self, fair_counts: np.ndarray) -> None:
        weights = ShrinkageEnsemble(self.cheap_components(), evidence_window=60).weights(
            fair_counts
        )
        assert weights.shape == (4,)
        assert weights.sum() == pytest.approx(1.0)
        assert np.all(weights >= 0.0)

    def test_collapses_entirely_to_baseline_without_evidence(self) -> None:
        """Trên chuỗi công bằng, nền phải giữ toàn bộ trọng số."""
        counts = simulate_draws(260, np.random.default_rng(151))
        ensemble = ShrinkageEnsemble(self.cheap_components(), evidence_window=60)
        weights = ensemble.weights(counts)
        assert weights[-1] == pytest.approx(1.0)
        assert np.allclose(ensemble.predict_next(counts), BASELINE_RATE)

    def test_moves_weight_off_baseline_when_signal_is_real(self) -> None:
        """Đối chứng dương: có bạc nhớ thật thì nền phải nhường trọng số."""
        counts = carryover_counts(260)
        ensemble = ShrinkageEnsemble(self.cheap_components(), evidence_window=60)
        weights = ensemble.weights(counts)
        assert weights[-1] < 0.1
        # Trọng số phải về các mô hình nhìn thứ tự thời gian, không phải mô
        # hình tần suất — tín hiệu cấy vào giữ nguyên tần suất biên.
        #
        # Cả xích Markov lẫn mô hình nguy cơ theo độ gan đều là mô hình thời
        # gian và cùng bắt được tín hiệu này: ép một con của hôm qua về lại hôm
        # nay chính là làm nguy cơ ở mức gan 0 tăng vọt. Việc hai mô hình chia
        # nhau trọng số là đúng, nên phép kiểm khẳng định tổng của chúng chứ
        # không ép riêng một mô hình phải thắng.
        bayesian, markov, hazard = weights[0], weights[1], weights[2]
        assert bayesian < 0.01
        assert markov + hazard > 0.9
        assert markov > 0.2 and hazard > 0.2

    def test_predictions_move_away_from_baseline_only_under_signal(self) -> None:
        fair = simulate_draws(260, np.random.default_rng(157))
        planted = carryover_counts(260, seed=157)
        quiet = ShrinkageEnsemble(self.cheap_components(), evidence_window=60)
        loud = ShrinkageEnsemble(self.cheap_components(), evidence_window=60)
        assert quiet.predict_next(fair).std() < 1e-9
        assert loud.predict_next(planted).std() > 0.05

    def test_short_history_falls_back_to_baseline(self, fair_counts: np.ndarray) -> None:
        ensemble = ShrinkageEnsemble(self.cheap_components(), evidence_window=90)
        assert np.allclose(ensemble.predict_next(fair_counts[:100]), BASELINE_RATE)

    def test_beats_baseline_on_planted_signal_end_to_end(self) -> None:
        counts = carryover_counts(320)
        result = walk_forward(
            counts,
            ShrinkageEnsemble(self.cheap_components(), evidence_window=60),
            warmup=200,
        )
        assert result.beats_baseline
