"""Bố cục ``src/`` sau khi gom module phẳng vào gói con theo chức năng (23-10-2026).

``src/`` từng có 145 module ngang hàng. Nay mỗi module nằm trong một gói (``core``,
``ingest``, ``ensemble``, ``stats``, ``soi_cau``, ``ml``, ``forecast``, ``evaluation``,
``research``, ``web``, ``pages`` và các gói có sẵn); gốc ``src/`` chỉ còn ``pipeline.py``.
Tên module giữ nguyên nên nhãn đã ghi vào sổ (``calendar_alignment.known_non_draw_days``)
vẫn đúng.

Các phép kiểm dưới đây canh những thứ hỏng LẶNG LẼ khi bố cục trôi:

* import theo tên phẳng cũ chỉ chạy được khi kịch bản đứng cùng thư mục với module ấy;
* gói phụ thuộc vòng thì thứ tự import quyết định module nào còn dở dang;
* ``Path(__file__).parents[1]`` trong gói con trỏ vào ``src/``, không phải gốc kho;
* bước workflow chạy ``python src/<gói>/<module>.py`` mà thiếu ``src`` trên ``PYTHONPATH``;
* pack joblib ghi trước đợt gom nhắc lớp bằng tên module phẳng ``ml_models``.
"""

from __future__ import annotations

import ast
import os
import pickle
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
#: Thư mục dưới ``src/`` không phải gói Python.
NOT_PACKAGES = {"assets", "__pycache__"}
#: Hai nơi DUY NHẤT được tính đường dẫn từ ``__file__``: hằng số đường dẫn của kho, và
#: bộ nạp mẫu nằm ngay trong thư mục mẫu.
FILE_RELATIVE_ALLOWED = {"core/paths.py", "templates/__init__.py"}
#: Mọi nơi nạp pack joblib của production.
MODEL_LOADERS = (
    "ml.ml_predict",
    "forecast.predict_nextday_2d",
    "ml.cau_keo_ml",
    "ml.validate_cau_keo_domain",
    "ml.cau_keo_domain_challenger",
)


