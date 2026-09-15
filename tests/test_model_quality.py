"""Chẩn đoán chất lượng mô hình: phép đo phải đúng, và trang phải nói đúng.

Trang này tồn tại để người đọc biết mô hình tốt ở đâu và kém ở đâu. Một trang
chẩn đoán nói sai còn tệ hơn không có trang nào, nên tệp này khoá cả hai phía:
con số tính đúng, và hình vẽ mô tả đúng con số ấy.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import build_model_quality as page
import model_quality as mq

ROOT = Path(__file__).resolve().parents[1]


def _history(rows: list[tuple[str, str, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"mode": m, "target_date": d, "logloss": ll, "brier": br} for m, d, ll, br in rows]
    )


def test_stale_brier_rows_are_rescaled_to_the_current_definition() -> None:
    """``categorical_brier`` đổi từ trung bình sang tổng, nhưng lịch sử đã lưu
    thì chưa ai chuyển đổi.

    Hậu quả đã xuất bản: cột Brier của Đặc Biệt có 217 dòng quanh 0,0099 rồi
    đột ngột 12 dòng quanh 0,9901, và người đọc thấy một bước nhảy 100 lần
    trông như mô hình hỏng. Phép đổi là chính xác chứ không xấp xỉ: quy ước cũ
    bằng tổng chia 100.
    """
    stale, fresh = 0.009901, 0.990100
    frame = _history([("de", "2026-01-01", 4.60517, stale),
                      ("de", "2026-09-05", 4.60517, fresh)])
    out, converted = mq.normalize_brier_scale(frame)
    assert converted == 1
    assert out["brier"].iloc[0] == pytest.approx(stale * 100.0)
    assert out["brier"].iloc[1] == pytest.approx(fresh), "dòng đúng thang không được đụng tới"


def test_rescaling_never_touches_loto_rows() -> None:
    """LOTO dùng ``bernoulli_brier`` vốn ĐÚNG là trung bình trên 100 biên.

    Ca kiểm phải là dòng LOTO THẬT SỰ thủng cận dưới của phân phối phân loại,
    nếu không nó chẳng chạm tới bộ phát hiện và phép kiểm xanh dù bỏ hẳn điều
    kiện ``mode == "de"``. Với LogLoss 0,62 cận dưới ấy là 0,2116 trong khi
    Brier LOTO bình thường quanh 0,19 — thấp hơn, nên dòng này sẽ bị nhân 100
    nếu điều kiện chế độ biến mất.
    """
    logloss, brier = 0.62, 0.19
    bound = (1.0 - np.exp(-logloss)) ** 2
    assert brier < bound, "ca kiểm phải thật sự thủng cận dưới mới có tác dụng"

    out, converted = mq.normalize_brier_scale(_history([("loto", "2026-01-01", logloss, brier)]))
    assert converted == 0
    assert out["brier"].iloc[0] == pytest.approx(brier)


def test_murphy_decomposition_adds_back_up_to_brier() -> None:
    """``tin cậy − phân giải + bất định`` phải khớp Brier đo trực tiếp.

    Nếu phân rã dùng cách chia nhóm khác với biểu đồ hiệu chỉnh thì đẳng thức
    gãy, và hai phần của trang nói về hai thứ khác nhau trong khi trông như
    một.
    """
    rng = np.random.default_rng(5)
    p = np.clip(rng.normal(0.24, 0.02, size=(60, 100)), 0.01, 0.99)
    y = (rng.random((60, 100)) < p).astype(float)
    out = mq.murphy(p, y)
    # Đẳng thức đúng chính xác cho dự báo ĐÃ GỘP NHÓM; phần lệch so với dự báo
    # thô là phần dư do chia nhóm và phải được kê riêng chứ không nuốt đi.
    assert out["brier_from_decomposition"] == pytest.approx(out["brier_binned"], abs=1e-12)
    assert out["binning_residual"] == pytest.approx(
        out["brier_direct"] - out["brier_binned"], abs=1e-12
    )

    # Và phải dùng ĐÚNG cách chia nhóm của biểu đồ hiệu chỉnh. Dùng cách chia
    # khác thì đẳng thức trên VẪN đúng — nó tự nhất quán bên trong — nhưng
    # bảng và hình trên trang lại nói về hai phép chia khác nhau.
    rows = mq.calibration(p, y)
    total = p.size
    mean_y = float(y.mean())
    assert out["reliability"] == pytest.approx(
        sum(r["count"] * (r["predicted"] - r["observed"]) ** 2 for r in rows) / total, abs=1e-12
    )
    assert out["resolution"] == pytest.approx(
        sum(r["count"] * (r["observed"] - mean_y) ** 2 for r in rows) / total, abs=1e-12
    )


def test_murphy_separates_a_miscalibrated_model_from_a_blind_one() -> None:
    """Hai mô hình cùng kỹ năng ~0 vì hai lý do trái ngược, và phải phân biệt được.

    Đây là toàn bộ lý do trang tồn tại. Mô hình lệch hiệu chỉnh sửa được bằng
    hiệu chỉnh; mô hình không phân biệt được gì thì hiệu chỉnh không cứu nổi.
    """
    rng = np.random.default_rng(9)
    truth = rng.random((80, 100)) * 0.3 + 0.1
    y = (rng.random((80, 100)) < truth).astype(float)

    sharp_but_biased = np.clip(truth + 0.18, 0.01, 0.99)
    blind = np.full_like(truth, float(y.mean()))

    biased = mq.murphy(sharp_but_biased, y)
    dull = mq.murphy(blind, y)
    assert biased["reliability"] > 10 * dull["reliability"], (biased, dull)
    assert biased["resolution"] > 10 * dull["resolution"], (biased, dull)
    assert dull["resolution"] == pytest.approx(0.0, abs=1e-12)


def test_calibration_bins_carry_wilson_intervals_that_stay_in_range() -> None:
    """Ở chế độ Đặc Biệt tỉ lệ thực quanh 0,01; khoảng chuẩn tràn xuống dưới 0."""
    rng = np.random.default_rng(3)
    p = np.clip(rng.normal(0.01, 0.002, size=(120, 100)), 1e-4, 0.5)
    y = (rng.random((120, 100)) < p).astype(float)
    rows = mq.calibration(p, y)
    assert rows
    for row in rows:
        assert 0.0 <= row["ci_low"] <= row["observed"] <= row["ci_high"] <= 1.0, row
        assert row["count"] > 0

    # Chỗ hai công thức khác nhau rõ rệt: nhóm không có lần trúng nào. Khoảng
    # chuẩn co về đúng một điểm [0, 0] — khẳng định rằng tỉ lệ thật CHẮC CHẮN
    # bằng 0 sau 40 lần thử — còn Wilson vẫn cho một cận trên dương. Không có
    # ca kiểm này thì đổi Wilson thành khoảng chuẩn vẫn xanh.
    low, high = mq._wilson(0, 40)
    assert low == pytest.approx(0.0)
    assert high > 0.05, high


def test_ensemble_renormalizes_weights_over_available_components_only() -> None:
    """92% số ngày trong lịch sử này thiếu thành phần cầu và thống kê.

    Không chuẩn hoá lại thì những ngày ấy hụt tổng trọng số và xác suất tụt
    xuống thấp một cách giả tạo — một lỗi làm hỏng mọi biểu đồ hiệu chỉnh phía
    sau mà không để lại dấu vết nào.
    """
    rows = []
    for number in range(100):
        rows.append(
            {"target_date": "2026-01-01", "number": number, "p_ml": 0.30,
             "p_cau": np.nan, "p_stat": np.nan, "p_active": 0.10, "p_stable": 0.10, "y": 0.0}
        )
    weights = mq.EnsembleWeights(w_ml=0.5, w_cau=0.3, w_stat=0.1, w_active=0.05, w_stable=0.05)
    _, probabilities, _ = mq.ensemble_probabilities(pd.DataFrame(rows), weights, "loto")
    # ml 0,5 và active/stable 0,05 còn lại -> 0,5/0,6·0,30 + 0,1/0,6·0,10
    assert probabilities[0][0] == pytest.approx(0.5 / 0.6 * 0.30 + 0.1 / 0.6 * 0.10)


def test_skill_chart_pins_off_scale_points_instead_of_dropping_them() -> None:
    """Cắt thang mà im lặng là giấu dữ liệu.

    Lịch sử có 25/229 kỳ hỏng nặng, một kỳ xuống −96%. Để chúng định thang thì
    227 kỳ còn lại dồn thành một vạch; bỏ chúng đi thì trang nói dối. Nên
    chúng phải hiện thành mốc ghim ở mép, và chú thích phải đếm đúng số ấy.
    """
    points = [{"date": f"2026-01-{d:02d}", "skill": 0.001, "cumulative": 0.001}
              for d in range(1, 21)]
    points[3]["skill"] = -0.96
    points[7]["skill"] = 0.85
    svg = page.skill_chart({"points": points, "stderr": 0.0005}, "thử")
    assert "2 kỳ nằm ngoài thang" in svg, svg[-400:]
    assert svg.count("var(--ui-bad)") == 2, "mỗi điểm ngoài thang một mốc"
    assert "-0,960%" in svg or "−0,960%" in svg or "-96,000%" in svg, "vẫn phải tra được giá trị thật"


def test_skill_chart_does_not_describe_marks_it_did_not_draw() -> None:
    """Chú thích nói "đường đậm là trung bình tích luỹ" trong khi đường ấy nằm
    ngoài thang là gửi người đọc đi tìm thứ không tồn tại."""
    points = [{"date": f"2026-01-{d:02d}", "skill": 0.001, "cumulative": -0.5}
              for d in range(1, 21)]
    svg = page.skill_chart({"points": points, "stderr": 0.0002}, "thử")
    assert "nằm trọn ngoài thang nên không vẽ được" in svg
    assert "Đường liền là trung bình tích luỹ" not in svg


def test_charts_stay_inside_their_viewbox() -> None:
    """Toạ độ tràn khung thì nét bị xén mà không có cảnh báo nào."""
    rows = [{"bin": i, "count": 100 + i, "predicted": 0.23 + i * 0.001,
             "observed": 0.23 + i * 0.001, "ci_low": 0.21, "ci_high": 0.26} for i in range(8)]
    svg = page.calibration_chart(rows, 0.2377, "thử")
    coords = [float(v) for v in re.findall(r'c[xy]="([-\d.]+)"', svg)]
    assert coords, svg[:200]
    assert min(coords) >= 0.0 and max(coords) <= max(page.PLOT_W, page.PLOT_H), (
        min(coords), max(coords)
    )


def test_the_published_page_explains_why_not_only_how_much() -> None:
    """Trang cũ chỉ có LogLoss và Brier — trả lời "hơn kém bao nhiêu" mà không
    trả lời "vì sao", trong khi "vì sao" mới quyết định phải sửa cái gì."""
    html = (ROOT / "docs" / "model-quality.html").read_text(encoding="utf-8")
    for needle in ("Độ tin cậy", "Độ phân giải", "Độ bất định", "Vì sao kỹ năng"):
        assert needle in html, needle
    assert "artifact đã phát hành" in html, "trang phải nói rõ nguồn của con số"
    assert "<svg" in html, "trang phải có hình, không chỉ bảng"
