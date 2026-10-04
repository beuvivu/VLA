from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

import meta_predictor as meta
from ensemble_components import COMPONENT_POLICY, policy_column
from predict_nextday_2d import _meta_prediction


def _history(mode: str, days: int, valid_days: int | None = None) -> pd.DataFrame:
    """Đủ 100 số mỗi kỳ; cờ nguồn cũ không được biến thành bằng chứng mới."""
    rng = np.random.default_rng(413)
    rows = []
    for i, day in enumerate(pd.date_range("2025-01-01", periods=days)):
        frame = pd.DataFrame({"target_date": day.date().isoformat(), "number": range(100)})
        frame["y"] = 0
        frame.loc[rng.choice(100, size=1 if mode == "de" else 23, replace=False), "y"] = 1
        for name in ("ml", "cau", "stat", "active", "stable"):
            p = rng.uniform(0.15, 0.30, size=100)
            frame[f"p_{name}"] = p / p.sum() if mode == "de" else p
            frame[f"has_{name}"] = True
        frame[policy_column("cau")] = COMPONENT_POLICY["cau"]
        if valid_days is not None and i < days - valid_days:
            frame["has_ml"] = False
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def _train(tmp_path: Path, mode: str, frame: pd.DataFrame, **kwargs) -> dict:
    path = tmp_path / f"pred_{mode}.csv"
    frame.to_csv(path, index=False)
    return meta.train_meta(mode, path, tmp_path / "models", tmp_path / "reports", **kwargs)


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_short_valid_history_replaces_stale_model_with_disabled_artifacts(tmp_path, mode):
    """Bắt lỗi dừng pipeline hoặc giữ challenger cũ khi chỉ còn 28 kỳ thật."""
    models, reports = tmp_path / "models", tmp_path / "reports"
    models.mkdir()
    reports.mkdir()
    joblib.dump({"model": "stale", "quality_pass": True, "meta_trust": 0.4}, models / f"meta_{mode}.joblib")
    (reports / f"meta_report_{mode}.csv").write_text("validation_logloss\n0.1\n")
    pack = _train(tmp_path, mode, _history(mode, 120, valid_days=28))
    assert pack["status"] == "insufficient_history"
    assert pack["history_days"] == 28
    assert pack["minimum_history_days"] == 100
    assert set(pack["tier_maturity_days"].values()) == {28}
    saved = joblib.load(models / f"meta_{mode}.joblib")
    assert saved["model"] is None
    assert saved["quality_pass"] is False
    assert saved["meta_trust"] == 0.0
    assert saved.get("trained_through_target_date") is None
    assert saved.get("validation_logloss") is None
    report = json.loads((reports / f"meta_report_{mode}.json").read_text())
    assert report["status"] == "insufficient_history"
    assert report["history_days"] == 28
    table = pd.read_csv(reports / f"meta_report_{mode}.csv")
    assert table["status"].tolist() == ["insufficient_history"]
    assert "validation_logloss" not in table or table["validation_logloss"].isna().all()


def test_disabled_model_returns_exact_linear_vector_and_shortage_reason(tmp_path):
    """Bắt nhầm trạng thái thiếu lịch sử thành thiếu component hoặc model hoạt động."""
    pack = {"schema_version": meta.META_SCHEMA_VERSION, "mode": "de", "model": None,
            "status": "insufficient_history", "meta_trust": 0.0, "quality_pass": False,
            "component_cols": [], "history_days": 28, "minimum_history_days": 100}
    joblib.dump(pack, tmp_path / "meta_de.joblib")
    linear = np.arange(1.0, 101.0)
    linear /= linear.sum()
    vector, trust, report = _meta_prediction(
        tmp_path, "de", date(2026, 9, 28), *([linear] * 6),
        available={name: True for name in ("ml", "cau", "stat", "active", "stable")},
    )
    np.testing.assert_array_equal(vector, linear)
    assert trust == 0.0
    assert report["active"] is False
    assert report["reason"] == "insufficient_history"
    assert report["history_days"] == 28


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_mature_history_trains_real_model_and_keeps_chronological_validation(tmp_path, mode):
    """Nhánh luôn vô hiệu hóa không được làm cả bộ kiểm phát hành xanh."""
    pack = _train(tmp_path, mode, _history(mode, 100))
    assert pack["status"] == "trained"
    assert pack["model"] is not None
    assert pack["history_days"] == 100
    blocks = [pack[name] for name in ("train_days", "calibration_days", "selection_days", "validation_days")]
    assert all(max(left) < min(right) for left, right in zip(blocks[:-1], blocks[1:], strict=True))
    assert len(pack["validation_days"]) >= 20
    assert np.isfinite(pack["validation_logloss"])
    p = np.full(100, 0.01 if mode == "de" else 0.23)
    prediction = meta.predict_meta(pack, mode, "2026-01-01", *([p] * 5))
    assert prediction.shape == (100,)
    assert np.isfinite(prediction).all()
    if mode == "de":
        assert prediction.sum() == pytest.approx(1.0)


@pytest.mark.parametrize("stage", ["_fit_candidate", "_select_component_tier"])
def test_training_error_is_not_reclassified_as_insufficient_history(tmp_path, monkeypatch, stage):
    """Chỉ thiếu dữ liệu được fallback; lỗi estimator phải làm lượt đỏ."""
    def fail_fit(*args, **kwargs):
        raise RuntimeError("estimator failed")

    monkeypatch.setattr(meta, stage, fail_fit)
    with pytest.raises(RuntimeError, match="estimator failed"):
        _train(tmp_path, "loto", _history("loto", 100))
    assert not (tmp_path / "models" / "meta_loto.joblib").exists()


def test_cli_shortage_succeeds_but_malformed_history_still_fails(tmp_path):
    """Chạy đúng entrypoint dùng bởi pipeline --strict và script phát hành."""
    history = tmp_path / "pred_loto.csv"
    _history("loto", 28).to_csv(history, index=False)
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / "src/meta_predictor.py"), "--mode", "loto",
               "--history-dir", str(tmp_path), "--models-dir", str(tmp_path / "models"),
               "--report-dir", str(tmp_path / "reports")]
    result = subprocess.run(command, capture_output=True, text=True, cwd=root, check=False)
    assert result.returncode == 0, result.stderr
    assert joblib.load(tmp_path / "models/meta_loto.joblib")["quality_pass"] is False
    history.write_text("bad_column\ninvalid\n")
    result = subprocess.run(command, capture_output=True, text=True, cwd=root, check=False)
    assert result.returncode != 0


def test_release_check_accepts_truthful_shortage_but_rejects_enabled_pack(tmp_path):
    """Thực thi nguyên khối Python của shell, không kiểm chuỗi mã nguồn."""
    for mode in ("loto", "de"):
        _train(tmp_path, mode, _history(mode, 28))
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts/release_check.sh").read_text()
    code = script.split("python - <<PYMETA\n", 1)[1].split("\nPYMETA", 1)[0]
    code = code.replace("$TMP_MODELS", str(tmp_path / "models"))
    code = code.replace("$TMP_PRED", str(tmp_path / "reports"))
    result = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    path = tmp_path / "models/meta_loto.joblib"
    pack = joblib.load(path)
    pack["quality_pass"], pack["meta_trust"] = True, 0.15
    joblib.dump(pack, path)
    result = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode != 0, "Báo thiếu lịch sử không được che challenger đang bật"
