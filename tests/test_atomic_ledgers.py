"""Sổ cái chỉ-ghi-thêm phải sống sót khi tiến trình chết GIỮA lúc ghi.

Các sổ này đọc lại chính mình rồi ghi lại toàn bộ. Ghi bằng ``open("w")`` thì tệp bị
cắt về rỗng trước; chết giữa chừng (đĩa đầy, runner bị huỷ) để lại một sổ cụt, và
lần chạy sau gộp sổ cụt ấy — các dòng cũ mất khỏi bản làm việc. Mỗi phép kiểm dưới
đây làm hỏng đúng lần ghi (ghi được một nửa rồi ném lỗi) và đòi sổ cũ còn nguyên.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pandas as pd
import pytest

import atomic_io
import digit_sum_hypothesis
import fun_draw_ledger
import hot_tail_test
import skill_monitor

DATA = Path(__file__).resolve().parents[1] / "data"


def _crash_half_way_to_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """``DataFrame.to_csv`` ghi được nửa nội dung rồi ném lỗi, như đĩa đầy."""
    original = pd.DataFrame.to_csv

    def crashing(self, path_or_buf=None, *args, **kwargs):
        text = original(self, None, *args, **kwargs)
        half = text[: len(text) // 2]
        if hasattr(path_or_buf, "write"):
            path_or_buf.write(half)
        else:
            Path(path_or_buf).write_text(half, encoding="utf-8")
        raise OSError("đĩa đầy")

    monkeypatch.setattr(pd.DataFrame, "to_csv", crashing)


def _crash_on_second_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """``csv.DictWriter.writerow`` ghi được dòng đầu rồi ném lỗi ở dòng thứ hai."""
    original = csv.DictWriter.writerow
    calls = {"n": 0}

    def crashing(self, row):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("đĩa đầy")
        return original(self, row)

    monkeypatch.setattr(csv.DictWriter, "writerow", crashing)


def test_atomic_write_keeps_the_old_file_and_leaves_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "sổ.csv"
    target.write_text("cũ\n", encoding="utf-8")

    def broken(_src, _dst):
        raise OSError("đĩa đầy")

    original = atomic_io.os.replace
    atomic_io.os.replace = broken
    try:
        with pytest.raises(OSError):
            atomic_io.atomic_write_text(target, "mới\n")
    finally:
        atomic_io.os.replace = original
    assert target.read_text(encoding="utf-8") == "cũ\n"
    assert [p.name for p in tmp_path.iterdir()] == ["sổ.csv"]


def test_fun_draw_ledger_survives_a_crash_mid_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "fun_draw").mkdir()
    shutil.copy(DATA / fun_draw_ledger.LEDGER, tmp_path / fun_draw_ledger.LEDGER)
    before = (tmp_path / fun_draw_ledger.LEDGER).read_bytes()
    frame = fun_draw_ledger.read_ledger(tmp_path)
    _crash_half_way_to_csv(monkeypatch)
    with pytest.raises(OSError):
        fun_draw_ledger.write_ledger(frame, tmp_path)
    assert (tmp_path / fun_draw_ledger.LEDGER).read_bytes() == before


def test_hot_tail_ledger_survives_a_crash_mid_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shutil.copy(DATA / "xsmb-2-digits.csv", tmp_path / "xsmb-2-digits.csv")
    hot_tail_test.update_ledger(tmp_path)
    before = (tmp_path / hot_tail_test.LEDGER).read_bytes()
    _crash_on_second_row(monkeypatch)
    with pytest.raises(OSError):
        hot_tail_test.update_ledger(tmp_path)
    assert (tmp_path / hot_tail_test.LEDGER).read_bytes() == before


def test_digit_sum_ledger_survives_a_crash_mid_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shutil.copy(DATA / "xsmb.csv", tmp_path / "xsmb.csv")
    digit_sum_hypothesis.update_ledger(tmp_path)
    before = (tmp_path / digit_sum_hypothesis.LEDGER).read_bytes()
    _crash_on_second_row(monkeypatch)
    with pytest.raises(OSError):
        digit_sum_hypothesis.update_ledger(tmp_path)
    assert (tmp_path / digit_sum_hypothesis.LEDGER).read_bytes() == before


def test_published_skill_ledger_survives_a_crash_mid_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / skill_monitor.LEDGER
    ledger.parent.mkdir(parents=True)
    shutil.copy(DATA / skill_monitor.LEDGER, ledger)
    before = ledger.read_bytes()
    monkeypatch.setattr(skill_monitor, "graded_series",
                        lambda _d, _m: (["2026-10-01", "2026-10-02"], pd.Series([0.1, 0.2]).to_numpy()))
    _crash_half_way_to_csv(monkeypatch)
    with pytest.raises(OSError):
        skill_monitor.update_ledger(tmp_path)
    assert ledger.read_bytes() == before
