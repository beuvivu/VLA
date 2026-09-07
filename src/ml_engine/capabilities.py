"""Phát hiện thư viện tùy chọn một lần, ở một chỗ.

Vì sao module này tồn tại
--------------------------

``ml_engine`` được đặc tả trên LightGBM, Optuna, SHAP, river, CatBoost và
PyTorch. Không môi trường nào chắc chắn có đủ cả sáu: quy trình hằng ngày chạy
trên GitHub Actions với danh sách phụ thuộc gọn, còn PyTorch nặng khoảng 11 GB
nên không thể đưa vào đó.

Nếu để mỗi module tự ``try: import`` thì cùng một thư viện sẽ được thử ở sáu nơi
với sáu cách xử lý thiếu khác nhau, và lỗi "thiếu thư viện" sẽ hiện ra dưới dạng
``AttributeError`` ở giữa vòng huấn luyện. Ở đây phát hiện một lần, ghi nhật ký
một lần, và mọi thành phần hỏi cùng một câu hỏi.

Nguyên tắc suy giảm: mỗi khả năng thiếu đều có đường lui *đã được cài đặt và
kiểm thử*, không phải một nhánh chết. Kết quả có thể kém hơn, nhưng hệ thống
phải chạy và phải nói rõ nó đang chạy bằng đường nào.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from types import ModuleType
from typing import Final

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

#: Các thư viện tùy chọn, kèm lý do và đường lui khi thiếu.
_OPTIONAL: Final[dict[str, tuple[str, str]]] = {
    "lightgbm": ("cây tăng cường cho bảng và xếp hạng", "HistGradientBoosting của sklearn"),
    "catboost": ("cây tăng cường thay thế", "LightGBM hoặc HistGradientBoosting"),
    "optuna": ("tìm siêu tham số có cắt tỉa", "tìm ngẫu nhiên có kiểm soát hạt giống"),
    "shap": ("đo tầm quan trọng đặc trưng", "tầm quan trọng hoán vị"),
    "river": ("phát hiện trôi lệch trực tuyến (ADWIN)", "ADWIN tự cài trong drift.py"),
    "torch": ("mô hình chuỗi thời gian sâu (GRU)", "mô hình chuỗi tuyến tính có chính quy hóa"),
}


#: Các submodule phải nhập tường minh: gói cha không tự phơi chúng ra, nên
#: ``import river`` thành công mà ``river.drift`` vẫn ném AttributeError.
_SUBMODULES: Final[dict[str, tuple[str, ...]]] = {
    "river": ("drift",),
    "optuna": ("pruners", "samplers"),
}


def _load(name: str) -> ModuleType | None:
    try:
        module = importlib.import_module(name)
        for submodule in _SUBMODULES.get(name, ()):
            importlib.import_module(f"{name}.{submodule}")
        return module
    except Exception as error:  # pragma: no cover - phụ thuộc môi trường
        # Bắt Exception chứ không chỉ ImportError: một số gói (đáng kể là shap và
        # torch) nổ ngay lúc nhập khi lệch phiên bản nền, và một pipeline không
        # được sập vì một thư viện *tùy chọn* cài hỏng.
        LOGGER.debug("Không nhập được %s: %s", name, error)
        return None


@dataclass(frozen=True)
class Capabilities:
    """Ảnh chụp các thư viện tùy chọn có mặt trong tiến trình hiện tại."""

    lightgbm: ModuleType | None
    catboost: ModuleType | None
    optuna: ModuleType | None
    shap: ModuleType | None
    river: ModuleType | None
    torch: ModuleType | None

    @classmethod
    def detect(cls) -> Capabilities:
        """Dò một lượt toàn bộ thư viện tùy chọn.

        Returns:
            Ảnh chụp khả năng của tiến trình hiện tại.
        """
        return cls(**{name: _load(name) for name in _OPTIONAL})

    @property
    def has_boosting(self) -> bool:
        """Có sẵn cây tăng cường chuyên dụng (LightGBM hoặc CatBoost) không."""
        return self.lightgbm is not None or self.catboost is not None

    def summary(self) -> dict[str, bool]:
        """Bảng có/không cho từng thư viện, dùng để ghi vào báo cáo chạy."""
        return {name: getattr(self, name) is not None for name in _OPTIONAL}

    def log_summary(self, logger: logging.Logger = LOGGER) -> None:
        """Ghi nhật ký đường thực thi đã chọn cho từng khả năng."""
        for name, (purpose, fallback) in _OPTIONAL.items():
            if getattr(self, name) is not None:
                logger.info("ml_engine: dùng %s cho %s", name, purpose)
            else:
                logger.warning("ml_engine: thiếu %s (%s) → lui về %s", name, purpose, fallback)


#: Ảnh chụp dùng chung cho cả tiến trình. Dò lại tốn kém và không đổi khi chạy.
CAPABILITIES: Final[Capabilities] = Capabilities.detect()
