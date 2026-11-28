from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Protocol, runtime_checkable

import numpy as np

from core.number_reference import (
    bo,
    bong_am,
    bong_duong,
    digit_sum_mod10,
    head,
    normalize_two_digit,
    tail,
)
from core.xsmb_domain import FIELD_WIDTHS, LOTO_DRAWS_PER_DAY, UNIFORM_TWO_DIGIT_RATE, baseline_rate
from soi_cau.bridges.scanner import NUMBER_SPACE, DigitTensor


_EPS: Final[float] = 1e-9


@dataclass(frozen=True)
class FeatureContext:

    tensor: DigitTensor
    anchor_index: int

    def __post_init__(self) -> None:
        if not 0 <= self.anchor_index < self.tensor.n_days:
            raise ValueError("anchor_index nằm ngoài phạm vi lịch sử")

    @property
    def history_length(self) -> int:
        return self.anchor_index + 1

    def digits(self, days: int | None = None) -> np.ndarray:
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.values[start:stop]

    def hits(self, days: int | None = None) -> np.ndarray:
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.loto_hits()[start:stop]

    def counts(self, days: int | None = None) -> np.ndarray:
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.loto_counts[start:stop]

    def de_index(self, days: int | None = None) -> np.ndarray:
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.de_index[start:stop]

    def last_digits(self) -> np.ndarray:
        return self.tensor.values[self.anchor_index]


@runtime_checkable
class FeatureExtractor(Protocol):

    name: str
    description: str
    feature_names: tuple[str, ...]

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        ...


@dataclass(frozen=True)
class FeatureMatrix:

    values: np.ndarray
    columns: tuple[str, ...]
    groups: dict[str, tuple[int, int]]

    def __post_init__(self) -> None:
        if self.values.shape != (NUMBER_SPACE, len(self.columns)):
            raise ValueError(f"values phải có dạng ({NUMBER_SPACE}, {len(self.columns)})")

    @property
    def n_features(self) -> int:
        return len(self.columns)

    def group_slice(self, name: str) -> slice:
        try:
            start, stop = self.groups[name]
        except KeyError:
            raise KeyError(
                f"chưa có nhóm đặc trưng {name!r}; hiện có: {sorted(self.groups)}"
            ) from None
        return slice(start, stop)

    def group_values(self, name: str) -> np.ndarray:
        return self.values[:, self.group_slice(name)]


def validate_block(block: np.ndarray, extractor: FeatureExtractor) -> np.ndarray:
    expected = (NUMBER_SPACE, len(extractor.feature_names))
    if block.shape != expected:
        raise ValueError(f"{extractor.name} trả về {block.shape}, hợp đồng yêu cầu {expected}")
    if not np.all(np.isfinite(block)):
        raise ValueError(f"{extractor.name} trả về giá trị không hữu hạn")
    return block.astype(np.float64, copy=False)


