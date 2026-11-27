from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from math import factorial
from pathlib import Path
from typing import Any, Final

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit

from core.number_reference import normalize_two_digit
from core.time_policy import iso_local
from core.xsmb_domain import baseline_rate
from soi_cau.bridges.scanner import NUMBER_SPACE, DigitTensor
from soi_cau.features import FeatureContext, FeatureMatrix, FeatureRegistry, PatternMemoryExtractor, default_registry


_EPS: Final[float] = 1e-9
MIN_UNIFORM_SHARE: Final[float] = 1e-4


@dataclass(frozen=True)
class TrainingData:

    features: np.ndarray
    labels: np.ndarray
    day_index: np.ndarray
    columns: tuple[str, ...]
    groups: dict[str, tuple[int, int]]

    @property
    def n_days(self) -> int:
        return int(len(np.unique(self.day_index)))


def build_training_data(
    tensor: DigitTensor,
    *,
    mode: str = "loto",
    warmup_days: int = 180,
    registry: FeatureRegistry | None = None,
    last_anchor: int | None = None,
) -> TrainingData:
    if mode not in {"loto", "de"}:
        raise ValueError("mode phải là 'loto' hoặc 'de'")
    registry = registry or default_registry()
    stop = tensor.n_days - 1 if last_anchor is None else last_anchor + 1
    if stop <= warmup_days:
        raise ValueError("lịch sử quá ngắn so với warmup_days")

    hits = tensor.loto_hits()
    blocks, labels, days = [], [], []
    columns: tuple[str, ...] = ()
    groups: dict[str, tuple[int, int]] = {}

    for anchor in range(warmup_days, stop):
        matrix = registry.build_matrix(FeatureContext(tensor=tensor, anchor_index=anchor))
        if not columns:
            columns, groups = matrix.columns, matrix.groups
        blocks.append(matrix.values)
        if mode == "de":
            target = np.zeros(NUMBER_SPACE, dtype=np.int8)
            target[int(tensor.de_index[anchor + 1])] = 1
        else:
            target = hits[anchor + 1].astype(np.int8)
        labels.append(target)
        days.append(np.full(NUMBER_SPACE, anchor, dtype=np.int32))

    return TrainingData(
        features=np.vstack(blocks),
        labels=np.concatenate(labels),
        day_index=np.concatenate(days),
        columns=columns,
        groups=groups,
    )


def _base_learners() -> list[tuple[str, object]]:
    return [
        (
            "boosting",
            HistGradientBoostingClassifier(
                max_depth=3,
                max_iter=120,
                learning_rate=0.05,
                l2_regularization=1.0,
                early_stopping=False,
                random_state=20260906,
            ),
        ),
        (
            "linear",
            LogisticRegression(max_iter=1000, C=0.5, random_state=20260906),
        ),
    ]


@dataclass
class StackedEnsemble:

    mode: str = "loto"
    n_splits: int = 4
    name: str = "stacked_ensemble"
    description: str = "Boosting + tuyến tính, xếp chồng bằng chia theo thời gian"
    base_learners: list[tuple[str, object]] = field(default_factory=_base_learners)
    meta_learner: object = field(
        default_factory=lambda: LogisticRegression(max_iter=1000, random_state=20260906)
    )
    columns: tuple[str, ...] = ()
    groups: dict[str, tuple[int, int]] = field(default_factory=dict)
    _fitted: bool = False

    def fit(self, data: TrainingData) -> StackedEnsemble:
        if len(np.unique(data.labels)) < 2:
            raise ValueError("nhãn chỉ có một lớp; không huấn luyện được")
        self.columns, self.groups = data.columns, data.groups

        unique_days = np.unique(data.day_index)
        splitter = TimeSeriesSplit(n_splits=self.n_splits)
        meta_features = np.zeros((len(data.labels), len(self.base_learners)))

        for train_days, test_days in splitter.split(unique_days):
            train = np.isin(data.day_index, unique_days[train_days])
            test = np.isin(data.day_index, unique_days[test_days])
            if len(np.unique(data.labels[train])) < 2:
                continue
            for column, (_, learner) in enumerate(self.base_learners):
                fold_model = _clone(learner)
                fold_model.fit(data.features[train], data.labels[train])
                meta_features[test, column] = fold_model.predict_proba(data.features[test])[:, 1]

        scored = meta_features.any(axis=1)
        if scored.sum() == 0 or len(np.unique(data.labels[scored])) < 2:
            raise ValueError("không sinh được dự đoán ngoài mẫu để học lớp meta")
        self.meta_learner.fit(meta_features[scored], data.labels[scored])

        for _, learner in self.base_learners:
            learner.fit(data.features, data.labels)
        self._fitted = True
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("mô hình chưa được huấn luyện")
        stacked = np.column_stack(
            [learner.predict_proba(features)[:, 1] for _, learner in self.base_learners]
        )
        return self.meta_learner.predict_proba(stacked)[:, 1]

    def predict_day(self, matrix: FeatureMatrix) -> np.ndarray:
        raw = self.predict_proba(matrix.values)
        if self.mode != "de":
            return np.clip(raw, _EPS, 1.0 - _EPS)
        total = raw.sum()
        shaped = raw / total if total > _EPS else np.full(NUMBER_SPACE, 1.0 / NUMBER_SPACE)
        blended = (1.0 - MIN_UNIFORM_SHARE) * shaped + MIN_UNIFORM_SHARE / NUMBER_SPACE
        return blended / blended.sum()

    @property
    def baseline(self) -> float:
        return baseline_rate(self.mode)


