"""Ba khối thêm vào báo cáo Chất lượng mô hình (16-11-2026): ECE có mốc đúng, thứ hạng toàn vector, kỹ năng theo tháng.

Mỗi khối phải im khi vector đã công bố không có gì, và lên tiếng khi có — kể cả khi lên tiếng theo hướng
"tốt hơn", vì với một kỳ quay đã kiểm là ngẫu nhiên thì đó cũng là tin phải kiểm lại.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.xsmb_domain import LOTO_BASELINE_RATE
from evaluation import model_quality as mq
from pages import build_model_quality as page

ROOT = Path(__file__).resolve().parents[2]


def _fair_loto(draws: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Vector phẳng ở mức nền và kết cục của kỳ quay công bằng 27 giải."""
    rng = np.random.default_rng(seed)
    p = np.full((draws, 100), LOTO_BASELINE_RATE)
    y = np.zeros((draws, 100))
    picks = rng.integers(0, 100, size=(draws, 27))
    y[np.arange(draws)[:, None], picks] = 1.0
    return p, y


def test_simulated_outcomes_follow_the_forecast_and_keep_the_draw_structure() -> None:
    rng = np.random.default_rng(1)
    p = np.full((4000, 100), LOTO_BASELINE_RATE)
    p[:, :10] = 0.40
    p *= 100 * LOTO_BASELINE_RATE / p.sum(axis=1, keepdims=True)
    y = mq.simulate_calibrated_outcomes(p, "loto", rng)
    assert set(np.unique(y)) <= {0.0, 1.0}
    assert y.sum(axis=1).max() <= 27  # 27 giải mỗi kỳ, con trùng chỉ tính một lần
    assert y[:, :10].mean() == pytest.approx(p[0, 0], abs=0.01)
    assert y[:, 10:].mean() == pytest.approx(p[0, 10], abs=0.005)
    special = np.full((3000, 100), 0.005)
    special[:, 7] = 0.505
    one_hot = mq.simulate_calibrated_outcomes(special, "de", rng)
    assert (one_hot.sum(axis=1) == 1).all() and one_hot[:, 7].mean() == pytest.approx(0.505, abs=0.03)


def test_ece_of_a_calibrated_forecast_sits_inside_its_own_null() -> None:
    p, y = _fair_loto(300, seed=2)
    out = mq.calibration_summary(p, y, "loto", simulations=200, seed=3)
    assert out["ece"] > 0  # ECE dương kể cả khi hiệu chỉnh hoàn hảo
    assert out["p_value"] > 0.05 and out["ece"] <= out["ece_upper95"] + 1e-12
    assert out["simulations"] == 200 and out["ece_expected"] > 0


def test_ece_of_a_miscalibrated_forecast_is_flagged() -> None:
    p, y = _fair_loto(300, seed=4)
    sharp = np.where(np.arange(100) < 50, 0.33, 0.14)[None].repeat(300, axis=0)  # nói 33% mà chỉ 23,8% về
    out = mq.calibration_summary(sharp, y, "loto", simulations=200, seed=5)
    assert out["p_value"] < 0.01 and out["ece"] > out["ece_upper95"]
    flagged = page.calibration_reading(out)
    assert "lớn hơn mức mà dao động mẫu giải thích được" in flagged and "chưa có" not in flagged
    calm = page.calibration_reading(mq.calibration_summary(p, y, "loto", simulations=200, seed=5))
    assert calm.startswith("ECE nằm trong dải") and "chưa có bằng chứng lệch hiệu chỉnh" in calm


