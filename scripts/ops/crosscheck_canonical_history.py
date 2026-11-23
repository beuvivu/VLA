"""Đối chiếu một dải kỳ của sổ chuẩn XSMB với nơi ghi KHÁC, từng ô một.

Vì sao cần: các kỳ 2015 → 08-2026 của ``data/xsmb.csv`` vào kho qua đợt bổ sung lịch sử tháng
9-2026, với ``min_agreement = 1``. Mỗi kỳ chỉ cần MỘT nguồn bóc được, và nguồn đầu danh sách khi
ấy là ``xoso.com.vn`` (thứ tự ``default_sources`` lúc đó: xoso.com.vn, mketqua.net, Minh Ngọc,
…). Một độ lệch thống kê tìm thấy trên những kỳ ấy (đợt lệch lồng đơn vị 2024 của
``stats.xsmb_venue_effects``) có thể là đặc tính của kết quả công bố, hoặc lỗi của đúng một nơi
ghi. Đọc lại các kỳ ấy từ nơi ghi khác thì phân biệt được hai trường hợp.

Máy phiên làm việc không gọi được trang ngoài, nên script chạy trên runner
(``.github/workflows/diagnose-live-sources.yml``, khi khai ``crosscheck_start``). Nó chỉ ĐỌC:
không ghi gì vào kho, không lưu trang. Log chỉ in số ô trùng, từng ô khác, các kỳ không đọc
được, và số đếm chữ số lồng đơn vị trên chính bản ghi của nơi ghi kia.

Nơi ghi
-------
``minhngoc``  Trang theo ngày của Minh Ngọc hiện BẢY kỳ liền (ngày chọn và sáu ngày trước). Script
              gọi một trang cho mỗi bảy ngày, tách từng kỳ theo dòng «Ngày: dd/mm/yyyy».
``mketqua``   Một trang cho mỗi kỳ; khối giải bắt đầu ở dòng mang «ngày dd-mm-yyyy».

Mỗi trang gọi đúng một lần, chờ 1,5–3 giây giữa hai lần gọi.
"""

from __future__ import annotations

import argparse
import csv
import html
import random
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ingest.sources import (  # noqa: E402
    EXPECTED_COUNTS,
    EXPECTED_WIDTHS,
    PRIZE_ORDER,
    MketquaSource,
    MinhNgocSource,
    _request_page,
    extract_partial_prize_map,
)

#: Tên cột của sổ chuẩn theo đúng thứ tự giải: special, prize1, prize2_1, prize2_2, …
FIELDS: tuple[str, ...] = tuple(
    key if EXPECTED_COUNTS[key] == 1 else f"{key}_{i}"
    for key in PRIZE_ORDER
    for i in range(1, EXPECTED_COUNTS[key] + 1)
)
WIDTHS: dict[str, int] = {field: EXPECTED_WIDTHS[field.split("_")[0]] for field in FIELDS}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
DELAY_RANGE = (1.5, 3.0)
#: Minh Ngọc in bảy kỳ trên một trang theo ngày.
MINHNGOC_DAYS_PER_PAGE = 7

#: Minh Ngọc mở mỗi kỳ bằng «KẾT QUẢ XỔ SỐ Miền Bắc - dd/mm/yyyy» rồi «Ngày: dd/mm/yyyy»; khối của dòng
#: đầu không có giải nên bị bỏ, khối của dòng sau mang trọn 27 ô.
_MN_DAY = re.compile(r"(?:Ngày:|Miền Bắc\s*-)\s*(\d{2})/(\d{2})/(\d{4})")
_MK_DAY = re.compile(r"ngày\s+(\d{2})-(\d{2})-(\d{4})", re.IGNORECASE)


def text_lines(html: str) -> list[str]:
    """Các dòng văn bản của trang, đúng như bộ bóc giải nhìn thấy."""
    soup = BeautifulSoup(html or "", "lxml")
    lines = [re.sub(r"\s+", " ", line).strip() for line in soup.get_text("\n", strip=True).splitlines()]
    return [line for line in lines if line]


