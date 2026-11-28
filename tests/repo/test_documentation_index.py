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
        if relative.startswith("engineering-log/"):
            continue
        if relative not in index_text:
            missing.append(relative)
    assert not missing, "tài liệu chưa có trong mục lục:\n  " + "\n  ".join(missing)


def test_the_index_does_not_point_at_files_that_no_longer_exist() -> None:
    import re

    broken: list[str] = []
    for target in re.findall(r"\]\((?!https?:)([^)#]+)\)", INDEX.read_text(encoding="utf-8")):
        if not (ROOT / "documentation" / target).exists():
            broken.append(target)
    assert not broken, "mục lục trỏ tới tệp không tồn tại:\n  " + "\n  ".join(broken)


_LINK = re.compile(r"\]\(((?!https?:|mailto:|#)[^)\s#]+)(?:#[^)]*)?\)")
_LAYOUT_ROW = re.compile(r"^\| `([\w-]+)/` \|", re.M)


def declared_groups(index_text: str) -> set[str]:
    section = index_text.split("## Bố cục thư mục", 1)[-1].split("\n## ", 1)[0]
    return set(_LAYOUT_ROW.findall(section))


def layout_offenders(documentation: Path) -> list[str]:
    index = documentation / "README.md"
    declared = declared_groups(index.read_text(encoding="utf-8"))
    on_disk = {p.name for p in documentation.iterdir() if p.is_dir()}
    bad = [f"{name}/: có trên đĩa, không có trong bảng" for name in sorted(on_disk - declared)]
    bad += [f"{name}/: có trong bảng, không có trên đĩa" for name in sorted(declared - on_disk)]
    bad += [f"{p.name}: tệp ở gốc documentation/" for p in sorted(documentation.iterdir())
            if p.is_file() and p.name != "README.md"]
    return bad


def dead_links(documentation: Path) -> list[str]:
    return [
        f"{path.relative_to(documentation).as_posix()}: {target}"
        for path in sorted(documentation.rglob("*.md"))
        for target in _LINK.findall(path.read_text(encoding="utf-8"))
        if not (path.parent / target).exists()
    ]


def test_every_document_sits_in_a_group_the_index_declares() -> None:
    documentation = ROOT / "documentation"
    assert {"architecture", "qa", "research"} <= declared_groups(INDEX.read_text(encoding="utf-8"))
    assert not layout_offenders(documentation)


def test_no_document_links_to_a_file_that_no_longer_exists() -> None:
    documentation = ROOT / "documentation"
    assert sum(1 for _ in documentation.rglob("*.md")) > 50
    broken = dead_links(documentation)
    assert not broken, "liên kết chết:\n  " + "\n  ".join(broken)


def test_the_documentation_layout_rules_catch_a_drift(tmp_path: Path) -> None:
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
    assert dead_links(doc) == ["architecture/a.md: ../qa/b.md"]
