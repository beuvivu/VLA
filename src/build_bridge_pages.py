"""Bảy trang cầu vị trí (LOTO, hai nháy, bạch thủ, Đặc Biệt, bộ số, theo thứ) và
công cụ tạo phôi tuần.

Đọc ``data/bridge_pages/latest.json`` (do ``bridge_rules.py`` sinh ngay sau mỗi
kỳ quay). Mỗi trang nhúng 420 kỳ gần nhất; ``templates/bridge_pages.js`` tính lại
cầu cho mọi tham số người xem chọn (biên ngày, số ngày cầu chạy, thứ trong tuần,
"cả hai chữ số") và tô vị trí cầu trên các bảng kiểu Sổ kết quả.

Mỗi trang kèm bảng "Cầu dài có đáng tin hơn?" đo trên toàn lịch sử — kết luận rút
từ số đo, không viết cứng.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from bridge_rules import OUT, RULES
from build_position_bridges import MIN_ROWS, Z_ALERT, _count, _date, _rows_table, _streak_label
from page_output import write_page
from shared_results import shared_results_css
from ui_theme import app_shell_close, app_shell_open, card, page_header, stylesheet_link, write_stylesheet
from web_security import json_for_html_script, security_meta_tags

TOOL_PAGE = "tao-phoi-tuan.html"
TOOL_DRAWS = 600
WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")

#: Luật của từng kiểu, viết cho người đọc.
RULE_TEXT = {
    "loto": "Ghép chữ số ở hai vị trí a < b của bảng kết quả thành số ab. Kỳ sau trúng khi ab "
            "hoặc số lộn ba về ít nhất một nháy.",
    "hai-nhay": "Kỳ sau trúng khi số ab về từ hai nháy trở lên, hoặc cả ab lẫn số lộn ba cùng về.",
    "bach-thu": "Chỉ tính đúng số ab (không tính số lộn): kỳ sau trúng khi ab về ít nhất một nháy.",
    "dac-biet": "Kỳ sau trúng khi một chữ số của ab trùng hàng chục hoặc hàng đơn vị của hai số cuối "
                "giải Đặc Biệt. Chọn \"cả hai chữ số\" thì phải trùng đúng hai số cuối (xuôi hoặc lộn).",
    "bo-so": "Cầu chạy khi số ab ở hai vị trí giữ nguyên trong cùng một bộ qua các kỳ liên tiếp; "
             "cầu báo giải Đặc Biệt kỳ sau rơi vào bộ ấy. Bộ của xy ghép {x, bóng x} với {y, bóng y}, "
             "cả hai chiều — bộ 03 gồm 03 30 08 80 53 35 58 85.",
    "dac-biet-theo-thu": "Như cầu Đặc Biệt nhưng chỉ xét các kỳ quay cùng một thứ trong tuần.",
    "loto-theo-thu": "Như cầu LOTO nhưng chỉ xét các kỳ quay cùng một thứ trong tuần.",
}


def load(data_dir: Path) -> dict | None:
    path = data_dir / OUT / "latest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def page_css() -> str:
    return (Path(__file__).parent / "templates" / "bridge_pages.css").read_text(encoding="utf-8")


def page_script() -> str:
    return (Path(__file__).parent / "templates" / "bridge_pages.js").read_text(encoding="utf-8")


def form_card(key: str, cfg: dict, report: dict) -> str:
    extra = ""
    if cfg["kind"] == "dac-biet":
        extra += ('<label class="app-cau-inline"><input type="checkbox" name="both" value="1"> '
                  "Cả hai chữ số</label>")
    if cfg["weekday"]:
        default = report["rules"][key]["default_weekday"]
        options = "".join(f'<option value="{i}"{" selected" if i == default else ""}>{name}</option>'
                          for i, name in enumerate(WEEKDAYS))
        extra += f'<label>Thứ trong tuần<select name="thu">{options}</select></label>'
    return (
        '<form id="app-cau-form" class="app-cau-form" method="get">'
        '<label>Biên ngày cầu chạy<select name="ngay">'
        f'<option value="{report["source_date"]}">{_date(report["source_date"])}</option></select></label>'
        f'<label>Số ngày cầu chạy<input type="number" name="count" min="1" max="{report["window"] - 1}" '
        f'value="{cfg["count"]}" inputmode="numeric" required></label>'
        f"{extra}"
        '<button type="submit">Xem kết quả</button></form>'
    )


def static_grid(counts: dict[str, int]) -> str:
    """Bảng đầu 0–9 dựng sẵn — đúng khi chưa ai đổi tham số và khi JS không chạy."""
    rows = []
    for head in range(10):
        cells = "".join(
            (f'<td><span class="app-cau-cell"><b>{head}{tail}</b><span>{counts[f"{head}{tail}"]} cầu</span></span></td>'
             if f"{head}{tail}" in counts else f'<td class="app-cau-empty"><span>{head}{tail}</span></td>')
            for tail in range(10)
        )
        rows.append(f"<tr><th>Đầu {head}</th>{cells}</tr>")
    return f'<div class="app-cau-grid-wrap"><table class="app-cau-grid"><tbody>{"".join(rows)}</tbody></table></div>'


def backtest_card(cfg: dict, data: dict) -> str:
    bt = data["backtest"]
    rows = [r for r in bt["rows"] if r["n"] >= MIN_ROWS]
    up = [r for r in rows if r["z"] >= Z_ALERT]
    running = sum(r["n"] for r in bt["rows"] if r["k"] >= cfg["count"])
    per_day = f'{running / bt["draws"]:.1f}'.replace(".", ",") if bt["draws"] else "0"
    verdict = (f"{len(up)} trên {len(rows)} hàng đủ mẫu vượt kỳ vọng với z ≥ {Z_ALERT:g} — cần kiểm lại ngoài mẫu."
               if up else
               f"Không hàng nào trong {len(rows)} hàng đủ mẫu vượt kỳ vọng rõ rệt (z ≥ {Z_ALERT:g}): "
               "cầu chạy dài hơn không làm điều nó báo xảy ra thường hơn.")
    return (
        f'<p class="app-bridge-verdict">Đo trên {_count(bt["draws"])} bước kỳ-sang-kỳ trong lịch sử: '
        f"trung bình mỗi kỳ có {per_day} cầu kiểu này chạy từ {cfg['count']} ngày chỉ do ngẫu nhiên của "
        f"5 671 cặp vị trí. {verdict}</p>"
        + _rows_table("Cầu đã chạy", bt["rows"], _streak_label)
    )


def page_payload(key: str, cfg: dict, report: dict) -> dict:
    data = report["rules"][key]
    return {
        "window": report["window"],
        "draws": report["draws"],
        "rule": {"key": key, "title": cfg["title"], "kind": cfg["kind"], "count": cfg["count"],
                 "weekday": cfg["weekday"], "default_weekday": data["default_weekday"]},
        "backtest": {"rows": [{"k": r["k"], "plus": r["plus"], "n": r["n"], "rate": r["rate"],
                               "expected": r["expected"]} for r in data["backtest"]["rows"]]},
    }


def _nav_links(current: str) -> str:
    links = []
    for key, cfg in RULES.items():
        attr = ' aria-current="page"' if key == current else ""
        links.append(f'<a href="{cfg["slug"]}.html"{attr}>{html.escape(cfg["nav"])}</a>')
    return '<nav class="app-cau-tabs" aria-label="Các kiểu cầu vị trí">' + "".join(links) + "</nav>"


def render(key: str, report: dict) -> str:
    cfg = RULES[key]
    data = report["rules"][key]
    weekday_note = (f" Mặc định là các kỳ {WEEKDAYS[data['default_weekday']]} — cùng thứ với kỳ "
                    f"{_date(report['target_date'])}." if cfg["weekday"] else "")
    blocks = [
        card(_nav_links(key) + form_card(key, cfg, report), title="Tuỳ chọn", span=12, flush=True),
        card(f'<p id="app-cau-summary" class="app-cau-summary">{html.escape(cfg["title"])}: '
             f'{data["total"]} cầu chạy từ {cfg["count"]} ngày, cầu dài nhất {data["longest"]} ngày.</p>'
             f'<p class="app-cau-help">Rê chuột hoặc chạm vào một ô để thấy các vị trí tạo cầu trên bảng kết quả; '
             f'bấm vào ô để chọn từng cầu và xem cách tính.</p>'
             f'<div id="app-cau-grid">{static_grid(data["counts"])}</div>'
             '<div id="app-cau-detail" class="app-cau-detail" aria-live="polite"></div>',
             title=f"Bảng cầu cho kỳ {_date(report['target_date'])}", span=12, lift=True),
        card('<div id="app-cau-days" class="tr-results app-cau-days" data-layout="2"></div>',
             title="Vị trí cầu trên bảng kết quả", span=12, lift=True),
        card('<div id="app-cau-groups"></div>', title="Xếp hạng", span=12, lift=True),
        card(backtest_card(cfg, data), title="Cầu dài có đáng tin hơn?", span=12, lift=True),
        card(f'<p class="app-cau-rule">{html.escape(RULE_TEXT[key])}{html.escape(weekday_note)}</p>'
             '<p class="app-cau-rule">Vị trí đánh số từ 0 như trang Soi cầu vị trí: ĐB 0–4, G1 5–9, G2 10–19, '
             "G3 20–49, G4 50–65, G5 66–89, G6 90–98, G7 99–106. Cầu \"chạy N ngày\" khi N bước kỳ-sang-kỳ "
             "gần nhất đều trúng; mỗi ô của bảng là số của kỳ cuối kèm số cầu đang chạy báo nó.</p>",
             title="Cách tính", span=12, lift=True),
    ]
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  <title>{html.escape(cfg["title"])} — Phân tích XSMB</title>
  <style>
{shared_results_css()}
{page_css()}
  </style>
</head>
<body>
{app_shell_open(cfg["slug"] + ".html")}
{page_header(cfg["title"], RULE_TEXT[key] + " Công cụ mô tả, không phải lời khuyên đặt cược.")}
<div class="ui-grid">{"".join(blocks)}</div>
<script id="app-cau-data" type="application/json">{json_for_html_script(page_payload(key, cfg, report))}</script>
<script>{page_script()}</script>
{app_shell_close(cfg["slug"] + ".html")}
</body>
</html>
"""


