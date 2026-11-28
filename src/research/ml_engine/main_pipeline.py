from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from numbers import Integral
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from research.ml_engine.aggregation import DEFAULT_LEARNING_RATE, DEFAULT_SHARE, ExponentialWeights
from research.ml_engine.capabilities import CAPABILITIES
from research.ml_engine.drift import ConceptDriftDetector
from research.ml_engine.fallback import DEFAULT_MIN_DAYS, DEFAULT_WINDOW, SafeModeController
from research.ml_engine.features import build_features, build_training_table
from research.ml_engine.metrics import PerformanceTracker, score_day, validate_probabilities
from research.ml_engine.models import RankingBooster, TabularBooster, TemporalSequenceModel
from research.ml_engine.schema import BASELINE_RATE, NUMBER_SPACE, DailyRequest, ObservationMatrix
from research.ml_engine.selection import select_features

LOGGER: Final[logging.Logger] = logging.getLogger("research.ml_engine")

@dataclass(frozen=True)
class PipelineConfig:

    window: int = 240
    warmup: int = 120
    refit_every: int = 21
    top_k: int = 10
    learning_rate: float = DEFAULT_LEARNING_RATE
    share: float = DEFAULT_SHARE
    trust_window: int = DEFAULT_WINDOW
    trust_min_days: int = DEFAULT_MIN_DAYS
    use_temporal: bool = True
    use_ranking: bool = True
    feature_epsilon: float = 1e-4

    def __post_init__(self) -> None:
        for name, minimum in (("window", 30), ("warmup", 60), ("refit_every", 1),
                              ("top_k", 1), ("trust_window", 1), ("trust_min_days", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
                raise ValueError(f"{name} phải là số nguyên ít nhất {minimum}")
        if self.top_k > NUMBER_SPACE:
            raise ValueError(f"top_k không được vượt {NUMBER_SPACE}")
        if self.trust_min_days > self.trust_window:
            raise ValueError("trust_min_days không được vượt trust_window")
        if not np.isfinite(self.learning_rate) or self.learning_rate <= 0.0:
            raise ValueError("learning_rate phải hữu hạn và dương")
        if not np.isfinite(self.share) or not 0.0 <= self.share < 1.0:
            raise ValueError("share phải nằm trong [0, 1)")
        if not np.isfinite(self.feature_epsilon) or self.feature_epsilon < 0.0:
            raise ValueError("feature_epsilon phải hữu hạn và không âm")


@dataclass
class DayResult:

    day_index: int
    date: pd.Timestamp
    probabilities: np.ndarray
    top_k: list[int]
    arm_weights: dict[str, float]
    mode: str
    trust: float
    drifted: bool
    hits_in_top_k: int
    arm_losses: dict[str, float] = field(default_factory=dict)
    mixture_logloss: float = float("nan")


class ContinuousLearningPipeline:

    def __init__(
        self,
        observations: ObservationMatrix,
        config: PipelineConfig | None = None,
    ) -> None:
        self.observations = observations
        self.config = config or PipelineConfig()
        self.arm_builders = self._build_arms()

        self.aggregator = ExponentialWeights(
            self.arm_builders,
            learning_rate=self.config.learning_rate,
            share=self.config.share,
        )
        self.drift = ConceptDriftDetector(method="both")
        self.safe_mode = SafeModeController(
            window=self.config.trust_window, min_days=self.config.trust_min_days
        )
        self.tracker = PerformanceTracker()
        self.selected_features: list[str] | None = None
        self._fitted: dict[str, Any] = {}
        self._fitted_features: dict[str, list[str]] = {}
        self._refit_failed = False
        self._model_failed = False
        self._fitted_at = -1
        self._force_refit = False
        self._last_observed_day = -1
        self._forecast_day = -1
        self._forecast: tuple[np.ndarray, dict[str, float], dict[str, np.ndarray]] | None = None
        self._forecast_mixture: np.ndarray | None = None
        self._forecast_mode = self.safe_mode.mode.value
        self._forecast_trust = self.safe_mode.trust
        self._forecast_reason = self.safe_mode.reason
        self._forecast_model_failed = False


    def _build_arms(self) -> dict[str, Callable[[], Any]]:
        arms: dict[str, Callable[[], Any]] = {
            "baseline": lambda: None,
            "frequency": lambda: None,
            "gap_hazard": lambda: None,
            "tabular_boosting": lambda: TabularBooster(),
        }
        if self.config.use_ranking:
            arms["ranking_lambdamart"] = lambda: RankingBooster()
        if self.config.use_temporal:
            arms["temporal_sequence"] = lambda: TemporalSequenceModel()
        return arms

    @staticmethod
    def _frequency_probabilities(counts: np.ndarray) -> np.ndarray:
        if counts.shape[0] < 30:
            return np.full(NUMBER_SPACE, BASELINE_RATE)
        empirical = (counts > 0).mean(axis=0)
        weight = min(counts.shape[0] / (counts.shape[0] + 200.0), 1.0)
        return weight * empirical + (1.0 - weight) * BASELINE_RATE

    @staticmethod
    def _gap_hazard_probabilities(counts: np.ndarray, *, max_gap: int = 12) -> np.ndarray:
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


    def _refit(self, day: int) -> None:
        start = max(0, day - self.config.window)
        x, y, names = build_training_table(self.observations.counts, start=start, stop=day)
        if len(np.unique(y)) < 2:
            LOGGER.warning("Ngày %d: nhãn chỉ có một lớp, bỏ qua lần khớp này", day)
            self._refit_failed = True
            return

        fitted = dict(self._fitted)
        fitted_features = dict(self._fitted_features)
        failed = False

        probe = TabularBooster()
        try:
            probe.fit(x, y)
            result = select_features(probe._model, x, y, names, epsilon=self.config.feature_epsilon)
            selected_features = result.kept
            LOGGER.info("Ngày %d: %s", day, result.describe())
        except (ValueError, RuntimeError, TypeError, AttributeError, ImportError, OSError) as error:
            LOGGER.warning("Ngày %d: chọn đặc trưng thất bại (%s); giữ toàn bộ cột", day, error)
            selected_features = list(names)
            failed = True

        keep = [names.index(name) for name in selected_features if name in names]
        x_selected = x[:, keep]

        for name, builder in self.arm_builders.items():
            try:
                model = builder()
                if model is None:
                    continue
                if isinstance(model, TemporalSequenceModel):
                    model.fit_sequence(self.observations.hits[start:day])
                elif isinstance(model, RankingBooster):
                    model.fit(x, y)
                else:
                    model.fit(x_selected, y)
                fitted[name] = model
                fitted_features[name] = list(selected_features)
            except (ValueError, RuntimeError, TypeError, AttributeError, ImportError, OSError) as error:
                failed = True
                LOGGER.error("Ngày %d: cánh tay %s khớp lỗi: %s", day, name, error)

        self._fitted = fitted
        self._fitted_features = fitted_features
        self.selected_features = list(selected_features)
        self._fitted_at = day
        self._refit_failed = failed

    def arm_probabilities(self, day: int) -> dict[str, np.ndarray]:
        self._check_prediction_day(day)
        self._model_failed = self._refit_failed
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
                    features = self._fitted_features.get(name)
                    values = (matrix.values[:, [matrix.names.index(n) for n in features]]
                              if features is not None else selected)
                    output[name] = model.predict_proba(values)
            except (ValueError, RuntimeError, TypeError, AttributeError, ImportError, OSError) as error:
                self._model_failed = True
                LOGGER.error("Ngày %d: cánh tay %s dự đoán lỗi: %s", day, name, error)
        return output

    def _check_prediction_day(self, day: int) -> None:
        if isinstance(day, bool) or not isinstance(day, Integral):
            raise ValueError("day phải là số nguyên")
        if not self.config.warmup <= day <= self.observations.n_days:
            raise ValueError("day phải nằm sau warmup và không vượt kỳ kế tiếp")
        if day < max(self._forecast_day, self._fitted_at, self._last_observed_day):
            raise ValueError("không được dự báo lùi thời gian bằng trạng thái đã học")

    def _copy_forecast(self) -> tuple[np.ndarray, dict[str, float], dict[str, np.ndarray]]:
        assert self._forecast is not None
        probabilities, weights, per_arm = self._forecast
        return probabilities.copy(), dict(weights), {name: p.copy() for name, p in per_arm.items()}

    def predict_day(self, day: int) -> tuple[np.ndarray, dict[str, float], dict[str, np.ndarray]]:
        self._check_prediction_day(day)
        if day == self._forecast_day and self._forecast is not None:
            return self._copy_forecast()
        checkpoint = (self._fitted, self._fitted_at, self.selected_features, self._force_refit,
                      self._fitted_features, self._refit_failed, self._model_failed)
        try:
            return self._predict_uncached(day)
        except Exception:
            (self._fitted, self._fitted_at, self.selected_features, self._force_refit,
             self._fitted_features, self._refit_failed, self._model_failed) = checkpoint
            raise

    def _predict_uncached(self, day: int) -> tuple[np.ndarray, dict[str, float], dict[str, np.ndarray]]:
        if (self._force_refit or day - self._fitted_at >= self.config.refit_every
                or not self._fitted):
            self._refit(day)
            self._force_refit = False

        per_arm = {
            name: validate_probabilities(probability).copy()
            for name, probability in self.arm_probabilities(day).items()
        }
        weights = {name: weight for name, weight in self.aggregator.weights().items()
                   if name in per_arm}
        available_weight = sum(weights.values())
        if available_weight > 0:
            weights = {name: weight / available_weight for name, weight in weights.items()}
        else:
            weights = {"baseline": 1.0}
        blended = np.zeros(NUMBER_SPACE)
        for name, probability in per_arm.items():
            blended += weights.get(name, 0.0) * probability
        total = sum(weights.get(name, 0.0) for name in per_arm)
        if total > 0:
            blended /= total

        blended = validate_probabilities(blended).copy()
        final = validate_probabilities(self.safe_mode.apply(blended)).copy()
        self._forecast_day = day
        self._forecast_mixture = blended
        self._forecast_mode = self.safe_mode.mode.value
        self._forecast_trust = self.safe_mode.trust
        self._forecast_reason = self.safe_mode.reason
        self._forecast_model_failed = self._model_failed
        self._forecast = final, dict(weights), per_arm
        return self._copy_forecast()


    def step(self, day: int) -> DayResult:
        if day <= self._last_observed_day:
            raise ValueError("ngày đã được chấm; không được học lại hay chạy lùi thời gian")
        if day >= self.observations.n_days:
            raise ValueError("chưa có kết quả thật của ngày cần chấm")
        probabilities, weights, per_arm = self.predict_day(day)
        prediction_mode, prediction_trust = self._forecast_mode, self._forecast_trust
        assert self._forecast_mixture is not None
        outcome = (self.observations.counts[day] > 0).astype(float)

        top_k = np.argsort(-probabilities, kind="stable")[: self.config.top_k]
        hits_in_top_k = int(outcome[top_k].sum())

        losses = {
            name: score_day(probability, outcome).logloss
            for name, probability in per_arm.items()
        }
        mixture = score_day(self._forecast_mixture, outcome)
        components = (self.aggregator, self.drift, self.safe_mode)
        checkpoint = [deepcopy(component.__dict__) for component in components]
        score_count = len(self.tracker._scores)
        cursors = self._force_refit, self._last_observed_day
        try:
            self.aggregator.update({name: NUMBER_SPACE * loss for name, loss in losses.items()})
            self.tracker.add(probabilities, outcome, counts=self.observations.counts[day])
            verdict = self.drift.update(mixture.brier)
            if verdict.drifted:
                self._force_refit = True
            self.safe_mode.observe(
                logloss=mixture.logloss, brier=mixture.brier,
                baseline_logloss=mixture.baseline_logloss,
                baseline_brier=mixture.baseline_brier,
                drifted=verdict.drifted, model_failed=self._forecast_model_failed,
                day_index=day,
            )
            self._last_observed_day = day
        except Exception:
            for component, state in zip(components, checkpoint, strict=True):
                component.__dict__.clear()
                component.__dict__.update(state)
            del self.tracker._scores[score_count:]
            self._force_refit, self._last_observed_day = cursors
            raise

        return DayResult(
            day_index=day,
            date=self.observations.dates[day],
            probabilities=probabilities,
            top_k=[int(n) for n in top_k],
            arm_weights=weights,
            mode=prediction_mode,
            trust=prediction_trust,
            drifted=verdict.drifted,
            hits_in_top_k=hits_in_top_k,
            arm_losses=losses,
            mixture_logloss=mixture.logloss,
        )

    def run(self, *, start: int, stop: int) -> list[DayResult]:
        if not self.config.warmup <= start < stop <= self.observations.n_days:
            raise ValueError(
                f"khoảng [{start}, {stop}) phải nằm sau warmup={self.config.warmup} "
                f"và trong {self.observations.n_days} ngày"
            )
        if start <= self._last_observed_day:
            raise ValueError("khoảng chạy chứa ngày đã chấm; cần pipeline mới để replay")
        self._check_prediction_day(start)
        results = []
        for day in range(start, stop):
            results.append(self.step(day))
            if (day - start) % 25 == 0:
                LOGGER.info(
                    "Ngày %d/%d · độ tin=%.3f · trúng@%d=%d",
                    day,
                    stop,
                    results[-1].trust,
                    self.config.top_k,
                    results[-1].hits_in_top_k,
                )
        return results

    def predict_next(self, request: DailyRequest) -> dict[str, Any]:
        last_date = self.observations.dates[-1]
        if request.anchor_date.normalize() != last_date.normalize():
            raise ValueError(
                f"anchor_date ({request.anchor_date.date()}) phải là ngày cuối của "
                f"lịch sử ({last_date.date()})"
            )

        day = self.observations.n_days
        probabilities, weights, per_arm = self.predict_day(day)
        order = np.argsort(-probabilities, kind="stable")[: request.top_k]
        return {
            "anchor_date": str(request.anchor_date.date()),
            "target_date": str(request.target_date.date()),
            "mode": self._forecast_mode,
            "trust": self._forecast_trust,
            "mode_reason": self._forecast_reason,
            "probabilities": [float(p) for p in probabilities],
            "top_k": [
                {"number": f"{int(n):02d}", "probability": float(probabilities[n])} for n in order
            ],
            "arm_weights": {name: float(weight) for name, weight in weights.items()},
            "arms_available": sorted(per_arm),
            "baseline_rate": BASELINE_RATE,
            "selected_features": self.selected_features,
        }


def arm_skill(results: list[DayResult]) -> list[dict[str, Any]]:
    names = sorted({name for result in results for name in result.arm_losses})
    rows = []
    for name in names:
        pairs = np.array([
            (result.arm_losses["baseline"], result.arm_losses[name])
            for result in results
            if name in result.arm_losses and "baseline" in result.arm_losses
        ])
        if len(pairs) == 0:
            continue
        gain = pairs[:, 0] - pairs[:, 1]
        spread = gain.std(ddof=1) if len(gain) > 1 else 0.0
        rows.append({
            "arm": name,
            "days": len(gain),
            "logloss": float(pairs[:, 1].mean()),
            "logloss_skill": float(gain.mean() / pairs[:, 0].mean()),
            "paired_t": float(gain.mean() / (spread / np.sqrt(len(gain)))) if spread > 0 else 0.0,
        })
    return sorted(rows, key=lambda row: -row["logloss_skill"])


def summarise(pipeline: ContinuousLearningPipeline, results: list[DayResult]) -> dict[str, Any]:
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
        "aggregation": {
            "method": "exponential_weights_logloss_fixed_share",
            "learning_rate": pipeline.aggregator.learning_rate,
            "share": pipeline.aggregator.share,
            "updates": pipeline.aggregator.updates,
            "arms": pipeline.aggregator.report(),
        },
        "arm_skill": arm_skill(results),
        "drift": {
            "backend": pipeline.drift.backend,
            "detections": pipeline.drift.drift_count,
        },
        "trust": {
            "mean": float(np.mean([r.trust for r in results])) if results else 0.0,
            "days_at_zero": sum(1 for r in results if r.mode == "safe"),
            **pipeline.safe_mode.state(),
        },
        "selected_features": pipeline.selected_features,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/xsmb.csv", help="tệp kết quả thô")
    parser.add_argument("--out", default="data/research/ml_engine_report.json")
    parser.add_argument("--start", type=int, default=None, help="ngày đầu; mặc định warmup")
    parser.add_argument("--stop", type=int, default=None, help="ngày cuối; mặc định hết lịch sử")
    parser.add_argument("--warmup", type=int, default=120)
    parser.add_argument("--window", type=int, default=240)
    parser.add_argument("--refit-every", type=int, default=21)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=DEFAULT_LEARNING_RATE)
    parser.add_argument("--share", type=float, default=DEFAULT_SHARE)
    parser.add_argument("--no-temporal", action="store_true", help="tắt cánh tay GRU")
    parser.add_argument("--no-ranking", action="store_true", help="tắt cánh tay LambdaMART")
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

    try:
        config = PipelineConfig(
            window=args.window,
            warmup=args.warmup,
            refit_every=args.refit_every,
            top_k=args.top_k,
            learning_rate=args.learning_rate,
            share=args.share,
            use_temporal=not args.no_temporal,
            use_ranking=not args.no_ranking,
        )
    except ValueError as error:
        LOGGER.error("Cấu hình không hợp lệ: %s", error)
        return 1
    pipeline = ContinuousLearningPipeline(observations, config)

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
    weights = {row["arm"]: row["weight"] for row in summary["aggregation"]["arms"]}
    print("\n  cánh tay (kỹ năng log-loss ngoài mẫu so với nền · trọng số cuối):")
    for row in summary["arm_skill"]:
        print(
            f"    {row['arm']:<22} kỹ năng={row['logloss_skill']:+.6f} "
            f"(t {row['paired_t']:+.2f}) · trọng số={weights.get(row['arm'], 0.0):.4f}"
        )
    trust = summary["trust"]
    print(
        f"\n  trôi lệch: {summary['drift']['detections']} lần · "
        f"độ tin trung bình {trust['mean']:.3f} · về nền {trust['days_at_zero']}/{summary['days']} kỳ"
    )
    print(f"{'=' * 72}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
