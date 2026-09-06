"""Chọn đặc trưng theo tầm quan trọng đo được, không theo trực giác.

Vì sao cần chọn đặc trưng ở miền này
-------------------------------------

Sinh đặc trưng tự động dễ tạo ra hàng chục cột, và trên dữ liệu gần như ngẫu
nhiên thì mỗi cột thừa là một cơ hội để mô hình khớp nhiễu. Bỏ bớt cột không
phải để chạy nhanh hơn mà để **giảm phương sai**.

Điều dễ làm sai: chọn đặc trưng trên toàn bộ dữ liệu rồi mới chia train/test.
Khi đó tập kiểm tra đã tham gia vào việc chọn cột, và kết quả ngoài mẫu không
còn ngoài mẫu nữa. Ở đây hàm chọn chỉ nhận dữ liệu huấn luyện, và tầng cuốn
chiếu gọi nó *bên trong* mỗi lần khớp.

Tại sao SHAP thay vì tầm quan trọng có sẵn của cây
---------------------------------------------------

``feature_importances_`` của cây đếm số lần một cột được dùng để chia, nên nó
thiên vị các cột có nhiều giá trị phân biệt — một cột liên tục thuần nhiễu sẽ
"quan trọng" hơn một cột nhị phân mang tin thật. Giá trị Shapley phân bổ đóng
góp theo lý thuyết trò chơi và không có thiên vị đó.

Không có ``shap`` thì lui về tầm quan trọng hoán vị: xáo trộn một cột rồi đo
mức tăng mất mát. Chậm hơn, nhưng đo đúng thứ cần đo và không thiên vị.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from sklearn.metrics import log_loss

from ml_engine.capabilities import CAPABILITIES

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

#: Ngưỡng mặc định: cột có tầm quan trọng dưới mức này bị loại.
DEFAULT_EPSILON: Final[float] = 1e-4

#: Số cột tối thiểu luôn giữ lại, kể cả khi mọi cột đều dưới ngưỡng.
MIN_FEATURES: Final[int] = 3


@dataclass(frozen=True)
class SelectionResult:
    """Kết quả một lần chọn đặc trưng.

    Attributes:
        kept: Tên các cột được giữ, sắp giảm dần theo tầm quan trọng.
        dropped: Tên các cột bị loại.
        importance: Tầm quan trọng của mọi cột, kể cả cột bị loại.
        method: ``"shap"`` hoặc ``"permutation"``.
    """

    kept: list[str]
    dropped: list[str]
    importance: dict[str, float]
    method: str

    def describe(self) -> str:
        """Câu tóm tắt để ghi nhật ký."""
        top = ", ".join(self.kept[:5])
        return (
            f"chọn {len(self.kept)}/{len(self.importance)} đặc trưng bằng {self.method}; "
            f"dẫn đầu: {top}"
        )


def shap_importance(model: Any, x: np.ndarray, names: tuple[str, ...]) -> dict[str, float]:
    """Tầm quan trọng trung bình theo trị tuyệt đối của giá trị SHAP.

    Args:
        model: Mô hình cây đã khớp.
        x: Đặc trưng dùng để giải thích.
        names: Tên cột, cùng thứ tự với ``x``.

    Returns:
        Ánh xạ tên cột sang ``mean(|SHAP|)``.

    Raises:
        RuntimeError: Khi không có ``shap`` hoặc mô hình không giải thích được.
    """
    if CAPABILITIES.shap is None:
        raise RuntimeError("thiếu thư viện shap")
    with warnings.catch_warnings():
        # shap cảnh báo mỗi lần gọi rằng định dạng đầu ra cho bộ phân loại nhị
        # phân LightGBM đã đổi thành danh sách ndarray. Hàm này xử lý cả hai
        # định dạng ngay bên dưới, nên cảnh báo chỉ làm nhiễu nhật ký — mỗi lần
        # khớp lại in một dòng, che mất những cảnh báo thật sự đáng đọc.
        warnings.filterwarnings("ignore", message=".*list of ndarray.*", category=UserWarning)
        explainer = CAPABILITIES.shap.TreeExplainer(model)
        values = explainer.shap_values(x)
    if isinstance(values, list):
        # Bộ phân loại nhị phân trả về một mảng cho mỗi lớp; lấy lớp dương.
        values = values[-1]
    values = np.asarray(values)
    if values.ndim == 3:
        # shap mới trả (n, d, n_lớp) thay vì danh sách.
        values = values[..., -1]
    magnitude = np.abs(values).mean(axis=0)
    return dict(zip(names, magnitude.astype(float), strict=True))


def permutation_importance(
    model: Any, x: np.ndarray, y: np.ndarray, names: tuple[str, ...], *, seed: int = 0
) -> dict[str, float]:
    """Tầm quan trọng hoán vị: mức log-loss tăng lên khi xáo trộn một cột.

    Args:
        model: Mô hình đã khớp, có ``predict_proba``.
        x: Đặc trưng ``(n, d)``.
        y: Nhãn nhị phân ``(n,)``.
        names: Tên cột.
        seed: Hạt giống cho phép hoán vị, để tái lập được.

    Returns:
        Ánh xạ tên cột sang mức tăng log-loss; giá trị âm được kẹp về 0 vì
        "xáo trộn cột này làm mô hình tốt lên" chỉ có nghĩa là cột đó vô dụng.
    """
    rng = np.random.default_rng(seed)
    baseline = log_loss(y, model.predict_proba(x)[:, 1], labels=[0, 1])
    scores: dict[str, float] = {}
    for position, name in enumerate(names):
        shuffled = x.copy()
        shuffled[:, position] = rng.permutation(shuffled[:, position])
        degraded = log_loss(y, model.predict_proba(shuffled)[:, 1], labels=[0, 1])
        scores[name] = max(float(degraded - baseline), 0.0)
    return scores


def select_features(
    model: Any,
    x: np.ndarray,
    y: np.ndarray,
    names: tuple[str, ...],
    *,
    epsilon: float = DEFAULT_EPSILON,
    max_features: int | None = None,
    seed: int = 0,
) -> SelectionResult:
    """Chọn tập cột đáng giữ dựa trên tầm quan trọng đo được.

    Args:
        model: Mô hình đã khớp trên ``x``, ``y``.
        x: Đặc trưng huấn luyện — **chỉ** dữ liệu huấn luyện, không có tập kiểm.
        y: Nhãn huấn luyện.
        names: Tên cột.
        epsilon: Ngưỡng dưới; cột có tầm quan trọng nhỏ hơn hoặc bằng bị loại.
        max_features: Nếu đặt, chỉ giữ nhiều nhất bấy nhiêu cột đầu bảng.
        seed: Hạt giống cho đường lui hoán vị.

    Returns:
        Kết quả chọn, gồm cột giữ, cột loại và bảng tầm quan trọng.

    Raises:
        ValueError: Khi số cột không khớp với ``names``.
    """
    if x.shape[1] != len(names):
        raise ValueError(f"x có {x.shape[1]} cột nhưng names có {len(names)} tên")

    try:
        importance = shap_importance(model, x, names)
        method = "shap"
    except Exception as error:
        LOGGER.info("Không dùng được SHAP (%s); chuyển sang tầm quan trọng hoán vị", error)
        importance = permutation_importance(model, x, y, names, seed=seed)
        method = "permutation"

    ordered = sorted(importance, key=lambda name: -importance[name])
    kept = [name for name in ordered if importance[name] > epsilon]
    if len(kept) < MIN_FEATURES:
        # Không cột nào vượt ngưỡng nghĩa là mô hình không tìm thấy tín hiệu —
        # một kết quả hợp lệ và đáng ghi nhận. Vẫn giữ vài cột đầu bảng để
        # pipeline chạy tiếp thay vì ném lỗi; tầng chuyển chế độ an toàn mới là
        # nơi xử lý tình huống "không có tín hiệu".
        LOGGER.warning(
            "Chỉ %d/%d đặc trưng vượt ngưỡng %.1e — giữ tối thiểu %d cột đầu bảng",
            len(kept),
            len(names),
            epsilon,
            MIN_FEATURES,
        )
        kept = ordered[:MIN_FEATURES]
    if max_features is not None:
        kept = kept[:max_features]

    return SelectionResult(
        kept=kept,
        dropped=[name for name in ordered if name not in set(kept)],
        importance=importance,
        method=method,
    )
