from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def test_live_workflow_uses_utc_schedule_and_subminute_poll_loop() -> None:
    text = _text("live-results.yml")
    assert 'cron: "4 11 * * *"' in text  # 18:04 Vietnam (UTC+7)
    assert 'POLL_SECONDS: "25"' in text
    assert 'MAX_SECONDS: "2700"' in text
    assert "refs/heads/live" in text
    assert "complete_verified" in text
    assert "actions: write" in text
    assert "actions/workflows/update-data.yml/dispatches" in text
    assert "cancel-in-progress: false" in text


def test_daily_workflow_has_primary_and_recovery_finalization_times() -> None:
    text = _text("update-data.yml")
    expected_utc_crons = (
        "18 11 * * *",  # 18:18 Vietnam
        "28 11 * * *",  # 18:28 Vietnam
        "38 11 * * *",  # 18:38 Vietnam
        "48 11 * * *",  # 18:48 Vietnam
        "58 11 * * *",  # 18:58 Vietnam
        "13 12 * * *",  # 19:13 Vietnam
        "28 12 * * *",  # 19:28 Vietnam
    )
    for cron in expected_utc_crons:
        assert f'cron: "{cron}"' in text
    assert "--cutoff 18:15" in text
    assert '"--consensus-min-recent", "2"' in text
    assert "Ghi nhận kết quả chuẩn ngay lập tức" in text
    assert "--fail-on-stale" in text
    assert "--fail-on-missing" in text
    assert "--cutoff-aware" in text
    assert "push:" in text


def test_pages_use_official_actions_deployment_flow() -> None:
    page = _text("pages.yml")
    daily = _text("update-data.yml")
    for text in (page, daily):
        assert "actions/configure-pages@v6" in text
        assert "actions/upload-pages-artifact@v5" in text
        assert "actions/deploy-pages@v5" in text
