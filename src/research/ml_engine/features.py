from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from research.ml_engine.schema import NUMBER_SPACE

FREQUENCY_WINDOWS: Final[tuple[int, ...]] = (7, 14, 30, 90, 180)

MIN_HISTORY: Final[int] = 60

FOURIER_WINDOW: Final[int] = 128


@dataclass(frozen=True)
class FeatureMatrix:

    values: np.ndarray
    names: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.values.shape != (NUMBER_SPACE, len(self.names)):
            raise ValueError(
                f"values phải có dạng ({NUMBER_SPACE}, {len(self.names)}), nhận {self.values.shape}"
            )

    def select(self, keep: list[str]) -> FeatureMatrix:
        index = {name: position for position, name in enumerate(self.names)}
        missing = [name for name in keep if name not in index]
        if missing:
            raise KeyError(f"không có cột: {missing}")
        columns = [index[name] for name in keep]
        return FeatureMatrix(values=self.values[:, columns], names=tuple(keep))


def _gaps(hits: np.ndarray) -> np.ndarray:
    n = hits.shape[0]
    ever = hits.any(axis=0)
    last = np.where(ever, n - 1 - np.argmax(hits[::-1], axis=0), -1)
    return (n - 1 - last).astype(float)


def _mean_gap(hits: np.ndarray) -> np.ndarray:
    n = hits.shape[0]
    out = np.full(NUMBER_SPACE, float(n))
    for number in range(NUMBER_SPACE):
        days = np.flatnonzero(hits[:, number])
        if days.size >= 2:
            out[number] = float(np.diff(days).mean())
    return out


def _fourier(hits: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    window = hits[-FOURIER_WINDOW:].astype(float)
    length = window.shape[0]
    if length < 16:
        return np.zeros(NUMBER_SPACE), np.zeros(NUMBER_SPACE)

    centred = window - window.mean(axis=0, keepdims=True)
    spectrum = np.abs(np.fft.rfft(centred, axis=0)) ** 2
    spectrum = spectrum[1:]
    total = spectrum.sum(axis=0)
    safe_total = np.where(total > 0, total, 1.0)

    weekly_bin = max(int(round(length / 7.0)) - 1, 0)
    weekly = spectrum[min(weekly_bin, spectrum.shape[0] - 1)] / safe_total
    peak = spectrum.max(axis=0) / safe_total
    return weekly, peak


def build_features(counts: np.ndarray, day: int) -> FeatureMatrix:
    if not 0 <= day <= counts.shape[0]:
        raise ValueError(f"day phải nằm trong [0, {counts.shape[0]}], nhận {day}")

    past = counts[:day]
    names: list[str] = []
    columns: list[np.ndarray] = []

    if past.shape[0] < MIN_HISTORY:
        probe = build_features(
            np.zeros((MIN_HISTORY, NUMBER_SPACE), dtype=counts.dtype), MIN_HISTORY
        )
        return FeatureMatrix(values=np.zeros((NUMBER_SPACE, len(probe.names))), names=probe.names)

    hits = past > 0
    n = hits.shape[0]

    for window in FREQUENCY_WINDOWS:
        columns.append(hits[-window:].mean(axis=0))
        names.append(f"rate_{window}d")

    gaps = _gaps(hits)
    mean_gap = _mean_gap(hits)
    columns.append(np.minimum(gaps, 60.0) / 60.0)
    names.append("gap_days")
    columns.append(np.clip(gaps / np.maximum(mean_gap, 1e-9), 0.0, 5.0) / 5.0)
    names.append("gap_over_mean")

    for lag in (1, 2, 3):
        columns.append(hits[-lag].astype(float) if n >= lag else np.zeros(NUMBER_SPACE))
        names.append(f"hit_lag_{lag}")

    for window in (30, 90):
        columns.append((past[-window:] >= 2).mean(axis=0))
        names.append(f"double_rate_{window}d")

    weekly, peak = _fourier(hits)
    columns.extend([weekly, peak])
    names.extend(["fourier_weekly", "fourier_peak"])

    numbers = np.arange(NUMBER_SPACE)
    tens, units = numbers // 10, numbers % 10
    columns.append((tens + units) / 18.0)
    names.append("digit_sum")
    columns.append(np.abs(tens - units) / 9.0)
    names.append("digit_span")
    columns.append((tens == units).astype(float))
    names.append("is_double_digit")

    index = {name: position for position, name in enumerate(names)}
    short_rate = columns[index["rate_7d"]]
    long_rate = columns[index["rate_180d"]]
    gap_norm = columns[index["gap_days"]]
    columns.append(short_rate * gap_norm)
    names.append("cross_hot_and_overdue")
    columns.append(short_rate - long_rate)
    names.append("cross_momentum")
    columns.append(gap_norm * columns[index["gap_over_mean"]])
    names.append("cross_overdue_squared")

    return FeatureMatrix(values=np.stack(columns, axis=1).astype(np.float64), names=tuple(names))


def build_training_table(
    counts: np.ndarray, *, start: int, stop: int
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    if not 0 <= start < stop <= counts.shape[0]:
        raise ValueError(f"khoảng ngày không hợp lệ: [{start}, {stop}) trên {counts.shape[0]} ngày")

    blocks, labels, names = [], [], None
    for day in range(start, stop):
        matrix = build_features(counts, day)
        names = matrix.names
        blocks.append(matrix.values)
        labels.append((counts[day] > 0).astype(np.int8))
    assert names is not None
    return np.concatenate(blocks, axis=0), np.concatenate(labels, axis=0), names
