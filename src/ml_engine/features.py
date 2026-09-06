"""Sinh đặc trưng tự động, có bảo đảm không rò rỉ thời gian.

Bất biến trung tâm
-------------------

Mọi cột đặc trưng cho ngày ``t`` phải là hàm của ``counts[:t]`` — nghiêm ngặt
quá khứ, không bao gồm ngày ``t``. Đây là bất biến duy nhất mà toàn bộ kết quả
đánh giá phía sau dựa vào, và nó không thể được bảo đảm bằng cách đọc mã cho
kỹ: một phép ``rolling().mean()`` của pandas mặc định *bao gồm* hàng hiện tại,
nên chỉ cần quên một lần ``shift(1)`` là mô hình nhìn thấy đáp án.

Vì vậy hàm ở đây nhận ``counts`` và ``day`` rồi tự cắt ``counts[:day]`` ngay
dòng đầu, và bộ kiểm thử khẳng định bất biến bằng cách sửa ``counts[day]`` rồi
so ma trận đặc trưng phải không đổi.

Các nhóm đặc trưng
-------------------

1. **Tần suất nhiều thang** — tỉ lệ về trong 7/14/30/90/180 ngày gần nhất.
2. **Nhịp gan** — số ngày kể từ lần về gần nhất, và độ gan so với trung bình
   lịch sử của chính con đó.
3. **Bạc nhớ** — trạng thái về/không của một, hai, ba ngày trước.
4. **Hai nháy** — tỉ lệ con đó về từ hai lần trở lên trong kỳ.
5. **Fourier** — biên độ thành phần chu kỳ 7 ngày và biên độ đỉnh phổ, bắt tính
   chu kỳ mà đặc trưng cửa sổ trượt không thấy.
6. **Cấu trúc chữ số** — tổng chữ số, hiệu chữ số, đôi (số kép).
7. **Tương tác chéo** — tích của các cặp đặc trưng có ý nghĩa miền, ví dụ
   "gan lâu *và* gần đây nóng".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from ml_engine.schema import NUMBER_SPACE

#: Các cửa sổ tần suất, tính bằng ngày.
FREQUENCY_WINDOWS: Final[tuple[int, ...]] = (7, 14, 30, 90, 180)

#: Số ngày lịch sử tối thiểu để đặc trưng có nghĩa.
MIN_HISTORY: Final[int] = 60

#: Cửa sổ dùng cho biến đổi Fourier.
FOURIER_WINDOW: Final[int] = 128


@dataclass(frozen=True)
class FeatureMatrix:
    """Ma trận đặc trưng kèm tên cột.

    Attributes:
        values: Mảng ``(100, d)``; hàng ``k`` là đặc trưng của con ``k``.
        names: Tên của ``d`` cột, cùng thứ tự với ``values``.
    """

    values: np.ndarray
    names: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.values.shape != (NUMBER_SPACE, len(self.names)):
            raise ValueError(
                f"values phải có dạng ({NUMBER_SPACE}, {len(self.names)}), nhận {self.values.shape}"
            )

    def select(self, keep: list[str]) -> FeatureMatrix:
        """Giữ lại một tập cột theo tên.

        Args:
            keep: Tên các cột cần giữ, theo thứ tự mong muốn.

        Returns:
            Ma trận chỉ còn các cột đã chọn.

        Raises:
            KeyError: Khi có tên cột không tồn tại.
        """
        index = {name: position for position, name in enumerate(self.names)}
        missing = [name for name in keep if name not in index]
        if missing:
            raise KeyError(f"không có cột: {missing}")
        columns = [index[name] for name in keep]
        return FeatureMatrix(values=self.values[:, columns], names=tuple(keep))


def _gaps(hits: np.ndarray) -> np.ndarray:
    """Số ngày kể từ lần về gần nhất, tính đến hết lịch sử đã cho.

    Args:
        hits: Ma trận nhị phân ``(n, 100)``.

    Returns:
        Mảng ``(100,)``; con chưa từng về nhận đúng ``n``.
    """
    n = hits.shape[0]
    ever = hits.any(axis=0)
    last = np.where(ever, n - 1 - np.argmax(hits[::-1], axis=0), -1)
    return (n - 1 - last).astype(float)


def _mean_gap(hits: np.ndarray) -> np.ndarray:
    """Khoảng cách trung bình giữa hai lần về, theo từng con."""
    n = hits.shape[0]
    out = np.full(NUMBER_SPACE, float(n))
    for number in range(NUMBER_SPACE):
        days = np.flatnonzero(hits[:, number])
        if days.size >= 2:
            out[number] = float(np.diff(days).mean())
    return out


def _fourier(hits: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Biên độ chu kỳ 7 ngày và biên độ đỉnh phổ, theo từng con.

    Args:
        hits: Ma trận nhị phân ``(n, 100)``.

    Returns:
        Cặp ``(biên độ chu kỳ tuần, biên độ đỉnh phổ)``, mỗi mảng ``(100,)``,
        đã chuẩn hóa theo tổng công suất nên so sánh được giữa các con.
    """
    window = hits[-FOURIER_WINDOW:].astype(float)
    length = window.shape[0]
    if length < 16:
        return np.zeros(NUMBER_SPACE), np.zeros(NUMBER_SPACE)

    centred = window - window.mean(axis=0, keepdims=True)
    spectrum = np.abs(np.fft.rfft(centred, axis=0)) ** 2
    spectrum = spectrum[1:]  # bỏ thành phần một chiều
    total = spectrum.sum(axis=0)
    safe_total = np.where(total > 0, total, 1.0)

    # Chỉ số tần số ứng với chu kỳ 7 ngày, làm tròn về bin gần nhất.
    weekly_bin = max(int(round(length / 7.0)) - 1, 0)
    weekly = spectrum[min(weekly_bin, spectrum.shape[0] - 1)] / safe_total
    peak = spectrum.max(axis=0) / safe_total
    return weekly, peak