def test_a_sharp_but_calibrated_forecast_is_not_flagged() -> None:
    """Mốc của ECE là chính các xác suất ấy khi kết cục rút đúng theo chúng — không phải dự báo hằng số.

    Dự báo hằng số dồn mọi ô vào một nhóm nên ECE của nó nhỏ hơn hẳn; so với nó thì mọi vector
    phân tán, dù hiệu chỉnh hoàn hảo, đều bị gắn cờ oan.
    """
    rng = np.random.default_rng(9)
    # Phân tán liên tục nên đủ mười nhóm phân vị, mỗi nhóm ~1 000 ô: nhiễu của từng nhóm lớn hơn hẳn
    # nhiễu của một nhóm duy nhất mà dự báo hằng số tạo ra.
    p = rng.uniform(0.10, 0.38, size=(100, 100))
    p *= 100 * LOTO_BASELINE_RATE / p.sum(axis=1, keepdims=True)
    y = mq.simulate_calibrated_outcomes(p, "loto", rng)
    out = mq.calibration_summary(p, y, "loto", simulations=200, seed=10)
    assert out["bins"] == 10 and out["p_value"] > 0.05 and out["ece"] <= out["ece_upper95"]
    constant = np.full_like(p, LOTO_BASELINE_RATE)
    constant_null = np.mean([mq.calibration_error(mq.calibration(constant, mq.simulate_calibrated_outcomes(
        p, "loto", np.random.default_rng(seed))))["ece"] for seed in range(50)])
    assert out["ece_expected"] > 2 * constant_null  # đúng lý do không được dùng hằng số làm mốc


def test_a_flat_vector_ranks_exactly_at_chance_in_both_modes() -> None:
    p, y = _fair_loto(80, seed=6)
    loto = mq.ranking(p, y, "loto")
    assert loto["metric"] == "auc" and loto["value"] == pytest.approx(0.5) and loto["chance"] == 0.5
    assert loto["p_value"] > 0.5
    rng = np.random.default_rng(7)
    special = np.zeros((80, 100))
    special[np.arange(80), rng.integers(0, 100, 80)] = 1.0
    de = mq.ranking(np.full((80, 100), 0.01), special, "de")
    assert de["metric"] == "mrr" and de["value"] == pytest.approx(de["chance"])
    assert de["mean_rank"] == pytest.approx(50.5) and de["chance_rank"] == 50.5
    assert "không phân biệt được với xếp ngẫu nhiên" in page.ranking_reading(loto)


def test_a_ranking_that_carries_information_is_reported_in_its_direction() -> None:
    rng = np.random.default_rng(8)
    score = rng.random((80, 100))
    y = (rng.random((80, 100)) < 0.1 + 0.3 * score).astype(float)
    good = mq.ranking(score, y, "loto")
    assert good["value"] > 0.6 and good["p_value"] < 0.01 and good["ci_low"] > 0.5
    assert "TỐT hơn" in page.ranking_reading(good) and "kiểm lại" in page.ranking_reading(good)
    bad = mq.ranking(-score, y, "loto")
    assert bad["value"] < 0.4 and "KÉM hơn" in page.ranking_reading(bad)


def test_build_writes_the_new_blocks_from_the_published_series(tmp_path: Path) -> None:
    """Chạy ``model_quality.build`` thật trên bản sao dữ liệu: khối theo tháng là ĐÚNG chuỗi đã chấm."""
    import shutil

    from evaluation.skill_monitor import graded_series
    from evaluation.forecast_metrics import by_period

    data = tmp_path / "data"
    for relative in ("xsmb-2-digits.csv", "forecast/predict", "evaluation/prob_eval",
                     "evaluation/model_quality/published_skill.csv", "evaluation/history", "ensemble"):
        source, target = ROOT / "data" / relative, data / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if source.is_dir() else shutil.copyfile)(source, target)
    report = json.loads(mq.build(data).read_text(encoding="utf-8"))
    for mode, block in report["modes"].items():
        assert block["source"] == "published"
        assert block["by_month"] == by_period(*graded_series(data, mode))
        assert {"ece", "ece_expected", "ece_upper95", "p_value"} <= set(block["calibration_error"])
        assert block["ranking"]["metric"] == ("mrr" if mode == "de" else "auc")