def _clone(estimator: object) -> object:
    from sklearn.base import clone

    return clone(estimator)


class LotoModel(StackedEnsemble):

    def __init__(self, **kwargs: object) -> None:
        super().__init__(mode="loto", **kwargs)  # type: ignore[arg-type]


class DeModel(StackedEnsemble):

    def __init__(self, **kwargs: object) -> None:
        super().__init__(mode="de", **kwargs)  # type: ignore[arg-type]


_SHAPLEY_EPS = 1e-12


@dataclass
class Explainer:

    model: StackedEnsemble
    reference: np.ndarray

    @classmethod
    def from_training(cls, model: StackedEnsemble, features: np.ndarray) -> Explainer:
        return cls(model=model, reference=np.median(features, axis=0))

    @property
    def group_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.model.groups))

    def _masked(self, values: np.ndarray, active: frozenset[str]) -> np.ndarray:
        out = values.copy()
        for name, (start, stop) in self.model.groups.items():
            if name not in active:
                out[:, start:stop] = self.reference[start:stop]
        return out

    def contributions(self, matrix: FeatureMatrix) -> dict[str, np.ndarray]:
        names = self.group_names
        n = len(names)
        if n == 0:
            return {}

        values: dict[frozenset[str], np.ndarray] = {}
        for size in range(n + 1):
            for subset in combinations(names, size):
                active = frozenset(subset)
                values[active] = self.model.predict_proba(self._masked(matrix.values, active))

        shapley = {name: np.zeros(matrix.values.shape[0]) for name in names}
        for name in names:
            others = [x for x in names if x != name]
            for size in range(len(others) + 1):
                weight = factorial(size) * factorial(n - size - 1) / factorial(n)
                for subset in combinations(others, size):
                    active = frozenset(subset)
                    shapley[name] += weight * (values[active | {name}] - values[active])
        return shapley

    def group_shares(self, matrix: FeatureMatrix, row: int) -> dict[str, float]:
        contributions = self.contributions(matrix)
        magnitudes = {name: abs(float(v[row])) for name, v in contributions.items()}
        total = sum(magnitudes.values())
        if total <= _SHAPLEY_EPS:
            return dict.fromkeys(magnitudes, 0.0)
        return {
            name: float(contributions[name][row]) / total
            for name in sorted(magnitudes, key=lambda k: -magnitudes[k])
        }

    def top_reasons(self, matrix: FeatureMatrix, row: int, k: int = 3) -> list[tuple[str, float]]:
        shares = self.group_shares(matrix, row)
        ordered = sorted(shares.items(), key=lambda item: -abs(item[1]))
        return ordered[:k]


DEFAULT_GAN_THRESHOLD_DAYS = 15


@dataclass
class GanFilter:

    threshold_days: int = DEFAULT_GAN_THRESHOLD_DAYS
    exclude: bool = False

    def gaps(self, ctx: FeatureContext) -> np.ndarray:
        block = PatternMemoryExtractor().extract(ctx)
        return block[:, 2]

    def flagged(self, ctx: FeatureContext) -> list[str]:
        gaps = self.gaps(ctx)
        return [normalize_two_digit(int(n)) for n in np.flatnonzero(gaps > self.threshold_days)]

    def apply(self, probabilities: np.ndarray, ctx: FeatureContext) -> np.ndarray:
        if probabilities.shape != (NUMBER_SPACE,):
            raise ValueError(f"xác suất phải là vector {NUMBER_SPACE} phần tử")
        if not self.exclude:
            return probabilities

        keep = self.gaps(ctx) <= self.threshold_days
        if not keep.any():
            return probabilities
        filtered = np.where(keep, probabilities, 0.0)
        total = float(probabilities.sum())
        if abs(total - 1.0) < 1e-6:
            return filtered / max(filtered.sum(), 1e-12)
        return filtered


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class NumberPick:

    number: str
    probability: float
    baseline: float
    lift: float
    contribution_reasons: dict[str, float]
    gan_days: int
    gan_flagged: bool


@dataclass(frozen=True)
class PredictionBundle:

    date: str
    generated_at_local: str
    generated_at_utc: str
    top_lo_to: list[NumberPick]
    top_dac_biet: dict[str, Any]
    active_bridges: list[dict[str, Any]]
    disclaimer: str
    schema_version: str = SCHEMA_VERSION
    evidence: dict[str, Any] = field(default_factory=dict)
    gan_flagged: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["top_lo_to"] = [asdict(pick) for pick in self.top_lo_to]
        return payload

    def to_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def build_picks(
    probabilities: np.ndarray,
    *,
    baseline: float,
    gaps: np.ndarray,
    gan_threshold: int,
    reasons: dict[int, dict[str, float]],
    top_k: int = 10,
    max_per_tail: int | None = None,
) -> list[NumberPick]:
    if max_per_tail is None:
        order = np.lexsort((np.arange(len(probabilities)), -probabilities))[:top_k]
    else:
        from ensemble.pick_diversity import diversified_order

        order = diversified_order(probabilities, top_k, max_per_tail=max_per_tail)
    return [
        NumberPick(
            number=normalize_two_digit(int(n)),
            probability=float(probabilities[n]),
            baseline=float(baseline),
            lift=float(probabilities[n] - baseline),
            contribution_reasons={k: round(v, 4) for k, v in reasons.get(int(n), {}).items()},
            gan_days=int(gaps[n]),
            gan_flagged=bool(gaps[n] > gan_threshold),
        )
        for n in order
    ]


def utc_stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_stamp() -> str:
    return iso_local()
