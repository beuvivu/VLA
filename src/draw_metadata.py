"""Lưu mã hiệu Đặc Biệt theo kỳ; không suy mã từ ngày hoặc kỳ liền trước."""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from calendar_widget import load_special_results
from sources import XosoComVnSource, _request_page

logger = logging.getLogger(__name__)
STATIONS = ("Hà Nội", "Quảng Ninh", "Bắc Ninh", "Hà Nội", "Hải Phòng", "Nam Định", "Thái Bình")
CODE = re.compile(r"[1-9][0-9]?[A-Z]{2}")
CACHE = Path("data/draw_metadata.json")


def station_for_date(value: str) -> str:
    """Lịch đài theo nhãn ngày Việt Nam, không phụ thuộc múi giờ máy dựng."""
    try:
        return STATIONS[date.fromisoformat(value).weekday()]
    except (TypeError, ValueError):
        return ""


def _valid_codes(values: object) -> bool:
    return (isinstance(values, list) and 0 < len(values) <= 20
            and all(isinstance(item, str) and CODE.fullmatch(item) for item in values)
            and len(set(values)) == len(values))


def parse_draw_metadata(page: str, selected_date: date, expected_special: str) -> dict | None:
    """Chỉ nhận mã trong đúng khối ngày và khi Đặc Biệt khớp lịch sử thật."""
    soup = BeautifulSoup(page, "lxml")
    block = soup.find(id=f"kqngay_{selected_date:%d%m%Y}_kq")
    if block is None:
        return None
    code_cell = block.find(id="mb_prizeCode")
    special_cell = block.find(id="mb_prizeDB_item0")
    if code_cell is None or special_cell is None:
        return None
    special = special_cell.get_text(strip=True)
    if special != expected_special or re.fullmatch(r"[0-9]{5}", special) is None:
        return None
    codes = [node.get_text(strip=True) for node in code_cell.find_all("span")]
    if not _valid_codes(codes):
        return None
    return {"station": station_for_date(selected_date.isoformat()), "special_codes": codes, "special": special}


def _read_cache(repo_root: Path) -> dict:
    try:
        payload = json.loads((repo_root / CACHE).read_text(encoding="utf-8"))
        draws = payload.get("draws", {})
        return draws if isinstance(draws, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def load_draw_metadata(repo_root: Path) -> dict[str, dict]:
    """Chỉ đưa chú thích còn khớp kết quả vào giao diện, không lộ nguồn nội bộ."""
    results = load_special_results(repo_root)
    out = {}
    for key, item in _read_cache(repo_root).items():
        if (not isinstance(item, dict) or not station_for_date(key)
                or key not in results or item.get("special") != results[key]
                or not _valid_codes(item.get("special_codes"))):
            continue
        out[key] = {"station": station_for_date(key), "special_codes": item["special_codes"]}
    return out


def refresh_draw_metadata(repo_root: Path, *, http=None, selected_date: date | None = None) -> bool:
    """Cập nhật kỳ đã có kết quả; mất mạng giữ nguyên sổ mã đã xác nhận."""
    results = load_special_results(repo_root)
    if not results:
        return False
    key = selected_date.isoformat() if selected_date else max(results)
    if key not in results:
        return False
    selected_date = date.fromisoformat(key)
    url = XosoComVnSource().date_url(selected_date)
    owned = http is None
    client = http or requests.Session()
    try:
        if owned:
            client.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Language": "vi-VN,vi;q=0.9"})
        page = _request_page(client, url, timeout=10)
        metadata = parse_draw_metadata(page, selected_date, results[key])
    finally:
        if owned:
            client.close()
    if metadata is None:
        logger.warning("Chưa xác nhận được mã hiệu Đặc Biệt kỳ %s; giữ dữ liệu đã lưu.", key)
        return False
    draws = _read_cache(repo_root)
    draws[key] = {**metadata, "source_url": url,
                  "checked_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(timespec="seconds")}
    path = repo_root / CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"schema_version": 1, "draws": dict(sorted(draws.items()))},
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Cập nhật mã hiệu Đặc Biệt cho kỳ đã xác thực.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--date", type=date.fromisoformat)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    refresh_draw_metadata(args.repo_root, selected_date=args.date)


if __name__ == "__main__":
    main()
