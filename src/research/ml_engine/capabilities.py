from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from types import ModuleType
from typing import Final

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_OPTIONAL: Final[dict[str, tuple[str, str]]] = {
    "lightgbm": ("cây tăng cường cho bảng và xếp hạng", "HistGradientBoosting của sklearn"),
    "catboost": ("cây tăng cường thay thế", "LightGBM hoặc HistGradientBoosting"),
    "optuna": ("tìm siêu tham số có cắt tỉa", "tìm ngẫu nhiên có kiểm soát hạt giống"),
    "shap": ("đo tầm quan trọng đặc trưng", "tầm quan trọng hoán vị"),
    "river": ("phát hiện trôi lệch trực tuyến (ADWIN)", "ADWIN tự cài trong drift.py"),
    "torch": ("mô hình chuỗi thời gian sâu (GRU)", "mô hình chuỗi tuyến tính có chính quy hóa"),
}


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
        LOGGER.debug("Không nhập được %s: %s", name, error)
        return None


@dataclass(frozen=True)
class Capabilities:

    lightgbm: ModuleType | None
    catboost: ModuleType | None
    optuna: ModuleType | None
    shap: ModuleType | None
    river: ModuleType | None
    torch: ModuleType | None

    @classmethod
    def detect(cls) -> Capabilities:
        return cls(**{name: _load(name) for name in _OPTIONAL})

    @property
    def has_boosting(self) -> bool:
        return self.lightgbm is not None or self.catboost is not None

    def summary(self) -> dict[str, bool]:
        return {name: getattr(self, name) is not None for name in _OPTIONAL}

    def log_summary(self, logger: logging.Logger = LOGGER) -> None:
        for name, (purpose, fallback) in _OPTIONAL.items():
            if getattr(self, name) is not None:
                logger.info("ml_engine: dùng %s cho %s", name, purpose)
            else:
                logger.warning("ml_engine: thiếu %s (%s) → lui về %s", name, purpose, fallback)


CAPABILITIES: Final[Capabilities] = Capabilities.detect()
