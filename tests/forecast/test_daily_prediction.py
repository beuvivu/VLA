from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.time_policy import utc_cron_for_vietnam
from core.resilience import RetryPolicy, first_available, with_retry
from core.xsmb_domain import FIELD_WIDTHS

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/daily_prediction.yml"


def test_retry_gives_up_after_the_configured_attempts() -> None:
    calls = {"n": 0}

    def always_fails() -> None:
        calls["n"] += 1
        raise OSError("mạng hỏng")

    with pytest.raises(OSError):
        with_retry(always_fails, policy=RetryPolicy(attempts=3), sleep=lambda _: None)
    assert calls["n"] == 3


def test_retry_returns_as_soon_as_it_succeeds() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("chậm")
        return "xong"

    assert with_retry(flaky, sleep=lambda _: None) == "xong"
    assert calls["n"] == 3


def test_retry_does_not_swallow_programming_errors() -> None:
    calls = {"n": 0}

    def broken() -> None:
        calls["n"] += 1
        raise ValueError("lỗi lập trình")

    with pytest.raises(ValueError):
        with_retry(broken, sleep=lambda _: None)
    assert calls["n"] == 1, "không được thử lại lỗi ngoài nhóm đã khai báo"


def test_retry_backoff_grows_exponentially() -> None:
    policy = RetryPolicy(base_delay=2.0)
    assert [policy.delay_for(i) for i in range(4)] == [2.0, 4.0, 8.0, 16.0]


def test_retry_policy_validates_its_arguments() -> None:
    with pytest.raises(ValueError, match="attempts"):
        RetryPolicy(attempts=0)
    with pytest.raises(ValueError, match="base_delay"):
        RetryPolicy(base_delay=-1.0)


def test_first_available_names_the_source_it_used() -> None:

    def broken() -> str:
        raise RuntimeError("nguồn chính hỏng")

    name, value = first_available([("chinh", broken), ("du_phong", lambda: "ok")])
    assert name == "du_phong"
    assert value == "ok"


def test_first_available_reports_every_failure_when_all_sources_die() -> None:
    def fail(label: str):
        def inner() -> str:
            raise RuntimeError(f"hỏng {label}")

        return inner

    with pytest.raises(RuntimeError) as excinfo:
        first_available([("a", fail("a")), ("b", fail("b"))])
    assert "hỏng a" in str(excinfo.value)
    assert "hỏng b" in str(excinfo.value)


def test_first_available_needs_at_least_one_source() -> None:
    with pytest.raises(ValueError, match="ít nhất một nguồn"):
        first_available([])


def test_workflow_runs_at_the_vietnamese_draw_time() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    crons = re.findall(r'cron:\s*"([^"]+)"', text)
    assert utc_cron_for_vietnam(18, 35) in crons


def test_workflow_shares_the_data_pipeline_concurrency_group() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    pipeline = (ROOT / ".github/workflows/update-data.yml").read_text(encoding="utf-8")
    group = re.search(r"concurrency:\s*\n\s*group:\s*(\S+)", text).group(1)
    pipeline_group = re.search(r"concurrency:\s*\n\s*group:\s*(\S+)", pipeline).group(1)
    assert group == pipeline_group


def test_workflow_retries_the_push() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "for attempt in 1 2 3 4" in text
    assert 'git reset --hard "origin/${GITHUB_REF_NAME}"' in text
    assert "git pull --rebase" not in text


def test_workflow_pins_the_vietnamese_timezone() -> None:
    assert "TZ: Asia/Ho_Chi_Minh" in WORKFLOW.read_text(encoding="utf-8")


def _history(days: int, end: str) -> pd.DataFrame:
    rng = np.random.default_rng(4)
    dates = pd.date_range(end=end, periods=days, freq="D")
    frame = {"date": dates}
    for field, width in FIELD_WIDTHS:
        frame[field] = rng.integers(0, 10**width, size=days)
    return pd.DataFrame(frame)


def test_runner_refuses_to_predict_a_draw_that_already_happened(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "xsmb.csv"
    _history(220, "2020-01-01").to_csv(raw, index=False)
    result = subprocess.run(
        [
            sys.executable,
            "src/forecast/modeling/run_daily_prediction.py",
            "--raw",
            str(raw),
            "--out",
            str(tmp_path / "out.json"),
            "--max-staleness-days",
            "1000000",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    assert "hậu đoán" in result.stderr
    assert not (tmp_path / "out.json").exists()


def test_runner_refuses_stale_data(tmp_path: Path) -> None:
    raw = tmp_path / "xsmb.csv"
    _history(220, "2020-01-01").to_csv(raw, index=False)
    result = subprocess.run(
        [
            sys.executable,
            "src/forecast/modeling/run_daily_prediction.py",
            "--raw",
            str(raw),
            "--out",
            str(tmp_path / "out.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    assert "cũ hơn" in result.stderr


def test_published_bundle_carries_the_evidence_and_the_disclaimer() -> None:
    import json

    path = ROOT / "data/predictions_today.json"
    if not path.exists():
        pytest.skip("chưa sinh dự đoán")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "đường cơ sở" in payload["disclaimer"]
    assert payload["evidence"]["bridge_scan"]["loto"]["survived_fdr"] == 0
    for pick in payload["top_lo_to"]:
        assert "baseline" in pick and "lift" in pick
        assert pick["lift"] == pytest.approx(pick["probability"] - pick["baseline"])
