from __future__ import annotations


import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
JS = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")


def test_the_table_builder_reads_a_declared_pair_into_the_cell_key() -> None:
    body = re.search(r"const pair = opts\.pairOf[^\n]*\n[^\n]*\n?", JS)
    assert body, "table() không còn đọc opts.pairOf"
    assert re.search(r"const key = pair [^\n]*\|n\$\{pair\}", JS), (
        "table() đọc opts.pairOf nhưng không gắn cặp vào data-key, nên "
        "markPair() vẫn không đọc ra gì"
    )


def test_a_cell_lights_up_from_pair_marks_not_only_from_cell_marks() -> None:
    for scope in ("const on = (MARKS.has(key)", "const on = (MARKS.has(hKey)"):
        line = next((l for l in JS.split("\n") if l.strip().startswith(scope)), None)
        assert line, f"không tìm thấy nhánh tô sáng: {scope}"
        assert "PAIR_MARKS.has(pair)" in line or "PAIR_MARKS.has(hPair)" in line, (
            f"nhánh tô sáng chỉ tra MARKS, bỏ qua PAIR_MARKS: {line.strip()}"
        )


def test_pair_marks_are_stored_site_wide_but_cell_marks_stay_per_page() -> None:
    mark = re.search(r"^const MARK_KEY = (.+)$", JS, re.M)
    pair = re.search(r"^const PAIR_KEY = (.+)$", JS, re.M)
    assert mark and pair, "thiếu một trong hai khoá lưu trữ"
    assert "location.pathname" in mark.group(1), "dấu Ô phải theo từng trang"
    assert "location.pathname" not in pair.group(1), (
        "dấu CẶP phải dùng chung cho toàn site; có location.pathname là đang "
        "nhốt nó lại theo trang"
    )


def test_pages_without_two_digit_numbers_do_not_offer_pair_mode() -> None:
    offered = {
        p.name for p in DOCS.glob("*.html")
        if 'id="sp-pair-mode"' in p.read_text(encoding="utf-8")
    }
    assert len(offered) >= 10, "quá ít trang có ô tick; phép kiểm mất đối tượng"
    for name in ("dau-duoi-loto.html", "giai-dac-biet-theo-tong.html"):
        assert (DOCS / name).exists(), f"thiếu {name}; phép kiểm mất đối tượng"
        assert name not in offered, (
            f"{name} chỉ có chữ số đơn 0-9 nên đánh dấu theo cặp hai chữ số là "
            "vô nghĩa ở đó, nhưng trang vẫn bày ô tick."
        )
