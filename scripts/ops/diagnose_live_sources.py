from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ingest.sources import (
    EXPECTED_COUNTS,
    PRIZE_ORDER,
    _label_key,
    _request_page,
    default_sources,
    extract_partial_prize_map,
)
from core.time_policy import VIETNAM_TZ

AFTER_G7_LINES = 30


def text_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "lxml")
    lines = [re.sub(r"\s+", " ", line).strip() for line in soup.get_text("\n", strip=True).splitlines()]
    return [line for line in lines if line]


def describe(html: str) -> list[str]:
    lines = text_lines(html)
    labels = [(i, _label_key(line), line) for i, line in enumerate(lines) if _label_key(line)]
    out = [f"    {len(lines)} dòng văn bản, {len(labels)} dòng mang nhãn giải"]
    for i, key, line in labels[:40]:
        out.append(f"      dòng {i:5d} {key:<8} {line[:70]!r}")
    prize_map = extract_partial_prize_map(html)
    out.append("    bóc được: " + ", ".join(f"{k}={prize_map[k]}" for k in PRIZE_ORDER))
    g7 = [i for i, key, _ in labels if key == "prize7"]
    for start in g7[:3]:
        out.append(f"    --- {AFTER_G7_LINES} dòng từ nhãn giải 7 ở dòng {start} ---")
        for j in range(start, min(len(lines), start + AFTER_G7_LINES)):
            out.append(f"      {j:5d} {lines[j][:90]!r}")
    for start in [i for i, key, line in labels if key == "special"][:3]:
        out.append(f"    --- vùng bảng giải từ dòng {start} ---")
        for j in range(start, min(len(lines), start + 45)):
            out.append(f"      {j:5d} {lines[j][:90]!r}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", action="append", default=[],
        help="ngày quay YYYY-MM-DD, lặp được; không có là hôm nay giờ VN",
    )
    parser.add_argument("--out-dir", type=Path, help="lưu HTML thô vào thư mục này")
    args = parser.parse_args(argv)
    draws = [date.fromisoformat(d) for d in args.date if d] or [datetime.now(VIETNAM_TZ).date()]
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    http = requests.Session()
    for draw in draws:
        print(f"\n##### Kỳ quay {draw.isoformat()}")
        for source in default_sources():
            for kind, urls in (("live", source.live_urls(draw)), ("ngày", source.date_urls(draw))):
                for n, url in enumerate(urls, start=1):
                    print(f"\n=== {source.name} [{kind} #{n}] {url}")
                    html = _request_page(http, url, timeout=20)
                    if not html:
                        print("    không đọc được (lỗi mạng, HTTP khác 200 hoặc trang quá lớn)")
                        continue
                    print(f"    {len(html) / 1024:.0f} KB")
                    if args.out_dir:
                        safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{draw}_{source.name}_{kind}_{n}")
                        (args.out_dir / f"{safe}.html").write_text(html, encoding="utf-8")
                    print("\n".join(describe(html)))
        print(f"\n----- {draw.isoformat()}: fetch_partial(live=True) như live_sync -----")
        for source in default_sources():
            try:
                parsed = source.fetch_partial(draw, http, live=True)
            except Exception as exc:
                print(f"  {source.name}: lỗi {type(exc).__name__}")
                continue
            received = sum(len(parsed.get(k, [])) for k in PRIZE_ORDER)
            print(f"  {source.name}: {received}/{sum(EXPECTED_COUNTS.values())} "
                  f"ĐB={parsed.get('special')} G7={parsed.get('prize7')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
