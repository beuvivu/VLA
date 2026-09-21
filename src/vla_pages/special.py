from __future__ import annotations

"""Tám trang nhóm Đặc Biệt.

Quy tắc thuật ngữ của mục IX áp triệt để ở đây: mọi nhãn hiển thị viết "Đặc
Biệt", trong khi tên tệp dữ liệu (``special_*``, ``cycle_de.csv``,
``period_matrix_de_*``) và khoá kỹ thuật (``mode="de"``) giữ nguyên.
"""

import csv
from pathlib import Path

from vla_design.blocks import (
    card,
    dataset_fallback,
    disclaimer,
    esc,
    kpi,
    kpi_row,
    source_note,
    table,
)
from vla_design.data_access import (
    Dataset,
    decimal_text,
    epoch_ms_text,
    integer_text,
    number_text,
    percent_text,
    read_csv_rows,
    read_json_rows,
)
from vla_design.shell import Crumb, Page
from vla_pages.common import PREDICTION_DISCLAIMER, latest_prediction_csv, write

CRUMB = (Crumb("Đặc Biệt"),)


def _advanced(data_dir: Path, name: str) -> Dataset:
    return read_json_rows(Path(data_dir) / "advanced" / name)


def _page(nav_key: str, title: str, subtitle: str, filename: str, content: str, docs_dir: Path) -> Path:
    page = Page(
        nav_key=nav_key, title=title, subtitle=subtitle, crumbs=CRUMB, wide=True
    )
    return write(docs_dir, filename, page, disclaimer(PREDICTION_DISCLAIMER) + content)


def build_board(docs_dir: Path, data_dir: Path) -> Path:
    """Bảng Đặc Biệt theo ngày, đọc thẳng từ lịch sử đã chốt."""
    path = Path(data_dir) / "xsmb.csv"
    if not path.exists():
        content = dataset_fallback(
            Dataset("error", source="data/xsmb.csv", reason="không tìm thấy tệp"),
            empty_message="Kho chưa có kỳ nào",
        )
        ds = Dataset("error", source="data/xsmb.csv")
    else:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))[-180:][::-1]
        ds = Dataset("ok", tuple(rows), source="data/xsmb.csv")
        content = card(
            "Một trăm tám mươi kỳ gần nhất",
            table(
                (("ngay", "Ngày"), ("db", "Giải Đặc Biệt"), ("haiso", "Hai số cuối")),
                [
                    (esc(r.get("date")), esc(r.get("special")), esc(str(r.get("special") or "")[-2:].zfill(2)))
                    for r in rows
                ],
                caption="Giải Đặc Biệt của 180 kỳ gần nhất",
            ),
            wide_body=True,
        ) + source_note(ds)
    return _page(
        "bang-dac-biet",
        "Bảng Đặc Biệt",
        "Giải Đặc Biệt theo từng kỳ, kèm hai số cuối — phần duy nhất mô hình ước lượng.",
        "bang-dac-biet.html",
        content,
        docs_dir,
    )


def build_month_board(docs_dir: Path, data_dir: Path) -> Path:
    """Bảng Đặc Biệt gom theo tháng: hàng là tháng, cột là ngày trong tháng."""
    ds = _advanced(data_dir, "special_month_board.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có bảng theo tháng")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: str(r.get("month_key")), reverse=True)[:24]
        days = [f"{d:02d}" for d in range(1, 32)]
        columns = (("thang", "Tháng"), *((d, d) for d in days))
        content = card(
            "Hai mươi tư tháng gần nhất",
            table(
                columns,
                [(esc(r.get("month_key")), *(esc(r.get(d) or "—") for d in days)) for r in rows],
                caption="Hai số cuối của giải Đặc Biệt theo tháng và ngày",
                numeric=tuple(range(1, len(days) + 1)),
            ),
            note="Ô trống là ngày không có kỳ quay, ví dụ nghỉ Tết.",
            wide_body=True,
        ) + source_note(ds)
    return _page(
        "bang-dac-biet-thang",
        "Bảng Đặc Biệt theo tháng",
        "Hai số cuối của giải Đặc Biệt, xếp theo tháng và ngày trong tháng.",
        "bang-dac-biet-thang.html",
        content,
        docs_dir,
    )


