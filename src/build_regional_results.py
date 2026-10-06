"""Dựng trang kết quả XSMT/XSMN từ kho dữ liệu vùng đã lưu."""

from __future__ import annotations

import csv
import html
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Sequence

from css_links import stylesheet_link
from page_output import write_page
from shared_results import shared_results_css, shared_results_script
from ui_theme import app_shell_close, app_shell_open
from web_security import json_for_html_script, security_meta_tags

PRIZE_ORDER = ("ĐB", "G.1", "G.2", "G.3", "G.4", "G.5", "G.6", "G.7", "G.8")
PRIZE_LABELS = dict(zip(PRIZE_ORDER, (
    "Đặc Biệt", "Giải Nhất", "Giải Nhì", "Giải Ba", "Giải Tư",
    "Giải Năm", "Giải Sáu", "Giải Bảy", "Giải Tám",
), strict=True))
REGION_META = {
    "mt": ("Miền Trung", "XSMT", "ket-qua-mien-trung.html"),
    "mn": ("Miền Nam", "XSMN", "ket-qua-mien-nam.html"),
}


def _asset(name: str) -> str:
    return (Path(__file__).parent / "templates" / name).read_text(encoding="utf-8")


def load_rows(root: Path, region: str) -> list[dict[str, str]]:
    path = root / "data" / "regions" / f"xs{region}.csv"
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def grouped(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, list[str]]]]:
    draws = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for row in rows:
        draws[row["date"]][row["province"]][row["prize"]].append(row["value"])
    return {d: {p: dict(v) for p, v in provinces.items()} for d, provinces in draws.items()}


def board(draw_date: str, provinces: dict[str, dict[str, list[str]]]) -> str:
    """Bảng thật theo giải và tỉnh; số gốc không qua ép kiểu hay cắt độ dài."""
    day_key = html.escape(draw_date)
    display_date = date.fromisoformat(draw_date).strftime("%d/%m/%Y")
    station_ids = {province: f"rg-{draw_date}-station-{index}" for index, province in enumerate(provinces)}
    heads = "".join(
        f'<th scope="col" id="{html.escape(station_ids[p])}" data-province="{html.escape(p)}">{html.escape(p)}</th>'
        for p in provinces
    )
    body = []
    for prize in PRIZE_ORDER:
        code = "special" if prize == "ĐB" else f"prize{prize[-1]}"
        prize_id = f"rg-{draw_date}-{code}"
        cells = []
        for province in provinces:
            values = provinces[province].get(prize, [])
            nums = []
            for index, value in enumerate(values):
                pair = value[-2:]
                content = html.escape(value)
                if prize == "ĐB":
                    content = f'{html.escape(value[:-2])}<span class="tr-special-tail">{html.escape(pair)}</span>'
                cell_key = html.escape(f"{draw_date}|{province}|{code}|{index}")
                number_label = html.escape(f"Đánh dấu kết quả {value}, {PRIZE_LABELS[prize]}, {province}, ngày {display_date}")
                nums.append(
                    f'<div class="rg-num tr-number" data-cell="{cell_key}" tabindex="0" role="button"'
                    f' aria-pressed="false" aria-label="{number_label}">{content}</div>'
                )
            contents = (
                f'<div class="tr-number-grid" style="--count: {min(2, len(values))};">{"".join(nums)}</div>'
                if nums else '<span class="rg-missing" aria-label="Chưa có kết quả giải này">—</span>'
            )
            cells.append(
                f'<td class="rg-cell" data-province="{html.escape(province)}"'
                f' headers="{html.escape(prize_id)} {html.escape(station_ids[province])}">{contents}</td>'
            )
        body.append(
            f'<tr class="tr-prize-row" data-prize="{code}"><th class="tr-prize-label"'
            f' scope="row" id="{html.escape(prize_id)}">{PRIZE_LABELS[prize]}</th>{"".join(cells)}</tr>'
        )
    return (
        f'<article class="rg-draw tr-day" data-date="{day_key}">'
        f'<header class="rg-draw-head tr-day-head"><div class="tr-day-title"><h2>'
        f'<time datetime="{day_key}">{display_date}</time></h2>'
        '<span>Kết quả theo tỉnh / thành</span></div>'
        f'<span class="rg-station-count">{len(provinces)} đài</span></header>'
        '<div class="rg-board-body">'
        f'<div class="rg-table-wrap" tabindex="0" role="region" aria-label="Bảng kết quả ngày {display_date}">'
        f'<table class="rg-table" style="--rg-visible-provinces: {len(provinces)};">'
        f'<caption class="rg-caption">Kết quả ngày {display_date}, mỗi cột là một tỉnh / thành.</caption>'
        f'<thead><tr><th class="rg-corner" scope="col">Giải</th>{heads}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
        '<p class="rg-scroll-hint">Cuộn ngang để xem các đài; tên giải và tên tỉnh luôn được giữ trong bảng.</p>'
        '</div></article>'
    )


