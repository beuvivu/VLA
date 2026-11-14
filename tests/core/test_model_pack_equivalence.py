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

from core.model_io import atomic_joblib_dump, dump_pack_unless_equivalent

STAMPS = frozenset({"trained_at_utc"})


def _model(c: float = 1.0) -> LogisticRegression:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, 3))
    return LogisticRegression(C=c).fit(x, (x[:, 0] > 0).astype(int))


def _pack(model: LogisticRegression, when: str, **extra: object) -> dict[str, object]:
    return {"mode": "de", "model": model, "features": ["a", "b", "c"], "trained_at_utc": when, **extra}


def test_a_pack_that_only_differs_in_training_time_keeps_the_file(tmp_path: Path) -> None:
    path = tmp_path / "meta_de.joblib"
    atomic_joblib_dump(_pack(_model(), "2026-11-10T11:39:26Z"), path)
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
    atomic_joblib_dump(shared, path)
    before = path.read_bytes()
    assert dump_pack_unless_equivalent(separate, path, stamp_keys=STAMPS) is False
    assert path.read_bytes() == before


def test_a_different_model_or_field_is_written(tmp_path: Path) -> None:
    path = tmp_path / "meta_de.joblib"
    atomic_joblib_dump(_pack(_model(), "a"), path)
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
