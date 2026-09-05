"""Kiến trúc plugin cho các thuật toán phỏng đoán hai chữ số.

Mỗi thuật toán là một *strategy* độc lập, đăng ký vào registry và nhận cùng một
:class:`PredictionContext`. Nhờ vậy có thể thêm, thay hoặc gỡ thuật toán mà
không sửa phần khung, và mọi thuật toán đều được chấm điểm bằng cùng một thước.

Ba nguyên tắc bắt buộc, được khung bảo đảm chứ không phó mặc cho từng thuật
toán:

1. **Không rò rỉ tương lai.** Context chỉ phơi ra lịch sử tính tới ``anchor``;
   chỉ số ngày mục tiêu không nằm trong tầm với của strategy.
2. **Đường cơ sở là công dân hạng nhất.** :class:`BaselineStrategy` luôn có mặt
   để mọi thuật toán khác phải chứng minh mình hơn được nó.
3. **Co về đường cơ sở.** Điểm thô của strategy được khung co về tần suất nền
   theo hệ số tin cậy — đây chính là lớp lọc nhiễu: bằng chứng càng mỏng thì
   dự đoán càng gần baseline.

Với xổ số công bằng, kỳ vọng đúng là không thuật toán nào thắng được baseline
một cách bền vững. Registry này tồn tại để *đo* điều đó một cách trung thực,
không phải để giả định điều ngược lại.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Protocol, runtime_checkable

import numpy as np

from xsmb_domain import baseline_rate

NUMBER_SPACE: Final[int] = 100
_EPS: Final[float] = 1e-9

# Phần nền đều luôn được giữ lại trong phân phối ĐB, nên xác suất nhỏ nhất không
# bao giờ xuống 0 (sàn = _MIN_UNIFORM_SHARE / 100).
_MIN_UNIFORM_SHARE: Final[float] = 1e-4

Mode = str  # "loto" | "de"


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PredictionContext:
    """Lát cắt lịch sử mà một strategy được phép đọc.

    ``hits`` là ma trận ``(số ngày, 100)`` giá trị 0/1: ``hits[i, n]`` bằng 1 khi
    số ``n`` xuất hiện ở ngày ``dates[i]``. ``anchor_index`` là ngày cuối cùng
    được phép dùng; mọi hàm trợ giúp bên dưới đều cắt tại đó nên strategy không
    thể vô tình đọc ngày mục tiêu.
    """

    mode: Mode
    dates: Sequence[date]
    hits: np.ndarray
    anchor_index: int
    target_date: date

    def __post_init__(self) -> None:
        if self.hits.ndim != 2 or self.hits.shape[1] != NUMBER_SPACE:
            raise ValueError(f"hits phải có dạng (n, {NUMBER_SPACE})")
        if not 0 <= self.anchor_index < len(self.dates):
            raise ValueError("anchor_index nằm ngoài phạm vi lịch sử")
        if len(self.dates) != self.hits.shape[0]:
            raise ValueError("dates và hits phải cùng độ dài")

    @property
    def baseline(self) -> float:
        """Tần suất nền không thông tin của chế độ hiện tại."""
        return baseline_rate(self.mode)

    @property
    def history_length(self) -> int:
        """Số ngày quan sát được, tính cả ngày neo."""
        return self.anchor_index + 1

    def window(self, days: int | None = None) -> np.ndarray:
        """Ma trận 0/1 của ``days`` ngày gần nhất tính tới ngày neo."""
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        return self.hits[start:stop]

    def last_row(self) -> np.ndarray:
        """Vector 0/1 của đúng ngày neo."""
        return self.hits[self.anchor_index]

    def weekday_rows(self, weekday: int, days: int | None = None) -> np.ndarray:
        """Các ngày trong cửa sổ trùng thứ ``weekday`` (0 = thứ Hai)."""
        stop = self.anchor_index + 1
        start = 0 if days is None else max(0, stop - days)
        mask = [d.weekday() == weekday for d in self.dates[start:stop]]
        if not any(mask):
            return np.empty((0, NUMBER_SPACE), dtype=self.hits.dtype)
        return self.hits[start:stop][np.asarray(mask)]


# --------------------------------------------------------------------------
# Protocol + registry
# --------------------------------------------------------------------------


@runtime_checkable
class PredictorStrategy(Protocol):
    """Hợp đồng tối thiểu của một thuật toán phỏng đoán."""

    name: str
    description: str

    def score(self, ctx: PredictionContext) -> np.ndarray:
        """Trả về điểm thô không âm cho 100 số.

        Khung sẽ chuẩn hoá và co về baseline, nên strategy chỉ cần diễn đạt
        "số nào đáng chú ý hơn số nào".
        """
        ...

    def confidence(self, ctx: PredictionContext) -> float:
        """Mức tin cậy trong ``[0, 1]`` dùng làm hệ số co về baseline.

        0 nghĩa là trả thẳng baseline; 1 nghĩa là tin hoàn toàn vào điểm thô.
        """
        ...


class StrategyRegistry:
    """Sổ đăng ký strategy, cho phép thêm/thay thuật toán mà không sửa khung."""

    def __init__(self) -> None:
        self._items: dict[str, PredictorStrategy] = {}

    def register(self, strategy: PredictorStrategy) -> PredictorStrategy:
        if not strategy.name:
            raise ValueError("strategy phải có tên")
        if strategy.name in self._items:
            raise ValueError(f"strategy trùng tên: {strategy.name}")
        self._items[strategy.name] = strategy
        return strategy

    def replace(self, strategy: PredictorStrategy) -> PredictorStrategy:
        """Thay một strategy cùng tên; dùng khi nâng cấp thuật toán tại chỗ."""
        self._items[strategy.name] = strategy
        return strategy

    def unregister(self, name: str) -> None:
        self._items.pop(name, None)

    def get(self, name: str) -> PredictorStrategy:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(
                f"chưa đăng ký strategy {name!r}; hiện có: {sorted(self._items)}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._items)

    def all(self) -> list[PredictorStrategy]:
        return [self._items[n] for n in self.names()]

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, name: object) -> bool:
        return name in self._items


REGISTRY: Final[StrategyRegistry] = StrategyRegistry()


# --------------------------------------------------------------------------
# Chuẩn hoá + co về baseline (lớp lọc nhiễu dùng chung)
# --------------------------------------------------------------------------


def finalize(scores: np.ndarray, ctx: PredictionContext, confidence: float) -> np.ndarray:
    """Biến điểm thô thành xác suất hợp lệ đã co về baseline.

    ``confidence`` càng thấp thì kết quả càng gần tần suất nền. Đây là cơ chế
    lọc nhiễu trung tâm: một thuật toán dựa trên vài quan sát sẽ tự động bị kéo
    về baseline thay vì phát ra khẳng định mạnh từ dữ liệu mỏng.
    """
    if scores.shape != (NUMBER_SPACE,):
        raise ValueError(f"điểm phải là vector {NUMBER_SPACE} phần tử")
    if not np.all(np.isfinite(scores)):
        raise ValueError("điểm chứa giá trị không hữu hạn")

    weight = float(np.clip(confidence, 0.0, 1.0))
    base = ctx.baseline
    raw = np.clip(scores.astype(np.float64), 0.0, None)

    if ctx.mode == "de":
        # ĐB là phân phối phân loại: đúng một số trúng nên tổng phải bằng 1.
        total = raw.sum()
        shaped = raw / total if total > _EPS else np.full(NUMBER_SPACE, 1.0 / NUMBER_SPACE)
        # Luôn giữ lại một phần nền đều: không thuật toán nào được phép tuyên bố
        # một số là *bất khả thi*. Xác suất 0 mà số đó lại trúng sẽ cho log-loss
        # bùng nổ — đúng lớp lỗi mà đợt kiểm định trước đã phải xử lý.
        effective = min(weight, 1.0 - _MIN_UNIFORM_SHARE)
        blended = effective * shaped + (1.0 - effective) * (1.0 / NUMBER_SPACE)
        return blended / blended.sum()

    # Lô tô là đa nhãn: mỗi số có xác suất riêng, không ràng buộc tổng.
    # Chuẩn hoá quanh trung bình để điểm thô giữ đúng mức nền trung bình.
    mean = raw.mean()
    shaped = raw * (base / mean) if mean > _EPS else np.full(NUMBER_SPACE, base)
    blended = weight * shaped + (1.0 - weight) * base
    return np.clip(blended, _EPS, 1.0 - _EPS)


def predict(strategy: PredictorStrategy, ctx: PredictionContext) -> np.ndarray:
    """Chạy một strategy qua đủ chuẩn hoá và co baseline."""
    return finalize(strategy.score(ctx), ctx, strategy.confidence(ctx))


# --------------------------------------------------------------------------
# Strategy nền
# --------------------------------------------------------------------------


@dataclass
class BaselineStrategy:
    """Hằng số tần suất nền — thước đo mọi thuật toán khác phải vượt qua."""

    name: str = "baseline"
    description: str = "Hằng số tần suất nền, không dùng thông tin lịch sử"

    def score(self, ctx: PredictionContext) -> np.ndarray:
        return np.full(NUMBER_SPACE, ctx.baseline, dtype=np.float64)

    def confidence(self, ctx: PredictionContext) -> float:
        return 0.0  # luôn trả đúng baseline


REGISTRY.register(BaselineStrategy())
