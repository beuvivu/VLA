"""Adapter bộ nhớ: tiền tố lịch sử, ngữ cảnh và luật của kho hiện hữu."""
from __future__ import annotations

from functools import cached_property

import numpy as np
import pandas as pd

from core.calendar_alignment import known_non_draw_days, missing_calendar_dates
from forecast.knowledge_base import ContextMemory
from forecast.online_learning import _history, _outcomes
from core.xsmb_domain import baseline_rate


class KnowledgeBaseManager:
    """Chuẩn hóa một tiền tố duy nhất cho mọi tác tử; không nhìn nhãn đích."""

    def __init__(self, frame: pd.DataFrame, *, target_date: str | None = None) -> None:
        if target_date is not None:
            # Lọc TRƯỚC khi chuẩn hóa để cả dữ liệu tương lai hỏng cũng không
            # thay đổi kết quả hoặc làm lộ thông tin cho dự báo quá khứ.
            frame = frame.loc[frame["date"].astype(str) < target_date]
        self.frame = _history(frame)
        gaps = set(missing_calendar_dates(self.frame["date"])) - known_non_draw_days()
        if gaps:
            raise ValueError(f"Thiếu kết quả trong lịch sử (gap): {sorted(gaps)[:3]}")

    @cached_property
    def outcomes(self) -> dict[str, np.ndarray]:
        """Chỉ báo theo kỳ: một lớp Đặc Biệt, tối đa 27 con LOTO."""
        return {mode: _outcomes(mode, self.frame) for mode in ("de", "loto")}

    @cached_property
    def memories(self) -> dict[str, ContextMemory]:
        """Vectơ 300 chiều dùng lại bộ truy xuất và khoảng bỏ chồng cửa sổ."""
        return {mode: ContextMemory(y) for mode, y in self.outcomes.items()}

    def retrieve(self, mode: str, *, at: int | None = None, k: int = 20) -> list[dict]:
        """K ngữ cảnh quá khứ đã biết kết quả, trước khoảng cách 30 kỳ."""
        t = len(self.frame) if at is None else at
        idx, similarities = self.memories[mode].neighbours(t, k)
        return [{"date": str(self.frame.iloc[int(i)]["date"]), "index": int(i),
                 "similarity": float(s)} for i, s in zip(idx, similarities, strict=True)]

    def analog_probability(self, mode: str, t: int) -> np.ndarray:
        """Đặc trưng truy xuất có co về nền; chưa là xác suất công bố."""
        idx, _ = self.memories[mode].neighbours(t, 20)
        y = self.outcomes[mode]
        return (y[idx].sum(axis=0) + 100 * baseline_rate(mode)) / (len(idx) + 100)

    def short_memory(self, mode: str) -> dict:
        """Tần suất hai cửa sổ gần nhất; số kỳ thực được ghi cùng mẫu số."""
        y = self.outcomes[mode]
        return {str(w): {"draws": min(w, len(y)), "rates": y[-w:].mean(axis=0).tolist()}
                for w in (10, 30)}

    def matching_rules(self, document: dict) -> list[dict]:
        """Chỉ truy xuất luật đã đăng ký; ảnh chụp cũ không thành bằng chứng mới."""
        current = self.outcomes["loto"][-1]
        return [{"id": r["id"], "text": r["text"], "status": r["status"],
                 "then": int(r["then"])} for r in document.get("rules", [])
                if r.get("status") != "het-han" and current[int(r["if"])]]
