from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from scipy import stats

from core.calendar_alignment import require_daily_contiguous
from core.number_reference import BONG_AM, BONG_DUONG, bo
from core.xsmb_domain import (
    FIELD_WIDTHS,
    LOTO_DRAWS_PER_DAY,
    TOTAL_DIGITS,
    UNIFORM_TWO_DIGIT_RATE,
    build_position_labels,
    raw_digit_matrix,
)


NUMBER_SPACE: Final[int] = 100

_LAST_TWO: Final[tuple[tuple[int, int], ...]] = tuple(
    (offset + width - 2, offset + width - 1)
    for offset, width in zip(
        np.cumsum([0, *[w for _, w in FIELD_WIDTHS[:-1]]]).tolist(),
        [w for _, w in FIELD_WIDTHS],
        strict=True,
    )
)


@dataclass(frozen=True)
class DigitTensor:

    values: np.ndarray
    dates: pd.DatetimeIndex
    position_labels: tuple[str, ...]
    loto_counts: np.ndarray
    de_index: np.ndarray

    def __post_init__(self) -> None:
        if self.values.ndim != 2 or self.values.shape[1] != TOTAL_DIGITS:
            raise ValueError(f"values phải có dạng (n, {TOTAL_DIGITS})")
        if len(self.dates) != self.values.shape[0]:
            raise ValueError("dates và values phải cùng độ dài")
        if self.loto_counts.shape != (self.values.shape[0], NUMBER_SPACE):
            raise ValueError(f"loto_counts phải có dạng (n, {NUMBER_SPACE})")
        if self.de_index.shape != (self.values.shape[0],):
            raise ValueError("de_index phải có một phần tử mỗi ngày")

    @property
    def n_days(self) -> int:
        return int(self.values.shape[0])

    @property
    def n_positions(self) -> int:
        return int(self.values.shape[1])

    def loto_hits(self) -> np.ndarray:
        return self.loto_counts > 0

    def loto_double_hits(self) -> np.ndarray:
        return self.loto_counts >= 2

    @classmethod
    def from_raw(cls, df_raw: pd.DataFrame) -> DigitTensor:
        if "date" not in df_raw.columns:
            raise ValueError("bảng kết quả thô thiếu cột 'date'")
        frame = df_raw.sort_values("date", kind="stable").reset_index(drop=True)
        dates = require_daily_contiguous(frame["date"], context="quét cầu ghép chéo ngày")

        values = raw_digit_matrix(frame)
        labels = tuple(build_position_labels())

        n_days = values.shape[0]
        pairs = np.empty((n_days, len(_LAST_TWO)), dtype=np.int16)
        for slot, (hi, lo) in enumerate(_LAST_TWO):
            pairs[:, slot] = values[:, hi].astype(np.int16) * 10 + values[:, lo]

        counts = np.zeros((n_days, NUMBER_SPACE), dtype=np.uint8)
        rows = np.repeat(np.arange(n_days), pairs.shape[1])
        np.add.at(counts, (rows, pairs.ravel()), 1)

        de_index = pairs[:, 0].astype(np.int16)

        return cls(
            values=values,
            dates=dates,
            position_labels=labels,
            loto_counts=counts,
            de_index=de_index,
        )


TRANSFORM_CONCAT: Final[str] = "concat"
TRANSFORM_REVERSE_CONCAT: Final[str] = "reverse_concat"
TRANSFORM_REVERSE_PAIR: Final[str] = "reverse_pair"
TRANSFORM_BO: Final[str] = "bo"

TRANSFORMATIONS: Final[tuple[str, ...]] = (
    TRANSFORM_CONCAT,
    TRANSFORM_REVERSE_CONCAT,
    TRANSFORM_REVERSE_PAIR,
    TRANSFORM_BO,
)

TARGET_LOTO: Final[str] = "loto"
TARGET_LOTO_2_NHAY: Final[str] = "loto_2_nhay"
TARGET_DE: Final[str] = "de"

TARGET_TYPES: Final[tuple[str, ...]] = (TARGET_LOTO, TARGET_LOTO_2_NHAY, TARGET_DE)


