"""Bố cục kho đã sắp xếp lại ngày 13-10-2026: giữ cho nó không trôi về mớ hỗn độn cũ.

* ``docs/`` là gốc GitHub Pages: mọi thứ trong đó đều được xuất bản. Tài liệu nội bộ, kế hoạch
  và báo cáo kiểm toán từng nằm ở ``docs/audit``, ``docs/design``, ``docs/superpowers``,
  ``docs/ui-ux`` — tức bị đăng công khai cùng trang. Nay chúng ở ``documentation/``.
* ``scripts/`` chia theo chức năng (``SCRIPT_GROUPS``). Script ở hai cấp dưới gốc kho, nên gốc kho là
  ``Path(__file__).resolve().parents[2]`` (Python) hay ``$(dirname "$0")/../..`` (shell);
  ``parents[1]`` nay trỏ vào ``scripts/`` và làm script đọc sai chỗ mà không báo lỗi.
* ``tests/`` chia theo chức năng (``TEST_GROUPS``, 24-10-2026): phép kiểm nằm ở ``tests/<nhóm>/``,
  cũng hai cấp dưới gốc kho. ``parents[1]`` trỏ vào ``tests/`` và ``(ROOT / "docs").glob(...)``
  trả tập rỗng: phép kiểm tham số hoá trên tập ấy không chạy lần nào mà vẫn báo xanh.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: Nhóm của ``scripts/`` theo chức năng (24-10-2026: bốn công cụ dựng trang tách khỏi ``ops``).
SCRIPT_GROUPS = {
    "ops": "vận hành CI và triển khai: báo động đường đúng giờ, chẩn đoán nguồn, xoá cache, đẩy trang",
    "web": "công cụ dựng và hậu xử lý trang đã xuất bản: critical CSS, khung điều hướng, CSP, DOM",
    "browser": "kiểm trang đã xuất bản trên Chromium thật",
    "reference": "đọc trang tham chiếu qua runner Actions",
    "release": "bốn kịch bản chốt phát hành",
    "research": "phép đo và benchmark tái lập được của tài liệu nghiên cứu",
}
#: Nhóm của ``tests/`` theo chức năng: mười một nhóm trùng tên gói ``src/`` mà chúng kiểm, cộng bốn
#: nhóm cắt ngang không thuộc gói nào.
TEST_GROUPS = {
    "core": "gói src/core", "ingest": "gói src/ingest", "ensemble": "gói src/ensemble",
    "stats": "gói src/stats", "soi_cau": "gói src/soi_cau", "ml": "gói src/ml",
    "forecast": "gói src/forecast", "evaluation": "gói src/evaluation", "research": "gói src/research",
    "web": "gói src/web", "pages": "gói src/pages",
    "pipeline": "thứ tự bước của src/pipeline.py",
    "site": "bất biến trên trang đã xuất bản trong docs/",
    "worker": "Worker Cloudflare (worker/) và phép so bản Python ↔ JS",
    "repo": "bố cục kho, workflow, CI, tài liệu, kịch bản vận hành, bảo mật cắt ngang",
}
#: Ở gốc ``tests/`` chỉ có cấu hình pytest, helper dùng chung giữa các nhóm và hai thư mục dữ liệu.
TEST_ROOT_FILES = {"conftest.py"}
TEST_ROOT_DIRS = {"fixtures", "frontend", "__pycache__"}
#: ``Path(__file__)…parents[N]`` trong phép kiểm: gốc kho là ``parents[2]``; ``parents[1]`` chỉ được
#: dùng để tới ``tests/fixtures``.
_FILE_PARENTS = re.compile(r"Path\(__file__\)(?:\.resolve\(\))?\.(?:parents\[(\d+)\]|parent\b)(\s*/\s*\S+)?")
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
    """Script nằm ngoài nhóm, tính gốc kho sai độ sâu, hoặc (Python) không nói nó làm gì."""
    bad = []
    for path in _files(scripts):
        rel = path.relative_to(scripts)
        if len(rel.parts) != 2 or rel.parts[0] not in SCRIPT_GROUPS:
            bad.append(f"{rel.as_posix()}: không thuộc nhóm nào trong {sorted(SCRIPT_GROUPS)}")
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py" and re.search(r"Path\(__file__\)\.resolve\(\)\.parents\[(?!2\])\d+\]", text):
            bad.append(f"{rel.as_posix()}: gốc kho phải là Path(__file__).resolve().parents[2]")
        if path.suffix == ".py" and not ast.get_docstring(ast.parse(text)):
            bad.append(f"{rel.as_posix()}: thiếu docstring nói script làm gì")
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


def layout_offenders_in_tests(tests: Path) -> list[str]:
    """Tệp lạc ở gốc ``tests/``, nhóm lạ, tên phép kiểm trùng giữa hai nhóm, hoặc tính gốc kho sai tầng.

    Tên trùng là lỗi thật: không có ``__init__.py`` thì pytest nạp phép kiểm theo TÊN TỆP, và tệp
    thứ hai cùng tên làm cả lượt thu thập dừng.
    """
    bad, seen = [], {}
    for path in sorted(tests.iterdir()):
        if path.is_file() and path.name not in TEST_ROOT_FILES and not path.name.endswith("_helpers.py"):
            bad.append(f"{path.name}: tệp ở gốc tests/ (phép kiểm vào tests/<nhóm>/, helper đặt tên *_helpers.py)")
        elif path.is_dir() and path.name not in TEST_ROOT_DIRS and path.name not in TEST_GROUPS:
            bad.append(f"{path.name}/: không thuộc nhóm nào trong {sorted(TEST_GROUPS)}")
    for path in sorted(tests.glob("*/*.py")):
        rel = path.relative_to(tests).as_posix()
        if path.parent.name not in TEST_GROUPS:
            continue
        if not path.name.startswith("test_"):
            bad.append(f"{rel}: trong nhóm chỉ có test_*.py")
        if path.name in seen:
            bad.append(f"{rel}: trùng tên với {seen[path.name]}")
        seen.setdefault(path.name, rel)
        source = path.read_text(encoding="utf-8")
        bad += [f"{rel}: {why}" for why in _cross_test_imports(source, path.parent, tests)]
        code = _code_only(source)
        for level, tail in _FILE_PARENTS.findall(code):
            if level == "2" or (level == "1" and tail.lstrip("/ ").startswith('"fixtures"')):
                continue
            bad.append(f"{rel}: gốc kho phải là Path(__file__).resolve().parents[2]")
    return bad


def _cross_test_imports(source: str, group: Path, tests: Path) -> list[str]:
    """Import tới tệp kiểm khác hay helper không tìm thấy, kể cả import trễ trong hàm.

    Phép kiểm chỉ được import tệp kiểm CÙNG nhóm (pytest đặt thư mục nhóm lên ``sys.path``) hoặc
    helper ``*_helpers.py`` ở gốc ``tests/``. ``from tests.test_x import …`` gắn vào bố cục cũ: sau khi
    chuyển nhóm nó hỏng ngay trong hàm, và ``pytest --collect-only`` không thấy.
    """
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top == "tests":
                bad.append(f"import {name}: import tệp cùng nhóm hoặc helper ở gốc tests/")
            elif top.startswith("test_") and not (group / f"{top}.py").is_file():
                bad.append(f"import {name}: không có tệp kiểm cùng nhóm tên ấy")
            elif top.endswith("_helpers") and not (tests / f"{top}.py").is_file():
                bad.append(f"import {name}: không có helper ấy ở gốc tests/")
    return bad


def _code_only(source: str) -> str:
    """Mã nguồn với chuỗi và chú thích đã thay tại chỗ: mẫu dựng sẵn trong chuỗi không phải lời gọi thật.

    Chuỗi đường dẫn bắt đầu bằng ``fixtures`` được giữ (thành ``"fixtures"``) để luật còn nhận ra
    ``parents[1] / "fixtures"``; mọi chuỗi khác thành ``""``, chú thích thành rỗng.
    """
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    out, last = [], 0
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        a = starts[tok.start[0] - 1] + tok.start[1]
        b = starts[tok.end[0] - 1] + tok.end[1]
        out.append(source[last:a])
        if tok.type == tokenize.STRING:
            try:
                value = ast.literal_eval(tok.string)
            except (ValueError, SyntaxError):
                value = None
            out.append('"fixtures"' if isinstance(value, str) and value.startswith("fixtures") else '""')
        last = b
    out.append(source[last:])
    return "".join(out)


#: Kiểm kê phụ thuộc đã đóng băng ở ngày lập: ghi đường dẫn của THỜI ĐIỂM ấy, không sửa theo.
FROZEN_SNAPSHOTS = {"documentation/qa/2026-10-09-python-dependencies.json"}
SCRIPT_REF = re.compile(
    r"(?<![\w/.-])(?:scripts/[\w/.-]+\.(?:py|sh)|tests/[\w/.-]+\.py|documentation/[\w/.-]+\.(?:md|json|gz))\b"
)


def dead_script_references(root: Path, files: list[str]) -> list[str]:
    """``scripts/…``, ``tests/…py`` hay ``documentation/…`` được nhắc trong tệp của kho mà không tồn tại.

    Tìm ở gốc kho hoặc ở ``vietlott/``.

    Engine Vietlott có ``scripts/`` riêng; workflow ``vlm-*`` chạy với ``working-directory: vietlott``.
    """
    bad = []
    for rel in files:
        if rel in FROZEN_SNAPSHOTS or rel.startswith(("vietlott/", "data/")):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for ref in sorted(set(SCRIPT_REF.findall(text))):
            if not (root / ref).exists() and not (root / "vietlott" / ref).exists():
                bad.append(f"{rel}: {ref}")
    return bad


def _tracked(root: Path) -> list[str]:
    import subprocess

    out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
    return out.stdout.split()


def test_docs_holds_only_the_published_site() -> None:
    assert not docs_offenders(ROOT / "docs")


def test_every_script_sits_in_a_group_and_finds_the_repository_root() -> None:
    assert not script_offenders(ROOT / "scripts")


def test_every_mention_of_a_script_points_at_a_file_that_exists() -> None:
    """Đổi chỗ hay xoá script mà còn sót đường dẫn cũ ở workflow, test, tài liệu hay lệnh tái lập."""
    own = Path(__file__).resolve().relative_to(ROOT).as_posix()     # mẫu dựng sẵn của chính luật
    assert not dead_script_references(ROOT, [f for f in _tracked(ROOT) if f != own])


def test_every_test_sits_in_a_functional_group() -> None:
    assert not layout_offenders_in_tests(ROOT / "tests")
    # Phép quét phải THẤY đủ nhóm: thiếu một nhóm là glob đã hỏng hoặc nhóm bị bỏ trống.
    groups = {p.parent.name for p in (ROOT / "tests").glob("*/test_*.py")}
    assert groups == set(TEST_GROUPS), groups ^ set(TEST_GROUPS)


def test_the_test_layout_rule_catches_a_stray_test(tmp_path: Path) -> None:
    """Ghim luật trên cây dựng sẵn: tệp lạc ở gốc, nhóm lạ, tên trùng, gốc kho sai tầng."""
    tests = tmp_path / "tests"
    for d in ("web", "core", "fixtures"):
        (tests / d).mkdir(parents=True)
    (tests / "conftest.py").write_text("", encoding="utf-8")
    (tests / "theme_helpers.py").write_text("", encoding="utf-8")
    (tests / "web" / "test_a.py").write_text(
        'ROOT = Path(__file__).resolve().parents[2]\n'
        'F = Path(__file__).resolve().parents[1] / "fixtures" / "x.html"\n'
        'SAMPLE = "ROOT = Path(__file__).resolve().parents[1]"  # mẫu trong chuỗi không tính\n',
        encoding="utf-8")
    assert layout_offenders_in_tests(tests) == []
    (tests / "test_loose.py").write_text("", encoding="utf-8")
    (tests / "misc").mkdir()
    (tests / "core" / "test_a.py").write_text("", encoding="utf-8")
    (tests / "core" / "test_b.py").write_text('ROOT = Path(__file__).resolve().parents[1]\nD = ROOT / "docs"\n',
                                             encoding="utf-8")
    (tests / "core" / "test_c.py").write_text('D = Path(__file__).parent / "data.json"\n', encoding="utf-8")
    (tests / "core" / "util.py").write_text("", encoding="utf-8")
    (tests / "core" / "test_d.py").write_text(
        "from test_b import X\nfrom theme_helpers import Y\n"
        "def f():\n    from tests.test_a import Z\n    from test_a_web import W\n    import gone_helpers\n",
        encoding="utf-8")
    found = [f.split(":")[0] for f in layout_offenders_in_tests(tests)]
    assert found == ["misc/", "test_loose.py", "core/test_b.py", "core/test_c.py",
                     "core/test_d.py", "core/test_d.py", "core/test_d.py", "core/util.py", "web/test_a.py"]


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
    (scripts / "ops" / "good.py").write_text('"""Việc."""\nROOT = Path(__file__).resolve().parents[2]\n',
                                         encoding="utf-8")
    (scripts / "release" / "good.sh").write_text(
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"\n', encoding="utf-8")
    assert script_offenders(scripts) == []
    (scripts / "loose.py").write_text("", encoding="utf-8")
    (scripts / "ops" / "shallow.py").write_text('"""Việc."""\nROOT = Path(__file__).resolve().parents[1]\n',
                                            encoding="utf-8")
    (scripts / "ops" / "mute.py").write_text("ROOT = Path(__file__).resolve().parents[2]\n", encoding="utf-8")
    (scripts / "release" / "shallow.sh").write_text(
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n', encoding="utf-8")
    found = script_offenders(scripts)
    assert [f.split(":")[0] for f in found] == ["loose.py", "ops/mute.py", "ops/shallow.py", "release/shallow.sh"]


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


def test_the_reference_rule_catches_a_stale_path(tmp_path: Path) -> None:
    (tmp_path / "scripts" / "ops").mkdir(parents=True)
    (tmp_path / "scripts" / "ops" / "tool.py").write_text("", encoding="utf-8")
    (tmp_path / "vietlott" / "scripts").mkdir(parents=True)
    (tmp_path / "vietlott" / "scripts" / "build_site.py").write_text("", encoding="utf-8")
    (tmp_path / "a.json").write_text('{"run": "python scripts/ops/tool.py; python scripts/build_site.py"}',
                                     encoding="utf-8")
    assert dead_script_references(tmp_path, ["a.json"]) == []
    (tmp_path / "b.md").write_text("python scripts/tool.py", encoding="utf-8")
    assert dead_script_references(tmp_path, ["a.json", "b.md"]) == ["b.md: scripts/tool.py"]
    # Đường dẫn phép kiểm cũng thế: ``tests/test_x.py`` sau khi chuyển vào nhóm là đường dẫn chết.
    (tmp_path / "tests" / "web").mkdir(parents=True)
    (tmp_path / "tests" / "web" / "test_x.py").write_text("", encoding="utf-8")
    (tmp_path / "c.yml").write_text("run: pytest tests/web/test_x.py::t tests/test_x.py vietlott/tests/test_y.py",
                                    encoding="utf-8")
    assert dead_script_references(tmp_path, ["c.yml"]) == ["c.yml: tests/test_x.py"]
    # Tài liệu chuyển nhóm (``documentation/ui/…`` -> ``documentation/architecture/…``) cũng thế.
    (tmp_path / "documentation" / "architecture").mkdir(parents=True)
    (tmp_path / "documentation" / "architecture" / "spec.md").write_text("", encoding="utf-8")
    (tmp_path / "d.md").write_text("`documentation/architecture/spec.md`, `documentation/ui/spec.md`", encoding="utf-8")
    assert dead_script_references(tmp_path, ["d.md"]) == ["d.md: documentation/ui/spec.md"]
