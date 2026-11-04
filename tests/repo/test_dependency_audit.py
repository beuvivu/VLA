"""Job kiểm lỗ hổng hằng tuần (`dependency-audit.yml`) chấm MỌI gói chạy trên runner (04-11-2026).

Dependabot không cập nhật pip cho Python 3.15, nên job này là cảnh báo bảo mật duy nhất của gói Python.
Ngoài requirements, nó phải cài cả gói mà workflow cài thẳng trong lệnh `pip install` (playwright của job
Chromium, build của vlm-release.yml) và mọi phần tuỳ chọn của engine mà workflow cài (xgboost/lightgbm
của job ML) — bốn góp ý Codex trên PR #206 chỉ ra từng gói lọt khỏi bản trước. Tập gói tính bằng
`scripts/ops/audit_install_set.py`; luật đọc lệnh cài được ghim trên workflow dựng sẵn, còn phép trên kho
thật canh rằng các gói đã biết vẫn nằm trong tập.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

from test_python_version import requirement_pins

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "dependency-audit.yml"
SCRIPT = ROOT / "scripts" / "ops" / "audit_install_set.py"

_spec = importlib.util.spec_from_file_location("audit_install_set", SCRIPT)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def _steps(job: str) -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"][job]["steps"]


def _fake_repo(tmp_path: Path, workflows: dict[str, str], requirements: str = "requests==2.32.5\n") -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    for name, text in workflows.items():
        (tmp_path / ".github" / "workflows" / name).write_text(text, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(requirements, encoding="utf-8")
    return tmp_path


FAKE = """
defaults:
  run:
    working-directory: vietlott
jobs:
  a:
    steps:
      - run: |
          # python -m pip install commented==1.0
          # cũ: cd x; pip install retired==0.1
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt playwright==1.55.0 requests
          pip install build && python -m build
          python -m pip install -e ".[dev,crawler]"
          python -m pip install \\
            joined==2.0
  b:
    defaults:
      run:
        working-directory: .
    steps:
      - run: python -m pip install -e ".[root]" bare
      - working-directory: vietlott
        run: python -m pip install ".[ml]" "$PKG" ./wheel.whl
"""


def test_the_install_set_follows_what_workflows_really_run(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path, {"x.yml": FAKE})
    assert audit.extra_requirements(root) == ["bare", "build", "joined==2.0", "pip", "playwright==1.55.0"]
    # Phần tuỳ chọn chỉ tính bước chạy trong vietlott/ (mặc định của workflow, của job, hay của bước).
    assert audit.engine_extras(root) == ["crawler", "dev", "ml"]


def test_a_pinned_install_wins_over_a_bare_one(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path, {"a.yml": "jobs:\n  a:\n    steps:\n      - run: pip install build\n",
                                 "b.yml": "jobs:\n  b:\n    steps:\n      - run: pip install build==1.3.0\n"})
    assert audit.extra_requirements(root) == ["build==1.3.0"]


def test_the_real_install_set_covers_every_package_codex_found_missing() -> None:
    extra = audit.extra_requirements()
    assert {"playwright==1.55.0", "build"} <= set(extra)
    pins = requirement_pins()
    assert [line for line in extra if line.split("==")[0].lower() in pins] == [], "gói đã có trong requirements"
    extras = audit.engine_extras()
    assert {"dev", "crawler", "ml"} <= set(extras)
    declared = tomllib.loads((ROOT / "vietlott" / "pyproject.toml").read_text(encoding="utf-8"))
    assert set(extras) <= set(declared["project"]["optional-dependencies"]), "phần tuỳ chọn engine không khai"


def test_the_vla_job_installs_the_computed_set_before_auditing() -> None:
    steps = _steps("vla")
    runs = [str(step.get("run", "")) for step in steps]
    extra = next(i for i, run in enumerate(runs) if "scripts/ops/audit_install_set.py > audit-extra.txt" in run)
    assert "python -m pip install --no-cache-dir -r audit-extra.txt" in runs[extra]
    audit_step = next(i for i, run in enumerate(runs) if "pip_audit" in run)
    assert audit_step > extra
    assert 'exit "$status"' in runs[audit_step] and "--strict" in runs[audit_step]


def test_the_engine_job_installs_every_extra_a_workflow_installs() -> None:
    steps = _steps("vietlott")
    runs = [str(step.get("run", "")) for step in steps]
    install = next(i for i, run in enumerate(runs) if "--engine-extras" in run)
    assert 'extras=$(python ../scripts/ops/audit_install_set.py --engine-extras)' in runs[install]
    assert 'pip install --no-cache-dir -e ".[$extras]"' in runs[install]
    audit_step = next(i for i, run in enumerate(runs) if "pip_audit" in run)
    assert audit_step > install
    assert 'exit "$status"' in runs[audit_step] and "--strict" in runs[audit_step]


@pytest.mark.parametrize("argv, expected", [([], "playwright==1.55.0"), (["--engine-extras"], "ml")])
def test_the_script_prints_what_the_workflow_reads(argv: list[str], expected: str,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    assert audit.main(argv) == 0
    assert expected in capsys.readouterr().out


# --- Bước đối chiếu, chạy thật bằng bash -e như GitHub ---------------------------------------------------
# Lượt đầu trên main (04-11-2026) đỏ cả hai job dù không có lỗ hổng nào: pip-audit KHÔNG ghi `--output` khi
# không có gì để báo nên `cat audit.md` hỏng dưới `bash -e`, và `--strict` coi gói editable bị
# `--skip-editable` bỏ qua là lỗi chí mạng. `python` giả dưới đây mô phỏng đúng hai hành vi đã đo ấy của
# pip-audit 2.10.1; mọi lệnh khác làm nó dừng với mã 97.
FAKE_PYTHON = r"""#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG"
if [ "$1 $2 $3" = "-m pip freeze" ]; then
  echo "numpy==2.5.4"
  case " $* " in *" --exclude-editable "*) ;; *) echo "-e /work/vietlott" ;; esac
  exit 0