def flatten(prize_map: dict[str, list[str]]) -> dict[str, str] | None:
    """Bảng giải bóc được → một hàng theo tên cột của sổ; ``None`` khi thiếu ô."""
    if any(len(prize_map.get(key, [])) != EXPECTED_COUNTS[key] for key in PRIZE_ORDER):
        return None
    values = [value for key in PRIZE_ORDER for value in prize_map[key]]
    return dict(zip(FIELDS, values, strict=True))


def split_days(lines: list[str], marker: re.Pattern[str]) -> dict[date, dict[str, str]]:
    """Tách trang thành từng kỳ: khối của một kỳ chạy từ dòng mang ngày của nó tới dòng mang ngày kế.

    Kỳ nào bóc không đủ 27 ô thì bỏ (không đoán). Một ngày xuất hiện hai lần thì giữ lần đầu.
    """
    starts: list[tuple[int, date]] = []
    for index, line in enumerate(lines):
        # Nhãn và ngày có thể nằm ở hai phần tử («Ngày:» rồi một liên kết ngày), tức hai dòng.
        joined = f"{line} {lines[index + 1]}" if index + 1 < len(lines) else line
        match = marker.search(line) or marker.search(joined)
        if match and match.start() < len(line):
            day, month, year = (int(part) for part in match.groups())
            try:
                starts.append((index, date(year, month, day)))
            except ValueError:
                continue
    found: dict[date, dict[str, str]] = {}
    for position, (index, day) in enumerate(starts):
        if day in found:
            continue
        stop = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        # Dòng văn bản như «<<<<» của thanh chuyển trang phải về lại là chữ, không thành thẻ.
        row = flatten(extract_partial_prize_map(html.escape("\n".join(lines[index:stop]), quote=False)))
        if row is not None:
            found[day] = row
    return found


