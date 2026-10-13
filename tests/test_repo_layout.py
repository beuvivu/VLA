"""Bố cục kho đã sắp xếp lại ngày 13-10-2026: giữ cho nó không trôi về mớ hỗn độn cũ.

* ``docs/`` là gốc GitHub Pages: mọi thứ trong đó đều được xuất bản. Tài liệu nội bộ, kế hoạch
  và báo cáo kiểm toán từng nằm ở ``docs/audit``, ``docs/design``, ``docs/superpowers``,
  ``docs/ui-ux`` — tức bị đăng công khai cùng trang. Nay chúng ở ``documentation/``.
* ``scripts/`` chia theo công dụng. Script ở hai cấp dưới gốc kho, nên gốc kho là
  ``Path(__file__).resolve().parents[2]`` (Python) hay ``$(dirname "$0")/../..`` (shell);
  ``parents[1]`` nay trỏ vào ``scripts/`` và làm script đọc sai chỗ mà không báo lỗi.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_GROUPS = {"release", "browser", "ops", "research", "reference"}


def _files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts]


def docs_offenders(docs: Path) -> list[str]:
    """Tệp trong ``docs/`` không phải trang web: chỉ cho phép ``*.html`` ở gốc, ``.nojekyll`` và ``assets/``."""
    bad = []
    for path in _files(docs):
        rel = path.relative_to(docs)
        if rel.parts[0] == "assets" or rel.as_posix() == ".nojekyll":
            continue
        if len(rel.parts) == 1 and rel.suffix == ".html":
            continue
        bad.append(rel.as_posix())
    return sorted(bad)


def script_offenders(scripts: Path) -> list[str]:
    """Script nằm ngoài nhóm, hoặc tính gốc kho sai độ sâu."""
    bad = []
    for path in _files(scripts):
        rel = path.relative_to(scripts)
        if len(rel.parts) != 2 or rel.parts[0] not in SCRIPT_GROUPS:
            bad.append(f"{rel.as_posix()}: không thuộc nhóm nào trong {sorted(SCRIPT_GROUPS)}")
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py" and re.search(r"Path\(__file__\)\.resolve\(\)\.parents\[(?!2\])\d+\]", text):
            bad.append(f"{rel.as_posix()}: gốc kho phải là Path(__file__).resolve().parents[2]")
        if path.suffix == ".sh" and "BASH_SOURCE" in text and '/../.." && pwd' not in text:
            bad.append(f"{rel.as_posix()}: gốc kho phải là $(dirname BASH_SOURCE)/../..")
    return sorted(bad)


def test_docs_holds_only_the_published_site() -> None:
    assert not docs_offenders(ROOT / "docs")


def test_every_script_sits_in_a_group_and_finds_the_repository_root() -> None:
    assert not script_offenders(ROOT / "scripts")


def test_the_layout_rules_catch_a_stray_file(tmp_path: Path) -> None:
    """Ghim chính luật trên cây dựng sẵn, để một lần quét rỗng không làm hai phép kiểm trên luôn xanh."""
    docs = tmp_path / "docs"
    (docs / "assets").mkdir(parents=True)
    (docs / "index.html").write_text("x", encoding="utf-8")
    (docs / ".nojekyll").write_text("", encoding="utf-8")
    (docs / "assets" / "app.js").write_text("x", encoding="utf-8")
    assert docs_offenders(docs) == []
    (docs / "notes.md").write_text("x", encoding="utf-8")
    (docs / "plans").mkdir()
    (docs / "plans" / "page.html").write_text("x", encoding="utf-8")
    assert docs_offenders(docs) == ["notes.md", "plans/page.html"]

    scripts = tmp_path / "scripts"
    (scripts / "ops").mkdir(parents=True)
    (scripts / "release").mkdir()
    (scripts / "ops" / "good.py").write_text("ROOT = Path(__file__).resolve().parents[2]\n", encoding="utf-8")
    (scripts / "release" / "good.sh").write_text(
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"\n', encoding="utf-8")
    assert script_offenders(scripts) == []
    (scripts / "loose.py").write_text("", encoding="utf-8")
    (scripts / "ops" / "shallow.py").write_text("ROOT = Path(__file__).resolve().parents[1]\n", encoding="utf-8")
    (scripts / "release" / "shallow.sh").write_text(
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n', encoding="utf-8")
    found = script_offenders(scripts)
    assert [f.split(":")[0] for f in found] == ["loose.py", "ops/shallow.py", "release/shallow.sh"]
