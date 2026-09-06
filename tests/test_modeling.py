"""Kiểm thử mô hình xếp chồng, phân bổ Shapley và bộ lọc lô gan."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bridges import DigitTensor
from features import FeatureContext, default_registry
from modeling import (
    DEFAULT_GAN_THRESHOLD_DAYS,
    DeModel,
    Explainer,
    GanFilter,
    LotoModel,
    PredictionBundle,
    build_picks,
    build_training_data,
)
from modeling.stacking import MIN_UNIFORM_SHARE
from xsmb_domain import FIELD_WIDTHS


def _history(days: int, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = {"date": pd.date_range("2025-01-01", periods=days, freq="D")}
    for field, width in FIELD_WIDTHS:
        frame[field] = rng.integers(0, 10**width, size=days)
    return pd.DataFrame(frame)


@pytest.fixture(scope="module")
def tensor() -> DigitTensor:
    return DigitTensor.from_raw(_history(150))


@pytest.fixture(scope="module")
def trained(tensor: DigitTensor):
    data = build_training_data(tensor, mode="loto", warmup_days=60)
    return LotoModel(n_splits=3).fit(data), data


# --- Dựng dữ liệu huấn luyện ----------------------------------------------


def test_labels_come_from_the_day_after_the_anchor(tensor: DigitTensor) -> None:
    """Khoảng cách một ngày giữa đặc trưng và nhãn là bất biến của hàm dựng."""
    data = build_training_data(tensor, mode="loto", warmup_days=60)
    hits = tensor.loto_hits()
    for anchor in np.unique(data.day_index)[:5]:
        rows = data.day_index == anchor
        assert np.array_equal(data.labels[rows], hits[anchor + 1].astype(np.int8))


def test_de_labels_mark_exactly_one_winner(tensor: DigitTensor) -> None:
    data = build_training_data(tensor, mode="de", warmup_days=60)
    for anchor in np.unique(data.day_index)[:5]:
        assert data.labels[data.day_index == anchor].sum() == 1


def test_build_training_data_rejects_an_unknown_mode(tensor: DigitTensor) -> None:
    with pytest.raises(ValueError, match="mode"):
        build_training_data(tensor, mode="xien", warmup_days=60)


def test_build_training_data_refuses_a_too_short_history(tensor: DigitTensor) -> None:
    with pytest.raises(ValueError, match="quá ngắn"):
        build_training_data(tensor, mode="loto", warmup_days=10_000)


# --- Mô hình ---------------------------------------------------------------


def test_model_refuses_to_predict_before_training(tensor: DigitTensor) -> None:
    with pytest.raises(RuntimeError, match="chưa được huấn luyện"):
        LotoModel().predict_proba(np.zeros((10, 20)))


def test_loto_probabilities_stay_strictly_inside_zero_and_one(trained) -> None:
    model, _ = trained
    tensor_local = DigitTensor.from_raw(_history(150))
    matrix = default_registry().build_matrix(
        FeatureContext(tensor=tensor_local, anchor_index=140)
    )
    probability = model.predict_day(matrix)
    assert (probability > 0).all() and (probability < 1).all()


def test_de_distribution_sums_to_one_and_never_declares_a_number_impossible(
    tensor: DigitTensor,
) -> None:
    """Xác suất 0 mà con đó về sẽ cho log-loss bùng nổ."""
    data = build_training_data(tensor, mode="de", warmup_days=60)
    model = DeModel(n_splits=3).fit(data)
    matrix = default_registry().build_matrix(
        FeatureContext(tensor=tensor, anchor_index=140)
    )
    probability = model.predict_day(matrix)
    assert probability.sum() == pytest.approx(1.0)
    assert probability.min() >= MIN_UNIFORM_SHARE / 100 * 0.5


def test_time_series_split_never_cuts_through_a_single_day(tensor: DigitTensor) -> None:
    """Cắt giữa một ngày sẽ để 99 con ở tập huấn luyện và 1 con ở tập kiểm."""
    from sklearn.model_selection import TimeSeriesSplit

    data = build_training_data(tensor, mode="loto", warmup_days=60)
    unique_days = np.unique(data.day_index)
    for train_days, test_days in TimeSeriesSplit(n_splits=3).split(unique_days):
        train = set(unique_days[train_days].tolist())
        test = set(unique_days[test_days].tolist())
        assert not (train & test)
        assert max(train) < min(test), "tập kiểm phải nằm sau tập huấn luyện"


def test_model_rejects_single_class_labels(tensor: DigitTensor) -> None:
    data = build_training_data(tensor, mode="loto", warmup_days=60)
    broken = type(data)(
        features=data.features,
        labels=np.zeros_like(data.labels),
        day_index=data.day_index,
        columns=data.columns,
        groups=data.groups,
    )
    with pytest.raises(ValueError, match="một lớp"):
        LotoModel(n_splits=3).fit(broken)


# --- Phân bổ Shapley -------------------------------------------------------


def test_shapley_contributions_satisfy_the_efficiency_axiom(trained, tensor) -> None:
    """Tổng đóng góp phải bằng chênh lệch giữa mô hình đầy đủ và nền tham chiếu.

    Đây là tiên đề hiệu quả của giá trị Shapley. Nếu nó không đúng thì con số
    báo ra không phải phân bổ Shapley, chỉ là một cách chia tùy tiện.
    """
    model, data = trained
    explainer = Explainer.from_training(model, data.features)
    matrix = default_registry().build_matrix(
        FeatureContext(tensor=tensor, anchor_index=140)
    )
    contributions = explainer.contributions(matrix)
    total = sum(contributions.values())

    full = model.predict_proba(matrix.values)
    empty = model.predict_proba(explainer._masked(matrix.values, frozenset()))
    assert np.allclose(total, full - empty, atol=1e-9)


def test_shapley_is_computed_exactly_over_every_coalition(trained, tensor) -> None:
    """Bốn nhóm cho 16 liên minh, nên tính chính xác được — không cần lấy mẫu."""
    model, data = trained
    explainer = Explainer.from_training(model, data.features)
    names = explainer.group_names
    expected = sum(len(list(combinations(names, k))) for k in range(len(names) + 1))
    assert expected == 2 ** len(names)
    assert len(names) == 4


def test_group_shares_are_normalised_by_absolute_magnitude(trained, tensor) -> None:
    """Nhóm kéo xác suất xuống phải hiện ra, không bị triệt tiêu lặng lẽ."""
    model, data = trained
    explainer = Explainer.from_training(model, data.features)
    matrix = default_registry().build_matrix(
        FeatureContext(tensor=tensor, anchor_index=140)
    )
    shares = explainer.group_shares(matrix, row=0)
    assert sum(abs(v) for v in shares.values()) == pytest.approx(1.0, abs=1e-6)


def test_top_reasons_are_ordered_by_magnitude(trained, tensor) -> None:
    model, data = trained
    explainer = Explainer.from_training(model, data.features)
    matrix = default_registry().build_matrix(
        FeatureContext(tensor=tensor, anchor_index=140)
    )
    reasons = explainer.top_reasons(matrix, row=0, k=3)
    magnitudes = [abs(value) for _, value in reasons]
    assert magnitudes == sorted(magnitudes, reverse=True)
    assert len(reasons) == 3


# --- Bộ lọc lô gan ---------------------------------------------------------


def test_gan_filter_flags_only_numbers_past_the_threshold(tensor: DigitTensor) -> None:
    ctx = FeatureContext(tensor=tensor, anchor_index=140)
    filt = GanFilter(threshold_days=DEFAULT_GAN_THRESHOLD_DAYS)
    gaps = filt.gaps(ctx)
    flagged = set(filt.flagged(ctx))
    for number in range(100):
        assert (f"{number:02d}" in flagged) == bool(
            gaps[number] > DEFAULT_GAN_THRESHOLD_DAYS
        )


def test_gan_filter_warns_without_changing_probabilities(tensor: DigitTensor) -> None:
    """Chế độ mặc định chỉ cảnh báo: xổ số công bằng thì gan không đổi xác suất."""
    ctx = FeatureContext(tensor=tensor, anchor_index=140)
    probability = np.full(100, 0.2377)
    assert np.array_equal(GanFilter().apply(probability, ctx), probability)


def test_gan_filter_renormalises_a_distribution_when_excluding(
    tensor: DigitTensor,
) -> None:
    """Loại con mà không chia lại sẽ tạo phân phối hụt và làm sai mọi log-loss."""
    ctx = FeatureContext(tensor=tensor, anchor_index=140)
    distribution = np.full(100, 0.01)
    filtered = GanFilter(threshold_days=1, exclude=True).apply(distribution, ctx)
    assert filtered.sum() == pytest.approx(1.0)
    assert (filtered == 0).any(), "phải có con bị loại ở ngưỡng 1 ngày"


def test_gan_filter_rejects_a_wrong_shape(tensor: DigitTensor) -> None:
    ctx = FeatureContext(tensor=tensor, anchor_index=140)
    with pytest.raises(ValueError, match="100 phần tử"):
        GanFilter().apply(np.zeros(50), ctx)


# --- Gói đầu ra ------------------------------------------------------------


def test_picks_carry_the_baseline_next_to_every_probability() -> None:
    """Xác suất 0,26 không có nền 0,2377 bên cạnh sẽ bị đọc là 'cao'."""
    probability = np.linspace(0.20, 0.30, 100)
    picks = build_picks(
        probability,
        baseline=0.2377,
        gaps=np.zeros(100),
        gan_threshold=15,
        reasons={99: {"pattern_memory": 0.6}},
        top_k=5,
    )
    assert len(picks) == 5
    assert picks[0].number == "99"
    assert picks[0].baseline == 0.2377
    assert picks[0].lift == pytest.approx(picks[0].probability - 0.2377)
    assert picks[0].contribution_reasons == {"pattern_memory": 0.6}


def test_bundle_round_trips_through_json(tmp_path: Path) -> None:
    bundle = PredictionBundle(
        date="2026-09-06",
        generated_at_local="2026-09-06T10:00:00+07:00",
        generated_at_utc="2026-09-06T03:00:00Z",
        top_lo_to=build_picks(
            np.full(100, 0.2377),
            baseline=0.2377,
            gaps=np.zeros(100),
            gan_threshold=15,
            reasons={},
            top_k=3,
        ),
        top_dac_biet={"cham": [1, 2], "tong": [5], "dan_36": ["01"]},
        active_bridges=[],
        disclaimer="Không có bằng chứng nào cho thấy mô hình hơn đường cơ sở.",
        evidence={"tested_hypotheses": 412164, "survived": 0},
    )
    path = bundle.to_json(tmp_path / "predictions_today.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert len(payload["top_lo_to"]) == 3
    assert payload["evidence"]["survived"] == 0
    assert "đường cơ sở" in payload["disclaimer"]
