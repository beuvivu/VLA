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


#: Cách ghi DOM nhận chuỗi rồi PHÂN TÍCH nó thành thẻ. Dữ liệu không tin cậy
#: đi qua đây là thực thi mã trong trình duyệt người đọc.
DOM_SINKS = (".innerHTML", "insertAdjacentHTML", "outerHTML", "document.write")


def dom_sink_offenders(source: str) -> list[str]:
    """Các cách ghi DOM biến chuỗi thành thẻ, tìm thấy trong ``source``."""
    return [sink for sink in DOM_SINKS if sink in source]


def markup_emitters(root: Path) -> list[Path]:
    """Mọi tệp có thể đưa thẻ HTML tới trình duyệt.

    Tự DÒ thay vì liệt kê tay, và đó là toàn bộ lý do hàm này tồn tại. Bản
    trước ghim cứng ba đường dẫn (`build_landing_page.py`,
    `build_statistics_dashboard.py`, `docs/live.html`); khi tầng trình bày bị
    xóa thì cả ba biến mất và phép kiểm nổ, còn khi giao diện MỚI lên thì
    không ai nhớ thêm nó vào danh sách — bất biến bảo mật im lặng ngừng hoạt
    động đúng lúc cần nhất.
    """
    found: list[Path] = []
    docs = root / "docs"
    if docs.is_dir():
        found.extend(sorted(docs.rglob("*.html")))
    for path in sorted((root / "src").rglob("*")):
        if path.suffix not in {".py", ".js", ".j2", ".html"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "<!DOCTYPE" in text or "<!doctype" in text or "<html" in text:
            found.append(path)
    return found


def test_the_dom_sink_rule_catches_each_sink_it_names() -> None:
    """Luật phải tự kiểm được, vì hiện KHÔNG còn tệp nào để quét.

    Tầng trình bày đã bị xóa, nên phép kiểm chạy qua tệp thật hiện quét qua
    tập rỗng và xanh miễn phí. Một phép kiểm rỗng không phân biệt được với một
    phép kiểm đã bị tháo. Nên luật được ghim trên chuỗi dựng sẵn ở đây, và nó
    sẽ tự áp cho giao diện mới ngay khi giao diện mới xuất hiện.
    """
    assert dom_sink_offenders("const x = 1;") == []
    for sink in DOM_SINKS:
        assert dom_sink_offenders(f"el{sink} = data") == [sink], sink


def test_the_markup_discovery_actually_finds_markup(tmp_path: Path) -> None:
    """Bộ dò phải thật sự tìm ra, nếu không phép kiểm dưới là rỗng vĩnh viễn."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "trang.html").write_text("<!DOCTYPE html><p>xin chào", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "dung_trang.py").write_text(
        'HTML = "<!DOCTYPE html><html lang=vi>"\n', encoding="utf-8"
    )
    (tmp_path / "src" / "chi_du_lieu.py").write_text("import json\n", encoding="utf-8")

    names = {p.name for p in markup_emitters(tmp_path)}
    assert names == {"trang.html", "dung_trang.py"}


def test_the_published_tree_holds_at_least_one_page() -> None:
    """Chốt chặn cho cả một LỚP lỗi: phép kiểm cấp trang hoá rỗng trong im lặng.

    Mọi phép kiểm duyệt ``docs/**/*.html`` đều xanh miễn phí khi ``docs/``
    không có trang nào. Đó không phải giả thuyết — nó đã xảy ra: sau khi tầng
    trình bày bị xóa ngày 2026-09-21, bộ kiểm báo 1 127 xanh / 0 đỏ, nhưng
    trong số đó ``tests/test_dock_on_mobile.py`` (7 phép kiểm) xanh CHỈ VÌ nó
    parametrize qua 0 trang. Nó thức dậy ngay khi trang đầu tiên xuất hiện và
    đòi một thành phần đã bị xóa cùng giao diện cũ.

    Một phép kiểm quét tập rỗng không phân biệt được với một phép kiểm đã bị
    tháo. Bất biến này đứng thay cho tất cả chúng: hễ ``docs/`` còn trang thì
    mọi phép kiểm cấp trang còn có đối tượng, và hễ nó trống thì CHÍNH phép
    kiểm này đỏ — nói ra sự rỗng thay vì để nó ẩn trong màu xanh.
    """
    pages = sorted((ROOT / "docs").rglob("*.html"))
    assert pages, (
        "docs/ không có trang HTML nào. Mọi phép kiểm duyệt trang đã xuất bản "
        "hiện quét qua tập rỗng và xanh miễn phí — xem lại chúng trước khi tin "
        "vào màu xanh của bộ kiểm."
    )


def test_nothing_that_emits_markup_uses_an_untrusted_dom_sink() -> None:
    """Không nguồn nào đưa thẻ tới trình duyệt được dùng cách ghi phân tích chuỗi.

    Hiện tập này RỖNG vì tầng trình bày đã bị xóa. Phép kiểm vẫn ở đây để
    giao diện mới bị soi ngay khi nó xuất hiện, và hai phép kiểm trên bảo đảm
    cả luật lẫn bộ dò đều còn sống trong lúc tập rỗng.
    """
    offenders: list[str] = []
    for path in markup_emitters(ROOT):
        source = path.read_text(encoding="utf-8", errors="replace")
        for sink in dom_sink_offenders(source):
            offenders.append(f"{path.relative_to(ROOT)}: {sink}")
    assert not offenders, "dùng cách ghi DOM không an toàn: " + "; ".join(offenders)


def test_every_published_page_declares_a_content_security_policy() -> None:
    """Trang xuất bản phải khai CSP, và khai cả nguồn được phép gọi mạng.

    Cũng đang rỗng cùng lý do trên. Khi giao diện mới lên, mỗi trang HTML
    trong ``docs/`` phải mang ``Content-Security-Policy``.
    """
    missing = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "docs").rglob("*.html"))
        if "Content-Security-Policy" not in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert not missing, "trang thiếu CSP: " + "; ".join(missing)


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
