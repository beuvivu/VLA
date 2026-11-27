import json
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from evaluation import monitor_health
from evaluation.monitor_health import expected_latest_draw_date

ROOT = Path(__file__).resolve().parents[2]


def test_expected_latest_draw_is_yesterday_before_cutoff() -> None:
    now = datetime(2026, 8, 31, 5, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    assert expected_latest_draw_date(now=now, cutoff=dtime(18, 35)).isoformat() == "2026-08-30"


def test_expected_latest_draw_is_today_after_cutoff() -> None:
    now = datetime(2026, 8, 31, 18, 40, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    assert expected_latest_draw_date(now=now, cutoff=dtime(18, 35)).isoformat() == "2026-08-31"


def _health(tmp_path: Path, latest: str) -> Path:
    path = tmp_path / "health.json"
    path.write_text(json.dumps({"ok": True, "latest_date": latest, "missing_count": 0}), encoding="utf-8")
    return path


def test_the_expected_date_replaces_the_wall_clock(tmp_path: Path) -> None:
    health = _health(tmp_path, "2026-11-23")
    args = ["--health", str(health), "--max-staleness-days", "0", "--fail-on-stale"]

    monitor_health.main([*args, "--expected-date", "2026-11-23"])
    with pytest.raises(SystemExit, match="staleness=1 > 0"):
        monitor_health.main([*args, "--expected-date", "2026-11-24"])


def test_the_finalization_job_checks_health_against_the_settled_target() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/update-data.yml").read_text(encoding="utf-8"))
    step = next(s for s in workflow["jobs"]["update"]["steps"] if "src/evaluation/monitor_health.py" in s.get("run", ""))
    assert step["env"]["TARGET_DATE"] == "${{ needs.canonical.outputs.target }}"
    assert '--expected-date "$TARGET_DATE"' in step["run"]
    assert "--cutoff-aware" not in step["run"]
