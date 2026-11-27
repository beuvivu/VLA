from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from ingest import sources

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

UNTRUSTED = re.compile(
    r"\$\{\{\s*(?:github\.event\.)?"
    r"(inputs|client_payload|issue|pull_request|comment|head_commit)\."
)


def _run_blocks(document: dict) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for job_name, job in (document.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                found.append((f"{job_name}/{step.get('name', '?')}", step["run"]))
    return found


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_no_untrusted_context_is_interpolated_into_a_shell_block(workflow: Path) -> None:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    offenders = [
        f"{where}: {UNTRUSTED.search(script).group(0)}"
        for where, script in _run_blocks(document)
        if UNTRUSTED.search(script)
    ]
    assert not offenders, f"{workflow.name} nội suy ngữ cảnh không tin cậy vào shell: {offenders}"


def jobs_without_token_scope(document: dict) -> list[str]:
    if "permissions" in document:
        return []
    jobs = document.get("jobs") or {}
    if not jobs:
        return ["<không có job>"]
    return [name for name, job in jobs.items() if "permissions" not in (job or {})]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_workflow_declares_its_token_scope(workflow: Path) -> None:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    thieu = jobs_without_token_scope(document)
    assert not thieu, f"{workflow.name}: job thiếu khai báo permissions: {thieu}"


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"permissions": {"contents": "read"}, "jobs": {"a": {}}}, []),
        ({"jobs": {"a": {"permissions": {"contents": "write"}}}}, []),
        (
            {
                "jobs": {
                    "a": {"permissions": {"contents": "read"}},
                    "b": {"runs-on": "ubuntu-latest"},
                }
            },
            ["b"],
        ),
        ({"jobs": {"a": None}}, ["a"]),
        ({"name": "chỉ có tên"}, ["<không có job>"]),
    ],
    ids=["cấp tài liệu", "cấp job", "một job thiếu", "job rỗng", "không có job"],
)
def test_the_token_scope_rule_requires_every_job_not_merely_one(
    document: dict, expected: list[str]
) -> None:
    assert jobs_without_token_scope(document) == expected


class _Response:
    def __init__(self, text: str, *, status: int = 200, headers: dict | None = None) -> None:
        self.text = text
        self.status_code = status
        self.headers = headers or {}


class _Client:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls = 0

    def get(self, url: str, timeout: int | float = 20, **kwargs: object) -> _Response:
        self.calls += 1
        return self.response


def test_a_page_within_the_cap_passes_through_untouched() -> None:
    body = "<html>" + "x" * 1000 + "</html>"
    client = _Client(_Response(body, headers={"Content-Length": str(len(body))}))
    assert sources._request_page(client, "https://nguon/x") == body


def test_a_body_declared_larger_than_the_cap_is_refused_before_parsing() -> None:
    huge = sources.MAX_PAGE_BYTES + 1
    client = _Client(_Response("nội dung", headers={"Content-Length": str(huge)}))
    assert sources._request_page(client, "https://nguon/x") == ""


def test_a_body_that_lies_about_its_length_is_still_refused() -> None:
    oversized = "x" * (sources.MAX_PAGE_BYTES + 1)
    for headers in ({}, {"Content-Length": "42"}, {"Content-Length": "không phải số"}):
        client = _Client(_Response(oversized, headers=headers))
        assert sources._request_page(client, "https://nguon/x") == "", headers


def test_the_cap_is_generous_enough_for_a_real_results_page() -> None:
    assert sources.MAX_PAGE_BYTES >= 4 * 1024 * 1024
    realistic = "<html>" + "y" * (600 * 1024) + "</html>"
    client = _Client(_Response(realistic))
    assert sources._request_page(client, "https://nguon/x") == realistic
