from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from evaluation.production_audit import audit, expected_latest_draw
from ingest.reconcile_live_canonical import build_payload


POST_BUILD_ONLY_PATHS = {
    "data/stats/statistical_signal/predict_next_loto_stat_all.csv",
    "data/stats/statistical_signal/predict_next_de_stat_all.csv",
    "data/stats/number_dynamics/current_dynamics_loto.csv",
    "data/stats/number_dynamics/current_dynamics_de.csv",
    "data/stats/number_dynamics/diagnostics_loto.json",
    "data/stats/number_dynamics/diagnostics_de.json",
    "data/stats/advanced/conditional_matrices_diagnostics.json",
    "data/stats/advanced/ai_ml_signal_diagnostics.json",
    "data/stats/advanced/ai_ml_signal_loto.csv",
    "data/stats/advanced/ai_ml_signal_de.csv",
    "data/ai_ml/cau_keo_manifest_loto.json",
    "data/ai_ml/cau_keo_manifest_de.json",
}
POST_BUILD_ONLY_PREFIXES = (
    "stat_signal_loto_target=",
    "stat_signal_de_target=",
    "cau_keo_loto_target=",
    "cau_keo_de_target=",
    "cau_keo_loto_calendar_contract_missing",
    "cau_keo_de_calendar_contract_missing",
    "conditional_",
    "ai_overlay_",
    "dynamics_loto_calendar_not_verified",
    "dynamics_de_calendar_not_verified",
    "dynamics_loto_anchor=",
    "dynamics_de_anchor=",
)


def test_expected_latest_draw_is_cutoff_aware():
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    assert expected_latest_draw(datetime(2026, 9, 1, 10, 0, tzinfo=tz), time(18, 35)).isoformat() == "2026-08-31"
    assert expected_latest_draw(datetime(2026, 9, 1, 19, 0, tzinfo=tz), time(18, 35)).isoformat() == "2026-09-01"


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

    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "2026-08-31": {
                    "accepted": True,
                    "agreement": 1,
                    "source_agreement": 1,
                    "independent_groups": ["xoso"],
                    "sources": ["xoso.com.vn"],
                }
            }
        ),
        encoding="utf-8",
    )

    payload = build_payload(canonical=canonical, audit_path=audit_path)
    assert payload["draw_date"] == "2026-08-31"
    assert payload["status"] == "complete_verified"
    assert payload["verified_complete"] is True
    assert payload["canonical_reconciled"] is True
    assert payload["received_values"] == 27
    assert payload["prizes"]["special"] == ["35644"]
    assert sum(len(v) for v in payload["prizes"].values()) == 27


