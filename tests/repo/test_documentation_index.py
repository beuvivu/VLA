"""Mọi tài liệu đều phải tìm được từ mục lục.

Tài liệu không ai tìm ra thì bằng không có. Ba tệp trong
``documentation/operations/`` đã nằm ngoài mục lục suốt một thời gian mà không
gì phát hiện — kể cả tệp mô tả đúng cái việc bạn phải làm bằng tay.

Phép kiểm này rẻ và chặn đúng kiểu hỏng ấy: thêm tài liệu mà quên liên kết thì
đỏ ngay, chứ không đợi tới lúc cần dùng mới biết.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


#: Liên kết tương đối trong một tài liệu Markdown (bỏ URL tuyệt đối, mailto và neo trong trang).
_LINK = re.compile(r"\]\(((?!https?:|mailto:|#)[^)\s#]+)(?:#[^)]*)?\)")
#: Một hàng của bảng "Bố cục thư mục" trong mục lục: | `nhóm/` | nội dung |
_LAYOUT_ROW = re.compile(r"^\| `([\w-]+)/` \|", re.M)


def declared_groups(index_text: str) -> set[str]:
    """Nhóm mà bảng "Bố cục thư mục" của mục lục khai."""
    section = index_text.split("## Bố cục thư mục", 1)[-1].split("\n## ", 1)[0]
    return set(_LAYOUT_ROW.findall(section))


def layout_offenders(documentation: Path) -> list[str]:
    """Tệp nằm ngoài nhóm, hoặc nhóm trên đĩa và nhóm trong bảng không khớp nhau."""
    index = documentation / "README.md"
    declared = declared_groups(index.read_text(encoding="utf-8"))
    on_disk = {p.name for p in documentation.iterdir() if p.is_dir()}
    bad = [f"{name}/: có trên đĩa, không có trong bảng" for name in sorted(on_disk - declared)]
    bad += [f"{name}/: có trong bảng, không có trên đĩa" for name in sorted(declared - on_disk)]
    bad += [f"{p.name}: tệp ở gốc documentation/" for p in sorted(documentation.iterdir())
            if p.is_file() and p.name != "README.md"]
    return bad


def dead_links(documentation: Path) -> list[str]:
    """Liên kết tương đối trong MỌI tài liệu mà không trỏ tới tệp có thật."""
    return [
        f"{path.relative_to(documentation).as_posix()}: {target}"
        for path in sorted(documentation.rglob("*.md"))
        for target in _LINK.findall(path.read_text(encoding="utf-8"))
        if not (path.parent / target).exists()
    ]


def test_every_document_sits_in_a_group_the_index_declares() -> None:
    """Tài liệu chia theo chức năng; bảng nhóm trong mục lục là hợp đồng, không phải mô tả."""
    documentation = ROOT / "documentation"
    assert {"architecture", "qa", "research"} <= declared_groups(INDEX.read_text(encoding="utf-8"))
    assert not layout_offenders(documentation)


def test_no_document_links_to_a_file_that_no_longer_exists() -> None:
    """Chuyển tài liệu sang nhóm khác làm hỏng liên kết TƯƠNG ĐỐI của chính nó và của tệp trỏ tới nó."""
    documentation = ROOT / "documentation"
    assert sum(1 for _ in documentation.rglob("*.md")) > 50
    broken = dead_links(documentation)
    assert not broken, "liên kết chết:\n  " + "\n  ".join(broken)


def test_the_documentation_layout_rules_catch_a_drift(tmp_path: Path) -> None:
    """Ghim luật trên cây dựng sẵn để một phép quét rỗng không thể xanh."""
    doc = tmp_path / "documentation"
    for name in ("architecture", "qa"):
        (doc / name).mkdir(parents=True)
    (doc / "README.md").write_text(
        "# x\n\n## Bố cục thư mục\n\n| Thư mục | Nội dung |\n| --- | --- |\n"
        "| `architecture/` | a |\n| `qa/` | b |\n\n## Index\n\n| `ui/` | ngoài bảng |\n", encoding="utf-8")
    (doc / "architecture" / "a.md").write_text("[b](../qa/b.md) [web](https://x.y/z.md) [neo](#t)\n", encoding="utf-8")
    (doc / "qa" / "b.md").write_text("[a](../architecture/a.md#muc)\n", encoding="utf-8")
    assert layout_offenders(doc) == [] and dead_links(doc) == []
    (doc / "ui").mkdir()
    (doc / "notes.md").write_text("", encoding="utf-8")
    (doc / "qa" / "b.md").rename(doc / "ui" / "b.md")
    assert layout_offenders(doc) == ["ui/: có trên đĩa, không có trong bảng", "notes.md: tệp ở gốc documentation/"]
    # ui/b.md vẫn tới được ../architecture/a.md; chỉ liên kết TỚI tệp đã chuyển là chết.
    assert dead_links(doc) == ["architecture/a.md: ../qa/b.md"]