class FeatureRegistry:

    def __init__(self) -> None:
        self._items: dict[str, FeatureExtractor] = {}

    def register(self, extractor: FeatureExtractor) -> FeatureExtractor:
        if not extractor.name:
            raise ValueError("extractor phải có tên")
        if extractor.name in self._items:
            raise ValueError(f"extractor trùng tên: {extractor.name}")
        if not extractor.feature_names:
            raise ValueError(f"{extractor.name} không khai báo cột đặc trưng nào")
        self._items[extractor.name] = extractor
        return extractor

    def replace(self, extractor: FeatureExtractor) -> FeatureExtractor:
        self._items[extractor.name] = extractor
        return extractor

    def unregister(self, name: str) -> None:
        self._items.pop(name, None)

    def get(self, name: str) -> FeatureExtractor:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(
                f"chưa đăng ký extractor {name!r}; hiện có: {sorted(self._items)}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def build_matrix(self, ctx: FeatureContext) -> FeatureMatrix:
        if not self._items:
            raise ValueError("chưa đăng ký extractor nào")

        blocks: list[np.ndarray] = []
        columns: list[str] = []
        groups: dict[str, tuple[int, int]] = {}
        cursor = 0
        for name in self.names():
            extractor = self._items[name]
            block = validate_block(extractor.extract(ctx), extractor)
            blocks.append(block)
            columns.extend(f"{name}.{col}" for col in extractor.feature_names)
            groups[name] = (cursor, cursor + block.shape[1])
            cursor += block.shape[1]

        return FeatureMatrix(
            values=np.hstack(blocks),
            columns=tuple(columns),
            groups=groups,
        )


_TWO_NHAY_BASELINE: float = float(
    1.0
    - (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY
    - LOTO_DRAWS_PER_DAY
    * UNIFORM_TWO_DIGIT_RATE
    * (1.0 - UNIFORM_TWO_DIGIT_RATE) ** (LOTO_DRAWS_PER_DAY - 1)
)


@dataclass
class DoubleHitBridgeExtractor:

    window_days: int = 30
    correlation_days: int = 180
    name: str = "double_hit"
    description: str = "Mật độ nổ kép 30 kỳ và tương quan xiên cặp"
    feature_names: tuple[str, ...] = field(
        default_factory=lambda: (
            "double_rate",
            "double_excess",
            "partner_correlation",
            "partner_cohit_rate",
        )
    )

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        out = np.zeros((NUMBER_SPACE, len(self.feature_names)), dtype=np.float64)

        counts = ctx.counts(self.window_days)
        if counts.size:
            double_rate = (counts >= 2).mean(axis=0)
            out[:, 0] = double_rate
            out[:, 1] = double_rate - _TWO_NHAY_BASELINE

        hits = ctx.hits(self.correlation_days).astype(np.float64)
        today = ctx.hits(1)[0] if ctx.history_length else np.zeros(NUMBER_SPACE, bool)
        if hits.shape[0] >= 2 and today.any():
            out[:, 2], out[:, 3] = self._partner_signals(hits, today)
        return out

    @staticmethod
    def _partner_signals(hits: np.ndarray, today: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        centred = hits - hits.mean(axis=0, keepdims=True)
        norms = np.sqrt((centred**2).sum(axis=0))
        safe = np.where(norms > _EPS, norms, 1.0)
        correlation = (centred.T @ centred) / np.outer(safe, safe)
        np.fill_diagonal(correlation, 0.0)

        partners = np.flatnonzero(today)
        mean_correlation = correlation[:, partners].mean(axis=1)

        cohit = hits.T @ hits[:, partners]
        appearances = np.maximum(hits.sum(axis=0), 1.0)[:, None]
        mean_cohit = (cohit / appearances).mean(axis=1)
        return mean_correlation, mean_cohit


_OFFSETS: dict[str, int] = {}
_cursor = 0
for _field, _width in FIELD_WIDTHS:
    _OFFSETS[_field] = _cursor
    _cursor += _width


def pascal_reduce(digits: np.ndarray) -> int:
    row = np.asarray(digits, dtype=np.int16)
    if row.size < 2:
        raise ValueError("cầu Pascal cần ít nhất hai chữ số")
    while row.size > 2:
        row = (row[:-1] + row[1:]) % 10
    return int(10 * row[0] + row[1])


@dataclass
class GeometricBridgeExtractor:

    name: str = "geometric"
    description: str = "Cầu Pascal, hình trám và kẹp nách trên bảng kết quả"
    feature_names: tuple[str, ...] = field(
        default_factory=lambda: (
            "pascal_hit",
            "diamond_hit",
            "diamond_weight",
            "clamped_hit",
            "clamped_weight",
        )
    )

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        digits = ctx.last_digits()
        out = np.zeros((NUMBER_SPACE, len(self.feature_names)), dtype=np.float64)

        special = digits[_OFFSETS["special"] : _OFFSETS["special"] + 5]
        prize1 = digits[_OFFSETS["prize1"] : _OFFSETS["prize1"] + 5]
        out[pascal_reduce(np.concatenate([special, prize1])), 0] = 1.0

        diamond = self._diamond_numbers(digits)
        self._fill(out, diamond, hit_column=1, weight_column=2)

        clamped = self._clamped_numbers(digits)
        self._fill(out, clamped, hit_column=3, weight_column=4)
        return out

    @staticmethod
    def _fill(out: np.ndarray, numbers: list[int], *, hit_column: int, weight_column: int) -> None:
        if not numbers:
            return
        counts = np.bincount(np.asarray(numbers), minlength=NUMBER_SPACE).astype(float)
        out[:, hit_column] = (counts > 0).astype(float)
        out[:, weight_column] = counts / counts.sum()

    @staticmethod
    def _diamond_numbers(digits: np.ndarray) -> list[int]:
        fields = [name for name, _ in FIELD_WIDTHS]
        found: list[int] = []
        for index in range(len(fields) - 2):
            trio = fields[index : index + 3]
            width = min(dict(FIELD_WIDTHS)[name] for name in trio)
            for column in range(width):
                a, b, c = (digits[_OFFSETS[name] + column] for name in trio)
                if a == c and a != b:
                    found.append(int(10 * b + a))
        return found

    @staticmethod
    def _clamped_numbers(digits: np.ndarray) -> list[int]:
        found: list[int] = []
        for name, width in FIELD_WIDTHS:
            if width < 3:
                continue
            row = digits[_OFFSETS[name] : _OFFSETS[name] + width]
            for index in range(1, width - 1):
                if row[index - 1] == row[index + 1] and row[index] != row[index - 1]:
                    found.append(int(10 * row[index] + row[index - 1]))
        return found


_LAPLACE = 1.0


@dataclass
class PatternMemoryExtractor:

    memory_days: int = 365
    name: str = "pattern_memory"
    description: str = "Bạc nhớ ma trận điều kiện và Z-score nhịp gan"
    feature_names: tuple[str, ...] = field(
        default_factory=lambda: (
            "memory_prob",
            "memory_excess",
            "gap_current",
            "gap_zscore",
            "gap_ratio",
        )
    )

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        out = np.zeros((NUMBER_SPACE, len(self.feature_names)), dtype=np.float64)
        hits = ctx.hits(self.memory_days)
        if hits.shape[0] >= 2:
            out[:, 0], out[:, 1] = self._memory_signals(hits, ctx.hits(1)[0])

        full = ctx.hits()
        if full.shape[0]:
            out[:, 2], out[:, 3], out[:, 4] = self._gap_signals(full)
        return out

    @staticmethod
    def _memory_signals(hits: np.ndarray, today: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        previous = hits[:-1].astype(np.float64)
        following = hits[1:].astype(np.float64)
        joint = previous.T @ following
        occurrences = previous.sum(axis=0)[:, None]
        table = (joint + _LAPLACE) / (occurrences + _LAPLACE * NUMBER_SPACE)

        partners = np.flatnonzero(today)
        if partners.size == 0:
            return np.zeros(NUMBER_SPACE), np.zeros(NUMBER_SPACE)
        probability = table[partners].mean(axis=0)
        return probability, probability - baseline_rate("loto")

    @staticmethod
    def _gap_signals(
        hits: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n_days = hits.shape[0]
        current = np.full(NUMBER_SPACE, float(n_days))
        zscore = np.zeros(NUMBER_SPACE)
        ratio = np.zeros(NUMBER_SPACE)

        for number in range(NUMBER_SPACE):
            days = np.flatnonzero(hits[:, number])
            if days.size == 0:
                continue
            current[number] = float(n_days - 1 - days[-1])
            if days.size < 3:
                continue
            intervals = np.diff(days).astype(np.float64)
            mean = float(intervals.mean())
            std = float(intervals.std(ddof=1)) if intervals.size > 1 else 0.0
            if std > _EPS:
                zscore[number] = (current[number] - mean) / std
            if mean > _EPS:
                ratio[number] = current[number] / mean
        return current, zscore, ratio


_HEAD: Final[np.ndarray] = np.array([head(n) for n in range(NUMBER_SPACE)], dtype=np.int16)
_TAIL: Final[np.ndarray] = np.array([tail(n) for n in range(NUMBER_SPACE)], dtype=np.int16)
_SUM: Final[np.ndarray] = np.array(
    [digit_sum_mod10(n) for n in range(NUMBER_SPACE)], dtype=np.int16
)
_BONG_DUONG: Final[np.ndarray] = np.array(
    [int(bong_duong(n)) for n in range(NUMBER_SPACE)], dtype=np.int16
)
_BONG_AM: Final[np.ndarray] = np.array(
    [int(bong_am(n)) for n in range(NUMBER_SPACE)], dtype=np.int16
)
_BO_ID: Final[np.ndarray] = np.array(
    [min(int(item) for item in bo(n)) for n in range(NUMBER_SPACE)], dtype=np.int16
)

DAN_SIZES: Final[tuple[int, ...]] = (36, 64)


def touches(number: int) -> tuple[int, int]:
    text = normalize_two_digit(number)
    return int(text[0]), int(text[1])


@dataclass
class SpecialSetExtractor:

    window_days: int = 7
    name: str = "special_set"
    description: str = "Bộ số, chạm, tổng và bóng của giải Đặc Biệt gần đây"
    feature_names: tuple[str, ...] = field(
        default_factory=lambda: (
            "touch_rate",
            "sum_rate",
            "bo_rate",
            "shadow_rate",
            "head_rate",
            "tail_rate",
        )
    )

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        out = np.zeros((NUMBER_SPACE, len(self.feature_names)), dtype=np.float64)
        recent = ctx.de_index(self.window_days)
        if recent.size == 0:
            return out

        numbers = np.arange(NUMBER_SPACE)
        out[:, 0] = self._share(recent, numbers, lambda x: np.stack([_HEAD[x], _TAIL[x]], axis=-1))
        out[:, 1] = self._equal_rate(_SUM[recent], _SUM[numbers])
        out[:, 2] = self._equal_rate(_BO_ID[recent], _BO_ID[numbers])
        out[:, 3] = self._shadow_rate(recent, numbers)
        out[:, 4] = self._equal_rate(_HEAD[recent], _HEAD[numbers])
        out[:, 5] = self._equal_rate(_TAIL[recent], _TAIL[numbers])
        return out

    @staticmethod
    def _equal_rate(recent_key: np.ndarray, number_key: np.ndarray) -> np.ndarray:
        return (number_key[:, None] == recent_key[None, :]).mean(axis=1)

    @staticmethod
    def _share(recent: np.ndarray, numbers: np.ndarray, key) -> np.ndarray:
        recent_keys = key(recent)
        number_keys = key(numbers)
        shared = (number_keys[:, None, :, None] == recent_keys[None, :, None, :]).any(axis=(2, 3))
        return shared.mean(axis=1)

    @staticmethod
    def _shadow_rate(recent: np.ndarray, numbers: np.ndarray) -> np.ndarray:
        duong = _BONG_DUONG[recent]
        am = _BONG_AM[recent]
        match = (numbers[:, None] == duong[None, :]) | (numbers[:, None] == am[None, :])
        return match.mean(axis=1)

    def build_dan(self, ctx: FeatureContext, size: int = 36) -> list[str]:
        if size <= 0 or size > NUMBER_SPACE:
            raise ValueError(f"kích thước dàn phải trong 1..{NUMBER_SPACE}")
        block = self.extract(ctx)
        score = block[:, 0] + block[:, 1]
        order = np.lexsort((np.arange(NUMBER_SPACE), -score))
        return [normalize_two_digit(int(n)) for n in order[:size]]


__all__ = [
    "DAN_SIZES",
    "DoubleHitBridgeExtractor",
    "FeatureContext",
    "FeatureExtractor",
    "FeatureMatrix",
    "FeatureRegistry",
    "GeometricBridgeExtractor",
    "PatternMemoryExtractor",
    "SpecialSetExtractor",
    "default_registry",
    "pascal_reduce",
    "touches",
    "validate_block",
]


def default_registry() -> FeatureRegistry:
    registry = FeatureRegistry()
    registry.register(GeometricBridgeExtractor())
    registry.register(DoubleHitBridgeExtractor())
    registry.register(PatternMemoryExtractor())
    registry.register(SpecialSetExtractor())
    return registry