def build_year_frequency(docs_dir: Path, data_dir: Path) -> Path:
    """Tần suất Đặc Biệt theo năm."""
    ds = _advanced(data_dir, "special_year_frequency.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có tần suất theo năm")
    if fallback:
        content = fallback
    else:
        years = sorted({str(r.get("period_key")) for r in ds.rows}, reverse=True)
        latest = years[0] if years else ""
        subset = sorted(
            (r for r in ds.rows if str(r.get("period_key")) == latest),
            key=lambda r: -(r.get("freq") or 0),
        )
        content = (
            kpi_row(
                (
                    kpi("Năm đang xem", esc(latest or "—"), note="mới nhất", tone="info"),
                    kpi("Số năm có dữ liệu", integer_text(len(years)), note="trong kho", tone="neutral"),
                    kpi(
                        "Về nhiều nhất",
                        number_text(subset[0].get("number")) if subset else "—",
                        note=f"{subset[0].get('freq', 0) if subset else 0} lượt",
                        tone="success",
                    ),
                    kpi("Số con có mặt", integer_text(len(subset)), note=f"trong {latest}", tone="neutral"),
                )
            )
            + card(
                f"Tần suất Đặc Biệt — năm {latest}",
                table(
                    (("so", "Số"), ("freq", "Lượt về"), ("hang", "Hạng trong năm")),
                    [
                        (
                            esc(r.get("number_str") or number_text(r.get("number"))),
                            integer_text(r.get("freq")),
                            integer_text(r.get("rank_in_period")),
                        )
                        for r in subset
                    ],
                    caption=f"Tần suất hai số cuối của giải Đặc Biệt trong năm {latest}",
                    numeric=(1, 2),
                ),
                wide_body=True,
            )
            + source_note(ds)
        )
    return _page(
        "bang-dac-biet-nam",
        "Bảng Đặc Biệt theo năm",
        "Tần suất hai số cuối của giải Đặc Biệt, gom theo năm.",
        "bang-dac-biet-nam.html",
        content,
        docs_dir,
    )


def build_bridge(docs_dir: Path, data_dir: Path) -> Path:
    """Cầu giải Đặc Biệt: số kỳ này theo sau số kỳ trước."""
    ds = _advanced(data_dir, "conditional_special_after_special_top500.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có bảng cầu")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -(r.get("conditional_rate") or 0))[:200]
        content = card(
            "Hai trăm cặp có tỉ lệ điều kiện cao nhất",
            table(
                (
                    ("truoc", "Kỳ trước"),
                    ("sau", "Kỳ sau"),
                    ("lan", "Số lần"),
                    ("nen", "Số kỳ nền"),
                    ("tile", "Tỉ lệ điều kiện"),
                ),
                [
                    (
                        esc(r.get("prev_special_2d")),
                        esc(r.get("next_special_2d")),
                        integer_text(r.get("count")),
                        integer_text(r.get("base_count")),
                        percent_text(r.get("conditional_rate")),
                    )
                    for r in rows
                ],
                caption="Tỉ lệ số kỳ sau xuất hiện, với điều kiện số kỳ trước",
                numeric=(2, 3, 4),
            ),
            note=(
                "Tỉ lệ cao trên một số kỳ nền NHỎ không phải bằng chứng. "
                "Với 100 × 100 cặp, một vài tỉ lệ cao là điều chắc chắn xảy ra ngay cả khi "
                "hai kỳ liên tiếp hoàn toàn độc lập — hãy đọc cột 'Số kỳ nền' trước cột tỉ lệ."
            ),
            wide_body=True,
        ) + source_note(ds)
    return _page(
        "cau-dac-biet",
        "Cầu giải Đặc Biệt",
        "Tỉ lệ có điều kiện giữa hai số Đặc Biệt của hai kỳ liền nhau.",
        "cau-giai-dac-biet.html",
        content,
        docs_dir,
    )


