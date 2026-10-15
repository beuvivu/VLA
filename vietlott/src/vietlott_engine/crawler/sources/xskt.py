"""Kết quả Mega 6/45, Power 6/55 và Lotto 5/35 từ trang đăng lại ``xskt.com.vn``.

Vì sao có nguồn này
-------------------
Từ runner GitHub, trang nhà phát hành trả thách thức chống bot (đo 06-10-2026), nên chuỗi
``auto`` rơi xuống bản sao cộng đồng trên GitHub. Bản sao ấy cập nhật chậm: đo trên kho ngày
15-10-2026, kết quả vào dữ liệu trễ trung vị 5,6 giờ (Mega) đến 8,6 giờ (Lotto 5/35), có kỳ
34 giờ — Lotto quay hai kỳ mỗi ngày nên dự báo kỳ 21:00 hầu như không kịp ghi trước giờ quay.
``xskt.com.vn`` đăng kết quả ngay sau kỳ quay và đọc được từ runner (lớp Miền Trung/Nam của
VLA đồng bộ từ đây mỗi ngày). Nguồn này đứng SAU bản sao trong ``fallback_order``: chỉ được hỏi
khi các nguồn trước không có kỳ mới.

Cấu trúc trang (HTML chép nguyên từ trang thật qua runner ngày 06-10-2026, ghim trong
``tests/test_xskt_source.py``): mỗi kỳ là một ``table.result``; ô ``.kmt`` mang liên kết
``/<sản phẩm>/ngay-D-M-YYYY`` (ngày quay) và ``#<số kỳ>``; ô ``.megaresult`` mang dãy số. Lotto
5/35 đặt số đặc biệt trong ``<span>`` cuối dãy; Power 6/55 đặt số Jackpot 2 ở hàng "Số JP2".
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from vietlott_engine.core.exceptions import SourceError
from vietlott_engine.core.games import GameCode, GameSpec
from vietlott_engine.core.logging import get_logger
from vietlott_engine.core.models import Draw
from vietlott_engine.crawler.http import AsyncHttpClient
from vietlott_engine.crawler.sources.base import DrawSource, FetchResult

log = get_logger(__name__)

#: Trang tổng (các kỳ gần nhất) của từng sản phẩm.
PAGES: dict[GameCode, str] = {
    GameCode.MEGA_645: "/xsmega645",
    GameCode.POWER_655: "/xspower",
    GameCode.LOTTO_535: "/xslotto-5-35",
}
_DATE_IN_LINK = re.compile(r"/ngay-(\d{1,2})-(\d{1,2})-(\d{4})")
_TWO_DIGITS = re.compile(r"(?<!\d)(\d{2})(?!\d)")


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("Đ", "D").replace("đ", "d")).strip().lower()


def _money(text: str) -> int | None:
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if len(digits) >= 6 else None


def _jackpots(table) -> tuple[int | None, int | None]:  # type: ignore[no-untyped-def]
    """Giá trị Jackpot 1/2 từ bảng "Thống kê trúng giải" ngay sau bảng kết quả (nếu có)."""
    stats = table.find_next("table")
    if stats is None or "trunggiai" not in (stats.get("class") or []):
        return None, None
    jp1 = jp2 = None
    for row in stats.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        label = _fold(cells[0].get_text(" ", strip=True)).replace(".", "")
        if label == "jpot":
            jp1 = _money(cells[-1].get_text(" ", strip=True))
        elif label == "jpot2":
            jp2 = _money(cells[-1].get_text(" ", strip=True))
    return jp1, jp2


def _draw(spec: GameSpec, table) -> Draw | None:  # type: ignore[no-untyped-def]
    """Một kỳ từ một ``table.result``; None khi bảng thiếu ngày, số kỳ hay đủ số."""
    head = table.find(class_="kmt")
    link = head.find("a", href=True) if head else None
    day = _DATE_IN_LINK.search(link["href"]) if link else None
    draw_id = re.search(r"#\s*0*(\d+)", head.get_text(" ") if head else "")
    cell = table.find(class_="megaresult")
    if day is None or draw_id is None or cell is None:
        return None
    values = [int(v) for v in _TWO_DIGITS.findall(cell.get_text(" ", strip=True))]
    bonus = None
    if spec.code == GameCode.POWER_655:
        for row in table.find_all("tr"):
            if "jp2" in _fold(row.get_text(" ", strip=True)):
                found = _TWO_DIGITS.findall(row.get_text(" ", strip=True))
                bonus = int(found[-1]) if found else None
    elif spec.code == GameCode.LOTTO_535:
        if len(values) != spec.pick + 1:
            return None
        values, bonus = values[:spec.pick], values[-1]
    if len(values) != spec.pick or (spec.has_bonus and bonus is None):
        return None
    jp1, jp2 = _jackpots(table)
    return Draw(game=spec.code, draw_id=int(draw_id[1]),
                draw_date=date(int(day[3]), int(day[2]), int(day[1])),
                numbers=tuple(values), bonus=bonus, jackpot1_value=jp1, jackpot2_value=jp2, source="xskt")


def parse_page(spec: GameSpec, html: str) -> FetchResult:
    """Mọi kỳ của ``spec`` trên một trang; bảng không đọc được ghi vào ``rejected``, không bịa."""
    out = FetchResult()
    seen: dict[int, Draw] = {}
    for table in BeautifulSoup(html or "", "html.parser").select("table.result"):
        try:
            draw = _draw(spec, table)
        except ValueError as exc:  # số ngoài khoảng, trùng số, thiếu bonus… — Draw tự kiểm
            out.rejected.append((table.get_text(" ", strip=True)[:200], str(exc).splitlines()[0]))
            continue
        if draw is None:
            continue
        if draw.draw_id in seen and seen[draw.draw_id] != draw:
            raise SourceError(f"{spec.code.value} #{draw.draw_id}: trang đưa hai kết quả khác nhau")
        seen[draw.draw_id] = draw
    out.draws = [seen[i] for i in sorted(seen)]
    return out


class XsktDrawSource(DrawSource):
    """Trang tổng của sản phẩm trên ``xskt.com.vn``: vài kỳ gần nhất, mỗi kỳ có ngày và số kỳ."""

    name = "xskt"

    def __init__(self, client: AsyncHttpClient, base_url: str) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def fetch(self, spec: GameSpec, since_id: int | None = None) -> FetchResult:
        url = self.base_url + PAGES[spec.code]
        log.info("downloading %s", url)
        response = await self.client.get(url)
        result = parse_page(spec, response.text)
        if not result.draws:
            # Trang đổi cấu trúc hay trả trang lỗi: báo lỗi để chuỗi dự phòng hỏi nguồn sau,
            # không coi là "không có kỳ mới".
            raise SourceError(f"{url}: không đọc được kỳ nào")
        result.draws = [d for d in result.draws if since_id is None or d.draw_id > since_id]
        if since_id is not None and result.draws and result.draws[0].draw_id != since_id + 1:
            # Trang tổng chỉ có vài kỳ gần nhất: nhận nó sẽ để hở #since_id+1… mà lượt sau
            # (since_id đã vượt) không bao giờ bù. Báo lỗi để chuỗi hỏi nguồn có đủ lịch sử.
            raise SourceError(f"{url}: trang bắt đầu ở #{result.draws[0].draw_id}, còn thiếu từ #{since_id + 1}")
        return result
