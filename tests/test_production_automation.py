from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from production_audit import expected_latest_draw
from reconcile_live_canonical import build_payload


def test_expected_latest_draw_is_cutoff_aware():
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    assert expected_latest_draw(datetime(2026, 9, 1, 10, 0, tzinfo=tz), time(18, 15)).isoformat() == "2026-08-31"
    assert expected_latest_draw(datetime(2026, 9, 1, 19, 0, tzinfo=tz), time(18, 15)).isoformat() == "2026-09-01"


def test_reconcile_live_uses_only_accepted_canonical(tmp_path: Path):
    canonical = tmp_path / "xsmb.csv"
    fields = [
        "date", "special", "prize1", "prize2_1", "prize2_2",
        "prize3_1", "prize3_2", "prize3_3", "prize3_4", "prize3_5", "prize3_6",
        "prize4_1", "prize4_2", "prize4_3", "prize4_4",
        "prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6",
        "prize6_1", "prize6_2", "prize6_3",
        "prize7_1", "prize7_2", "prize7_3", "prize7_4",
    ]
    values = ["2026-08-31", "35644", "44080"] + [str(10000 + i) for i in range(2)] + [str(20000 + i) for i in range(6)] + [str(3000 + i) for i in range(4)] + [str(4000 + i) for i in range(6)] + [str(500 + i) for i in range(3)] + [str(60 + i) for i in range(4)]
    canonical.write_text(",".join(fields) + "\n" + ",".join(values) + "\n", encoding="utf-8")

    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "2026-08-31": {
                    "accepted": True,
                    "agreement": 4,
                    "source_agreement": 5,
                    "independent_groups": ["xoso", "mketqua", "minhngoc", "xosodaiphat"],
                    "sources": ["xoso.com.vn", "mketqua.net"],
                }
            }
        ),
        encoding="utf-8",
    )

    payload = build_payload(canonical=canonical, audit_path=audit)
    assert payload["draw_date"] == "2026-08-31"
    assert payload["status"] == "complete_verified"
    assert payload["verified_complete"] is True
    assert payload["canonical_reconciled"] is True
    assert payload["received_values"] == 27
    assert payload["prizes"]["special"] == ["35644"]
    assert sum(len(v) for v in payload["prizes"].values()) == 27


def test_watchdog_and_post_finalization_workflows_are_wired():
    watchdog = Path(".github/workflows/watchdog.yml").read_text(encoding="utf-8")
    post = Path(".github/workflows/post-finalization.yml").read_text(encoding="utf-8")

    for cron in ("10 11 * * *", "20 11 * * *", "35 12 * * *", "5 13 * * *", "20 13 * * *", "15 0 * * *"):
        assert cron in watchdog
    assert 'dispatch("live-results.yml")' in watchdog
    assert 'dispatch("update-data.yml")' in watchdog
    assert 'dispatch("pages.yml")' in watchdog
    assert 'dispatch("post-finalization.yml")' in watchdog
    assert 'workflows: ["Finalize XSMB + Statistics + AI/ML"]' in post
    assert "src/production_audit.py" in post
    assert "src/reconcile_live_canonical.py" in post
