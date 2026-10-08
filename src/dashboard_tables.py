"""Các bảng Dashboard có cột hữu hạn và hồ sơ kiểm chứng tách riêng."""

from __future__ import annotations

import html
from pathlib import Path

from lab_ui import lab_card
from lottery_codes import lottery_code
from ui_locale import column_label, localize_mapping_for_display, value_label
from ui_theme import dataframe_table, definition_table, raw_details, render_table


def dashboard_styles() -> str:
    return '<style id="app-dashboard-style">' + Path(__file__).with_name("templates").joinpath(
        "dashboard_tables.css"
    ).read_text(encoding="utf-8") + '</style>'


def _text(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value_label(value))


def _facts(items: list[tuple[str, object]]) -> str:
    return '<dl class="app-dash-facts">' + ''.join(
        f'<div><dt>{html.escape(label)}</dt><dd>{html.escape(_text(value))}</dd></div>'
        for label, value in items
    ) + '</dl>'


def _mark_table(table: str, kind: str) -> str:
    return table.replace('class="ui-table"', f'class="ui-table app-dash-table app-dash-{kind}"')


def _audit(payload: dict, *, metadata: dict | None = None) -> str:
    result = ""
    if metadata:
        result = ('<details class="app-dash-audit"><summary>Thông tin thẩm định và cấu hình</summary>'
                  + _mark_table(definition_table(localize_mapping_for_display(metadata)), "properties")
                  + '</details>')
    return '<div class="app-dash-proof">' + result + raw_details(payload) + '</div>'


def _caption(text: str) -> str:
    return f'<p class="app-dash-caption">{html.escape(text)}</p>'


def _channel(mode: str) -> str:
    return "LOTO" if mode == "loto" else "Đặc Biệt"


def forecast_card(frame, mode: str) -> str:
    """Giữ thứ tự và sáu chữ số thập phân của bảng xác suất hiện hành."""
    if frame.empty or not {"number", "prob"}.issubset(frame.columns):
        table = '<p class="ui-table-empty">Chưa có dữ liệu.</p>'
    else:
        view = frame[["number", "prob"]].copy()
        view["number"] = view["number"].map(lottery_code)
        view["prob"] = view["prob"].astype(float).map(lambda value: f"{value:.6f}")
        view = view.rename(columns=column_label)
        view.insert(0, "#", range(1, len(view) + 1))
        table = _mark_table(dataframe_table(view, align=["right", "left", "right"], key_column=1), "ranking")
    note = ("Xác suất xuất hiện ít nhất một lần trong kỳ." if mode == "loto"
            else "Xác suất của hai chữ số cuối giải Đặc Biệt.")
    return lab_card(_caption(note) + table,
                    title=f"Xác suất {_channel(mode)} cao nhất", span=6,
                    aside=f'<span class="app-dash-tag">{len(frame)} ứng viên</span>',
                    ident=f"app-lab-{mode}")


def picks_card(payload: dict, mode: str) -> str:
    rows = []
    for count in (4, 8, 10):
        numbers = payload.get(f"top{count}")
        chips = ' '.join(f'<span class="app-dash-code">{html.escape(lottery_code(number))}</span>'
                        for number in numbers) if isinstance(numbers, list) else ''
        rows.append(f'<tr><td class="app-dash-pick-label">Top {count}</td>'
                    f'<td><div class="app-dash-codes">{chips or "Chưa có dữ liệu"}</div></td></tr>')
    table = (f'<div class="ui-table-wrap"><table class="ui-table app-dash-table app-dash-picks" data-picks-mode="{mode}">'
             '<thead><tr><th scope="col">Nhóm</th><th scope="col">Các số theo thứ tự công bố</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    online = payload.get("online") or {}
    status = {"shadow": "Theo dõi đối chứng", "active": "Đang áp dụng"}.get(online.get("status"), "—")
    meta = payload.get("meta") or {}
    active = meta.get("active")
    stacked = "Đang áp dụng" if active is True else "Chưa áp dụng" if active is False else "—"
    body = _facts([("Kỳ dự báo", payload.get("target_date")), ("Ngày dữ liệu neo", payload.get("anchor_date"))])
    body += table + _facts([("Mô hình xếp chồng", stacked), ("Học trực tuyến", status),
                           ("Kỳ đã chốt", online.get("n_settled"))]) + _audit(payload)
    return lab_card(body, title=f"Danh sách gợi ý ({_channel(mode)})", span=6,
                    ident="app-lab-picks" if mode == "loto" else "app-dash-picks-de")


def weights_card(payload: dict, mode: str) -> str:
    weights = payload.get("weights") or {}
    labels = {"w_active": "Cầu đang chạy", "w_stable": "Cầu ổn định", "w_ml": "Học máy",
              "w_cau": "Cầu-kèo AI/ML", "w_stat": "Thống kê"}
    rows = [(labels.get(key, column_label(key)), _text(value)) for key, value in weights.items()]
    table = _mark_table(render_table(["Thành phần", "Trọng số"], rows,
                                    align=["left", "right"]), "weights")
    metadata = {key: value for key, value in payload.items() if key not in {"weights", "mode"}}
    body = _caption(payload.get("nguon", "Chưa có thông tin xuất xứ")) + table + _audit(payload, metadata=metadata)
    return lab_card(body, title=f"Trọng số ({_channel(mode)})", span=6,
                    ident="app-lab-weights" if mode == "loto" else "app-dash-weights-de")


def calibration_card(payload: dict, mode: str) -> str:
    params = payload.get("params") or {}
    labels = {"a": "Hệ số a", "b": "Độ lệch b", "temperature": "Nhiệt độ hiệu chỉnh"}
    rows = [(label, _text(params.get(key))) for key, label in labels.items()]
    selection = payload.get("selection") or {}
    chosen = selection.get("chosen")
    method = "Giữ nguyên xác suất" if chosen == "identity" else _text(chosen)
    body = _facts([("Phương pháp được chọn", method), ("Số ngày huấn luyện", selection.get("fit_days")),
                   ("Số ngày kiểm định riêng", selection.get("holdout_days"))])
    body += _mark_table(render_table(["Tham số", "Giá trị"], rows, align=["left", "right"]), "calibration")
    body += _audit(payload, metadata={key: value for key, value in payload.items() if key != "params"})
    return lab_card(body, title=f"Hiệu chỉnh ({_channel(mode)})", span=6,
                    ident=f"app-dash-calibration-{mode}")


def dashboard_group(index: int, title: str, note: str, cards: str) -> str:
    return (f'<section class="app-dash-group" aria-label="{html.escape(title)}">'
            f'<header class="app-dash-group-head"><span>{index:02d}</span><div><h2>{html.escape(title)}</h2>'
            f'<p>{html.escape(note)}</p></div></header><div class="ui-grid ai-signal-grid">{cards}</div></section>')
