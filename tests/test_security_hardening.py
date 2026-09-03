from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import ml_predict
from calibration import CalibParams
from ml_train import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION
from predict_nextday_2d import _load_calibration, _load_weights
from lottery import Lottery, RepoPaths, vietnam_today


ROOT = Path(__file__).resolve().parents[1]


def test_http_collection_does_not_depend_on_anti_bot_bypass_package() -> None:
    assert "cloudscraper" not in (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "cloudscraper" not in (ROOT / "requirements-live.txt").read_text(
        encoding="utf-8"
    )
    assert "cloudscraper" not in (ROOT / "src" / "lottery.py").read_text(
        encoding="utf-8"
    )


def test_release_checks_do_not_use_fixed_shared_temporary_files() -> None:
    release_check = (ROOT / "scripts" / "release_check.sh").read_text(
        encoding="utf-8"
    )
    assert "/tmp/production-audit-release.json" not in release_check
    assert '"$TMP_PRED/production-audit-release.json"' in release_check


def test_static_page_builders_do_not_use_untrusted_html_dom_sinks() -> None:
    paths = [
        ROOT / "src" / "build_landing_page.py",
        ROOT / "src" / "build_statistics_dashboard.py",
        ROOT / "docs" / "live.html",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert ".innerHTML" not in source, path.name
        assert "insertAdjacentHTML" not in source, path.name

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


def test_production_modules_do_not_use_optimizable_assertions() -> None:
    for name in (
        "number_reference.py",
        "sources.py",
        "cau_keo_ml.py",
        "learn_ensemble_weights.py",
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

    assert _load_weights(tmp_path, "loto").as_dict() == {
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
    assert _load_weights(tmp_path, "loto").as_dict() == {
        "w_ml": 0.25,
        "w_cau": 0.30,
        "w_stat": 0.20,
        "w_active": 0.125,
        "w_stable": 0.125,
    }
