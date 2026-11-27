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

from ingest.sources import (
    EXPECTED_COUNTS,
    EXPECTED_WIDTHS,
    PRIZE_ORDER,
    MketquaSource,
    MAX_PAGE_BYTES,
    MinhNgocSource,
    extract_partial_prize_map,
)

FIELDS: tuple[str, ...] = tuple(
    key if EXPECTED_COUNTS[key] == 1 else f"{key}_{i}"
    for key in PRIZE_ORDER
    for i in range(1, EXPECTED_COUNTS[key] + 1)
)
WIDTHS: dict[str, int] = {field: EXPECTED_WIDTHS[field.split("_")[0]] for field in FIELDS}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
DELAY_RANGE = (1.5, 3.0)
REQUEST_DEADLINE = 45.0
MINHNGOC_DAYS_PER_PAGE = 7

_MN_DAY = re.compile(r"(?:Ngày:|Miền Bắc\s*-)\s*(\d{2})/(\d{2})/(\d{4})")
_MK_DAY = re.compile(r"ngày\s+(\d{2})-(\d{2})-(\d{4})", re.IGNORECASE)


def text_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "lxml")
    lines = [re.sub(r"\s+", " ", line).strip() for line in soup.get_text("\n", strip=True).splitlines()]
    return [line for line in lines if line]


def flatten(prize_map: dict[str, list[str]]) -> dict[str, str] | None:
    if any(len(prize_map.get(key, [])) != EXPECTED_COUNTS[key] for key in PRIZE_ORDER):
        return None
    values = [value for key in PRIZE_ORDER for value in prize_map[key]]
    return dict(zip(FIELDS, values, strict=True))


def split_days(lines: list[str], marker: re.Pattern[str]) -> dict[date, dict[str, str]]:
    starts: list[tuple[int, date]] = []
    for index, line in enumerate(lines):
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
        row = flatten(extract_partial_prize_map(html.escape("\n".join(lines[index:stop]), quote=False)))
        if row is not None:
            found[day] = row
    return found


def read_ledger(path: Path, start: date, end: date) -> dict[date, dict[str, str]]:
    rows: dict[date, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            day = date.fromisoformat(raw["date"][:10])
            if start <= day <= end:
                rows[day] = {field: str(int(float(raw[field]))).zfill(WIDTHS[field]) for field in FIELDS}
    return rows


def minhngoc_anchors(days: Iterable[date]) -> list[date]:
    pending = sorted(set(days), reverse=True)
    anchors: list[date] = []
    while pending:
        anchor = pending[0]
        anchors.append(anchor)
        floor = anchor - timedelta(days=MINHNGOC_DAYS_PER_PAGE - 1)
        pending = [day for day in pending if day < floor]
    return anchors


def _page_days(url: str, get: Callable[[str], str], marker: re.Pattern[str]) -> dict[date, dict[str, str]]:
    began = time.monotonic()
    lines = text_lines(get(url))
    days = split_days(lines, marker)
    if not days:
        hints = [line[:90] for line in lines if "gày" in line][:4]
        print(f"   trang không cho kỳ nào ({len(lines)} dòng, {time.monotonic() - began:.0f}s): {url} {hints}",
              flush=True)
    return days


def fetch_with_deadline(session: requests.Session, url: str, *, deadline: float = REQUEST_DEADLINE) -> str:
    began = time.monotonic()
    try:
        with session.get(url, timeout=(10, 20), stream=True) as response:
            if response.status_code != 200:
                return ""
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_PAGE_BYTES or time.monotonic() - began > deadline:
                    print(f"   bỏ trang ({size // 1024} KB, {time.monotonic() - began:.0f}s): {url}", flush=True)
                    return ""
            body = b"".join(chunks)
    except requests.RequestException as exc:
        print(f"   lỗi mạng {type(exc).__name__}: {url}", flush=True)
        return ""
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode(response.encoding or "utf-8", errors="replace")


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
    parser = argparse.ArgumentParser()
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
        return fetch_with_deadline(session, url)

    def pause() -> None:
        time.sleep(random.uniform(*DELAY_RANGE))

    exit_code = 0
    for name in dict.fromkeys(args.source):
        began = time.monotonic()
        other = READERS[name](sorted(ledger), get, pause)
        print(f"   ({name}: {time.monotonic() - began:.0f}s)", flush=True)
        for line in report(name, ledger, other):
            print(line, flush=True)
        if compare(ledger, other)["differences"]:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
