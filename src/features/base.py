"""Hợp đồng chung cho mọi extractor đặc trưng soi cầu.

Ba điều khung bảo đảm, không phó mặc cho từng extractor:

1. **Không rò rỉ tương lai.** :class:`FeatureContext` chỉ phơi ra lịch sử tính
   tới ``anchor_index``. Ngày mục tiêu không nằm trong tầm với, nên một extractor
   không thể vô tình đọc kết quả mà nó đang dự đoán — cùng cơ chế mà
   ``predictor_strategies`` dùng.
2. **Hình dạng thống nhất.** Mọi extractor trả về ma trận ``(100, k)``: một hàng
   cho mỗi con số 00–99, cột là các đặc trưng. Nhờ vậy ghép chúng lại là phép
   nối ngang, không cần lớp điều phối nào biết chi tiết từng phương pháp.
3. **Nhóm cột được giữ tên.** :class:`FeatureMatrix` nhớ cột nào thuộc extractor
   nào, nên phần giải thích dự đoán quy được đóng góp về đúng phương pháp thay
   vì về một chỉ số cột vô danh.

Lưu ý về tính xác thực của phương pháp dân gian: các phương pháp soi cầu kinh
điển không có định nghĩa chuẩn duy nhất. Mỗi extractor hiện thực MỘT cách hình
thức hóa cụ thể và ghi rõ cách đó trong tài liệu lớp. Việc cách hình thức hóa ấy
có mang tín hiệu hay không là câu hỏi để đo, không phải để giả định.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

import numpy as np

from bridges.tensor import NUMBER_SPACE, DigitTensor

_EPS: Final[float] = 1e-9


@dataclass(frozen=True)
class FeatureContext:
    """Lát cắt lịch sử mà một extractor được phép đọc."""

    tensor: DigitTensor
    anchor_index: int

    def __post_init__(self) -> None:
        if not 0 <= self.anchor_index < self.tensor.n_days:
            raise ValueError("anchor_index nằm ngoài phạm vi lịch sử")

    @property
    def history_length(self) -> int:
        """Số ngày quan sát được, tính cả ngày neo."""
        return self.anchor_index + 1

    def digits(self, days: int | None = None) -> np.ndarray:
        """Chữ số theo vị trí của ``days`` ngày gần nhất tính tới ngày neo."""
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.values[start:stop]

    def hits(self, days: int | None = None) -> np.ndarray:
        """Ma trận trúng lô tô ``(ngày, 100)`` trong cửa sổ."""
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.loto_hits()[start:stop]

    def counts(self, days: int | None = None) -> np.ndarray:
        """Số nháy lô tô ``(ngày, 100)`` trong cửa sổ."""
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.loto_counts[start:stop]

    def de_index(self, days: int | None = None) -> np.ndarray:
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.de_index[start:stop]

    def last_digits(self) -> np.ndarray:
        """Chữ số theo vị trí của đúng ngày neo."""
        return self.tensor.values[self.anchor_index]


@runtime_checkable
class FeatureExtractor(Protocol):
    """Hợp đồng tối thiểu của một bộ trích đặc trưng."""

    name: str
    description: str
    feature_names: tuple[str, ...]

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        """Trả về ma trận ``(100, len(feature_names))`` giá trị hữu hạn."""
        ...


@dataclass(frozen=True)
class FeatureMatrix:
    """Ma trận đặc trưng đã ghép, còn nhớ cột nào thuộc phương pháp nào."""

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
    """Ép mọi extractor về đúng hợp đồng trước khi khối của nó được ghép vào.

    Một cột NaN lọt vào ma trận sẽ lan ra toàn bộ mô hình phía sau và rất khó
    truy ngược, nên chặn ngay tại biên rẻ hơn nhiều.
    """
    expected = (NUMBER_SPACE, len(extractor.feature_names))
    if block.shape != expected:
        raise ValueError(f"{extractor.name} trả về {block.shape}, hợp đồng yêu cầu {expected}")
    if not np.all(np.isfinite(block)):
        raise ValueError(f"{extractor.name} trả về giá trị không hữu hạn")
    return block.astype(np.float64, copy=False)