@pytest.mark.parametrize("unsafe_value", ["12.5", "NaN", "<script>", "１２３４５"])
def test_reconcile_live_rejects_noncanonical_prize_values(
    tmp_path: Path, unsafe_value: str
) -> None:
    canonical = tmp_path / "xsmb.csv"
    canonical.write_text(
        "date,special\n2026-08-31," + unsafe_value + "\n", encoding="utf-8"
    )
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "2026-08-31": {
                    "accepted": True,
                    "agreement": 2,
                    "sources": ["xoso.com.vn", "mketqua.net"],
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises((KeyError, ValueError)):
        build_payload(canonical=canonical, audit_path=audit_path)


class _SameEvidenceForEveryDate(dict):

    def __init__(self, item: dict) -> None:
        super().__init__()
        self._item = item

    def get(self, key, default=None):
        return self._item


@pytest.mark.parametrize(("agreement", "flagged"), [(1, False), (0, True)])
def test_one_accepted_source_is_enough_for_the_canonical_draw(
    monkeypatch: pytest.MonkeyPatch, agreement: int, flagged: bool
) -> None:
    from evaluation import production_audit

    original = production_audit._json

    def fake_json(path: str) -> dict:
        if path == "data/source_audit.json":
            return _SameEvidenceForEveryDate({"accepted": True, "agreement": agreement})
        return original(path)

    monkeypatch.setattr(production_audit, "_json", fake_json)
    critical = audit(check_freshness=False, check_docs=False)["critical"]
    hits = [item for item in critical if item.startswith("source_consensus")]
    assert bool(hits) is flagged, critical
    if flagged:
        assert hits[0].startswith("source_consensus_missing=")


@pytest.mark.parametrize(("accepted", "agreement"), [(True, 0), (False, 1)])
def test_reconcile_live_needs_an_accepted_source(
    tmp_path: Path, accepted: bool, agreement: int
) -> None:
    canonical = tmp_path / "xsmb.csv"
    canonical.write_text("date,special\n2026-08-31,35644\n", encoding="utf-8")
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps({"2026-08-31": {"accepted": accepted, "agreement": agreement}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no accepted source"):
        build_payload(canonical=canonical, audit_path=audit_path)


def _prebuild_critical(critical: list[str]) -> list[str]:
    out: list[str] = []
    for item in critical:
        if item.startswith("missing_or_empty="):
            paths = item.split("=", 1)[1].split(",")
            remaining = [p for p in paths if p not in POST_BUILD_ONLY_PATHS]
            if remaining:
                out.append("missing_or_empty=" + ",".join(remaining))
            continue
        if item.startswith(POST_BUILD_ONLY_PREFIXES):
            continue
        out.append(item)
    return out


def test_current_repo_data_and_models_are_internally_consistent():
    result = audit(check_freshness=False, check_docs=False)
    critical = _prebuild_critical(result["critical"])
    assert not critical, critical


def test_prebuild_filter_covers_only_regenerated_analytics():
    critical = _prebuild_critical(
        [
            "missing_or_empty=data/stats/advanced/ai_ml_signal_diagnostics.json,data/xsmb.csv",
            "conditional_diagnostics_invalid=not built yet",
            "cau_keo_loto_calendar_contract_missing",
            "dynamics_de_calendar_not_verified",
            "stat_signal_loto_target=2026-08-31 expected=2026-09-01",
            "source_consensus_missing=2026-09-01",
            "health_json_not_ok",
        ]
    )
    assert critical == [
        "missing_or_empty=data/xsmb.csv",
        "source_consensus_missing=2026-09-01",
        "health_json_not_ok",
    ]


def test_watchdog_and_post_finalization_workflows_are_wired():
    watchdog = Path(".github/workflows/watchdog.yml").read_text(encoding="utf-8")
    post = Path(".github/workflows/post-finalization.yml").read_text(encoding="utf-8")
    daily = Path(".github/workflows/update-data.yml").read_text(encoding="utf-8")

    for cron in (
        "55 10 * * *", "5 11 * * *", "15 11 * * *", "25 11 * * *", "45 11 * * *",
        "5 12 * * *", "25 12 * * *", "45 12 * * *", "5 13 * * *", "15 0 * * *",
    ):
        assert cron in watchdog
    assert 'dispatch("live-results.yml")' in watchdog
    assert 'dispatch("update-data.yml", {"reason": "watchdog_recovery"})' in watchdog
    assert 'dispatch("pages.yml")' in watchdog
    assert 'dispatch("post-finalization.yml")' in watchdog

    assert "actions: write" in daily
    assert "canonical_ready" in daily
    assert "trigger-post-finalization:" in daily
    assert "post-finalization.yml/dispatches" in daily

    assert "workflow_run:" not in post
    assert "workflow_dispatch:" in post
    assert "src/evaluation/production_audit.py" in post
    assert "src/ingest/reconcile_live_canonical.py" in post
    assert "/tmp/live-canonical.json" not in post
    assert "mktemp" in post

    assert "/tmp/production_audit.json" not in watchdog
    assert "TemporaryDirectory" in watchdog

    live = Path(".github/workflows/live-results.yml").read_text(encoding="utf-8")
    assert "/tmp/live.json" not in live
    assert "mktemp" in live


def test_a_learner_that_stops_following_new_draws_turns_the_audit_red(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    from evaluation import production_audit

    latest = date(2026, 11, 14)
    fresh = {
        "data/forecast/online/loto.json": {"history": {"last_date": "2026-11-14"}},
        "data/forecast/online/de.json": {"history": {"last_date": "2026-11-14"}},
        "data/forecast/online/agents_loto.json": {"history": {"last_date": "2026-11-14"}},
        "data/forecast/online/agents_de.json": {"history": {"last_date": "2026-11-14"}},
        "data/forecast/agents/report.json": {"anchor_date": "2026-11-14"},
        "data/forecast/knowledge/kb.json": {"source_date": "2026-11-14"},
        "data/ensemble/meta_report_loto.json": {"status": "insufficient_history", "trained_through_target_date": None},
        "data/ensemble/meta_report_de.json": {"status": "trained", "trained_through_target_date": "2026-11-14"},
    }
    files = dict(fresh)
    monkeypatch.setattr(production_audit, "_json", lambda path: files[path])
    assert production_audit.stale_learners(latest) == []
    for path, stale in (("data/forecast/online/de.json", {"history": {"last_date": "2026-11-13"}}),
                        ("data/forecast/knowledge/kb.json", {"source_date": "2026-11-13"}),
                        ("data/forecast/agents/report.json", {}),
                        ("data/ensemble/meta_report_de.json", {"status": "trained", "trained_through_target_date": "2026-11-13"})):
        files = {**fresh, path: stale}
        found = production_audit.stale_learners(latest)
        assert len(found) == 1 and found[0].startswith("learner_stale:"), (path, found)
    files = {k: v for k, v in fresh.items() if k != "data/forecast/online/loto.json"}

    def missing(path: str) -> dict:
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]

    monkeypatch.setattr(production_audit, "_json", missing)
    assert production_audit.stale_learners(latest) == ["learner_unreadable:online_loto=FileNotFoundError"]
    assert {path for _, path, _ in production_audit.ADAPTIVE_LEARNERS} <= set(production_audit.REQUIRED_PATHS)


def test_the_full_audit_reports_stale_learners_and_the_consistency_audit_does_not(monkeypatch: pytest.MonkeyPatch) -> None:
    from evaluation import production_audit

    monkeypatch.setattr(production_audit, "stale_learners", lambda latest: [f"learner_stale:kiem_thu expected={latest}"])
    full = audit(check_freshness=True, check_docs=False)["critical"]
    assert any(item.startswith("learner_stale:kiem_thu") for item in full), full
    consistency = audit(check_freshness=False, check_docs=False)["critical"]
    assert not any(item.startswith("learner_stale:") for item in consistency), consistency
