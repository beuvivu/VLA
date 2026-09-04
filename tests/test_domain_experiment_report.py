from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from build_domain_experiment_report import _records_for_mode


ROOT = Path(__file__).resolve().parents[1]


def test_domain_experiment_report_matches_current_gated_artifacts() -> None:
    subprocess.run(
        [sys.executable, "src/build_domain_experiment_report.py"],
        cwd=ROOT,
        check=True,
    )
    report = json.loads(
        (ROOT / "docs/research/experiment_results.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["schema_version"] == 2
    assert len(report["experiments"]) == 12
    assert report["result_summary"]["production_changed"] is False
    assert report["result_summary"]["promoted_groups"] == {
        "loto": [],
        "de": [],
    }
    for experiment in report["experiments"]:
        assert experiment["oos_dates"] >= 30
        assert experiment["oos_rows"] >= 3_000
        assert experiment["promoted"] is False
        assert experiment["rejection_reason"]
        assert experiment["brier_ci"] is None
        assert experiment["logloss_ci"] is None


def test_promoted_report_rows_follow_gate_state() -> None:
    rows = pd.DataFrame(
        [
            {
                "stage": "confirm",
                "candidate": "partner",
                "feature_count": 2,
                "fold": 3,
                "val_start": "2026-01-01",
                "val_end_exclusive": "2026-02-01",
                "baseline_brier": 0.2,
                "candidate_brier": 0.1,
                "baseline_logloss": 0.3,
                "candidate_logloss": 0.2,
                "oos_dates": 31,
                "oos_rows": 3100,
            }
        ]
    )
    gate = {
        "feature_groups": {"partner": ["x"]},
        "screened_groups": ["partner"],
        "production_selected_groups": ["partner"],
        "baseline_feature_count": 39,
        "positive_skill_threshold": 0.0,
        "generated_at": "2026-02-01T00:00:00Z",
    }
    record = _records_for_mode("loto", rows, gate)[0]
    assert record["promoted"] is True
    assert record["rejection_reason"] == []
    assert record["ci_status"] == "passed_final_gate"