def tool_payload(report: dict, specials: list[list[str]]) -> dict:
    return {"source_date": report["source_date"], "specials": specials}


def render_tool(specials: list[list[str]]) -> str:
    """Tạo phôi tuần: bảng giải Đặc Biệt theo tuần, tách 3 chữ số đầu và 2 chữ số cuối."""
    form = (
        '<form id="app-phoi-form" class="app-cau-form">'
        '<label>Số tuần (5–80)<input type="number" name="count" min="5" max="80" value="50"></label>'
        '<label>Cỡ chữ 3 chữ số đầu (15–35)<input type="number" name="headsize" min="15" max="35" value="20"></label>'
        '<label>Cỡ chữ 2 chữ số cuối (15–35)<input type="number" name="tailsize" min="15" max="35" value="20"></label>'
        '<label>Màu nền<input type="color" name="bgcolour" value="#ffffff"></label>'
        '<label>Màu 3 chữ số đầu<input type="color" name="headcolour" value="#000000"></label>'
        '<label>Màu 2 chữ số cuối<input type="color" name="tailcolour" value="#d11a1a"></label>'
        '<button type="button" id="app-phoi-print">In phôi</button></form>'
    )
    blocks = [
        card(form, title="Tuỳ chọn phôi", span=12, flush=True),
        card('<div id="app-phoi" class="app-phoi-wrap"><p class="app-cau-help">Bật JavaScript để tạo phôi.</p></div>',
             title="Phôi giải Đặc Biệt theo tuần", span=12, lift=True),
    ]
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  <title>Tạo phôi tuần — Phân tích XSMB</title>
  <style>
{page_css()}
  </style>
