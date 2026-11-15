"""Đặc trưng soi cầu kinh điển, số hóa thành ma trận cho mô hình học máy.

Một module từ 15-11-2026 (trước đó là gói con bảy tệp `base`, `registry`, `double_hit`, `geometric`,
`pattern_memory`, `special_set`). Mọi nơi đã nhập qua `soi_cau.features`, nên lệnh nhập không đổi.
"""

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


# --- Hợp đồng chung (trước 15-11-2026: features/base.py) ------------------------------------------
#
# Hợp đồng chung cho mọi extractor đặc trưng soi cầu.
#
# Ba điều khung bảo đảm, không phó mặc cho từng extractor:
#
# 1. **Không rò rỉ tương lai.** :class:`FeatureContext` chỉ phơi ra lịch sử tính
#    tới ``anchor_index``. Ngày mục tiêu không nằm trong tầm với, nên một extractor
#    không thể vô tình đọc kết quả mà nó đang dự đoán.
# 2. **Hình dạng thống nhất.** Mọi extractor trả về ma trận ``(100, k)``: một hàng
#    cho mỗi con số 00–99, cột là các đặc trưng. Nhờ vậy ghép chúng lại là phép
#    nối ngang, không cần lớp điều phối nào biết chi tiết từng phương pháp.
# 3. **Nhóm cột được giữ tên.** :class:`FeatureMatrix` nhớ cột nào thuộc extractor
#    nào, nên phần giải thích dự đoán quy được đóng góp về đúng phương pháp thay
#    vì về một chỉ số cột vô danh.
#
# Lưu ý về tính xác thực của phương pháp dân gian: các phương pháp soi cầu kinh
# điển không có định nghĩa chuẩn duy nhất. Mỗi extractor hiện thực MỘT cách hình
# thức hóa cụ thể và ghi rõ cách đó trong tài liệu lớp. Việc cách hình thức hóa ấy
# có mang tín hiệu hay không là câu hỏi để đo, không phải để giả định.

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
        """Ma trận trúng LOTO ``(ngày, 100)`` trong cửa sổ."""
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.tensor.loto_hits()[start:stop]

    def counts(self, days: int | None = None) -> np.ndarray:
        """Số nháy LOTO ``(ngày, 100)`` trong cửa sổ."""
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


# --- Sổ đăng ký (trước 15-11-2026: features/registry.py) ------------------------------------------
#
# Sổ đăng ký extractor: thêm, thay hoặc gỡ phương pháp mà không sửa khung.

class FeatureRegistry:
    """Tập extractor có thứ tự ổn định theo tên."""

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
        """Thay một extractor cùng tên; dùng khi nâng cấp phương pháp tại chỗ."""
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
        """Ghép mọi extractor đã đăng ký thành một ma trận ``(100, F)``."""
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


# --- Cầu hai nháy (trước 15-11-2026: features/double_hit.py) --------------------------------------
#
# Cầu hai nháy và tương quan xiên cặp.
#
# Hai đặc trưng độc lập nhau:
#
# * **Mật độ nổ kép** — tần suất một con về từ hai nháy trở lên trong cửa sổ gần
#   đây, so với tỉ lệ nền lý thuyết chứ không so với chính nó.
# * **Tương quan xiên cặp** — với mỗi con, mức độ nó hay về cùng ngày với những
#   con vừa về ở ngày neo. Dùng hệ số Pearson trên ma trận trúng 0/1.


