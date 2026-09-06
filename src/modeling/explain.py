"""Đóng góp của từng nhóm đặc trưng vào một dự đoán cụ thể.

Với bốn nhóm đặc trưng, giá trị Shapley tính được **chính xác** chứ không cần
xấp xỉ: chỉ có 2^4 = 16 liên minh, và mỗi liên minh là một lượt dự đoán trên
100 hàng. Đây là điểm khác biệt đáng kể so với xấp xỉ lấy mẫu — con số báo ra là
phân bổ Shapley thật, không phải ước lượng có sai số không nêu.

Cách "tắt" một nhóm là thay các cột của nó bằng trung vị trên toàn tập huấn
luyện, tức đưa nhóm đó về mức "không mang thông tin gì đặc biệt về con này".
Đây là quy ước phải nêu rõ: Shapley luôn được định nghĩa tương đối với một nền
tham chiếu, và chọn nền khác sẽ cho phân bổ khác.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import factorial

import numpy as np

from features import FeatureMatrix
from modeling.stacking import StackedEnsemble

_EPS = 1e-12


@dataclass
class Explainer:
    """Phân bổ Shapley chính xác ở cấp nhóm đặc trưng."""

    model: StackedEnsemble
    reference: np.ndarray

    @classmethod
    def from_training(cls, model: StackedEnsemble, features: np.ndarray) -> Explainer:
        """Lấy nền tham chiếu là trung vị từng cột trên tập huấn luyện."""
        return cls(model=model, reference=np.median(features, axis=0))

    @property
    def group_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.model.groups))

    def _masked(self, values: np.ndarray, active: frozenset[str]) -> np.ndarray:
        """Bản sao ma trận với các nhóm ngoài ``active`` đưa về nền tham chiếu."""
        out = values.copy()
        for name, (start, stop) in self.model.groups.items():
            if name not in active:
                out[:, start:stop] = self.reference[start:stop]
        return out

    def contributions(self, matrix: FeatureMatrix) -> dict[str, np.ndarray]:
        """Giá trị Shapley của mỗi nhóm cho cả 100 con, tính chính xác."""
        names = self.group_names
        n = len(names)
        if n == 0:
            return {}

        # Một lượt dự đoán cho mỗi liên minh, dùng lại cho mọi nhóm.
        values: dict[frozenset[str], np.ndarray] = {}
        for size in range(n + 1):
            for subset in combinations(names, size):
                active = frozenset(subset)
                values[active] = self.model.predict_proba(self._masked(matrix.values, active))

        shapley = {name: np.zeros(matrix.values.shape[0]) for name in names}
        for name in names:
            others = [x for x in names if x != name]
            for size in range(len(others) + 1):
                weight = factorial(size) * factorial(n - size - 1) / factorial(n)
                for subset in combinations(others, size):
                    active = frozenset(subset)
                    shapley[name] += weight * (values[active | {name}] - values[active])
        return shapley

    def group_shares(self, matrix: FeatureMatrix, row: int) -> dict[str, float]:
        """Đóng góp của mỗi nhóm cho một con, chuẩn hóa thành phần trăm.

        Chuẩn hóa theo tổng trị tuyệt đối để nhóm kéo xác suất *xuống* vẫn hiện
        ra thay vì bị triệt tiêu lặng lẽ bởi nhóm kéo lên.
        """
        contributions = self.contributions(matrix)
        magnitudes = {name: abs(float(v[row])) for name, v in contributions.items()}
        total = sum(magnitudes.values())
        if total <= _EPS:
            return dict.fromkeys(magnitudes, 0.0)
        return {
            name: float(contributions[name][row]) / total
            for name in sorted(magnitudes, key=lambda k: -magnitudes[k])
        }

    def top_reasons(self, matrix: FeatureMatrix, row: int, k: int = 3) -> list[tuple[str, float]]:
        """``k`` nhóm đóng góp mạnh nhất cho một con, kèm tỉ trọng có dấu."""
        shares = self.group_shares(matrix, row)
        ordered = sorted(shares.items(), key=lambda item: -abs(item[1]))
        return ordered[:k]
