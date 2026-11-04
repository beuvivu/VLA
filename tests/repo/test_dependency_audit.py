"""Job kiểm lỗ hổng hằng tuần (`dependency-audit.yml`) chấm MỌI gói chạy trên runner (04-11-2026).

Dependabot không cập nhật pip cho Python 3.15, nên job này là cảnh báo bảo mật duy nhất của gói Python.
Ngoài requirements, nó phải cài cả gói mà workflow ghim thẳng trong lệnh `pip install` (như playwright
của job Chromium) — Codex chỉ ra gói ấy lọt khỏi bản đầu. Phép kiểm chạy đúng khối Python của bước ấy,
lấy từ YAML, trên kho thật.
"""
from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

from test_python_version import requirement_pins

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "dependency-audit.yml"


def _inline_step() -> str:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["vla"]["steps"]
    found = [step["run"] for step in steps if "ghim thẳng" in str(step.get("name", ""))]
    assert len(found) == 1, "job vla phải có đúng một bước cài gói ghim thẳng trong workflow"
    return found[0]


def test_the_audit_installs_every_package_a_workflow_pins_inline() -> None:
    run = _inline_step()
    code = re.search(r"<<'PY'\n(.*?)\nPY\n", run, re.S)
    assert code, "bước phải dựng danh sách bằng khối Python <<'PY'"
    out = subprocess.run([sys.executable, "-"], input=textwrap.dedent(code.group(1)), cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    assert "playwright==1.55.0" in out
    pins = requirement_pins()
    assert [line for line in out if line.split("==")[0].lower() in pins] == [], "gói đã có trong requirements"
    assert "pip install --no-cache-dir -r inline-pins.txt" in run


def test_the_audit_runs_after_both_installs_and_fails_on_findings() -> None:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["vla"]["steps"]
    names = [str(step.get("name", "")) for step in steps]
    assert names.index("Đối chiếu với cơ sở lỗ hổng") > names.index("Cài thêm gói mà workflow ghim thẳng trong lệnh cài")
    assert 'exit "$status"' in steps[-1]["run"] and "--strict" in steps[-1]["run"]
