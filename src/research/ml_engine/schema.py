from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Any, Final

import numpy as np
import pandas as pd

from core.calendar_alignment import unexpected_gap_dates
from core.xsmb_domain import (
    FIELD_WIDTH_MAP,
    LOTO_BASELINE_RATE,
    LOTO_DRAWS_PER_DAY,
    PRIZE_FIELDS,
)

NUMBER_SPACE: Final[int] = 100

BASELINE_RATE: Final[float] = LOTO_BASELINE_RATE


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class ObservationMatrix:

    dates: pd.DatetimeIndex
    counts: np.ndarray

    def __post_init__(self) -> None:
        counts = np.asarray(self.counts)
        if counts.dtype.kind not in "buif" or not np.all(np.isfinite(counts)):
            raise SchemaError("counts phải là số hữu hạn")
        if np.any(counts != np.floor(counts)):
            raise SchemaError("counts phải là số nguyên lần xuất hiện")
        object.__setattr__(self, "counts", counts)
        if self.counts.ndim != 2 or self.counts.shape[1] != NUMBER_SPACE:
            raise SchemaError(f"counts phải có dạng (n, {NUMBER_SPACE}), nhận {self.counts.shape}")
        if len(self.dates) != self.counts.shape[0]:
            raise SchemaError("dates và counts phải cùng số hàng")
        if self.dates.hasnans:
            raise SchemaError("dates không được chứa ngày không hợp lệ")
        if self.counts.shape[0] == 0:
            raise SchemaError("cần ít nhất một kỳ quay")
        if np.any(self.counts < 0):
            raise SchemaError("counts không được âm")
        if np.any(self.counts > LOTO_DRAWS_PER_DAY):
            raise SchemaError(f"mỗi count không được vượt {LOTO_DRAWS_PER_DAY}")

        totals = self.counts.sum(axis=1)
        if not np.all(totals == LOTO_DRAWS_PER_DAY):
            bad = int(np.flatnonzero(totals != LOTO_DRAWS_PER_DAY)[0])
            raise SchemaError(
                f"mỗi kỳ phải có đúng {LOTO_DRAWS_PER_DAY} con; hàng {bad} có {int(totals[bad])}"
            )

        if len(self.dates) > 1:
            gaps = unexpected_gap_dates(self.dates)
            if gaps:
                raise SchemaError(
                    "dates thiếu kỳ ngoài lịch nghỉ quay; "
                    f"{len(gaps)} ngày, bắt đầu từ {gaps[0]}"
                )

        protected = np.array(self.counts, dtype=np.int16, copy=True)
        protected.setflags(write=False)
        object.__setattr__(self, "counts", protected)

    @property
    def n_days(self) -> int:
        return int(self.counts.shape[0])

    @property
    def hits(self) -> np.ndarray:
        return self.counts > 0

    @property
    def double_hits(self) -> np.ndarray:
        return self.counts >= 2

    def window(self, start: int, stop: int) -> ObservationMatrix:
        return ObservationMatrix(dates=self.dates[start:stop], counts=self.counts[start:stop])

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> ObservationMatrix:
        missing = {"date", *PRIZE_FIELDS} - set(frame.columns)
        if missing:
            raise SchemaError(f"thiếu cột bắt buộc: {sorted(missing)}")

        working = frame.copy()
        working["date"] = pd.to_datetime(working["date"], errors="coerce")
        if working["date"].isna().any():
            raise SchemaError("cột date có giá trị không phân tích được")
        if working["date"].duplicated().any():
            duplicated = working.loc[working["date"].duplicated(), "date"].iloc[0]
            raise SchemaError(f"ngày bị lặp: {duplicated.date()}")

        working = working.sort_values("date", kind="stable").reset_index(drop=True)
        n_days = len(working)
        counts = np.zeros((n_days, NUMBER_SPACE), dtype=np.int16)
        for field in PRIZE_FIELDS:
            digits = working[field].astype(str).str.strip().str.zfill(FIELD_WIDTH_MAP[field])
            valid = digits.str.fullmatch(rf"\d{{{FIELD_WIDTH_MAP[field]}}}")
            if not valid.all():
                bad = digits[~valid].iloc[0]
                raise SchemaError(f"cột {field} có giá trị không hợp lệ: {bad!r}")
            np.add.at(counts, (np.arange(n_days), digits.str[-2:].astype(int).to_numpy()), 1)

        return cls(dates=pd.DatetimeIndex(working["date"]), counts=counts)


@dataclass(frozen=True)
class DailyRequest:

    anchor_date: pd.Timestamp
    target_date: pd.Timestamp
    top_k: int = 10

    def __post_init__(self) -> None:
        if isinstance(self.top_k, bool) or not isinstance(self.top_k, Integral):
            raise SchemaError("top_k phải là số nguyên")
        if self.top_k < 1 or self.top_k > NUMBER_SPACE:
            raise SchemaError(f"top_k phải nằm trong [1, {NUMBER_SPACE}]")
        if pd.isna(self.anchor_date) or pd.isna(self.target_date):
            raise SchemaError("anchor_date và target_date phải là ngày hợp lệ")
        if self.target_date.normalize() != self.anchor_date.normalize() + pd.Timedelta(days=1):
            raise SchemaError(
                "target_date phải là ngày ngay sau anchor_date "
                f"(nhận {self.anchor_date.date()} → {self.target_date.date()})"
            )

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> DailyRequest:
        if "anchor_date" not in payload:
            raise SchemaError("JSON đầu vào thiếu 'anchor_date'")
        anchor = pd.to_datetime(payload["anchor_date"], errors="coerce")
        if pd.isna(anchor):
            raise SchemaError(f"anchor_date không hợp lệ: {payload['anchor_date']!r}")
        target = (
            pd.to_datetime(payload["target_date"])
            if payload.get("target_date")
            else anchor + pd.Timedelta(days=1)
        )
        return cls(anchor_date=anchor, target_date=target, top_k=payload.get("top_k", 10))
