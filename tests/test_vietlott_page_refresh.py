"""Trang công khai theo ngay lượt engine hợp lệ, không chạy mã từ nhánh lạ."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))


def test_page_refresh_follows_both_engine_workflows_without_a_cycle() -> None:
    document = _workflow("vietlott-results.yml")
    trigger = document[True]["workflow_run"]
    upstream = {_workflow(name)["name"] for name in ("vlm-results.yml", "vlm-update.yml")}
    assert set(trigger["workflows"]) == upstream
    assert document["name"] not in trigger["workflows"]
    assert trigger["types"] == ["completed"]
    assert trigger["branches"] == ["main"]
    checkout = next(s for s in document["jobs"]["build"]["steps"]
                    if str(s.get("uses", "")).startswith("actions/checkout"))
    assert "github.event.repository.default_branch" in checkout["with"]["ref"]


@pytest.mark.parametrize("event,conclusion,branch,repo,allowed", [
    ("workflow_run", "success", "main", "beuvivu/VLA", True),
    ("workflow_run", "failure", "main", "beuvivu/VLA", True),
    ("workflow_run", "cancelled", "main", "beuvivu/VLA", False),
    ("workflow_run", "skipped", "main", "beuvivu/VLA", False),
    ("workflow_run", "success", "feature", "beuvivu/VLA", False),
    ("workflow_run", "failure", "feature", "beuvivu/VLA", False),
    ("workflow_run", "success", "main", "someone/VLA", False),
    ("workflow_run", "failure", "main", "someone/VLA", False),
    ("push", None, None, None, True),
    ("schedule", None, None, None, True),
    ("workflow_dispatch", None, None, None, True),
])
def test_actual_build_guard_accepts_trusted_completed_updates_or_direct_events(
    event: str, conclusion: str | None, branch: str | None, repo: str | None, allowed: bool,
) -> None:
    # Đọc CHÍNH biểu thức trong workflow; chỉ đổi toán tử Boolean sang cú pháp Python.
    guard = _workflow("vietlott-results.yml")["jobs"]["build"]["if"]
    expression = guard.replace("&&", " and ").replace("||", " or ")
    github = SimpleNamespace(event_name=event, repository="beuvivu/VLA", event=SimpleNamespace(
        repository=SimpleNamespace(default_branch="main"),
        workflow_run=SimpleNamespace(conclusion=conclusion, head_branch=branch,
                                     head_repository=SimpleNamespace(full_name=repo)),
    ))
    assert eval(expression, {"__builtins__": {}}, {"github": github}) is allowed
