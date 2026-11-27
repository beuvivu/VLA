from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ml import ml_predict
from ensemble.calibration import CalibParams
from ml.ml_train import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, TRUST_POLICY_VERSION
from ensemble.ensemble_utils import load_ensemble_weights
from forecast.predict_nextday_2d import _load_calibration
from ingest.lottery import Lottery, RepoPaths, vietnam_today


ROOT = Path(__file__).resolve().parents[2]


def test_http_collection_does_not_depend_on_anti_bot_bypass_package() -> None:
    assert "cloudscraper" not in (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "cloudscraper" not in (ROOT / "requirements-live.txt").read_text(
        encoding="utf-8"
    )
    assert "cloudscraper" not in (ROOT / "src" / "ingest" / "lottery.py").read_text(
        encoding="utf-8"
    )


def test_release_checks_do_not_use_fixed_shared_temporary_files() -> None:
    release_check = (ROOT / "scripts" / "release" / "release_check.sh").read_text(
        encoding="utf-8"
    )
    assert "/tmp/production-audit-release.json" not in release_check
    assert '"$TMP_PRED/production-audit-release.json"' in release_check


DOM_SINKS = (".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write")


def dom_sinks_in(source: str) -> list[str]:
    return [sink for sink in DOM_SINKS if sink in source]


def files_scanned_for_dom_sinks() -> list[Path]:
    engine = ROOT / "vietlott"
    return sorted(
        {
            *(ROOT / "src").rglob("*.js"),
            *(ROOT / "src").rglob("*.py"),
            *(ROOT / "docs").rglob("*.html"),
            *(ROOT / "docs").rglob("*.js"),
            *(engine / "src").rglob("*.py"),
            *(engine / "scripts").rglob("*.py"),
            *(engine / "scripts").rglob("*.js"),
            *(engine / "scripts").rglob("*.html"),
        }
    )


def test_the_dom_sink_rule_itself_catches_a_sink() -> None:
    assert dom_sinks_in('box.innerHTML = "<b>x</b>";') == [".innerHTML"]
    assert dom_sinks_in("el.outerHTML = s;") == [".outerHTML"]
    assert dom_sinks_in('el.insertAdjacentHTML("beforeend", s);') == [
        "insertAdjacentHTML"
    ]
    assert dom_sinks_in('document.write("<p>");') == ["document.write"]
    assert (
        dom_sinks_in(
            'node.textContent = ""; node.appendChild(document.createElement("b"));'
        )
        == []
    )


def test_nothing_published_to_the_browser_uses_an_untrusted_html_dom_sink() -> None:
    scanned = files_scanned_for_dom_sinks()
    names = {path.name for path in scanned}
    assert {
        "stat_pages.js",
        "frequency_bento.js",
        "frequency_demo.js",
        "traditional_results.js",
        "build_landing_page.py",
        "build_statistics_dashboard.py",
        "build_stat_pages.py",
        "live.html",
        "matrix-virt.js",
        "apply-data-styles.js",
        "css-async.js",
        "dashboard.js",
        "build_site.py",
    } <= names, sorted(names)
    assert sum(1 for path in scanned if path.suffix == ".html") >= 29

    ban = {
        path.relative_to(ROOT).as_posix(): dom_sinks_in(
            path.read_text(encoding="utf-8")
        )
        for path in scanned
    }
    assert {ten: xs for ten, xs in ban.items() if xs} == {}


LOCAL_CLOCK_GETTERS = re.compile(r"\.(?:getDay|getDate|getMonth|getFullYear|getHours|getMinutes)\(\)")


def local_clock_reads_in(source: str) -> list[str]:
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    code = "\n".join(line.split("//", 1)[0] if "://" not in line else line for line in code.splitlines())
    return LOCAL_CLOCK_GETTERS.findall(code)


def test_no_browser_script_reads_the_calendar_from_the_viewer_clock() -> None:
    scanned = sorted({*(ROOT / "src").rglob("*.js"), *(ROOT / "docs").rglob("*.js"),
                      *(ROOT / "worker").rglob("*.js")} - set((ROOT / "worker").rglob("node_modules/**/*.js")))
    assert {"stat_pages.js", "live-scorecard.js", "shared_results.js"} <= {path.name for path in scanned}
    found = {path.relative_to(ROOT).as_posix(): calls for path in scanned
             if (calls := local_clock_reads_in(path.read_text(encoding="utf-8")))}
    assert found == {}
    assert local_clock_reads_in("const m = new Date().getMonth();") == [".getMonth()"]
    assert local_clock_reads_in("// new Date().getMonth()\n/* d.getDay() */ d.getUTCDay();") == []


def test_the_live_page_declares_its_content_security_policy() -> None:
    live = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in live
    assert "connect-src 'self' https://raw.githubusercontent.com" in live


def test_empty_history_uses_vietnam_business_date() -> None:
    assert vietnam_today(now=datetime(2026, 9, 3, 18, 30, tzinfo=UTC)) == date(
        2026, 9, 4
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        vietnam_today(now=datetime(2026, 9, 3, 18, 30))


def test_duplicate_dates_in_canonical_json_fail_closed(tmp_path: Path) -> None:
    row = {
        "date": "2026-09-01",
        "special": 12345,
        "prize1": 12345,
        **{f"prize2_{i}": 12345 for i in range(1, 3)},
        **{f"prize3_{i}": 12345 for i in range(1, 7)},
        **{f"prize4_{i}": 1234 for i in range(1, 5)},
        **{f"prize5_{i}": 1234 for i in range(1, 7)},
        **{f"prize6_{i}": 123 for i in range(1, 4)},
        **{f"prize7_{i}": 12 for i in range(1, 5)},
    }
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "xsmb.json").write_text(
        json.dumps([row, row]), encoding="utf-8"
    )
    lottery = Lottery(
        paths=RepoPaths(root=tmp_path, data_dir=data_dir, images_dir=tmp_path / "images"),
        http=object(),  # type: ignore[arg-type]
        sources=[],
    )
    with pytest.raises(ValueError, match="duplicate draw dates"):
        lottery.load()


_RUN_EXPRESSION = re.compile(r"\$\{\{.*?\}\}", re.S)


def _expressions_in_run_blocks(doc: dict) -> list[str]:
    found = []
    for job_name, job in (doc.get("jobs") or {}).items():
        for index, step in enumerate(job.get("steps") or []):
            for match in _RUN_EXPRESSION.finditer(step.get("run") or ""):
                found.append(f"{job_name}/{step.get('id') or step.get('name') or index}: {match.group(0)}")
    return found


def test_the_run_block_expression_rule_itself_catches_an_interpolation() -> None:
    import yaml

    dangerous = yaml.safe_load(
        "jobs:\n  a:\n    steps:\n"
        "      - name: x\n        run: echo \"${{ github.event.inputs.reason }}\"\n"
        "      - name: y\n        env:\n          REASON: ${{ github.event.inputs.reason }}\n"
        "        run: echo \"$REASON\"\n"
    )
    assert _expressions_in_run_blocks(dangerous) == ["a/x: ${{ github.event.inputs.reason }}"]


def test_no_workflow_substitutes_an_expression_into_a_run_block() -> None:
    import yaml

    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert len(workflows) > 10
    offenders = []
    for path in workflows:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        offenders += [f"{path.name}: {item}" for item in _expressions_in_run_blocks(doc)]
    assert offenders == []


def test_production_modules_do_not_use_optimizable_assertions() -> None:
    for name in (
        "core/number_reference.py",
        "ingest/sources.py",
        "ml/cau_keo_ml.py",
        "ensemble/learn_ensemble_weights.py",
    ):
        source = (ROOT / "src" / name).read_text(encoding="utf-8")
        assert "assert " not in source, name


class _ProbabilityModel:
    def predict_proba(self, values):
        return values


def test_base_ml_pack_cannot_expand_the_production_feature_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_path = tmp_path / "ml_loto.joblib"
    model_path.touch()
    bad = {
        "features": [*FEATURE_COLUMNS, "rejected_experiment"],
        "model": _ProbabilityModel(),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "trust_policy_version": TRUST_POLICY_VERSION,
        "trained_through_date": "2026-09-03",
        "window_days": 2000,
        "baseline_prob": 0.2,
        "model_trust": 0.5,
    }
    good = {**bad, "features": list(FEATURE_COLUMNS)}
    loaded = iter((bad, good))
    retrained: list[str] = []
    monkeypatch.setattr(ml_predict.joblib, "load", lambda _: next(loaded))
    monkeypatch.setattr(
        ml_predict,
        "train_one",
        lambda mode, models_dir, window_days: retrained.append(mode),
    )

    pack = ml_predict._load_or_train_model(
        "loto",
        tmp_path,
        window_days=2000,
        latest_data_date="2026-09-03",
    )

    assert pack["features"] == FEATURE_COLUMNS
    assert retrained == ["loto"]


def test_base_ml_pack_with_invalid_numeric_metadata_is_retrained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_path = tmp_path / "ml_loto.joblib"
    model_path.touch()
    base = {
        "features": list(FEATURE_COLUMNS),
        "model": _ProbabilityModel(),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "trust_policy_version": TRUST_POLICY_VERSION,
        "trained_through_date": "2026-09-03",
        "window_days": 2000,
        "baseline_prob": 0.2,
        "model_trust": 0.5,
    }
    loaded = iter(({**base, "model_trust": float("nan")}, base))
    retrained: list[str] = []
    monkeypatch.setattr(ml_predict.joblib, "load", lambda _: next(loaded))
    monkeypatch.setattr(
        ml_predict,
        "train_one",
        lambda mode, models_dir, window_days: retrained.append(mode),
    )

    pack = ml_predict._load_or_train_model(
        "loto",
        tmp_path,
        window_days=2000,
        latest_data_date="2026-09-03",
    )

    assert pack["model_trust"] == 0.5
    assert retrained == ["loto"]


def test_base_ml_pack_trained_under_an_old_trust_policy_is_retrained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_path = tmp_path / "ml_loto.joblib"
    model_path.touch()
    current = {
        "features": list(FEATURE_COLUMNS),
        "model": _ProbabilityModel(),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "trust_policy_version": TRUST_POLICY_VERSION,
        "trained_through_date": "2026-09-03",
        "window_days": 2000,
        "baseline_prob": 0.2,
        "model_trust": 0.0,
    }
    old = {k: v for k, v in current.items() if k != "trust_policy_version"} | {"model_trust": 0.35}
    for stale in (old, {**old, "trust_policy_version": TRUST_POLICY_VERSION - 1}):
        assert ml_predict._model_pack_issue(
            stale, window_days=2000, latest_data_date="2026-09-03"
        ) == "trust policy changed"
    loaded = iter((old, current))
    retrained: list[str] = []
    monkeypatch.setattr(ml_predict.joblib, "load", lambda _: next(loaded))
    monkeypatch.setattr(
        ml_predict,
        "train_one",
        lambda mode, models_dir, window_days: retrained.append(mode),
    )
    pack = ml_predict._load_or_train_model(
        "loto", tmp_path, window_days=2000, latest_data_date="2026-09-03"
    )
    assert pack["model_trust"] == 0.0
    assert retrained == ["loto"]


def test_base_ml_pack_rejects_fractional_schema_metadata() -> None:
    pack = {
        "features": list(FEATURE_COLUMNS),
        "model": _ProbabilityModel(),
        "feature_schema_version": float(FEATURE_SCHEMA_VERSION),
        "trained_through_date": "2026-09-03",
        "window_days": 2000,
        "baseline_prob": 0.2,
        "model_trust": 0.5,
    }

    assert ml_predict._model_pack_issue(
        pack,
        window_days=2000,
        latest_data_date="2026-09-03",
    ) == "invalid model-pack metadata"


def test_invalid_ensemble_configuration_falls_back_safely(tmp_path: Path) -> None:
    ensemble = tmp_path / "ensemble"
    ensemble.mkdir()
    (ensemble / "weights_loto.json").write_text(
        '{"schema_version":5,"weights":{"w_ml":"NaN","w_stat":1}}',
        encoding="utf-8",
    )
    (ensemble / "calibration_loto.json").write_text(
        '{"schema_version":5,"params":{"a":"NaN","temperature":0}}',
        encoding="utf-8",
    )

    assert load_ensemble_weights(tmp_path, "loto").as_dict() == {
        "w_ml": 0.25,
        "w_cau": 0.30,
        "w_stat": 0.20,
        "w_active": 0.125,
        "w_stable": 0.125,
    }
    assert _load_calibration(tmp_path, "loto") == CalibParams(mode="loto")

    (ensemble / "weights_loto.json").write_text(
        '{"schema_version":5.5,"weights":{"w_ml":1,"w_stat":1}}',
        encoding="utf-8",
    )
    assert load_ensemble_weights(tmp_path, "loto").as_dict() == {
        "w_ml": 0.25,
        "w_cau": 0.30,
        "w_stat": 0.20,
        "w_active": 0.125,
        "w_stable": 0.125,
    }
