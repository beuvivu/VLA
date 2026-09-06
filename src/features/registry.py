"""Sổ đăng ký extractor: thêm, thay hoặc gỡ phương pháp mà không sửa khung."""

from __future__ import annotations

import numpy as np

from features.base import (
    FeatureContext,
    FeatureExtractor,
    FeatureMatrix,
    validate_block,
)


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
