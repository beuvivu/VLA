"""Workflow dùng token của job để dispatch phải được cấp quyền Actions ghi."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _dispatch_permission_issues(document: dict) -> list[str]:
    """Quyền cấp job thay toàn bộ quyền workflow, không cộng dồn từng khóa."""
    issues: list[str] = []
    for name, job in document.get("jobs", {}).items():
        runs = "\n".join(step.get("run", "") for step in job.get("steps", []))
        if "/actions/workflows/" not in runs or "/dispatches" not in runs:
            continue
        effective = job.get("permissions", document.get("permissions", {}))
        allowed = effective == "write-all" or (
            isinstance(effective, dict) and effective.get("actions") == "write"
        )
        if not allowed:
            issues.append(name)
    return issues


@pytest.mark.parametrize(
    ("workflow_permissions", "job_permissions", "expected"),
    [
        ({"contents": "read"}, None, ["collect"]),
        ({"actions": "read"}, None, ["collect"]),
        ({"actions": "write"}, None, []),
        ({"actions": "write"}, {"contents": "read"}, ["collect"]),
        ({"actions": "write"}, {"actions": "read"}, ["collect"]),
        ({"contents": "read"}, {"actions": "write"}, []),
        ("read-all", None, ["collect"]),
        ("write-all", None, []),
        ("write-all", {}, ["collect"]),
    ],
)
def test_dispatch_permission_gate_handles_job_overrides(
    workflow_permissions, job_permissions, expected,
) -> None:
    """Ghim luật trên mẫu để thiếu quyền không thể bị bỏ qua lặng lẽ."""
    job = {"steps": [{"run": 'POST /repos/owner/repo/actions/workflows/update.yml/dispatches'}]}
    if job_permissions is not None:
        job["permissions"] = job_permissions
    document = {"permissions": workflow_permissions, "jobs": {"collect": job}}
    assert _dispatch_permission_issues(document) == expected


def test_every_workflow_dispatch_job_has_actions_write_permission() -> None:
    offenders: list[str] = []
    dispatch_workflows: set[str] = set()
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "/actions/workflows/" in path.read_text(encoding="utf-8"):
            dispatch_workflows.add(path.name)
        offenders.extend(f"{path.name}:{job}" for job in _dispatch_permission_issues(document))
    assert {"daily_update.yml", "live-results.yml", "update-data.yml", "watchdog.yml"} <= dispatch_workflows
    assert not offenders, "Thiếu actions: write ở job dispatch: " + ", ".join(offenders)
