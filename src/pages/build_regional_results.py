"""Dựng trang kết quả XSMT/XSMN từ kho dữ liệu vùng đã lưu.

Khối «Kiểm định ngẫu nhiên và mốc xác suất» in TỪ ba tệp số đo của cùng lượt chạy
(`stats.regional_stats`, `evaluation.regional_benchmark`, `research.regional_cage_test`): mọi câu
kết luận là câu của tệp, trình dựng không tự viết kết luận nào. Trình dựng chỉ đọc JSON nên không
kéo scipy/scikit-learn vào những nơi chỉ dựng trang.
"""

from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from collections.abc import Sequence

from web.css_links import stylesheet_link
from web.page_output import write_page
from web.shared_results import shared_results_css, shared_results_script
from web.ui_theme import app_shell_close, app_shell_open
from web.web_security import json_for_html_script, security_meta_tags
from core.paths import REPO_ROOT, TEMPLATES

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
    return (TEMPLATES / name).read_text(encoding="utf-8")


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


def _vn(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _p_text(value: float) -> str:
    return "< 0,001" if value < 0.001 else _vn(value, 3)


def _vn_date(day: str) -> str:
    return date.fromisoformat(day).strftime("%d/%m/%Y")


def load_evidence(root: Path, region: str) -> dict | None:
    """Số đo của một miền: tóm tắt kiểm định, phép chấm tiến cứu, trạng thái phép kiểm đã đăng ký.

    Thiếu bản tóm tắt hoặc phép chấm thì trả ``None`` và trang không in khối này — không in một
    nửa kết luận. Bản tóm tắt và phép chấm phải cùng nói về một ngày dữ liệu.
    """
    data = root / "data"
    summary_path = data / "stats" / "regional" / f"summary_{region}.json"
    benchmark_path = data / "evaluation" / "regional_benchmark" / "benchmark.json"
    if not summary_path.exists() or not benchmark_path.exists():
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))["regions"].get(region)
    if benchmark is None or benchmark["data_through"] != summary["data_through"]:
        return None
    registry_path = data / "research" / "hypotheses" / "regional_cage_bias.json"
    registered = []
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registered = [row for row in registry.get("status", []) if row["region"] == region]
    return {"summary": summary, "benchmark": benchmark, "registered": registered}


def _cage_tables(summary: dict) -> str:
    """Bảng đếm theo lồng của từng đài bị gắn cờ: mỗi hàng một lồng, mỗi cột một quả 0–9."""
    names = summary["tests"]["cage_names"]
    out = []
    for block in summary["tests"]["per_station"]:
        counts = block.get("cage_counts")
        if not counts:
            continue
        # Chỉ năm lồng thấp: lồng trăm nghìn mỗi kỳ rút một lần, nằm ngoài phép kiểm theo lồng.
        rows = "".join(
            f'<tr><th scope="row">{html.escape(names[cage].capitalize())}</th>'
            + "".join(f"<td>{int(value)}</td>" for value in counts[cage])
            + f"<td>{_vn(sum(counts[cage]) / 10, 1)}</td></tr>"
            for cage in range(len(counts) - 1)
        )
        head = "".join(f'<th scope="col">{digit}</th>' for digit in range(10))
        label = f"rg-cage-{len(out)}"
        out.append(
            f'<p class="rg-evidence-caption" id="{label}">Đài {html.escape(block["province"])}: số lần từng quả ra '
            f'ở từng lồng qua {int(block["draws"])} kỳ</p>'
            f'<div class="ui-table-wrap"><table class="ui-table rg-cage-table" aria-labelledby="{label}">'
            f'<thead><tr><th scope="col">Lồng</th>{head}<th scope="col">Nếu đều</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>"
        )
    return "".join(out)


