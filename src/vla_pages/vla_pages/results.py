from __future__ import annotations

"""Hai trang nhóm Kết quả: trực tiếp và sổ kết quả truyền thống."""

import csv
from pathlib import Path

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
from vla_design.data_access import Dataset, integer_text
from vla_design.shell import Crumb, Page
from vla_pages.common import write

#: Thứ tự giải và số ô mỗi giải, theo luật XSMB. Tổng đúng 27 ô, và con số 27
#: ấy chính là ràng buộc vật lý mà tầng thống kê dùng để chặn tổng biên.
PRIZE_LAYOUT: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("special", "Đặc Biệt", ("special",)),
    ("prize1", "Giải nhất", ("prize1",)),
    ("prize2", "Giải nhì", ("prize2_1", "prize2_2")),
    ("prize3", "Giải ba", tuple(f"prize3_{i}" for i in range(1, 7))),
    ("prize4", "Giải tư", tuple(f"prize4_{i}" for i in range(1, 5))),
    ("prize5", "Giải năm", tuple(f"prize5_{i}" for i in range(1, 7))),
    ("prize6", "Giải sáu", tuple(f"prize6_{i}" for i in range(1, 4))),
    ("prize7", "Giải bảy", tuple(f"prize7_{i}" for i in range(1, 5))),
)

PRIZE_SLOTS = sum(len(cols) for _, _, cols in PRIZE_LAYOUT)


def _read_draws(data_dir: Path, *, limit: int) -> tuple[Dataset, list[dict[str, str]]]:
    """Các kỳ MỚI NHẤT từ ``data/xsmb.csv``.

    Đọc ngược từ cuối thay vì nạp cả 4 212 hàng rồi cắt: tệp chỉ vài MB nên cả
    hai cách đều chạy được, nhưng cách này giữ chi phí không đổi khi lịch sử
    dài thêm.
    """
    path = Path(data_dir) / "xsmb.csv"
    if not path.exists():
        return Dataset("error", source="data/xsmb.csv", reason="không tìm thấy tệp"), []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        return Dataset("error", source="data/xsmb.csv", reason=f"không đọc được: {exc}"), []
    if not rows:
        return Dataset("empty", source="data/xsmb.csv"), []
    recent = rows[-limit:][::-1]
    return Dataset("ok", tuple(recent), source="data/xsmb.csv"), recent


def _two_digit(value: str) -> str:
    text = str(value or "").strip()
    return text[-2:].zfill(2) if text else "—"


def _board(draw: dict[str, str]) -> str:
    """Bảng giải của một kỳ, theo lối sổ truyền thống."""
    rows = []
    for _, label, columns in PRIZE_LAYOUT:
        values = " · ".join(str(draw.get(col) or "—") for col in columns)
        rows.append((label, values))
    return table(
        (("giai", "Giải"), ("so", "Số trúng")),
        rows,
        caption="Bảng giải của kỳ",
    )


def _digit_column(draw: dict[str, str], *, position: int, title: str) -> str:
    """Bảng Chục hoặc Đơn vị: gom hai số cuối của MỌI ô giải theo chữ số.

    ``position`` 0 là chữ số hàng chục, 1 là hàng đơn vị. Gom theo đúng tập 27
    ô giải, không theo một tập con — lấy thiếu ô là bảng nói sai về phân bố.
    """
    buckets: dict[str, list[str]] = {str(d): [] for d in range(10)}
    for _, _, columns in PRIZE_LAYOUT:
        for column in columns:
            pair = _two_digit(draw.get(column, ""))
            if pair == "—":
                continue
            buckets[pair[position]].append(pair[1 - position])
    rows = [(digit, " ".join(sorted(values)) if values else "—") for digit, values in buckets.items()]
    return table(
        (("chuso", title), ("so", "Các số")),
        rows,
        caption=f"Phân bố theo {title.lower()}",
    )


