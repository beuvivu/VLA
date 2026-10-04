"""Trang Soi cầu vị trí và ô "cầu đẹp nhất" cạnh bảng LOTO ở trang chủ.

Đọc ``data/position_bridges/latest.json`` (do ``position_bridges.py`` sinh ngay
sau mỗi kỳ quay) và dựng ``docs/soi-cau-vi-tri.html``. Trang nhúng 60 kỳ gần
nhất; bộ máy trong trình duyệt (``templates/position_bridges.js``) tính lại cầu
cho mọi tham số người xem chọn và vẽ đường cầu trên bảng kiểu Sổ kết quả.

Phần "Cầu dài có đáng tin hơn?" là phép kiểm trên toàn lịch sử, không phải lời
khuyên: nó trả lời bằng số đo câu hỏi mà cách soi cầu mặc nhiên coi là đúng.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from urllib.parse import urlencode

from page_output import write_page
from position_bridges import MODES, OUT, pair_key
from shared_results import shared_results_css
from ui_theme import app_shell_close, app_shell_open, card, page_header, stylesheet_link, write_stylesheet
from web_security import json_for_html_script, security_meta_tags

PAGE = "soi-cau-vi-tri.html"
#: Dưới cỡ mẫu này z không đáng tin (xấp xỉ chuẩn hỏng khi số lần trúng kỳ vọng
#: chỉ vài lần), nên trang ghi "mẫu nhỏ" thay cho con số.
MIN_ROWS = 200
Z_ALERT = 3.0


def load(data_dir: Path) -> dict | None:
    path = data_dir / OUT / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%".replace(".", ",")


def _count(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def bridge_css() -> str:
    return (Path(__file__).parent / "templates" / "position_bridges.css").read_text(encoding="utf-8")


def bridge_script() -> str:
    return (Path(__file__).parent / "templates" / "position_bridges.js").read_text(encoding="utf-8")


def analysis_css() -> str:
    """Bố cục chung của các trang soi cầu, chỉ áp dụng trong họ trang này."""
    return (Path(__file__).parent / "templates" / "bridge_workspace.css").read_text(encoding="utf-8")


def analysis_header(title: str, subtitle: str, meta=(), *, section="Soi cầu / Miền Bắc") -> str:
    header = page_header(title, subtitle, meta)
    return header.replace(
        '<header class="ui-header">',
        '<header class="ui-header app-analysis-header">'
        '<div class="app-analysis-topline"><a href="index.html">← Trang chính</a>'
        '<span class="ui-badge ui-badge-ok">Dữ liệu XSMB · Miền Bắc</span></div>'
        f'<p class="app-analysis-eyebrow">{html.escape(section)}</p>',
        1,
    )


def link(cfg: dict, bridge: dict | None = None, *, base: str = PAGE) -> str:
    """Đường dẫn tới đường cầu, cùng bộ tham số với trang đối chiếu."""
    params = {}
    if bridge is not None:
        params["vt"] = bridge["vt"]
    params.update({"limit": cfg["limit"], "exactlimit": 0, "lon": int(cfg["lon"]),
                   "nhay": cfg["nhay"], "db": int(cfg["db"])})
    return f"{base}?{urlencode(params)}"


def _chip(cfg: dict, bridge: dict) -> str:
    """Một cầu trong ô trang chủ: cặp số, số bóng (nếu là số kép) và số ngày chạy."""
    numbers = pair_key(bridge["numbers"])
    shadow = bridge.get("shadow")
    # Mỗi số một phần tử: "67,76" viết liền đọc như số thập phân 67,76.
    num = lambda n: f'<span class="app-bridge-num">{html.escape(n)}</span>'  # noqa: E731
    shown = ",".join(num(n) for n in numbers.split(","))
    extra = f'<i class="app-bridge-shadow">,{num(shadow)}</i>' if shadow else ""
    title = f'Vị trí {bridge["vt"]} · chạy {bridge["streak"]} ngày · {bridge.get("same_pair", 1)} cầu cùng báo cặp này'
    if shadow:
        title += f" · {shadow} là số bóng của {numbers}, chỉ tham khảo"
    return (f'<li><a href="{html.escape(link(cfg, bridge))}" title="{html.escape(title)}">'
            f'<b>{shown}{extra}</b>'
            f'<span class="app-bridge-streak">{bridge["streak"]}</span></a></li>')


def best_panel(report: dict | None, draw_date: str) -> str:
    """Ô ba nhóm "cầu đẹp nhất" đặt cạnh bảng LOTO của khung kết quả hằng ngày.

    Chỉ hiện khi báo cáo dựng từ ĐÚNG kỳ đang hiển thị — ô cầu của hôm qua đặt
    cạnh kết quả hôm nay là sai lặng lẽ.
    """
    if not report or report.get("source_date") != draw_date:
        return ('<aside class="app-bridge-best" aria-label="Soi cầu vị trí">'
                '<div class="app-bridge-best-head"><h3>Soi cầu vị trí</h3></div>'
                '<p class="app-bridge-stale">Cầu cho kỳ mới đang được tính lại sau kỳ quay.</p></aside>')
    groups = []
    for key, cfg in MODES.items():
        mode = report["modes"][key]
        summary = mode["summary"]
        chips = "".join(_chip(cfg, bridge) for bridge in mode["best"])
        body = (f'<ol class="app-bridge-list">{chips}</ol>' if chips
                else '<p class="app-bridge-stale">Không có cầu nào đủ độ dài.</p>')
        groups.append(
            f'<section class="app-bridge-group" data-mode="{key}"><h4>'
            f'<a href="{html.escape(link(cfg))}">{html.escape(cfg["title"])}</a>'
            f'<small>≥ {cfg["limit"]} ngày · {summary["count"]} cầu</small></h4>{body}</section>'
        )
    return (
        '<aside class="app-bridge-best" aria-label="Soi cầu vị trí">'
        f'<div class="app-bridge-best-head"><h3>Cầu đẹp nhất kỳ {_date(report["target_date"])[:5]}</h3>'
        f'<a href="{PAGE}#kiem-chung">Cầu dài có đáng tin? →</a></div>'
        f'<div class="app-bridge-groups">{"".join(groups)}</div>'
        '<p class="app-bridge-note">Số nhỏ: số ngày cầu đã chạy. Số nhạt sau số kép là số bóng.</p></aside>'
    )


def _z(row: dict) -> str:
    if row["n"] < MIN_ROWS:
        return "mẫu nhỏ"
    return f"{row['z']:+.2f}".replace(".", ",")


def _rows_table(head: str, rows: list[dict], label) -> str:
    body = "".join(
        f"<tr><td>{html.escape(label(r))}</td><td>{_count(r['n'])}</td><td>{_pct(r['rate'])}</td>"
        f"<td>{_pct(r['expected'])}</td><td>{_z(r)}</td></tr>"
        for r in rows if r["n"]
    )
    return ('<div class="ui-table-wrap"><table class="ui-table ui-r2 ui-r3 ui-r4 ui-r5">'
            f"<thead><tr><th>{html.escape(head)}</th><th>Số lần</th><th>Kỳ sau trúng</th>"
            f"<th>Kỳ vọng</th><th>z</th></tr></thead><tbody>{body}</tbody></table></div>")


def _streak_label(row: dict) -> str:
    return f"≥ {row['k']} ngày" if row["plus"] else f"{row['k']} ngày"


def _consensus_label(row: dict) -> str:
    if row["to"] is None:
        return f"≥ {row['from']} cầu"
    return f"{row['from']} cầu" if row["from"] == row["to"] else f"{row['from']}–{row['to']} cầu"


def verdict(mode: dict) -> dict:
    """Kết luận rút TỪ SỐ ĐO: có hàng nào (đủ mẫu) trúng nhiều hơn kỳ vọng rõ rệt?"""
    rows = [r for r in mode["streaks"]["rows"] + mode["consensus"]["rows"] if r["n"] >= MIN_ROWS]
    up = [r for r in rows if r["z"] >= Z_ALERT]
    limit = mode["limit"]
    running = sum(r["n"] for r in mode["streaks"]["rows"] if r["k"] >= limit)
    return {"tested": len(rows), "up": len(up),
            "per_day": running / mode["streaks"]["draws"] if mode["streaks"]["draws"] else 0.0}


def backtest_card(report: dict) -> str:
    parts = []
    for key, cfg in MODES.items():
        mode = report["modes"][key]
        v = verdict(mode)
        streaks = mode["streaks"]
        if v["up"]:
            line = (f"{v['up']} trên {v['tested']} hàng đủ mẫu trúng nhiều hơn kỳ vọng với z ≥ {Z_ALERT:g} — "
                    "cần kiểm lại ngoài mẫu trước khi tin.")
        else:
            line = (f"Không hàng nào trong {v['tested']} hàng đủ mẫu trúng nhiều hơn kỳ vọng rõ rệt "
                    f"(z ≥ {Z_ALERT:g}): cầu dài hơn, hay nhiều cầu cùng báo một cặp hơn, không làm số về "
                    "thường hơn.")
        per_day = f'{v["per_day"]:.1f}'.replace(".", ",")
        parts.append(
            f'<h3 class="app-bridge-subhead">{html.escape(cfg["title"])}</h3>'
            f'<p class="app-bridge-summary">Trung bình mỗi ngày có {per_day} cầu đạt '
            f'≥ {cfg["limit"]} ngày chỉ do ngẫu nhiên của 5 671 cặp vị trí; hôm nay có '
            f'{mode["summary"]["count"]}. {line}</p>'
            + _rows_table("Cầu đã chạy", streaks["rows"], _streak_label)
            + _rows_table(f"Cùng báo một cặp (cầu ≥ {cfg['limit']} ngày)", mode["consensus"]["rows"],
                          _consensus_label)
        )
    draws = report["modes"]["lo"]["streaks"]["draws"]
    return (
        f'<p class="app-bridge-verdict">Đo trên {_count(draws)} kỳ đã quay: mỗi dòng là tỉ lệ kỳ '
        "kế tiếp trúng, so với kỳ vọng nếu cầu KHÔNG mang thông tin (tính riêng số kép và số thường "
        "vì số kép chỉ là một số). z đếm mỗi kỳ là một cụm, vì mọi cầu cùng kỳ dùng chung 27 giải.</p>"
        + "".join(parts)
    )


def method_card() -> str:
    items = [
        "Bảng kết quả có 107 chữ số, đánh vị trí từ 0: ĐB 0–4, G1 5–9, G2 10–19, G3 20–49, "
        "G4 50–65, G5 66–89, G6 90–98, G7 99–106.",
        "Cầu a×b lấy chữ số ở vị trí a và vị trí b của kỳ hôm trước ghép thành số hai chữ số. "
        "Có lộn thì báo cả hai chiều (ví dụ 4 và 6 báo 46, 64); không lộn thì thứ tự có nghĩa.",
        "LOTO: kỳ sau trúng khi các số của cặp về đủ số nháy, cộng gộp cả hai chiều. "
        "Đặc Biệt: hai số cuối giải Đặc Biệt kỳ sau nằm trong cặp.",
        "Cầu chạy N ngày khi N kỳ quay liên tiếp gần nhất đều trúng; kỳ nghỉ không tính.",
        "Số kép hiện kèm số bóng (0↔5, 1↔6, 2↔7, 3↔8, 4↔9: 44 kèm 99) để tham khảo; "
        "số bóng không dùng khi dò cầu.",
        "Ba ô ở trang chủ chọn mỗi cặp số một cầu, xếp theo độ dài rồi số cầu cùng báo. "
        "Quy tắc này tự đặt và công khai; bảng kiểm chứng bên trên cho thấy nó không nâng tỉ lệ trúng.",
    ]
    return '<ol class="app-bridge-method">' + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ol>"


def form_card() -> str:
    options = "".join(f'<option value="{n}">{n} nháy</option>' for n in range(1, 6))
    return (
        f'<form id="app-bridge-form" class="app-bridge-form" action="{PAGE}" method="get">'
        '<label>Độ dài của cầu (ngày)<input type="number" name="limit" min="1" max="59" value="5" '
        'inputmode="numeric" required></label>'
        '<label>So độ dài<select name="exactlimit"><option value="0">Bằng hoặc hơn</option>'
        '<option value="1">Chính xác bằng</option></select></label>'
        f'<label>Số nháy LOTO<select name="nhay">{options}</select></label>'
        '<fieldset><legend>Loại cầu</legend><label class="app-bridge-inline">'
        '<input type="checkbox" name="db" value="1"> Giải Đặc Biệt</label></fieldset>'
        '<fieldset><legend>Chiều ghép</legend><div class="app-bridge-radios">'
        '<label><input type="radio" name="lon" value="1" checked> Lộn</label>'
        '<label><input type="radio" name="lon" value="0"> Không lộn</label></div></fieldset>'
        '<button type="submit">Soi cầu</button></form>'
    )


def page_payload(report: dict) -> dict:
    """Phần nhúng cho bộ máy trình duyệt: kỳ quay và dòng kiểm lịch sử rút gọn."""
    return {
        "source_date": report["source_date"],
        "target_date": report["target_date"],
        "window": report["window"],
        "draws": report["draws"],
        "backtests": {
            key: {"nhay": mode["nhay"], "db": mode["db"], "lon": mode["lon"],
                  "draws": mode["streaks"]["draws"],
                  "rows": [{"k": r["k"], "plus": r["plus"], "n": r["n"], "rate": r["rate"],
                            "expected": r["expected"]} for r in mode["streaks"]["rows"]]}
            for key, mode in report["modes"].items()
        },
    }


def render(report: dict) -> str:
    target = _date(report["target_date"])
    blocks = [
        card(form_card(), title="Bộ lọc & lựa chọn", span=12, flush=True,
             aside='<span class="app-analysis-caption">Chọn điều kiện rồi bấm Soi cầu</span>'),
        '<section class="ui-card ui-c12 app-bridge-path" hidden>'
        '<div id="app-bridge-path" class="ui-card-body" aria-live="polite"></div></section>',
        card(f'<div id="app-bridge-list">{best_panel(report, report["source_date"])}</div>',
             title=f"Cầu cho kỳ {target}", span=12, lift=True),
        card('<div id="app-bridge-matrix"><p class="app-bridge-help">Bật JavaScript để xem bảng vị trí cầu.'
             '</p></div>', title="Bảng vị trí cầu", span=12, lift=True),
        card(backtest_card(report), title="Cầu dài có đáng tin hơn?", span=12, lift=True)
        .replace('<section class="', '<section id="kiem-chung" class="', 1),
        card(method_card(), title="Cách soi cầu vị trí", span=12, lift=True),
    ]
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  <title>Soi cầu vị trí — Phân tích XSMB</title>
  <style>
{shared_results_css()}
{bridge_css()}
{analysis_css()}
  </style>
</head>
<body class="app-analysis-page app-position-page">
{app_shell_open(PAGE)}
{analysis_header(
    "Soi cầu vị trí",
    "Chọn vị trí, theo dõi đường cầu và đối chiếu với từng kỳ kết quả.",
    (f"Dữ liệu đến {_date(report['source_date'])}", f"Kỳ tiếp theo {target}",
     "Thống kê mô tả · Không phải khuyến nghị đặt cược"),
)}
<div class="ui-grid">{"".join(blocks)}</div>
<script id="app-bridge-data" type="application/json">{json_for_html_script(page_payload(report))}</script>
<script>{bridge_script()}</script>
{app_shell_close(PAGE)}
</body>
</html>
"""


def build(data_dir: Path, docs_dir: Path) -> Path | None:
    report = load(data_dir)
    if report is None:
        print("Chưa có data/position_bridges/latest.json — bỏ qua.")
        return None
    write_stylesheet(docs_dir)
    out = docs_dir / PAGE
    write_page(out, render(report))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args()
    print("Wrote:", build(Path(args.data_dir), Path(args.docs_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
