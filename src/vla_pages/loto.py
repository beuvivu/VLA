from __future__ import annotations

"""Năm trang nhóm Lô tô: tần suất, tần suất cặp, cặp lớn, đầu đuôi, lô gan."""

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
    decimal_text,
    integer_text,
    number_text,
    read_csv_rows,
    read_json_rows,
)
from vla_design.shell import Crumb, Page
from vla_pages.common import PREDICTION_DISCLAIMER, write

CRUMB = (Crumb("Lô tô"),)


def _advanced(data_dir: Path, name: str):
    return read_json_rows(Path(data_dir) / "advanced" / name)


def build_frequency(docs_dir: Path, data_dir: Path) -> Path:
    """Tần suất lô tô trên cửa sổ 99 kỳ, đủ cả 100 con."""
    ds = _advanced(data_dir, "freq_99d.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có số liệu tần suất")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -(r.get("freq") or 0))
        total = sum(r.get("freq") or 0 for r in rows)
        top = rows[0] if rows else {}
        content = (
            kpi_row(
                (
                    kpi("Số con theo dõi", integer_text(len(rows)), note="đủ 00–99", tone="info"),
                    kpi("Tổng lượt về", integer_text(total), note="trong cửa sổ", tone="neutral"),
                    kpi("Về nhiều nhất", number_text(top.get("value")), note=f"{top.get('freq', 0)} lượt", tone="success"),
                    kpi("Trung bình mỗi con", decimal_text(total / len(rows) if rows else 0), note="lượt", tone="neutral"),
                )
            )
            + card(
                "Tần suất 99 kỳ",
                table(
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
                    caption="Tần suất của cả một trăm con trong 99 kỳ",
                    numeric=(1, 2, 3),
                ),
                note="Cả một trăm con, sắp theo lượt về giảm dần.",
                wide_body=True,
            )
            + source_note(ds)
        )
    page = Page(
        nav_key="tan-suat-loto",
        title="Tần suất lô tô",
        subtitle="Số lần về của từng con trong 99 kỳ gần nhất, kèm số kỳ có mặt và nháy tối đa.",
        crumbs=CRUMB,
        wide=True,
    )
    return write(docs_dir, "tan-suat-loto.html", page, disclaimer(PREDICTION_DISCLAIMER) + content)


def build_pair_frequency(docs_dir: Path, data_dir: Path) -> Path:
    """Tần suất cặp lộn — hai con là đảo chữ số của nhau."""
    ds = _advanced(data_dir, "reverse_pair_frequency_current.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có số liệu cặp")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -(r.get("freq") or 0))[:100]
        content = card(
            "Cặp lộn — kỳ gần nhất",
            table(
                (
                    ("cap", "Cặp"),
                    ("freq", "Tổng lượt"),
                    ("ngay", "Số kỳ có mặt"),
                    ("cung", "Số kỳ cùng về"),
                    ("tb", "Trung bình mỗi kỳ"),
                ),
                [
                    (
                        esc(r.get("pair")),
                        integer_text(r.get("freq")),
                        integer_text(r.get("days_hit")),
                        integer_text(r.get("cooccur_days")),
                        decimal_text(r.get("avg_per_draw")),
                    )
                    for r in rows
                ],
                caption="Một trăm cặp lộn có tổng lượt cao nhất",
                numeric=(1, 2, 3, 4),
            ),
            note="Cột 'Số kỳ cùng về' là số kỳ CẢ HAI con cùng xuất hiện — khác với tổng lượt.",
            wide_body=True,
        ) + source_note(ds)
    page = Page(
        nav_key="tan-suat-cap-loto",
        title="Tần suất cặp lô tô",
        subtitle="Cặp lộn: hai con là đảo chữ số của nhau. Tổng lượt, số kỳ có mặt và số kỳ cùng về.",
        crumbs=CRUMB,
        wide=True,
    )
    return write(docs_dir, "tan-suat-cap-loto.html", page, disclaimer(PREDICTION_DISCLAIMER) + content)


