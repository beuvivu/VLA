from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def test_live_workflow_uses_local_timezone_and_subminute_poll_loop() -> None:
    text = _text("live-results.yml")
    assert 'timezone: "Asia/Ho_Chi_Minh"' in text
    assert 'cron: "4 18 * * *"' in text
    assert 'POLL_SECONDS: "25"' in text
    assert "refs/heads/live" in text
    assert "complete_verified" in text


def test_daily_workflow_has_primary_and_recovery_finalization_times() -> None:
    text = _text("update-data.yml")
    assert text.count('timezone: "Asia/Ho_Chi_Minh"') == 3
    for cron in ('38 18 * * *', '53 18 * * *', '13 19 * * *'):
        assert f'cron: "{cron}"' in text
    assert "--fail-on-stale" in text
    assert "--fail-on-missing" in text
    assert "--cutoff-aware" in text
    assert "push:" in text
    assert "push-bootstrap" in text


def test_pages_use_official_actions_deployment_flow() -> None:
    page = _text("pages.yml")
    daily = _text("update-data.yml")
    for text in (page, daily):
        assert "actions/configure-pages@v5" in text
        assert "actions/upload-pages-artifact@v4" in text
        assert "actions/deploy-pages@v4" in text