def read_ledger(path: Path, start: date, end: date) -> dict[date, dict[str, str]]:
    """Các kỳ của sổ chuẩn trong dải, mỗi ô đệm số 0 đầu theo độ rộng giải."""
    rows: dict[date, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            day = date.fromisoformat(raw["date"][:10])
            if start <= day <= end:
                rows[day] = {field: str(int(float(raw[field]))).zfill(WIDTHS[field]) for field in FIELDS}
    return rows


def minhngoc_anchors(days: Iterable[date]) -> list[date]:
    """Ngày cần gọi để phủ mọi kỳ: mỗi trang phủ ngày gọi và sáu ngày trước nó."""
    pending = sorted(set(days), reverse=True)
    anchors: list[date] = []
    while pending:
        anchor = pending[0]
        anchors.append(anchor)
        floor = anchor - timedelta(days=MINHNGOC_DAYS_PER_PAGE - 1)
        pending = [day for day in pending if day < floor]
    return anchors


def _page_days(url: str, get: Callable[[str], str], marker: re.Pattern[str]) -> dict[date, dict[str, str]]:
    """Các kỳ bóc được trên một trang; trang không cho kỳ nào thì in vài dòng mang ngày để chẩn đoán."""
    lines = text_lines(get(url))
    days = split_days(lines, marker)
    if not days:
        hints = [line[:90] for line in lines if "gày" in line][:4]
        print(f"   trang không cho kỳ nào ({len(lines)} dòng): {url} {hints}", flush=True)
    return days


def read_minhngoc(days: list[date], get: Callable[[str], str], pause: Callable[[], None]) -> dict[date, dict[str, str]]:
    source, found = MinhNgocSource(), {}
    for n, anchor in enumerate(minhngoc_anchors(days)):
        if n:
            pause()
        for day, row in _page_days(source.date_url(anchor), get, _MN_DAY).items():
            found.setdefault(day, row)
    return {day: found[day] for day in days if day in found}


def read_mketqua(days: list[date], get: Callable[[str], str], pause: Callable[[], None]) -> dict[date, dict[str, str]]:
    source, found = MketquaSource(), {}
    for n, day in enumerate(sorted(days, reverse=True)):
        if n:
            pause()
        rows = _page_days(source.date_url(day), get, _MK_DAY)
        if day in rows:
            found[day] = rows[day]
    return found


READERS: dict[str, Callable[..., dict[date, dict[str, str]]]] = {"minhngoc": read_minhngoc, "mketqua": read_mketqua}


def compare(ledger: dict[date, dict[str, str]], other: dict[date, dict[str, str]]) -> dict[str, object]:
    """So từng ô; trả số kỳ/ô trùng, danh sách ô khác và các kỳ nơi ghi kia không có."""
    differences = [(day, field, ledger[day][field], other[day][field])
                   for day in sorted(other) if day in ledger
                   for field in FIELDS if ledger[day][field] != other[day][field]]
    compared = [day for day in sorted(other) if day in ledger]
    return {
        "draws": len(compared),
        "cells": len(compared) * len(FIELDS),
        "matching_draws": len(compared) - len({day for day, *_ in differences}),
        "differences": differences,
        "missing": sorted(set(ledger) - set(other)),
    }


def units_digits(rows: dict[date, dict[str, str]]) -> tuple[list[int], float]:
    """Số đếm chữ số hàng đơn vị của 27 giải trên mọi kỳ, và χ² so với phân bố đều (9 bậc tự do)."""
    counts = Counter(row[field][-1] for row in rows.values() for field in FIELDS)
    observed = [counts.get(str(digit), 0) for digit in range(10)]
    expected = sum(observed) / 10
    chi2 = sum((value - expected) ** 2 / expected for value in observed) if expected else 0.0
    return observed, chi2


def report(name: str, ledger: dict[date, dict[str, str]], other: dict[date, dict[str, str]]) -> list[str]:
    result = compare(ledger, other)
    lines = [
        f"== {name}: đọc được {len(other)}/{len(ledger)} kỳ; so {result['draws']} kỳ, {result['cells']} ô; "
        f"{result['matching_draws']} kỳ trùng đủ 27 ô; {len(result['differences'])} ô khác",
    ]
    lines += [f"   KHÁC {day} {field}: sổ={mine} {name}={theirs}" for day, field, mine, theirs in result["differences"]]
    if result["missing"]:
        lines.append(f"   không đọc được {len(result['missing'])} kỳ: " + ", ".join(map(str, result["missing"])))
    observed, chi2 = units_digits(other)
    lines.append(f"   lồng đơn vị trên bản ghi của {name}: {observed}, χ² = {chi2:.2f} (9 bậc tự do)")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", required=True, type=date.fromisoformat, help="ngày đầu YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=date.fromisoformat, help="ngày cuối YYYY-MM-DD")
    parser.add_argument("--source", action="append", choices=sorted(READERS), required=True,
                        help="nơi ghi để đối chiếu; lặp lại để đọc nhiều nơi")
    parser.add_argument("--ledger", type=Path, default=ROOT / "data" / "xsmb.csv")
    args = parser.parse_args(argv)
    if args.start > args.end:
        parser.error("--start phải trước --end")

    ledger = read_ledger(args.ledger, args.start, args.end)
    observed, chi2 = units_digits(ledger)
    print(f"Sổ chuẩn {args.start} → {args.end}: {len(ledger)} kỳ; lồng đơn vị {observed}, χ² = {chi2:.2f}")

    session = requests.Session()
    session.headers["User-Agent"] = UA

    def get(url: str) -> str:
        return _request_page(session, url)

    def pause() -> None:
        time.sleep(random.uniform(*DELAY_RANGE))

    exit_code = 0
    for name in dict.fromkeys(args.source):
        other = READERS[name](sorted(ledger), get, pause)
        for line in report(name, ledger, other):
            print(line, flush=True)
        if compare(ledger, other)["differences"]:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
