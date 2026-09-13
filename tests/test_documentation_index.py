"""Mọi tài liệu đều phải tìm được từ mục lục.

Tài liệu không ai tìm ra thì bằng không có. Ba tệp trong
``documentation/operations/`` đã nằm ngoài mục lục suốt một thời gian mà không
gì phát hiện — kể cả tệp mô tả đúng cái việc bạn phải làm bằng tay.

Phép kiểm này rẻ và chặn đúng kiểu hỏng ấy: thêm tài liệu mà quên liên kết thì
đỏ ngay, chứ không đợi tới lúc cần dùng mới biết.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "documentation" / "README.md"


def test_every_documentation_file_is_linked_from_the_index() -> None:
    index_text = INDEX.read_text(encoding="utf-8")
    missing: list[str] = []
    for path in sorted(ROOT.joinpath("documentation").rglob("*.md")):
        relative = path.relative_to(ROOT / "documentation").as_posix()
        if relative == "README.md":
            continue
        # engineering-log là sổ tay nội bộ, mục lục trỏ tới cả THƯ MỤC chứ
        # không liệt kê từng tệp — đó là chủ ý, không phải sót.
        if relative.startswith("engineering-log/"):
            continue
        if relative not in index_text:
            missing.append(relative)
    assert not missing, "tài liệu chưa có trong mục lục:\n  " + "\n  ".join(missing)


def test_the_index_does_not_point_at_files_that_no_longer_exist() -> None:
    """Liên kết chết còn tệ hơn thiếu liên kết: nó hứa rồi không giữ lời."""
    import re

    broken: list[str] = []
    for target in re.findall(r"\]\((?!https?:)([^)#]+)\)", INDEX.read_text(encoding="utf-8")):
        if not (ROOT / "documentation" / target).exists():
            broken.append(target)
    assert not broken, "mục lục trỏ tới tệp không tồn tại:\n  " + "\n  ".join(broken)
