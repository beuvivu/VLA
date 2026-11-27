from __future__ import annotations

import logging
from numbers import Integral
from typing import Any, Final, Protocol, runtime_checkable

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from research.ml_engine.capabilities import CAPABILITIES
from research.ml_engine.schema import BASELINE_RATE, NUMBER_SPACE

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_EPSILON: Final[float] = 1e-6

RIDGE_PENALTIES: Final[tuple[float, ...]] = (1e6, 1e5, 1e4, 1e3, 1e2, 1e1)

RIDGE_VALIDATION_FRACTION: Final[float] = 0.2


def _clip(values: np.ndarray) -> np.ndarray:
    if not np.isfinite(values).all():
        raise ValueError("đầu ra mô hình phải hữu hạn")
    return np.clip(values, _EPSILON, 1.0 - _EPSILON)


@runtime_checkable
class Learner(Protocol):

    name: str

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        ...

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        ...


class TabularBooster:

    def __init__(self, name: str = "tabular_boosting", **params: Any) -> None:
        self.name = name
        self.params: dict[str, Any] = {
            "max_depth": 3,
            "n_estimators": 200,
            "learning_rate": 0.05,
            "l2_regularization": 1.0,
            **params,
        }
        self.backend = "chưa khớp"
        self._model: Any = None

    def _build(self) -> tuple[Any, str]:
        depth = int(self.params["max_depth"])
        trees = int(self.params["n_estimators"])
        rate = float(self.params["learning_rate"])
        l2 = float(self.params["l2_regularization"])

        if CAPABILITIES.lightgbm is not None:
            return (
                CAPABILITIES.lightgbm.LGBMClassifier(
                    max_depth=depth,
                    n_estimators=trees,
                    learning_rate=rate,
                    reg_lambda=l2,
                    num_leaves=max(2, 2**depth),
                    min_child_samples=int(self.params.get("min_child_samples", 40)),
                    subsample=float(self.params.get("subsample", 0.9)),
                    subsample_freq=1,
                    colsample_bytree=float(self.params.get("colsample_bytree", 0.9)),
                    random_state=0,
                    verbose=-1,
                    n_jobs=1,
                ),
                "lightgbm",
            )
        if CAPABILITIES.catboost is not None:
            return (
                CAPABILITIES.catboost.CatBoostClassifier(
                    depth=depth,
                    iterations=trees,
                    learning_rate=rate,
                    l2_leaf_reg=l2,
                    random_seed=0,
                    verbose=False,
                    thread_count=1,
                ),
                "catboost",
            )
        return (
            HistGradientBoostingClassifier(
                max_depth=depth,
                max_iter=trees,
                learning_rate=rate,
                l2_regularization=l2,
                random_state=0,
            ),
            "sklearn",
        )

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        if len(np.unique(y)) < 2:
            raise ValueError("cần cả hai lớp trong nhãn để khớp")
        candidate, backend = self._build()
        candidate.fit(x, y)
        self._model, self.backend = candidate, backend

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError(f"{self.name}: phải gọi fit() trước predict_proba()")
        return _clip(np.asarray(self._model.predict_proba(x))[:, 1])


class RankingBooster:

    def __init__(self, name: str = "ranking_lambdamart", **params: Any) -> None:
        self.name = name
        self.group_size = NUMBER_SPACE
        self.params: dict[str, Any] = {
            "max_depth": 3,
            "n_estimators": 200,
            "learning_rate": 0.05,
            **params,
        }
        self.is_calibrated = False
        self._model: Any = None
        self._calibrator: IsotonicRegression | None = None
        self._fallback: TabularBooster | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        if x.shape[0] % self.group_size != 0:
            raise ValueError(
                f"số hàng ({x.shape[0]}) phải chia hết cho kích thước nhóm ({self.group_size})"
            )
        self._model = None
        self._calibrator = None
        self._fallback = None
        self.is_calibrated = False
        if CAPABILITIES.lightgbm is None:
            LOGGER.warning("%s: thiếu lightgbm, lui về phân loại bảng", self.name)
            self._fallback = TabularBooster(name=f"{self.name}_fallback", **self.params)
            self._fallback.fit(x, y)
            self.is_calibrated = False
            return

        n_days = x.shape[0] // self.group_size
        if n_days < 2:
            raise ValueError("cần ít nhất hai ngày để tách huấn luyện và hiệu chuẩn")
        calibration_days = max(1, int(np.ceil(n_days * 0.2)))
        training_days = n_days - calibration_days
        boundary = training_days * self.group_size
        groups = [self.group_size] * training_days
        self._model = CAPABILITIES.lightgbm.LGBMRanker(
            objective="lambdarank",
            max_depth=int(self.params["max_depth"]),
            n_estimators=int(self.params["n_estimators"]),
            learning_rate=float(self.params["learning_rate"]),
            num_leaves=max(2, 2 ** int(self.params["max_depth"])),
            label_gain=[0, 1],
            random_state=0,
            verbose=-1,
            n_jobs=1,
        )
        self._model.fit(x[:boundary], y[:boundary], group=groups)

        raw = np.asarray(self._model.predict(x[boundary:]), dtype=float)
        self._calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self._calibrator.fit(raw, y[boundary:].astype(float))
        self.is_calibrated = True

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self._fallback is not None:
            return self._fallback.predict_proba(x)
        if self._model is None or self._calibrator is None:
            raise RuntimeError(f"{self.name}: phải gọi fit() trước predict_proba()")
        return _clip(self._calibrator.predict(np.asarray(self._model.predict(x), dtype=float)))