fi
if [ "$1 $2" = "-m pip_audit" ]; then
  out=""; req=""; prev=""
  for a in "$@"; do
    [ "$prev" = "--output" ] && out="$a"
    [ "$prev" = "-r" ] && req="$a"
    prev="$a"
  done
  case " $* " in
    *" --strict "*)
      if [ -n "$req" ] && grep -q "^-e " "$req"; then echo "ERROR: editable" >&2; exit 1; fi
      if [ -z "$req" ] && [ "$STUB_EDITABLE" = 1 ]; then echo "ERROR: distribution marked as editable" >&2; exit 1; fi ;;
  esac
  case "$STUB_OUTCOME" in
    clean) echo "No known vulnerabilities found" >&2; exit 0 ;;
    vulns) printf "Name | Version | ID\n--- | --- | ---\nurllib3 | 1.26.0 | PYSEC-2021-108\n" > "$out"; exit 1 ;;
    broken) echo "network error" >&2; exit 2 ;;
  esac
fi
echo "lệnh python không lường trước: $*" >&2
exit 97
"""
HEADINGS = {"vla": "## Gói của pipeline và bộ kiểm", "vietlott": "## Gói của engine Vietlott"}


@pytest.mark.skipif(shutil.which("bash") is None, reason="cần bash")
@pytest.mark.parametrize("job", ["vla", "vietlott"])
@pytest.mark.parametrize(("outcome", "code", "line"), [
    ("clean", 0, "Không có lỗ hổng đã biết."),
    ("vulns", 1, "urllib3 | 1.26.0 | PYSEC-2021-108"),
    ("broken", 2, "pip-audit dừng với mã 2 mà không ghi bảng"),
])
def test_the_audit_step_turns_red_only_on_findings_and_always_reports(
        tmp_path: Path, job: str, outcome: str, code: int, line: str) -> None:
    step = next(step for step in _steps(job) if "pip_audit" in str(step.get("run", "")))
    assert "shell" not in step, "khối chạy bằng shell mặc định của GitHub: bash -e"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "python"
    fake.write_text(FAKE_PYTHON, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    script = tmp_path / "step.sh"
    script.write_text(step["run"], encoding="utf-8")
    summary = tmp_path / "summary.md"
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "GITHUB_STEP_SUMMARY": str(summary),
           "STUB_OUTCOME": outcome, "STUB_EDITABLE": "1" if job == "vietlott" else "0",
           "STUB_LOG": str(tmp_path / "calls.log")}
    work = tmp_path / "work"
    work.mkdir()
    result = subprocess.run(["bash", "-e", str(script)], check=False, cwd=work, env=env, capture_output=True, text=True)
    assert result.returncode == code, result.stderr
    text = summary.read_text(encoding="utf-8")
    assert text.startswith(HEADINGS[job]) and line in text, text
    assert "--strict" in (tmp_path / "calls.log").read_text(encoding="utf-8")
