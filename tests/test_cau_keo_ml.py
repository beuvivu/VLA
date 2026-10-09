from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

import cau_keo_ml
from cau_keo_ml import (
    FEATURE_COLS,
    TRUST_POLICY_VERSION,
    _add_ai_judgement,
    _bong_number,
    _score_band,
    _train_model,
    trust_from_pack,
    trusted_probability,
)
from ml_train import model_trust


def test_bong_number_modulo_5_transform_preserves_two_digit_range() -> None:
    assert _bong_number(0) == 55
    assert _bong_number(49) == 94
    assert _bong_number(95) == 40


def test_score_band_thresholds() -> None:
    assert _score_band(80) == "very_high"
    assert _score_band(60) == "high"
    assert _score_band(40) == "medium"
    assert _score_band(10) == "low"


def test_ai_judgement_adds_reason_and_probability_alias() -> None:
    df = pd.DataFrame(
        {
            "number_str": ["00", "01", "02"],
            "number": [0, 1, 2],
            "ml_prob_raw": [0.3, 0.1, 0.2],
            "path_support": [100, 20, 50],
            "cond_de_rate": [0.4, 0.05, 0.2],
            "cond_loto_max_rate": [0.35, 0.1, 0.2],
            "same_weekday_freq_364": [5, 0, 3],
            "reverse_hit_today": [1, 0, 0],
            "is_reverse_prev_special": [0, 0, 0],
            "is_bong_prev_special": [0, 0, 1],
            "cham_overlap_prev_special": [1, 0, 1],
            "gap": [8, 1, 4],
            "freq_30d": [9, 2, 5],
            "freq_7d": [3, 0, 1],
            "trend_7_vs_30": [1.5, -0.2, 0.5],
        }
    )
    out = _add_ai_judgement(df, mode="de", trust=1.0, base_rate=0.01)
    assert "cau_score" in out.columns
    assert "primary_reason" in out.columns
    assert "prob" in out.columns
    assert abs(float(out["prob"].sum()) - 1.0) < 1e-9
    assert out.iloc[0]["number_str"] == "00"


def _judgement_frame(raw: list[float]) -> pd.DataFrame:
    n = len(raw)
    return pd.DataFrame(
        {
            "number_str": [f"{i:02d}" for i in range(n)],
            "number": list(range(n)),
            "ml_prob_raw": raw,
            "path_support": [10 * (i + 1) for i in range(n)],
            "cond_de_rate": [0.1] * n,
            "cond_loto_max_rate": [0.2] * n,
            "same_weekday_freq_364": [1] * n,
            "reverse_hit_today": [0] * n,
            "is_reverse_prev_special": [0] * n,
            "is_bong_prev_special": [0] * n,
            "cham_overlap_prev_special": [0] * n,
            "gap": [3] * n,
            "freq_30d": [5] * n,
            "freq_7d": [1] * n,
            "trend_7_vs_30": [0.0] * n,
        }
    )


def test_trusted_probability_shrinks_toward_the_base_rate_by_trust() -> None:
    raw = np.array([0.30, 0.20, 0.10])
    np.testing.assert_allclose(
        trusted_probability(raw, mode="loto", trust=0.25, base_rate=0.24),
        0.25 * raw + 0.75 * 0.24,
    )
    # Đặc Biệt: co rồi chuẩn hoá lại về tổng 1.
    shrunk = 0.25 * raw + 0.75 * 0.01
    np.testing.assert_allclose(
        trusted_probability(raw, mode="de", trust=0.25, base_rate=0.01),
        shrunk / shrunk.sum(),
    )


def test_zero_trust_emits_the_base_rate_but_keeps_the_raw_ranking() -> None:
    raw = [0.30, 0.10, 0.20]
    out = _add_ai_judgement(_judgement_frame(raw), mode="loto", trust=0.0, base_rate=0.237)
    np.testing.assert_allclose(out["prob"].astype(float), 0.237)
    assert (out["model_trust"] == 0.0).all() and (out["base_rate"] == 0.237).all()
    # Sổ lịch sử đọc phiên bản này để không trộn xác suất thô cũ với bản đã co.
    assert (out["trust_policy_version"] == TRUST_POLICY_VERSION).all()
    # Xác suất thô vẫn được giữ và vẫn quyết định điểm, nên thứ tự không đổi.
    by_number = out.set_index("number")
    np.testing.assert_allclose(by_number.loc[[0, 1, 2], "ml_prob_raw"], raw)
    assert by_number.loc[0, "cau_score"] > by_number.loc[1, "cau_score"]
    de = _add_ai_judgement(_judgement_frame(raw), mode="de", trust=0.0, base_rate=0.0102)
    np.testing.assert_allclose(de["prob"].astype(float), 1.0 / 3.0)


def _pack(**overrides: object) -> dict[str, object]:
    pack: dict[str, object] = {
        "model_trust": 0.2,
        "base_rate": 0.238,
        "trust_policy_version": TRUST_POLICY_VERSION,
    }
    pack.update(overrides)
    return {k: v for k, v in pack.items() if v is not None}


def test_trust_from_pack_has_no_default_for_a_pack_saved_before_the_policy() -> None:
    assert trust_from_pack(_pack()) == (0.2, 0.238)
    for bad in (
        _pack(trust_policy_version=None),
        _pack(trust_policy_version=TRUST_POLICY_VERSION + 1),
        _pack(trust_policy_version=True),
        _pack(model_trust=None),
        _pack(model_trust=1.5),
        _pack(model_trust=float("nan")),
        _pack(model_trust=True),
        _pack(base_rate=None),
        _pack(base_rate=-0.1),
        "không phải gói",
    ):
        with pytest.raises(ValueError):
            trust_from_pack(bad)


