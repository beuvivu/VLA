"""Các thuật toán phỏng đoán nâng cao, mỗi thuật toán là một plugin độc lập.

Nhóm kỹ thuật được cài đặt:

* **Chuỗi thời gian** — :class:`RecencyDecayStrategy` (trọng số suy giảm mũ),
  :class:`WeekdaySeasonalStrategy` (mùa vụ theo thứ trong tuần).
* **Nhận diện mẫu** — :class:`GapHazardStrategy` (khoảng gan / hazard),
  :class:`MarkovFollowStrategy` (chuyển tiếp có điều kiện từ ngày liền trước).
* **Tổ hợp có trọng số** — :class:`WeightedEnsembleStrategy` pha trộn các
  thành phần trên, mỗi thành phần được cân theo độ tin cậy riêng.

Mỗi lớp chỉ chịu trách nhiệm cho *một* tín hiệu (nguyên lý đơn trách nhiệm);
việc chuẩn hoá, co về đường cơ sở và lọc nhiễu do khung
:mod:`predictor_strategies` đảm nhiệm. Nhờ vậy thêm một thuật toán mới chỉ là
viết thêm một lớp rồi đăng ký, không phải sửa phần khung.

Độ tin cậy (``confidence``) của mỗi thuật toán tăng theo lượng bằng chứng và bị
chặn trần có chủ đích: với dữ liệu xổ số, một tín hiệu tự tin quá mức sẽ bị các
quy tắc chấm điểm chuẩn phạt nặng hơn là được thưởng.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from predictor_strategies import (
    NUMBER_SPACE,
    REGISTRY,
    PredictionContext,
    PredictorStrategy,
    predict,
)

_EPS = 1e-9


def _confidence_from_evidence(observations: int, saturation: float, ceiling: float) -> float:
    """Độ tin cậy bão hoà dần theo số quan sát.

    Dùng dạng ``n / (n + saturation)`` nên tăng nhanh lúc đầu rồi chững lại,
    và luôn bị chặn bởi ``ceiling`` để không thuật toán nào tự cho mình quyền
    phát biểu mạnh hơn mức dữ liệu cho phép.
    """
    if observations <= 0:
        return 0.0
    ratio = observations / (observations + saturation)
    return float(np.clip(ratio * ceiling, 0.0, 1.0))


# --------------------------------------------------------------------------
# Chuỗi thời gian
# --------------------------------------------------------------------------


@dataclass
class RecencyDecayStrategy:
    """Tần suất có trọng số suy giảm mũ theo thời gian.

    Ngày càng gần ngày neo càng nặng ký, theo hệ số nửa đời ``half_life_days``.
    Đây là dạng làm mượt hàm mũ kinh điển của phân tích chuỗi thời gian: nó ước
    lượng "mức độ hoạt động gần đây" của từng số thay vì tần suất phẳng.
    """

    half_life_days: int = 45
    window_days: int = 365
    name: str = "recency_decay"
    description: str = "Tần suất suy giảm mũ theo độ gần thời gian"

    def score(self, ctx: PredictionContext) -> np.ndarray:
        window = ctx.window(self.window_days)
        if window.size == 0:
            return np.full(NUMBER_SPACE, ctx.baseline)
        age = np.arange(window.shape[0] - 1, -1, -1, dtype=np.float64)
        weights = np.exp(-np.log(2.0) * age / max(1, self.half_life_days))
        weighted = (window * weights[:, None]).sum(axis=0)
        return weighted / max(weights.sum(), _EPS)

    def confidence(self, ctx: PredictionContext) -> float:
        return _confidence_from_evidence(ctx.history_length, saturation=180.0, ceiling=0.35)


@dataclass
class WeekdaySeasonalStrategy:
    """Mùa vụ theo thứ trong tuần.

    So sánh tần suất của từng số trong các ngày cùng thứ với tần suất chung. Nếu
    thực sự có hiệu ứng thứ trong tuần thì tín hiệu này bắt được; nếu không, tỷ
    lệ hai bên xấp xỉ 1 và thuật toán tự thoái lui về baseline.
    """

    window_days: int = 730
    min_samples: int = 12
    name: str = "weekday_seasonal"
    description: str = "Lệch tần suất theo thứ trong tuần so với nền chung"

    def score(self, ctx: PredictionContext) -> np.ndarray:
        weekday = ctx.target_date.weekday()
        rows = ctx.weekday_rows(weekday, self.window_days)
        overall = ctx.window(self.window_days)
        if rows.shape[0] < self.min_samples or overall.size == 0:
            return np.full(NUMBER_SPACE, ctx.baseline)
        # Làm mượt Laplace hai phía để một thứ hiếm gặp không tạo tỷ lệ cực đoan.
        same = (rows.sum(axis=0) + 1.0) / (rows.shape[0] + 2.0)
        general = (overall.sum(axis=0) + 1.0) / (overall.shape[0] + 2.0)
        ratio = same / np.clip(general, _EPS, None)
        return np.clip(ctx.baseline * ratio, 0.0, None)

    def confidence(self, ctx: PredictionContext) -> float:
        rows = ctx.weekday_rows(ctx.target_date.weekday(), self.window_days)
        if rows.shape[0] < self.min_samples:
            return 0.0
        return _confidence_from_evidence(rows.shape[0], saturation=60.0, ceiling=0.20)


# --------------------------------------------------------------------------
# Nhận diện mẫu
# --------------------------------------------------------------------------


@dataclass
class GapHazardStrategy:
    """Hazard theo khoảng gan: số lâu chưa về so với chu kỳ trung bình của nó.

    Với mỗi số, tính khoảng cách từ lần xuất hiện gần nhất tới ngày neo, rồi so
    với khoảng cách trung bình lịch sử. Tỷ lệ lớn hơn 1 nghĩa là số đang "gan"
    hơn thường lệ. Đây là mẫu hình được giới chơi quan tâm nhất, nên nó được đưa
    vào để *đo* chứ không phải để mặc định là đúng.
    """

    window_days: int = 365
    max_ratio: float = 3.0
    name: str = "gap_hazard"
    description: str = "Tỷ lệ khoảng gan hiện tại trên chu kỳ trung bình"

    def score(self, ctx: PredictionContext) -> np.ndarray:
        window = ctx.window(self.window_days)
        days = window.shape[0]
        if days == 0:
            return np.full(NUMBER_SPACE, ctx.baseline)

        scores = np.empty(NUMBER_SPACE, dtype=np.float64)
        for number in range(NUMBER_SPACE):
            appearances = np.flatnonzero(window[:, number])
            if appearances.size < 2:
                scores[number] = ctx.baseline
                continue
            current_gap = days - 1 - appearances[-1]
            mean_gap = float(np.diff(appearances).mean())
            ratio = (current_gap + 1.0) / max(mean_gap, 1.0)
            scores[number] = ctx.baseline * min(ratio, self.max_ratio)
        return scores

    def confidence(self, ctx: PredictionContext) -> float:
        return _confidence_from_evidence(ctx.history_length, saturation=240.0, ceiling=0.25)


@dataclass
class MarkovFollowStrategy:
    """Chuyển tiếp Markov bậc 1: số nào hay theo sau các số của ngày liền trước.

    Với mỗi số xuất hiện ở ngày neo, đếm xem ngày kế tiếp trong lịch sử thường
    có những số nào, rồi cộng dồn. Đây là nhận diện mẫu có điều kiện, chỉ dùng
    đúng cặp ngày liền kề trong cửa sổ.
    """

    window_days: int = 365
    name: str = "markov_follow"
    description: str = "Xác suất có điều kiện từ các số của ngày liền trước"

    def score(self, ctx: PredictionContext) -> np.ndarray:
        window = ctx.window(self.window_days)
        if window.shape[0] < 2:
            return np.full(NUMBER_SPACE, ctx.baseline)

        previous, following = window[:-1], window[1:]
        anchor_numbers = np.flatnonzero(ctx.last_row())
        if anchor_numbers.size == 0:
            return np.full(NUMBER_SPACE, ctx.baseline)

        totals = np.zeros(NUMBER_SPACE, dtype=np.float64)
        for number in anchor_numbers:
            mask = previous[:, number] > 0
            occurrences = int(mask.sum())
            if occurrences == 0:
                continue
            # Làm mượt Laplace: cặp hiếm không được tạo tín hiệu cực đoan.
            totals += (following[mask].sum(axis=0) + 1.0) / (occurrences + 2.0)
        if totals.sum() <= _EPS:
            return np.full(NUMBER_SPACE, ctx.baseline)
        return totals / anchor_numbers.size

    def confidence(self, ctx: PredictionContext) -> float:
        return _confidence_from_evidence(ctx.history_length, saturation=300.0, ceiling=0.20)


# --------------------------------------------------------------------------
# Tổ hợp có trọng số
# --------------------------------------------------------------------------


@dataclass
class WeightedEnsembleStrategy:
    """Pha trộn nhiều thuật toán, cân theo độ tin cậy từng thành phần.

    Trọng số cuối của mỗi thành phần là ``weight × confidence`` của chính nó, nên
    một thành phần đang thiếu dữ liệu sẽ tự động nhường chỗ cho các thành phần
    khác thay vì kéo cả tổ hợp đi lệch.
    """

    components: list[tuple[PredictorStrategy, float]] = field(default_factory=list)
    name: str = "weighted_ensemble"
    description: str = "Tổ hợp có trọng số của các tín hiệu thành phần"

    def score(self, ctx: PredictionContext) -> np.ndarray:
        total = np.zeros(NUMBER_SPACE, dtype=np.float64)
        weight_sum = 0.0
        for strategy, weight in self.components:
            effective = weight * strategy.confidence(ctx)
            if effective <= 0.0:
                continue
            total += effective * predict(strategy, ctx)
            weight_sum += effective
        if weight_sum <= _EPS:
            return np.full(NUMBER_SPACE, ctx.baseline)
        return total / weight_sum

    def confidence(self, ctx: PredictionContext) -> float:
        # Tổ hợp không được tự tin hơn thành phần tự tin nhất của nó.
        confidences = [s.confidence(ctx) for s, w in self.components if w > 0]
        return float(max(confidences)) if confidences else 0.0


def default_ensemble() -> WeightedEnsembleStrategy:
    """Tổ hợp mặc định gồm bốn tín hiệu, trọng số khởi tạo bằng nhau."""
    return WeightedEnsembleStrategy(
        components=[
            (RecencyDecayStrategy(), 1.0),
            (GapHazardStrategy(), 1.0),
            (MarkovFollowStrategy(), 1.0),
            (WeekdaySeasonalStrategy(), 1.0),
        ]
    )


def register_defaults(registry=REGISTRY) -> None:
    """Đăng ký bộ thuật toán mặc định; gọi lại nhiều lần vẫn an toàn."""
    for strategy in (
        RecencyDecayStrategy(),
        WeekdaySeasonalStrategy(),
        GapHazardStrategy(),
        MarkovFollowStrategy(),
        default_ensemble(),
    ):
        registry.replace(strategy)


register_defaults()
