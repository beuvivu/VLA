from __future__ import annotations

"""Bốn trang nhóm Tổng quan: trang chủ, bảng điều khiển, thống kê, tổng hợp."""

from pathlib import Path
from typing import Any

from vla_design.blocks import (
    card,
    dataset_fallback,
    disclaimer,
    empty_state,
    esc,
    kpi,
    kpi_row,
    source_note,
    table,
)
from vla_design.data_access import (
    first,
    integer_text,
    number_text,
    percent_text,
    read_json_object,
    read_json_rows,
)
from vla_design.navigation import NAV
from vla_design.shell import Crumb, Page
from vla_design.ensemble_view import weights_card
from vla_pages.common import PREDICTION_DISCLAIMER, health, latest_prediction_csv, write


def _pred_rows(data_dir: Path) -> Any:
    return read_json_object(Path(data_dir) / "predictions_today.json")


def build_index(docs_dir: Path, data_dir: Path) -> Path:
    """Trang chủ: cửa vào, chỉ ra từng nhánh, không cố nhồi mọi thứ."""
    hb = health(data_dir)
    h = first(hb)
    kpis = kpi_row(
        (
            kpi("Số kỳ trong kho", integer_text(h.get("row_count")), note="dữ liệu thật", tone="info"),
            kpi("Kỳ mới nhất", esc(h.get("latest_date") or "—"), note="đã chốt", tone="success"),
            kpi("Kỳ đầu tiên", esc(h.get("first_date") or "—"), note="lịch sử", tone="neutral"),
            kpi(
                "Ngày thiếu",
                integer_text(h.get("missing_count")),
                note="liên tục" if not h.get("missing_count") else "có lỗ hổng",
                tone="success" if not h.get("missing_count") else "danger",
            ),
        )
    )
    fallback = dataset_fallback(hb, empty_message="Kho chưa có kỳ nào")
    if fallback:
        kpis = fallback

    groups = "".join(
        '<li class="vla-nav-card">'
        f'<a href="{esc(group.items[0].href)}"><strong>{esc(group.label)}</strong>'
        f'<span>{len(group.items)} trang</span></a></li>'
        for group in NAV
        if group.key != "tong-quan"
    )

    content = (
        disclaimer(PREDICTION_DISCLAIMER)
        + kpis
        + '<div class="vla-grid">'
        + '<div class="vla-col-12">'
        + card(
            "Các nhánh phân tích",
            f'<ul class="vla-nav-card-list">{groups}</ul>',
            note="Mỗi nhánh mở ra các bảng thống kê riêng của nó.",
        )
        + "</div></div>"
        + source_note(hb)
    )
    page = Page(
        nav_key="trang-chu",
        title="Phân tích XSMB",
        subtitle="Thống kê mô tả và nghiên cứu xác suất trên dữ liệu lịch sử xổ số miền Bắc.",
    )
    return write(docs_dir, "index.html", page, content)


