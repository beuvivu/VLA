"""Tầng điều phối: nối toàn bộ luồng từ JSON đầu vào tới báo cáo chỉ số.

Luồng
------

::

    JSON đầu vào → ObservationMatrix (kiểm hợp đồng)
                 → sinh đặc trưng (không rò rỉ)
                 → chọn đặc trưng bằng SHAP
                 → mỗi "cánh tay" khai báo xác suất riêng
                 → MAB trộn theo trọng số hậu nghiệm
                 → chế độ an toàn có quyền phủ quyết
                 → Top-K
                 → kết quả thật → phần thưởng → cập nhật MAB
                                → sai số → phát hiện trôi lệch
                                → chỉ số → nhật ký

Thứ tự ở hai bước cuối là có chủ đích: **chế độ an toàn đứng sau MAB**, không
phải trước. MAB tối ưu trong giả định "có ít nhất một cánh tay đáng dùng"; chế
độ an toàn là nơi duy nhất chất vấn chính giả định đó, nên nó phải có tiếng nói
sau cùng.

Nền là một cánh tay, và điều đó quyết định
-------------------------------------------

``baseline`` được đăng ký như một cánh tay bình thường, cạnh tranh sòng phẳng
với mọi mô hình. Nhờ vậy hệ thống có thể *kết luận bằng dữ liệu* rằng không mô
hình nào đáng tin — trọng số dồn về nền — thay vì phải có người quyết định điều
đó. Không có cánh tay nền thì trọng số luôn bị chuẩn hóa giữa các mô hình, và
hệ thống không có cách nào diễn đạt câu "không cái nào đáng dùng".
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from ml_engine.bandit import DiscountedThompsonSamplingMAB
from ml_engine.capabilities import CAPABILITIES
from ml_engine.drift import ConceptDriftDetector
from ml_engine.fallback import SafeModeController
from ml_engine.features import build_features, build_training_table
from ml_engine.metrics import PerformanceTracker
from ml_engine.models import RankingBooster, TabularBooster, TemporalSequenceModel
from ml_engine.schema import BASELINE_RATE, NUMBER_SPACE, DailyRequest, ObservationMatrix
from ml_engine.selection import select_features

LOGGER: Final[logging.Logger] = logging.getLogger("ml_engine")

#: Mức K dùng để tính phần thưởng cho MAB.
REWARD_K: Final[int] = 10


@dataclass
class PipelineConfig:
    """Tham số vận hành của pipeline.

    Attributes:
        window: Số ngày trong cửa sổ huấn luyện trượt.
        warmup: Số ngày đầu chỉ tích lũy, không dự đoán.
        refit_every: Khớp lại mô hình sau mỗi bấy nhiêu ngày.
        top_k: Số con trả về trong danh sách gợi ý.
        discount: Hệ số chiết khấu của MAB.
        use_temporal: Có bật cánh tay mô hình chuỗi sâu không.
        use_ranking: Có bật cánh tay LambdaMART không.
        feature_epsilon: Ngưỡng loại đặc trưng theo tầm quan trọng.
        seed: Hạt giống, để tái lập được.
    """

    window: int = 240
    warmup: int = 120
    refit_every: int = 21
    top_k: int = 10
    discount: float = 0.98
    use_temporal: bool = True
    use_ranking: bool = True
    feature_epsilon: float = 1e-4
    seed: int = 0


@dataclass
class DayResult:
    """Kết quả xử lý một kỳ.

    Attributes:
        day_index: Chỉ số ngày trong ma trận quan sát.
        date: Ngày được dự đoán.
        probabilities: Xác suất cuối cùng sau khi trộn và qua chế độ an toàn.
        top_k: Danh sách con được gợi ý.
        arm_weights: Trọng số MAB tại thời điểm dự đoán.
        mode: Chế độ vận hành khi dự đoán.
        drifted: Có phát hiện trôi lệch sau khi biết kết quả không.
        hits_in_top_k: Số con trong Top-K thực sự về.
        arm_rewards: Phần thưởng của từng cánh tay ở kỳ này.
    """

    day_index: int
    date: pd.Timestamp
    probabilities: np.ndarray
    top_k: list[int]
    arm_weights: dict[str, float]
    mode: str
    drifted: bool
    hits_in_top_k: int
    arm_rewards: dict[str, float] = field(default_factory=dict)


class ContinuousLearningPipeline:
    """Hệ thống học tiếp diễn với MAB, phát hiện trôi lệch và chế độ an toàn.

    Ví dụ:
        >>> import pandas as pd
        >>> from ml_engine.schema import ObservationMatrix
        >>> frame = pd.read_csv("data/xsmb.csv")  # doctest: +SKIP
        >>> pipeline = ContinuousLearningPipeline(  # doctest: +SKIP
        ...     ObservationMatrix.from_frame(frame)
        ... )
        >>> report = pipeline.run(start=300, stop=320)  # doctest: +SKIP

    Attributes:
        observations: Ma trận quan sát đã kiểm hợp đồng.
        config: Tham số vận hành.
        bandit: Bộ trộn trọng số theo bằng chứng.
        drift: Bộ phát hiện trôi lệch.
        safe_mode: Bộ điều khiển chế độ an toàn.
        tracker: Bộ tích lũy chỉ số.
    """

    def __init__(
        self,
        observations: ObservationMatrix,
        config: PipelineConfig | None = None,
    ) -> None:
        self.observations = observations
        self.config = config or PipelineConfig()
        self.arm_builders = self._build_arms()

        self.bandit = DiscountedThompsonSamplingMAB.with_baseline_prior(
            list(self.arm_builders),
            baseline=BASELINE_RATE,
            discount=self.config.discount,
            seed=self.config.seed,
        )
        self.drift = ConceptDriftDetector(method="both")
        self.safe_mode = SafeModeController()
        self.tracker = PerformanceTracker()
        self.selected_features: list[str] | None = None
        self._fitted: dict[str, Any] = {}
        self._fitted_at = -1

    # -- Cánh tay --------------------------------------------------------

    def _build_arms(self) -> dict[str, Callable[[], Any]]:
        """Danh mục cánh tay đang bật, theo cấu hình và thư viện sẵn có."""
        arms: dict[str, Callable[[], Any]] = {
            "baseline": lambda: None,
            "frequency": lambda: None,
            "gap_hazard": lambda: None,
            "tabular_boosting": lambda: TabularBooster(),
        }
        if self.config.use_ranking:
            arms["ranking_lambdamart"] = lambda: RankingBooster()
        if self.config.use_temporal and CAPABILITIES.torch is not None:
            arms["temporal_sequence"] = lambda: TemporalSequenceModel()
        return arms

    @staticmethod
    def _frequency_probabilities(counts: np.ndarray) -> np.ndarray:
        """Cánh tay tần suất: tỉ lệ về kinh nghiệm, co rút nhẹ về nền."""
        if counts.shape[0] < 30:
            return np.full(NUMBER_SPACE, BASELINE_RATE)
        empirical = (counts > 0).mean(axis=0)
        weight = min(counts.shape[0] / (counts.shape[0] + 200.0), 1.0)
        return weight * empirical + (1.0 - weight) * BASELINE_RATE

    @staticmethod
    def _gap_hazard_probabilities(counts: np.ndarray, *, max_gap: int = 12) -> np.ndarray:
        """Cánh tay nhịp gan: nguy cơ về theo số ngày đã gan."""
        hits = counts > 0
        n = hits.shape[0]
        if n < 60:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        successes = np.zeros(max_gap + 1)
        totals = np.zeros(max_gap + 1)
        gaps = np.zeros(NUMBER_SPACE, dtype=np.int64)
        for day in range(n):
            bucket = np.minimum(gaps, max_gap)
            np.add.at(totals, bucket, 1)
            np.add.at(successes, bucket, hits[day].astype(float))
            gaps = np.where(hits[day], 0, gaps + 1)

        prior = 40.0
        hazard = (successes + prior * BASELINE_RATE) / (totals + prior)
        ever = hits.any(axis=0)
        last = np.where(ever, n - 1 - np.argmax(hits[::-1], axis=0), -1)
        current = np.minimum(n - 1 - last, max_gap)
        return hazard[current]

    # -- Khớp và dự đoán -------------------------------------------------

    def _refit(self, day: int) -> None:
        """Khớp lại các cánh tay có tham số, dùng cửa sổ trượt tới ``day``."""
        start = max(0, day - self.config.window)
        x, y, names = build_training_table(self.observations.counts, start=start, stop=day)
        if len(np.unique(y)) < 2:
            LOGGER.warning("Ngày %d: nhãn chỉ có một lớp, bỏ qua lần khớp này", day)
            return

        fitted: dict[str, Any] = {}

        probe = TabularBooster()
        try:
            probe.fit(x, y)
            result = select_features(probe._model, x, y, names, epsilon=self.config.feature_epsilon)
            self.selected_features = result.kept
            LOGGER.info("Ngày %d: %s", day, result.describe())
        except Exception as error:
            LOGGER.warning("Ngày %d: chọn đặc trưng thất bại (%s); giữ toàn bộ cột", day, error)
            self.selected_features = list(names)

        keep = [names.index(name) for name in self.selected_features if name in names]
        x_selected = x[:, keep]

        for name, builder in self.arm_builders.items():
            model = builder()
            if model is None:
                continue
            try:
                if isinstance(model, TemporalSequenceModel):
                    model.fit_sequence(self.observations.hits[start:day])
                elif isinstance(model, RankingBooster):
                    # LambdaMART cần nhóm nguyên vẹn 100 con mỗi ngày, nên nó
                    # dùng toàn bộ cột thay vì tập đã lọc — lọc cột không đổi số
                    # hàng, nhưng giữ hai đường đi khác nhau ở đây làm mã khó
                    # theo dõi hơn là nó tiết kiệm.
                    model.fit(x, y)
                else:
                    model.fit(x_selected, y)
                fitted[name] = model
            except Exception as error:
                LOGGER.error("Ngày %d: cánh tay %s khớp lỗi: %s", day, name, error)

        self._fitted = fitted
        self._fitted_at = day

    def arm_probabilities(self, day: int) -> dict[str, np.ndarray]:
        """Xác suất do từng cánh tay khai báo cho ngày ``day``.

        Args:
            day: Chỉ số ngày cần dự đoán.

        Returns:
            Ánh xạ tên cánh tay sang mảng ``(100,)`` xác suất.
        """
        past = self.observations.counts[:day]
        matrix = build_features(self.observations.counts, day)
        if self.selected_features:
            keep = [matrix.names.index(n) for n in self.selected_features if n in matrix.names]
            selected = matrix.values[:, keep]
        else:
            selected = matrix.values

        output: dict[str, np.ndarray] = {
            "baseline": np.full(NUMBER_SPACE, BASELINE_RATE),
            "frequency": self._frequency_probabilities(past),
            "gap_hazard": self._gap_hazard_probabilities(past),
        }
        for name, model in self._fitted.items():
            try:
                if isinstance(model, TemporalSequenceModel):
                    output[name] = model.predict_sequence(self.observations.hits[:day])
                elif isinstance(model, RankingBooster):
                    output[name] = model.predict_proba(matrix.values)
                else:
                    output[name] = model.predict_proba(selected)
            except Exception as error:
                LOGGER.error("Ngày %d: cánh tay %s dự đoán lỗi: %s", day, name, error)
        for name in self.arm_builders:
            output.setdefault(name, np.full(NUMBER_SPACE, BASELINE_RATE))
        return output

    def predict_day(self, day: int) -> tuple[np.ndarray, dict[str, float], dict[str, np.ndarray]]:
        """Dự đoán một kỳ: trộn các cánh tay rồi cho chế độ an toàn phủ quyết.

        Args:
            day: Chỉ số ngày cần dự đoán.

        Returns:
            Bộ ba ``(xác suất cuối, trọng số cánh tay, xác suất từng cánh tay)``.
        """
        if day - self._fitted_at >= self.config.refit_every or not self._fitted:
            self._refit(day)

        per_arm = self.arm_probabilities(day)
        weights = self.bandit.select_weights()
        blended = np.zeros(NUMBER_SPACE)
        for name, probability in per_arm.items():
            blended += weights.get(name, 0.0) * probability
        # Chuẩn hóa lại phòng trường hợp một cánh tay vắng mặt: bỏ qua bước này
        # thì tổng trọng số nhỏ hơn 1 và xác suất bị co về 0 một cách âm thầm.
        total = sum(weights.get(name, 0.0) for name in per_arm)
        if total > 0:
            blended /= total

        final = self.safe_mode.apply(self.observations.counts[:day], blended)
        return final, weights, per_arm

    # -- Vòng lặp chính --------------------------------------------------

    def step(self, day: int) -> DayResult:
        """Xử lý trọn một kỳ: dự đoán, đối chiếu kết quả, cập nhật trạng thái.

        Args:
            day: Chỉ số ngày.

        Returns:
            Kết quả của kỳ đó.
        """
        probabilities, weights, per_arm = self.predict_day(day)
        outcome = (self.observations.counts[day] > 0).astype(float)

        top_k = np.argsort(-probabilities)[: self.config.top_k]
        hits_in_top_k = int(outcome[top_k].sum())

        # Phần thưởng cho mỗi cánh tay: tỉ lệ trúng trong Top-K *của riêng nó*.
        # Chấm từng cánh tay theo lựa chọn của chính nó, không theo lựa chọn
        # chung — nếu không thì mọi cánh tay nhận cùng một phần thưởng và bandit
        # không học được gì.
        rewards = {
            name: float(outcome[np.argsort(-probability)[:REWARD_K]].sum() / REWARD_K)
            for name, probability in per_arm.items()
        }
        self.bandit.update_batch(rewards)

        score = self.tracker.add(probabilities, outcome)
        verdict = self.drift.update(1.0 - hits_in_top_k / self.config.top_k)
        self.safe_mode.observe(
            hits_in_top_k / self.config.top_k, drifted=verdict.drifted, day_index=day
        )

        return DayResult(
            day_index=day,
            date=self.observations.dates[day],
            probabilities=probabilities,
            top_k=[int(n) for n in top_k],
            arm_weights=weights,
            mode=self.safe_mode.mode.value,
            drifted=verdict.drifted,
            hits_in_top_k=hits_in_top_k,
            arm_rewards=rewards,
        )

    def run(self, *, start: int, stop: int) -> list[DayResult]:
        """Chạy toàn bộ vòng học tiếp diễn trên ``[start, stop)``.

        Args:
            start: Ngày đầu tiên được dự đoán.
            stop: Ngày cuối, không bao gồm.

        Returns:
            Danh sách kết quả theo ngày.

        Raises:
            ValueError: Khi khoảng ngày không hợp lệ.
        """
        if not self.config.warmup <= start < stop <= self.observations.n_days:
            raise ValueError(
                f"khoảng [{start}, {stop}) phải nằm sau warmup={self.config.warmup} "
                f"và trong {self.observations.n_days} ngày"
            )
        results = []
        for day in range(start, stop):
            results.append(self.step(day))
            if (day - start) % 25 == 0:
                LOGGER.info(
                    "Ngày %d/%d · chế độ=%s · trúng@%d=%d",
                    day,
                    stop,
                    results[-1].mode,
                    self.config.top_k,
                    results[-1].hits_in_top_k,
                )
        return results

    def predict_next(self, request: DailyRequest) -> dict[str, Any]:
        """Dự đoán cho kỳ kế tiếp, dùng trong vận hành hằng ngày.

        Args:
            request: Yêu cầu đã kiểm hợp lệ.

        Returns:
            Bản ghi kết quả, sẵn sàng ghi ra JSON.

        Raises:
            ValueError: Khi ``anchor_date`` không phải ngày cuối của lịch sử.
        """
        last_date = self.observations.dates[-1]
        if request.anchor_date.normalize() != last_date.normalize():
            raise ValueError(
                f"anchor_date ({request.anchor_date.date()}) phải là ngày cuối của "
                f"lịch sử ({last_date.date()})"
            )

        day = self.observations.n_days
        probabilities, weights, per_arm = self.predict_day(day)
        order = np.argsort(-probabilities)[: request.top_k]
        return {
            "anchor_date": str(request.anchor_date.date()),
            "target_date": str(request.target_date.date()),
            "mode": self.safe_mode.mode.value,
            "mode_reason": self.safe_mode.reason,
            "top_k": [
                {"number": f"{int(n):02d}", "probability": float(probabilities[n])} for n in order
            ],
            "arm_weights": {name: float(weight) for name, weight in weights.items()},
            "arms_available": sorted(per_arm),
            "baseline_rate": BASELINE_RATE,
            "selected_features": self.selected_features,
        }


def summarise(pipeline: ContinuousLearningPipeline, results: list[DayResult]) -> dict[str, Any]:
    """Gộp kết quả chạy thành báo cáo JSON được.

    Args:
        pipeline: Pipeline đã chạy xong.
        results: Danh sách kết quả theo ngày.

    Returns:
        Báo cáo tổng hợp.
    """
    report = pipeline.tracker.report()
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "capabilities": CAPABILITIES.summary(),
        "days": report.days,
        "baseline_rate": BASELINE_RATE,
        "metrics": {
            "logloss": report.logloss,
            "brier": report.brier,
            "logloss_skill": report.logloss_skill,
            "brier_skill": report.brier_skill,
            "paired_t": report.paired_t,
            "beats_baseline": report.beats_baseline,
            "hit_rate_at": {str(k): v for k, v in report.hit_rate_at.items()},
            "random_hit_rate_at": {str(k): v for k, v in report.random_hit_rate_at.items()},
            "precision_at": {str(k): v for k, v in report.precision_at.items()},
            "recall_at": {str(k): v for k, v in report.recall_at.items()},
            "profit_ratio": {str(k): v for k, v in report.profit_ratio.items()},
        },
        "bandit": {
            "arms": pipeline.bandit.report(BASELINE_RATE),
            "max_effective_n": pipeline.bandit.max_effective_n,
            "power_floor": pipeline.bandit.power_floor(BASELINE_RATE),
        },
        "drift": {
            "backend": pipeline.drift.backend,
            "detections": pipeline.drift.drift_count,
            "days_in_safe_mode": sum(1 for r in results if r.mode == "safe"),
        },
        "safe_mode": pipeline.safe_mode.state(),
        "selected_features": pipeline.selected_features,
    }


def main(argv: list[str] | None = None) -> int:
    """Điểm vào dòng lệnh.

    Args:
        argv: Tham số dòng lệnh; mặc định lấy từ ``sys.argv``.

    Returns:
        Mã thoát: 0 khi thành công, 1 khi lỗi dữ liệu hoặc cấu hình.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default="data/xsmb.csv", help="tệp kết quả thô")
    parser.add_argument("--out", default="data/research/ml_engine_report.json")
    parser.add_argument("--start", type=int, default=None, help="ngày đầu; mặc định warmup")
    parser.add_argument("--stop", type=int, default=None, help="ngày cuối; mặc định hết lịch sử")
    parser.add_argument("--warmup", type=int, default=120)
    parser.add_argument("--window", type=int, default=240)
    parser.add_argument("--refit-every", type=int, default=21)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--discount", type=float, default=0.98)
    parser.add_argument("--no-temporal", action="store_true", help="tắt cánh tay GRU")
    parser.add_argument("--no-ranking", action="store_true", help="tắt cánh tay LambdaMART")
    parser.add_argument("--bandit-state", default=None, help="tệp JSON để nạp/ghi trạng thái MAB")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    CAPABILITIES.log_summary()

    try:
        observations = ObservationMatrix.from_frame(pd.read_csv(args.raw))
    except FileNotFoundError:
        LOGGER.error("Không tìm thấy tệp dữ liệu: %s", args.raw)
        return 1
    except Exception as error:
        LOGGER.error("Dữ liệu đầu vào không hợp lệ: %s", error)
        return 1

    config = PipelineConfig(
        window=args.window,
        warmup=args.warmup,
        refit_every=args.refit_every,
        top_k=args.top_k,
        discount=args.discount,
        use_temporal=not args.no_temporal,
        use_ranking=not args.no_ranking,
    )
    pipeline = ContinuousLearningPipeline(observations, config)

    if args.bandit_state and Path(args.bandit_state).exists():
        try:
            pipeline.bandit = DiscountedThompsonSamplingMAB.load_json(args.bandit_state)
            LOGGER.info("Đã nạp trạng thái MAB từ %s", args.bandit_state)
        except Exception as error:
            LOGGER.warning("Không nạp được trạng thái MAB (%s); bắt đầu từ tiên nghiệm", error)

    start = args.start if args.start is not None else config.warmup
    stop = args.stop if args.stop is not None else observations.n_days
    try:
        results = pipeline.run(start=start, stop=stop)
    except ValueError as error:
        LOGGER.error("Không chạy được: %s", error)
        return 1

    summary = summarise(pipeline, results)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("Đã ghi báo cáo vào %s", target)

    if args.bandit_state:
        pipeline.bandit.save_json(args.bandit_state)

    metrics = summary["metrics"]
    print(f"\n{'=' * 72}")
    print(f"ml_engine · {summary['days']} kỳ · nền {BASELINE_RATE:.4f}")
    print(f"{'=' * 72}")
    print(
        f"  kỹ năng log-loss : {metrics['logloss_skill']:+.6f}  (t ghép cặp {metrics['paired_t']:+.2f})"
    )
    print(f"  kỹ năng Brier    : {metrics['brier_skill']:+.6f}")
    for k in ("3", "5", "10"):
        if k in metrics["hit_rate_at"]:
            print(
                f"  trúng@{k:<3}        : {metrics['hit_rate_at'][k]:.4f}  "
                f"(chọn ngẫu nhiên {metrics['random_hit_rate_at'][k]:.4f}, "
                f"lời/lỗ {metrics['profit_ratio'][k]:+.1%})"
            )
    print(f"  vượt nền         : {'CÓ' if metrics['beats_baseline'] else 'KHÔNG'}")
    print(f"\n  trọng số cánh tay (trần n hiệu dụng {summary['bandit']['max_effective_n']:.0f}):")
    for row in summary["bandit"]["arms"]:
        verdict = "VƯỢT NỀN" if row["beats_baseline"] else ""
        print(
            f"    {row['arm']:<22} trung bình={row['posterior_mean']:.4f} "
            f"[{row['credible_low']:.4f}, {row['credible_high']:.4f}] {verdict}"
        )
    print(
        f"\n  trôi lệch: {summary['drift']['detections']} lần · "
        f"chế độ an toàn: {summary['drift']['days_in_safe_mode']}/{summary['days']} kỳ"
    )
    print(f"{'=' * 72}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