@dataclass(frozen=True)
class CrossDayPatternSpec:

    position_a: int
    position_b: int
    lag_a: int
    lag_b: int
    transformation: str = TRANSFORM_CONCAT
    shadow: str = "thuc"

    def __post_init__(self) -> None:
        if self.lag_a < 1 or self.lag_b < 1:
            raise ValueError("độ trễ phải tính bằng số ngày dương")
        if self.transformation not in TRANSFORMATIONS:
            raise ValueError(f"phép biến đổi không hợp lệ: {self.transformation!r}")

    @property
    def span(self) -> int:
        return abs(self.lag_a - self.lag_b) + 1

    @property
    def identifier(self) -> str:
        return (
            f"{self.transformation}|{self.shadow}|"
            f"p{self.position_a}@T-{self.lag_a}+p{self.position_b}@T-{self.lag_b}"
        )


def default_lag_pairs(max_span: int = 3) -> tuple[tuple[int, int], ...]:
    if max_span < 1:
        raise ValueError("max_span phải ít nhất bằng 1")
    pairs = [(1, 1)]
    pairs.extend((k, k - 1) for k in range(2, max_span + 1))
    return tuple(pairs)


KIND_THUC: Final[str] = "thuc"
KIND_BONG_DUONG: Final[str] = "bong_duong"
KIND_BONG_AM: Final[str] = "bong_am"

SHADOW_KINDS: Final[tuple[str, ...]] = (KIND_THUC, KIND_BONG_DUONG, KIND_BONG_AM)


def _lookup_table(mapping: dict[int, int]) -> np.ndarray:
    table = np.arange(10, dtype=np.uint8)
    for source, target in mapping.items():
        table[int(source)] = np.uint8(int(target))
    return table


_TABLES: Final[dict[str, np.ndarray]] = {
    KIND_THUC: np.arange(10, dtype=np.uint8),
    KIND_BONG_DUONG: _lookup_table(BONG_DUONG),
    KIND_BONG_AM: _lookup_table(BONG_AM),
}


def shadow_table(kind: str) -> np.ndarray:
    try:
        return _TABLES[kind]
    except KeyError:
        raise ValueError(
            f"loại bóng không hợp lệ: {kind!r}; hiện có {list(SHADOW_KINDS)}"
        ) from None


def apply_shadow(kind: str, digits: np.ndarray) -> np.ndarray:
    if digits.size and (digits.min() < 0 or digits.max() > 9):
        raise ValueError("chữ số phải nằm trong 0..9")
    return shadow_table(kind)[digits]


_MAX_BO_MEMBERS: Final[int] = 8


