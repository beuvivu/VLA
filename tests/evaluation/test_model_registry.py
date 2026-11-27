from __future__ import annotations

import json
import shutil
from pathlib import Path

import joblib
import numpy as np
import pytest

from evaluation import model_registry as mr

ROOT = Path(__file__).resolve().parents[2]
COPIED = (
    "models",
    "data/ensemble",
    "data/forecast/online",
    "data/forecast/knowledge",
    "data/forecast/cage_bayes",
    "data/forecast/predict",
    "data/evaluation/model_quality",
    "data/evaluation/regional_benchmark",
    "data/xsmb-2-digits.csv",
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for relative in COPIED:
        source, target = ROOT / relative, tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)
    return tmp_path


def _by_id(entries: list[dict]) -> dict[str, dict]:
    return {entry["model_id"]: entry for entry in entries}


def _edit_pack(root: Path, name: str, **changes: object) -> None:
    path = root / "models" / f"{name}.joblib"
    pack = joblib.load(path)
    pack.update(changes)
    joblib.dump(pack, path)


def _edit_json(path: Path, edit) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    edit(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_digest_is_canonical_and_reads_numpy_values_as_plain_numbers() -> None:
    assert mr.digest({"a": 1, "b": [1.5, None]}) == mr.digest({"b": [np.float64(1.5), None], "a": np.int64(1)})
    assert mr.digest({"a": 1}) != mr.digest({"a": 2})
    assert mr._json(float("nan")) is None and mr._json(np.float64("inf")) is None
    assert mr._json(object()) == "object"


def test_the_registry_covers_every_stage_of_the_forecast_chain(root: Path) -> None:
    entries = mr.collect(root)
    ids = [entry["model_id"] for entry in entries]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    expected = {f"xsmb/{stage}/{mode}" for mode in mr.MODES for stage in (
        "published", "ensemble_weights", "calibration", "ml", "cau_keo", "stacking", "online_hedge", "agents")}
    assert set(ids) == expected | {"xsmb/knowledge_base", "xsmb/cage_bayes", "xsmt/forecast", "xsmn/forecast"}
    for entry in entries:
        assert entry["deployment"] in mr.DEPLOYMENTS and entry["deployment"] != "missing", entry["model_id"]
        assert entry["deployment_reason"] and entry["fingerprint"] == mr.digest(entry["definition"])
        assert entry["artifact"] and (root / entry["artifact"]).is_file()
        json.dumps(entry)


def test_the_committed_registry_describes_the_committed_artifacts() -> None:
    saved = json.loads((ROOT / "data" / mr.REGISTRY).read_text(encoding="utf-8"))
    fresh = _by_id(mr.collect(ROOT))
    assert saved["schema_version"] == mr.SCHEMA_VERSION
    assert {e["model_id"] for e in saved["models"]} == set(fresh)
    for entry in saved["models"]:
        now = fresh[entry["model_id"]]
        assert entry["fingerprint"] == now["fingerprint"], entry["model_id"]
        if not entry["continuous_trust"]:
            assert entry["deployment"] == now["deployment"], entry["model_id"]
    assert saved["summary"] == mr._count(e["deployment"] for e in saved["models"])


def test_a_trust_scaled_component_is_gated_at_zero_and_in_production_above_it(root: Path) -> None:
    _edit_pack(root, "ml_loto", model_trust=0.0)
    _edit_pack(root, "ml_de", model_trust=0.25)
    entries = _by_id(mr.collect(root))
    assert entries["xsmb/ml/loto"]["deployment"] == "gated"
    assert "bằng mức nền" in entries["xsmb/ml/loto"]["deployment_reason"]
    assert entries["xsmb/ml/de"]["deployment"] == "production"
    assert "trust 25%" in entries["xsmb/ml/de"]["deployment_reason"]
    assert entries["xsmb/ml/de"]["continuous_trust"] and entries["xsmb/cau_keo/de"]["continuous_trust"]
    assert not entries["xsmb/stacking/de"]["continuous_trust"]
    assert entries["xsmb/ml/de"]["validation"]["model_trust"] == 0.25


def test_retraining_does_not_change_the_fingerprint_but_a_new_definition_does(root: Path) -> None:
    before = _by_id(mr.collect(root))["xsmb/ml/loto"]["fingerprint"]
    _edit_pack(root, "ml_loto", trained_through_date="2031-01-01", val_logloss=0.5, model_trust=0.4,
               selected_candidate={"name": "khac", "max_depth": 9})
    assert _by_id(mr.collect(root))["xsmb/ml/loto"]["fingerprint"] == before
    pack = joblib.load(root / "models" / "ml_loto.joblib")
    _edit_pack(root, "ml_loto", features=[*pack["features"], "dac_trung_moi"])
    changed = _by_id(mr.collect(root))["xsmb/ml/loto"]
    assert changed["fingerprint"] != before and changed["definition"]["features"]["count"] == len(pack["features"]) + 1
    _edit_pack(root, "ml_loto", features=pack["features"], feature_schema_version=pack["feature_schema_version"] + 1)
    assert _by_id(mr.collect(root))["xsmb/ml/loto"]["fingerprint"] not in {before, changed["fingerprint"]}


def test_cau_keo_trust_is_read_only_through_its_own_reader(root: Path) -> None:
    pack = joblib.load(root / "models" / "cau_keo_loto.joblib")
    pack.pop("trust_policy_version")
    joblib.dump(pack, root / "models" / "cau_keo_loto.joblib")
    entries = _by_id(mr.collect(root))
    assert entries["xsmb/cau_keo/loto"]["deployment"] == "missing"
    assert "ValueError" in entries["xsmb/cau_keo/loto"]["deployment_reason"]
    assert entries["xsmb/cau_keo/de"]["deployment"] != "missing"


def test_stacking_follows_its_quality_gate(root: Path) -> None:
    _edit_pack(root, "meta_loto", status="insufficient_history", quality_pass=False, meta_trust=0.0,
               history_days=40, minimum_history_days=100)
    _edit_pack(root, "meta_de", status="trained", quality_pass=True, meta_trust=0.5)
    entries = _by_id(mr.collect(root))
    assert entries["xsmb/stacking/loto"]["deployment"] == "gated"
    assert "40/100" in entries["xsmb/stacking/loto"]["deployment_reason"]
    assert entries["xsmb/stacking/de"]["deployment"] == "production"
    _edit_pack(root, "meta_de", status="trained", quality_pass=True, meta_trust=0.0)
    assert _by_id(mr.collect(root))["xsmb/stacking/de"]["deployment"] == "gated"
    _edit_pack(root, "meta_de", status="trained", quality_pass=False, meta_trust=0.5)
    gated = _by_id(mr.collect(root))["xsmb/stacking/de"]
    assert gated["deployment"] == "gated" and "không thắng" in gated["deployment_reason"]


def test_ensemble_weights_report_the_provenance_recorded_by_the_gate(root: Path) -> None:
    path = root / "data" / "ensemble" / "weights_loto.json"
    _edit_json(path, lambda p: p["promotion"].update(promoted=False, reason="biên thắng chưa đạt sàn"))
    rejected = _by_id(mr.collect(root))["xsmb/ensemble_weights/loto"]
    assert rejected["deployment"] == "production" and rejected["validation"]["origin"] == "bi_tu_choi"
    assert "từ chối" in rejected["deployment_reason"]
    _edit_json(path, lambda p: p.pop("promotion"))
    assert _by_id(mr.collect(root))["xsmb/ensemble_weights/loto"]["deployment"] == "missing"
    path.unlink()
    assert _by_id(mr.collect(root))["xsmb/ensemble_weights/loto"]["deployment"] == "missing"


def test_calibration_is_gated_while_it_keeps_the_identity(root: Path) -> None:
    path = root / "data" / "ensemble" / "calibration_de.json"
    _edit_json(path, lambda p: p.setdefault("selection", {}).update(chosen="identity"))
    assert _by_id(mr.collect(root))["xsmb/calibration/de"]["deployment"] == "gated"
    _edit_json(path, lambda p: p["selection"].update(chosen="platt", selected=True))
    chosen = _by_id(mr.collect(root))["xsmb/calibration/de"]
    assert chosen["deployment"] == "production" and "platt" in chosen["deployment_reason"]


def test_online_learning_follows_its_promotion_gate_and_agents_stay_in_shadow(root: Path) -> None:
    hedge = root / "data" / "forecast" / "online" / "loto.json"
    _edit_json(hedge, lambda p: p["records"][-1]["gate"].update(active=True, reason="cổng mở"))
    assert _by_id(mr.collect(root))["xsmb/online_hedge/loto"]["deployment"] == "production"
    _edit_json(hedge, lambda p: p["records"][-1]["gate"].update(active=False, reason="giữ đương nhiệm"))
    held = _by_id(mr.collect(root))["xsmb/online_hedge/loto"]
    assert held["deployment"] == "shadow" and held["deployment_reason"] == "giữ đương nhiệm"
    agent = root / "data" / "forecast" / "online" / "agents_loto.json"
    _edit_json(agent, lambda p: p["records"][-1]["gate"].update(active=True))
    assert _by_id(mr.collect(root))["xsmb/agents/loto"]["deployment"] == "shadow"


def test_the_cage_model_stays_in_shadow_even_when_eligible(root: Path) -> None:
    path = root / "data" / "forecast" / "cage_bayes" / "summary.json"
    entry = _by_id(mr.collect(root))["xsmb/cage_bayes"]
    assert entry["deployment"] == "shadow" and entry["artifact"] == "data/forecast/cage_bayes/summary.json"
    assert not any(ch.isdigit() for ch in entry["deployment_reason"].replace("2,326", ""))
    assert {"loto_z", "de_z", "prospective_log10_e", "eligible"} <= set(entry["validation"])
    _edit_json(path, lambda p: p["promotion"].update(eligible=True))
    eligible = _by_id(mr.collect(root))["xsmb/cage_bayes"]
    assert eligible["deployment"] == "shadow" and eligible["validation"]["eligible"]
    assert eligible["deployment_reason"] != entry["deployment_reason"]


def test_a_corrupt_record_becomes_missing_without_losing_the_rest(root: Path) -> None:
    (root / "models" / "ml_loto.joblib").write_bytes(b"khong phai joblib")
    (root / "data" / "forecast" / "knowledge" / "kb.json").write_text("{", encoding="utf-8")
    (root / "data" / "evaluation" / "regional_benchmark" / "benchmark.json").unlink()
    entries = _by_id(mr.collect(root))
    for model_id in ("xsmb/ml/loto", "xsmb/knowledge_base", "xsmt/forecast", "xsmn/forecast"):
        assert entries[model_id]["deployment"] == "missing", model_id
    assert len(entries) == 20 and entries["xsmb/ml/de"]["deployment"] != "missing"
    assert mr.build(root)["summary"]["missing"] == 4


def test_the_published_forecast_entry_reads_its_own_out_of_sample_ledger(root: Path) -> None:
    entry = _by_id(mr.collect(root))["xsmb/published/loto"]
    assert entry["deployment"] == "production"
    validation = entry["validation"]
    assert validation["graded_draws"] >= 20 and validation["ci95_low"] < validation["mean_logloss_skill"] < validation["ci95_high"]
    assert validation["monitor_state"] in {"chua_du", "vung_0", "te_hon", "hon"}
    assert entry["training"]["first_graded"] < entry["training"]["last_graded"]


def test_the_regional_entry_copies_conclusions_not_daily_numbers(root: Path) -> None:
    entry = _by_id(mr.collect(root))["xsmn/forecast"]
    assert entry["definition"]["law"] == "deu" and entry["artifact_sha256"] is None and entry["training"] == {}
    assert entry["definition"]["benchmark"]["benchmark_version"] >= 1
    path = root / "data" / "evaluation" / "regional_benchmark" / "benchmark.json"
    before = entry["fingerprint"]
    _edit_json(path, lambda p: p["regions"]["mn"].update(data_through="2031-01-01"))
    assert _by_id(mr.collect(root))["xsmn/forecast"] == entry
    _edit_json(path, lambda p: p["regions"]["mn"]["modes"]["loto"].update(edge=["bayes_thuc_nghiem"]))
    won = _by_id(mr.collect(root))["xsmn/forecast"]
    assert won["fingerprint"] == before and "chưa qua phép kiểm tiến cứu" in won["deployment_reason"]
    assert won["validation"]["regional_edge"]["loto"] == ["bayes_thuc_nghiem"]


def test_history_is_append_only_and_logs_gate_transitions_and_new_definitions(root: Path) -> None:
    registry_path = mr.run(root)
    history = root / "data" / mr.HISTORY
    first = history.read_text(encoding="utf-8")
    lines = len(mr.collect(root)) + 1
    assert first.splitlines()[0] == ",".join(mr.HISTORY_FIELDS) and first.count("\n") == lines
    registry_bytes = registry_path.read_bytes()
    mr.run(root)
    assert history.read_text(encoding="utf-8") == first and registry_path.read_bytes() == registry_bytes

    _edit_pack(root, "ml_loto", model_trust=0.3)
    _edit_pack(root, "ml_de", model_trust=0.0)
    mr.run(root)
    assert history.read_text(encoding="utf-8") == first
    _edit_pack(root, "meta_de", status="trained", quality_pass=True, meta_trust=0.5)
    mr.run(root)
    second = history.read_text(encoding="utf-8")
    assert second.startswith(first) and second.count("\n") == lines + 1
    assert second.splitlines()[-1].split(",")[1:4:2] == ["xsmb/stacking/de", "production"]
    pack = joblib.load(root / "models" / "ml_loto.joblib")
    _edit_pack(root, "ml_loto", feature_schema_version=pack["feature_schema_version"] + 1)
    mr.run(root)
    third = history.read_text(encoding="utf-8")
    assert third.startswith(second) and third.count("\n") == lines + 2
    last = third.splitlines()[-1].split(",")
    assert last[1] == "xsmb/ml/loto" and last[2] == _by_id(mr.collect(root))["xsmb/ml/loto"]["fingerprint"]
    assert last[0] == mr.data_through(root)
    _edit_pack(root, "meta_de", status="trained", quality_pass=False, meta_trust=0.0)
    mr.run(root)
    fourth = history.read_text(encoding="utf-8")
    assert fourth.startswith(third) and fourth.splitlines()[-1].split(",")[3] == "gated"


def test_strict_mode_fails_the_step_when_a_record_cannot_be_read(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mr, "REPO_ROOT", root)
    assert mr.main(["--strict"]) == 0
    (root / "models" / "meta_loto.joblib").unlink()
    assert mr.main([]) == 0
    assert mr.main(["--strict"]) == 1
    saved = json.loads((root / "data" / mr.REGISTRY).read_text(encoding="utf-8"))
    assert saved["summary"]["missing"] == 1 and "generated" not in json.dumps(saved)
    assert saved["data_through"] == mr.data_through(root)
