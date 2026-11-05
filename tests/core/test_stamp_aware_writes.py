"""Lượt pipeline chạy lại trên cùng dữ liệu không được ghi lại tệp chỉ để đổi giờ dựng hay giờ lưu.

Ngày 05-11-2026 lượt chạy lại (theo push khi gộp một PR) ghi lại 15 trang chỉ đổi «Dựng lúc …» và ba
tệp xlsx chỉ đổi ``docProps/core.xml``, rồi commit cả loạt vào kho.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook

from core.atomic_io import save_xlsx, write_text_unless_only_stamps, xlsx_payload_equal

STAMP = (re.compile(r"Dựng lúc \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"),)


def test_a_text_that_differs_only_by_its_build_stamp_keeps_the_existing_file(tmp_path: Path) -> None:
    page = tmp_path / "trang.html"
    assert write_text_unless_only_stamps(page, "<p>12 · Dựng lúc 2026-11-05T11:38:57Z.</p>", STAMP)
    assert not write_text_unless_only_stamps(page, "<p>12 · Dựng lúc 2026-11-05T12:32:58Z.</p>", STAMP)
    assert page.read_text(encoding="utf-8") == "<p>12 · Dựng lúc 2026-11-05T11:38:57Z.</p>"
    # Nội dung đổi thật: ghi, kèm giờ mới.
    assert write_text_unless_only_stamps(page, "<p>13 · Dựng lúc 2026-11-05T12:32:58Z.</p>", STAMP)
    assert page.read_text(encoding="utf-8") == "<p>13 · Dựng lúc 2026-11-05T12:32:58Z.</p>"
    # Không có mẫu dấu giờ nào thì mọi khác biệt đều là nội dung.
    assert write_text_unless_only_stamps(page, "<p>13 · Dựng lúc 2026-11-06T00:00:00Z.</p>", ())


def _utc(*parts: int) -> datetime:
    """openpyxl lưu giờ UTC không múi."""
    return datetime(*parts, tzinfo=UTC).replace(tzinfo=None)


def _workbook(value: int, created: datetime) -> Workbook:
    wb = Workbook()
    wb.active["A1"] = value
    wb.properties.created = created
    return wb


def test_a_workbook_whose_cells_did_not_change_is_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "xsmb.xlsx"
    assert save_xlsx(_workbook(7, _utc(2026, 11, 5, 11, 38)), path)
    before = path.read_bytes()
    # Cùng ô, giờ lưu khác: docProps/core.xml khác nhưng tệp giữ nguyên từng byte.
    assert not save_xlsx(_workbook(7, _utc(2026, 11, 5, 12, 32)), path)
    assert path.read_bytes() == before
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".")], "không để lại tệp tạm"
    # Ô đổi: ghi tệp mới.
    assert save_xlsx(_workbook(8, _utc(2026, 11, 5, 12, 32)), path)
    assert path.read_bytes() != before


def test_payload_comparison_ignores_only_the_core_properties(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a.xlsx", tmp_path / "b.xlsx", tmp_path / "c.xlsx"
    _workbook(7, _utc(2020, 1, 1)).save(a)
    _workbook(7, _utc(2021, 1, 1)).save(b)
    _workbook(9, _utc(2020, 1, 1)).save(c)
    assert xlsx_payload_equal(a, b)
    assert not xlsx_payload_equal(a, c)
    assert not xlsx_payload_equal(a, tmp_path / "khong-co.xlsx")
