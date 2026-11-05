"""Bước pytest của job Chromium chạy trên máy CHỈ có playwright và pytest: chuỗi import của nó không
được kéo theo pandas, numpy hay các gói phân tích khác.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _jobs() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


#: Gói mà job Chromium KHÔNG cài (nó chỉ cài playwright và pytest).
NOT_IN_BROWSER_JOB = ("pandas", "numpy", "scipy", "sklearn", "joblib", "jinja2", "bs4")


def test_the_browser_job_can_import_what_its_pytest_step_imports_without_the_analysis_stack() -> None:
    """Bước pytest của job Chromium chạy trên máy chỉ có playwright và pytest.

    Ngày 05-11-2026 ``web.page_output`` bắt đầu nhập ``core.atomic_io``, vốn nhập pandas ở đầu tệp,
    và job đỏ sau 35 giây ở PR #212: hàm kiểm menu điện thoại nhập ``web.ui_theme`` trong thân hàm.
    Phép kiểm đọc mọi lệnh import của đúng hàm kiểm ấy rồi nhập chúng khi các gói phân tích bị chặn.
    """
    step = next(s for s in _jobs()["browser"]["steps"] if "pytest" in s.get("run", "") and "tests/" in s["run"])
    target = next(part for part in step["run"].split() if part.startswith("tests/"))
    path, _, name = target.partition("::")
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)
    modules = sorted({node.module for node in ast.walk(function) if isinstance(node, ast.ImportFrom) and node.module}
                     | {alias.name for node in ast.walk(function) if isinstance(node, ast.Import) for alias in node.names})
    assert modules, "hàm kiểm không nhập gì: phép kiểm này không còn canh được chuỗi import"
    blocker = "; ".join(f"sys.modules[{blocked!r}] = None" for blocked in NOT_IN_BROWSER_JOB)
    imports = "; ".join(f"importlib.import_module({module!r})" for module in modules)
    code = f"import importlib, sys; sys.path.insert(0, 'src'); {blocker}; {imports}"
    result = subprocess.run(  # noqa: S603 — lệnh dựng từ hằng của chính phép kiểm
        [sys.executable, "-c", code], check=False, cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, f"{modules}: " + result.stderr[-2000:]