def build_big_pairs(docs_dir: Path, data_dir: Path) -> Path:
    """Năm mươi cặp lô tô, thống kê đồng hiện trên toàn lịch sử."""
    ds = read_csv_rows(Path(data_dir) / "pairs" / "cap_loto_50_stats_loto.csv")
    fallback = dataset_fallback(ds, empty_message="Chưa có số liệu cặp lớn")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -float(r.get("jaccard") or 0))
        content = card(
            "Năm mươi cặp — toàn lịch sử",
            table(
                (
                    ("cap", "Cặp"),
                    ("kieu", "Kiểu"),
                    ("ca", "Kỳ có ít nhất một"),
                    ("cahai", "Kỳ có cả hai"),
                    ("jaccard", "Jaccard"),
                    ("phi", "Hệ số phi"),
                ),
                [
                    (
                        esc(r.get("pair_id")),
                        esc(r.get("pair_kind")),
                        integer_text(r.get("pair_any_hit_days")),
                        integer_text(r.get("pair_both_hit_days")),
                        decimal_text(r.get("jaccard"), places=4),
                        decimal_text(r.get("phi"), places=4),
                    )
                    for r in rows
                ],
                caption="Năm mươi cặp lô tô sắp theo hệ số Jaccard",
                numeric=(2, 3, 4, 5),
            ),
            note=(
                "Hệ số phi gần 0 nghĩa là hai con độc lập với nhau. "
                "Đo trên toàn bộ lịch sử, phần lớn cặp nằm quanh 0 — đó là điều cần biết."
            ),
            wide_body=True,
        ) + source_note(ds)
    page = Page(
        nav_key="cap-lon-loto",
        title="Cặp lớn lô tô",
        subtitle="Thống kê đồng hiện của năm mươi cặp, tính trên toàn bộ lịch sử đã chốt.",
        crumbs=CRUMB,
        wide=True,
    )
    return write(docs_dir, "cap-lon-loto.html", page, disclaimer(PREDICTION_DISCLAIMER) + content)


def build_head_tail(docs_dir: Path, data_dir: Path) -> Path:
    """Đầu, đuôi và tổng của kỳ hiện tại, ba bảng cạnh nhau."""
    ds = _advanced(data_dir, "head_tail_total_loto_current.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có số liệu đầu đuôi")
    if fallback:
        content = fallback
    else:
        cards = []
        for kind, title in (("head", "Đầu"), ("tail", "Đuôi"), ("total", "Tổng")):
            subset = sorted(
                (r for r in ds.rows if r.get("group_type") == kind),
                key=lambda r: -(r.get("freq") or 0),
            )
            cards.append(
                '<div class="vla-col-4">'
                + card(
                    title,
                    table(
                        (("nhom", title), ("freq", "Lượt"), ("hang", "Hạng")),
                        [
                            (
                                esc(r.get("group_value")),
                                integer_text(r.get("freq")),
                                integer_text(r.get("rank_in_period_group")),
                            )
                            for r in subset
                        ],
                        caption=f"Phân bố theo {title.lower()}",
                        numeric=(1, 2),
                    ),
                    wide_body=True,
                )
                + "</div>"
            )
        content = f'<div class="vla-grid">{"".join(cards)}</div>' + source_note(ds)
    page = Page(
        nav_key="dau-duoi-loto",
        title="Đầu đuôi lô tô",
        subtitle="Phân bố theo chữ số đầu, chữ số cuối và tổng hai chữ số của kỳ gần nhất.",
        crumbs=CRUMB,
        wide=True,
    )
    return write(docs_dir, "dau-duoi-loto.html", page, disclaimer(PREDICTION_DISCLAIMER) + content)


def build_overdue(docs_dir: Path, data_dir: Path) -> Path:
    """Lô gan: số kỳ liên tiếp một con chưa về."""
    ds = _advanced(data_dir, "overdue.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có số liệu lô gan")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -(r.get("days_since_last") or 0))
        longest = rows[0] if rows else {}
        content = (
            kpi_row(
                (
                    kpi("Gan lâu nhất", number_text(longest.get("value")), note=f"{longest.get('days_since_last', 0)} kỳ", tone="warning"),
                    kpi("Lần cuối về", esc(longest.get("last_seen") or "—"), note="của con gan nhất", tone="neutral"),
                    kpi("Số con đang theo dõi", integer_text(len(rows)), note="đủ 00–99", tone="info"),
                    kpi(
                        "Gan trên 10 kỳ",
                        integer_text(sum(1 for r in rows if (r.get("days_since_last") or 0) >= 10)),
                        note="con",
                        tone="neutral",
                    ),
                )
            )
            + card(
                "Lô gan — cả một trăm con",
                table(
                    (("so", "Số"), ("gan", "Số kỳ chưa về"), ("lancuoi", "Lần cuối về")),
                    [
                        (
                            number_text(r.get("value")),
                            integer_text(r.get("days_since_last")),
                            esc(r.get("last_seen")),
                        )
                        for r in rows
                    ],
                    caption="Số kỳ chưa về của cả một trăm con",
                    numeric=(1,),
                ),
                note=(
                    "Một con gan lâu KHÔNG làm nó dễ về hơn ở kỳ sau. "
                    "Mỗi kỳ là một phép thử độc lập; bảng này mô tả quá khứ, không dự báo tương lai."
                ),
                wide_body=True,
            )
            + source_note(ds)
        )
    page = Page(
        nav_key="lo-gan",
        title="Lô gan",
        subtitle="Số kỳ liên tiếp một con chưa về, tính đến kỳ đã chốt gần nhất.",
        crumbs=CRUMB,
        wide=True,
    )
    return write(docs_dir, "lo-gan.html", page, disclaimer(PREDICTION_DISCLAIMER) + content)