def test_the_page_builder_emits_the_new_cards(tmp_path: Path) -> None:
    """Dựng trang thật vào thư mục tạm: ba thẻ mới và mục lục trỏ tới sổ đăng ký."""
    html = page.build(ROOT / "data", tmp_path).read_text(encoding="utf-8")
    report = json.loads((ROOT / "data" / "evaluation" / "model_quality" / "report.json").read_text("utf-8"))
    for mode in report["modes"]:
        assert f'id="app-lab-{mode}-ranking"' in html and f'id="app-lab-{mode}-monthly"' in html
    assert 'id="app-lab-registry"' in html and 'href="#app-lab-registry"' in html
    registry = json.loads((ROOT / "data" / "evaluation" / "model_registry" / "registry.json").read_text("utf-8"))
    assert all(entry["deployment_reason"] in html for entry in registry["models"])


def test_the_committed_report_carries_the_three_new_blocks_for_each_mode() -> None:
    report = json.loads((ROOT / "data" / "evaluation" / "model_quality" / "report.json").read_text("utf-8"))
    assert report["schema_version"] == mq.SCHEMA_VERSION == 2
    for mode, block in report["modes"].items():
        error, rank = block["calibration_error"], block["ranking"]
        assert 0 <= error["ece"] <= error["mce"] and 0 < error["p_value"] <= 1
        assert rank["metric"] == ("mrr" if mode == "de" else "auc") and rank["ci_low"] <= rank["value"] <= rank["ci_high"]
        if block["source"] == "published":
            months = [row["period"] for row in block["by_month"]]
            assert months == sorted(months) and sum(row["draws"] for row in block["by_month"]) == block["skill"]["days"]


def test_the_monthly_table_reads_each_month_from_its_own_interval() -> None:
    rows = [
        {"period": "2026-09", "draws": 30, "mean": 0.002, "stderr": 0.0005},  # khác 0
        {"period": "2026-10", "draws": 31, "mean": 0.0001, "stderr": 0.0004},  # trong vùng 0
        {"period": "2026-11", "draws": 1, "mean": -0.001, "stderr": float("nan")},  # một kỳ
    ]
    html = page.monthly_table(rows)
    assert html.index("09/2026") < html.index("10/2026") < html.index("11/2026")
    assert html.count("khác 0") == 2  # một ô và một lần trong câu chú thích
    assert "trong vùng 0" in html and "chỉ một kỳ" in html
    assert page.monthly_table([]) == '<p class="ui-table-empty">Chưa có kỳ đã công bố để gom theo tháng.</p>'


def test_the_registry_table_shows_every_entry_with_its_reason() -> None:
    registry = json.loads((ROOT / "data" / "evaluation" / "model_registry" / "registry.json").read_text("utf-8"))
    html = page.registry_table(registry)
    for entry in registry["models"]:
        assert entry["deployment_reason"] in html
    assert html.count("<tr>") == len(registry["models"]) + 1
    assert f"{len(registry['models'])} mắt xích" in html
    assert page._vn_day("2026-11-16") == "16/11/2026" and page._vn_day(None) == "—"
    assert page.registry_table({}) == '<p class="ui-table-empty">Chưa có sổ đăng ký mô hình.</p>'


def test_the_published_page_prints_the_new_cards_from_the_committed_report() -> None:
    html = (ROOT / "docs" / "model-quality.html").read_text(encoding="utf-8")
    report = json.loads((ROOT / "data" / "evaluation" / "model_quality" / "report.json").read_text("utf-8"))
    for mode, block in report["modes"].items():
        assert f'id="app-lab-{mode}-ranking"' in html and f'id="app-lab-{mode}-monthly"' in html
        assert page.calibration_reading(block["calibration_error"]) in html
        assert page.ranking_reading(block["ranking"]) in html
    assert 'id="app-lab-registry"' in html and 'href="#app-lab-registry"' in html
