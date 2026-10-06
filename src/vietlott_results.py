"""Thu thập và lưu kết quả Vietlott vào cơ sở dữ liệu phân tích riêng.

Vì sao không đọc trang của nhà phát hành
----------------------------------------
Đo ngày 06-10-2026 từ runner GitHub Actions: mọi trang của nhà phát hành (cả
trang chủ) trả HTTP 403 kèm thách thức chống bot "Just a moment… Enable
JavaScript and cookies"; Chromium thật cũng không qua được. Lách thách thức ấy
là vượt rào truy cập của trang, nên bộ thu thập KHÔNG làm. Kết quả đọc từ nguồn
đăng lại đã duyệt trong ``sources.REGIONAL_SOURCE_NAMES`` (cùng nguồn của lớp
Miền Trung/Miền Nam), nơi có Mega 6/45, Power 6/55, Max 3D/3D+, Max 3D Pro và
Lotto 5/35. Keno và Bingo18 KHÔNG có ở nguồn ấy: hai sản phẩm này để trống.

Hai cách đọc
------------
* ``update``: trang tổng của mỗi sản phẩm liệt kê vài kỳ gần nhất, mỗi bảng tự
  mang ngày và số kỳ — đủ cho lượt hằng ngày.
* ``backfill``: lùi từng ngày quay theo lịch của sản phẩm từ kỳ cũ nhất đã lưu,
  đọc trang theo ngày. Ngày không quay, trang ấy lại hiện kết quả CÙNG NGÀY của
  các năm khác, nên chỉ nhận bảng có ngày trùng đúng ngày yêu cầu.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from sources import REGIONAL_SOURCE_NAMES

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SOURCE = REGIONAL_SOURCE_NAMES[0]
BASE = f"https://{SOURCE}"
UA = "VLA/1.0 (+GitHub Actions; lottery research)"

#: sản phẩm → (tên, kiểu bảng, số giá trị chính, có số phụ, đường dẫn theo ngày, thứ quay).
#: Thứ quay theo ``date.weekday()`` (0 = thứ Hai); ``None`` là quay mọi ngày.
PRODUCTS: dict[str, tuple[str, str, int, bool, tuple[str, ...], tuple[int, ...] | None]] = {
    "lotto535": ("Lotto 5/35", "balls", 5, True, ("xslotto-13h", "xslotto-21h"), None),
    "mega645": ("Mega 6/45", "balls", 6, False, ("xsmega645",), (2, 4, 6)),
    "power655": ("Power 6/55", "balls", 6, True, ("xspower",), (1, 3, 5)),
    "max3d": ("Max 3D / Max 3D+", "max3d", 20, False, ("xsmax3d",), (0, 2, 4)),
    "max3dpro": ("Max 3D Pro", "max3dpro", 20, False, ("xsmax3dpro",), (1, 3, 5)),
    "keno": ("Keno", "unavailable", 20, False, (), None),
    "bingo18": ("Bingo18", "unavailable", 3, False, (), None),
}
#: Trang tổng (kỳ gần nhất) của từng sản phẩm có nguồn.
LATEST_PAGES = {
    "lotto535": "/xslotto-5-35",
    "mega645": "/xsmega645",
    "power655": "/xspower",
    "max3d": "/xsmax3d",
    "max3dpro": "/xsmax3dpro",
}
#: Max 3D xếp giải Nhất 2, Nhì 4, Ba 6, Tư 8 bộ; Max 3D Pro xếp ĐB 2, Nhất 4, Nhì 6, Ba 8.
TRIPLE_GROUPS = {
    "max3d": (("first", "Giải nhất", 2), ("second", "Giải nhì", 4),
              ("third", "Giải ba", 6), ("fourth", "Giải tư", 8)),
    "max3dpro": (("special", "Giải ĐB", 2), ("first", "Giải nhất", 4),
                 ("second", "Giải nhì", 6), ("third", "Giải ba", 8)),
}
DATE_IN_LINK = re.compile(r"/ngay-(\d{1,2})-(\d{1,2})-(\d{4})")


@dataclass(frozen=True)
class Draw:
    product: str
    draw_id: str
    draw_date: str
    result: tuple[str, ...]
    bonus: str = ""
    jackpot_1: int | None = None
    jackpot_2: int | None = None
    meta_json: str = "{}"
    source_url: str = ""
    fetched_at: str = ""


def _fold(text: str) -> str:
    """Chữ thường, gộp khoảng trắng — để so nhãn giải mà không lệ thuộc định dạng."""
    return re.sub(r"\s+", " ", (text or "").replace("Đ", "D").replace("đ", "d")).strip().lower()


def _link_date(href: str) -> str:
    m = DATE_IN_LINK.search(href or "")
    return f"{int(m[3]):04d}-{int(m[2]):02d}-{int(m[1]):02d}" if m else ""


def _draw_id(text: str) -> str:
    m = re.search(r"#\s*(\d+)", text or "")
    return m[1] if m else ""


def _money(text: str) -> int | None:
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if len(digits) >= 6 else None


def _jackpots(table) -> tuple[int | None, int | None]:
    """Giá trị Jackpot 1/2 từ bảng "Thống kê trúng giải" ngay sau bảng kết quả."""
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


def _parse_balls(product: str, table, stamp: str, url: str) -> Draw | None:
    _, _, count, has_bonus, _, _ = PRODUCTS[product]
    head = table.find(class_="kmt")
    link = head.find("a", href=True) if head else None
    day, did = _link_date(link["href"] if link else ""), _draw_id(head.get_text(" ") if head else "")
    cell = table.find(class_="megaresult")
    if not day or not did or cell is None:
        return None
    values = re.findall(r"(?<!\d)(\d{2})(?!\d)", cell.get_text(" ", strip=True))
    bonus = ""
    if product == "power655":
        # Số Jackpot 2 nằm ở một hàng riêng ngay dưới dãy kết quả.
        for row in table.find_all("tr"):
            if "jp2" in _fold(row.get_text(" ", strip=True)):
                found = re.findall(r"(?<!\d)(\d{2})(?!\d)", row.get_text(" ", strip=True))
                bonus = found[-1] if found else ""
    elif has_bonus:
        # Lotto 5/35: số đặc biệt nằm trong <span> cuối dãy.
        bonus = values[-1] if len(values) == count + 1 else ""
        values = values[:count]
    if len(values) != count or (has_bonus and not bonus):
        return None
    jp1, jp2 = _jackpots(table)
    meta = {}
    if product == "lotto535":
        m = re.search(r"\((\d{1,2})h\)", head.get_text(" ", strip=True))
        meta = {"session": f"{m[1]}h"} if m else {}
    return Draw(product, did, day, tuple(values), bonus, jp1, jp2,
                json.dumps(meta, ensure_ascii=False), url, stamp)


def _parse_triples(product: str, table, stamp: str, url: str) -> Draw | None:
    head = table.find(class_="kmt")
    link = head.find("a", href=True) if head else None
    day, did = _link_date(link["href"] if link else ""), _draw_id(head.get_text(" ") if head else "")
    if not day or not did:
        return None
    groups: dict[str, list[str]] = {}
    for key, label, count in TRIPLE_GROUPS[product]:
        wanted = _fold(label)
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2 or not _fold(cells[0].get_text(" ", strip=True)).startswith(wanted):
                continue
            found = re.findall(r"(?<!\d)(\d{3})(?!\d)", cells[1].get_text(" ", strip=True))
            if len(found) == count:
                groups[key] = found
                break
    if len(groups) != len(TRIPLE_GROUPS[product]):
        return None
    result = tuple(v for key, _, _ in TRIPLE_GROUPS[product] for v in groups[key])
    return Draw(product, did, day, result, "", None, None,
                json.dumps({"groups": groups}, ensure_ascii=False), url, stamp)


def parse_page(product: str, html: str, url: str = "") -> list[Draw]:
    """Mọi kỳ quay của ``product`` có trên một trang, mỗi kỳ mang ngày và số kỳ riêng."""
    kind = PRODUCTS[product][1]
    soup = BeautifulSoup(html or "", "lxml")
    stamp = datetime.now(TZ).isoformat(timespec="seconds")
    draws: list[Draw] = []
    if kind == "balls":
        for table in soup.select("table.result"):
            draw = _parse_balls(product, table, stamp, url)
            if draw:
                draws.append(draw)
    elif kind in TRIPLE_GROUPS:
        for table in soup.find_all("table"):
            if table.find(class_="kmt") is None:
                continue
            draw = _parse_triples(product, table, stamp, url)
            if draw:
                draws.append(draw)
    return draws


def _get(http, url: str, attempts: int = 3, pause: float = 2.0) -> str | None:
    """Trang ở ``url``; lỗi mạng hay 5xx thì thử lại. Lượt nạp 06-10-2026 mất trọn
    hai ngày Lotto 5/35 vì một lần gọi lỗi thoáng qua không được thử lại."""
    for attempt in range(attempts):
        try:
            r = http.get(url, timeout=30, headers={"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9"})
        except requests.RequestException:
            r = None
        if r is not None and r.status_code == 200:
            return r.text
        if r is not None and r.status_code < 500:
            return None
        if attempt + 1 < attempts and pause:
            time.sleep(pause * (attempt + 1))
    return None


def day_urls(product: str, day: date) -> list[str]:
    return [f"{BASE}/{slug}/ngay-{day.day}-{day.month}-{day.year}" for slug in PRODUCTS[product][4]]


def fetch_day(http, product: str, day: date) -> list[Draw]:
    """Các kỳ của ``product`` quay đúng ngày ``day`` — bỏ kết quả cùng ngày năm khác."""
    out = []
    for url in day_urls(product, day):
        html = _get(http, url)
        out.extend(d for d in parse_page(product, html or "", url) if d.draw_date == day.isoformat())
    return out


def fetch_latest(http, product: str) -> list[Draw]:
    url = urljoin(BASE, LATEST_PAGES[product])
    return parse_page(product, _get(http, url) or "", url)


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript("""PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS draws(product TEXT NOT NULL,draw_id TEXT NOT NULL,draw_date TEXT NOT NULL,
    result_json TEXT NOT NULL,bonus TEXT NOT NULL DEFAULT '',jackpot_1 INTEGER,jackpot_2 INTEGER,
    meta_json TEXT NOT NULL DEFAULT '{}',source_url TEXT NOT NULL,fetched_at TEXT NOT NULL,
    PRIMARY KEY(product,draw_id));
    CREATE INDEX IF NOT EXISTS idx_vietlott_product_date ON draws(product,draw_date DESC,draw_id DESC);""")
    return db


def upsert(db: sqlite3.Connection, d: Draw) -> None:
    db.execute("""INSERT INTO draws VALUES(?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(product,draw_id) DO UPDATE SET draw_date=excluded.draw_date,result_json=excluded.result_json,
    bonus=excluded.bonus,jackpot_1=excluded.jackpot_1,jackpot_2=excluded.jackpot_2,
    meta_json=excluded.meta_json,source_url=excluded.source_url,fetched_at=excluded.fetched_at""",
               (d.product, d.draw_id, d.draw_date, json.dumps(d.result), d.bonus, d.jackpot_1,
                d.jackpot_2, d.meta_json, d.source_url, d.fetched_at))


def backfill_days(start: date, weekdays: tuple[int, ...] | None, limit_days: int):
    """Các ngày quay lùi dần từ ``start`` (không gồm ``start``), tối đa ``limit_days`` ngày lịch."""
    for back in range(1, limit_days + 1):
        day = start - timedelta(days=back)
        if weekdays is None or day.weekday() in weekdays:
            yield day


def gap_days(known: list[tuple[str, str]], weekdays: tuple[int, ...] | None) -> list[date]:
    """Các ngày quay nằm giữa hai kỳ đã lưu mà số kỳ bị đứt quãng.

    ``known`` là (số kỳ, ngày). Tính cả hai ngày đầu mút vì Lotto 5/35 quay hai
    kỳ một ngày: kỳ thiếu có thể cùng ngày với kỳ đã có.
    """
    rows = sorted((int(did), day) for did, day in known)
    days: set[date] = set()
    for (a_id, a_day), (b_id, b_day) in zip(rows, rows[1:]):
        if b_id - a_id <= 1:
            continue
        cursor, end = date.fromisoformat(a_day), date.fromisoformat(b_day)
        while cursor <= end:
            if weekdays is None or cursor.weekday() in weekdays:
                days.add(cursor)
            cursor += timedelta(days=1)
    return sorted(days, reverse=True)


def crawl_product(db, http, product: str, limit: int = 500, delay: float = 0.15,
                  mode: str = "update") -> tuple[int, int]:
    """Trả (số kỳ đọc được, số kỳ mới ghi)."""
    if PRODUCTS[product][1] == "unavailable":
        return 0, 0
    known = {r[0] for r in db.execute("SELECT draw_id FROM draws WHERE product=?", (product,))}
    draws = fetch_latest(http, product)
    if mode == "backfill":
        row = db.execute("SELECT MIN(draw_date) FROM draws WHERE product=?", (product,)).fetchone()
        oldest = min([date.fromisoformat(row[0])] if row and row[0] else
                     [date.fromisoformat(d.draw_date) for d in draws] or [datetime.now(TZ).date()])
        empty_streak = 0
        for day in backfill_days(oldest, PRODUCTS[product][5], limit * 3):
            if len(draws) >= limit or empty_streak >= 30:
                break
            found = fetch_day(http, product, day)
            empty_streak = 0 if found else empty_streak + 1
            draws.extend(found)
            if delay:
                time.sleep(delay)
    # Vá lỗ hổng: số kỳ đứt quãng giữa hai kỳ đã lưu thì đọc lại các ngày ở giữa.
    stored = list(db.execute("SELECT draw_id, draw_date FROM draws WHERE product=?", (product,)))
    stored += [(d.draw_id, d.draw_date) for d in draws]
    for day in gap_days(stored, PRODUCTS[product][5])[:limit]:
        draws.extend(fetch_day(http, product, day))
        if delay:
            time.sleep(delay)
    added = 0
    for draw in draws:
        if draw.draw_id not in known:
            upsert(db, draw)
            known.add(draw.draw_id)
            added += 1
    db.commit()
    return len(draws), added


def export(root: Path, db: sqlite3.Connection) -> None:
    out = root / "data" / "vietlott"
    out.mkdir(parents=True, exist_ok=True)
    rows = db.execute("""SELECT product,draw_id,draw_date,result_json,bonus,jackpot_1,jackpot_2,meta_json,source_url,fetched_at
    FROM draws ORDER BY draw_date,product,CAST(draw_id AS INTEGER)""").fetchall()
    fields = ("product", "draw_id", "draw_date", "result_json", "bonus", "jackpot_1", "jackpot_2",
              "meta_json", "source_url", "fetched_at")
    with (out / "draws.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)
    latest: dict = {}
    counts: dict[str, int] = {}
    for row in rows:
        p = row[0]
        counts[p] = counts.get(p, 0) + 1
        latest[p] = {"draw_id": row[1], "draw_date": row[2], "result": json.loads(row[3]), "bonus": row[4],
                     "jackpot_1": row[5], "jackpot_2": row[6], "meta": json.loads(row[7]), "source_url": row[8]}
    (out / "latest.json").write_text(json.dumps(
        {"source": SOURCE, "timezone": "Asia/Ho_Chi_Minh", "counts": counts, "latest": latest},
        ensure_ascii=False, indent=2), encoding="utf-8")


def available_products() -> list[str]:
    return [p for p, spec in PRODUCTS.items() if spec[1] != "unavailable"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Đồng bộ kết quả Vietlott")
    ap.add_argument("--products", default="all")
    ap.add_argument("--limit", type=int, default=500, help="số kỳ tối đa mỗi sản phẩm (backfill)")
    ap.add_argument("--delay", type=float, default=0.15)
    ap.add_argument("--mode", choices=("update", "backfill"), default="update")
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    db = init_db(root / "data" / "vietlott" / "vietlott.sqlite3")
    http = requests.Session()
    products = available_products() if a.products == "all" else [x.strip() for x in a.products.split(",") if x.strip()]
    for p in products:
        scanned, added = crawl_product(db, http, p, max(1, a.limit), max(0.0, a.delay), a.mode)
        print(p, scanned, added)
    export(root, db)
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
