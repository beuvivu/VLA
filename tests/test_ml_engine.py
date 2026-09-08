"""Kiểm thử ``ml_engine``.

Trọng tâm không phải "mô hình có tốt không" mà là **các bất biến mà mọi kết
luận phía sau dựa vào**: không rò rỉ thời gian, tuần tự hóa trung thực, bandit
hội tụ đúng chiều, phát hiện trôi lệch có cả hai chiều, và chế độ an toàn kích
hoạt đúng lúc.

Mỗi phép kiểm hành vi đều có đối chứng hai chiều. Kiểm một chiều thôi thì một
hàm trả hằng số cũng qua được — và một hệ thống luôn im lặng không phân biệt
được với một hệ thống hỏng.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from ml_engine.bandit import ArmState, BanditError, DiscountedThompsonSamplingMAB
from ml_engine.capabilities import CAPABILITIES
from ml_engine.drift import ConceptDriftDetector, _PureAdwin
from ml_engine.fallback import Mode, SafeModeController
from ml_engine.features import FeatureMatrix, build_features, build_training_table
from ml_engine.main_pipeline import ContinuousLearningPipeline, PipelineConfig
from ml_engine.metrics import EconomicModel, PerformanceTracker, score_day
from ml_engine.models import RankingBooster, TabularBooster, TemporalSequenceModel
from ml_engine.schema import (
    BASELINE_RATE,
    NUMBER_SPACE,
    DailyRequest,
    ObservationMatrix,
    SchemaError,
)
from ml_engine.selection import select_features
from ml_engine.validation import WalkForwardValidator
from xsmb_domain import LOTO_BASELINE_RATE, LOTO_DRAWS_PER_DAY


def synthetic_counts(n_days: int, seed: int = 0) -> np.ndarray:
    """Chuỗi công bằng: 27 lần rút độc lập, đều trên 00–99, có hoàn lại."""
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, NUMBER_SPACE, size=(n_days, LOTO_DRAWS_PER_DAY))
    counts = np.zeros((n_days, NUMBER_SPACE), dtype=np.int16)
    rows = np.repeat(np.arange(n_days), LOTO_DRAWS_PER_DAY)
    np.add.at(counts, (rows, draws.ravel()), 1)
    return counts


def synthetic_matrix(n_days: int, seed: int = 0) -> ObservationMatrix:
    return ObservationMatrix(
        dates=pd.date_range("2025-01-01", periods=n_days, freq="D"),
        counts=synthetic_counts(n_days, seed),
    )


@pytest.fixture(scope="module")
def matrix() -> ObservationMatrix:
    return synthetic_matrix(300, seed=11)


# ---------------------------------------------------------------------------
# Hợp đồng dữ liệu
# ---------------------------------------------------------------------------


class TestObservationMatrix:
    def test_baseline_is_the_domain_constant(self) -> None:
        """Nền phải lấy từ miền, không phải bản sao tính lại."""
        assert BASELINE_RATE == LOTO_BASELINE_RATE

    def test_accepts_a_well_formed_matrix(self, matrix: ObservationMatrix) -> None:
        assert matrix.n_days == 300
        assert matrix.counts.shape == (300, NUMBER_SPACE)
        assert matrix.hits.shape == matrix.counts.shape

    def test_rejects_a_day_with_the_wrong_number_of_draws(self) -> None:
        counts = synthetic_counts(20)
        counts[7, 0] += 1  # 28 con thay vì 27
        with pytest.raises(SchemaError, match="27"):
            ObservationMatrix(
                dates=pd.date_range("2025-01-01", periods=20, freq="D"), counts=counts
            )

    def test_rejects_a_gap_in_the_calendar(self) -> None:
        """Kỳ cào hụt vẫn phải bị chặn: đó là dữ liệu thiếu, không phải ngày nghỉ."""
        dates = pd.DatetimeIndex(
            list(pd.date_range("2025-01-01", periods=10, freq="D"))
            + list(pd.date_range("2025-01-15", periods=10, freq="D"))
        )
        with pytest.raises(SchemaError, match="thiếu kỳ"):
            ObservationMatrix(dates=dates, counts=synthetic_counts(20))

    def test_accepts_a_gap_that_falls_on_known_non_draw_days(self) -> None:
        """Ngày XSMB không quay không phải lỗi dữ liệu.

        Tết 2025 nghỉ 28-31/01. Đòi liền mạch tuyệt đối thì chuỗi thật bị từ
        chối, và trước đây nó chỉ lọt vì 50 bản ghi bịa lấp vào chỗ trống —
        bất biến được bảo đảm bởi chính dữ liệu sai.
        """
        from calendar_alignment import known_non_draw_days

        assert "2025-01-28" in known_non_draw_days(), "cần mốc Tết 2025 để test"

        dates = pd.DatetimeIndex(
            list(pd.date_range("2025-01-24", periods=4, freq="D"))
            + list(pd.date_range("2025-02-01", periods=6, freq="D"))
        )
        matrix = ObservationMatrix(dates=dates, counts=synthetic_counts(10))
        assert matrix.n_days == 10

    def test_rejects_negative_counts(self) -> None:
        counts = synthetic_counts(10).astype(np.int16)
        counts[0, 0] = -1
        with pytest.raises(SchemaError, match="âm"):
            ObservationMatrix(
                dates=pd.date_range("2025-01-01", periods=10, freq="D"), counts=counts
            )

    def test_window_preserves_every_guarantee(self, matrix: ObservationMatrix) -> None:
        sliced = matrix.window(10, 60)
        assert sliced.n_days == 50
        assert sliced.dates[0] == matrix.dates[10]

    def test_from_frame_matches_the_repository_tensor(self) -> None:
        """Đối chiếu với DigitTensor đã được kho tin cậy từ trước."""
        from bridges import DigitTensor

        raw = pd.read_csv("data/xsmb.csv")
        mine = ObservationMatrix.from_frame(raw)
        theirs = DigitTensor.from_raw(raw)
        assert np.array_equal(mine.counts.astype(int), theirs.loto_counts.astype(int))

    def test_from_frame_pads_prizes_that_lost_leading_zeros(self) -> None:
        """CSV lưu giải dạng số nguyên nên '08' thành 8; phải đệm lại đúng."""
        raw = pd.read_csv("data/xsmb.csv")
        assert (raw["prize7_1"].astype(str).str.len() < 2).any(), "dữ liệu không còn ca kiểm này"
        ObservationMatrix.from_frame(raw)  # không được ném lỗi

    def test_rejects_a_frame_missing_prize_columns(self) -> None:
        with pytest.raises(SchemaError, match="thiếu cột"):
            ObservationMatrix.from_frame(pd.DataFrame({"date": ["2025-01-01"]}))


class TestDailyRequest:
    def test_infers_target_date_from_anchor(self) -> None:
        request = DailyRequest.from_json({"anchor_date": "2026-09-06"})
        assert str(request.target_date.date()) == "2026-09-07"

    def test_rejects_a_target_that_is_not_the_next_day(self) -> None:
        with pytest.raises(SchemaError, match="ngay sau"):
            DailyRequest.from_json({"anchor_date": "2026-09-06", "target_date": "2026-09-20"})

    def test_rejects_top_k_outside_the_number_space(self) -> None:
        with pytest.raises(SchemaError, match="top_k"):
            DailyRequest.from_json({"anchor_date": "2026-09-06", "top_k": 500})


# ---------------------------------------------------------------------------
# Không rò rỉ thời gian — bất biến quan trọng nhất của cả module
# ---------------------------------------------------------------------------


class TestNoTemporalLeakage:
    def test_features_ignore_the_day_being_predicted(self, matrix: ObservationMatrix) -> None:
        before = build_features(matrix.counts, 200)
        tampered = matrix.counts.copy()
        tampered[200] = 0
        tampered[200, :LOTO_DRAWS_PER_DAY] = 1
        assert np.array_equal(before.values, build_features(tampered, 200).values)

    def test_features_ignore_every_later_day(self, matrix: ObservationMatrix) -> None:
        before = build_features(matrix.counts, 200)
        tampered = matrix.counts.copy()
        tampered[200:] = np.roll(tampered[200:], 17, axis=1)
        assert np.array_equal(before.values, build_features(tampered, 200).values)

    def test_training_table_labels_come_from_the_day_features_stop_at(
        self, matrix: ObservationMatrix
    ) -> None:
        """Nhãn của ngày t là kết quả ngày t; đặc trưng chỉ tới t-1."""
        x, y, _ = build_training_table(matrix.counts, start=250, stop=252)
        assert x.shape[0] == 2 * NUMBER_SPACE
        expected = np.concatenate(
            [(matrix.counts[250] > 0).astype(np.int8), (matrix.counts[251] > 0).astype(np.int8)]
        )
        assert np.array_equal(y, expected)

    def test_walk_forward_window_never_includes_the_predicted_day(
        self, matrix: ObservationMatrix
    ) -> None:
        validator = WalkForwardValidator(matrix.counts, window=100, warmup=120)
        for split in validator.splits(150, 160):
            assert split.train_stop == split.predict_day
            assert split.train_start < split.train_stop


class TestFeatureMatrix:
    def test_shape_matches_the_number_space(self, matrix: ObservationMatrix) -> None:
        built = build_features(matrix.counts, 200)
        assert built.values.shape == (NUMBER_SPACE, len(built.names))
        assert np.all(np.isfinite(built.values))

    def test_short_history_returns_zeros_with_the_right_width(self) -> None:
        """Lịch sử ngắn phải giữ nguyên hình dạng, không đổi số cột."""
        counts = synthetic_counts(300, seed=3)
        early = build_features(counts, 10)
        late = build_features(counts, 200)
        assert early.names == late.names
        assert np.all(early.values == 0.0)

    def test_select_keeps_requested_columns_in_order(self, matrix: ObservationMatrix) -> None:
        built = build_features(matrix.counts, 200)
        picked = built.select(["gap_days", "rate_7d"])
        assert picked.names == ("gap_days", "rate_7d")
        assert picked.values.shape == (NUMBER_SPACE, 2)

    def test_select_rejects_unknown_columns(self, matrix: ObservationMatrix) -> None:
        with pytest.raises(KeyError):
            build_features(matrix.counts, 200).select(["khong_ton_tai"])

    def test_matrix_rejects_mismatched_names(self) -> None:
        with pytest.raises(ValueError):
            FeatureMatrix(values=np.zeros((NUMBER_SPACE, 3)), names=("a", "b"))


# ---------------------------------------------------------------------------
# Bandit
# ---------------------------------------------------------------------------


class TestBanditContract:
    def test_rejects_duplicate_arms(self) -> None:
        with pytest.raises(BanditError, match="trùng"):
            DiscountedThompsonSamplingMAB(["a", "a"])

    def test_rejects_a_discount_outside_the_unit_interval(self) -> None:
        with pytest.raises(BanditError, match="discount"):
            DiscountedThompsonSamplingMAB(["a"], discount=1.5)

    def test_rejects_a_reward_outside_zero_one(self) -> None:
        mab = DiscountedThompsonSamplingMAB(["a"])
        with pytest.raises(BanditError, match="reward"):
            mab.update_reward("a", 1.5)

    def test_rejects_an_unknown_arm(self) -> None:
        mab = DiscountedThompsonSamplingMAB(["a"])
        with pytest.raises(BanditError, match="không tồn tại"):
            mab.update_reward("b", 1.0)

    def test_weights_form_a_distribution(self) -> None:
        mab = DiscountedThompsonSamplingMAB(["a", "b", "c"], seed=1)
        weights = mab.select_weights()
        assert sum(weights.values()) == pytest.approx(1.0)
        assert all(value >= 0.0 for value in weights.values())


class TestBanditLearns:
    def test_converges_to_the_better_arm(self) -> None:
        """Đối chứng dương: cánh tay tốt hơn phải giành phần lớn trọng số."""
        mab = DiscountedThompsonSamplingMAB(["tot", "te"], discount=1.0, seed=2)
        rng = np.random.default_rng(2)
        for _ in range(200):
            mab.update_batch({"tot": float(rng.random() < 0.60), "te": float(rng.random() < 0.20)})
        weights = mab.select_weights(draws=4000)
        assert weights["tot"] > 0.9

    def test_stays_undecided_between_identical_arms(self) -> None:
        """Đối chứng âm: hai cánh tay như nhau thì không được ưu ái cái nào."""
        mab = DiscountedThompsonSamplingMAB(["a", "b"], discount=1.0, seed=3)
        rng = np.random.default_rng(3)
        for _ in range(200):
            mab.update_batch({"a": float(rng.random() < 0.25), "b": float(rng.random() < 0.25)})
        weights = mab.select_weights(draws=4000)
        assert abs(weights["a"] - weights["b"]) < 0.45

    def test_discount_lets_it_follow_a_regime_change(self) -> None:
        """Cánh tay từng tốt rồi gãy phải mất trọng số; không chiết khấu thì không."""
        rng = np.random.default_rng(5)
        discounted = DiscountedThompsonSamplingMAB(["cu", "moi"], discount=0.9, seed=5)
        plain = DiscountedThompsonSamplingMAB(["cu", "moi"], discount=1.0, seed=5)
        for mab in (discounted, plain):
            local = np.random.default_rng(5)
            for _ in range(150):  # giai đoạn đầu: "cu" tốt
                mab.update_batch(
                    {"cu": float(local.random() < 0.7), "moi": float(local.random() < 0.2)}
                )
            for _ in range(60):  # đảo chiều: "cu" gãy
                mab.update_batch(
                    {"cu": float(local.random() < 0.1), "moi": float(local.random() < 0.7)}
                )
        _ = rng
        assert discounted.select_weights(draws=4000)["moi"] > 0.9
        assert (
            plain.select_weights(draws=4000)["moi"] < discounted.select_weights(draws=4000)["moi"]
        )

    def test_effective_sample_size_is_capped_by_the_discount(self) -> None:
        """Tính chất quyết định công suất: chiết khấu chặn cứng n hiệu dụng."""
        mab = DiscountedThompsonSamplingMAB(["a"], discount=0.98)
        for _ in range(2000):
            mab.update_reward("a", 1.0)
        assert mab.arms["a"].effective_n == pytest.approx(mab.max_effective_n, rel=0.02)
        assert mab.max_effective_n == pytest.approx(50.0, rel=1e-6)

    def test_power_floor_matches_the_standard_error_at_the_cap(self) -> None:
        mab = DiscountedThompsonSamplingMAB(["a"], discount=0.98)
        expected = float(np.sqrt(BASELINE_RATE * (1 - BASELINE_RATE) / 50.0))
        assert mab.power_floor(BASELINE_RATE) == pytest.approx(expected, rel=1e-9)

    def test_baseline_prior_starts_at_the_domain_rate(self) -> None:
        mab = DiscountedThompsonSamplingMAB.with_baseline_prior(
            ["a"], baseline=BASELINE_RATE, strength=8.0
        )
        alpha, beta = mab.arms["a"].posterior(mab.prior_alpha, mab.prior_beta)
        assert alpha / (alpha + beta) == pytest.approx(BASELINE_RATE, rel=1e-9)

    def test_noise_arm_does_not_beat_baseline(self) -> None:
        """Cánh tay thuần nhiễu ở đúng nền không được kết luận là vượt nền."""
        mab = DiscountedThompsonSamplingMAB.with_baseline_prior(
            ["nhieu"], baseline=BASELINE_RATE, discount=1.0, seed=7
        )
        rng = np.random.default_rng(7)
        for _ in range(400):
            mab.update_reward("nhieu", float(rng.random() < BASELINE_RATE))
        assert not mab.beats_baseline("nhieu", BASELINE_RATE)


class TestBanditSerialisation:
    def _trained(self) -> DiscountedThompsonSamplingMAB:
        mab = DiscountedThompsonSamplingMAB(["a", "b"], discount=0.95, seed=13)
        rng = np.random.default_rng(13)
        for _ in range(50):
            mab.update_batch({"a": float(rng.random() < 0.5), "b": float(rng.random() < 0.3)})
        return mab

    def test_json_round_trip_preserves_state(self) -> None:
        original = self._trained()
        restored = DiscountedThompsonSamplingMAB.from_dict(
            json.loads(json.dumps(original.to_dict()))
        )
        for name in original.arms:
            assert restored.arms[name].successes == pytest.approx(original.arms[name].successes)
            assert restored.arms[name].failures == pytest.approx(original.arms[name].failures)
        assert restored.total_updates == original.total_updates

    def test_round_trip_preserves_the_random_stream(self) -> None:
        """Không lưu trạng thái RNG thì mỗi lần khởi động lại đổi hành vi thăm dò."""
        original = self._trained()
        restored = DiscountedThompsonSamplingMAB.from_dict(
            json.loads(json.dumps(original.to_dict()))
        )
        assert original.select_weights(draws=64) == restored.select_weights(draws=64)

    def test_json_file_round_trip(self, tmp_path) -> None:
        original = self._trained()
        path = original.save_json(tmp_path / "nested" / "mab.json")
        assert path.exists()
        restored = DiscountedThompsonSamplingMAB.load_json(path)
        assert restored.to_dict()["arms"] == original.to_dict()["arms"]

    def test_pickle_file_round_trip(self, tmp_path) -> None:
        original = self._trained()
        restored = DiscountedThompsonSamplingMAB.load_pickle(
            original.save_pickle(tmp_path / "mab.pkl")
        )
        assert restored.to_dict()["arms"] == original.to_dict()["arms"]

    def test_missing_file_raises_a_clear_error(self, tmp_path) -> None:
        with pytest.raises(BanditError, match="không tìm thấy"):
            DiscountedThompsonSamplingMAB.load_json(tmp_path / "khong-co.json")

    def test_corrupt_json_raises_a_clear_error(self, tmp_path) -> None:
        broken = tmp_path / "hong.json"
        broken.write_text("{khong phai json", encoding="utf-8")
        with pytest.raises(BanditError, match="hỏng"):
            DiscountedThompsonSamplingMAB.load_json(broken)

    def test_unsupported_version_is_rejected(self) -> None:
        with pytest.raises(BanditError, match="phiên bản"):
            DiscountedThompsonSamplingMAB.from_dict({"version": 99})

    def test_arm_state_posterior_adds_the_prior(self) -> None:
        arm = ArmState(name="a", successes=3.0, failures=7.0)
        assert arm.posterior(1.0, 1.0) == (4.0, 8.0)
        assert arm.effective_n == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Trôi lệch khái niệm
# ---------------------------------------------------------------------------


class TestDriftDetection:
    def test_stays_quiet_on_a_stable_stream(self) -> None:
        """Đối chứng âm: chuỗi ổn định không được báo động."""
        detector = ConceptDriftDetector(method="both")
        rng = np.random.default_rng(21)
        verdicts = detector.update_many(rng.binomial(1, 0.24, 300).astype(float))
        assert sum(v.drifted for v in verdicts) == 0

    def test_detects_a_real_regime_change(self) -> None:
        """Đối chứng dương: đổi chế độ phải bị bắt."""
        detector = ConceptDriftDetector(method="both")
        rng = np.random.default_rng(22)
        detector.update_many(rng.binomial(1, 0.24, 200).astype(float))
        verdicts = detector.update_many(rng.binomial(1, 0.70, 200).astype(float))
        assert any(v.drifted for v in verdicts)

    def test_pure_fallback_matches_river_closely(self) -> None:
        """Đường lui phải là đường lui thật, không phải nhánh chết.

        Bản đầu của ``_PureAdwin`` xét cả n điểm cắt nên phải hiệu chỉnh δ/n,
        làm chặn quá rộng và không bao giờ báo động trên cùng dữ liệu mà river
        bắt được. Lưới cấp số nhân sửa điều đó.
        """
        delays = {}
        for prefer in (True, False):
            detector = ConceptDriftDetector(method="adwin", prefer_river=prefer)
            rng = np.random.default_rng(23)
            stable = detector.update_many(rng.binomial(1, 0.24, 300).astype(float))
            assert sum(v.drifted for v in stable) == 0
            after = detector.update_many(rng.binomial(1, 0.65, 300).astype(float))
            found = next((i for i, v in enumerate(after) if v.drifted), None)
            assert found is not None, f"prefer_river={prefer} không phát hiện được"
            delays[detector.backend] = found
        if "river" in delays and "pure" in delays:
            assert abs(delays["pure"] - delays["river"]) < 60

    def test_pure_adwin_drops_the_stale_half(self) -> None:
        """Ý nghĩa của 'adaptive windowing': cửa sổ phải co lại khi có trôi lệch."""
        adwin = _PureAdwin(delta=0.002)
        for _ in range(150):
            adwin.update(0.0)
        before = len(adwin.window)
        fired = any(adwin.update(1.0) for _ in range(150))
        assert fired
        assert len(adwin.window) < before

    def test_rejects_a_non_finite_observation(self) -> None:
        with pytest.raises(ValueError, match="hữu hạn"):
            ConceptDriftDetector().update(float("nan"))

    def test_reset_clears_state(self) -> None:
        detector = ConceptDriftDetector()
        detector.update_many(np.zeros(50))
        detector.reset()
        assert len(detector._history) == 0

    def test_ks_alone_detects_variance_change_without_mean_change(self) -> None:
        """KS bắt được kiểu trôi mà ADWIN bỏ sót: đổi hình dạng, giữ trung bình."""
        detector = ConceptDriftDetector(method="ks", reference_size=90, recent_size=40)
        rng = np.random.default_rng(24)
        detector.update_many(rng.normal(0.0, 0.05, 200))
        verdicts = detector.update_many(rng.normal(0.0, 1.0, 100))
        assert any(v.drifted for v in verdicts)


# ---------------------------------------------------------------------------
# Chế độ an toàn
# ---------------------------------------------------------------------------


class TestSafeMode:
    def test_threshold_defaults_to_the_domain_baseline(self) -> None:
        """Ngưỡng phải neo vào miền, không phải một con số chọn tay."""
        assert SafeModeController().threshold == pytest.approx(BASELINE_RATE)

    def test_stays_normal_while_performance_holds(self) -> None:
        controller = SafeModeController()
        for _ in range(20):
            controller.observe(0.35)
        assert controller.mode is Mode.NORMAL

    def test_enters_safe_mode_when_performance_falls_below_random(self) -> None:
        controller = SafeModeController()
        for _ in range(10):
            controller.observe(0.05)
        assert controller.mode is Mode.SAFE
        assert "Hit-Rate" in controller.reason

    def test_drift_forces_safe_mode_immediately(self) -> None:
        controller = SafeModeController()
        for _ in range(10):
            controller.observe(0.50)
        controller.observe(0.50, drifted=True)
        assert controller.mode is Mode.SAFE
        assert "trôi lệch" in controller.reason

    def test_model_failure_forces_safe_mode(self) -> None:
        controller = SafeModeController()
        controller.observe(0.50, model_failed=True)
        assert controller.mode is Mode.SAFE

    def test_recovery_needs_a_sustained_streak(self) -> None:
        """Một kỳ may mắn không đủ để rời chế độ an toàn."""
        controller = SafeModeController(window=3, recovery_days=4)
        for _ in range(5):
            controller.observe(0.02)
        assert controller.mode is Mode.SAFE
        controller.observe(0.90)
        assert controller.mode is Mode.SAFE, "một kỳ tốt không được kéo ra khỏi chế độ an toàn"
        for _ in range(5):
            controller.observe(0.90)
        assert controller.mode is Mode.NORMAL

    def test_safe_probabilities_sit_near_the_baseline(self) -> None:
        controller = SafeModeController()
        probabilities = controller.safe_probabilities(synthetic_counts(300, seed=31))
        assert abs(float(probabilities.mean()) - BASELINE_RATE) < 0.02
        assert float(probabilities.std()) < 0.02

    def test_apply_overrides_the_model_only_in_safe_mode(self) -> None:
        controller = SafeModeController()
        counts = synthetic_counts(200, seed=32)
        loud = np.full(NUMBER_SPACE, 0.9)
        assert np.array_equal(controller.apply(counts, loud), loud)
        controller.observe(0.0, model_failed=True)
        assert not np.array_equal(controller.apply(counts, loud), loud)

    def test_rejects_an_out_of_range_hit_rate(self) -> None:
        with pytest.raises(ValueError, match="hit_rate"):
            SafeModeController().observe(1.5)


# ---------------------------------------------------------------------------
# Chỉ số
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_baseline_scores_exactly_zero_skill(self) -> None:
        """Nền chấm chính nó phải ra 0; nếu không thì thước đo bị lệch."""
        tracker = PerformanceTracker()
        rng = np.random.default_rng(41)
        for _ in range(40):
            outcome = (
                np.bincount(
                    rng.integers(0, NUMBER_SPACE, LOTO_DRAWS_PER_DAY), minlength=NUMBER_SPACE
                )
                > 0
            ).astype(float)
            tracker.add(np.full(NUMBER_SPACE, BASELINE_RATE), outcome)
        report = tracker.report()
        assert report.logloss_skill == pytest.approx(0.0, abs=1e-12)
        assert report.paired_t == 0.0

    def test_an_oracle_scores_high(self) -> None:
        """Đối chứng dương cho thước đo: kẻ biết đáp án phải được điểm cao."""
        tracker = PerformanceTracker()
        rng = np.random.default_rng(42)
        for _ in range(30):
            outcome = (
                np.bincount(
                    rng.integers(0, NUMBER_SPACE, LOTO_DRAWS_PER_DAY), minlength=NUMBER_SPACE
                )
                > 0
            ).astype(float)
            tracker.add(np.where(outcome > 0, 0.95, 0.05), outcome)
        report = tracker.report()
        assert report.logloss_skill > 0.5
        assert report.beats_baseline
        assert report.hit_rate_at[10] > 9.0

    def test_random_hit_rate_is_the_honest_comparison_point(self) -> None:
        """Mốc so cho Top-K là K/100 × số con thực về, không phải 0."""
        tracker = PerformanceTracker()
        rng = np.random.default_rng(43)
        for _ in range(50):
            outcome = (
                np.bincount(
                    rng.integers(0, NUMBER_SPACE, LOTO_DRAWS_PER_DAY), minlength=NUMBER_SPACE
                )
                > 0
            ).astype(float)
            tracker.add(np.full(NUMBER_SPACE, BASELINE_RATE), outcome)
        report = tracker.report()
        assert report.random_hit_rate_at[10] == pytest.approx(report.hit_rate_at[10], rel=0.25)

    def test_score_day_rejects_wrong_shapes(self) -> None:
        with pytest.raises(ValueError):
            score_day(np.zeros(50), np.zeros(NUMBER_SPACE))

    def test_score_day_rejects_probabilities_outside_zero_one(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            score_day(np.full(NUMBER_SPACE, 1.5), np.zeros(NUMBER_SPACE))

    def test_report_on_empty_tracker_is_an_error_not_a_zero(self) -> None:
        with pytest.raises(ValueError, match="chưa có kỳ nào"):
            PerformanceTracker().report()


class TestEconomics:
    def test_break_even_rate_is_above_the_baseline(self) -> None:
        """Con số đóng khung mọi thứ: phải hơn nền +21% mới hòa vốn."""
        economics = EconomicModel()
        assert economics.break_even_rate > BASELINE_RATE
        assert economics.required_relative_lift() == pytest.approx(0.21, abs=0.01)

    def test_baseline_edge_is_negative(self) -> None:
        assert EconomicModel().baseline_edge < 0

    def test_rejects_a_payout_that_cannot_win(self) -> None:
        with pytest.raises(ValueError, match="payout"):
            EconomicModel(stake=80.0, payout=23.0)


# ---------------------------------------------------------------------------
# Mô hình
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def training(matrix: ObservationMatrix):
    """Bảng huấn luyện dùng chung cho các phép kiểm mô hình."""
    return build_training_table(matrix.counts, start=180, stop=280)


class TestModels:
    def test_tabular_booster_returns_probabilities(self, training, matrix) -> None:
        x, y, _ = training
        model = TabularBooster()
        model.fit(x, y)
        probabilities = model.predict_proba(build_features(matrix.counts, 280).values)
        assert probabilities.shape == (NUMBER_SPACE,)
        assert np.all((probabilities > 0.0) & (probabilities < 1.0))

    def test_tabular_booster_refuses_single_class_labels(self, training) -> None:
        x, _, _ = training
        with pytest.raises(ValueError, match="cả hai lớp"):
            TabularBooster().fit(x, np.zeros(x.shape[0], dtype=int))

    def test_predict_before_fit_is_an_error(self) -> None:
        with pytest.raises(RuntimeError, match="fit"):
            TabularBooster().predict_proba(np.zeros((5, 3)))

    def test_ranking_booster_output_is_calibrated_to_probabilities(self, training, matrix) -> None:
        """Điểm xếp hạng không phải xác suất; phải hiệu chỉnh trước khi dùng."""
        x, y, _ = training
        model = RankingBooster()
        model.fit(x, y)
        probabilities = model.predict_proba(build_features(matrix.counts, 280).values)
        assert np.all((probabilities >= 0.0) & (probabilities <= 1.0))
        if CAPABILITIES.lightgbm is not None:
            assert model.is_calibrated

    def test_ranking_booster_rejects_ragged_groups(self, training) -> None:
        x, y, _ = training
        with pytest.raises(ValueError, match="chia hết"):
            RankingBooster().fit(x[:150], y[:150])

    def test_temporal_model_is_calibrated_near_the_baseline(self, matrix) -> None:
        """Hồi quy: bản dùng pos_weight khai báo trung bình 0.49 so với nền 0.24."""
        model = TemporalSequenceModel(epochs=25)
        model.fit_sequence(matrix.hits)
        probabilities = model.predict_sequence(matrix.hits)
        assert abs(float(probabilities.mean()) - BASELINE_RATE) < 0.06

    def test_temporal_linear_fallback_works(self, matrix) -> None:
        model = TemporalSequenceModel()
        model.backend = "linear"
        model.fit_sequence(matrix.hits)
        probabilities = model.predict_sequence(matrix.hits)
        assert probabilities.shape == (NUMBER_SPACE,)
        assert np.all(np.isfinite(probabilities))

    def test_gru_capacity_exceeds_the_available_observations(self) -> None:
        """Cảnh báo dung lượng phải kiểm được ở MỌI môi trường, kể cả không torch.

        Bản đầu của phép kiểm này gọi ``parameter_count``, vốn phân nhánh theo
        backend, nên nó đạt trên máy có PyTorch và đổ trên CI (không có torch)
        với 1 401 tham số của đường lui tuyến tính. Khẳng định cần kiểm là về
        *kiến trúc GRU*, nên phải hỏi hàm số học thuần.
        """
        gru = TemporalSequenceModel.gru_parameter_count(64)
        assert gru == 38_372
        observations = 391 * NUMBER_SPACE
        assert gru > 0.9 * observations, "GRU 64 chiều xấp xỉ một tham số cho mỗi quan sát"

    def test_parameter_count_reports_the_backend_actually_running(self) -> None:
        """Báo số tham số của GRU khi đang chạy tuyến tính là nói sai."""
        model = TemporalSequenceModel(hidden_size=64, lookback=14)
        if model.backend == "torch":
            assert model.parameter_count == TemporalSequenceModel.gru_parameter_count(64)
        else:
            assert model.parameter_count == 14 * NUMBER_SPACE + 1

    def test_temporal_model_needs_more_days_than_the_lookback(self) -> None:
        with pytest.raises(ValueError, match="cần hơn"):
            TemporalSequenceModel(lookback=14).fit_sequence(np.ones((10, NUMBER_SPACE)))


# ---------------------------------------------------------------------------
# Chọn đặc trưng
# ---------------------------------------------------------------------------


class TestFeatureSelection:
    def test_keeps_an_informative_column_and_drops_noise(self) -> None:
        """Đối chứng hai chiều trên dữ liệu có tín hiệu cấy sẵn."""
        rng = np.random.default_rng(51)
        signal = rng.normal(size=800)
        noise = rng.normal(size=(800, 4))
        x = np.column_stack([signal, noise])
        y = (signal + rng.normal(scale=0.3, size=800) > 0).astype(int)
        names = ("tin_hieu", "nhieu_1", "nhieu_2", "nhieu_3", "nhieu_4")

        model = TabularBooster()
        model.fit(x, y)
        result = select_features(model._model, x, y, names)
        assert result.kept[0] == "tin_hieu"
        assert result.importance["tin_hieu"] > max(result.importance[name] for name in names[1:])

    def test_never_returns_an_empty_feature_set(self) -> None:
        """Không cột nào vượt ngưỡng vẫn phải giữ tối thiểu vài cột."""
        rng = np.random.default_rng(52)
        x = rng.normal(size=(400, 5))
        y = rng.integers(0, 2, 400)
        model = TabularBooster()
        model.fit(x, y)
        result = select_features(model._model, x, y, tuple(f"c{i}" for i in range(5)), epsilon=1e9)
        assert len(result.kept) >= 3

    def test_rejects_a_name_count_mismatch(self) -> None:
        with pytest.raises(ValueError, match="cột"):
            select_features(None, np.zeros((10, 3)), np.zeros(10), ("a", "b"))


# ---------------------------------------------------------------------------
# Kiểm định cuốn chiếu
# ---------------------------------------------------------------------------


class TestWalkForwardValidator:
    def test_rejects_a_warmup_that_is_too_short(self, matrix) -> None:
        with pytest.raises(ValueError, match="warmup"):
            WalkForwardValidator(matrix.counts, warmup=10)

    def test_rejects_an_evaluation_range_inside_warmup(self, matrix) -> None:
        validator = WalkForwardValidator(matrix.counts, warmup=120)
        with pytest.raises(ValueError, match="warmup"):
            validator.evaluate(TabularBooster, start=50, stop=100)

    def test_evaluates_every_day_in_range(self, matrix) -> None:
        validator = WalkForwardValidator(matrix.counts, window=120, warmup=120, refit_every=30)
        report = validator.evaluate(TabularBooster, start=260, stop=280)
        assert report.days == 20
        assert np.isfinite(report.logloss)


# ---------------------------------------------------------------------------
# Tầng điều phối
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pipeline(matrix: ObservationMatrix) -> ContinuousLearningPipeline:
    """Pipeline dùng chung, tắt các cánh tay nặng để kiểm thử chạy nhanh."""
    config = PipelineConfig(
        window=120, warmup=120, refit_every=40, use_temporal=False, use_ranking=False
    )
    return ContinuousLearningPipeline(matrix, config)


class TestPipeline:
    def test_baseline_is_registered_as_a_competing_arm(self, pipeline) -> None:
        """Điểm mấu chốt của kiến trúc: nền phải cạnh tranh sòng phẳng."""
        assert "baseline" in pipeline.bandit.arms

    def test_run_produces_one_result_per_day(self, pipeline, matrix) -> None:
        results = pipeline.run(start=260, stop=275)
        assert len(results) == 15
        assert [r.day_index for r in results] == list(range(260, 275))
        assert all(len(r.top_k) == pipeline.config.top_k for r in results)
        assert all(len(set(r.top_k)) == pipeline.config.top_k for r in results)

    def test_probabilities_stay_a_valid_distribution_per_number(self, pipeline) -> None:
        probabilities, weights, per_arm = pipeline.predict_day(280)
        assert probabilities.shape == (NUMBER_SPACE,)
        assert np.all((probabilities > 0.0) & (probabilities < 1.0))
        assert sum(weights.values()) == pytest.approx(1.0)
        assert set(per_arm) >= {"baseline", "frequency", "gap_hazard"}

    def test_arms_are_rewarded_on_their_own_picks(self, pipeline, matrix) -> None:
        """Chấm mỗi cánh tay theo lựa chọn của chính nó, nếu không bandit mù."""
        result = pipeline.step(285)
        assert set(result.arm_rewards) >= {"baseline", "frequency", "gap_hazard"}
        assert all(0.0 <= value <= 1.0 for value in result.arm_rewards.values())

    def test_rejects_a_range_before_warmup(self, pipeline) -> None:
        with pytest.raises(ValueError, match="warmup"):
            pipeline.run(start=10, stop=50)

    def test_predict_next_requires_the_anchor_to_be_the_last_day(
        self, matrix: ObservationMatrix
    ) -> None:
        pipeline = ContinuousLearningPipeline(
            matrix,
            PipelineConfig(window=120, warmup=120, use_temporal=False, use_ranking=False),
        )
        request = DailyRequest(
            anchor_date=matrix.dates[-1] - pd.Timedelta(days=5),
            target_date=matrix.dates[-1] - pd.Timedelta(days=4),
        )
        with pytest.raises(ValueError, match="ngày cuối"):
            pipeline.predict_next(request)

    def test_predict_next_returns_a_serialisable_record(self, matrix: ObservationMatrix) -> None:
        pipeline = ContinuousLearningPipeline(
            matrix,
            PipelineConfig(window=120, warmup=120, use_temporal=False, use_ranking=False),
        )
        request = DailyRequest(
            anchor_date=matrix.dates[-1], target_date=matrix.dates[-1] + pd.Timedelta(days=1)
        )
        record = pipeline.predict_next(request)
        json.dumps(record)  # không được ném lỗi
        assert len(record["top_k"]) == request.top_k
        assert all(len(entry["number"]) == 2 for entry in record["top_k"])
        assert record["baseline_rate"] == pytest.approx(BASELINE_RATE)


# ---------------------------------------------------------------------------
# Đối chứng hai chiều cho toàn kiến trúc
# ---------------------------------------------------------------------------


def planted_counts(n_days: int, seed: int, carried: int = 12) -> np.ndarray:
    """Chuỗi cấy 'bạc nhớ' thuần thời gian, giữ ĐÚNG 27 lần rút mỗi kỳ.

    Cấy ở mức *lần rút*, không ở mức đếm: thay giá trị của ``carried`` ô rút
    (những ô có giá trị không thuộc tập hôm qua) bằng các con của hôm qua chưa
    có mặt hôm nay. Số lần rút không đổi nên ``ObservationMatrix`` chấp nhận,
    và thông tin cấy vào thuần là thứ tự thời gian.

    Bản đầu của hàm này bật/tắt trực tiếp trên ma trận đếm và bị chính
    ``ObservationMatrix`` từ chối vì làm hỏng bất biến 27 con — một minh chứng
    rằng hợp đồng dữ liệu bắt được lỗi thật, kể cả lỗi trong bộ kiểm thử.
    """
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, NUMBER_SPACE, size=(n_days, LOTO_DRAWS_PER_DAY))
    for day in range(1, n_days):
        yesterday = set(draws[day - 1].tolist())
        today = set(draws[day].tolist())
        slots = [i for i, value in enumerate(draws[day]) if value not in yesterday]
        candidates = sorted(yesterday - today)
        k = min(carried, len(slots), len(candidates))
        if k:
            for slot, value in zip(
                rng.choice(slots, k, replace=False),
                rng.choice(candidates, k, replace=False),
                strict=True,
            ):
                draws[day, slot] = value
    counts = np.zeros((n_days, NUMBER_SPACE), dtype=np.int16)
    np.add.at(
        counts,
        (np.repeat(np.arange(n_days), LOTO_DRAWS_PER_DAY), draws.ravel()),
        1,
    )
    return counts


class TestArchitectureIsTwoSided:
    """Luận điểm kiến trúc chính, kiểm cả hai chiều.

    Im lặng khi không có tín hiệu thì dễ — một hàm trả hằng số cũng làm được.
    Điều phải chứng minh là hệ thống *không* im lặng khi tín hiệu có thật.
    """

    @staticmethod
    def _run(counts: np.ndarray):
        matrix = ObservationMatrix(
            dates=pd.date_range("2025-01-01", periods=counts.shape[0], freq="D"),
            counts=counts,
        )
        pipeline = ContinuousLearningPipeline(
            matrix,
            PipelineConfig(
                window=150, warmup=120, refit_every=30, use_temporal=False, use_ranking=False
            ),
        )
        results = pipeline.run(start=200, stop=counts.shape[0])
        return pipeline, results, pipeline.tracker.report()

    def test_planted_signal_is_found_and_baseline_yields(self) -> None:
        """Đối chứng dương: có bạc nhớ thật thì nền phải nhường trọng số."""
        pipeline, results, report = self._run(planted_counts(360, seed=61))
        weights = pipeline.bandit.select_weights(draws=4000)
        assert report.beats_baseline
        assert report.logloss_skill > 0.1
        assert report.hit_rate_at[10] > 2 * report.random_hit_rate_at[10]
        assert weights["baseline"] < 0.05
        assert sum(1 for r in results if r.mode == "safe") == 0

    def test_fair_data_keeps_the_system_quiet(self) -> None:
        """Đối chứng âm: chuỗi công bằng không được kết luận là có tín hiệu."""
        pipeline, results, report = self._run(synthetic_counts(360, seed=61))
        assert not report.beats_baseline
        assert abs(report.logloss_skill) < 0.01
        # Không có tín hiệu thì chế độ an toàn phải bật phần lớn thời gian.
        assert sum(1 for r in results if r.mode == "safe") > len(results) // 3
        assert not any(
            pipeline.bandit.beats_baseline(arm, BASELINE_RATE) for arm in pipeline.bandit.arms
        )
