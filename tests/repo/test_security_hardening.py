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

    Engine Vietlott ``vietlott/`` cũng nằm trong kho: trang riêng
    của nó dựng bằng ``scripts/build_site.py`` + ``scripts/site_assets/*.js``.
    Bản chép đầu tiên mang bốn cống trong ``dashboard.js`` mà CodeQL bắt được
    còn phép kiểm này không, vì nó chỉ quét ``src`` và ``docs``.

    Returns:
        Kịch bản trình duyệt, trình dựng Python, và trang đã xuất bản.
    """
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
        # Trang riêng của engine Vietlott.
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
    """Các lời gọi đọc lịch theo đồng hồ MÁY NGƯỜI XEM, bỏ qua chú thích ``//`` và ``/* … */``."""
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    code = "\n".join(line.split("//", 1)[0] if "://" not in line else line for line in code.splitlines())
    return LOCAL_CLOCK_GETTERS.findall(code)


def test_no_browser_script_reads_the_calendar_from_the_viewer_clock() -> None:
    """Lịch quay theo giờ Việt Nam. `getDay()`, `getMonth()`… đọc theo múi giờ máy người xem: bộ lọc «Thứ hai»
    từng trả toàn kỳ Chủ nhật ở `America/Los_Angeles`, và bảng «Đặc Biệt theo năm» chọn sẵn tháng trước
    vào tối 31 ở bờ Tây nước Mỹ (15-11-2026). Dùng `Date.UTC`/`getUTC*` hoặc `Intl` với `Asia/Ho_Chi_Minh`."""
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
    """Mọi biểu thức ``${{ }}`` nằm TRONG khối ``run:`` của một workflow đã đọc."""
    found = []
    for job_name, job in (doc.get("jobs") or {}).items():
        for index, step in enumerate(job.get("steps") or []):
            for match in _RUN_EXPRESSION.finditer(step.get("run") or ""):
                found.append(f"{job_name}/{step.get('id') or step.get('name') or index}: {match.group(0)}")
    return found


def test_the_run_block_expression_rule_itself_catches_an_interpolation() -> None:
    """Ghim chính LUẬT trên mẫu dựng sẵn, để một lần đổi thư mục không thu tập quét về rỗng."""
    import yaml

    dangerous = yaml.safe_load(
        "jobs:\n  a:\n    steps:\n"
        "      - name: x\n        run: echo \"${{ github.event.inputs.reason }}\"\n"
        "      - name: y\n        env:\n          REASON: ${{ github.event.inputs.reason }}\n"
        "        run: echo \"$REASON\"\n"
    )
    assert _expressions_in_run_blocks(dangerous) == ["a/x: ${{ github.event.inputs.reason }}"]


def test_no_workflow_substitutes_an_expression_into_a_run_block() -> None:
    """Runner thay ``${{ }}`` vào văn bản lệnh TRƯỚC khi shell đọc nó, nên dấu nháy không bảo vệ gì:
    một giá trị chứa ``"; lệnh; "`` trở thành lệnh. Mọi giá trị (đầu vào dispatch, đầu ra bước khác,
    tên sự kiện) đi qua ``env:`` rồi được đọc là ``"$BIEN"`` — shell nhận nó làm dữ liệu. Đến
    25-11-2026 còn tám chỗ thay thẳng (đều là giá trị do chính kho sinh ra); luật này giữ con số ấy ở 0."""
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
    """Gói lưu ``model_trust`` theo luật cũ (sàn 0,35) không được dùng lại."""
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