</head>
<body>
{app_shell_open(TOOL_PAGE)}
{page_header("Tạo phôi tuần", "Bảng giải Đặc Biệt theo tuần — mỗi hàng một tuần, cột Thứ Hai đến Chủ Nhật, "
             "tách 3 chữ số đầu và 2 chữ số cuối — chỉnh số tuần, cỡ chữ và màu rồi in.")}
<div class="ui-grid">{"".join(blocks)}</div>
<script id="app-phoi-data" type="application/json">{json_for_html_script({"specials": specials})}</script>
<script>{(Path(__file__).parent / "templates" / "weekly_sheet.js").read_text(encoding="utf-8")}</script>
{app_shell_close(TOOL_PAGE)}
</body>
</html>
"""


def specials_from(report: dict) -> list[list[str]]:
    """(ngày, giải Đặc Biệt) của các kỳ nhúng — dòng mã hoá mang ĐB ở 5 chữ số đầu."""
    return [[row[:10], row[10:15]] for row in report["draws"][-TOOL_DRAWS:]]


def build(data_dir: Path, docs_dir: Path) -> list[Path]:
    report = load(data_dir)
    if report is None:
        print("Chưa có data/bridge_pages/latest.json — bỏ qua.")
        return []
    write_stylesheet(docs_dir)
    written = []
    for key, cfg in RULES.items():
        out = docs_dir / f"{cfg['slug']}.html"
        write_page(out, render(key, report))
        written.append(out)
    out = docs_dir / TOOL_PAGE
    write_page(out, render_tool(specials_from(report)))
    written.append(out)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args()
    for path in build(Path(args.data_dir), Path(args.docs_dir)):
        print("Wrote:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
