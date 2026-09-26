from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import ml_predict
from calibration import CalibParams
from ml_train import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION
from ensemble_utils import load_ensemble_weights
from predict_nextday_2d import _load_calibration
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


#: Các cống HTML: chuỗi đi qua chúng được trình duyệt PHÂN TÍCH thành thẻ,
#: nên một ký tự lọt vào từ dữ liệu có thể thành mã đánh dấu. Mã dựng DOM phải
#: đi bằng ``createElement`` + ``textContent``.
DOM_SINKS = (".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write")


def dom_sinks_in(source: str) -> list[str]:
    """Các cống HTML mà ``source`` có nhắc tới.

    Args:
        source: Nội dung một tệp kịch bản, trang, hay trình dựng.

    Returns:
        Tên các cống tìm thấy, theo thứ tự đã khai trong ``DOM_SINKS``.
    """
    return [sink for sink in DOM_SINKS if sink in source]


def files_scanned_for_dom_sinks() -> list[Path]:
    """Mọi tệp mà luật cấm cống HTML áp lên.

    ``docs/**/*.js`` phải có mặt riêng, không thể dựa vào ``src``: ba tệp
    trong ``docs/assets/`` (``matrix-virt.js``, ``apply-data-styles.js``,
    ``css-async.js``) KHÔNG có bản
    nguồn nào dưới ``src``, mà trang sinh ra vẫn nạp chúng. Quét mỗi ``src``
    và ``docs/*.html`` thì một cống thêm vào bất kỳ tệp nào trong số đó vẫn
    để phép kiểm XANH — đúng thứ mà tên phép kiểm hứa là không xảy ra.

    Returns:
        Kịch bản trình duyệt, trình dựng Python, và trang đã xuất bản.
    """
    return sorted(
        {
            *(ROOT / "src").rglob("*.js"),
            *(ROOT / "src").rglob("*.py"),
            *(ROOT / "docs").rglob("*.html"),
            *(ROOT / "docs").rglob("*.js"),
        }
    )


def test_the_dom_sink_rule_itself_catches_a_sink() -> None:
    """Ghim chính LUẬT trên mẫu dựng sẵn.

    Phép kiểm dưới đây quét một tập tệp tìm bằng ``rglob``. Nếu cách tìm ấy
    hỏng — đổi thư mục, đổi đuôi — tập thành rỗng và phép kiểm vẫn XANH trong
    khi nó không còn canh gì. Mẫu dựng sẵn ở đây không thể rỗng.
    """
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
    # Tập quét phải chứa đúng những tệp từng vi phạm, cộng các trình dựng mà
    # bản cũ của phép kiểm này soi. Ghim tên để một lần đổi thư mục không lặng
    # lẽ thu tập về rỗng — tập rỗng là phép kiểm không thể đỏ.
    assert {
        "stat_pages.js",
        "frequency_bento.js",
        "frequency_demo.js",
        "traditional_results.js",
        "build_landing_page.py",
        "build_statistics_dashboard.py",
        "build_stat_pages.py",
        "live.html",
        # Ba tệp kịch bản bảo trì không có bản nguồn dưới `src`.
        "matrix-virt.js",
        "apply-data-styles.js",
        "css-async.js",
    } <= names, sorted(names)
    assert sum(1 for path in scanned if path.suffix == ".html") >= 29

    ban = {
        path.relative_to(ROOT).as_posix(): dom_sinks_in(
            path.read_text(encoding="utf-8")
        )
        for path in scanned
    }
    assert {ten: xs for ten, xs in ban.items() if xs} == {}


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
