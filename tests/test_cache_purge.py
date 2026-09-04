from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import purge_github_caches as purge  # noqa: E402


def test_purge_requires_explicit_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(purge, "_request", lambda *args, **kwargs: pytest.fail("network called"))
    with pytest.raises(ValueError, match="--confirm"):
        purge.purge("token", "beuvivu/VLA", confirm=False)


def test_purge_lists_all_pages_then_deletes_repository_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_request(token: str, url: str, *, method: str = "GET") -> tuple[int, bytes]:
        calls.append((method, url))
        if method == "GET" and "page=1" in url:
            payload = {"actions_caches": [{"id": 1, "key": "a", "ref": "refs/heads/main"}]}
            return 200, json.dumps(payload).encode()
        if method == "DELETE":
            return 204, b""
        raise AssertionError((method, url))

    monkeypatch.setattr(purge, "_request", fake_request)
    assert purge.purge("token", "beuvivu/VLA", confirm=True) == 1
    assert calls == [
        ("GET", "https://api.github.com/repos/beuvivu/VLA/actions/caches?per_page=100&page=1"),
        ("DELETE", "https://api.github.com/repos/beuvivu/VLA/actions/caches"),
    ]


def test_main_fails_closed_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert purge.main(["--repo", "beuvivu/VLA", "--confirm"]) == 2
