from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def test_live_workflow_uses_utc_schedule_and_subminute_poll_loop() -> None:
    text = _text("live-results.yml")
    assert 'cron: "0 11 * * *"' in text  # 18:00 Vietnam (UTC+7)
    assert 'POLL_SECONDS: "15"' in text
    assert 'MAX_SECONDS: "3600"' in text
    assert "refs/heads/live" in text
    assert "complete_verified" in text
    assert "actions: write" in text
    assert "actions/workflows/update-data.yml/dispatches" in text
    assert "cancel-in-progress: false" in text


def test_daily_workflow_has_primary_and_recovery_finalization_times() -> None:
    text = _text("update-data.yml")
    expected_utc_crons = (
        "30 11 * * *",  # 18:30 Vietnam
        "40 11 * * *",  # 18:40 Vietnam
        "50 11 * * *",  # 18:50 Vietnam
        "0 12 * * *",  # 19:00 Vietnam
        "10 12 * * *",  # 19:10 Vietnam
        "20 12 * * *",  # 19:20 Vietnam
        "30 12 * * *",  # 19:30 Vietnam
        "45 12 * * *",  # 19:45 Vietnam
        "0 13 * * *",  # 20:00 Vietnam
    )
    for cron in expected_utc_crons:
        assert f'cron: "{cron}"' in text
    assert "--cutoff 18:35" in text
    assert '"--consensus-min-recent", "2"' in text
    assert "Ghi nhận kết quả chuẩn ngay lập tức" in text
    assert "--fail-on-stale" in text
    assert "--fail-on-missing" in text
    assert "--cutoff-aware" in text
    assert "push:" in text
    assert '"reason": "live_verified"' in _text("live-results.yml")


def test_watchdog_and_post_finalization_use_utc7_cutoff_and_recovery() -> None:
    watchdog = _text("watchdog.yml")
    for cron in ("55 10", "5 11", "15 11", "25 11", "45 11", "5 12", "25 12", "45 12", "5 13"):
        assert f'cron: "{cron} * * *"' in watchdog
    assert '"18:35"' in watchdog
    assert '"reason": "watchdog_recovery"' in watchdog
    assert "--cutoff 18:35" in _text("post-finalization.yml")


def test_dashboard_refresh_checks_vietnamese_contract() -> None:
    text = _text("dashboard-refresh.yml")
    for marker in ("lịch 7 cột", "Độ nâng so với nền", "Kiểm toán và liên kết chi tiết"):
        assert marker in text
    assert "Lift vs baseline" not in text


def test_daily_workflow_scopes_privileged_permissions_to_the_jobs_that_need_them() -> None:
    text = _text("update-data.yml")
    top, jobs = text.split("jobs:\n", 1)
    update, rest = jobs.split("  trigger-post-finalization:\n", 1)
    trigger, deploy = rest.split("  deploy-pages:\n", 1)

    assert "permissions:\n  contents: read" in top
    assert "    permissions:\n      contents: write" in update
    assert "    permissions:\n      actions: write\n      contents: read" in trigger
    assert (
        "    permissions:\n"
        "      contents: read\n"
        "      id-token: write\n"
        "      pages: write"
    ) in deploy


def test_pages_use_official_actions_deployment_flow() -> None:
    page = _text("pages.yml")
    daily = _text("update-data.yml")
    for text in (page, daily):
        assert "actions/configure-pages@v6" in text
        assert "actions/upload-pages-artifact@v5" in text
        assert "actions/deploy-pages@v5" in text


def test_production_refreshes_do_not_restore_package_caches() -> None:
    # Live/daily jobs must not restore an old runner cache while repairing a
    # stale data snapshot.  CI may retain its dependency cache for speed.
    for name in ("ci.yml", "live-results.yml", "update-data.yml", "dashboard-refresh.yml"):
        text = _text(name)
        assert "cache:" not in text
        assert "--no-cache-dir" in text


def test_cache_purge_is_explicit_and_not_scheduled() -> None:
    text = _text("cache-purge.yml")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "actions: write" in text
    assert "gh cache delete --all --confirm" in text