def build_features(counts: np.ndarray, day: int) -> FeatureMatrix:
    """Dựng ma trận đặc trưng cho ngày ``day``, chỉ dùng dữ liệu trước đó.

    Args:
        counts: Ma trận đếm ``(n_days, 100)`` của toàn lịch sử.
        day: Chỉ số ngày cần dự đoán. Chỉ ``counts[:day]`` được đọc.

    Returns:
        Ma trận đặc trưng ``(100, d)`` kèm tên cột.

    Raises:
        ValueError: Khi ``day`` nằm ngoài phạm vi.
    """
    if not 0 <= day <= counts.shape[0]:
        raise ValueError(f"day phải nằm trong [0, {counts.shape[0]}], nhận {day}")

    past = counts[:day]
    names: list[str] = []
    columns: list[np.ndarray] = []

    if past.shape[0] < MIN_HISTORY:
        # Lịch sử quá ngắn: trả ma trận 0 có đúng hình dạng thay vì đặc trưng
        # tính từ vài ngày, vốn nhiễu hơn là có ích.
        probe = build_features(
            np.zeros((MIN_HISTORY, NUMBER_SPACE), dtype=counts.dtype), MIN_HISTORY
        )
        return FeatureMatrix(values=np.zeros((NUMBER_SPACE, len(probe.names))), names=probe.names)

    hits = past > 0
    n = hits.shape[0]

    # 1. Tần suất nhiều thang.
    for window in FREQUENCY_WINDOWS:
        columns.append(hits[-window:].mean(axis=0))
        names.append(f"rate_{window}d")

    # 2. Nhịp gan.
    gaps = _gaps(hits)
    mean_gap = _mean_gap(hits)
    columns.append(np.minimum(gaps, 60.0) / 60.0)
    names.append("gap_days")
    columns.append(np.clip(gaps / np.maximum(mean_gap, 1e-9), 0.0, 5.0) / 5.0)
    names.append("gap_over_mean")

    # 3. Bạc nhớ.
    for lag in (1, 2, 3):
        columns.append(hits[-lag].astype(float) if n >= lag else np.zeros(NUMBER_SPACE))
        names.append(f"hit_lag_{lag}")

    # 4. Hai nháy.
    for window in (30, 90):
        columns.append((past[-window:] >= 2).mean(axis=0))
        names.append(f"double_rate_{window}d")

    # 5. Fourier.
    weekly, peak = _fourier(hits)
    columns.extend([weekly, peak])
    names.extend(["fourier_weekly", "fourier_peak"])

    # 6. Cấu trúc chữ số — hằng số theo con, để mô hình tự quyết có dùng không.
    numbers = np.arange(NUMBER_SPACE)
    tens, units = numbers // 10, numbers % 10
    columns.append((tens + units) / 18.0)
    names.append("digit_sum")
    columns.append(np.abs(tens - units) / 9.0)
    names.append("digit_span")
    columns.append((tens == units).astype(float))
    names.append("is_double_digit")

    # 7. Tương tác chéo — các tích có nghĩa trong miền.
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
    """Xếp chồng đặc trưng và nhãn cho khoảng ngày ``[start, stop)``.

    Mỗi ngày đóng góp 100 hàng, mỗi hàng là một con. Nhãn của hàng ``(t, k)`` là
    ``counts[t, k] > 0`` — kết quả *của chính ngày t*, trong khi đặc trưng chỉ
    dùng tới ``t-1``. Đó là ranh giới duy nhất cần giữ đúng.

    Args:
        counts: Ma trận đếm toàn lịch sử.
        start: Ngày đầu tiên đưa vào bảng, đã bao gồm.
        stop: Ngày cuối, không bao gồm.

    Returns:
        Bộ ba ``(X, y, tên cột)`` với ``X`` dạng ``((stop-start)*100, d)``.

    Raises:
        ValueError: Khi khoảng ngày rỗng hoặc ngoài phạm vi.
    """
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
