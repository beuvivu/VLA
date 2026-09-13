"""Hợp nhất ý kiến: trộn số học, trộn log-odds, và chọn giữa chúng bằng số đo.

Vấn đề đo được với cách trộn hiện tại
=====================================
Toàn hệ thống hợp tín hiệu bằng TRỘN SỐ HỌC trong không gian xác suất, ở bốn
tầng lồng nhau. Phép trộn ấy có một tính chất cấu trúc không thể lách:

    Σ wᵢ pᵢ  luôn nằm trong  [min pᵢ, max pᵢ]

Nó không bao giờ tạo ra giá trị SẮC hơn thành phần sắc nhất. Với sáu thành phần
gần trực giao, nó hội tụ về trung bình. Đo trên đầu ra thật của kho: thành phần
``dyn.regime_prob`` có dải 73,0 % của tần suất nền, nhưng đầu ra ``stat`` chỉ
còn 23,0 %. Kiến trúc hiện tại **về cấu trúc không thể phát ra dự báo sắc**, kể
cả khi một thành phần tìm được thứ gì thật.

Hai phép hợp, và chúng trả lời hai câu hỏi khác nhau
===================================================
* **Trộn số học** (linear opinion pool) đúng khi các thành phần là những GIẢ
  THUYẾT THAY THẾ NHAU — "mô hình nào đúng?". Kết quả là hỗn hợp, và nó làm
  giảm phương sai.
* **Trộn log-odds** (logarithmic opinion pool) đúng khi các thành phần là những
  BẰNG CHỨNG ĐỘC LẬP về cùng một đại lượng — đó là phép cập nhật Bayes. Nó SẮC
  LÊN được khi các nguồn đồng thuận.

Ở đây không phép nào đúng hoàn toàn: các thành phần cùng ước lượng một đại
lượng nhưng từ dữ liệu CHỒNG LẤN (đo được: stat ↔ dynamics = 0,681, vì dynamics
được nhúng sẵn vào stat ở trọng số cứng 0,30). Trộn log-odds thuần sẽ đếm trùng
bằng chứng chung và sinh ra tự tin thái quá.

Vì thế dạng tổng quát dưới đây có một tham số ĐỘ SẮC ``s`` học từ dữ liệu:

    logit(p) = logit(p₀) + s · Σ wᵢ · [logit(pᵢ) − logit(p₀)]

* ``s = 0`` → trả về đúng tần suất nền, bỏ hết tín hiệu;
* ``s = 1`` → trộn log-odds thuần;
* ``s < 1`` → co lại, đúng cách xử lý khi các nguồn chồng lấn;
* ``s > 1`` → sắc lên, hợp lệ khi các nguồn thật sự độc lập.

Dữ liệu chọn ``s``, không phải niềm tin. Và trộn số học vẫn là một ứng viên
ngang hàng: nếu nó thắng trên lát giữ riêng thì nó được dùng.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np

from ensemble_utils import clip01, logit, normalize_distribution, sigmoid

Mode = Literal["loto", "de"]
PoolKind = Literal["linear", "log"]

_EPS: Final[float] = 1e-6
#: Dưới ngưỡng này, cắt thêm lát giữ riêng sẽ làm hỏng chính phép khớp.
MIN_SELECTION_DAYS: Final[int] = 60
DEFAULT_HOLDOUT: Final[float] = 0.30
#: Số sai số chuẩn mà một ứng viên phải VƯỢT QUA để soán ngôi bản đương nhiệm.
#:
#: 1 SE (~68 % tin cậy) là quá lỏng cho một thay đổi kiến trúc. Đo thật trên
#: dữ liệu của kho, 90 kỳ giữ riêng, thống kê t cặp đôi so với trộn số học:
#:
#:     s=0    t = -1,13      s=0,7  t = -1,24      s=1,5  t = +1,32
#:     s=0,3  t = -1,17      s=1    t = -1,37      s=2    t = +1,40
#:     s=0,5  t = -1,20
#:
#: Không ứng viên nào đạt |t| >= 2. Ở ngưỡng 1 SE, bộ chọn đã chọn ``s = 0`` —
#: tức VỨT SẠCH tín hiệu và trả về đúng tần suất nền — trên một chênh lệch
#: Brier 7e-6. Một thay đổi kiến trúc phải TỰ CHỨNG MINH, không được thắng nhờ
#: nhiễu.
SIGNIFICANCE_SIGMAS = 2.0

#: Dải tìm độ sắc. Trên 3 là tự tin tới mức mọi thành phần phải độc lập hoàn
#: toàn mới biện minh được, và dữ liệu ở đây chưa bao giờ nói vậy.
SHARPNESS_GRID: Final[tuple[float, ...]] = (
    0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 3.0,
)


@dataclass(frozen=True)
class PoolParams:
    """Phép hợp đã chọn, kèm mọi thứ cần để áp dụng lại y hệt."""

    kind: PoolKind
    weights: tuple[float, ...]
    baseline: float
    sharpness: float = 1.0

    def __post_init__(self) -> None:
        w = np.asarray(self.weights, dtype=float)
        if w.size == 0:
            raise ValueError("phải có ít nhất một thành phần")
        if not np.isfinite(w).all() or np.any(w < 0.0):
            raise ValueError("trọng số phải hữu hạn và không âm")
        if float(w.sum()) <= 0.0:
            raise ValueError("tổng trọng số phải dương")
        if not 0.0 < self.baseline < 1.0:
            raise ValueError("tần suất nền phải nằm trong (0, 1)")
        if not np.isfinite(self.sharpness) or self.sharpness < 0.0:
            raise ValueError("độ sắc phải hữu hạn và không âm")

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "weights": [float(v) for v in self.weights],
            "baseline": float(self.baseline),
            "sharpness": float(self.sharpness),
        }


def apply_pool(mode: Mode, components: np.ndarray, params: PoolParams) -> np.ndarray:
    """Hợp một ma trận ``(số thành phần, 100)`` thành một vectơ 100 chiều."""
    matrix = np.asarray(components, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("components phải có dạng (số thành phần, số con)")
    if matrix.shape[0] != len(params.weights):
        raise ValueError("số thành phần không khớp số trọng số")
    if not np.isfinite(matrix).all():
        raise ValueError("xác suất thành phần phải hữu hạn")

    w = np.asarray(params.weights, dtype=float)
    w = w / w.sum()

    if params.kind == "linear":
        pooled = np.tensordot(w, clip01(matrix, eps=_EPS), axes=(0, 0))
    else:
        # Trộn trong không gian log-odds, đo LỆCH so với nền chứ không đo tuyệt
        # đối: nhờ vậy ``s = 0`` cho đúng tần suất nền thay vì cho 0,5, và mọi
        # giá trị của ``s`` đều giữ nền làm điểm neo.
        base_logit = logit(np.full(matrix.shape[1], params.baseline))
        deviation = logit(clip01(matrix, eps=_EPS)) - base_logit[None, :]
        pooled = sigmoid(base_logit + params.sharpness * np.tensordot(w, deviation, axes=(0, 0)))

    pooled = clip01(pooled, eps=_EPS)
    return normalize_distribution(pooled) if mode == "de" else pooled


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


@dataclass(frozen=True)
class PoolAudit:
    """Vì sao phép hợp này được chọn, và các ứng viên khác đạt bao nhiêu."""

    chosen: PoolKind
    sharpness: float
    brier_by_candidate: dict[str, float]
    fit_days: int
    holdout_days: int
    selected: bool

    def describe(self) -> str:
        if not self.selected:
            return (
                f"Không chọn được ({self.fit_days + self.holdout_days} kỳ, dưới ngưỡng "
                f"{MIN_SELECTION_DAYS}); giữ trộn số học."
            )
        ranked = sorted(self.brier_by_candidate.items(), key=lambda kv: kv[1])
        detail = ", ".join(f"{name} {score:.6f}" for name, score in ranked[:4])
        return (
            f"Chọn '{self.chosen}' (độ sắc {self.sharpness:g}) theo Brier trên "
            f"{self.holdout_days} kỳ giữ riêng ({detail})."
        )


def fit_pool(
    mode: Mode,
    components_by_day: np.ndarray,
    y_by_day: np.ndarray,
    weights: np.ndarray,
    *,
    holdout_fraction: float = DEFAULT_HOLDOUT,
) -> tuple[PoolParams, PoolAudit]:
    """Chọn phép hợp và độ sắc bằng Brier trên lát giữ riêng cắt theo thời gian.

    ``components_by_day`` có dạng ``(số kỳ, số thành phần, 100)``.

    Trọng số ``weights`` được coi là ĐÃ CHO — tệp này chỉ quyết định *cách hợp*,
    không quyết định *hợp cái gì*. Tách hai câu hỏi ra là cố ý: gộp chúng vào
    một phép tối ưu sẽ cho một mặt mục tiêu mà không ai đọc được kết quả.
    """
    cube = np.asarray(components_by_day, dtype=float)
    labels = np.asarray(y_by_day, dtype=float)
    if cube.ndim != 3:
        raise ValueError("components_by_day phải có dạng (kỳ, thành phần, số con)")
    if labels.shape != (cube.shape[0], cube.shape[2]):
        raise ValueError("y_by_day phải có dạng (kỳ, số con)")
    if not 0.05 <= holdout_fraction <= 0.6:
        raise ValueError("holdout_fraction phải nằm trong [0.05, 0.6]")

    days = cube.shape[0]
    split = int(round(days * (1.0 - holdout_fraction)))
    w = tuple(float(v) for v in np.asarray(weights, dtype=float))

    if days < MIN_SELECTION_DAYS or split <= 0 or days - split <= 0:
        baseline = float(np.clip(labels.mean(), _EPS, 1 - _EPS)) if labels.size else 0.5
        return (
            PoolParams(kind="linear", weights=w, baseline=baseline),
            PoolAudit("linear", 1.0, {}, days, 0, selected=False),
        )

    # Tần suất nền học trên lát KHỚP, không trên lát kiểm — nền là một tham số
    # như mọi tham số khác, và học nó trên lát kiểm là rò rỉ.
    baseline = float(np.clip(labels[:split].mean(), _EPS, 1 - _EPS))

    candidates: dict[str, PoolParams] = {
        "linear": PoolParams(kind="linear", weights=w, baseline=baseline),
    }
    for sharpness in SHARPNESS_GRID:
        candidates[f"log(s={sharpness:g})"] = PoolParams(
            kind="log", weights=w, baseline=baseline, sharpness=sharpness
        )

    # Giữ sai số TỪNG KỲ, không chỉ trung bình: phép so cặp đôi bên dưới cần
    # chúng, và không có nó thì bộ chọn quyết định theo chữ số thập phân cuối.
    per_day: dict[str, np.ndarray] = {}
    for name, params in candidates.items():
        pooled = np.vstack([apply_pool(mode, day, params) for day in cube[split:]])
        per_day[name] = np.mean((pooled - labels[split:]) ** 2, axis=1)
    scores = {name: float(errors.mean()) for name, errors in per_day.items()}

    # So CẶP ĐÔI có sai số chuẩn — cùng lý do và cùng cách làm với bộ chọn chu
    # kỳ bán rã. Đây không phải chi tiết trang trí: đo thật trên dữ liệu của
    # kho, bộ chọn không có phép so này đã chọn ``log s=0`` — tức VỨT SẠCH tín
    # hiệu và trả về đúng tần suất nền — dựa trên chênh lệch Brier 1e-6.
    #
    # Chênh lệch không đo được thì giữ hành vi hiện tại. Đó là lựa chọn có chủ
    # ý: một thay đổi kiến trúc phải TỰ CHỨNG MINH, không được thắng nhờ nhiễu.
    names = list(candidates)
    best_name = min(names, key=lambda n: (scores[n], names.index(n)))
    best_errors = per_day[best_name]
    n_days = max(best_errors.size, 1)

    tied = []
    for name in names:
        delta = per_day[name] - best_errors
        standard_error = (
            float(np.std(delta, ddof=1) / np.sqrt(n_days)) if n_days > 1 else 0.0
        )
        if float(delta.mean()) <= SIGNIFICANCE_SIGMAS * standard_error + 1e-12:
            tied.append(name)
    # Thứ tự chèn đặt "linear" đầu tiên, nên khi hoà nó thắng.
    chosen = candidates[tied[0]]
    return chosen, PoolAudit(
        chosen=chosen.kind,
        sharpness=chosen.sharpness,
        brier_by_candidate=scores,
        fit_days=split,
        holdout_days=days - split,
        selected=True,
    )
