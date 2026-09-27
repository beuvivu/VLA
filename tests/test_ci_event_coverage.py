"""PR từ nhánh ngoài allowlist push vẫn phải chạy đủ hai job CI."""

from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
REPOSITORY = "beuvivu/VLA"


def _route(script: str, event: str, branch: str, head_repo: str) -> tuple[int, str]:
    """Chạy nguyên khối shell của job chọn cổng và đọc đầu ra GitHub Actions."""
    with TemporaryDirectory() as dirname:
        output_path = Path(dirname) / "github-output"
        env = {
            **os.environ,
            "GITHUB_OUTPUT": str(output_path),
            "EVENT_NAME": event,
            "REPO_NAME": REPOSITORY,
            "HEAD_REPO": head_repo,
            "HEAD_REF": branch,
        }
        result = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, output_path.read_text() if output_path.exists() else ""


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _router(workflow: dict) -> str:
    route = workflow["jobs"]["route"]
    assert route["outputs"]["run_checks"] == "${{ steps.route.outputs.run_checks }}"
    steps = [step for step in route["steps"] if step.get("id") == "route"]
    assert len(steps) == 1
    assert steps[0]["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "REPO_NAME": "${{ github.repository }}",
        "HEAD_REPO": "${{ github.event.pull_request.head.repo.full_name }}",
        "HEAD_REF": "${{ github.event.pull_request.head.ref }}",
    }
    return steps[0]["run"]


@pytest.mark.parametrize("job", ["browser", "test"])
@pytest.mark.parametrize(
    ("event", "branch", "head_repo", "should_run"),
    [
        ("pull_request", "dependabot/pip/pytest-9", REPOSITORY, True),
        ("pull_request", "feature/navigation", REPOSITORY, True),
        ("pull_request", "some-arbitrary-branch", REPOSITORY, True),
        ("pull_request", "CODEX/ui-polish", REPOSITORY, True),
        ("pull_request", "CLAUDE/fix-workflow", REPOSITORY, True),
        ("pull_request", "MAIN", REPOSITORY, True),
        ("pull_request", "codex/ui-polish", REPOSITORY, False),
        ("pull_request", "claude/fix-workflow", REPOSITORY, False),
        ("pull_request", "main", REPOSITORY, False),
        ("pull_request", "master", REPOSITORY, False),
        ("pull_request", "codex/ui-polish", "contributor/VLA", True),
        ("pull_request", "feature/navigation", "contributor/VLA", True),
        ("workflow_dispatch", "", "", True),
        ("push", "codex/ui-polish", "", True),
        ("push", "claude/fix-workflow", "", True),
        ("push", "main", "", True),
        ("push", "master", "", True),
        ("push", "CODEX/ui-polish", "", False),
        ("push", "MAIN", "", False),
        ("push", "dependabot/pip/pytest-9", "", False),
        ("push", "feature/navigation", "", False),
        ("push", "live/daily-results", "", False),
    ],
)
def test_ci_event_coverage(
    job: str, event: str, branch: str, head_repo: str, should_run: bool
) -> None:
    workflow = _workflow()
    events = workflow.get("on", workflow.get(True))  # PyYAML 1.1 đọc `on` thành boolean.
    assert {"push", "pull_request", "workflow_dispatch"} <= set(events)
    push_branches = events["push"]["branches"]
    assert push_branches == ["main", "master", "claude/**", "codex/**"]

    gate = workflow["jobs"][job]
    assert gate["needs"] == "route"
    assert gate["if"] == "needs.route.outputs.run_checks == 'true'"
    script = _router(workflow)

    # Push ngoài allowlist không tạo lượt chạy workflow để job chọn cổng xử lý.
    if event == "push" and not any(
        fnmatch.fnmatchcase(branch, pattern) for pattern in push_branches
    ):
        assert not should_run
        return

    code, output = _route(script, event, branch, head_repo)
    assert code == 0, (event, branch, head_repo)
    assert output == f"run_checks={str(should_run).lower()}\n", (
        job, event, branch, head_repo, output
    )


@pytest.mark.parametrize(("branch", "head_repo"), [("", REPOSITORY), ("feature/x", "")])
def test_ci_does_not_silently_skip_pr_with_missing_metadata(
    branch: str, head_repo: str
) -> None:
    script = _router(_workflow())
    code, output = _route(script, "pull_request", branch, head_repo)
    assert code != 0
    assert not output


@pytest.mark.parametrize(
    "branch",
    ["main", "master", "claude/fix", "codex/fix", "MAIN", "CODEX/fix", "feature/fix", "dependabot/pip/pytest"],
)
def test_internal_pr_has_exactly_one_check_run(branch: str) -> None:
    workflow = _workflow()
    events = workflow.get("on", workflow.get(True))
    push_matches = any(
        fnmatch.fnmatchcase(branch, pattern) for pattern in events["push"]["branches"]
    )
    code, output = _route(_router(workflow), "pull_request", branch, REPOSITORY)
    assert code == 0
    pr_checks = output == "run_checks=true\n"
    assert int(push_matches) + int(pr_checks) == 1, branch
