"""Thu thập và lưu kết quả xổ số Miền Trung/Miền Nam từ xskt.com.vn.

Miền Bắc vẫn là miền phân tích chính của VLA. Module này tách dữ liệu XSMT/XSMN
khỏi data/xsmb.csv để không làm thay đổi hợp đồng thống kê/AI hiện hữu.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from sources import REGIONAL_SOURCE_NAMES

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SOURCE = REGIONAL_SOURCE_NAMES[0]
REGIONS = {"mt": "Miền Trung", "mn": "Miền Nam"}
PRIZE_SPECS = (
    ("G.8", 1, 2), ("G.7", 1, 3), ("G.6", 3, 4), ("G.5", 1, 4),
    ("G.4", 7, 5), ("G.3", 2, 5), ("G.2", 1, 5), ("G.1", 1, 5), ("ĐB", 1, 6),
)
SPEC_BY_PRIZE = {name: (count, width) for name, count, width in PRIZE_SPECS}
CSV_FIELDS = ("date", "region", "province", "prize", "position", "value", "source", "fetched_at")


@dataclass(frozen=True)
class RegionalPrize:
    date: str
    region: str
    province: str
    prize: str
    position: int
    value: str
    source: str = SOURCE
    fetched_at: str = ""

    @property
    def key(self):
        return self.date, self.region, self.province, self.prize, self.position


def _fold(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.replace("Đ", "D").replace("đ", "d").lower()).strip()


def _prize_name(text: str) -> str | None:
    token = _fold(text).replace("giai ", "g").replace("giai", "g").replace(" ", "")
    aliases = {
        "g8": "G.8", "g.8": "G.8", "g7": "G.7", "g.7": "G.7",
        "g6": "G.6", "g.6": "G.6", "g5": "G.5", "g.5": "G.5",
        "g4": "G.4", "g.4": "G.4", "g3": "G.3", "g.3": "G.3",
        "g2": "G.2", "g.2": "G.2", "g1": "G.1", "g.1": "G.1",
        "db": "ĐB", "dacbiet": "ĐB",
    }
    return aliases.get(token)


def date_url(region: str, selected_date: date) -> str:
    if region not in REGIONS:
        raise ValueError("region phải là mt hoặc mn")
    return f"https://xskt.com.vn/xs{region}/ngay-{selected_date.day}-{selected_date.month}-{selected_date.year}"


def _cell_values(cell, *, width: int, count: int) -> list[str]:
    values: list[str] = []
    for part in cell.stripped_strings:
        values.extend(re.findall(rf"(?<!\d)\d{{{width}}}(?!\d)", part))
    if len(values) < count:
        values = re.findall(rf"(?<!\d)\d{{{width}}}(?!\d)", cell.get_text(" ", strip=True))
    return values[:count]


def parse_xskt_html(html_text: str, *, region: str, selected_date: date) -> list[RegionalPrize]:
    """Bóc bảng kết quả; chỉ nhận khi đủ toàn bộ 18 giá trị cho mỗi đài."""
    soup = BeautifulSoup(html_text or "", "lxml")
    stamp = datetime.now(VN_TZ).isoformat(timespec="seconds")
    date_tokens = {
        selected_date.strftime("%d/%m"),
        f"{selected_date.day}/{selected_date.month}",
        selected_date.strftime("%d-%m-%Y"),
        f"{selected_date.day}-{selected_date.month}-{selected_date.year}",
    }
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if len(trs) < 10:
            continue
        header = trs[0].find_all(["th", "td"])
        if len(header) < 2:
            continue
        lead = header[0].get_text(" ", strip=True)
        preview = table.get_text(" ", strip=True)[:240]
        if not any(t in lead or t in preview for t in date_tokens):
            continue
        provinces = [c.get_text(" ", strip=True) for c in header[1:]]
        if not provinces or any(not p or re.fullmatch(r"\d+", p) for p in provinces):
            continue

        by_prize = {}
        for tr in trs[1:]:
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            prize = _prize_name(cells[0].get_text(" ", strip=True))
            if prize:
                by_prize[prize] = cells[1:]
        if set(by_prize) != set(SPEC_BY_PRIZE):
            continue

        out: list[RegionalPrize] = []
        valid = True
        for prize, count, width in PRIZE_SPECS:
            cells = by_prize[prize]
            if len(cells) < len(provinces):
                valid = False
                break
            for province, cell in zip(provinces, cells[: len(provinces)], strict=True):
                values = _cell_values(cell, width=width, count=count)
                if len(values) != count:
                    valid = False
                    break
                for pos, value in enumerate(values, 1):
                    out.append(RegionalPrize(
                        date=selected_date.isoformat(), region=region, province=province,
                        prize=prize, position=pos, value=value, fetched_at=stamp,
                    ))
            if not valid:
                break
        if valid and len(out) == len(provinces) * 18:
            return out
    return []


def fetch_day(region: str, selected_date: date, *, session=None) -> list[RegionalPrize]:
    http = session or requests.Session()
    response = http.get(
        date_url(region, selected_date), timeout=25,
        headers={"User-Agent": "VLA/1.0 (+GitHub Actions; lottery research)"},
    )
    return parse_xskt_html(response.text, region=region, selected_date=selected_date) if response.status_code == 200 else []


def load_csv(path: Path) -> list[RegionalPrize]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [RegionalPrize(
            date=r["date"], region=r["region"], province=r["province"], prize=r["prize"],
            position=int(r["position"]), value=r["value"], source=r.get("source", SOURCE),
            fetched_at=r.get("fetched_at", ""),
        ) for r in csv.DictReader(handle)]


def write_dataset(path: Path, rows: Iterable[RegionalPrize]) -> None:
    dedup = {row.key: row for row in rows}
    order = {name: i for i, (name, _, _) in enumerate(PRIZE_SPECS)}
    rows = sorted(dedup.values(), key=lambda r: (r.date, r.province, order[r.prize], r.position))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    grouped = {}
    for row in rows:
        grouped.setdefault(row.date, {}).setdefault(row.province, {}).setdefault(row.prize, []).append(row.value)
    payload = {
        "schema_version": 1, "region": rows[0].region if rows else path.stem,
        "source": SOURCE, "timezone": "Asia/Ho_Chi_Minh",
        "draw_dates": len(grouped), "rows": len(rows), "results": grouped,
    }
    path.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_region(repo_root: Path, region: str, start: date, end: date, *, delay: float = 0.25):
    target = repo_root / "data" / "regions" / f"xs{region}.csv"
    existing = load_csv(target)
    have = {r.date for r in existing}
    added: list[RegionalPrize] = []
    attempted = 0
    http = requests.Session()
    cursor = start
    while cursor <= end:
        if cursor.isoformat() not in have:
            attempted += 1
            try:
                rows = fetch_day(region, cursor, session=http)
            except requests.RequestException:
                rows = []
            if rows:
                added.extend(rows)
                have.add(cursor.isoformat())
            if delay:
                time.sleep(delay)
        cursor += timedelta(days=1)
    write_dataset(target, [*existing, *added])
    return attempted, len(added)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Đồng bộ XSMT/XSMN từ xskt.com.vn")
    parser.add_argument("--region", choices=("mt", "mn", "both"), default="both")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--backfill-days", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args(argv)
    today = datetime.now(VN_TZ).date()
    end = date.fromisoformat(args.end_date) if args.end_date else today
    start = date.fromisoformat(args.start_date) if args.start_date else (
        end - timedelta(days=args.backfill_days - 1) if args.backfill_days > 0 else end
    )
    if start > end:
        parser.error("start-date phải <= end-date")
    root = Path(__file__).resolve().parents[1]
    for region in (("mt", "mn") if args.region == "both" else (args.region,)):
        attempted, added = sync_region(root, region, start, end, delay=max(0.0, args.delay))
        print(f"XS{region.upper()}: thử {attempted} ngày, thêm {added} dòng ({start} → {end})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
