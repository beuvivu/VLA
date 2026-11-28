from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
VERSION_FILE = ".python-version"


def pinned_version(root: Path = ROOT) -> str:
    text = (root / VERSION_FILE).read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"3\.\d+", text), f"{VERSION_FILE} phải là '3.<minor>', không phải {text!r}"
    return text


def setup_python_steps(workflow: dict):
    for job_name, job in (workflow.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            if str(step.get("uses", "")).startswith("actions/setup-python@"):
                yield job_name, job, step


def violations(workflow: dict, version: str) -> list[str]:
    out = []
    for job_name, job, step in setup_python_steps(workflow):
        given = step.get("with") or {}
        if given.get("python-version-file") == VERSION_FILE and "python-version" not in given:
            continue
        if str(given.get("python-version", "")).strip() == "${{ matrix.python }}":
            matrix = (job.get("strategy") or {}).get("matrix") or {}
            listed = [str(v) for v in matrix.get("python") or []]
            listed += [str(extra.get("python")) for extra in matrix.get("include") or [] if "python" in extra]
            if version in listed:
                continue
            out.append(f"{job_name}: ma trận {listed} thiếu {version}")
            continue
        out.append(f"{job_name}: {given}")
    return out


def test_the_version_file_names_a_minor_release():
    pinned_version()


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_setup_python_step_reads_the_version_file(path):
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert violations(workflow, pinned_version()) == []


def test_the_workflow_rule_itself_catches_a_hard_coded_version():
    assert len(WORKFLOWS) > 20
    good = {"jobs": {"a": {"steps": [{"uses": "actions/setup-python@v7",
                                      "with": {"python-version-file": VERSION_FILE}}]}}}
    pinned = {"jobs": {"a": {"steps": [{"uses": "actions/setup-python@v7", "with": {"python-version": "3.11"}}]}}}
    both = {"jobs": {"a": {"steps": [{"uses": "actions/setup-python@v7",
                                      "with": {"python-version-file": VERSION_FILE, "python-version": "3.11"}}]}}}
    stale_matrix = {"jobs": {"a": {"strategy": {"matrix": {"python": ["3.11", "3.12"]}},
                                   "steps": [{"uses": "actions/setup-python@v7",
                                              "with": {"python-version": "${{ matrix.python }}"}}]}}}
    assert violations(good, "3.15") == []
    assert violations(pinned, "3.15") and violations(both, "3.15") and violations(stale_matrix, "3.15")


def test_ruff_targets_the_pinned_version():
    version = pinned_version()
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^target-version = "py(\d+)"', text, re.M).group(1) == version.replace(".", "")


def test_the_engine_container_runs_the_pinned_version():
    version = pinned_version()
    images = re.findall(r"^FROM python:(\d+\.\d+)", (ROOT / "vietlott" / "Dockerfile").read_text(encoding="utf-8"), re.M)
    assert images and set(images) == {version}


REQUIREMENT_FILES = ("requirements.txt", "requirements-live.txt", "requirements-ml-engine.txt", "requirements-dev.txt")


def requirement_pins(root: Path = ROOT) -> dict[str, str]:
    pins: dict[str, str] = {}
    for name in REQUIREMENT_FILES:
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([A-Za-z0-9_.-]+)==([^\s;#]+)", line)
            if match:
                pins[match.group(1).lower()] = match.group(2)
    return pins


def unpinned_requirements(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.\[\],-]+==[^\s;,<>=!~]+(\s*;.*)?", line):
            out.append(line)
    return out


def test_every_direct_requirement_is_pinned_to_one_version():
    found = {name: unpinned_requirements((ROOT / name).read_text(encoding="utf-8")) for name in REQUIREMENT_FILES}
    assert {name: lines for name, lines in found.items() if lines} == {}
    assert unpinned_requirements("-r requirements.txt\n# chú thích\nnumpy==2.5.4  # ghim\nlightgbm>=4.7.0,<5.0\npytest\n") == [
        "lightgbm>=4.7.0,<5.0", "pytest"]


def workflow_pins(paths=WORKFLOWS) -> dict[str, str]:
    pins: dict[str, str] = {}
    for path in paths:
        for line in re.findall(r"pip install([^\n]*)", Path(path).read_text(encoding="utf-8")):
            for token in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", line):
                match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s,;]+)", token.strip("\"'"))
                if match:
                    pins.setdefault(match.group(1).lower(), match.group(2))
    return pins


def inline_pin_drift(run_text: str, pins: dict[str, str]) -> list[str]:
    out = []
    lines = [line for raw in run_text.splitlines() if not raw.strip().startswith("#")
             for line in re.findall(r"pip install(.*)", raw)]
    for line in lines:
        for token in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", line):
            token = token.strip("\"'")
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s,;]+)", token)
            if match:
                if match.group(1).lower() in pins and pins[match.group(1).lower()] != match.group(2):
                    out.append(f"{match.group(1)}=={match.group(2)} (requirements: {pins[match.group(1).lower()]})")
                continue
            name = re.match(r"[A-Za-z0-9_.-]+", token)
            rest = token[name.end():].lstrip() if name else ""
            if name and name.group(0).lower() in pins and rest and rest[0] in "<>=!~":
                out.append(f"{token} (requirements: {pins[name.group(0).lower()]})")
            elif name and not rest and name.group(0).lower() in pins:
                out.append(f"{token} (không ghim; bản ghim: {pins[name.group(0).lower()]})")
    return out


def test_versions_pinned_inline_in_workflows_match_the_requirement_files():
    pins = {**workflow_pins(), **requirement_pins()}
    assert {"numpy", "pandas", "scikit-learn", "playwright"} <= set(pins)
    drift = {path.name: inline_pin_drift(path.read_text(encoding="utf-8"), pins) for path in WORKFLOWS}
    assert {name: found for name, found in drift.items() if found} == {}
    assert inline_pin_drift('python -m pip install "numpy==2.2.6" pandas==3.1.0', {"numpy": "2.5.4", "pandas": "3.1.0"}) == [
        "numpy==2.2.6 (requirements: 2.5.4)"]
    assert inline_pin_drift("""python -m pip install "pytest>=9.1.1,<10" 'numpy==2.5.4' playwright==1.55.0""",
                            {"numpy": "2.5.4", "pytest": "9.2.0"}) == ["pytest>=9.1.1,<10 (requirements: 9.2.0)"]
    assert inline_pin_drift("python -m pip install --upgrade pip wheel && pip install --no-cache-dir playwright",
                            {"playwright": "1.55.0"}) == ["playwright (không ghim; bản ghim: 1.55.0)"]
    assert inline_pin_drift("# lệnh `pip install` trần như playwright\n  # cũ: pip install numpy==2.2.6\n",
                            {"playwright": "1.55.0", "numpy": "2.5.4"}) == []