def render(region: str, rows: list[dict[str, str]]) -> str:
    name, code, filename = REGION_META[region]
    data = grouped(rows)
    dates = sorted(data, reverse=True)
    provinces = sorted({row["province"] for row in rows})
    latest = dates[0] if dates else "—"
    boards = "".join(board(d, data[d]) for d in dates[:120])
    if not boards:
        boards = '<div class="rg-empty"><strong>Chưa có dữ liệu đã lưu.</strong><span>Dữ liệu vùng sẽ có sau lượt đồng bộ kế tiếp.</span></div>'
    filter_data = json_for_html_script({"dates": dates, "provinces": provinces})

    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>Kết quả xổ số {name} · {code}</title>
<style>{shared_results_css()}
{_asset("regional_results.css")}</style></head><body>
{app_shell_open(filename, wide=True)}
<section class="rg-hero"><div><p class="rg-kicker">KẾT QUẢ XỔ SỐ {name.upper()}</p><h1>{code} · Kết quả theo tỉnh</h1><p>Tra cứu theo ngày quay và tỉnh / thành; xem đầy đủ các giải đã công bố trong cùng một bảng.</p></div><div class="rg-guide"><strong>Cách đọc bảng</strong><br>Mỗi cột là một tỉnh, mỗi hàng là một giải. Bấm số để đánh dấu hoặc so các cặp trùng.</div></section>
<section class="rg-filter" aria-label="Bộ lọc kết quả"><label>Ngày quay<select id="rg-date"><option value="">Tất cả ngày đang hiển thị</option>{"".join(f'<option value="{d}">{d}</option>' for d in dates[:120])}</select></label><label>Tỉnh / thành<select id="rg-province"><option value="">Tất cả đài</option>{"".join(f'<option value="{html.escape(p)}">{html.escape(p)}</option>' for p in provinces)}</select></label><button class="rg-btn" id="rg-reset" type="button">Đặt lại</button></section>
<div class="rg-meta"><span><strong>{len(dates)}</strong> ngày đã lưu</span><span><strong>{len(provinces)}</strong> tỉnh/thành</span><span>Mới nhất: <strong>{latest}</strong></span></div>
<div class="rg-tools"><p>Bấm số hoặc dùng Enter / Space để đánh dấu.</p><label class="tr-chip"><input type="checkbox" id="rg-pair-mode"><span>Đánh dấu cặp trùng</span></label><button class="tr-btn" id="rg-mark-clear" type="button" hidden>Bỏ đánh dấu</button></div>
<section class="rg-results tr-results" id="rg-results" aria-label="Kết quả xổ số {name}">{boards}</section>
<div class="rg-empty" id="rg-filter-empty" role="status" hidden><strong>Không có kết quả phù hợp.</strong><span>Chọn ngày hoặc tỉnh / thành khác để xem kết quả đã lưu.</span></div>
{app_shell_close(filename)}
<script id="rg-data" type="application/json">{filter_data}</script>
<script>{shared_results_script()}</script>
<script>{_asset("regional_results.js")}</script></body></html>"""


def build(root: Path) -> list[Path]:
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    outputs = []
    for region, (_, _, filename) in REGION_META.items():
        target = docs / filename
        write_page(target, render(region, load_rows(root, region)))
        outputs.append(target)
    return outputs


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    for path in build(root):
        print(f"đã ghi {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
