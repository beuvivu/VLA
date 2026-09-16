from __future__ import annotations

"""Lịch của DỮ LIỆU ĐÃ XUẤT BẢN phải khớp danh sách ngày không quay.

`validate_data.py` đã kiểm bất biến này, nhưng chỉ khi chạy cả pipeline. Lần
bổ sung lịch sử 2015→2019 cho thấy đó là chỗ hở thật: kho dài thêm 1806 kỳ,
kéo theo 20 ngày Tết cũ chưa có trong `data/non_draw_days.json`, và bộ kiểm
vẫn xanh trọn vẹn — chỉ pipeline mới đỏ, sau khi mọi thứ đã được đẩy lên.

Nên bất biến được ghim thẳng vào bộ kiểm, đọc đúng hai tệp đã xuất bản.
"""

import csv
from pathlib import Path

from calendar_alignment import known_non_draw_days, missing_calendar_dates

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPO_ROOT / "data" / "xsmb.csv"


def _shipped_dates() -> list[str]:
    with CANONICAL.open(encoding="utf-8") as handle:
        return [row["date"] for row in csv.DictReader(handle)]


def test_every_gap_in_shipped_history_is_a_declared_non_draw_day() -> None:
    gaps = set(missing_calendar_dates(_shipped_dates()))
    undeclared = sorted(gaps - known_non_draw_days())
    assert not undeclared, (
        "Lịch sử đã xuất bản có ngày vắng chưa khai trong data/non_draw_days.json. "
        "Vắng vì KHÔNG QUAY thì thêm vào tệp đó; vắng vì CÀO HỤT thì phải cào lại. "
        f"{len(undeclared)} ngày: {undeclared[:10]}"
    )


def test_declared_non_draw_days_are_not_silently_stale() -> None:
    """Mỗi ngày đã khai phải thực sự vắng trong dải dữ liệu hiện có.

    Nếu một ngày vừa nằm trong danh sách vừa có bản ghi, thì hoặc bản ghi là
    đồ bịa lọt lưới, hoặc danh sách khai sai. Cả hai đều phải nổ.
    """
    present = set(_shipped_dates())
    first, last = min(present), max(present)
    contradictions = sorted(
        d for d in known_non_draw_days() if first <= d <= last and d in present
    )
    assert not contradictions, (
        "Ngày vừa được khai là KHÔNG QUAY vừa có bản ghi trong data/xsmb.csv: "
        f"{contradictions[:10]}"
    )
