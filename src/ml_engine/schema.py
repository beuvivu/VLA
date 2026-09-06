"""Hợp đồng dữ liệu đầu vào cho ``ml_engine``.

Vì sao kiểm ở đây chứ không ở chỗ khác
---------------------------------------

Mọi bảo đảm chống rò rỉ thời gian của module này đều dựa trên một giả định duy
nhất: **chỉ số hàng bằng thứ tự thời gian**. Nếu giả định đó sai — thiếu ngày,
trùng ngày, hoặc dữ liệu không sắp xếp — thì ``history[:day]`` không còn nghĩa
là "quá khứ", và mọi phép kiểm không-rò-rỉ phía sau sẽ đạt trong khi hệ thống
vẫn nhìn thấy tương lai.

Vì vậy ``ObservationMatrix`` từ chối dựng nếu giả định đó không giữ. Từ chối
sớm và ồn ào tốt hơn nhiều so với một mô hình có vẻ tốt vì lý do sai.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from xsmb_domain import (
    FIELD_WIDTH_MAP,
    LOTO_BASELINE_RATE,
    LOTO_DRAWS_PER_DAY,
    PRIZE_FIELDS,
)

#: Số con hai chữ số trong không gian kết quả.
NUMBER_SPACE: Final[int] = 100

#: Tỉ lệ nền của miền: xác suất một con về ít nhất một lần trong 27 giải.
BASELINE_RATE: Final[float] = LOTO_BASELINE_RATE


class SchemaError(ValueError):
    """Dữ liệu đầu vào vi phạm hợp đồng mà ``ml_engine`` dựa vào."""


@dataclass(frozen=True)
class ObservationMatrix:
    """Ma trận quan sát đã chuẩn hóa, bất biến, sắp theo thời gian.

    Đây là dạng dữ liệu duy nhất mà mọi thành phần trong ``ml_engine`` nhận.
    Quy ước: hàng ``t`` là kỳ quay ngày ``dates[t]``, và ``dates`` tăng nghiêm
    ngặt theo bước đúng một ngày. Nhờ vậy ``counts[:t]`` *luôn* là quá khứ chặt
    của ngày ``t``, không cần thành phần nào tự kiểm lại.

    Attributes:
        dates: Chỉ mục ngày, tăng nghiêm ngặt, liên tục từng ngày.
        counts: Ma trận ``(n_days, 100)``; ``counts[t, k]`` là số lần con ``k``
            xuất hiện trong 27 giải của ngày ``t``.
    """

    dates: pd.DatetimeIndex
    counts: np.ndarray

    def __post_init__(self) -> None:
        if self.counts.ndim != 2 or self.counts.shape[1] != NUMBER_SPACE:
            raise SchemaError(f"counts phải có dạng (n, {NUMBER_SPACE}), nhận {self.counts.shape}")
        if len(self.dates) != self.counts.shape[0]:
            raise SchemaError("dates và counts phải cùng số hàng")
        if self.counts.shape[0] == 0:
            raise SchemaError("cần ít nhất một kỳ quay")
        if np.any(self.counts < 0):
            raise SchemaError("counts không được âm")

        totals = self.counts.sum(axis=1)
        if not np.all(totals == LOTO_DRAWS_PER_DAY):
            bad = int(np.flatnonzero(totals != LOTO_DRAWS_PER_DAY)[0])
            raise SchemaError(
                f"mỗi kỳ phải có đúng {LOTO_DRAWS_PER_DAY} con; hàng {bad} có {int(totals[bad])}"
            )

        if len(self.dates) > 1:
            steps = self.dates.to_series().diff().dropna().dt.days.to_numpy()
            if not np.all(steps == 1):
                gap = int(np.flatnonzero(steps != 1)[0])
                raise SchemaError(
                    "dates phải liên tục từng ngày; đứt quãng sau "
                    f"{self.dates[gap].date()} ({int(steps[gap])} ngày)"
                )

    @property
    def n_days(self) -> int:
        """Số kỳ quay trong ma trận."""
        return int(self.counts.shape[0])

    @property
    def hits(self) -> np.ndarray:
        """Ma trận nhị phân ``(n_days, 100)``: con đó có về trong kỳ hay không."""
        return self.counts > 0

    @property
    def double_hits(self) -> np.ndarray:
        """Ma trận nhị phân: con đó về từ hai lần trở lên (cầu "hai nháy")."""
        return self.counts >= 2

    def window(self, start: int, stop: int) -> ObservationMatrix:
        """Cắt một cửa sổ liên tục, giữ nguyên mọi bảo đảm của lớp.

        Args:
            start: Chỉ số hàng đầu tiên, đã bao gồm.
            stop: Chỉ số hàng cuối, không bao gồm.

        Returns:
            Ma trận con trên khoảng ``[start, stop)``.
        """
        return ObservationMatrix(dates=self.dates[start:stop], counts=self.counts[start:stop])

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> ObservationMatrix:
        """Dựng ma trận từ bảng kết quả thô của kho.

        Args:
            frame: Bảng có cột ``date`` và 27 cột giải của ``xsmb_domain``.

        Returns:
            Ma trận quan sát đã chuẩn hóa.

        Raises:
            SchemaError: Khi thiếu cột, ngày trùng, hoặc ngày không liên tục.
        """
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

        working = working.sort_values("date").reset_index(drop=True)
        n_days = len(working)
        counts = np.zeros((n_days, NUMBER_SPACE), dtype=np.int16)
        for field in PRIZE_FIELDS:
            # Phải đệm 0 về đúng bề rộng khai báo của giải trước khi lấy hai chữ
            # số cuối. Tệp CSV lưu giải dưới dạng số nguyên nên số 0 đứng đầu bị
            # mất: giải 7 "08" nằm trong tệp là 8, giải 4 "0000" là 0. Cắt đuôi
            # trên chuỗi chưa đệm sẽ cho "8" — vẫn ra đúng con 08 một cách may
            # rủi, nhưng phép kiểm định dạng thì trượt, và với giải rộng hơn thì
            # không còn may nữa.
            digits = working[field].astype(str).str.strip().str.zfill(FIELD_WIDTH_MAP[field])
            valid = digits.str.fullmatch(rf"\d{{{FIELD_WIDTH_MAP[field]}}}")
            if not valid.all():
                bad = digits[~valid].iloc[0]
                raise SchemaError(f"cột {field} có giá trị không hợp lệ: {bad!r}")
            np.add.at(counts, (np.arange(n_days), digits.str[-2:].astype(int).to_numpy()), 1)

        return cls(dates=pd.DatetimeIndex(working["date"]), counts=counts)


@dataclass(frozen=True)
class DailyRequest:
    """Yêu cầu dự đoán cho đúng một kỳ.

    Attributes:
        anchor_date: Ngày cuối cùng đã biết kết quả.
        target_date: Ngày cần dự đoán; phải đúng bằng ``anchor_date`` cộng 1 ngày.
        top_k: Số con cần trả về trong danh sách gợi ý.
    """

    anchor_date: pd.Timestamp
    target_date: pd.Timestamp
    top_k: int = 10

    def __post_init__(self) -> None:
        if self.top_k < 1 or self.top_k > NUMBER_SPACE:
            raise SchemaError(f"top_k phải nằm trong [1, {NUMBER_SPACE}]")
        if (self.target_date - self.anchor_date).days != 1:
            raise SchemaError(
                "target_date phải là ngày ngay sau anchor_date "
                f"(nhận {self.anchor_date.date()} → {self.target_date.date()})"
            )

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> DailyRequest:
        """Dựng yêu cầu từ JSON đầu vào hằng ngày.

        Args:
            payload: Đối tượng có ``anchor_date`` và tùy chọn ``top_k``.
                ``target_date`` suy ra từ ``anchor_date`` nếu không có.

        Returns:
            Yêu cầu đã kiểm hợp lệ.

        Raises:
            SchemaError: Khi thiếu trường hoặc ngày không hợp lệ.
        """
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
        return cls(anchor_date=anchor, target_date=target, top_k=int(payload.get("top_k", 10)))
