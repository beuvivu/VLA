"""Đọc tệp của trình dựng trang: thiếu thì rỗng im lặng, hỏng thì cảnh báo, lỗi mã thì nổ.

Trước ``safe_io``, mười một trình dựng tự viết ``_read_csv``/``_read_json`` với
``except Exception``. Ngay lần chuyển đầu tiên, một ``NameError`` của chính lần
sửa ấy suýt bị nuốt thành ô "—" trên trang chủ; các phép kiểm dưới đây ghim cả
ba nhánh để luật không trôi về chỗ cũ.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pandas as pd
import pytest

import safe_io

SRC = Path(__file__).resolve().parents[1] / "src"


def test_a_missing_or_empty_file_is_empty_and_silent(tmp_path: Path, caplog) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="safe_io"):
        assert safe_io.read_csv_or_empty(tmp_path / "missing.csv").empty
        assert safe_io.read_csv_or_empty(empty).empty
        assert safe_io.read_json_or_empty(tmp_path / "missing.json") == {}
    assert caplog.records == []


def test_a_present_file_is_read_with_the_given_options(tmp_path: Path) -> None:
    path = tmp_path / "x.csv"
    path.write_text("number,prob\n07,0.5\n", encoding="utf-8")
    frame = safe_io.read_csv_or_empty(path, dtype={"number": str})
    assert frame.to_dict("records") == [{"number": "07", "prob": 0.5}]
    (tmp_path / "x.json").write_text('{"a": [1, 2]}', encoding="utf-8")
    assert safe_io.read_json_or_empty(tmp_path / "x.json") == {"a": [1, 2]}


@pytest.mark.parametrize(
    "name, payload, reader",
    [
        ("broken.json", b'{"modes": {"de":', safe_io.read_json_or_empty),
        ("latin1.json", b'{"x": "\xe9"}', safe_io.read_json_or_empty),
        ("ragged.csv", b'a,b\n1,2\n"3,4\n', safe_io.read_csv_or_empty),
    ],
)
def test_a_corrupt_file_is_empty_but_named_in_a_warning(
    tmp_path: Path, caplog, name, payload, reader
) -> None:
    """Tệp có mặt mà hỏng là sự cố dữ liệu: trang vẫn dựng, nhưng log phải nói."""
    path = tmp_path / name
    path.write_bytes(payload)
    with caplog.at_level(logging.WARNING, logger="safe_io"):
        out = reader(path)
    assert len(out) == 0
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert str(path) in caplog.records[0].getMessage()


def test_a_programming_error_is_not_swallowed(tmp_path: Path) -> None:
    """Truyền sai tham số là lỗi của MÃ: phải nổ, không được thành 'chưa có dữ liệu'."""
    path = tmp_path / "x.csv"
    path.write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(TypeError):
        safe_io.read_csv_or_empty(path, no_such_option=True)
    # ValueError trần của pandas cũng là lỗi tham số, không phải tệp hỏng.
    with pytest.raises(ValueError, match="engine"):
        safe_io.read_csv_or_empty(path, engine="no-such-engine")


def test_the_page_builders_read_through_safe_io(tmp_path: Path, caplog) -> None:
    """Trình dựng thật: JSON hỏng thì ra trạng thái trống KÈM cảnh báo."""
    import build_landing_page as landing

    research = tmp_path / "data" / "research"
    research.mkdir(parents=True)
    (research / "model_scores.json").write_text('{"modes": ', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="safe_io"):
        assert landing._model_grade(tmp_path) == "—"
    assert any("model_scores.json" in r.getMessage() for r in caplog.records)

    (research / "model_scores.json").write_text(
        '{"modes": {"de": {"beats_baseline": true}, "loto": {}}}', encoding="utf-8"
    )
    assert landing._model_grade(tmp_path) == "B"


_FILE_READERS = {"read_csv", "loads", "load", "read_text"}


def _swallowing_readers(tree: ast.AST) -> list[int]:
    """Dòng của mọi ``try`` đọc tệp mà ``except Exception`` nuốt im lặng."""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        reads = {
            n.func.attr
            for stmt in node.body
            for n in ast.walk(stmt)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        } & _FILE_READERS
        for handler in node.handlers:
            broad = handler.type is None or (
                isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}
            )
            if broad and reads and handler.name is None:
                hits.append(handler.lineno)
    return hits


def test_the_rule_itself_catches_a_swallowing_reader() -> None:
    """Ghim chính LUẬT trên mẫu dựng sẵn, để một lần quét hỏng không thành tập rỗng."""
    sample = ast.parse(
        "def f(p):\n"
        "    try:\n"
        "        return pd.read_csv(p)\n"
        "    except Exception:\n"
        "        return None\n"
    )
    assert _swallowing_readers(sample) == [4]
    narrowed = ast.parse(
        "def f(p):\n"
        "    try:\n"
        "        return pd.read_csv(p)\n"
        "    except (OSError, ValueError):\n"
        "        return None\n"
    )
    assert _swallowing_readers(narrowed) == []


def test_no_page_builder_swallows_a_file_read_silently() -> None:
    builders = sorted(SRC.glob("build_*.py")) + [
        SRC / name for name in ("cau_position_evidence.py", "cap_loto_50_stats.py", "lottery.py")
    ]
    assert len(builders) > 10
    offenders = {
        path.name: lines
        for path in builders
        if (lines := _swallowing_readers(ast.parse(path.read_text(encoding="utf-8"))))
    }
    assert offenders == {}, "đọc tệp qua safe_io thay vì except Exception im lặng"


def test_an_empty_frame_from_safe_io_is_a_real_dataframe(tmp_path: Path) -> None:
    assert isinstance(safe_io.read_csv_or_empty(tmp_path / "none.csv"), pd.DataFrame)