class TemporalSequenceModel:

    def __init__(
        self,
        name: str = "temporal_sequence",
        *,
        hidden_size: int = 16,
        lookback: int = 14,
        epochs: int = 40,
        learning_rate: float = 0.01,
        seed: int = 0,
    ) -> None:
        if isinstance(lookback, bool) or not isinstance(lookback, Integral) or lookback <= 0:
            raise ValueError("lookback phải là số nguyên dương")
        self.name = name
        self.hidden_size = int(hidden_size)
        self.lookback = int(lookback)
        self.epochs = int(epochs)
        self.learning_rate = float(learning_rate)
        self.seed = int(seed)
        self.backend = "torch" if CAPABILITIES.torch is not None else "linear"
        self._model: Any = None
        self._linear_weights: np.ndarray | None = None
        self.ridge_penalty: float | None = None

    @staticmethod
    def gru_parameter_count(hidden_size: int) -> int:
        gates = 3 * (hidden_size * (NUMBER_SPACE + hidden_size) + 2 * hidden_size)
        head = hidden_size * NUMBER_SPACE + NUMBER_SPACE
        return int(gates + head)

    @property
    def parameter_count(self) -> int:
        if self.backend == "torch":
            return self.gru_parameter_count(self.hidden_size)
        return int((self.lookback * NUMBER_SPACE + 1) * NUMBER_SPACE)

    def _windows(self, hits: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n = hits.shape[0]
        if n <= self.lookback:
            raise ValueError(f"cần hơn {self.lookback} ngày, chỉ có {n}")
        starts = np.arange(0, n - self.lookback)
        sequences = np.stack([hits[s : s + self.lookback] for s in starts]).astype(np.float32)
        targets = hits[self.lookback :].astype(np.float32)
        return sequences, targets

    def fit_sequence(self, hits: np.ndarray) -> None:
        if not np.isfinite(hits).all():
            raise ValueError("lịch sử chuỗi phải hữu hạn")
        sequences, targets = self._windows(hits)
        if self.backend == "torch":
            self._fit_torch(sequences, targets)
        else:
            self._fit_linear(sequences, targets)

    def _fit_torch(self, sequences: np.ndarray, targets: np.ndarray) -> None:
        torch = CAPABILITIES.torch
        assert torch is not None
        torch.manual_seed(self.seed)

        class _Net(torch.nn.Module):
            def __init__(self, hidden: int) -> None:
                super().__init__()
                self.gru = torch.nn.GRU(NUMBER_SPACE, hidden, batch_first=True)
                self.head = torch.nn.Linear(hidden, NUMBER_SPACE)

            def forward(self, batch):
                output, _ = self.gru(batch)
                return self.head(output[:, -1, :])

        model = _Net(self.hidden_size)
        optimiser = torch.optim.Adam(model.parameters(), lr=self.learning_rate)
        loss_function = torch.nn.BCEWithLogitsLoss()

        x = torch.from_numpy(sequences)
        y = torch.from_numpy(targets)
        model.train()
        for _ in range(self.epochs):
            optimiser.zero_grad()
            loss = loss_function(model(x), y)
            loss.backward()
            optimiser.step()
        model.eval()
        self._model = model

    @staticmethod
    def _ridge_paths(x: np.ndarray, y: np.ndarray, penalties: tuple[float, ...]):
        mean = x.mean(axis=0)
        u, singular, vt = np.linalg.svd(x - mean, full_matrices=False)
        projected = u.T @ y
        for penalty in penalties:
            shrink = singular / (singular**2 + penalty)
            yield penalty, mean, vt.T @ (shrink[:, None] * projected)

    def _fit_linear(self, sequences: np.ndarray, targets: np.ndarray) -> None:
        if not np.isfinite(sequences).all() or not np.isfinite(targets).all():
            raise ValueError("đặc trưng và nhãn chuỗi phải hữu hạn")
        flat = sequences.reshape(sequences.shape[0], -1).astype(np.float64)
        labels = targets.astype(np.float64)
        split = int(len(flat) * (1.0 - RIDGE_VALIDATION_FRACTION))
        penalty, best = RIDGE_PENALTIES[0], np.inf
        if split >= 2:
            for candidate, mean, weights in self._ridge_paths(
                flat[:split], labels[:split], RIDGE_PENALTIES
            ):
                held = np.clip(BASELINE_RATE + (flat[split:] - mean) @ weights,
                               _EPSILON, 1.0 - _EPSILON)
                truth = labels[split:]
                loss = float(-np.mean(truth * np.log(held) + (1 - truth) * np.log1p(-held)))
                if loss < best:
                    penalty, best = candidate, loss
        ((_, mean, weights),) = self._ridge_paths(flat, labels, (penalty,))
        intercept = BASELINE_RATE - mean @ weights
        self._linear_weights = np.vstack([weights, intercept[None, :]])
        self.ridge_penalty = penalty

    def predict_sequence(self, hits: np.ndarray) -> np.ndarray:
        window = hits[-self.lookback :].astype(np.float32)
        if window.shape[0] < self.lookback:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        if self.backend == "torch" and self._model is not None:
            torch = CAPABILITIES.torch
            assert torch is not None
            with torch.no_grad():
                logits = self._model(torch.from_numpy(window[None, ...]))
                return _clip(torch.sigmoid(logits).numpy().ravel())
        if self._linear_weights is not None:
            design = np.concatenate([window.ravel().astype(np.float64), [1.0]])
            return _clip(design @ self._linear_weights)
        raise RuntimeError(f"{self.name}: phải gọi fit_sequence() trước predict_sequence()")
