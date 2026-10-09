"""Hồi quy vòng đời pack: lỗi học/ghi không được phá bản đương nhiệm."""

import logging
import lzma
import zlib
from datetime import date
from io import BytesIO

import joblib
import numpy as np
import pandas as pd
import pytest

import model_io
import meta_predictor
import ml_predict
import ml_train
from ensemble_utils import normalize_distribution


def test_failed_retrain_keeps_incumbent_bytes(tmp_path, monkeypatch):
    path = tmp_path / "ml_loto.joblib"
    joblib.dump({"stale": True}, path)
    incumbent = path.read_bytes()

    def fail(*args, **kwargs):
        raise RuntimeError("fit failed")

    monkeypatch.setattr(ml_predict, "train_one", fail)
    with pytest.raises(RuntimeError, match="fit failed"):
        ml_predict._load_or_train_model(
            "loto", tmp_path, window_days=2000, latest_data_date="2026-10-08"
        )
    assert path.exists() and path.read_bytes() == incumbent


@pytest.mark.parametrize("corrupt", [b"not-a-valid-joblib", b"\x80\x04"])
def test_corrupt_serialization_reaches_retrain_without_logging_payload(
    tmp_path, monkeypatch, caplog, corrupt
):
    (tmp_path / "ml_loto.joblib").write_bytes(corrupt)

    def fail(*args, **kwargs):
        raise RuntimeError("retrain reached")

    monkeypatch.setattr(ml_predict, "train_one", fail)
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match="retrain reached"):
        ml_predict._load_or_train_model(
            "loto", tmp_path, window_days=2000, latest_data_date="2026-10-08"
        )
    assert corrupt.decode("latin1") not in caplog.text


def test_load_error_does_not_log_exception_contents(tmp_path, monkeypatch, caplog):
    (tmp_path / "ml_loto.joblib").write_bytes(b"old")

    def corrupt(*args):
        raise ValueError("private-pack-contents")

    def fail(*args, **kwargs):
        raise RuntimeError("retrain reached")

    monkeypatch.setattr(joblib, "load", corrupt)
    monkeypatch.setattr(ml_predict, "train_one", fail)
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match="retrain reached"):
        ml_predict._load_or_train_model(
            "loto", tmp_path, window_days=2000, latest_data_date="2026-10-08"
        )
    assert "private-pack-contents" not in caplog.text


@pytest.mark.parametrize('compressor,position,error', [('zlib', 5, zlib.error), ('lzma', 20, lzma.LZMAError)])
@pytest.mark.parametrize('loader', ['base', 'cau_keo', 'domain', 'meta'])
def test_corrupt_compressed_pack_reaches_safe_recovery(tmp_path, monkeypatch, compressor, position, error, loader):
    buffer = BytesIO()
    joblib.dump({'private-pack':list(range(30))}, buffer, compress=(compressor, 3))
    raw = bytearray(buffer.getvalue())
    raw[position] ^= 255
    with pytest.raises(error):
        joblib.load(BytesIO(raw))
    filename = 'ml_loto.joblib' if loader == 'base' else 'meta_loto.joblib' if loader == 'meta' else 'cau_keo_loto.joblib'
    path = tmp_path / filename
    path.write_bytes(raw)
    def fail_train(*args, **kwargs):
        raise RuntimeError('retrain reached')
    if loader == 'meta':
        from predict_nextday_2d import _meta_prediction
        vector = np.full(100, .2)
        prediction, trust, info = _meta_prediction(tmp_path, 'loto', date(2026, 1, 2), *([vector] * 6))
        np.testing.assert_array_equal(prediction, vector)
        assert trust == 0 and info['active'] is False
        assert 'private-pack' not in info['reason']
    elif loader == 'base':
        monkeypatch.setattr(ml_predict, 'train_one', fail_train)
        with pytest.raises(RuntimeError, match='retrain reached'):
            ml_predict._load_or_train_model('loto', tmp_path, window_days=2000, latest_data_date='2026-10-08')
    elif loader == 'domain':
        import cau_keo_domain_challenger as module
        (tmp_path / 'cau_keo_loto_all.csv').write_text('existing output')
        monkeypatch.setattr(module, 'run_baseline', fail_train)
        with pytest.raises(RuntimeError, match='retrain reached'):
            module._ensure_baseline(mode='loto', models_dir=tmp_path, out_dir=tmp_path, config=module.CauKeoConfig())
    else:
        import cau_keo_ml as module
        from tests.test_cau_keo_ml import _synthetic_training
        x, y = _synthetic_training(120, signal=0., seed=7)
        monkeypatch.setattr(module, 'build_cau_keo_feature_frame', lambda *args, **kwargs: (x, y))
        monkeypatch.setattr(module, '_train_model', fail_train)
        with pytest.raises(RuntimeError, match='retrain reached'):
            module._load_or_train('loto', tmp_path, module.CauKeoConfig())
    assert path.read_bytes() == raw