def _python_files(*bases: Path) -> list[Path]:
    return sorted(p for base in bases for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def top_level_names(src: Path) -> set[str]:
    """Tên import được ở cấp cao nhất khi ``src`` nằm trên ``sys.path``."""
    names = {p.stem for p in src.glob("*.py")}
    names |= {p.name for p in src.iterdir() if p.is_dir() and (p / "__init__.py").is_file()}
    return names


def nested_module_names(src: Path) -> set[str]:
    """Tên module chỉ còn tồn tại TRONG gói, tức tên phẳng cũ không còn import được."""
    nested = {p.stem for p in src.glob("*/*.py") if p.stem != "__init__"}
    return nested - top_level_names(src)


def flat_imports(source: str, flat: set[str]) -> list[str]:
    """Các import theo tên phẳng (``import x`` / ``from x import y``) trong một tệp Python."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in flat]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] in flat:
                found.append(node.module)
    return found


#: Mã Python nằm trong văn bản khác: khối ``run:`` của workflow, shell, kiểm thử Node.
_EMBEDDED_IMPORT = re.compile(r"(?:^|[\s;'\"(])(?:from\s+(\w+)(?:\.\w+)*\s+import|import\s+(\w+))\b", re.M)


def embedded_flat_imports(text: str, flat: set[str]) -> list[str]:
    return [a or b for a, b in _EMBEDDED_IMPORT.findall(text) if (a or b) in flat]


def package_graph(src: Path) -> dict[str, set[str]]:
    """Gói -> các gói nó import (kể cả import trễ trong hàm)."""
    packages = {p.name for p in src.iterdir() if p.is_dir() and (p / "__init__.py").is_file()}
    graph: dict[str, set[str]] = {p: set() for p in packages}
    for path in _python_files(src):
        rel = path.relative_to(src)
        if len(rel.parts) < 2:
            continue
        owner = rel.parts[0]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                tops = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                tops = [node.module.split(".")[0]]
            else:
                continue
            graph[owner] |= {t for t in tops if t in packages and t != owner}
    return graph


def find_cycle(graph: dict[str, set[str]]) -> list[str]:
    """Một vòng phụ thuộc (danh sách gói, đầu = cuối), hoặc rỗng nếu đồ thị không vòng."""
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        state[node] = 1
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if nxt not in state:
                cycle = visit(nxt)
                if cycle:
                    return cycle
        stack.pop()
        state[node] = 2
        return []

    for node in sorted(graph):
        if node not in state:
            cycle = visit(node)
            if cycle:
                return cycle
    return []


def jobs_missing_pythonpath(document: dict) -> list[str]:
    """Job chạy kịch bản trong gói con của ``src/`` mà không có ``src`` trên ``PYTHONPATH``.

    ``python src/<gói>/<module>.py`` đặt ``src/<gói>`` lên ``sys.path``, KHÔNG phải ``src``,
    nên ``from core.time_policy import ...`` hỏng ngay dòng đầu.
    """
    missing = []
    workflow_env = document.get("env") or {}
    for name, job in (document.get("jobs") or {}).items():
        job_env = (job or {}).get("env") or {}
        for step in (job or {}).get("steps") or []:
            run = step.get("run") if isinstance(step, dict) else None
            if not isinstance(run, str) or not re.search(r"\bsrc/\w+/[\w/]+\.py\b", run):
                continue
            envs = (workflow_env, job_env, step.get("env") or {})
            if not any("PYTHONPATH" in env for env in envs) and "PYTHONPATH=" not in run:
                missing.append(f"{name}: {step.get('name', run.splitlines()[0])}")
    return missing


# --- Luật được ghim trên dữ liệu dựng sẵn: phép quét rỗng không thể đỏ. -----------------


def test_the_flat_import_rule_itself_catches_a_flat_import() -> None:
    sample = "import ensemble_utils\nfrom core import atomic_io\ndef f():\n    from lottery import Lottery\n"
    assert flat_imports(sample, {"ensemble_utils", "atomic_io", "lottery"}) == ["ensemble_utils", "lottery"]
    assert embedded_flat_imports("python -c 'from lottery import Lottery'", {"lottery"}) == ["lottery"]
    assert embedded_flat_imports("python -c 'from ingest.lottery import Lottery'", {"lottery"}) == []


def test_the_cycle_rule_itself_catches_a_cycle() -> None:
    assert find_cycle({"a": {"b"}, "b": {"c"}, "c": {"a"}}) == ["a", "b", "c", "a"]
    assert find_cycle({"a": {"b"}, "b": {"c"}, "c": set()}) == []


def test_the_pythonpath_rule_itself_catches_a_job_without_it() -> None:
    step = {"name": "Dựng", "run": "python src/pages/build_docs.py"}
    assert jobs_missing_pythonpath({"jobs": {"j": {"steps": [step]}}}) == ["j: Dựng"]
    assert jobs_missing_pythonpath({"jobs": {"j": {"env": {"PYTHONPATH": "src"}, "steps": [step]}}}) == []
    assert jobs_missing_pythonpath({"jobs": {"j": {"steps": [{"run": "python src/pipeline.py"}]}}}) == []


# --- Bố cục thật. -----------------------------------------------------------------------


def test_src_root_holds_only_the_pipeline_entry_point() -> None:
    assert sorted(p.name for p in SRC.glob("*.py")) == ["pipeline.py"]


def test_every_directory_under_src_is_a_documented_package() -> None:
    for directory in sorted(p for p in SRC.iterdir() if p.is_dir() and p.name not in NOT_PACKAGES):
        init = directory / "__init__.py"
        assert init.is_file(), directory.name
        assert ast.get_docstring(ast.parse(init.read_text(encoding="utf-8"))), directory.name


def test_nested_names_really_are_the_old_flat_modules() -> None:
    """Tập tên phẳng phải chứa các module đã chuyển, nếu không phép quét dưới vô dụng."""
    flat = nested_module_names(SRC)
    assert {"ensemble_utils", "lottery", "ui_theme", "atomic_io", "ml_models"} <= flat
    assert "pipeline" not in flat and "features" not in flat


def test_nothing_imports_a_module_by_its_old_flat_name() -> None:
    flat = nested_module_names(SRC)
    offenders = []
    for path in _python_files(SRC, ROOT / "tests", ROOT / "scripts"):
        names = flat_imports(path.read_text(encoding="utf-8"), flat)
        offenders += [f"{path.relative_to(ROOT)}: {name}" for name in names]
    embedded = [
        *(ROOT / ".github" / "workflows").glob("*.yml"),
        *(ROOT / "scripts").rglob("*.sh"),
        *(ROOT / "tests" / "frontend").glob("*.mjs"),
    ]
    for path in embedded:
        names = embedded_flat_imports(path.read_text(encoding="utf-8"), flat)
        offenders += [f"{path.relative_to(ROOT)}: {name}" for name in names]
    assert not offenders, offenders


def test_packages_under_src_depend_on_each_other_without_a_cycle() -> None:
    graph = package_graph(SRC)
    assert graph["pages"] and graph["core"] == set(), graph
    assert find_cycle(graph) == []


def test_repository_paths_are_computed_once() -> None:
    from core import paths

    assert (paths.REPO_ROOT / "CLAUDE.md").is_file()
    assert (paths.TEMPLATES / "app_shell.css").is_file()
    assert (paths.ASSETS / "app-shell.js").is_file()
    offenders = [
        str(path.relative_to(SRC))
        for path in _python_files(SRC)
        if "__file__" in path.read_text(encoding="utf-8")
        and path.relative_to(SRC).as_posix() not in FILE_RELATIVE_ALLOWED
    ]
    assert not offenders, offenders


def test_non_draw_calendar_is_read_from_the_repository_data() -> None:
    """Đường dẫn sai không báo lỗi: lịch ngày nghỉ chỉ rỗng đi."""
    from core.calendar_alignment import known_non_draw_days

    assert known_non_draw_days(), "data/non_draw_days.json không được đọc"


def test_workflow_jobs_running_src_packages_put_src_on_pythonpath() -> None:
    offenders = []
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        document = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        offenders += [f"{workflow.name}:{job}" for job in jobs_missing_pythonpath(document)]
    assert not offenders, offenders


def test_pipeline_steps_get_src_on_pythonpath() -> None:
    import pipeline

    env = pipeline._child_env()
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(SRC)


def _child(code: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, text=True,
                          capture_output=True, check=False, timeout=180)


def test_a_pack_pickled_under_the_old_flat_module_name_still_loads() -> None:
    from ml.ml_models import PlattCalibratedClassifier

    legacy = pickle.dumps(PlattCalibratedClassifier(), protocol=2).replace(
        b"cml.ml_models\n", b"cml_models\n"
    )
    assert b"cml_models\nPlattCalibratedClassifier" in legacy
    code = (
        "import pickle, sys\n"
        "import ml.ml_predict\n"
        f"obj = pickle.loads({legacy!r})\n"
        "print(type(obj).__module__)\n"
    )
    run = _child(code)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "ml.ml_models"


@pytest.mark.parametrize("loader", MODEL_LOADERS)
def test_every_model_loader_reads_the_committed_packs(loader: str) -> None:
    """Mỗi nơi nạp pack, trong một tiến trình MỚI, đọc được mọi pack đã commit."""
    packs = sorted((ROOT / "models").glob("*.joblib"))
    assert packs
    code = (
        "import joblib, sys\n"
        f"import {loader}\n"
        f"for path in {[str(p) for p in packs]!r}:\n"
        "    joblib.load(path)\n"
        "print('ok')\n"
    )
    run = _child(code)
    assert run.returncode == 0, run.stderr[-2000:]
    assert run.stdout.strip() == "ok"