def build_traditional(docs_dir: Path, data_dir: Path) -> Path:
    """Sổ kết quả truyền thống — bố cục mục 6.1 của spec.

    Bảng kết quả chính BÊN TRÁI, Chục và Đơn vị cạnh nhau BÊN PHẢI. Xếp cả ba
    theo chiều dọc trên máy tính là bỏ phí chiều ngang và buộc người đọc cuộn
    để so ba thứ vốn phải nhìn cùng lúc.
    """
    ds, rows = _read_draws(data_dir, limit=30)
    fallback = dataset_fallback(ds, empty_message="Kho chưa có kỳ nào")
    if fallback:
        content = fallback
    else:
        latest = rows[0]
        history = table(
            (("ngay", "Ngày"), ("db", "Đặc Biệt"), ("g1", "Giải nhất")),
            [(esc(r.get("date")), esc(r.get("special")), esc(r.get("prize1"))) for r in rows],
            caption="Ba mươi kỳ gần nhất",
        )
        content = (
            disclaimer(
                "Trang này là KẾT QUẢ ĐÃ CHỐT, không phải dự đoán. "
                "Các bảng Chục và Đơn vị mô tả phân bố của chính kỳ đang xem; "
                "chúng không nói gì về kỳ tiếp theo."
            )
            + kpi_row(
                (
                    kpi("Kỳ đang xem", esc(latest.get("date")), note="mới nhất", tone="success"),
                    kpi("Giải Đặc Biệt", esc(latest.get("special")), note="đã chốt", tone="info"),
                    kpi("Số ô giải", integer_text(PRIZE_SLOTS), note="theo luật XSMB", tone="neutral"),
                    kpi("Kỳ trong bảng dưới", integer_text(len(rows)), note="gần nhất", tone="neutral"),
                )
            )
            + '<div class="vla-grid">'
            + f'<div class="vla-col-6">{card("Kết quả kỳ " + str(latest.get("date")), _board(latest), wide_body=True)}</div>'
            + f'<div class="vla-col-3">{card("Chục", _digit_column(latest, position=0, title="Chục"), wide_body=True)}</div>'
            + f'<div class="vla-col-3">{card("Đơn vị", _digit_column(latest, position=1, title="Đơn vị"), wide_body=True)}</div>'
            + f'<div class="vla-col-12">{card("Ba mươi kỳ gần nhất", history, wide_body=True)}</div>'
            + "</div>"
            + source_note(ds)
        )
    page = Page(
        nav_key="so-truyen-thong",
        title="Sổ kết quả truyền thống",
        subtitle="Bảng giải theo lối sổ giấy, kèm phân bố Chục và Đơn vị của cùng kỳ.",
        crumbs=(Crumb("Kết quả"),),
        wide=True,
    )
    return write(docs_dir, "so-ket-qua-truyen-thong.html", page, content)


def build_live(docs_dir: Path, data_dir: Path) -> Path:
    """Trang trực tiếp.

    KHÔNG gọi mạng. Giao diện cũ có một trang trực tiếp lấy dữ liệu từ nguồn
    ngoài; dựng lại nó ở đây sẽ là dựng một tính năng chưa có hợp đồng dữ liệu
    nào trong kho, và mục XVIII.2 cấm bịa. Trang này hiện kỳ đã chốt gần nhất
    và nói rõ nó KHÔNG phải luồng trực tiếp.
    """
    ds, rows = _read_draws(data_dir, limit=1)
    fallback = dataset_fallback(ds, empty_message="Kho chưa có kỳ nào")
    if fallback:
        body = fallback
    else:
        body = _board(rows[0])

    note = (
        "Trang này hiện KỲ ĐÃ CHỐT gần nhất trong kho, không phải luồng trực tiếp. "
        "Luồng trực tiếp cần một nguồn dữ liệu ngoài mà kho hiện chưa có hợp đồng; "
        "dựng một trang trông như trực tiếp mà không có nguồn là nói sai với người đọc."
    )
    content = (
        disclaimer(note)
        + '<div class="vla-grid">'
        + f'<div class="vla-col-8">{card("Kỳ đã chốt gần nhất", body, wide_body=True)}</div>'
        + f'<div class="vla-col-4">{card("Vì sao chưa có luồng trực tiếp", empty_state("Chưa nối nguồn trực tiếp", hint="Cần một hợp đồng dữ liệu cho kết quả đang về. Khi có, trang này sẽ đọc nó."))}</div>'
        + "</div>"
        + source_note(ds)
    )
    page = Page(
        nav_key="truc-tiep",
        title="Kết quả trực tiếp",
        subtitle="Kỳ đã chốt gần nhất trong kho.",
        crumbs=(Crumb("Kết quả"),),
    )
    return write(docs_dir, "live.html", page, content)