@pytest.mark.parametrize("stage", ["dump", "replace"])
def test_atomic_model_write_failure_preserves_incumbent_and_removes_temp(
    tmp_path, monkeypatch, stage
):
    path = tmp_path / "model.joblib"
    joblib.dump({"incumbent": True}, path)
    before = path.read_bytes()

    def fail_dump(value, stream):
        if hasattr(stream, "write"):
            stream.write(b"partial")
        else:
            stream.write_bytes(b"partial")
        raise OSError("disk full")

    def fail_replace(*args):
        raise OSError("replace failed")

    if stage == "dump":
        monkeypatch.setattr(joblib, "dump", fail_dump)
    else:
        monkeypatch.setattr(model_io.os, "replace", fail_replace)
    with pytest.raises(OSError):
        model_io.atomic_joblib_dump({"candidate": True}, path)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_model_write_roundtrips(tmp_path):
    path = tmp_path / "model.joblib"
    model_io.atomic_joblib_dump({"weights": np.arange(5)}, path)
    np.testing.assert_array_equal(joblib.load(path)["weights"], np.arange(5))


def test_base_training_dump_failure_keeps_old_pack(tmp_path, monkeypatch):
    path = tmp_path / "ml_loto.joblib"
    joblib.dump({"incumbent": True}, path)
    before = path.read_bytes()
    frame = pd.DataFrame(np.zeros((200, len(ml_train.FEATURE_COLUMNS))), columns=ml_train.FEATURE_COLUMNS)
    frame["date"] = pd.date_range("2025-01-01", periods=200)
    labels = pd.Series(np.arange(200) % 2)
    monkeypatch.setattr(ml_train, "build_ml_table", lambda **kwargs: (frame, labels))
    monkeypatch.setattr(ml_train, "_candidate_configs", lambda: [{"name": "test"}])

    class Model:
        def predict_proba(self, x):
            return np.full((len(x), 2), 0.5)

    monkeypatch.setattr(ml_train, "_fit_candidate", lambda *args: Model())

    def fail_dump(value, destination):
        if hasattr(destination, "write"):
            destination.write(b"partial")
        else:
            destination.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(joblib, "dump", fail_dump)
    with pytest.raises(OSError, match="disk full"):
        ml_train.train_one("loto", tmp_path)
    assert path.read_bytes() == before


def test_disabled_meta_dump_failure_keeps_old_pack(tmp_path, monkeypatch):
    path = tmp_path / "meta_loto.joblib"
    joblib.dump({"incumbent": True}, path)
    before = path.read_bytes()
    history = tmp_path / "history.csv"
    pd.DataFrame({"target_date": ["2026-01-01"], "number": [0], "y": [0],
                  "p_ml": [0.2], "p_active": [0.2], "p_stable": [0.2]}).to_csv(history, index=False)

    def shortage(*args, **kwargs):
        raise meta_predictor.InsufficientMetaHistory({"full": 1}, 100)

    def fail_dump(value, destination):
        if hasattr(destination, "write"):
            destination.write(b"partial")
        else:
            destination.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(meta_predictor, "_select_component_tier", shortage)
    monkeypatch.setattr(joblib, "dump", fail_dump)
    with pytest.raises(OSError, match="disk full"):
        meta_predictor.train_meta("loto", history, tmp_path, tmp_path / "reports")
    assert path.read_bytes() == before


def test_distribution_with_large_finite_values_remains_normalized():
    actual = normalize_distribution(np.full(100, 1e308))
    assert np.isfinite(actual).all()
    assert actual.sum() == pytest.approx(1.0)
    np.testing.assert_allclose(actual, 0.01)