#: P(một con cụ thể về từ hai nháy trở lên trong một kỳ) dưới giả thiết đều.
_TWO_NHAY_BASELINE: float = float(
    1.0
    - (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY
    - LOTO_DRAWS_PER_DAY
    * UNIFORM_TWO_DIGIT_RATE
    * (1.0 - UNIFORM_TWO_DIGIT_RATE) ** (LOTO_DRAWS_PER_DAY - 1)
)


@dataclass
class DoubleHitBridgeExtractor:
    """Mật độ nổ kép và tương quan cùng về giữa các con."""

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
            # So với tỉ lệ nền lý thuyết: "hay nổ kép" chỉ có nghĩa khi đối chiếu
            # với mức mà một con bất kỳ nổ kép do ngẫu nhiên.
            out[:, 1] = double_rate - _TWO_NHAY_BASELINE

        hits = ctx.hits(self.correlation_days).astype(np.float64)
        today = ctx.hits(1)[0] if ctx.history_length else np.zeros(NUMBER_SPACE, bool)
        if hits.shape[0] >= 2 and today.any():
            out[:, 2], out[:, 3] = self._partner_signals(hits, today)
        return out

    @staticmethod
    def _partner_signals(hits: np.ndarray, today: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Tương quan trung bình và tỉ lệ cùng về với các con vừa ra hôm nay."""
        centred = hits - hits.mean(axis=0, keepdims=True)
        norms = np.sqrt((centred**2).sum(axis=0))
        # Con không bao giờ về (hoặc về mọi ngày) có phương sai 0; đặt chuẩn hóa
        # bằng 1 để phép chia trả 0 thay vì vô cực.
        safe = np.where(norms > _EPS, norms, 1.0)
        correlation = (centred.T @ centred) / np.outer(safe, safe)
        np.fill_diagonal(correlation, 0.0)

        partners = np.flatnonzero(today)
        mean_correlation = correlation[:, partners].mean(axis=1)

        cohit = hits.T @ hits[:, partners]
        appearances = np.maximum(hits.sum(axis=0), 1.0)[:, None]
        mean_cohit = (cohit / appearances).mean(axis=1)
        return mean_correlation, mean_cohit


# --- Cầu hình học (trước 15-11-2026: features/geometric.py) ---------------------------------------
#
# Cầu hình học và tọa độ: Pascal, hình trám, kẹp nách.
#
# Ba phương pháp này lưu truyền dưới nhiều biến thể khác nhau. Lớp dưới đây hiện
# thực một cách hình thức hóa cụ thể cho mỗi phương pháp và ghi rõ ngay tại chỗ,
# để kết quả đo sau này gắn được với đúng định nghĩa đã dùng — chứ không phải với
# một cái tên mơ hồ.

# Vị trí bắt đầu của mỗi trường giải trong luồng chữ số phẳng.
_OFFSETS: dict[str, int] = {}
_cursor = 0
for _field, _width in FIELD_WIDTHS:
    _OFFSETS[_field] = _cursor
    _cursor += _width


def pascal_reduce(digits: np.ndarray) -> int:
    """Rút gọn một dãy chữ số theo tam giác Pascal xuống còn hai chữ số.

    Mỗi bước thay dãy bằng tổng từng cặp kề nhau lấy theo modulo 10, lặp tới khi
    còn đúng hai chữ số; kết quả đọc là số hai chữ số.
    """
    row = np.asarray(digits, dtype=np.int16)
    if row.size < 2:
        raise ValueError("cầu Pascal cần ít nhất hai chữ số")
    while row.size > 2:
        row = (row[:-1] + row[1:]) % 10
    return int(10 * row[0] + row[1])


@dataclass
class GeometricBridgeExtractor:
    """Cầu hình học trên bảng kết quả của ngày neo.

    * **Pascal**: ghép chữ số giải Đặc Biệt với giải Nhất thành một dãy 10 chữ
      số rồi rút gọn theo tam giác Pascal.
    * **Hình trám**: quét ba giải liên tiếp tại cùng cột chữ số; nơi hai chữ số
      ngoài trùng nhau (dạng A-B-A), số dự đoán là ``BA``.
    * **Kẹp nách**: trong dãy chữ số của một giải, nơi hai chữ số hai bên trùng
      nhau, số dự đoán ghép từ chữ số bị kẹp và chữ số kẹp.

    Mỗi đặc trưng là chỉ báo 0/1 trên 100 con, cộng thêm một cột đếm chuẩn hóa
    cho biết phương pháp đó chỉ ra con này bao nhiêu lần trong ngày.
    """

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
        """Ba giải liên tiếp cùng cột, dạng A-B-A, cho số ``BA``."""
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
        """Chữ số bị kẹp giữa hai chữ số trùng nhau trong cùng một giải."""
        found: list[int] = []
        for name, width in FIELD_WIDTHS:
            if width < 3:
                continue
            row = digits[_OFFSETS[name] : _OFFSETS[name] + width]
            for index in range(1, width - 1):
                if row[index - 1] == row[index + 1] and row[index] != row[index - 1]:
                    found.append(int(10 * row[index] + row[index - 1]))
        return found


# --- Trí nhớ mẫu hình (trước 15-11-2026: features/pattern_memory.py) ------------------------------
#
# Bạc nhớ ma trận và nhịp gan.
#
# * **Bạc nhớ** — bảng xác suất điều kiện P(con Y về ngày T | con X về ngày T−1)
#   cho toàn bộ 100×100 cặp, làm trơn Laplace. Với mỗi con, đặc trưng là mức bạc
#   nhớ trung bình từ những con vừa về ở ngày neo.
# * **Nhịp gan** — Z-score của khoảng cách hiện tại so với phân bố khoảng cách của
#   chính con đó. Đây là thước "sắp gãy gan", và cũng chính là đại lượng mà bộ lọc
#   rủi ro ở giai đoạn sau dùng để chặn bẫy lô gan.
#
# Cả hai đều so với đường cơ sở chứ không đọc giá trị tuyệt đối: một xác suất điều
# kiện 0,24 nghe như tín hiệu cho tới khi biết tỉ lệ nền cũng là 0,2374.

_LAPLACE = 1.0


@dataclass
class PatternMemoryExtractor:
    """Bảng bạc nhớ có làm trơn, và Z-score nhịp gan."""

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
        """P(Y hôm nay | X hôm qua), làm trơn Laplace, lấy trung bình theo X."""
        previous = hits[:-1].astype(np.float64)
        following = hits[1:].astype(np.float64)
        joint = previous.T @ following
        occurrences = previous.sum(axis=0)[:, None]
        # Laplace: con X chỉ mới về vài lần không được phép phát ra xác suất 0
        # hay 1 chỉ vì mẫu quá mỏng.
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
        """Khoảng cách hiện tại, Z-score của nó, và tỉ lệ so với khoảng cách trung bình."""
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


# --- Bộ số Đặc Biệt (trước 15-11-2026: features/special_set.py) -----------------------------------
#
# Cầu Đặc Biệt: bộ số, chạm, tổng, đầu/đuôi, bóng — và dàn đề tinh gọn.
#
# Phân tích giải Đặc Biệt theo các trục mà giới soi cầu dùng, rồi quy mỗi trục về
# một đặc trưng trên 100 con: con này có cùng chạm/tổng/bộ với các giải Đặc Biệt gần đây
# đến mức nào, so với mức mà một con bất kỳ đạt được do ngẫu nhiên.
#
# ``build_dan`` xuất dàn đề tinh gọn từ phong độ tuần của các trục chạm và tổng.
# Dàn là danh sách con, không phải lời khuyên đặt cược: nó chỉ nói "các trục đang
# mạnh nhất trong cửa sổ gần đây chỉ tới nhóm con này".


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
#: ``_BO_ID[n]`` là mã bộ số của ``n``; hai con cùng bộ có cùng mã.
_BO_ID: Final[np.ndarray] = np.array(
    [min(int(item) for item in bo(n)) for n in range(NUMBER_SPACE)], dtype=np.int16
)

DAN_SIZES: Final[tuple[int, ...]] = (36, 64)


def touches(number: int) -> tuple[int, int]:
    """Hai chạm của một con: chữ số đầu và chữ số đuôi."""
    text = normalize_two_digit(number)
    return int(text[0]), int(text[1])


@dataclass
class SpecialSetExtractor:
    """Phong độ của các trục Đặc Biệt, quy về đặc trưng trên từng con."""

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
        # Mỗi trục: tỉ lệ ngày gần đây mà giải Đặc Biệt chia sẻ đặc điểm đó với con này.
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
        """Tỉ lệ ngày mà con này dùng chung ít nhất một chạm với giải Đặc Biệt."""
        recent_keys = key(recent)
        number_keys = key(numbers)
        shared = (number_keys[:, None, :, None] == recent_keys[None, :, None, :]).any(axis=(2, 3))
        return shared.mean(axis=1)

    @staticmethod
    def _shadow_rate(recent: np.ndarray, numbers: np.ndarray) -> np.ndarray:
        """Tỉ lệ ngày mà con này là bóng âm hoặc bóng dương của giải Đặc Biệt."""
        duong = _BONG_DUONG[recent]
        am = _BONG_AM[recent]
        match = (numbers[:, None] == duong[None, :]) | (numbers[:, None] == am[None, :])
        return match.mean(axis=1)

    def build_dan(self, ctx: FeatureContext, size: int = 36) -> list[str]:
        """Dàn đề tinh gọn ``size`` con, chọn theo các trục mạnh nhất trong cửa sổ.

        Không phải lời khuyên đặt cược. Đây là câu "các trục chạm/tổng đang mạnh
        nhất trong cửa sổ gần đây chỉ tới nhóm con này", và câu đó chỉ có giá trị
        nếu chính các trục ấy đo được là hơn ngẫu nhiên — điều mà lớp đo ở giai
        đoạn sau trả lời, không phải hàm này.
        """
        if size <= 0 or size > NUMBER_SPACE:
            raise ValueError(f"kích thước dàn phải trong 1..{NUMBER_SPACE}")
        block = self.extract(ctx)
        # Chạm và tổng là hai trục mà phương pháp dàn đề truyền thống dùng.
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
    """Sổ đăng ký với đủ bốn extractor trong đặc tả."""
    registry = FeatureRegistry()
    registry.register(GeometricBridgeExtractor())
    registry.register(DoubleHitBridgeExtractor())
    registry.register(PatternMemoryExtractor())
    registry.register(SpecialSetExtractor())
    return registry
