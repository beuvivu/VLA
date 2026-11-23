"""Lịch đài XSMB theo thứ, có mốc hiệu lực: MỘT nguồn cho mọi chỗ cần tên đài của một kỳ.

Căn cứ
------
* Từ 01-09-2005, Công ty XSKT Thủ Đô thay mặt Hội đồng XSKT miền Bắc tổ chức MỘT lần quay chung cho
  mọi công ty trong khu vực (Quyết định 2564/QĐ-BTC). «Đài» của một ngày là công ty phát hành vé hôm ấy,
  không phải một bộ máy quay riêng, nên mỗi ngày chỉ có một bộ 27 giải.
* Lịch luân phiên đang ghi nhận rộng rãi: Hà Nội (thứ Hai, thứ Năm), Quảng Ninh, Bắc Ninh, Hải Phòng,
  Nam Định, Thái Bình. Kho không xác minh được lịch này cho từng kỳ trong quá khứ; nó là lịch hiện hành,
  áp cho toàn bộ dữ liệu từ ngày đầu của sổ chuẩn.
* Công văn 15825/BTC-DCTC (10-10-2025) đề nghị xây dựng lịch quay mới sau đợt sáp nhập tỉnh, dự kiến áp
  dụng từ 2026 (Nam Định thuộc Ninh Bình, Thái Bình thuộc Hưng Yên). Tới 23-11-2026 kết quả vẫn ghi
  nhãn cũ. Khi lịch mới có hiệu lực, THÊM một thời kỳ vào ``ERAS`` với đúng ngày áp dụng; đừng sửa
  thời kỳ cũ, vì các kỳ trước ngày ấy vẫn mang nhãn cũ.

Vì sao có mốc hiệu lực: một bảng 7 phần tử theo thứ đổi nhãn của CẢ lịch sử khi lịch đổi, và phép phân
tích theo đài (``stats.xsmb_venue_effects``) khi ấy gộp nhầm kỳ của hai thời kỳ vào một đài.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

#: Thứ trong tuần theo ``date.weekday()``: 0 = thứ Hai … 6 = Chủ Nhật.
WEEKDAY_NAMES: Final[tuple[str, ...]] = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


@dataclass(frozen=True)
class ScheduleEra:
    """Một thời kỳ của lịch đài: từ ``start`` (kể cả) tới ngày bắt đầu của thời kỳ sau."""

    start: date
    venues: tuple[str, ...]
    basis: str

    def __post_init__(self) -> None:
        if len(self.venues) != 7 or not all(isinstance(v, str) and v for v in self.venues):
            raise ValueError("một thời kỳ phải khai đủ 7 đài, từ thứ Hai tới Chủ Nhật")


#: Các thời kỳ, xếp theo ngày bắt đầu. Đổi lịch: thêm một thời kỳ mới ở cuối, không sửa thời kỳ cũ.
ERAS: Final[tuple[ScheduleEra, ...]] = (
    ScheduleEra(
        start=date(2005, 9, 1),
        venues=("Hà Nội", "Quảng Ninh", "Bắc Ninh", "Hà Nội", "Hải Phòng", "Nam Định", "Thái Bình"),
        basis="Quay chung từ 01-09-2005 (Quyết định 2564/QĐ-BTC); lịch luân phiên đang ghi nhận.",
    ),
)


def _validate(eras: tuple[ScheduleEra, ...]) -> None:
    starts = [era.start for era in eras]
    if not eras or starts != sorted(starts) or len(set(starts)) != len(starts):
        raise ValueError("các thời kỳ phải có ngày bắt đầu tăng dần và không trùng")


_validate(ERAS)


def _as_date(value: date | str) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def era_for(value: date | str, eras: tuple[ScheduleEra, ...] = ERAS) -> ScheduleEra | None:
    """Thời kỳ áp cho ngày ấy; ``None`` khi ngày sai hoặc trước thời kỳ đầu tiên."""
    day = _as_date(value)
    if day is None:
        return None
    current = None
    for era in eras:
        if era.start <= day:
            current = era
    return current


def venue_for(value: date | str, eras: tuple[ScheduleEra, ...] = ERAS) -> str:
    """Tên đài của kỳ quay ngày ấy theo lịch có hiệu lực hôm đó; chuỗi rỗng khi không xác định."""
    day = _as_date(value)
    era = era_for(day, eras) if day is not None else None
    return era.venues[day.weekday()] if era is not None and day is not None else ""


def venues_of(eras: tuple[ScheduleEra, ...] = ERAS) -> tuple[str, ...]:
    """Mọi tên đài từng có trong lịch, theo thứ tự xuất hiện đầu tiên (thứ Hai trước)."""
    seen: list[str] = []
    for era in eras:
        for venue in era.venues:
            if venue not in seen:
                seen.append(venue)
    return tuple(seen)
