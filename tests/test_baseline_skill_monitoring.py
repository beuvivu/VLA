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

from backfill_baseline_skill import (
    BASELINE_COLUMNS,
    backfill,
    baseline_metrics,
    brier_is_comparable,
    load_labels,
)
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
    pd.DataFrame({"target_date": day, "number": numbers, "y": y}).to_csv(history, index=False)

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
    row = evaluate_latest_emitted(mode=mode, history_path=history, predict_dir=predict_dir)
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
    row = evaluate_latest_emitted(mode="loto", history_path=history, predict_dir=predict_dir)
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
    frame = pd.DataFrame({"mode": ["loto"], "target_date": ["2026-03-01"], "logloss": [0.5]})
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
    pd.DataFrame({"mode": ["loto"], "target_date": ["2026-03-01"], "logloss": [0.5]}).to_csv(
        path, index=False
    )
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


def test_release_check_runs_the_skill_gate_strictly() -> None:
    """Cổng phải nằm trong quy trình phát hành, và ở chế độ chặt.

    Lịch sử đã có đối chứng đủ, nên thiếu cột baseline từ nay là pipeline hỏng.
    Thiếu ``--require-baseline`` thì một thay đổi như thế sẽ tự tắt cổng trong
    im lặng, đúng lớp lỗi mà cổng sinh ra để chặn.
    """
    script = (ROOT / "scripts/release_check.sh").read_text(encoding="utf-8")
    assert "src/check_baseline_skill.py --require-baseline" in script


# --- Lớp 2: trang Chất lượng mô hình ---------------------------------------


def _quality_headers(page: Path) -> list[str]:
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    table = soup.find("table")
    return [th.get_text(strip=True) for th in table.find_all("th")] if table else []


def _build_quality_page() -> list[str]:
    subprocess.run([sys.executable, "src/build_dashboard.py"], cwd=ROOT, check=True)
    return _quality_headers(ROOT / "docs/model-quality.html")


def test_quality_page_shows_skill_only_when_the_data_supports_it() -> None:
    """Có đối chứng thì hiện cột kỹ năng; chưa có thì thoái lui êm, không lỗi.

    Kiểm cả hai chiều trên cùng một tệp lịch sử thật, nên kết quả không phụ
    thuộc việc kho đã sinh lại đối chứng cho lịch sử cũ hay chưa.
    """
    history = ROOT / "data/prob_eval/ensemble_history.csv"
    if not history.exists():
        pytest.skip("kho chưa có lịch sử đánh giá")

    original = history.read_text(encoding="utf-8")
    try:
        frame = pd.read_csv(history)
        frame["baseline_logloss"] = [
            baseline_rate("loto") if m == "loto" else 4.60517 for m in frame["mode"]
        ]
        frame["baseline_brier"] = 0.18
        frame["logloss_skill"] = (frame["baseline_logloss"] - frame["logloss"]) / frame[
            "baseline_logloss"
        ]
        frame["brier_skill"] = 0.0
        frame.to_csv(history, index=False)
        headers = _build_quality_page()
        assert any("Kỹ năng" in h for h in headers), headers
        assert any("đường cơ sở" in h for h in headers), headers

        # Không có đối chứng thì trang phải dựng được và lùi về bốn cột.
        stripped = frame.drop(columns=list(BASELINE_COLUMNS))
        stripped.to_csv(history, index=False)
        headers = _build_quality_page()
        assert not any("Kỹ năng" in h for h in headers), headers
    finally:
        history.write_text(original, encoding="utf-8")
        subprocess.run([sys.executable, "src/build_dashboard.py"], cwd=ROOT, check=True)


# --- Sinh lại đối chứng cho lịch sử cũ -------------------------------------


def _label_frame(mode: str, days: list[str]) -> pd.DataFrame:
    """Nhãn hợp lệ: lô tô 27 số trúng, ĐB đúng một số trúng."""
    rows = []
    for day in days:
        y = [0] * 100
        if mode == "de":
            y[7] = 1
        else:
            for n in range(27):
                y[n] = 1
        for number in range(100):
            rows.append({"target_date": day, "number": number, "y": y[number]})
    return pd.DataFrame(rows)


