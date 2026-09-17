from __future__ import annotations

"""Vector loto phải có TỔNG đúng luật chơi, không chỉ từng phần tử trong [0,1].

27 giải rút từ 100 số hai chữ số, nên số con PHÂN BIỆT kỳ vọng là
``100 · (1 − (99/100)^27) = 23,7657``. Tổng xác suất biên của một mô hình loto
đúng phải bằng chính đại lượng ấy — ràng buộc CỨNG của luật chơi.

Cổng canh cũ chỉ đòi mỗi phần tử nằm trong ``[0, 1]`` và ``sum > 0``. Một vector
toàn ``1,0`` qua sạch: mỗi phần tử hợp lệ, tổng 100 > 0. Đó là đúng lỗi đã xảy
ra — 212 trong 231 ngày lịch sử loto ghi ``p_active``/``p_stable`` ở thang
"gần 1,0 cho mọi con" và được coi là hợp lệ suốt.

Hệ quả đo được: trang Chất lượng mô hình báo Brier 0,3133 cho loto, trong khi
trên 18 ngày dữ liệu sạch con số thật là 0,1802. Toàn bộ khoảng cách ấy là
hiện vật của dữ liệu hỏng, không phải tính chất của mô hình.
"""

import numpy as np
import pandas as pd
import pytest

from ensemble_components import (
    LOTO_EXPECTED_MARGINAL_SUM,
    LOTO_PRIZE_SLOTS,
    availability_from_history_day,
    loto_marginal_sum_is_plausible,
    probability_component,
)


def test_the_ceiling_comes_from_the_draw_mechanism() -> None:
    """Trần 27 và kỳ vọng 23,7657 phải SUY RA từ luật chơi, không chép tay."""
    assert LOTO_PRIZE_SLOTS == 27
    expected = 100.0 * (1.0 - (99.0 / 100.0) ** LOTO_PRIZE_SLOTS)
    assert LOTO_EXPECTED_MARGINAL_SUM == pytest.approx(expected)
    assert LOTO_EXPECTED_MARGINAL_SUM == pytest.approx(23.7657, abs=1e-3)


def _vector(value: float) -> pd.DataFrame:
    return pd.DataFrame({"number": range(100), "prob": np.full(100, value)})


@pytest.mark.parametrize(
    ("label", "value", "ok"),
    [
        ("toàn 1,0 — tổng 100, đúng lỗi đã xảy ra", 1.0, False),
        ("toàn 0,5 — tổng 50", 0.5, False),
        ("vừa quá trần — tổng 28", 0.28, False),
        ("sát trần — tổng 27", 0.27, True),
        ("đúng thang — tổng 23,8", 0.238, True),
        # Tổng THẤP là lựa chọn mô hình, không phải dữ liệu hỏng. Bản đầu của
        # cổng canh có ngưỡng dưới tự đặt và loại oan hai trường hợp này.
        ("thiếu tự tin — tổng 11,9", 0.119, True),
        ("rất thiếu tự tin — tổng 5", 0.05, True),
    ],
)
def test_the_live_path_rejects_an_implausible_total(
    label: str, value: float, ok: bool
) -> None:
    component = probability_component(_vector(value), mode="loto")
    assert component.available is ok, f"{label}: lý do={component.reason}"
    if not ok:
        assert component.reason == "loto_marginal_sum_implausible", label


def test_de_is_normalised_so_the_total_is_not_a_constraint() -> None:
    """Đặc Biệt là phân phối phân loại: mô hình được phép phát điểm chưa chuẩn hoá."""
    component = probability_component(_vector(1.0), mode="de")
    assert component.available is True
    assert float(component.prob.sum()) == pytest.approx(1.0)


def _history_day(active_value: float) -> pd.DataFrame:
    return pd.DataFrame({
        "number": range(100),
        "y": np.zeros(100),
        "p_ml": np.full(100, 0.238),
        "p_cau": np.full(100, 0.238),
        "p_stat": np.full(100, 0.238),
        "p_active": np.full(100, active_value),
        "p_stable": np.full(100, 0.238),
    })


def test_the_history_path_marks_a_wrongly_scaled_component_unavailable() -> None:
    bad = availability_from_history_day(_history_day(1.0), mode="loto")
    assert bad["active"] is False, "vector tổng 100 phải bị coi là không dùng được"
    assert bad["ml"] is True, "các thành phần đúng thang không được bị kéo theo"

    good = availability_from_history_day(_history_day(0.238), mode="loto")
    assert all(good.values()), good


def test_without_a_mode_the_history_guard_stays_permissive() -> None:
    """Không biết mode thì KHÔNG được đoán: cổng canh tổng chỉ áp cho loto.

    Đây là hành vi có chủ ý, nên nó phải được ghim: một bản sửa sau này áp
    ngưỡng loto cho cả Đặc Biệt sẽ loại sạch mọi ngày Đặc Biệt.
    """
    assert availability_from_history_day(_history_day(1.0))["active"] is True


def test_every_real_artifact_passes_and_the_broken_scale_does_not() -> None:
    """Mọi tệp thật đo được phải qua; thang hỏng phải bị loại."""
    for observed in (23.562, 23.805, 23.895, 24.283):
        assert loto_marginal_sum_is_plausible(observed), observed
    assert not loto_marginal_sum_is_plausible(100.0)
    assert LOTO_EXPECTED_MARGINAL_SUM < LOTO_PRIZE_SLOTS, (
        "kỳ vọng phải nằm dưới trần, nếu không cổng canh loại cả mô hình đúng"
    )


def test_a_low_total_is_a_modelling_choice_not_corrupt_data() -> None:
    """Ghim CHỦ Ý chỉ chặn phía trên.

    Bản đầu đặt ngưỡng dưới bằng một nửa kỳ vọng — con số tự đặt, không suy ra
    từ đâu. Nó loại oan vector tổng 10 trong
    ``test_ensemble_renormalizes_weights_over_available_components_only``, và
    chính phép kiểm ấy đã bắt được.
    """
    for total in (0.1, 1.0, 5.0, 10.0, 20.0):
        assert loto_marginal_sum_is_plausible(total), total