def build_dashboard(docs_dir: Path, data_dir: Path) -> Path:
    """Bảng điều khiển: dự đoán kỳ tới và trọng số đang hiệu lực."""
    pb = _pred_rows(data_dir)
    payload = first(pb)
    hb = health(data_dir)

    fallback = dataset_fallback(pb, empty_message="Chưa có dự đoán cho kỳ tới")
    if fallback:
        body = fallback
    else:
        loto = payload.get("top_lo_to") or []
        rows = [
            (
                index + 1,
                number_text(item.get("number")),
                percent_text(item.get("probability"), places=3),
                percent_text(item.get("baseline"), places=3),
            )
            for index, item in enumerate(loto[:10])
        ]
        body = (
            table(
                (("hang", "#"), ("so", "Số"), ("xacsuat", "Xác suất mô hình"), ("coso", "Đường cơ sở")),
                rows,
                caption="Mười số lô tô có xác suất mô hình cao nhất cho kỳ tới",
                numeric=(0, 2, 3),
            )
            if rows
            else empty_state("Chưa có danh sách lô tô cho kỳ tới")
        )

    # Xác suất từng số đọc từ bảng dự đoán thật, không từ `top_numbers` (danh
    # sách ấy chỉ có số, không có xác suất). Hai cột xác suất đặt cạnh nhau là
    # cố ý: chênh lệch giữa mô hình và đường cơ sở MỚI là thông tin, còn một
    # cột xác suất đứng một mình trông như một khẳng định.
    de_ds = latest_prediction_csv(data_dir, "de")
    de_fallback = dataset_fallback(de_ds, empty_message="Chưa có bảng xác suất Đặc Biệt")
    de_base = (payload.get("top_dac_biet") or {}).get("baseline")
    if de_fallback:
        de_body = de_fallback
    else:
        top = sorted(de_ds.rows, key=lambda r: -float(r.get("prob") or 0))[:10]
        de_body = table(
            (("hang", "#"), ("so", "Số"), ("xacsuat", "Xác suất mô hình"), ("coso", "Đường cơ sở")),
            [
                (
                    i + 1,
                    number_text(r.get("number")),
                    percent_text(r.get("prob"), places=3),
                    percent_text(de_base, places=3),
                )
                for i, r in enumerate(top)
            ],
            caption="Mười số Đặc Biệt có xác suất mô hình cao nhất",
            numeric=(0, 2, 3),
        )

    groups = payload.get("top_dac_biet") or {}
    cham, tong = groups.get("cham") or [], groups.get("tong") or []
    group_body = (
        '<dl class="vla-meta">'
        f'<div><dt>Chạm</dt><dd>{esc(" · ".join(str(c) for c in cham)) if cham else "—"}</dd></div>'
        f'<div><dt>Tổng</dt><dd>{esc(" · ".join(str(t) for t in tong)) if tong else "—"}</dd></div>'
        f'<div><dt>Dàn 36</dt><dd>{esc(len(groups.get("dan_36") or []))} số</dd></div>'
        f'<div><dt>Dàn 64</dt><dd>{esc(len(groups.get("dan_64") or []))} số</dd></div>'
        "</dl>"
    )

    target = esc(payload.get("date") or "—")
    kpis = kpi_row(
        (
            kpi("Kỳ dự đoán", target, note="chưa mở", tone="info"),
            kpi("Kỳ neo", esc(first(hb).get("latest_date") or "—"), note="đã chốt", tone="success"),
            kpi("Số lô tô liệt kê", integer_text(len(payload.get("top_lo_to") or [])), note="mô hình", tone="neutral"),
            kpi("Cầu đang hoạt động", integer_text(len(payload.get("active_bridges") or [])), note="sau ba cổng", tone="neutral"),
        )
    )

    content = (
        disclaimer(PREDICTION_DISCLAIMER)
        + kpis
        + '<div class="vla-grid">'
        + f'<div class="vla-col-7">{card("Lô tô — kỳ tới", body, wide_body=True)}</div>'
        + f'<div class="vla-col-5">{card("Đặc Biệt — kỳ tới", de_body, wide_body=True)}</div>'
        + f'<div class="vla-col-12">{card("Nhóm Đặc Biệt gợi ý", group_body, note="Chạm và tổng là nhóm thu hẹp, không phải dự đoán một con.")}</div>'
        + f'<div class="vla-col-12">{weights_card(data_dir)}</div>'
        + "</div>"
        + source_note(pb, hb, de_ds)
    )
    page = Page(
        nav_key="bang-dieu-khien",
        title="Bảng điều khiển",
        subtitle="Dự đoán kỳ tới, trọng số tổ hợp đang có hiệu lực, và xuất xứ của chúng.",
        crumbs=(Crumb("Tổng quan"),),
    )
    return write(docs_dir, "dashboard.html", page, content)


def _freq_card(data_dir: Path, name: str, title: str, caption: str) -> tuple[str, Any]:
    ds = read_json_rows(Path(data_dir) / "advanced" / name)
    fallback = dataset_fallback(ds, empty_message="Chưa có số liệu tần suất")
    if fallback:
        return card(title, fallback), ds
    rows = sorted(ds.rows, key=lambda r: -(r.get("freq") or 0))[:20]
    body = table(
        (("so", "Số"), ("freq", "Lượt về"), ("days", "Số kỳ có mặt"), ("nhay", "Nháy tối đa")),
        [
            (
                number_text(r.get("value")),
                integer_text(r.get("freq")),
                integer_text(r.get("days_hit")),
                integer_text(r.get("max_nhay")),
            )
            for r in rows
        ],
        caption=caption,
        numeric=(1, 2, 3),
    )
    return card(title, body, wide_body=True), ds