def _model_table(benchmark: dict) -> str:
    loto, special = benchmark["modes"]["loto"], benchmark["modes"]["de"]
    if not loto.get("models"):
        return ""
    body = []
    for key, model in loto["models"].items():
        if key == "deu":
            continue
        other = special["models"][key]
        note = " <small>(thêm sau khi đã nhìn dữ liệu)</small>" if model.get("post_hoc") else ""
        body.append(
            f'<tr><th scope="row">{html.escape(model["name"])}{note}</th>'
            f'<td>{_vn(model["mean_gain"], 5)}</td>'
            f'<td>{_vn(model["ci_low"], 5)} … {_vn(model["ci_high"], 5)}</td>'
            f'<td>{_p_text(model["p_holm"])}</td>'
            f'<td>{_vn(other["mean_gain"], 4)}</td>'
            f'<td>{_p_text(other["p_holm"])}</td></tr>'
        )
    rankings = "".join(
        f'<tr><th scope="row">{html.escape(row["name"])}</th>'
        f'<td>{_vn(row["hit_rate"] * 100, 2)}%</td><td>{_vn(row["chance"] * 100, 2)}%</td>'
        f'<td>{_p_text(row["p_holm"])}</td></tr>'
        for row in loto["rankings"].values()
    )
    return (
        '<p class="rg-evidence-caption" id="rg-model-caption">Lợi log-loss mỗi kỳ so với dự báo đều trên '
        f'{int(loto["station_draws"])} kỳ chưa thấy lúc dự báo (dương = tốt hơn; p đã hiệu chỉnh Holm)</p>'
        '<div class="ui-table-wrap"><table class="ui-table" aria-labelledby="rg-model-caption">'
        '<thead><tr><th scope="col">Mô hình</th><th scope="col">Lô: lợi mỗi kỳ</th>'
        '<th scope="col">Lô: khoảng 95%</th><th scope="col">Lô: p</th>'
        '<th scope="col">Đặc Biệt: lợi mỗi kỳ</th><th scope="col">Đặc Biệt: p</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
        '<p class="rg-evidence-caption" id="rg-ranking-caption">Cách chọn dân gian: tỉ lệ con trong Top 10 có về, '
        'so với mức của kỳ quay công bằng</p>'
        '<div class="ui-table-wrap"><table class="ui-table" aria-labelledby="rg-ranking-caption">'
        '<thead><tr><th scope="col">Cách chọn</th><th scope="col">Top 10 có về</th>'
        '<th scope="col">Mức công bằng</th><th scope="col">p</th></tr></thead>'
        f"<tbody>{rankings}</tbody></table></div>"
    )


def evidence_block(evidence: dict | None) -> str:
    """Khối kiểm định của trang miền; rỗng khi chưa có số đo."""
    if not evidence:
        return ""
    summary, benchmark = evidence["summary"], evidence["benchmark"]
    game = summary["game"]
    cards = (
        f'<div class="rg-evidence-card"><span>Một con lô ở một đài</span><strong>{_vn(game["loto_baseline"] * 100, 2)}%'
        f'</strong><small>{int(game["prizes_per_station_draw"])} giải mỗi kỳ, mỗi giải một con trong 100</small></div>'
        f'<div class="rg-evidence-card"><span>Đuôi Đặc Biệt của một đài</span><strong>'
        f'{_vn(game["special_baseline"] * 100, 2)}%</strong><small>một con trong 100 mỗi kỳ</small></div>'
        f'<div class="rg-evidence-card"><span>Số con khác nhau mỗi kỳ</span><strong>'
        f'{_vn(game["observed_distinct_numbers"], 2)}</strong><small>kỳ vọng của máy công bằng: '
        f'{_vn(game["expected_distinct_numbers"], 2)}</small></div>'
    )
    registered = "".join(f"<li>{html.escape(row['reading'])}</li>" for row in evidence["registered"])
    registered_block = (
        '<h3>Phép kiểm đã đăng ký trước, chỉ chấm trên kỳ mới</h3>'
        f'<ul class="rg-evidence-list">{registered}</ul>' if registered else ""
    )
    quality = summary["quality"]
    return (
        '<details class="rg-evidence" id="rg-evidence"><summary><strong>Kiểm định ngẫu nhiên và mốc xác suất</strong>'
        f'<span>{int(quality["stations"])} đài · {int(quality["station_draws"])} kỳ · dữ liệu đến '
        f'{_vn_date(summary["data_through"])}</span></summary><div class="rg-evidence-body">'
        f'<div class="rg-evidence-cards">{cards}</div>'
        '<h3>Các đài có quay khác một máy công bằng không?</h3>'
        f'<p>{html.escape(summary["reading"])}</p>{_cage_tables(summary)}'
        '<h3>Có cách dự báo nào hơn dự báo đều không?</h3>'
        f'<p>{html.escape(benchmark["reading"])}</p>{_model_table(benchmark)}'
        f"{registered_block}"
        '<p class="rg-evidence-note">Mỗi đài là một bộ lồng cầu riêng nên được kiểm riêng. Trang này không công bố '
        "con số dự đoán nào cho các đài: chỉ khi một cách dự báo được xác nhận trên những kỳ quay sau ngày đăng ký "
        "thì mới có cơ sở để công bố.</p></div></details>"
    )


def render(region: str, rows: list[dict[str, str]], evidence: dict | None = None) -> str:
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
{evidence_block(evidence)}
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
        write_page(target, render(region, load_rows(root, region), load_evidence(root, region)))
        outputs.append(target)
    return outputs


def main(argv: Sequence[str] | None = None) -> int:
    root = REPO_ROOT
    for path in build(root):
        print(f"đã ghi {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