def load_labels_from(frame: pd.DataFrame, tmp: Path, mode: str) -> dict:
    """Ghi khung nhãn ra đĩa rồi đọc qua đúng đường vào của script sinh lại."""
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / f"pred_{mode}.csv"
    frame.to_csv(path, index=False)
    return load_labels(path)


def test_backfill_matches_what_the_pipeline_would_have_written(
    tmp_path: Path,
) -> None:
    """Giá trị sinh lại phải trùng giá trị bộ chấm sản xuất ghi cho cùng ngày.

    Đây là điều kiện để trộn dòng cũ và dòng mới trong cùng một cột mà không
    tạo ra bậc thang giả trong báo cáo.
    """
    for mode in ("loto", "de"):
        history, predict_dir = _write_history(tmp_path / mode, mode, baseline_rate(mode))
        produced = evaluate_latest_emitted(mode=mode, history_path=history, predict_dir=predict_dir)
        assert produced is not None

        labels = load_labels(history)
        metrics = baseline_metrics(mode, labels[str(produced["target_date"])])
        assert metrics is not None
        assert metrics[0] == pytest.approx(produced["baseline_logloss"], abs=1e-12)
        assert metrics[1] == pytest.approx(produced["baseline_brier"], abs=1e-12)


def test_backfill_fills_missing_rows_and_computes_skill(tmp_path: Path) -> None:
    days = ["2026-03-01", "2026-03-02"]
    labels = {"loto": load_labels_from(_label_frame("loto", days), tmp_path, "loto")}
    frame = pd.DataFrame(
        {
            "mode": ["loto"] * 2,
            "target_date": days,
            "logloss": [0.5, 0.6],
            "brier": [0.18, 0.19],
        }
    )
    filled, count, skipped = backfill(frame, labels)
    assert count == 2
    assert not skipped
    assert filled["baseline_logloss"].notna().all()
    # Mô hình tốt hơn baseline thì kỹ năng dương, và ngược lại.
    base = filled["baseline_logloss"].iloc[0]
    assert (filled["logloss_skill"].iloc[0] > 0) == (0.5 < base)


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    """Chạy lại không được ghi đè dòng đã có — tránh trộn hai lần tính khác nhau."""
    days = ["2026-03-01"]
    labels = {"loto": load_labels_from(_label_frame("loto", days), tmp_path, "loto")}
    frame = pd.DataFrame({"mode": ["loto"], "target_date": days, "logloss": [0.5], "brier": [0.18]})
    once, first_count, _ = backfill(frame, labels)
    once.loc[0, "baseline_logloss"] = 99.0  # dấu vết để phát hiện ghi đè
    twice, second_count, _ = backfill(once, labels)
    assert first_count == 1
    assert second_count == 0
    assert twice["baseline_logloss"].iloc[0] == 99.0

    forced, forced_count, _ = backfill(once, labels, overwrite=True)
    assert forced_count == 1
    assert forced["baseline_logloss"].iloc[0] != 99.0


def test_backfill_skips_days_it_cannot_score_instead_of_guessing(
    tmp_path: Path,
) -> None:
    """Ngày thiếu nhãn phải bị bỏ trống; đoán bừa sẽ làm hỏng chính cổng báo động."""
    days = ["2026-03-01"]
    labels = {"loto": load_labels_from(_label_frame("loto", days), tmp_path, "loto")}
    frame = pd.DataFrame(
        {
            "mode": ["loto"] * 2,
            "target_date": days + ["2026-03-09"],
            "logloss": [0.5, 0.6],
            "brier": [0.18, 0.19],
        }
    )
    filled, count, skipped = backfill(frame, labels)
    assert count == 1
    assert len(skipped) == 1
    assert "2026-03-09" in skipped[0]
    assert pd.isna(filled["baseline_logloss"].iloc[1])


