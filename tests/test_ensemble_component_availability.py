from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ensemble_components import (
    COMPONENT_POLICY,
    availability_from_history_day,
    policy_column,
    probability_component,
    renormalize_available_weights,
)
from ensemble_utils import EnsembleWeights
from learn_ensemble_weights import _select_recent_complete_days
from record_pred_history import _sanitize_history


def _frame(value: float = 0.2) -> pd.DataFrame:
    return pd.DataFrame({"number": np.arange(100), "prob": np.full(100, value)})


def test_missing_or_zero_component_is_unavailable() -> None:
    missing = probability_component(pd.DataFrame(columns=["number", "prob"]), mode="loto")
    zero = probability_component(_frame(0.0), mode="loto")
    assert not missing.available
    assert not zero.available
    assert np.isnan(missing.prob).all()
    assert zero.reason == "all_zero_probability_vector"


def test_stale_dated_component_is_unavailable() -> None:
    frame = _frame(0.2)
    frame["predict_for_date"] = "2026-08-31"
    stale = probability_component(
        frame,
        mode="loto",
        expected_target_date="2026-09-01",
    )
    assert stale.available is False
    assert stale.reason == "stale_predict_for_date"


def test_de_component_is_normalized_only_when_valid() -> None:
    comp = probability_component(_frame(0.2), mode="de")
    assert comp.available
    assert np.isclose(comp.prob.sum(), 1.0)


def test_available_weights_are_renormalized_without_missing_component() -> None:
    base = EnsembleWeights(w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125)
    effective = renormalize_available_weights(
        base,
        {"ml": True, "cau": False, "stat": True, "active": True, "stable": True},
    )
    assert effective.w_cau == 0.0
    assert np.isclose(sum(effective.as_dict().values()), 1.0)
    assert effective.w_ml > base.w_ml


def test_no_available_component_fails_loudly() -> None:
    base = EnsembleWeights(w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125)
    with pytest.raises(ValueError, match="No valid ensemble component"):
        renormalize_available_weights(base, {k: False for k in ["ml", "cau", "stat", "active", "stable"]})


def _history_day(day: str, *, zero_component: str | None = None, explicit_flags: bool = False) -> pd.DataFrame:
    y = np.zeros(100, dtype=int)
    y[0] = 1
    data: dict[str, object] = {
        "target_date": [day] * 100,
        "number": np.arange(100),
        "y": y,
    }
    for key in ["ml", "cau", "stat", "active", "stable"]:
        p = np.full(100, 0.2, dtype=float)
        if key == zero_component:
            p[:] = 0.0
        data[f"p_{key}"] = p
        data[policy_column("cau")] = COMPONENT_POLICY["cau"]
        if explicit_flags:
            data[f"has_{key}"] = [key != zero_component] * 100
    return pd.DataFrame(data)


def test_legacy_all_zero_placeholder_is_rejected_by_weight_learner() -> None:
    good = _history_day("2026-08-01")
    bad = _history_day("2026-08-02", zero_component="cau")
    df = pd.concat([good, bad], ignore_index=True)
    assert _select_recent_complete_days(df, 180) == ["2026-08-01"]


def test_history_sanitizer_migrates_old_zero_placeholder() -> None:
    old = _history_day("2026-08-02", zero_component="cau")
    clean = _sanitize_history(old)
    assert clean["has_ml"].all()
    assert not clean["has_cau"].any()
    assert clean["p_cau"].isna().all()


def test_explicit_string_false_availability_is_not_truthy() -> None:
    sub = _history_day("2026-08-01")
    for key in ["ml", "cau", "stat", "active", "stable"]:
        sub[f"has_{key}"] = "True"
    sub["has_stat"] = "False"
    available = availability_from_history_day(sub)
    assert available["ml"] is True
    assert available["stat"] is False


def test_learners_ignore_cau_recorded_under_an_older_definition() -> None:
    """Trước 04-10-2026 cột ``p_cau`` là xác suất THÔ; sau đó là bản đã co về nền.

    Bộ học trọng số và tầng xếp chồng không được học trên hỗn hợp hai định
    nghĩa, còn trang Chất lượng — dựng lại thứ ĐÃ công bố — vẫn đọc dòng cũ.
    """
    current = _history_day("2026-10-06")
    legacy = _history_day("2026-10-01").drop(columns=[policy_column("cau")])
    older = _history_day("2026-10-02")
    older[policy_column("cau")] = COMPONENT_POLICY["cau"] - 1
    df = pd.concat([legacy, older, current], ignore_index=True)

    assert _select_recent_complete_days(df, 180) == ["2026-10-06"]
    assert availability_from_history_day(legacy)["cau"] is True
    assert availability_from_history_day(legacy, current_policy=True)["cau"] is False
    assert availability_from_history_day(older, current_policy=True)["cau"] is False
    # Thành phần không đổi định nghĩa không bị ảnh hưởng.
    assert availability_from_history_day(legacy, current_policy=True)["ml"] is True


def test_stacked_model_tiers_without_cau_still_use_legacy_days() -> None:
    import meta_predictor as meta

    legacy = _history_day("2026-10-01").drop(columns=[policy_column("cau")])
    current = _history_day("2026-10-06")
    df = pd.concat([legacy, current], ignore_index=True)
    with_cau = meta._complete_days_for_components(df, ["p_ml", "p_cau"], 0, mode="loto")
    without_cau = meta._complete_days_for_components(df, ["p_ml", "p_active"], 0, mode="loto")
    assert with_cau == ["2026-10-06"]
    assert without_cau == ["2026-10-01", "2026-10-06"]


def test_history_records_the_definition_each_component_declares(tmp_path, monkeypatch) -> None:
    import record_pred_history as recorder

    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame({"date": ["2026-01-01"]}).to_csv(data / "xsmb.csv", index=False)
    dirs = {name: tmp_path / name for name in ("path_ui", "ml", "ai_ml", "stat", "history")}
    for path in dirs.values():
        path.mkdir()
    full = pd.DataFrame({"number": range(100), "prob": 0.2, "target_date": "2026-01-02"})
    full.to_csv(dirs["ml"] / "predict_next_loto_ml_all.csv", index=False)
    full.assign(trust_policy_version=COMPONENT_POLICY["cau"]).to_csv(
        dirs["ai_ml"] / "cau_keo_loto_all.csv", index=False
    )
    # Đặc Biệt: tệp cầu-kèo không khai phiên bản — phải ghi là KHÔNG rõ, không đoán.
    full.assign(prob=0.01).to_csv(dirs["ai_ml"] / "cau_keo_de_all.csv", index=False)
    argv = ["record_pred_history.py", "--data-dir", str(data), "--path-ui-dir", str(dirs["path_ui"]),
            "--ml-dir", str(dirs["ml"]), "--out-dir", str(dirs["history"]),
            "--ai-ml-dir", str(dirs["ai_ml"]), "--stat-dir", str(dirs["stat"])]
    monkeypatch.setattr(sys, "argv", argv)
    recorder.main()

    loto = pd.read_csv(dirs["history"] / "pred_loto.csv")
    de = pd.read_csv(dirs["history"] / "pred_de.csv")
    assert (loto[policy_column("cau")] == COMPONENT_POLICY["cau"]).all()
    assert de[policy_column("cau")].isna().all()
    assert recorder._policy_version(full.assign(trust_policy_version=[1] * 99 + [2])) != 1
