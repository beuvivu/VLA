from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pages import build_model_quality as page
from evaluation import model_quality as mq
from ensemble.ensemble_components import BLEND_POLICY, BLEND_POLICY_COLUMN
from ensemble.ensemble_utils import anchor_loto_level
from core.xsmb_domain import LOTO_BASELINE_RATE

ROOT = Path(__file__).resolve().parents[2]


def _history(rows: list[tuple[str, str, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"mode": m, "target_date": d, "logloss": ll, "brier": br} for m, d, ll, br in rows]
    )


def test_stale_brier_rows_are_rescaled_to_the_current_definition() -> None:
    stale, fresh = 0.009901, 0.990100
    frame = _history([("de", "2026-01-01", 4.60517, stale),
                      ("de", "2026-09-05", 4.60517, fresh)])
    out, converted = mq.normalize_brier_scale(frame)
    assert converted == 1
    assert out["brier"].iloc[0] == pytest.approx(stale * 100.0)
    assert out["brier"].iloc[1] == pytest.approx(fresh), "dòng đúng thang không được đụng tới"


def test_rescaling_never_touches_loto_rows() -> None:
    logloss, brier = 0.62, 0.19
    bound = (1.0 - np.exp(-logloss)) ** 2
    assert brier < bound, "ca kiểm phải thật sự thủng cận dưới mới có tác dụng"

    out, converted = mq.normalize_brier_scale(_history([("loto", "2026-01-01", logloss, brier)]))
    assert converted == 0
    assert out["brier"].iloc[0] == pytest.approx(brier)


def test_murphy_decomposition_adds_back_up_to_brier() -> None:
    rng = np.random.default_rng(5)
    p = np.clip(rng.normal(0.24, 0.02, size=(60, 100)), 0.01, 0.99)
    y = (rng.random((60, 100)) < p).astype(float)
    out = mq.murphy(p, y)
    assert out["brier_from_decomposition"] == pytest.approx(out["brier_binned"], abs=1e-12)
    assert out["binning_residual"] == pytest.approx(
        out["brier_direct"] - out["brier_binned"], abs=1e-12
    )

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


@pytest.mark.parametrize(
    ("probability", "positive_per_draw"), [(0.5, 20), (0.01, 1), (0.0, 20), (1.0, 20)]
)
def test_constant_predictions_keep_one_complete_calibration_bin(
    probability: float, positive_per_draw: int,
) -> None:
    p = np.full((10, 100), probability)
    y = np.zeros_like(p)
    y[:, :positive_per_draw] = 1.0

    rows = mq.calibration(p, y)

    assert len(rows) == 1
    row = rows[0]
    assert row["count"] == p.size
    assert row["predicted"] == pytest.approx(probability)
    assert row["observed"] == pytest.approx(positive_per_draw / 100)
    assert 0 <= row["ci_low"] <= row["observed"] <= row["ci_high"] <= 1


@pytest.mark.parametrize(
    ("probability", "positive_per_draw"), [(0.5, 20), (0.01, 1), (0.0, 20), (1.0, 20)]
)
def test_constant_murphy_matches_exact_brier_without_binning_residual(
    probability: float, positive_per_draw: int,
) -> None:
    p = np.full((10, 100), probability)
    y = np.zeros_like(p)
    y[:, :positive_per_draw] = 1.0

    out = mq.murphy(p, y)

    prevalence = positive_per_draw / 100
    expected_brier = prevalence * (1 - probability) ** 2 + (1 - prevalence) * probability**2
    assert out["reliability"] == pytest.approx((probability - prevalence) ** 2, abs=1e-12)
    assert out["resolution"] == pytest.approx(0, abs=1e-12)
    assert out["uncertainty"] == pytest.approx(prevalence * (1 - prevalence), abs=1e-12)
    assert out["brier_binned"] == pytest.approx(expected_brier, abs=1e-12)
    assert out["brier_from_decomposition"] == pytest.approx(expected_brier, abs=1e-12)
    assert out["brier_direct"] == pytest.approx(expected_brier, abs=1e-12)
    assert out["binning_residual"] == pytest.approx(0, abs=1e-12)


def test_calibration_bins_carry_wilson_intervals_that_stay_in_range() -> None:
    rng = np.random.default_rng(3)
    p = np.clip(rng.normal(0.01, 0.002, size=(120, 100)), 1e-4, 0.5)
    y = (rng.random((120, 100)) < p).astype(float)
    rows = mq.calibration(p, y)
    assert rows
    for row in rows:
        assert 0.0 <= row["ci_low"] <= row["observed"] <= row["ci_high"] <= 1.0, row
        assert row["count"] > 0

    low, high = mq._wilson(0, 40)
    assert low == pytest.approx(0.0)
    assert high > 0.05, high


