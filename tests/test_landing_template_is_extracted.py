from __future__ import annotations

"""CSS và JavaScript của các trang dựng phải là HẰNG SỐ, không nằm trong f-string.

``_render_html`` từng dài 1 795 dòng — 65% cả tệp trong một hàm — và 1 370
dòng trong đó là CSS (1 250) cùng JavaScript (120) nhúng thẳng vào f-string.

Nằm trong f-string nghĩa là MỌI dấu ngoặc phải viết đôi (``{{``/``}}``): cú
pháp CSS và JavaScript bị bóp méo chỉ vì chỗ đặt, và mỗi lần sửa một quy tắc
là một lần phải nhớ nhân đôi. Cả hai khối không nội suy biến nào (đã kiểm: 0
chỗ), nên chúng là văn bản thuần và thuộc về hằng số.

Sau khi trích: ``_render_html`` còn 429 dòng, và ba trang dựng ra TRÙNG KHÍT
với bản mã gốc (so sau khi chuẩn hoá hai dấu thời gian).
"""

import ast
import re
from pathlib import Path

import pytest

import build_landing_page as blp
import build_statistics_dashboard as bsd

SOURCE = Path(blp.__file__).read_text(encoding="utf-8")
DOUBLED_BRACE = re.compile(r"\{\{|\}\}")


def _function_length(name: str, source: str | None = None) -> int:
    tree = ast.parse(source if source is not None else SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.end_lineno - node.lineno + 1
    raise AssertionError(f"không tìm thấy hàm {name}")


BLOCKS = [
    (blp, "_LANDING_CSS", 800, ":root"),
    (blp, "_LANDING_SCRIPT", 60, "function"),
    (bsd, "_DASHBOARD_CSS", 500, "{"),
    (bsd, "_DASHBOARD_SCRIPT_MAIN", 20, "function"),
    (bsd, "_DASHBOARD_SCRIPT_EVIDENCE", 120, "function"),
]


@pytest.mark.parametrize(
    ("module", "name", "minimum_lines", "marker"),
    BLOCKS,
    ids=[f"{m.__name__.split('_')[-1]}:{n}" for m, n, _, _ in BLOCKS],
)
def test_the_block_lives_in_a_module_constant(module, name, minimum_lines, marker) -> None:
    block = getattr(module, name, None)
    assert isinstance(block, str), f"{name} phải là hằng số chuỗi cấp module"
    assert len(block.splitlines()) >= minimum_lines, (
        f"{name} chỉ còn {len(block.splitlines())} dòng — khối có vẻ đã bị gộp "
        "trở lại vào thân hàm"
    )
    assert marker in block, f"{name} không mang dấu hiệu nội dung mong đợi"


@pytest.mark.parametrize(
    ("module", "name"),
    [(m, n) for m, n, _, _ in BLOCKS],
    ids=[f"{m.__name__.split('_')[-1]}:{n}" for m, n, _, _ in BLOCKS],
)
def test_the_extracted_block_has_no_doubled_braces(module, name) -> None:
    """Đây là LỢI ÍCH THẬT của việc trích: cú pháp trở lại đúng.

    Còn dấu ngoặc đôi nghĩa là khối vẫn đang được viết cho f-string, tức việc
    trích chưa đi tới đâu.
    """
    block = getattr(module, name)
    doubled = DOUBLED_BRACE.findall(block)
    assert not doubled, (
        f"{name} còn {len(doubled)} dấu ngoặc viết đôi — khối vẫn mang cú pháp "
        "của f-string thay vì cú pháp CSS/JavaScript thật"
    )


@pytest.mark.parametrize(
    ("module", "function", "was", "ceiling"),
    [(blp, "_render_html", 1795, 700), (bsd, "main", 1441, 700)],
    ids=["landing:_render_html", "dashboard:main"],
)
def test_the_render_function_is_no_longer_the_whole_file(
    module, function, was, ceiling
) -> None:
    """Ngưỡng 700 nằm giữa số dòng TRƯỚC và SAU, nên nó phân biệt được hai bên."""
    source = Path(module.__file__).read_text(encoding="utf-8")
    length = _function_length(function, source)
    assert length < ceiling, (
        f"{function} dài {length} dòng (trước khi trích: {was}); CSS hoặc "
        "JavaScript có vẻ đã bị nhúng trở lại vào thân hàm"
    )


def test_the_page_still_carries_both_blocks() -> None:
    """Trích ra thì phải NỐI LẠI: chốt chặn cho một bản trích quên dùng hằng số."""
    page = blp._render_html(Path(blp.__file__).resolve().parents[2], generated_at="TS")
    for name in ("_LANDING_CSS", "_LANDING_SCRIPT"):
        block = getattr(blp, name)
        sample = next(
            line.strip() for line in block.splitlines()
            if len(line.strip()) > 30 and not line.strip().startswith("/*")
        )
        assert sample in page, f"trang dựng ra không chứa nội dung của {name}"