def _synthetic_training(days: int, signal: float, seed: int) -> tuple[pd.DataFrame, pd.Series]:
    """``days`` kỳ × 100 số; nhãn về với xác suất 0,24, cộng ``signal`` khi ``hit_today`` = 1."""
    rng = np.random.default_rng(seed)
    n = days * 100
    X = pd.DataFrame(rng.integers(0, 5, size=(n, len(FEATURE_COLS))).astype(float), columns=FEATURE_COLS)
    X["hit_today"] = rng.integers(0, 2, size=n)
    X["anchor_date"] = np.repeat(pd.date_range("2020-01-01", periods=days, freq="D"), 100)
    X["predict_for_date"] = (X["anchor_date"] + pd.Timedelta(days=1)).dt.date.astype(str)
    p = 0.24 + signal * X["hit_today"].to_numpy()
    y = pd.Series((rng.random(n) < p).astype(int), name="target")
    return X, y


def _fast_classifier(**_: object) -> LogisticRegression:
    """Thay cây tăng cường bằng hồi quy logistic: phép kiểm canh luật tin, không canh mô hình."""
    return LogisticRegression(max_iter=200)


def test_training_dump_failure_preserves_incumbent_pack(tmp_path, monkeypatch):
    path = tmp_path / "cau_keo_loto.joblib"
    joblib.dump({"incumbent": True}, path)
    before = path.read_bytes()
    monkeypatch.setattr(cau_keo_ml, "HistGradientBoostingClassifier", _fast_classifier)
    X, y = _synthetic_training(120, signal=0.0, seed=7)

    def fail_dump(value, destination):
        if hasattr(destination, "write"):
            destination.write(b"partial")
        else:
            destination.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(joblib, "dump", fail_dump)
    with pytest.raises(OSError, match="disk full"):
        _train_model("loto", X, y, tmp_path)
    assert path.read_bytes() == before


def test_corrupt_cached_pack_retrains_without_logging_private_contents(tmp_path, monkeypatch, caplog):
    path = tmp_path / "cau_keo_loto.joblib"
    path.write_bytes(b"not-a-valid-joblib")
    X, y = _synthetic_training(120, signal=0.0, seed=7)
    monkeypatch.setattr(cau_keo_ml, "build_cau_keo_feature_frame", lambda *args, **kwargs: (X, y))

    def invalid_load(*args):
        raise ValueError("private-pack-contents")

    def fail_train(*args, **kwargs):
        raise RuntimeError("retrain reached")

    monkeypatch.setattr(joblib, "load", invalid_load)
    monkeypatch.setattr(cau_keo_ml, "_train_model", fail_train)
    with pytest.raises(RuntimeError, match="retrain reached"):
        cau_keo_ml._load_or_train("loto", tmp_path, cau_keo_ml.CauKeoConfig())
    assert "private-pack-contents" not in caplog.text
    assert path.read_bytes() == b"not-a-valid-joblib"


def test_training_measures_trust_against_the_base_rate_known_before_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cau_keo_ml, "HistGradientBoostingClassifier", _fast_classifier)
    X, y = _synthetic_training(120, signal=0.0, seed=7)
    pack, report, _ = _train_model("loto", X, y, tmp_path)
    val_start = pd.Timestamp(pack["val_start"])
    before = (X["anchor_date"] < val_start).to_numpy()
    # Nền học CHỈ từ các kỳ trước khối thẩm định, không nhìn khối được chấm.
    assert pack["base_rate"] == pytest.approx(float(y[before].mean()), abs=0.0)
    assert pack["model_trust"] == model_trust(pack["logloss_skill"], pack["brier_skill"])
    assert pack["trust_policy_version"] == TRUST_POLICY_VERSION
    assert float(report["model_trust"].iloc[0]) == pack["model_trust"]
    # Nhiễu thuần: không có kỹ năng để tin.
    assert pack["model_trust"] < 0.05
    saved = joblib.load(tmp_path / "cau_keo_loto.joblib")
    assert trust_from_pack(saved) == (pack["model_trust"], pack["base_rate"])

    X, y = _synthetic_training(120, signal=0.25, seed=7)
    planted, _, _ = _train_model("loto", X, y, tmp_path / "planted")
    # Có tín hiệu thật thì kỹ năng thẩm định dương và luật tin cho nó vào.
    assert planted["model_trust"] > 0.5


def test_a_cached_pack_without_the_trust_policy_is_retrained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    X, y = _synthetic_training(30, signal=0.0, seed=1)
    X["anchor_date"] = X["anchor_date"].dt.date.astype(str)
    latest = str(X["anchor_date"].max())
    monkeypatch.setattr(cau_keo_ml, "build_cau_keo_feature_frame", lambda *a, **k: (X, y))
    calls: list[str] = []

    def fake_train(mode, X_train, y_train, models_dir):
        calls.append(mode)
        return {"retrained": True}, pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(cau_keo_ml, "_train_model", fake_train)
    model = LogisticRegression().fit(X[FEATURE_COLS].to_numpy(dtype=np.float32), y)
    stale = {"features": FEATURE_COLS, "trained_through_date": latest, "model": model}
    joblib.dump(stale, tmp_path / "cau_keo_loto.joblib")
    pack, _, _ = cau_keo_ml._load_or_train("loto", tmp_path, cau_keo_ml.CauKeoConfig())
    assert calls == ["loto"] and pack == {"retrained": True}

    # Đối chứng: cùng gói nhưng mang luật tin hiện hành thì dùng lại, không học lại.
    joblib.dump({**stale, **_pack()}, tmp_path / "cau_keo_loto.joblib")
    pack, _, _ = cau_keo_ml._load_or_train("loto", tmp_path, cau_keo_ml.CauKeoConfig())
    assert calls == ["loto"] and trust_from_pack(pack) == (0.2, 0.238)