def build_group_bridge(docs_dir: Path, data_dir: Path) -> Path:
    """Cầu Đặc Biệt theo bộ số: chạm, đầu, đuôi, tổng."""
    ds = _advanced(data_dir, "special_group_frequency_current.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có số liệu bộ số")
    if fallback:
        content = fallback
    else:
        labels = {"db_cham": "Chạm", "db_head": "Đầu", "db_tail": "Đuôi", "db_total": "Tổng"}
        cards = []
        for kind, title in labels.items():
            subset = sorted(
                (r for r in ds.rows if r.get("group_type") == kind),
                key=lambda r: -(r.get("freq") or 0),
            )
            if not subset:
                continue
            cards.append(
                '<div class="vla-col-3">'
                + card(
                    title,
                    table(
                        (("nhom", title), ("freq", "Lượt")),
                        [(esc(r.get("group_value")), integer_text(r.get("freq"))) for r in subset],
                        caption=f"Phân bố Đặc Biệt theo {title.lower()}",
                        numeric=(1,),
                    ),
                    wide_body=True,
                )
                + "</div>"
            )
        content = f'<div class="vla-grid">{"".join(cards)}</div>' + source_note(ds)
    return _page(
        "cau-dac-biet-bo-so",
        "Cầu Đặc Biệt theo bộ số",
        "Giải Đặc Biệt nhóm theo chạm, đầu, đuôi và tổng hai chữ số.",
        "cau-dac-biet-theo-bo-so.html",
        content,
        docs_dir,
    )


def build_cycle(docs_dir: Path, data_dir: Path) -> Path:
    """Chu kỳ Đặc Biệt: khoảng cách giữa hai lần về của cùng một số."""
    ds = read_csv_rows(Path(data_dir) / "cycle" / "cycle_de.csv")
    fallback = dataset_fallback(ds, empty_message="Chưa có số liệu chu kỳ")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -float(r.get("current_gap") or 0))
        unit = str(rows[0].get("gap_unit") or "") if rows else ""
        content = card(
            "Chu kỳ của cả một trăm con",
            table(
                (
                    ("so", "Số"),
                    ("lan", "Số lần về"),
                    ("hientai", "Khoảng hiện tại"),
                    ("toida", "Khoảng lớn nhất"),
                    ("tb", "Khoảng trung bình"),
                    ("trungvi", "Trung vị"),
                    ("cuoi", "Lần cuối"),
                ),
                [
                    (
                        esc(str(r.get("number")).zfill(2)),
                        integer_text(r.get("count")),
                        integer_text(r.get("current_gap")),
                        integer_text(r.get("max_gap")),
                        decimal_text(r.get("mean_gap")),
                        decimal_text(r.get("median_gap")),
                        esc(r.get("last_seen")),
                    )
                    for r in rows
                ],
                caption="Khoảng cách giữa hai lần về của từng số Đặc Biệt",
                numeric=(1, 2, 3, 4, 5),
            ),
            note=f"Đơn vị khoảng cách: {esc(unit)}. Khoảng trung bình lớn KHÔNG khiến một con 'đến hạn'.",
            wide_body=True,
        ) + source_note(ds)
    return _page(
        "chu-ky-dac-biet",
        "Chu kỳ Đặc Biệt",
        "Khoảng cách giữa hai lần về của cùng một số, tính trên toàn bộ lịch sử.",
        "chu-ky-dac-biet.html",
        content,
        docs_dir,
    )


