"""Chấm xác suất ĐÃ CÔNG BỐ, và báo động khi kỹ năng ngoài mẫu rời vùng 0.

Mọi phép kiểm ở đây dựng kho dữ liệu nhỏ trong thư mục tạm: artifact đã công
bố và kết quả quay, với hành vi biết trước. Không phép nào đọc ``data/`` thật —
kho thật hôm nay nằm trong vùng 0, nên dựa vào nó thì nhánh báo động không bao
giờ được chạy tới.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import skill_monitor as sm

PRIZES = [f"p{i}" for i in range(27)]


def _write_store(
    root: Path,
    days: int,
    *,
    de_mass_on_winner: float = 0.01,
    loto_winner_prob: float | None = None,
    extra_unplayed_day: bool = False,
    seed: int = 7,
) -> list[str]:
    """Kho giả: ``days`` kỳ đã quay, mỗi kỳ một cặp artifact đã công bố.

    ``de_mass_on_winner`` là xác suất Đặc Biệt đặt vào đúng con sẽ về (0,01 =
    đoán đều). ``loto_winner_prob`` là xác suất LOTO đặt vào mọi con sẽ về;
    None nghĩa là đặt đúng tỉ lệ nền cho mọi con.
    """
    rng = np.random.default_rng(seed)
    (root / "predict").mkdir(parents=True, exist_ok=True)
    rows, out_days = [], []
    base = sm.baseline_rate("loto")
    start = date(2026, 6, 1)
    for i in range(days + (1 if extra_unplayed_day else 0)):
        day = (start + timedelta(days=i)).isoformat()
        numbers = rng.integers(0, 100, size=28)
        special, loto = int(numbers[0]), numbers[1:]
        de = np.full(100, (1.0 - de_mass_on_winner) / 99)
        de[special] = de_mass_on_winner
        lo = np.full(100, base)
        if loto_winner_prob is not None:
            lo[np.unique(np.r_[special, loto])] = loto_winner_prob
        for mode, prob in (("de", de), ("loto", lo)):
            pd.DataFrame({"number": np.arange(100), "prob": prob}).to_csv(
                root / "predict" / f"predict_next_{mode}_all_{day}.csv", index=False
            )
        if i < days:  # kỳ cuối có thể là kỳ CHƯA quay
            rows.append({"date": day, "special": special, **dict(zip(PRIZES, [special, *loto], strict=False))})
            out_days.append(day)
    pd.DataFrame(rows).to_csv(root / "xsmb-2-digits.csv", index=False)
    return out_days


def test_it_grades_exactly_the_published_vector_against_the_real_draw(tmp_path: Path) -> None:
    days = _write_store(tmp_path, 5, extra_unplayed_day=True)

    graded, probs, labels = sm.published_evaluation(tmp_path, "de")

    assert graded == days, "kỳ chưa quay không được chấm"
    assert probs.shape == labels.shape == (5, 100)
    assert (labels.sum(axis=1) == 1).all(), "Đặc Biệt: đúng một con về mỗi kỳ"
    loto_days, _, loto_labels = sm.published_evaluation(tmp_path, "loto")
    assert loto_days == days
    assert (loto_labels.sum(axis=1) >= 1).all()


def test_the_no_information_forecast_scores_exactly_zero(tmp_path: Path) -> None:
    """Đoán đều / đoán tỉ lệ nền là mốc 0 theo định nghĩa. Nếu hàm chấm lệch
    mốc thì mọi báo động phía sau đều lệch theo."""
    _write_store(tmp_path, 10)
    for mode in sm.MODES:
        _, probs, labels = sm.published_evaluation(tmp_path, mode)
        assert np.allclose(sm.daily_skill(mode, probs, labels), 0.0, atol=1e-12), mode


@pytest.mark.parametrize(
    ("kwargs", "mode", "expected"),
    [
        ({}, "loto", "vung_0"),
        ({"de_mass_on_winner": 0.002}, "de", "te_hon"),
        ({"de_mass_on_winner": 0.05}, "de", "hon"),
        ({"loto_winner_prob": 0.15}, "loto", "te_hon"),
        ({"loto_winner_prob": 0.40}, "loto", "hon"),
    ],
)
def test_the_monitor_alarms_in_both_directions(
    tmp_path: Path, kwargs: dict, mode: str, expected: str
) -> None:
    """Rời vùng 0 theo hướng NÀO cũng là tin cần người xem: tệ hơn là hồi quy,
    tốt hơn trên một kỳ quay đã kiểm là ngẫu nhiên thì phải kiểm lại."""
    _write_store(tmp_path, 40, **kwargs)
    check = {c.mode: c for c in sm.evaluate(tmp_path)}[mode]

    assert check.state == expected, check.describe()
    assert check.alarm is (expected in ("te_hon", "hon"))


def test_too_few_days_is_not_a_verdict(tmp_path: Path) -> None:
    _write_store(tmp_path, sm.MIN_DAYS - 1, de_mass_on_winner=0.002)
    check = {c.mode: c for c in sm.evaluate(tmp_path)}["de"]
    assert check.state == "chua_du"
    assert check.alarm is False


def test_the_cli_turns_the_run_red_only_when_skill_leaves_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calm, bad = tmp_path / "calm", tmp_path / "bad"
    _write_store(calm, 40)
    _write_store(bad, 40, de_mass_on_winner=0.002)

    monkeypatch.setattr("sys.argv", ["skill_monitor", "--data-dir", str(calm)])
    assert sm.main() == 0
    monkeypatch.setattr("sys.argv", ["skill_monitor", "--data-dir", str(bad)])
    assert sm.main() == 1
    assert "::error::" in capsys.readouterr().out


def test_the_quality_report_grades_published_artifacts_once_there_are_enough(
    tmp_path: Path,
) -> None:
    """Trang Chất lượng từng chấm một bản dựng lại bỏ qua hiệu chỉnh — một mô
    hình khác mô hình được công bố. Đủ artifact thì phải chấm artifact."""
    import model_quality as mq

    _write_store(tmp_path, sm.MIN_DAYS, de_mass_on_winner=0.012)
    (tmp_path / "prob_eval").mkdir()
    pd.DataFrame(
        {"mode": ["de"], "target_date": ["2026-06-01"], "logloss": [4.6], "brier": [0.99]}
    ).to_csv(tmp_path / "prob_eval" / "ensemble_history.csv", index=False)

    report = json.loads(mq.build(tmp_path).read_text(encoding="utf-8"))

    for mode in sm.MODES:
        block = report["modes"][mode]
        assert block["source"] == "published", mode
        assert block["days"] == sm.MIN_DAYS
    de_max = report["modes"]["de"]["sharpness"]["max"]
    assert de_max == pytest.approx(0.012), "phải chấm đúng xác suất đã công bố"
    assert {row["mode"] for row in report["monitor"]} == set(sm.MODES)


def test_a_store_without_outcomes_or_artifacts_is_empty_not_a_crash(tmp_path: Path) -> None:
    """Thiếu dữ liệu là "chưa có gì để chấm", không phải lỗi — ném ở đây từng
    làm sập cả bước chẩn đoán của trang Chất lượng."""
    for mode in sm.MODES:
        days, probs, labels = sm.published_evaluation(tmp_path, mode)
        assert days == [] and probs.shape == labels.shape == (0, 100)
    assert all(check.state == "chua_du" for check in sm.evaluate(tmp_path))


# ---------------------------------------------------------------------------
# Sổ cái: chuỗi đánh giá phải sống lâu hơn artifact bị dọn
# ---------------------------------------------------------------------------


def test_the_real_cleanup_step_keeps_a_full_monitoring_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review của PR #93: pipeline chạy ``cleanup_artifacts --retention-days
    45``, nên chỉ đọc artifact thì cửa sổ 60 kỳ không bao giờ đầy. Chạy đúng
    bước dọn ấy trên 70 kỳ rồi đòi bộ theo dõi vẫn thấy đủ 60."""
    import cleanup_artifacts

    days = _write_store(tmp_path, 70)
    pd.DataFrame({"date": days}).to_csv(tmp_path / "xsmb.csv", index=False)

    monkeypatch.setattr(
        "sys.argv", ["cleanup_artifacts", "--data-dir", str(tmp_path), "--retention-days", "45"]
    )
    cleanup_artifacts.main()

    left = sorted((tmp_path / "predict").glob("predict_next_de_all_*.csv"))
    assert len(left) < 60, "mẫu dựng sẵn phải thật sự bị dọn bớt"
    for check in sm.evaluate(tmp_path):
        assert check.days == sm.DEFAULT_WINDOW, check.describe()
    ledger = pd.read_csv(tmp_path / sm.LEDGER, dtype={"target_date": str})
    assert set(ledger["target_date"]) == set(days)


def test_the_first_recorded_skill_is_never_overwritten(tmp_path: Path) -> None:
    """Lần chấm đầu sát lúc công bố nhất. Một tệp viết lại về sau — dù vì lý
    do gì — không được đè lên bản đã ghi."""
    days = _write_store(tmp_path, sm.MIN_DAYS)
    sm.update_ledger(tmp_path)
    ledger = pd.read_csv(tmp_path / sm.LEDGER, dtype={"target_date": str})
    ledger.loc[(ledger["mode"] == "de") & (ledger["target_date"] == days[0]), "skill"] = 0.123
    ledger.to_csv(tmp_path / sm.LEDGER, index=False)

    sm.update_ledger(tmp_path)
    graded_days, skills = sm.graded_series(tmp_path, "de")

    assert graded_days[0] == days[0]
    assert skills[0] == pytest.approx(0.123)


def test_updating_the_ledger_twice_changes_nothing(tmp_path: Path) -> None:
    _write_store(tmp_path, sm.MIN_DAYS)
    first = sm.update_ledger(tmp_path).read_bytes()
    assert sm.update_ledger(tmp_path).read_bytes() == first
