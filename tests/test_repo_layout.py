"""Bố cục kho đã sắp xếp lại ngày 13-10-2026: giữ cho nó không trôi về mớ hỗn độn cũ.

* ``docs/`` là gốc GitHub Pages: mọi thứ trong đó đều được xuất bản. Tài liệu nội bộ, kế hoạch
  và báo cáo kiểm toán từng nằm ở ``docs/audit``, ``docs/design``, ``docs/superpowers``,
  ``docs/ui-ux`` — tức bị đăng công khai cùng trang. Nay chúng ở ``documentation/``.
* ``scripts/`` chia theo công dụng. Script ở hai cấp dưới gốc kho, nên gốc kho là
  ``Path(__file__).resolve().parents[2]`` (Python) hay ``$(dirname "$0")/../..`` (shell);
  ``parents[1]`` nay trỏ vào ``scripts/`` và làm script đọc sai chỗ mà không báo lỗi.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_GROUPS = {"release", "browser", "ops", "research", "reference"}
#: Thư viện chỉ được cài trong job của chính script (trình duyệt, đọc trang tham chiếu), không có
#: trong môi trường kiểm thử chung.
TOOL_ONLY = {"playwright"}


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


def unresolved_imports(scripts: Path, src: Path) -> list[str]:
    """Import của script không tìm thấy ở đâu: thư viện chuẩn, ``src/``, cùng thư mục, đã cài, hay ``TOOL_ONLY``.

    Ngày 13-10-2026 một script bị xoá vì không ai nhắc tới TÊN TỆP của nó, trong khi script khác
    import nó theo TÊN MODULE; job trình duyệt của CI chết ở dòng import.
    """
    src_modules = {p.stem for p in src.glob("*.py")}
    src_modules |= {p.name for p in src.iterdir() if (p / "__init__.py").exists()}
    bad = []
    for path in sorted(scripts.glob("*/*.py")):
        siblings = {p.stem for p in path.parent.glob("*.py")}
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if (name == "__future__" or name in sys.stdlib_module_names or name in src_modules
                        or name in siblings or name in TOOL_ONLY):
                    continue
                if importlib.util.find_spec(name) is None:
                    bad.append(f"{path.relative_to(scripts).as_posix()}: import {name}")
    return bad


def test_docs_holds_only_the_published_site() -> None:
    assert not docs_offenders(ROOT / "docs")


def test_every_script_sits_in_a_group_and_finds_the_repository_root() -> None:
    assert not script_offenders(ROOT / "scripts")


def test_every_script_import_resolves() -> None:
    assert not unresolved_imports(ROOT / "scripts", ROOT / "src")


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


def test_the_import_rule_catches_a_removed_sibling(tmp_path: Path) -> None:
    scripts, src = tmp_path / "scripts", tmp_path / "src"
    (scripts / "browser").mkdir(parents=True)
    src.mkdir()
    (src / "ui_theme.py").write_text("", encoding="utf-8")
    (scripts / "browser" / "helper.py").write_text("import json\n", encoding="utf-8")
    (scripts / "browser" / "main.py").write_text(
        "from helper import x\nimport ui_theme\nfrom playwright.sync_api import sync_playwright\n", encoding="utf-8")
    assert unresolved_imports(scripts, src) == []
    (scripts / "browser" / "helper.py").unlink()
    assert unresolved_imports(scripts, src) == ["browser/main.py: import helper"]