def test_backfill_rejects_invalid_labels(tmp_path: Path) -> None:
    """Nhãn không đủ 100 số, không nhị phân, hoặc ĐB nhiều hơn một số trúng."""
    short = _label_frame("loto", ["2026-03-01"]).head(50)
    assert load_labels_from(short, tmp_path / "a", "loto") == {}

    noisy = _label_frame("loto", ["2026-03-01"])
    noisy["y"] = noisy["y"].astype(float)
    noisy.loc[0, "y"] = 0.5
    assert load_labels_from(noisy, tmp_path / "b", "loto") == {}

    two_winners = np.zeros(100, dtype=int)
    two_winners[[3, 9]] = 1
    assert baseline_metrics("de", two_winners) is None


def test_brier_convention_mismatch_is_detected_without_a_hardcoded_date() -> None:
    """``categorical_brier`` từng dùng mean thay vì sum, lệch đúng 100 lần.

    Chia baseline quy ước mới cho điểm mô hình quy ước cũ cho kỹ năng ~+99% —
    mô hình trông vượt trội ngoạn mục vì lệch đơn vị. Bất biến phát hiện: với ĐB,
    ``p = exp(-logloss)`` nên Brier theo quy ước sum bắt buộc ``>= (1 - p)^2``.
    """
    logloss = 4.614117  # một ngày ĐB thật trong lịch sử kho
    winner = float(np.exp(-logloss))
    correct = (1.0 - winner) ** 2 + 99 * (0.01**2)

    assert brier_is_comparable("de", logloss, correct)
    assert not brier_is_comparable("de", logloss, correct / 100)
    # Lô tô chưa từng đổi quy ước nên không bị chặn.
    assert brier_is_comparable("loto", 0.5478, 0.1826)
    assert not brier_is_comparable("de", float("nan"), correct)


def test_backfill_leaves_brier_blank_when_conventions_disagree(tmp_path: Path) -> None:
    """Bỏ trống trung thực hơn một con số +99% do lệch đơn vị.

    LogLoss không dùng chung quy ước đó nên vẫn phải được điền — đây mới là cột
    cổng báo động đọc.
    """
    days = ["2026-03-01"]
    labels = {"de": load_labels_from(_label_frame("de", days), tmp_path, "de")}
    frame = pd.DataFrame(
        {
            "mode": ["de"],
            "target_date": days,
            "logloss": [4.614117],
            "brier": [0.009902],  # quy ước mean cũ
        }
    )
    filled, count, skipped = backfill(frame, labels)
    assert count == 1 and not skipped
    assert pd.notna(filled["baseline_logloss"].iloc[0])
    assert pd.notna(filled["logloss_skill"].iloc[0])
    assert pd.isna(filled["baseline_brier"].iloc[0])
    assert pd.isna(filled["brier_skill"].iloc[0])


def test_repository_history_carries_no_fabricated_skill() -> None:
    """Chốt chặn trên dữ liệu đã ghi: không cột kỹ năng nào được vượt ngưỡng vô lý.

    Một mô hình xổ số hơn đường cơ sở vài chục phần trăm là dấu hiệu lỗi đo, không
    phải thành tích. Ngưỡng +50% rộng hơn mọi dao động thật nhiều lần.
    """
    history = ROOT / "data/prob_eval/ensemble_history.csv"
    if not history.exists():
        pytest.skip("kho chưa có lịch sử đánh giá")
    frame = pd.read_csv(history)
    for column in ("logloss_skill", "brier_skill"):
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        assert (values < 0.50).all(), (
            f"{column} có giá trị vượt +50%, gần như chắc chắn là lệch đơn vị: "
            f"{values[values >= 0.50].tolist()[:5]}"
        )


def test_backfilled_history_activates_the_production_gate() -> None:
    """Sau khi sinh lại, cổng phải chấm được thật chứ không còn bỏ qua."""
    history = ROOT / "data/prob_eval/ensemble_history.csv"
    if not history.exists():
        pytest.skip("kho chưa có lịch sử đánh giá")
    frame = pd.read_csv(history)
    for column in BASELINE_COLUMNS:
        assert column in frame.columns, f"lịch sử chưa sinh lại cột {column}"
    checks = evaluate_history(frame)
    assert checks, "cổng không chấm được chế độ nào"
    assert all(not c.failed for c in checks), [c.describe() for c in checks]
