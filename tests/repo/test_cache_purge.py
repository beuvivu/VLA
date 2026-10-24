from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import purge_github_caches as purge  # noqa: E402


REPOSITORY = "beuvivu/VLA"
BASE_URL = f"https://api.github.com/repos/{REPOSITORY}/actions/caches"
LIST_URL = f"{BASE_URL}?per_page=100&page=1"
FAKE_TOKEN = "only-a-test-token"


@pytest.fixture(autouse=True)
def no_live_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không phép kiểm nào được chạm mạng hoặc dùng token của môi trường."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        purge.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("live API called")
    )


def _listing(ids: list[object]) -> tuple[int, object]:
    return 200, {"actions_caches": [{"id": cache_id} for cache_id in ids]}


def _http(
    monkeypatch: pytest.MonkeyPatch,
    replies: list[tuple[int, object] | Exception],
) -> list[tuple[str, str]]:
    """Giả lập đúng biên HTTP; vẫn chạy logic phân trang và xử lý lỗi thật."""
    pending = iter(replies)
    calls: list[tuple[str, str]] = []

    def urlopen(request, *, timeout: int):
        calls.append((request.method, request.full_url))
        assert request.get_header("Authorization") == f"Bearer {FAKE_TOKEN}"
        assert timeout > 0
        try:
            reply = next(pending)
        except StopIteration:
            pytest.fail(f"unexpected API call: {calls[-1]}")
        if isinstance(reply, Exception):
            raise reply
        status, payload = reply
        raw = b"" if payload is None else json.dumps(payload).encode()
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "API error", None, io.BytesIO(raw))
        response = io.BytesIO(raw)
        response.status = status
        return response

    monkeypatch.setattr(purge.urllib.request, "urlopen", urlopen)
    return calls


def test_purge_requires_explicit_confirmation() -> None:
    with pytest.raises(ValueError, match="--confirm"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=False)


def test_purge_snapshots_101_caches_before_deleting_each_id_and_verifies(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _http(
        monkeypatch,
        [_listing(list(range(1, 101))), _listing([101])]
        + [(204, None)] * 101
        + [_listing([])],
    )

    assert purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True) == 101
    assert calls == [
        ("GET", LIST_URL),
        ("GET", f"{BASE_URL}?per_page=100&page=2"),
        *[("DELETE", f"{BASE_URL}/{cache_id}") for cache_id in range(1, 102)],
        ("GET", LIST_URL),
    ]
    assert "Verified removal of 101 initially targeted cache(s)" in capsys.readouterr().out


def test_empty_snapshot_performs_no_delete_and_is_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _http(monkeypatch, [_listing([]), _listing([])])
    assert purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True) == 0
    assert calls == [("GET", LIST_URL), ("GET", LIST_URL)]


@pytest.mark.parametrize("cache_id", [None, True, False, 0, -1, 1.0, "1", "../other"])
def test_invalid_id_aborts_before_any_cache_is_deleted(
    monkeypatch: pytest.MonkeyPatch, cache_id: object
) -> None:
    calls = _http(monkeypatch, [_listing([7, cache_id])])
    with pytest.raises(RuntimeError, match="positive integer"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)
    assert calls == [("GET", LIST_URL)]


def test_missing_id_aborts_before_any_cache_is_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _http(monkeypatch, [(200, {"actions_caches": [{"id": 7}, {}]})])
    with pytest.raises(RuntimeError, match="positive integer"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)
    assert calls == [("GET", LIST_URL)]


@pytest.mark.parametrize(
    "payload", [[], {}, {"actions_caches": None}, {"actions_caches": {}}, {"actions_caches": [None]}]
)
def test_malformed_list_response_fails_closed(
    monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    calls = _http(monkeypatch, [(200, payload)])
    with pytest.raises(RuntimeError, match="cache response"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)
    assert calls == [("GET", LIST_URL)]


def test_concurrent_expiry_404_for_an_id_still_deletes_other_ids_and_verifies(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _http(monkeypatch, [_listing([1, 2]), (404, {}), (204, None), _listing([])])
    assert purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True) == 2
    assert calls == [
        ("GET", LIST_URL),
        ("DELETE", f"{BASE_URL}/1"),
        ("DELETE", f"{BASE_URL}/2"),
        ("GET", LIST_URL),
    ]
    assert "id=1 already absent (HTTP 404)" in capsys.readouterr().out


@pytest.mark.parametrize("phase", ["snapshot", "delete", "verification"])
@pytest.mark.parametrize("status", [401, 403, 500])
def test_http_failure_in_any_phase_fails_without_claiming_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    phase: str,
    status: int,
) -> None:
    prefix = {"snapshot": [], "delete": [_listing([1])], "verification": [_listing([1]), (204, None)]}
    _http(monkeypatch, prefix[phase] + [(status, {})])
    with pytest.raises(RuntimeError, match=str(status)):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)
    output = capsys.readouterr().out
    assert "Verified removal" not in output
    assert "Deleted all" not in output


@pytest.mark.parametrize("phase", ["snapshot", "verification"])
def test_list_404_is_an_error(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    prefix = [] if phase == "snapshot" else [_listing([1]), (204, None)]
    _http(monkeypatch, prefix + [(404, {})])
    with pytest.raises(RuntimeError, match="404"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)


@pytest.mark.parametrize("phase", ["snapshot", "delete", "verification"])
@pytest.mark.parametrize(
    "failure", [urllib.error.URLError("offline"), TimeoutError("timeout"), ConnectionResetError("reset")]
)
def test_network_failure_in_any_phase_fails_without_claiming_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    phase: str,
    failure: Exception,
) -> None:
    prefix = {"snapshot": [], "delete": [_listing([1])], "verification": [_listing([1]), (204, None)]}
    _http(monkeypatch, prefix[phase] + [failure])
    with pytest.raises(RuntimeError, match="unavailable"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)
    output = capsys.readouterr().out
    assert "Verified removal" not in output
    assert "Deleted all" not in output


