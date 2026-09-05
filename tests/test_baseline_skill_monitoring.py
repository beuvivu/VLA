"""Kiểm thử ba lớp đối chứng đường cơ sở cho mô hình sản xuất.

Bối cảnh: trong 12/2025–01/2026 mô hình lô tô cho logloss ~0,95 so với đường cơ
sở ~0,55 suốt 22 ngày, và không ai phát hiện trong tám tháng vì lịch sử đánh
giá không mang đối chứng nào. Ba lớp dưới đây bịt đúng lỗ hổng đó:

1. ``prob_eval_history`` ghi kèm baseline và điểm kỹ năng cho từng ngày.
2. Trang Chất lượng mô hình hiển thị điểm kỹ năng.
3. ``check_baseline_skill`` chặn khi mô hình tệ hơn baseline quá ngưỡng.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from bs4 import BeautifulSoup

from check_baseline_skill import (
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW,
    evaluate_history,
)
from ensemble_utils import skill_score
from prob_eval_history import evaluate_latest_emitted
from xsmb_domain import baseline_rate

ROOT = Path(__file__).resolve().parents[1]


# --- skill_score -----------------------------------------------------------


def test_skill_score_sign_convention() -> None:
    """Dương = tốt hơn baseline. Sai dấu ở đây là đọc ngược toàn bộ báo cáo."""
    assert skill_score(0.5, 1.0) == pytest.approx(0.5)
    assert skill_score(1.5, 1.0) == pytest.approx(-0.5)
    assert skill_score(1.0, 1.0) == pytest.approx(0.0)


def test_skill_score_is_safe_on_degenerate_input() -> None:
    assert skill_score(0.5, 0.0) == 0.0
    assert skill_score(0.5, -1.0) == 0.0
    assert skill_score(float("nan"), 1.0) == 0.0
    assert skill_score(0.5, float("inf")) == 0.0


# --- Lớp 1: lịch sử đánh giá mang baseline ---------------------------------


def _write_history(tmp: Path, mode: str, probability: float) -> tuple[Path, Path]:
    """Dựng lịch sử nhãn + artifact dự đoán tối thiểu cho một ngày."""
    day = "2026-03-01"
    numbers = list(range(100))
    y = [0] * 100
    if mode == "de":
        y[7] = 1
    else:
        for n in range(20):
            y[n] = 1

    history_dir = tmp / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history = history_dir / f"pred_{mode}.csv"
    pd.DataFrame({"target_date": day, "number": numbers, "y": y}).to_csv(
        history, index=False
    )

    predict_dir = tmp / "predict"
    predict_dir.mkdir(parents=True, exist_ok=True)
    probabilities = np.full(100, probability, dtype=float)
    if mode == "de":
        probabilities = probabilities / probabilities.sum()
    pd.DataFrame(
        {
            "number": numbers,
            "prob": probabilities,
            "target_date": day,
            "predict_for_date": day,
        }
    ).to_csv(predict_dir / f"predict_next_{mode}_all_{day}.csv", index=False)
    return history, predict_dir


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_history_row_carries_baseline_and_skill(tmp_path: Path, mode: str) -> None:
    history, predict_dir = _write_history(tmp_path, mode, baseline_rate(mode))
    row = evaluate_latest_emitted(
        mode=mode, history_path=history, predict_dir=predict_dir
    )
    assert row is not None, "không chấm được ngày đã có đủ nhãn"
    for key in ("baseline_logloss", "baseline_brier", "logloss_skill", "brier_skill"):
        assert key in row, key
    assert np.isfinite(row["baseline_logloss"])
    # Dự đoán trùng đúng baseline thì điểm kỹ năng phải bằng 0.
    assert row["logloss_skill"] == pytest.approx(0.0, abs=1e-9)


def test_baseline_is_scored_with_the_same_metric_as_the_model(
    tmp_path: Path,
) -> None:
    """Nếu hai bên dùng thước khác nhau thì điểm kỹ năng vô nghĩa."""
    history, predict_dir = _write_history(tmp_path, "loto", baseline_rate("loto"))
    row = evaluate_latest_emitted(
        mode="loto", history_path=history, predict_dir=predict_dir
    )
    assert row is not None
    assert row["logloss"] == pytest.approx(row["baseline_logloss"])
    assert row["brier"] == pytest.approx(row["baseline_brier"])


# --- Lớp 3: cổng báo động --------------------------------------------------


def _history_frame(mode: str, model: float, baseline: float, days: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "mode": [mode] * days,
            "target_date": [f"2026-03-{d + 1:02d}" for d in range(days)],
            "logloss": [model] * days,
            "baseline_logloss": [baseline] * days,
        }
    )


def test_gate_passes_when_the_model_tracks_the_baseline() -> None:
    """Vận hành bình thường đo được là −0,82%; cổng không được báo giả."""
    frame = _history_frame("loto", 0.5480, 0.5435, DEFAULT_WINDOW)
    checks = evaluate_history(frame)
    assert len(checks) == 1
    assert not checks[0].failed
    assert checks[0].skill == pytest.approx(-0.00828, abs=1e-4)


def test_gate_catches_the_december_january_regression() -> None:
    """Đợt hỏng thật: logloss ~0,95 so với baseline ~0,55 (kỹ năng ~ −73%)."""
    frame = _history_frame("loto", 0.9487, 0.5495, DEFAULT_WINDOW)
    checks = evaluate_history(frame)
    assert checks[0].failed
    assert checks[0].skill < DEFAULT_THRESHOLD


def test_gate_reads_only_the_recent_window() -> None:
    """Sự cố cũ đã khắc phục không được tiếp tục làm đỏ cổng."""
    bad = _history_frame("loto", 0.95, 0.55, 30)
    good = _history_frame("loto", 0.548, 0.5435, DEFAULT_WINDOW)
    good["target_date"] = [f"2026-04-{d + 1:02d}" for d in range(DEFAULT_WINDOW)]
    frame = pd.concat([bad, good], ignore_index=True)
    checks = evaluate_history(frame, window=DEFAULT_WINDOW)
    assert not checks[0].failed


def test_gate_requires_the_baseline_columns() -> None:
    frame = pd.DataFrame(
        {"mode": ["loto"], "target_date": ["2026-03-01"], "logloss": [0.5]}
    )
    with pytest.raises(ValueError, match="baseline"):
        evaluate_history(frame)


def test_gate_checks_each_mode_independently() -> None:
    frame = pd.concat(
        [
            _history_frame("loto", 0.95, 0.55, DEFAULT_WINDOW),
            _history_frame("de", 4.60, 4.605, DEFAULT_WINDOW),
        ],
        ignore_index=True,
    )
    checks = {c.mode: c for c in evaluate_history(frame)}
    assert checks["loto"].failed
    assert not checks["de"].failed


def test_gate_cli_does_not_block_history_without_baseline(tmp_path: Path) -> None:
    """Lịch sử cũ chưa sinh lại thì bỏ qua, không làm đỏ CI một cách vô cớ."""
    path = tmp_path / "history.csv"
    pd.DataFrame(
        {"mode": ["loto"], "target_date": ["2026-03-01"], "logloss": [0.5]}
    ).to_csv(path, index=False)
    result = subprocess.run(
        [sys.executable, "src/check_baseline_skill.py", "--history", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "BỎ QUA" in result.stdout

    strict = subprocess.run(
        [
            sys.executable,
            "src/check_baseline_skill.py",
            "--history",
            str(path),
            "--require-baseline",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert strict.returncode == 1


def test_gate_cli_fails_on_a_real_regression(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    _history_frame("loto", 0.95, 0.55, DEFAULT_WINDOW).to_csv(path, index=False)
    result = subprocess.run(
        [sys.executable, "src/check_baseline_skill.py", "--history", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "LỖI" in result.stdout


def test_release_check_runs_the_skill_gate() -> None:
    """Cổng phải nằm trong quy trình phát hành, không chỉ tồn tại trong kho."""
    script = (ROOT / "scripts/release_check.sh").read_text(encoding="utf-8")
    assert "src/check_baseline_skill.py" in script


# --- Lớp 2: trang Chất lượng mô hình ---------------------------------------


def _quality_headers(page: Path) -> list[str]:
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    table = soup.find("table")
    return [th.get_text(strip=True) for th in table.find_all("th")] if table else []


def test_quality_page_shows_skill_only_when_the_data_supports_it() -> None:
    """Có đối chứng thì hiện cột kỹ năng; chưa có thì thoái lui êm, không lỗi."""
    history = ROOT / "data/prob_eval/ensemble_history.csv"
    page = ROOT / "docs/model-quality.html"
    if not history.exists():
        pytest.skip("kho chưa có lịch sử đánh giá")

    original = history.read_text(encoding="utf-8")
    try:
        frame = pd.read_csv(history)
        frame["baseline_logloss"] = [
            baseline_rate("loto") if m == "loto" else 4.60517 for m in frame["mode"]
        ]
        frame["baseline_brier"] = 0.18
        frame["logloss_skill"] = (
            frame["baseline_logloss"] - frame["logloss"]
        ) / frame["baseline_logloss"]
        frame["brier_skill"] = 0.0
        frame.to_csv(history, index=False)
        subprocess.run(
            [sys.executable, "src/build_dashboard.py"], cwd=ROOT, check=True
        )
        headers = _quality_headers(page)
        assert any("Kỹ năng" in h for h in headers), headers
        assert any("đường cơ sở" in h for h in headers), headers
    finally:
        history.write_text(original, encoding="utf-8")
        subprocess.run(
            [sys.executable, "src/build_dashboard.py"], cwd=ROOT, check=True
        )

    headers = _quality_headers(page)
    assert not any("Kỹ năng" in h for h in headers), headers
