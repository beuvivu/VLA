from __future__ import annotations

"""Exact calendar alignment primitives for time-dependent analytics.

Row adjacency is not a time interval.  Every algorithm that claims a one-day or
N-day lag must either use these index pairs or explicitly require a contiguous
daily series.  This prevents a missing canonical date from silently turning a
2-day jump into a "next-day" transition.
"""

import json
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd


def normalize_dates(dates: Sequence[object] | pd.Series | pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    if idx.hasnans:
        raise ValueError("dates contain null/invalid values")
    if idx.has_duplicates:
        duplicates = idx[idx.duplicated()].strftime("%Y-%m-%d").tolist()
        raise ValueError(f"dates contain duplicates: {duplicates[:5]}")
    if not idx.is_monotonic_increasing:
        raise ValueError("dates must be sorted in strictly increasing order")
    return idx


def calendar_lag_pairs(
    dates: Sequence[object] | pd.Series | pd.Index, lag_days: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return source/target indices separated by exactly ``lag_days`` calendar days."""
    if lag_days <= 0:
        raise ValueError("lag_days must be >= 1")
    idx = normalize_dates(dates)
    if len(idx) == 0:
        empty = np.array([], dtype=np.int32)
        return empty, empty.copy()

    # The dates are already sorted and unique (``normalize_dates`` enforces
    # both), so the "does date + lag exist?" lookup is a binary search rather
    # than a Python dict walk over every timestamp. ~2.7x faster and identical.
    wanted = idx + pd.Timedelta(days=int(lag_days))
    position = idx.searchsorted(wanted)
    in_range = position < len(idx)
    probe = np.where(in_range, position, 0)
    matches = in_range & (idx.to_numpy()[probe] == wanted.to_numpy())
    return (
        np.flatnonzero(matches).astype(np.int32),
        position[matches].astype(np.int32),
    )


def consecutive_next_pairs(
    dates: Sequence[object] | pd.Series | pd.Index,
) -> tuple[np.ndarray, np.ndarray]:
    return calendar_lag_pairs(dates, 1)


def missing_calendar_dates(
    dates: Sequence[object] | pd.Series | pd.Index,
) -> list[str]:
    idx = normalize_dates(dates)
    if len(idx) < 2:
        return []
    expected = pd.date_range(idx[0], idx[-1], freq="D")
    missing = expected.difference(idx)
    return missing.strftime("%Y-%m-%d").tolist()


@lru_cache(maxsize=1)
def known_non_draw_days() -> frozenset[str]:
    """Những ngày XSMB không quay, đọc từ ``data/non_draw_days.json``.

    XSMB nghỉ dịp Tết mỗi năm và suốt đợt giãn cách 01-22/4/2020. Vào những
    ngày đó trang nguồn vẫn trả kết quả gần nhất, nên trình cào từng ghi lại
    như thể đó là kỳ của ngày ấy — 50 bản ghi bịa, 4 trong số đó lọt qua cả
    kiểm đồng thuận hai nguồn (sáu nguồn cùng đọc một trang tin nên ở dạng
    hỏng này chúng không độc lập).

    Chính dữ liệu bịa đó đã làm chuỗi ngày trông liền mạch. Sau khi loại
    chúng, kiểm tra liền mạch phải phân biệt được hai việc khác hẳn nhau:

    * **không quay** — hợp lệ, ngày đó không tồn tại kỳ nào;
    * **cào hụt** — hỏng, phải báo lỗi.

    Returns:
        Tập ngày ``YYYY-MM-DD``; rỗng nếu chưa có tệp.
    """
    path = Path(__file__).resolve().parents[1] / "data" / "non_draw_days.json"
    if not path.exists():
        return frozenset()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(payload.get("ngay_khong_quay", ()))


def unexpected_gap_dates(
    dates: Sequence[object] | pd.Series | pd.Index,
    *,
    allow_missing: Iterable[str] | None = None,
) -> list[str]:
    """Ngày vắng mà KHÔNG giải thích được bằng lịch nghỉ quay.

    Ba nơi trong kho từng tự kiểm chuỗi ngày liền mạch bằng mã riêng
    (``calendar_alignment``, ``production_audit``, ``ml_engine.schema``). Cả ba
    đều coi mọi ngày vắng là hỏng, nên chúng chỉ xanh chừng nào 50 bản ghi bịa
    còn lấp vào chỗ trống — tức là bất biến được bảo đảm bởi chính dữ liệu sai.

    Args:
        dates: Chuỗi ngày cần kiểm.
        allow_missing: Ngày được phép vắng; mặc định
            :func:`known_non_draw_days`.

    Returns:
        Các ngày vắng cần báo động, tăng dần.
    """
    allowed = (
        known_non_draw_days() if allow_missing is None else frozenset(allow_missing)
    )
    return [d for d in missing_calendar_dates(dates) if d not in allowed]


def require_daily_contiguous(
    dates: Sequence[object] | pd.Series | pd.Index,
    *,
    context: str = "time series",
    allow_missing: Iterable[str] | None = None,
) -> pd.DatetimeIndex:
    """Bắt buộc chuỗi ngày liền mạch, trừ những ngày vốn không có kỳ quay.

    Args:
        dates: Chuỗi ngày cần kiểm.
        context: Tên ngữ cảnh, đưa vào thông báo lỗi.
        allow_missing: Ngày được phép vắng. Mặc định lấy
            :func:`known_non_draw_days`; truyền tập rỗng để đòi liền mạch
            tuyệt đối.

    Returns:
        Chỉ mục ngày đã chuẩn hoá.

    Raises:
        ValueError: Nếu còn ngày vắng không nằm trong danh sách cho phép.
    """
    idx = normalize_dates(dates)
    missing = unexpected_gap_dates(idx, allow_missing=allow_missing)
    if missing:
        raise ValueError(
            f"{context} requires contiguous calendar days; missing {len(missing)} date(s): "
            + ", ".join(missing[:10])
        )
    return idx