def test_delete_requires_documented_204_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _http(monkeypatch, [_listing([1]), (200, {})])
    with pytest.raises(RuntimeError, match="cache-delete status: HTTP 200"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)


def test_any_lingering_target_fails_verification(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _http(monkeypatch, [_listing([1, 2]), (204, None), (204, None), _listing([2, 99])])
    with pytest.raises(RuntimeError, match="initially targeted cache ID.*2"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)
    assert "Verified removal" not in capsys.readouterr().out


def test_verification_reads_all_pages_before_claiming_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _http(
        monkeypatch,
        [_listing([700]), (204, None), _listing(list(range(1, 101))), _listing([700])],
    )
    with pytest.raises(RuntimeError, match="initially targeted cache ID.*700"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)
    assert calls[-1] == ("GET", f"{BASE_URL}?per_page=100&page=2")


def test_new_concurrent_caches_are_reported_separately_and_left_untouched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _http(monkeypatch, [_listing([1]), (204, None), _listing([2])])
    assert purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True) == 1
    assert calls == [("GET", LIST_URL), ("DELETE", f"{BASE_URL}/1"), ("GET", LIST_URL)]
    output = capsys.readouterr().out
    assert "Verified removal of 1 initially targeted cache(s)" in output
    assert "1 new cache(s) created concurrently remain" in output
    assert "Deleted all" not in output


def test_invalid_verification_id_does_not_claim_removal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _http(monkeypatch, [_listing([1]), (204, None), _listing(["1"])])
    with pytest.raises(RuntimeError, match="positive integer"):
        purge.purge(FAKE_TOKEN, REPOSITORY, confirm=True)
    assert "Verified removal" not in capsys.readouterr().out


def test_main_fails_closed_without_token() -> None:
    assert purge.main(["--repo", REPOSITORY, "--confirm"]) == 2


def test_main_requires_confirmation_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", FAKE_TOKEN)
    assert purge.main(["--repo", REPOSITORY]) == 1


@pytest.mark.parametrize("token_name", ["GH_TOKEN", "GITHUB_TOKEN"])
def test_main_accepts_either_token_gate(
    monkeypatch: pytest.MonkeyPatch, token_name: str
) -> None:
    monkeypatch.setenv(token_name, FAKE_TOKEN)
    _http(monkeypatch, [_listing([]), _listing([])])
    assert purge.main(["--repo", REPOSITORY, "--confirm"]) == 0


@pytest.mark.parametrize("kind", ["http", "network"])
def test_main_does_not_print_tokens_or_untrusted_error_content(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    untrusted = f"server-echoed-secret-{FAKE_TOKEN}"
    monkeypatch.setenv("GH_TOKEN", FAKE_TOKEN)
    reply = (401, {"message": untrusted}) if kind == "http" else urllib.error.URLError(untrusted)
    _http(monkeypatch, [reply])
    assert purge.main(["--repo", REPOSITORY, "--confirm"]) == 1
    captured = capsys.readouterr()
    assert "Cache purge failed" in captured.err
    assert FAKE_TOKEN not in captured.out + captured.err
    assert untrusted not in captured.out + captured.err


def _workflow() -> dict:
    """BaseLoader giữ nguyên khoá `on` theo quy ước YAML của GitHub."""
    return yaml.load((ROOT / ".github/workflows/cache-purge.yml").read_text(), Loader=yaml.BaseLoader)


def test_workflow_purge_is_scoped_to_authorized_maintenance_changes() -> None:
    workflow = _workflow()
    assert set(workflow["on"]) == {"workflow_dispatch", "push"}
    assert workflow["on"]["push"] == {
        "branches": ["main"],
        "paths": [".github/workflows/cache-purge.yml", "scripts/ops/purge_github_caches.py"],
    }
    assert workflow["permissions"] == {"actions": "write", "contents": "read"}
    job = workflow["jobs"]["purge"]
    assert job.get("continue-on-error", "false") == "false"
    run_steps = [step for step in job["steps"] if "run" in step]
    assert len(run_steps) == 1
    step = run_steps[0]
    assert step.get("continue-on-error", "false") == "false"
    assert step["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "GITHUB_REPOSITORY": "${{ github.repository }}",
    }
    assert step["run"].splitlines()[0] == "set -euo pipefail"


@pytest.mark.parametrize("exit_status", [0, 9])
def test_workflow_passes_explicit_confirmation_and_propagates_purge_exit(
    tmp_path: Path, exit_status: int
) -> None:
    step = next(step for step in _workflow()["jobs"]["purge"]["steps"] if "run" in step)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        '#!/bin/bash\nprintf "%s\\n" "$@" > "$CAPTURE_ARGS"\nexit "$PURGE_STATUS"\n'
    )
    fake_python.chmod(0o755)
    arguments = tmp_path / "arguments"
    env = {
        **os.environ,
        "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
        "GH_TOKEN": FAKE_TOKEN,
        "GITHUB_REPOSITORY": REPOSITORY,
        "CAPTURE_ARGS": str(arguments),
        "PURGE_STATUS": str(exit_status),
    }
    result = subprocess.run(["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == exit_status, result.stderr
    assert arguments.read_text().splitlines() == [
        "scripts/ops/purge_github_caches.py", "--confirm", "--repo", REPOSITORY
    ]
