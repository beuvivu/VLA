from __future__ import annotations

import json
import os
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest
import requests
import yaml

import atomic_io
import regional_lottery as regional


ROOT = Path(__file__).resolve().parents[1]


def _rows(region: str, day: date) -> list[regional.RegionalPrize]:
    return [
        regional.RegionalPrize(day.isoformat(), region, "Đài mẫu", prize, pos, str(pos).zfill(width))
        for prize, count, width in regional.PRIZE_SPECS
        for pos in range(1, count + 1)
    ]


def _clock(monkeypatch, now: str) -> None:
    instant = datetime.fromisoformat(now)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    monkeypatch.setattr(regional, "datetime", Clock)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(regional, "__file__", str(tmp_path / "src/regional_lottery.py"))
    _clock(monkeypatch, "2026-10-09T20:00:00+07:00")
    return tmp_path


@pytest.mark.parametrize("missing_region", ["mt", "mn"])
@pytest.mark.parametrize("failure", ["empty", "request"])
def test_missing_latest_fails_after_saving_the_other_region(repo, monkeypatch, capsys, missing_region, failure):
    previous = date(2026, 10, 8)
    expected = date(2026, 10, 9)
    for region in regional.REGIONS:
        regional.write_dataset(repo / f"data/regions/xs{region}.csv", _rows(region, previous))

    def fetch(region, day, **kwargs):
        if region == missing_region:
            if failure == "request":
                raise requests.Timeout("nguồn chậm")
            return []
        return _rows(region, day)

    monkeypatch.setattr(regional, "fetch_day", fetch)
    assert regional.main(["--require-latest", "--delay", "0"]) == 1
    for region in regional.REGIONS:
        path = repo / f"data/regions/xs{region}.csv"
        saved = regional.load_csv(path)
        expected_days = {previous.isoformat()}
        if region != missing_region:
            expected_days.add(expected.isoformat())
        assert {row.date for row in saved} == expected_days
        assert set(json.loads(path.with_suffix(".json").read_text())["results"]) == expected_days
    output = capsys.readouterr().out
    assert f"XS{missing_region.upper()}" in output
    assert "2026-10-09" in output


@pytest.mark.parametrize(
    "now,expected",
    [
        ("2026-10-09T17:59:59+07:00", date(2026, 10, 8)),
        ("2026-10-09T18:00:00+07:00", date(2026, 10, 9)),
        ("2026-11-01T00:05:00+07:00", date(2026, 10, 31)),
        ("2027-01-01T00:05:00+07:00", date(2026, 12, 31)),
        ("2026-10-09T11:00:00+00:00", date(2026, 10, 9)),
    ],
)
def test_complete_required_day_succeeds_using_the_vietnam_cutoff(repo, monkeypatch, now, expected):
    _clock(monkeypatch, now)
    monkeypatch.setattr(regional, "fetch_day", lambda region, day, **kw: _rows(region, day))
    assert regional.main(["--require-latest", "--delay", "0"]) == 0
    for region in regional.REGIONS:
        saved = regional.load_csv(repo / f"data/regions/xs{region}.csv")
        assert {row.date for row in saved} == {expected.isoformat()}
        assert len(saved) == 18


def test_explicit_end_date_takes_priority_over_the_clock(repo, monkeypatch):
    monkeypatch.setattr(regional, "fetch_day", lambda region, day, **kw: _rows(region, day))
    assert regional.main(["--region", "mt", "--end-date", "2026-09-30", "--require-latest", "--delay", "0"]) == 0
    saved = regional.load_csv(repo / "data/regions/xsmt.csv")
    assert {row.date for row in saved} == {"2026-09-30"}
    assert not (repo / "data/regions/xsmn.csv").exists()


def test_historical_backfill_remains_best_effort_without_freshness_opt_in(repo, monkeypatch):
    monkeypatch.setattr(regional, "fetch_day", lambda *args, **kw: [])
    assert regional.main(["--end-date", "2020-01-01", "--delay", "0"]) == 0


def test_existing_complete_latest_day_does_not_need_the_source(repo, monkeypatch):
    for region in regional.REGIONS:
        regional.write_dataset(repo / f"data/regions/xs{region}.csv", _rows(region, date(2026, 10, 9)))

    def unavailable(*args, **kwargs):
        raise AssertionError("Ngày đủ sẵn phải dùng dữ liệu đã lưu")

    monkeypatch.setattr(regional, "fetch_day", unavailable)
    assert regional.main(["--require-latest", "--delay", "0"]) == 0


def test_partial_saved_day_cannot_satisfy_freshness(repo, monkeypatch):
    regional.write_dataset(repo / "data/regions/xsmt.csv", _rows("mt", date(2026, 10, 9))[:-1])
    monkeypatch.setattr(regional, "fetch_day", lambda *args, **kw: [])
    assert regional.main(["--region", "mt", "--require-latest", "--delay", "0"]) == 1


def test_failed_csv_replacement_preserves_the_previous_dataset(tmp_path, monkeypatch):
    path = tmp_path / "xsmt.csv"
    regional.write_dataset(path, _rows("mt", date(2026, 10, 8)))
    previous_csv = path.read_bytes()
    previous_json = path.with_suffix(".json").read_bytes()

    def disk_failure(*args):
        raise OSError("không thay được tệp")

    monkeypatch.setattr(atomic_io.os, "replace", disk_failure)
    with pytest.raises(OSError, match="không thay được tệp"):
        regional.write_dataset(path, _rows("mt", date(2026, 10, 9)))
    assert path.read_bytes() == previous_csv
    assert path.with_suffix(".json").read_bytes() == previous_json
    assert sorted(p.name for p in tmp_path.iterdir()) == ["xsmt.csv", "xsmt.json"]


def test_workflow_publishes_valid_partial_results_before_reporting_failure(tmp_path):
    workflow = yaml.safe_load((ROOT / ".github/workflows/regional-results.yml").read_text())
    steps = workflow["jobs"]["sync"]["steps"]
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"].get("ref") == "main"
    collector = next(step for step in steps if "src/regional_lottery.py" in step.get("run", ""))
    assert collector.get("id") == "collect"
    assert collector.get("continue-on-error") is True
    build = next(step for step in steps if "src/build_regional_results.py" in step.get("run", ""))
    deployment = next(step for step in steps if step.get("uses", "").startswith("actions/deploy-pages@"))
    final = steps[-1]
    assert steps.index(collector) < steps.index(build) < steps.index(deployment) < steps.index(final)
    assert "always()" in final["if"]
    assert "steps.collect.outcome == 'failure'" in final["if"]

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$ARGUMENTS"\nexit 1\n')
    fake_python.chmod(0o755)
    arguments = tmp_path / "arguments"
    env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}", ARGUMENTS=str(arguments), MANUAL_DAYS="30")
    shell = collector["run"].replace("${{ github.event_name }}", "push")
    result = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", shell], env=env, check=False)
    assert result.returncode == 1
    assert "--require-latest" in arguments.read_text().splitlines()
    result = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", final["run"]], capture_output=True, text=True, check=False)
    assert result.returncode == 1
