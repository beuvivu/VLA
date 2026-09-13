"""AUC-ROC là chỉ số PHỤ — và phép kiểm này tồn tại để giữ nó ở đúng vai trò ấy.

AUC đo khả năng XẾP HẠNG. Nó bất biến với mọi phép biến đổi đơn điệu, nghĩa là
một mô hình hiệu chuẩn sai bét vẫn có thể đạt AUC hoàn hảo. Với bài toán mà
giá trị nằm ở độ ĐÚNG của xác suất, dùng AUC thay cho Brier là tự lừa mình.

Phép kiểm quan trọng nhất ở đây chứng minh đúng điều đó bằng số: hai bộ xác
suất có cùng AUC tuyệt đối mà Brier chênh nhau nhiều lần.
"""

from __future__ import annotations

import numpy as np
import pytest

from meta_predictor import MetaMetrics, _evaluate, _roc_auc


def test_auc_matches_the_reference_implementation_including_ties() -> None:
    """Tự tính thì phải khớp bản chuẩn, nếu không nó là một chỉ số khác."""
    sklearn_metrics = pytest.importorskip("sklearn.metrics")
    rng = np.random.default_rng(0)
    cases = [
        (rng.random(2000), (rng.random(2000) < 0.24).astype(float)),
        (np.array([0.1, 0.2, 0.8, 0.9]), np.array([0.0, 0.0, 1.0, 1.0])),
        (np.array([0.9, 0.8, 0.2, 0.1]), np.array([0.0, 0.0, 1.0, 1.0])),
        # Nhiều giá trị hoà: hoà phải nhận thứ hạng TRUNG BÌNH, nếu không AUC
        # phụ thuộc vào thứ tự sắp xếp và không còn xác định.
        (np.array([0.5] * 10 + [0.7] * 10),
         np.array([0.0] * 8 + [1.0] * 2 + [0.0] * 3 + [1.0] * 7)),
        (np.full(50, 0.3), (rng.random(50) < 0.5).astype(float)),
    ]
    for probs, labels in cases:
        assert _roc_auc(probs, labels) == pytest.approx(
            sklearn_metrics.roc_auc_score(labels, probs)
        )


def test_auc_is_blind_to_calibration_and_brier_is_not() -> None:
    """Đây là lý do AUC không được dùng thay Brier.

    Hai bộ xác suất dưới đây xếp hạng GIỐNG HỆT nhau nên AUC bằng nhau tuyệt
    đối. Nhưng một bộ nói thật về mức độ chắc chắn còn bộ kia nói dối trắng
    trợn, và Brier tách được chúng ra.
    """
    rng = np.random.default_rng(7)
    truth = np.clip(rng.beta(2.0, 6.0, size=4000), 0.01, 0.99)
    labels = (rng.random(4000) < truth).astype(float)

    honest = truth
    # Phép biến đổi ĐƠN ĐIỆU: giữ nguyên thứ tự, phá hoàn toàn mức độ.
    liar = np.clip(truth**0.15, 0.01, 0.999)

    assert _roc_auc(honest, labels) == pytest.approx(_roc_auc(liar, labels)), (
        "hai bộ cùng thứ tự phải cho cùng AUC"
    )
    brier_honest = float(np.mean((honest - labels) ** 2))
    brier_liar = float(np.mean((liar - labels) ** 2))
    assert brier_liar > brier_honest * 2.0, (
        f"Brier phải tách được hai bộ ấy: {brier_honest:.4f} so với {brier_liar:.4f}"
    )


def test_auc_is_undefined_rather_than_a_half_when_one_class_is_absent() -> None:
    """Trả 0.5 sẽ đọc thành "đoán mò"; sự thật là "không đo được"."""
    assert np.isnan(_roc_auc(np.array([0.3, 0.4]), np.array([1.0, 1.0])))
    assert np.isnan(_roc_auc(np.array([0.3, 0.4]), np.array([0.0, 0.0])))
    assert np.isnan(_roc_auc(np.array([]), np.array([])))


def test_metrics_default_auc_to_undefined_not_to_a_number() -> None:
    """Bản ghi chỉ số cũ không có AUC phải đọc ra NaN, không phải 0."""
    assert np.isnan(MetaMetrics(logloss=0.5, brier=0.2).auc_roc)


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_the_evaluator_reports_auc_alongside_the_proper_scores(mode: str) -> None:
    """AUC phải đi KÈM Brier và log-loss, không thay chúng."""
    rng = np.random.default_rng(3)
    days = 60
    probs = rng.dirichlet(np.full(100, 5.0), size=days) if mode == "de" \
        else np.clip(rng.random((days, 100)), 0.01, 0.99)
    labels = np.zeros((days, 100))
    if mode == "de":
        labels[np.arange(days), rng.integers(0, 100, size=days)] = 1.0
    else:
        labels = (rng.random((days, 100)) < 0.24).astype(float)

    metrics = _evaluate(mode, probs, labels)
    assert np.isfinite(metrics.brier)
    assert np.isfinite(metrics.logloss)
    assert np.isfinite(metrics.auc_roc)
    assert 0.0 <= metrics.auc_roc <= 1.0