def build_statistics(docs_dir: Path, data_dir: Path) -> Path:
    """Bảng thống kê: tần suất và số kỳ chưa về, hai bảng cạnh nhau."""
    freq_card, freq_ds = _freq_card(
        data_dir, "freq_99d.json", "Tần suất 99 kỳ gần nhất", "Hai mươi số về nhiều nhất trong 99 kỳ"
    )
    over = read_json_rows(Path(data_dir) / "advanced" / "overdue.json")
    over_fallback = dataset_fallback(over, empty_message="Chưa có số liệu lô gan")
    if over_fallback:
        over_card = card("Lâu chưa về", over_fallback)
    else:
        rows = sorted(over.rows, key=lambda r: -(r.get("days_since_last") or 0))[:20]
        over_card = card(
            "Lâu chưa về",
            table(
                (("so", "Số"), ("ngay", "Số kỳ chưa về"), ("lan", "Lần cuối")),
                [
                    (number_text(r.get("value")), integer_text(r.get("days_since_last")), esc(r.get("last_seen")))
                    for r in rows
                ],
                caption="Hai mươi số có số kỳ chưa về lớn nhất",
                numeric=(1,),
            ),
            wide_body=True,
        )

    content = (
        disclaimer(PREDICTION_DISCLAIMER)
        + '<div class="vla-grid">'
        + f'<div class="vla-col-6">{freq_card}</div>'
        + f'<div class="vla-col-6">{over_card}</div>'
        + "</div>"
        + source_note(freq_ds, over)
    )
    page = Page(
        nav_key="thong-ke",
        title="Bảng thống kê",
        subtitle="Tần suất và khoảng cách giữa hai lần về, tính trên toàn bộ lịch sử đã chốt.",
        crumbs=(Crumb("Tổng quan"),),
        wide=True,
    )
    return write(docs_dir, "statistics.html", page, content)


def build_summary(docs_dir: Path, data_dir: Path) -> Path:
    """Thống kê tổng hợp: đầu, đuôi, tổng — ba bảng một trang."""
    cards: list[str] = []
    sources = []
    for name, title, caption in (
        ("head_20d.json", "Đầu — 20 kỳ", "Phân bố theo chữ số đầu trong 20 kỳ"),
        ("tail_20d.json", "Đuôi — 20 kỳ", "Phân bố theo chữ số cuối trong 20 kỳ"),
        ("total_20d.json", "Tổng — 20 kỳ", "Phân bố theo tổng hai chữ số trong 20 kỳ"),
    ):
        ds = read_json_rows(Path(data_dir) / "advanced" / name)
        sources.append(ds)
        fallback = dataset_fallback(ds, empty_message="Chưa có số liệu")
        if fallback:
            cards.append(f'<div class="vla-col-4">{card(title, fallback)}</div>')
            continue
        key = next((k for k in ("head", "tail", "total", "value", "group_value") if k in ds.rows[0]), None)
        freq_key = next((k for k in ("freq", "count") if k in ds.rows[0]), None)
        rows = [
            (esc(r.get(key)), integer_text(r.get(freq_key)))
            for r in sorted(ds.rows, key=lambda r: -(r.get(freq_key) or 0))
        ]
        cards.append(
            '<div class="vla-col-4">'
            + card(title, table((("nhom", "Nhóm"), ("freq", "Lượt")), rows, caption=caption, numeric=(1,)), wide_body=True)
            + "</div>"
        )

    content = (
        disclaimer(PREDICTION_DISCLAIMER)
        + f'<div class="vla-grid">{"".join(cards)}</div>'
        + source_note(*sources)
    )
    page = Page(
        nav_key="thong-ke-tong-hop",
        title="Thống kê tổng hợp",
        subtitle="Đầu, đuôi và tổng hai chữ số, gom trên hai mươi kỳ gần nhất.",
        crumbs=(Crumb("Tổng quan"),),
        wide=True,
    )
    return write(docs_dir, "thong-ke-tong-hop.html", page, content)
