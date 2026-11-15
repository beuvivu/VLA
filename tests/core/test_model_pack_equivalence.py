"""Pack mô hình học lại y hệt thì giữ tệp cũ (`core.model_io.dump_pack_unless_equivalent`, 11-11-2026).

Lượt chạy lại trên cùng dữ liệu ghi lại `models/meta_<mode>.joblib` dù mô hình trùng từng bit: khác giờ học,
và pickle khác cả cách chia sẻ chuỗi giữa các đối tượng.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from core.model_io import dump_pack_unless_equivalent

STAMPS = frozenset({"trained_at_utc"})


def _model(c: float = 1.0) -> LogisticRegression:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, 3))
    return LogisticRegression(C=c).fit(x, (x[:, 0] > 0).astype(int))


def _pack(model: LogisticRegression, when: str, **extra: object) -> dict[str, object]:
    return {"mode": "de", "model": model, "features": ["a", "b", "c"], "trained_at_utc": when, **extra}


def test_a_pack_that_only_differs_in_training_time_keeps_the_file(tmp_path: Path) -> None:
    path = tmp_path / "meta_de.joblib"
    joblib.dump(_pack(_model(), "2026-11-10T11:39:26Z"), path)
    before = path.read_bytes()
    assert dump_pack_unless_equivalent(_pack(_model(), "2026-11-11T02:01:48Z"), path, stamp_keys=STAMPS) is False
    assert path.read_bytes() == before


def test_shared_and_unshared_strings_are_the_same_pack(tmp_path: Path) -> None:
    """Hai pack bằng nhau theo giá trị nhưng pickle khác nhau: một pack dùng chung đối tượng chuỗi."""
    word = "".join(["log_", "loss"])
    shared = _pack(_model(), "a", names=[word, word])
    separate = _pack(_model(), "a", names=["log_loss", "".join(["log", "_loss"])])
    assert pickle.dumps(shared) != pickle.dumps(separate)
    path = tmp_path / "meta_de.joblib"
    joblib.dump(shared, path)
    before = path.read_bytes()
    assert dump_pack_unless_equivalent(separate, path, stamp_keys=STAMPS) is False
    assert path.read_bytes() == before


def test_a_different_model_or_field_is_written(tmp_path: Path) -> None:
    path = tmp_path / "meta_de.joblib"
    joblib.dump(_pack(_model(), "a"), path)
    assert dump_pack_unless_equivalent(_pack(_model(c=0.01), "a"), path, stamp_keys=STAMPS) is True
    assert joblib.load(path)["model"].C == 0.01
    assert dump_pack_unless_equivalent(_pack(_model(c=0.01), "a", quality_pass=True), path, stamp_keys=STAMPS)
    assert joblib.load(path)["quality_pass"] is True


def test_a_missing_or_unreadable_pack_is_written(tmp_path: Path) -> None:
    path = tmp_path / "meta_de.joblib"
    assert dump_pack_unless_equivalent(_pack(_model(), "a"), path, stamp_keys=STAMPS) is True
    path.write_bytes(b"not a pickle")
    assert dump_pack_unless_equivalent(_pack(_model(), "a"), path, stamp_keys=STAMPS) is True
    assert joblib.load(path)["trained_at_utc"] == "a"


def _hgb(features: np.ndarray, labels: np.ndarray):
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=20, random_state=0).fit(features, labels)


def _gap_features(shift_ulp: bool) -> tuple[np.ndarray, np.ndarray]:
    """Đặc trưng float32 kiểu `log1p(khoảng cách)`; ``shift_ulp`` = runner khác CPU lệch một ULP float32."""
    rng = np.random.default_rng(7)
    gaps = rng.integers(0, 60, size=(3000, 2)).astype(np.float32)
    values = np.log1p(gaps)
    if shift_ulp:
        values = np.where(values > 0, np.nextafter(values, np.float32(np.inf)), values)
    return values, (rng.random(3000) < 0.2 + 0.01 * gaps[:, 0]).astype(int)


def test_a_model_retrained_on_another_cpu_keeps_the_file_when_it_predicts_the_same(tmp_path: Path) -> None:
    """Lượt chạy lại 09-11-2026 trên runner khác CPU: ngưỡng bin lệch 10⁻⁸, hệ số Platt 10⁻¹⁴, số đo 10⁻¹³.

    Tham số khác (``joblib.hash`` khác) mà dự báo trùng: giữ tệp cũ khi có hàm dự báo, ghi khi không có.
    """
    old_x, labels = _gap_features(shift_ulp=False)
    new_x, _ = _gap_features(shift_ulp=True)
    old_model, new_model = _hgb(old_x, labels), _hgb(new_x, labels)
    assert joblib.hash(old_model) != joblib.hash(new_model)
    old_pack = {"model": old_model, "val_logloss": 0.056073120773549916, "rows": np.array([0.1, 0.2]),
                "features": ["gap", "log_gap"], "window_days": 1460}
    new_pack = {**old_pack, "model": new_model, "val_logloss": 0.05607312077354993,
                "rows": np.array([0.1 + 2 ** -55, 0.2])}
    path = tmp_path / "ml_loto.joblib"
    joblib.dump(old_pack, path)
    before = path.read_bytes()
    probe = {"model": lambda model: model.predict_proba(new_x)[:, 1]}
    assert dump_pack_unless_equivalent(new_pack, path, predictions=probe) is False
    assert path.read_bytes() == before
    assert dump_pack_unless_equivalent(new_pack, path) is True          # không có hàm dự báo: so tuyệt đối
    joblib.dump(old_pack, path)
    for key, value in (("val_logloss", 0.0561), ("window_days", 1461), ("features", ["gap"]),
                       ("rows", np.array([0.1, 0.21])), ("model", _hgb(new_x, 1 - labels))):
        joblib.dump(old_pack, path)
        assert dump_pack_unless_equivalent({**new_pack, key: value}, path, predictions=probe) is True, key


def test_an_old_model_that_cannot_predict_on_the_new_data_is_replaced(tmp_path: Path) -> None:
    features, labels = _gap_features(shift_ulp=False)
    path = tmp_path / "cau_keo_de.joblib"
    joblib.dump({"model": _hgb(features[:, :1], labels)}, path)
    probe = {"model": lambda model: model.predict_proba(features)[:, 1]}   # hai cột: mô hình cũ chỉ biết một
    assert dump_pack_unless_equivalent({"model": _hgb(features, labels)}, path, predictions=probe) is True
    assert joblib.load(path)["model"].n_features_in_ == 2


def _calls_without_predictions(source: str) -> list[int]:
    import ast
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None))
            == "dump_pack_unless_equivalent" and not any(kw.arg == "predictions" for kw in node.keywords)]


def test_every_model_pack_writer_says_how_to_compare_its_models() -> None:
    """Mỗi chỗ ghi pack khai ``predictions`` (kể cả ``{}`` cho pack không có mô hình): thiếu nó thì mô hình học
    lại trên runner khác CPU bị so tuyệt đối và tệp bị ghi lại dù dự báo trùng."""
    root = Path(__file__).resolve().parents[2] / "src"
    writers = {path: path.read_text(encoding="utf-8") for path in root.rglob("*.py")
               if "dump_pack_unless_equivalent(" in path.read_text(encoding="utf-8") and path.name != "model_io.py"}
    assert {path.name for path in writers} >= {"ml_train.py", "cau_keo_ml.py", "cau_keo_domain_challenger.py",
                                                "meta_predictor.py"}
    assert {str(path): lines for path, text in writers.items() if (lines := _calls_without_predictions(text))} == {}
    assert _calls_without_predictions("dump_pack_unless_equivalent(pack, path, stamp_keys=S)") == [1]
    assert _calls_without_predictions("model_io.dump_pack_unless_equivalent(pack, path, predictions={})") == []
