"""A merged PR must not cancel the main push before any CI job starts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


def _group(
    event: str,
    ref: str,
    *,
    pr: int = 0,
    workflow: str = "Kiểm thử liên tục",
    sha: str = "f3e833b",
) -> str:
    """Resolve the workflow's actual concurrency template for observed events."""
    config = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["concurrency"]
    context = {
        "github.workflow": workflow,
        "github.event_name": event,
        "github.ref": ref,
        "github.sha": sha,
        "github.event.pull_request.number": pr,
    }

    def resolve(match: re.Match) -> str:
        for field in match.group(1).split("||"):
            value = context[field.strip()]
            if value:
                return str(value)
        return ""

    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", resolve, config["group"])


@pytest.mark.parametrize(("event", "pr"), [("pull_request", 127), ("workflow_dispatch", 0)])
def test_main_push_cannot_be_cancelled_by_another_event(event: str, pr: int) -> None:
    # A PR event after merge uses refs/heads/main too. Concurrency happens
    # before the route job can skip the redundant PR checks.
    assert _group("push", "refs/heads/main") != _group(event, "refs/heads/main", pr=pr)


def test_merged_prs_do_not_cancel_each_other_on_the_base_ref() -> None:
    assert _group("pull_request", "refs/heads/main", pr=127) != _group(
        "pull_request", "refs/heads/main", pr=128
    )


def test_new_push_still_supersedes_old_checks_for_the_same_branch() -> None:
    assert _group("push", "refs/heads/main", sha="f3e833b") == _group(
        "push", "refs/heads/main", sha="01e5385"
    )
    assert _group("push", "refs/heads/main") != _group("push", "refs/heads/codex/fix")
    config = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["concurrency"]
    assert config["cancel-in-progress"] is True


def test_another_workflow_cannot_cancel_main_ci() -> None:
    assert _group("push", "refs/heads/main") != _group(
        "push", "refs/heads/main", workflow="Đồng bộ XSMT và XSMN"
    )
