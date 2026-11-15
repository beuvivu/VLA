"""Bố cục 27 giải XSMB khai MỘT lần ở ``core.xsmb_domain`` (15-11-2026).

Docstring của ``xsmb_domain`` nói bố cục đã được gom về một nguồn, nhưng đến 15-11-2026 vẫn còn mười bản chép
tay: ``path_models``, ``excel_export``, ``validate_data`` (độ rộng từng giải), ``board_record``,
``confidence_matrix``, ``update_pred_labels``, ``hot_tail_test`` (danh sách 27 cột), ``confidence_matrix``,
``build_stat_pages``, ``update_readme``, ``reconcile_live_canonical`` (độ rộng theo nhóm). Chúng còn khớp nhau,
nhưng không gì buộc chúng khớp: đổi một bản là bộ bóc, bộ kiểm dữ liệu và phép cắt chữ số theo vị trí lệch
nhau mà không phép kiểm nào thấy.

Còn đúng HAI bản nhẹ được phép, vì chúng chạy trong job live chỉ cài pydantic/requests/bs4 (không numpy, pandas):
``core.dtos.FIELD_WIDTHS`` và ``ingest.sources.EXPECTED_WIDTHS``/``EXPECTED_COUNTS``/``PRIZE_ORDER``. Hai bản ấy
bị buộc khớp nguồn chuẩn ở đây.
"""

from __future__ import annotations

import ast
from pathlib import Path

from core import dtos, xsmb_domain
from core.xsmb_domain import FIELD_WIDTH_MAP, FIELD_WIDTHS, PRIZE_FIELDS, PRIZE_GROUP_FIELDS, PRIZE_GROUP_WIDTHS

SRC = Path(__file__).resolve().parents[2] / "src"

#: Nơi duy nhất được khai bố cục bằng chữ: nguồn chuẩn và hai bản nhẹ đã ghim ở dưới.
ALLOWED = {"core/xsmb_domain.py", "core/dtos.py", "ingest/sources.py"}


def test_the_canonical_layout_is_the_xsmb_draw() -> None:
    assert len(PRIZE_FIELDS) == 27 and sum(w for _, w in FIELD_WIDTHS) == 107
    assert PRIZE_GROUP_WIDTHS == {"special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
                                  "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2}
    assert {group: len(fields) for group, fields in PRIZE_GROUP_FIELDS.items()} == {
        "special": 1, "prize1": 1, "prize2": 2, "prize3": 6, "prize4": 4, "prize5": 6, "prize6": 3, "prize7": 4}
    assert [f for fields in PRIZE_GROUP_FIELDS.values() for f in fields] == list(PRIZE_FIELDS)


def test_the_two_light_copies_match_the_canonical_layout() -> None:
    from ingest import sources

    assert list(dtos.FIELD_WIDTHS.items()) == list(FIELD_WIDTHS)
    assert sources.EXPECTED_WIDTHS == PRIZE_GROUP_WIDTHS
    assert sources.EXPECTED_COUNTS == {group: len(fields) for group, fields in PRIZE_GROUP_FIELDS.items()}
    assert sources.PRIZE_ORDER == list(PRIZE_GROUP_FIELDS)


def test_every_heavy_module_reads_the_canonical_layout() -> None:
    from core import excel_export, path_models
    from evaluation import board_record, confidence_matrix, update_pred_labels
    from ingest import reconcile_live_canonical, validate_data
    from pages import build_stat_pages, update_readme
    from research import hot_tail_test

    assert tuple(path_models.FIELD_WIDTHS) == FIELD_WIDTHS
    assert excel_export.FIELD_WIDTHS is FIELD_WIDTH_MAP and validate_data.FIELD_WIDTHS is FIELD_WIDTH_MAP
    for columns in (board_record.PRIZE_COLUMNS, confidence_matrix.PRIZE_COLUMNS,
                    update_pred_labels.PRIZE_COLS, hot_tail_test.PRIZES):
        assert columns == list(PRIZE_FIELDS)
    for widths in (confidence_matrix.PRIZE_WIDTH, build_stat_pages.PRIZE_WIDTH, update_readme.WIDTHS,
                   reconcile_live_canonical.WIDTHS):
        assert widths == PRIZE_GROUP_WIDTHS
    assert {group: tuple(f) for group, f in reconcile_live_canonical.FIELDS.items()} == PRIZE_GROUP_FIELDS


def layout_literals(source: str) -> list[int]:
    """Dòng của mọi chỗ khai bố cục giải BẰNG CHỮ trong ``source``.

    Ba dạng: bảng độ rộng (từ điển tên giải/nhóm → số nguyên), danh sách cặp ``("prize7_4", 2)``, và danh sách
    đủ 27 tên cột theo đúng thứ tự. Bảng NHÃN (``"prize7_4": "Giải bảy 4"``) không bị bắt: giá trị là chữ.
    """
    names = set(PRIZE_FIELDS) | set(PRIZE_GROUP_FIELDS)
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            ints = all(isinstance(v, ast.Constant) and type(v.value) is int for v in node.values)
            if ints and keys & {"prize7", "prize7_4"} and keys <= names:
                lines.append(node.lineno)
        elif isinstance(node, (ast.List, ast.Tuple)):
            values = [e.value for e in node.elts if isinstance(e, ast.Constant)]
            if values == list(PRIZE_FIELDS):
                lines.append(node.lineno)
            pairs = [e for e in node.elts if isinstance(e, ast.Tuple) and len(e.elts) == 2]
            if any(isinstance(p.elts[0], ast.Constant) and p.elts[0].value == "prize7_4" for p in pairs):
                lines.append(node.lineno)
    return lines


def test_the_rule_itself_catches_each_literal_layout_and_spares_label_tables() -> None:
    sample = "\n".join([
        'A = {"special": 5, "prize1": 5, "prize7": 2}',
        'B = [("special", 5), ("prize7_4", 2)]',
        "C = " + repr(list(PRIZE_FIELDS)),
        'LABELS = {"prize7_4": "Giải bảy 4", "prize7": "Giải bảy"}',
        "D = list(PRIZE_FIELDS)",
    ])
    assert layout_literals(sample) == [1, 2, 3]


def test_no_module_outside_the_canonical_source_declares_the_layout_literally() -> None:
    files = sorted(SRC.rglob("*.py"))
    assert len(files) > 100, "tập quét rỗng — luật không thể đỏ"
    found = {
        str(path.relative_to(SRC)): lines
        for path in files
        if str(path.relative_to(SRC)) not in ALLOWED
        and (lines := layout_literals(path.read_text(encoding="utf-8")))
    }
    assert found == {}
    # Chính nguồn chuẩn phải bị luật bắt — nếu không, luật đã mù với dạng khai ấy.
    assert layout_literals((SRC / "core" / "xsmb_domain.py").read_text(encoding="utf-8"))
    assert xsmb_domain.FIELD_WIDTHS is FIELD_WIDTHS