def test_ensemble_renormalizes_weights_over_available_components_only() -> None:
    rows = []
    for number in range(100):
        rows.append(
            {"target_date": "2026-01-01", "number": number, "p_ml": 0.25,
             "p_cau": np.nan, "p_stat": np.nan,
             "p_active": 0.30 if number == 1 else 0.10, "p_stable": 0.10, "y": 0.0,
             BLEND_POLICY_COLUMN: BLEND_POLICY}
        )
    weights = mq.EnsembleWeights(w_ml=0.5, w_cau=0.3, w_stat=0.1, w_active=0.05, w_stable=0.05)
    _, probabilities, _ = mq.ensemble_probabilities(pd.DataFrame(rows), weights, "loto")
    expected = np.full(100, 0.5 / 0.6 * 0.25 + 0.1 / 0.6 * 0.10)
    expected[1] += 0.05 / 0.6 * 0.20
    np.testing.assert_allclose(probabilities[0], anchor_loto_level(expected), rtol=1e-12)
    assert probabilities[0].sum() == pytest.approx(100 * LOTO_BASELINE_RATE)

    legacy = pd.DataFrame(rows).drop(columns=[BLEND_POLICY_COLUMN])
    _, probabilities, _ = mq.ensemble_probabilities(legacy, weights, "loto")
    np.testing.assert_allclose(probabilities[0], expected, rtol=1e-12)


def test_skill_chart_pins_off_scale_points_instead_of_dropping_them() -> None:
    points = [{"date": f"2026-01-{d:02d}", "skill": 0.001, "cumulative": 0.001}
              for d in range(1, 21)]
    points[3]["skill"] = -0.96
    points[7]["skill"] = 0.85
    svg = page.skill_chart({"points": points, "stderr": 0.0005}, "thử")
    assert "2 kỳ nằm ngoài thang" in svg, svg[-400:]
    assert svg.count("var(--ui-bad)") == 2, "mỗi điểm ngoài thang một mốc"
    assert "-0,960%" in svg or "−0,960%" in svg or "-96,000%" in svg, "vẫn phải tra được giá trị thật"


def test_skill_chart_does_not_describe_marks_it_did_not_draw() -> None:
    points = [{"date": f"2026-01-{d:02d}", "skill": 0.001, "cumulative": -0.5}
              for d in range(1, 21)]
    svg = page.skill_chart({"points": points, "stderr": 0.0002}, "thử")
    assert "nằm trọn ngoài thang nên không vẽ được" in svg
    assert "Đường liền là trung bình tích luỹ" not in svg


def test_charts_stay_inside_their_viewbox() -> None:
    rows = [{"bin": i, "count": 100 + i, "predicted": 0.23 + i * 0.001,
             "observed": 0.23 + i * 0.001, "ci_low": 0.21, "ci_high": 0.26} for i in range(8)]
    svg = page.calibration_chart(rows, 0.2377, "thử")
    coords = [float(v) for v in re.findall(r'c[xy]="([-\d.]+)"', svg)]
    assert coords, svg[:200]
    assert min(coords) >= 0.0 and max(coords) <= max(page.PLOT_W, page.PLOT_H), (
        min(coords), max(coords)
    )


def test_the_published_page_explains_why_not_only_how_much() -> None:
    html = (ROOT / "docs" / "model-quality.html").read_text(encoding="utf-8")
    for needle in ("Độ tin cậy", "Độ phân giải", "Độ bất định", "Vì sao kỹ năng"):
        assert needle in html, needle
    assert "kỳ đã công bố, chấm với kết quả quay thật" in html, "trang phải nói rõ nguồn của con số"
    assert "<svg" in html, "trang phải có hình, không chỉ bảng"


def test_the_page_detects_a_report_older_than_the_data(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "evaluation" / "prob_eval").mkdir(parents=True)
    pd.DataFrame({"target_date": ["2026-09-10", "2026-09-15"]}).to_csv(
        data_dir / "evaluation" / "prob_eval" / "ensemble_history.csv", index=False
    )
    assert page._staleness(data_dir, {"covers_through": "2026-09-15"}) == ""
    stale = page._staleness(data_dir, {"covers_through": "2026-09-01"})
    assert "2026-09-01" in stale and "2026-09-15" in stale, stale
    assert "chẩn đoán nhiều khả năng đã hỏng" in stale
    assert "không ghi ngày chấm cuối cùng" in page._staleness(data_dir, {})


def test_the_page_renders_a_dash_instead_of_crashing_on_a_truncated_report() -> None:
    assert page._num(None) == "—"
    assert page._num(float("nan")) == "—"
    assert page._num("không phải số") == "—"
    assert page._num(0.5, 3) == "0,500"
