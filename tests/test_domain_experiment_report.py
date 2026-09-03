from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


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
