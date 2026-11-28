from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from research.ml_engine.capabilities import CAPABILITIES
from research.ml_engine.features import build_features, build_training_table
from research.ml_engine.metrics import PerformanceReport, PerformanceTracker
from research.ml_engine.models import Learner, TabularBooster
from research.ml_engine.schema import BASELINE_RATE, NUMBER_SPACE

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

DEFAULT_SEARCH_SPACE: Final[dict[str, tuple[Any, ...]]] = {
    "max_depth": ("int", 2, 5),
    "n_estimators": ("int", 80, 320),
    "learning_rate": ("float", 0.01, 0.12),
    "l2_regularization": ("float", 0.1, 10.0),
}


@dataclass(frozen=True)
class Split:

    train_start: int
    train_stop: int
    predict_day: int

    def __post_init__(self) -> None:
        if self.train_start >= self.train_stop:
            raise ValueError("cửa sổ huấn luyện rỗng")
        if self.predict_day != self.train_stop:
            raise ValueError("ngày dự đoán phải ngay sau cửa sổ huấn luyện")


class WalkForwardValidator:

    def __init__(
        self,
        counts: np.ndarray,
        *,
        window: int = 240,
        warmup: int = 120,
        refit_every: int = 14,
    ) -> None:
        if counts.ndim != 2 or counts.shape[1] != NUMBER_SPACE:
            raise ValueError(f"counts phải có dạng (n, {NUMBER_SPACE})")
        if warmup < 60:
            raise ValueError("warmup phải ít nhất 60 ngày để đặc trưng có nghĩa")
        if window < 30:
            raise ValueError("window phải ít nhất 30 ngày")
        if refit_every < 1:
            raise ValueError("refit_every phải dương")
        if counts.shape[0] <= warmup:
            raise ValueError(f"cần hơn {warmup} ngày, chỉ có {counts.shape[0]}")

        self.counts = counts
        self.window = int(window)
        self.warmup = int(warmup)
        self.refit_every = int(refit_every)

    def splits(self, start: int, stop: int) -> Iterator[Split]:
        for day in range(start, stop):
            yield Split(
                train_start=max(self.warmup - self.window, max(0, day - self.window)),
                train_stop=day,
                predict_day=day,
            )

    def evaluate(
        self,
        model_factory: Callable[[], Learner],
        *,
        start: int,
        stop: int,
        feature_filter: list[str] | None = None,
    ) -> PerformanceReport:
        if not self.warmup <= start < stop <= self.counts.shape[0]:
            raise ValueError(
                f"khoảng [{start}, {stop}) phải nằm sau warmup={self.warmup} "
                f"và trong {self.counts.shape[0]} ngày"
            )

        tracker = PerformanceTracker()
        model: Learner | None = None
        fitted_at = -1

        for split in self.splits(start, stop):
            if model is None or split.predict_day - fitted_at >= self.refit_every:
                x, y, names = build_training_table(
                    self.counts, start=split.train_start, stop=split.train_stop
                )
                if feature_filter:
                    keep = [names.index(name) for name in feature_filter if name in names]
                    x = x[:, keep]
                if len(np.unique(y)) < 2:
                    model = None
                else:
                    model = model_factory()
                    model.fit(x, y)
                    fitted_at = split.predict_day

            if model is None:
                probabilities = np.full(NUMBER_SPACE, BASELINE_RATE)
            else:
                matrix = build_features(self.counts, split.predict_day)
                features = matrix.values
                if feature_filter:
                    keep = [matrix.names.index(n) for n in feature_filter if n in matrix.names]
                    features = features[:, keep]
                probabilities = model.predict_proba(features)

            counts = self.counts[split.predict_day]
            tracker.add(probabilities, (counts > 0).astype(float), counts=counts)

        return tracker.report()

    def tune(
        self,
        *,
        tune_start: int,
        tune_stop: int,
        n_trials: int = 30,
        search_space: dict[str, tuple[Any, ...]] | None = None,
        seed: int = 0,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        space = search_space or DEFAULT_SEARCH_SPACE
        if CAPABILITIES.optuna is None:
            LOGGER.warning("Thiếu optuna — chuyển sang dò ngẫu nhiên có kiểm soát hạt giống")
            return self._random_search(
                tune_start=tune_start,
                tune_stop=tune_stop,
                n_trials=n_trials,
                search_space=space,
                seed=seed,
            )

        optuna = CAPABILITIES.optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial: Any) -> float:
            params = self._suggest(trial, space)
            report = self.evaluate(
                lambda: TabularBooster(**params), start=tune_start, stop=tune_stop
            )
            return report.logloss

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=seed),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=0),
        )
        study.optimize(objective, n_trials=n_trials, timeout=timeout, show_progress_bar=False)

        LOGGER.info(
            "Optuna: %d lần thử, log-loss tốt nhất %.6f (nền %.6f)",
            len(study.trials),
            study.best_value,
            -np.log(BASELINE_RATE) * BASELINE_RATE - np.log1p(-BASELINE_RATE) * (1 - BASELINE_RATE),
        )
        return dict(study.best_params)

    @staticmethod
    def _suggest(trial: Any, space: dict[str, tuple[Any, ...]]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for name, spec in space.items():
            kind, low, high = spec[0], spec[1], spec[2]
            if kind == "int":
                params[name] = trial.suggest_int(name, int(low), int(high))
            elif kind == "float":
                params[name] = trial.suggest_float(name, float(low), float(high), log=False)
            else:
                raise ValueError(f"kiểu tham số không hỗ trợ: {kind}")
        return params

    def _random_search(
        self,
        *,
        tune_start: int,
        tune_stop: int,
        n_trials: int,
        search_space: dict[str, tuple[Any, ...]],
        seed: int,
    ) -> dict[str, Any]:
        rng = np.random.default_rng(seed)
        best_params: dict[str, Any] = {}
        best_loss = float("inf")
        for _ in range(n_trials):
            params: dict[str, Any] = {}
            for name, spec in search_space.items():
                kind, low, high = spec[0], spec[1], spec[2]
                params[name] = (
                    int(rng.integers(int(low), int(high) + 1))
                    if kind == "int"
                    else float(rng.uniform(float(low), float(high)))
                )
            report = self.evaluate(
                lambda: TabularBooster(**params),  # noqa: B023
                start=tune_start,
                stop=tune_stop,
            )
            if report.logloss < best_loss:
                best_loss, best_params = report.logloss, params
        return best_params