def build_by_total(docs_dir: Path, data_dir: Path) -> Path:
    """Đặc Biệt theo tổng, kèm số kỳ chưa về của từng tổng và từng chạm."""
    total_ds = _advanced(data_dir, "special_total_overdue.json")
    cham_ds = _advanced(data_dir, "special_cham_overdue.json")
    cards = []
    for ds, title, key, label in (
        (total_ds, "Tổng — lâu chưa về", "total", "Tổng"),
        (cham_ds, "Chạm — lâu chưa về", "digit", "Chạm"),
    ):
        fallback = dataset_fallback(ds, empty_message="Chưa có số liệu")
        if fallback:
            cards.append(f'<div class="vla-col-6">{card(title, fallback)}</div>')
            continue
        rows = sorted(ds.rows, key=lambda r: -(r.get("days_since_last") or 0))
        cards.append(
            '<div class="vla-col-6">'
            + card(
                title,
                table(
                    ((key, label), ("gan", "Số kỳ chưa về"), ("cuoi", "Lần cuối")),
                    [
                        (
                            esc(r.get(key)),
                            integer_text(r.get("days_since_last")),
                            epoch_ms_text(r.get("last_seen")),
                        )
                        for r in rows
                    ],
                    caption=f"Số kỳ chưa về theo {label.lower()}",
                    numeric=(1,),
                ),
                wide_body=True,
            )
            + "</div>"
        )
    content = f'<div class="vla-grid">{"".join(cards)}</div>' + source_note(total_ds, cham_ds)
    return _page(
        "dac-biet-theo-tong",
        "Đặc Biệt theo tổng",
        "Giải Đặc Biệt nhóm theo tổng hai chữ số và theo chạm, kèm số kỳ chưa về.",
        "giai-dac-biet-theo-tong.html",
        content,
        docs_dir,
    )


def build_tomorrow(docs_dir: Path, data_dir: Path) -> Path:
    """Đặc Biệt kỳ tới: xác suất từng số, đặt cạnh đường cơ sở."""
    ds = latest_prediction_csv(data_dir, "de")
    fallback = dataset_fallback(ds, empty_message="Chưa có bảng xác suất cho kỳ tới")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -float(r.get("prob") or 0))
        base = 0.01
        content = (
            kpi_row(
                (
                    kpi("Số con xếp hạng", integer_text(len(rows)), note="đủ 00–99", tone="info"),
                    kpi("Xác suất cao nhất", percent_text(rows[0].get("prob"), places=3) if rows else "—", note="của con đứng đầu", tone="neutral"),
                    kpi("Đường cơ sở", percent_text(base, places=3), note="chia đều 100 con", tone="neutral"),
                    kpi(
                        "Chênh so cơ sở",
                        percent_text(float(rows[0].get("prob") or 0) - base, places=3) if rows else "—",
                        note="tuyệt đối",
                        tone="neutral",
                    ),
                )
            )
            + card(
                "Xác suất mô hình — cả một trăm con",
                table(
                    (("so", "Số"), ("xacsuat", "Xác suất mô hình"), ("coso", "Đường cơ sở"), ("chenh", "Chênh lệch")),
                    [
                        (
                            esc(r.get("number_str") or number_text(r.get("number"))),
                            percent_text(r.get("prob"), places=3),
                            percent_text(base, places=3),
                            percent_text(float(r.get("prob") or 0) - base, places=3),
                        )
                        for r in rows
                    ],
                    caption="Xác suất mô hình của cả một trăm số Đặc Biệt cho kỳ tới",
                    numeric=(1, 2, 3),
                ),
                note=(
                    "Cột 'Chênh lệch' mới là thông tin. Một xác suất 1,006% cạnh đường cơ sở 1,000% "
                    "nghĩa là mô hình gần như không phân biệt được con nào với con nào."
                ),
                wide_body=True,
            )
            + source_note(ds)
        )
    return _page(
        "dac-biet-ngay-mai",
        "Đặc Biệt kỳ tới",
        "Xác suất mô hình cho từng số Đặc Biệt ở kỳ chưa mở, đặt cạnh đường cơ sở.",
        "giai-db-ngay-mai.html",
        content,
        docs_dir,
    )
