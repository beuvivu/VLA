"""Trộn các cánh tay bằng trọng số mũ trên log-loss, có chia sẻ cố định.

Vì sao thay bandit Thompson
----------------------------

Bản trước (gỡ ngày 20-10-2026) dùng Thompson Sampling có chiết khấu với phần
thưởng ``1 − Brier``. Hai chỗ hỏng không sửa được trong khuôn ấy:

* Chiết khấu γ = 0,98 chặn số quan sát hiệu dụng ở 50, nên độ lệch chuẩn hậu
  nghiệm không xuống dưới khoảng 0,05 — trong khi chênh Brier thật giữa các cánh
  tay cỡ 10⁻⁵–10⁻⁴. Trọng số là nhiễu của bộ sinh ngẫu nhiên.
* Beta với phần thưởng liên tục không phải hậu nghiệm của thứ gì cả: khoảng
  Beta không phải khoảng tin cậy, và Brier không phân biệt mạnh các xác suất
  sai mức ở đuôi như log-loss.

Phép trộn ở đây
---------------

Mỗi cánh tay ``i`` giữ một trọng số; sau khi biết kết quả kỳ ``t``::

    w_i ← w_i · exp(−η · L_i,t)          L = log-loss CỘNG trên 100 con của kỳ
    w   ← (1 − α) · w / Σw + α / K       chia sẻ cố định (Herbster–Warmuth)

Với ``η = 1``, ``L`` là âm log-hợp lý của kỳ dưới luật của cánh tay (100 con
Bernoulli độc lập theo biên nó khai báo), nên ``w`` là hậu nghiệm Bayes của các
cánh tay, và chia sẻ cố định là Bayes với tiên nghiệm "đổi cánh tay đúng nhất với
xác suất α mỗi kỳ". Hỗn hợp đầy đủ thua cánh tay tốt nhất (cố định) không quá
``ln(K/α) + (T − 1)·ln(1/(1 − α))`` nat trên ``T`` kỳ. Dự báo công bố là BIÊN của
hỗn hợp ấy, ``Σ_i w_i p_ij``; biên trộn không thừa hưởng đúng chặn đó, nên phép kiểm
đo hối tiếc của chính nó.

Tham số chốt trước khi đo, không dò trên dữ liệu (20-10-2026):

* ``η = 1`` trên loss cộng 100 con — Bayes, không ủ. Đặt ``η = 1`` trên log-loss
  TRUNG BÌNH mỗi con là ủ hợp lý đi 100 lần: chênh 10⁻³ nat/con mỗi kỳ, đủ phân
  biệt sau vài trăm kỳ, chỉ dời trọng số ``e⁻⁰·¹`` sau 100 kỳ.
* ``α = 0,001`` — kỳ vọng một lần đổi cánh tay dẫn đầu mỗi 1 000 kỳ. Trọng số cân
  bằng của một cánh tay kém hơn đều đặn ``Δ`` nat mỗi kỳ là khoảng
  ``(α/K)/(α + ηΔ)``; ``α = 0,01`` giữ ~15% trọng số cho MỖI cánh tay kém 0,1 nat
  (10⁻³ nat/con) trong sáu cánh tay.

Không có bộ sinh ngẫu nhiên: cùng lịch sử loss cho cùng trọng số, nên dự báo
lặp lại hay khôi phục sau lỗi không cần lưu trạng thái RNG.

Trọng số giữ trong MIỀN LOG. Loss cộng 100 con có thể chênh hàng nghìn nat sau một
dự báo cực đoan (xác suất kẹp ở 10⁻⁶); trong miền xác suất, ``e⁻⁷⁴⁵`` tràn dưới về
0, và với ``α = 0`` một lần loss đảo chiều sau đó cho 0/0 = NaN ở mọi trọng số.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

import numpy as np

#: Tốc độ học mặc định trên log-loss cộng 100 con của kỳ (Bayes, không ủ).
DEFAULT_LEARNING_RATE: Final[float] = 1.0

#: Tỉ lệ chia sẻ cố định mặc định.
DEFAULT_SHARE: Final[float] = 0.001


class AggregationError(ValueError):
    """Tham số hoặc loss không hợp lệ cho phép trộn."""


class ExponentialWeights:
    """Trọng số mũ có chia sẻ cố định trên các cánh tay.

    Ví dụ:
        >>> mixer = ExponentialWeights(["nen", "mo_hinh"])
        >>> mixer.update({"nen": 54.9, "mo_hinh": 56.2})
        >>> mixer.weights()["nen"] > mixer.weights()["mo_hinh"]
        True

    Attributes:
        arm_names: Tên các cánh tay, theo thứ tự cố định.
        learning_rate: ``η``.
        share: ``α`` của chia sẻ cố định.
        updates: Số kỳ đã học.
    """

    def __init__(
        self,
        arm_names: Iterable[str],
        *,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        share: float = DEFAULT_SHARE,
    ) -> None:
        names = tuple(arm_names)
        if not names:
            raise AggregationError("cần ít nhất một cánh tay")
        if len(set(names)) != len(names):
            raise AggregationError("tên cánh tay bị trùng")
        if not np.isfinite(learning_rate) or learning_rate <= 0.0:
            raise AggregationError("learning_rate phải hữu hạn và dương")
        if not np.isfinite(share) or not 0.0 <= share < 1.0:
            raise AggregationError("share phải nằm trong [0, 1)")
        self.arm_names = names
        self.learning_rate = float(learning_rate)
        self.share = float(share)
        self.updates = 0
        self._log_weights = np.full(len(names), -np.log(len(names)))
        self._cumulative_loss = np.zeros(len(names))

    def _normalised(self) -> np.ndarray:
        weights = np.exp(self._log_weights - self._log_weights.max())
        return weights / weights.sum()

    def weights(self) -> dict[str, float]:
        """Trọng số hiện hành, tổng bằng 1."""
        return {name: float(w) for name, w in zip(self.arm_names, self._normalised(), strict=True)}

    def update(self, losses: Mapping[str, float]) -> None:
        """Học một kỳ từ log-loss của từng cánh tay.

        Cánh tay vắng mặt ở kỳ này (khớp hoặc dự đoán lỗi) giữ nguyên trọng số
        tương đối: nó không bị phạt cũng không được thưởng cho một dự báo nó
        không đưa ra.

        Args:
            losses: Log-loss cộng 100 con của các cánh tay đã dự báo ở kỳ này.

        Raises:
            AggregationError: Khi có cánh tay lạ, loss không hữu hạn hoặc âm,
                hoặc không cánh tay nào có loss.
        """
        unknown = set(losses) - set(self.arm_names)
        if unknown:
            raise AggregationError(f"cánh tay không tồn tại: {sorted(unknown)}")
        if not losses:
            raise AggregationError("không có loss nào để học")
        given = np.array(list(losses.values()), dtype=float)
        if not np.all(np.isfinite(given)) or np.any(given < 0.0):
            raise AggregationError("loss phải hữu hạn và không âm")
        present = np.array([name in losses for name in self.arm_names])
        values = np.array([losses.get(name, 0.0) for name in self.arm_names], dtype=float)

        # Miền log: cánh tay có mặt nhận −η·L rồi được dời chung để tổng khối lượng
        # của nhóm có mặt giữ nguyên — cánh tay vắng giữ đúng phần của nó.
        log_weights = self._log_weights.copy()
        before = np.logaddexp.reduce(log_weights[present])
        log_weights[present] -= self.learning_rate * values[present]
        log_weights[present] += before - np.logaddexp.reduce(log_weights[present])
        if self.share > 0.0:
            mixed = (1.0 - self.share) * np.exp(log_weights) + self.share / len(log_weights)
            log_weights = np.log(mixed)

        self._log_weights = log_weights
        self._cumulative_loss = self._cumulative_loss + np.where(present, values, 0.0)
        self.updates += 1

    def report(self) -> list[dict[str, float | str]]:
        """Trọng số và loss tích luỹ từng cánh tay, xếp theo trọng số giảm dần."""
        rows = [
            {"arm": name, "weight": float(w), "cumulative_logloss": float(loss)}
            for name, w, loss in zip(
                self.arm_names, self._normalised(), self._cumulative_loss, strict=True
            )
        ]
        return sorted(rows, key=lambda row: -row["weight"])
