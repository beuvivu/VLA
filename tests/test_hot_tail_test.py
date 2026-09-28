"""Phép kiểm tiến cứu "đuôi nóng 7 kỳ": chấm đúng, chỉ chấm kỳ SAU ngày đăng ký,
sổ cái giữ lần ghi đầu, và tham số đã đăng ký không bị sửa lặng lẽ.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import hot_tail_test as ht


def test_the_registered_parameters_are_not_edited_to_fit_the_result() -> None:
    """Sửa bất kỳ tham số nào sau khi thấy kết quả là phá phép kiểm tiến cứu.
    Muốn đổi thì đăng ký giả thuyết MỚI với ngày bắt đầu mới."""
    assert (ht.REGISTERED_ON, ht.FIRST_TARGET) == ("2026-09-28", "2026-09-29")
    assert (ht.WINDOW, ht.MIN_DRAWS, ht.ALPHA, ht.Z_CRITICAL) == (7, 180, 0.01, 2.326)
    assert ht.FIRST_TARGET > ht.REGISTERED_ON, "kỳ đầu được chấm phải SAU ngày đăng ký"


def _draw(numbers: list[int]) -> np.ndarray:
    row = list(numbers) + [99] * (27 - len(numbers))
    return np.array(row[:27])


def test_one_draw_is_scored_against_the_same_draw_average() -> None:
    history = np.stack([_draw([4, 14, 24, 34]) for _ in range(7)])  # đuôi 4 và 9 (số 99)
    today = _draw([4, 14, 1])
    out = ht.score_draw(history, today)
    # đuôi 9 chỉ có con 99 (27−4 = 23 lần/kỳ nhưng tính theo KỲ-VỀ: 1/kỳ) — đuôi 4 có 4
    assert out["hot_tails"] == "4"
    rate4 = 2 / 10
    rates = np.zeros(10)
    rates[4], rates[1], rates[9] = 2 / 10, 1 / 10, 1 / 10
    assert out["hot_rate"] == pytest.approx(rate4)
    assert out["diff"] == pytest.approx(rate4 - rates.mean())


def test_tied_hot_tails_are_averaged() -> None:
    history = np.stack([_draw([3, 13, 7, 17]) for _ in range(7)])  # đuôi 3 và 7 hoà
    today = _draw([3, 13, 23])  # đuôi 3 về 3 con, đuôi 7 không con nào
    out = ht.score_draw(history, today)
    assert out["hot_tails"] == "37"
    assert out["hot_rate"] == pytest.approx((3 / 10 + 0) / 2)


def _store(root: Path, start: str, days: int, seed: int = 1) -> list[str]:
    rng = np.random.default_rng(seed)
    first = date.fromisoformat(start)
    dates = [(first + timedelta(days=i)).isoformat() for i in range(days)]
    frame = pd.DataFrame(rng.integers(0, 100, size=(days, 27)), columns=ht.PRIZES)
    frame.insert(0, "date", dates)
    root.mkdir(parents=True, exist_ok=True)
    frame.to_csv(root / "xsmb-2-digits.csv", index=False)
    return dates


def test_only_draws_after_registration_are_scored(tmp_path: Path) -> None:
    """Kỳ trước ngày đăng ký đã được nhìn khi đặt giả thuyết — chấm chúng là
    chấm lại chính bằng chứng hồi cứu."""
    dates = _store(tmp_path, "2026-09-01", 40)
    ht.update_ledger(tmp_path)
    ledger = pd.read_csv(tmp_path / ht.LEDGER, dtype={"date": str})
    assert ledger["date"].tolist() == [d for d in dates if d >= ht.FIRST_TARGET]
    assert ledger["date"].min() == ht.FIRST_TARGET


def test_the_first_recorded_score_is_never_overwritten(tmp_path: Path) -> None:
    _store(tmp_path, "2026-09-20", 30)
    path = ht.update_ledger(tmp_path)
    ledger = pd.read_csv(path, dtype={"date": str, "hot_tails": str})
    ledger.loc[0, "diff"] = 0.5
    ledger.to_csv(path, index=False)
    ht.update_ledger(tmp_path)
    again = pd.read_csv(path, dtype={"date": str, "hot_tails": str})
    assert again.loc[0, "diff"] == pytest.approx(0.5)
    assert ht.update_ledger(tmp_path).read_bytes() == path.read_bytes()


def _ledger(root: Path, diffs: list[float]) -> None:
    start = date.fromisoformat(ht.FIRST_TARGET)
    rows = [{"date": (start + timedelta(days=i)).isoformat(), "hot_tails": "4",
             "hot_rate": 0.3, "all_rate": 0.24, "diff": d} for i, d in enumerate(diffs)]
    (root / ht.LEDGER).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=ht.FIELDS).to_csv(root / ht.LEDGER, index=False)


@pytest.mark.parametrize(
    ("diffs", "state"),
    [
        ([0.05] * 50 + [0.0] * 50, "dang_thu"),          # chưa đủ MIN_DRAWS
        ([0.04, -0.02] * 100, "xac_nhan"),               # trung bình +0,01, rõ rệt
        ([0.02, -0.02] * 100, "bac_bo"),                 # trung bình 0
        ([-0.04, 0.02] * 100, "bac_bo"),                 # tệ hơn cũng là bác bỏ (một phía)
    ],
)
def test_the_verdict_follows_the_registered_rule(tmp_path: Path, diffs, state) -> None:
    _ledger(tmp_path, diffs)
    result = ht.evaluate(tmp_path)
    assert result["state"] == state, result
    assert result["draws"] == len(diffs)


def test_the_page_shows_the_prospective_state() -> None:
    import build_confidence_page as page

    report = {"hot_tail": {**ht.evaluate(Path("/nonexistent")), "draws": 12,
                           "first": "2026-09-29", "last": "2026-10-10"}}
    card = page.hot_tail_card(report)
    assert "12/180" in card
    assert "Đang thu thập" in card
    assert "2026-09-29 → 2026-10-10" in card