def _bo_membership() -> np.ndarray:
    table = np.empty((NUMBER_SPACE, _MAX_BO_MEMBERS), dtype=np.int16)
    for number in range(NUMBER_SPACE):
        members = sorted(int(item) for item in bo(number))
        if not members:
            members = [number]
        repeats = -(-_MAX_BO_MEMBERS // len(members))
        table[number] = (members * repeats)[:_MAX_BO_MEMBERS]
    return table


_BO_TABLE: Final[np.ndarray] = _bo_membership()


_BO_SIZE: Final[np.ndarray] = np.array(
    [len({int(item) for item in bo(number)}) for number in range(NUMBER_SPACE)],
    dtype=np.int16,
)

_MAX_SET_SIZE: Final[int] = int(_BO_SIZE.max())


def _two_nhay_rate(set_size: int) -> float:
    n, m = LOTO_DRAWS_PER_DAY, int(set_size)
    if m <= 0:
        return 0.0
    q = m * UNIFORM_TWO_DIGIT_RATE
    all_at_most_once = 0.0
    for j in range(0, min(n, m) + 1):
        distinct = 1.0
        for i in range(j):
            distinct *= (m - i) / m
        all_at_most_once += math.comb(n, j) * q**j * (1.0 - q) ** (n - j) * distinct
    return float(1.0 - all_at_most_once)


def target_baseline_rate(target_type: str, set_size: int = 1) -> float:
    m = int(set_size)
    if m <= 0:
        return 0.0
    if target_type == TARGET_DE:
        return float(min(1.0, m * UNIFORM_TWO_DIGIT_RATE))
    if target_type == TARGET_LOTO_2_NHAY:
        return _two_nhay_rate(m)
    return float(1.0 - (1.0 - m * UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY)


def baseline_rate_table(target_type: str) -> np.ndarray:
    return np.array(
        [target_baseline_rate(target_type, m) for m in range(_MAX_SET_SIZE + 1)],
        dtype=np.float64,
    )


_RARE_EVENT_RATE: Final[float] = 0.1


def _tail_probability(
    successes: np.ndarray,
    expected: np.ndarray,
    variance: np.ndarray,
    day_rate: np.ndarray,
) -> np.ndarray:
    rare = float(np.max(day_rate)) <= _RARE_EVENT_RATE
    if rare:
        return np.asarray(stats.poisson.sf(successes - 1, expected), dtype=float)
    z = (successes - 0.5 - expected) / np.sqrt(variance)
    return np.asarray(stats.norm.sf(z), dtype=float)


@dataclass(frozen=True)
class BridgeScanResult:

    frame: pd.DataFrame
    target_type: str
    baseline: float
    n_days_evaluated: int

    @property
    def n_hypotheses(self) -> int:
        return int(len(self.frame))

    def running(self, min_streak: int = 5) -> pd.DataFrame:
        return self.frame[self.frame["current_streak"] >= min_streak]


class BridgeScanner:

    def __init__(
        self,
        *,
        max_span: int = 3,
        shadows: tuple[str, ...] = SHADOW_KINDS,
        transformations: tuple[str, ...] = TRANSFORMATIONS,
    ) -> None:
        unknown_shadow = [s for s in shadows if s not in SHADOW_KINDS]
        if unknown_shadow:
            raise ValueError(f"loại bóng không hợp lệ: {unknown_shadow}")
        unknown_transform = [t for t in transformations if t not in TRANSFORMATIONS]
        if unknown_transform:
            raise ValueError(f"phép biến đổi không hợp lệ: {unknown_transform}")
        self.lag_pairs = default_lag_pairs(max_span)
        self.shadows = tuple(shadows)
        self.transformations = tuple(transformations)


    @staticmethod
    def _aligned_sources(
        tensor: DigitTensor, lag_a: int, lag_b: int, start: int
    ) -> tuple[np.ndarray, np.ndarray]:
        n = tensor.n_days
        a = tensor.values[start - lag_a : n - lag_a]
        b = tensor.values[start - lag_b : n - lag_b]
        return a, b

    @staticmethod
    def _hits_for(candidates: np.ndarray, target: np.ndarray, target_type: str) -> np.ndarray:
        rows = np.arange(candidates.shape[0])[:, None, None]
        if target_type == TARGET_DE:
            return candidates == target[:, None, None]
        return target[rows, candidates]

    def _evaluate_block(
        self,
        candidates: np.ndarray,
        target: np.ndarray,
        target_type: str,
        *,
        expand_bo: bool,
    ) -> tuple[np.ndarray, np.ndarray]:
        if not expand_bo:
            hits = self._hits_for(candidates, target, target_type)
            return hits, np.ones(candidates.shape, dtype=np.int16)

        members = _BO_TABLE[candidates]
        sizes = _BO_SIZE[candidates]
        if target_type == TARGET_DE:
            return (members == target[:, None, None, None]).any(axis=-1), sizes
        rows = np.arange(candidates.shape[0])[:, None, None, None]
        return target[rows, members].any(axis=-1), sizes


    @property
    def start_index(self) -> int:
        return max(max(pair) for pair in self.lag_pairs)

    def _target_for(self, tensor: DigitTensor, target_type: str) -> np.ndarray:
        start = self.start_index
        if target_type == TARGET_DE:
            return tensor.de_index[start:]
        if target_type == TARGET_LOTO_2_NHAY:
            return tensor.loto_double_hits()[start:]
        return tensor.loto_hits()[start:]

    def _iter_blocks(self, tensor: DigitTensor, target: np.ndarray, target_type: str):
        start = self.start_index
        for lag_a, lag_b in self.lag_pairs:
            raw_a, raw_b = self._aligned_sources(tensor, lag_a, lag_b, start)
            for shadow in self.shadows:
                table = shadow_table(shadow)
                a, b = table[raw_a], table[raw_b]
                forward = (10 * a[:, :, None] + b[:, None, :]).astype(np.uint8)
                reverse = (10 * b[:, None, :] + a[:, :, None]).astype(np.uint8)
                pair_sizes = np.where(forward == reverse, 1, 2).astype(np.int16)

                cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
                for transformation in self.transformations:
                    if transformation == TRANSFORM_CONCAT:
                        hits, sizes = self._evaluate_block(
                            forward, target, target_type, expand_bo=False
                        )
                    elif transformation == TRANSFORM_REVERSE_CONCAT:
                        hits, sizes = self._evaluate_block(
                            reverse, target, target_type, expand_bo=False
                        )
                    elif transformation == TRANSFORM_REVERSE_PAIR:
                        first = cache.get(TRANSFORM_CONCAT) or self._evaluate_block(
                            forward, target, target_type, expand_bo=False
                        )
                        second = cache.get(TRANSFORM_REVERSE_CONCAT) or self._evaluate_block(
                            reverse, target, target_type, expand_bo=False
                        )
                        hits, sizes = first[0] | second[0], pair_sizes
                    elif transformation == TRANSFORM_BO:
                        hits, sizes = self._evaluate_block(
                            forward, target, target_type, expand_bo=True
                        )
                    else:  # pragma: no cover - đã chặn ở __init__
                        raise ValueError(transformation)

                    if transformation in (TRANSFORM_CONCAT, TRANSFORM_REVERSE_CONCAT):
                        cache[transformation] = (hits, sizes)
                    yield hits, sizes, (lag_a, lag_b, shadow, transformation)
                cache.clear()

    def scan(self, tensor: DigitTensor, *, target_type: str = TARGET_LOTO) -> BridgeScanResult:
        if target_type not in TARGET_TYPES:
            raise ValueError(f"loại mục tiêu không hợp lệ: {target_type!r}")
        if tensor.n_days <= self.start_index:
            raise ValueError("lịch sử quá ngắn so với độ trễ lớn nhất")

        target = self._target_for(tensor, target_type)
        rate_table = baseline_rate_table(target_type)
        blocks = [
            self._summarise(
                hits,
                sizes,
                n_pos=tensor.n_positions,
                lag_a=meta[0],
                lag_b=meta[1],
                shadow=meta[2],
                transformation=meta[3],
                rate_table=rate_table,
            )
            for hits, sizes, meta in self._iter_blocks(tensor, target, target_type)
        ]
        return BridgeScanResult(
            frame=pd.concat(blocks, ignore_index=True),
            target_type=target_type,
            baseline=float(rate_table[1]),
            n_days_evaluated=tensor.n_days - self.start_index,
        )

    def family_max_skill(self, tensor: DigitTensor, target: np.ndarray, target_type: str) -> float:
        rate_table = baseline_rate_table(target_type)
        best = -np.inf
        for hits, sizes, _ in self._iter_blocks(tensor, target, target_type):
            skill = hits.mean(axis=0) - rate_table[sizes].mean(axis=0)
            best = max(best, float(skill.max()))
        return best

    def rebuild_hits(
        self,
        tensor: DigitTensor,
        rows: pd.DataFrame,
        *,
        target_type: str,
    ) -> tuple[RebuiltBridges, np.ndarray]:
        if target_type not in TARGET_TYPES:
            raise ValueError(f"loại mục tiêu không hợp lệ: {target_type!r}")
        start = max(max(pair) for pair in self.lag_pairs)
        n = tensor.n_days

        if target_type == TARGET_DE:
            target = tensor.de_index[start:]
        elif target_type == TARGET_LOTO_2_NHAY:
            target = tensor.loto_double_hits()[start:]
        else:
            target = tensor.loto_hits()[start:]

        members = np.empty((n - start, len(rows), _MAX_BO_MEMBERS), dtype=np.int16)
        sizes = np.empty((n - start, len(rows)), dtype=np.int16)

        for slot, (_, row) in enumerate(rows.iterrows()):
            table = shadow_table(str(row["shadow"]))
            lag_a, lag_b = int(row["lag_a"]), int(row["lag_b"])
            pos_a, pos_b = int(row["position_a"]), int(row["position_b"])
            a = table[tensor.values[start - lag_a : n - lag_a, pos_a]].astype(np.int16)
            b = table[tensor.values[start - lag_b : n - lag_b, pos_b]].astype(np.int16)
            forward = 10 * a + b
            reverse = 10 * b + a

            transformation = str(row["transformation"])
            if transformation == TRANSFORM_CONCAT:
                block, size = _pad_members(forward[:, None]), np.ones_like(forward)
            elif transformation == TRANSFORM_REVERSE_CONCAT:
                block, size = _pad_members(reverse[:, None]), np.ones_like(reverse)
            elif transformation == TRANSFORM_REVERSE_PAIR:
                block = _pad_members(forward[:, None], reverse[:, None])
                size = np.where(forward == reverse, 1, 2).astype(np.int16)
            elif transformation == TRANSFORM_BO:
                block = _BO_TABLE[forward][:, None, :]
                size = _BO_SIZE[forward]
            else:  # pragma: no cover - khung đã chặn từ __init__
                raise ValueError(transformation)

            members[:, slot, :] = block[:, 0, :]
            sizes[:, slot] = size

        return RebuiltBridges(members=members, sizes=sizes), target

    @staticmethod
    def _summarise(
        hits: np.ndarray,
        sizes: np.ndarray,
        *,
        n_pos: int,
        lag_a: int,
        lag_b: int,
        shadow: str,
        transformation: str,
        rate_table: np.ndarray,
    ) -> pd.DataFrame:
        n_days = hits.shape[0]
        successes = hits.sum(axis=0, dtype=np.int32).ravel()

        reversed_hits = hits[::-1].astype(np.uint8)
        streak = np.cumprod(reversed_hits, axis=0).sum(axis=0, dtype=np.int32).ravel()

        day_rate = rate_table[sizes]
        expected = day_rate.sum(axis=0).ravel()
        variance = np.maximum((day_rate * (1.0 - day_rate)).sum(axis=0).ravel(), 1e-9)
        p_value = _tail_probability(successes, expected, variance, day_rate)

        position_a, position_b = np.divmod(np.arange(n_pos * n_pos), n_pos)
        return pd.DataFrame(
            {
                "position_a": position_a.astype(np.int16),
                "position_b": position_b.astype(np.int16),
                "lag_a": np.int16(lag_a),
                "lag_b": np.int16(lag_b),
                "shadow": shadow,
                "transformation": transformation,
                "trials": np.int32(n_days),
                "successes": successes,
                "current_streak": streak,
                "precision": successes / n_days,
                "expected_rate": expected / n_days,
                "p_value": np.asarray(p_value, dtype=float),
            }
        )


@dataclass(frozen=True)
class RebuiltBridges:

    members: np.ndarray
    sizes: np.ndarray

    def hits_for(self, target: np.ndarray, target_type: str) -> np.ndarray:
        if target_type == TARGET_DE:
            return (self.members == target[:, None, None]).any(axis=-1)
        rows = np.arange(self.members.shape[0])[:, None, None]
        return target[rows, self.members].any(axis=-1)


def _pad_members(*columns: np.ndarray) -> np.ndarray:
    stacked = np.stack(columns, axis=-1).astype(np.int16)
    repeats = -(-_MAX_BO_MEMBERS // stacked.shape[-1])
    return np.tile(stacked, (1, 1, repeats))[:, :, :_MAX_BO_MEMBERS]
