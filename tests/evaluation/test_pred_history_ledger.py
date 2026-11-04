"""Sổ dự báo ``pred_<mode>.csv`` chỉ ghi thêm: dòng của kỳ cũ giữ nguyên TỪNG BYTE.

Mỗi lượt pipeline ghi sổ hai lần — ``record_pred_history`` thêm dòng kỳ tới (``y`` trống),
rồi ``update_pred_labels`` điền nhãn kỳ vừa quay. Trước 03-11-2026 bước đầu ghi ``y`` thành
``0.0`` (cột có ô trống nên pandas đọc là số thực) còn bước sau ép ``Int64`` và ghi ``0``:
hai lượt mỗi ngày viết lại cả 27 800 dòng của hai sổ mà không giá trị nào đổi. Phép kiểm
chạy đúng chuỗi ấy trên lịch sử dựng sẵn và đòi phần đầu tệp không đổi.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from evaluation import record_pred_history, update_pred_labels

DATA = Path(__file__).resolve().parents[2] / "data"
DAYS = ("2026-11-01", "2026-11-02", "2026-11-03")


def _forecast(target: str) -> pd.DataFrame:
    """Dòng dự báo kỳ ``target`` như ``record_pred_history.main`` dựng: chưa có cột ``y``."""
    p = np.full(100, 1 - 0.99 ** 27)
    return pd.DataFrame({
        "target_date": [target] * 100,
        "number": list(range(100)),
        "p_ml": p, "p_active": p, "p_stable": p, "p_cau": p, "p_stat": p,
        "policy_cau": [1.0] * 100,
        "policy_blend": [1.0] * 100,
    })


def _drawn(tmp: Path, upto: str) -> None:
    """``xsmb.csv`` của thư mục dữ liệu tạm: các kỳ thật tới hết ngày ``upto``."""
    xsmb = pd.read_csv(DATA / "xsmb.csv", dtype=str)
    xsmb[xsmb["date"] <= upto].to_csv(tmp / "xsmb.csv", index=False)


def _label(tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["update_pred_labels", "--data-dir", str(tmp), "--history-dir", str(tmp)])
    update_pred_labels.main()


def test_each_run_only_appends_and_old_rows_keep_every_byte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "pred_loto.csv"
    record_pred_history._upsert_history_csv(_forecast(DAYS[0]), ledger)
    _drawn(tmp_path, DAYS[0])
    _label(tmp_path, monkeypatch)
    labelled = ledger.read_bytes()

    # Lượt tối: dự báo kỳ tới, chưa quay.
    record_pred_history._upsert_history_csv(_forecast(DAYS[1]), ledger)
    pending = ledger.read_bytes()
    assert pending.startswith(labelled), "thêm kỳ chưa quay đã viết lại dòng của kỳ cũ"
    # Lượt chạy lại khi không có kết quả mới: không đổi gì.
    _label(tmp_path, monkeypatch)
    assert ledger.read_bytes() == pending

    # Kỳ ấy quay xong: điền nhãn, rồi lượt tối tiếp theo thêm kỳ sau nữa.
    _drawn(tmp_path, DAYS[1])
    _label(tmp_path, monkeypatch)
    second = ledger.read_bytes()
    assert second.startswith(labelled)
    record_pred_history._upsert_history_csv(_forecast(DAYS[2]), ledger)
    assert ledger.read_bytes().startswith(second)

    frame = pd.read_csv(ledger, dtype=str, keep_default_na=False)
    assert set(frame.loc[frame["target_date"] < DAYS[2], "y"]) == {"0", "1"}
    assert set(frame.loc[frame["target_date"] == DAYS[2], "y"]) == {""}
    assert frame["number"].tolist()[:3] == ["00", "01", "02"]


def test_labels_match_the_real_draw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "pred_loto.csv"
    record_pred_history._upsert_history_csv(_forecast(DAYS[0]), ledger)
    _drawn(tmp_path, DAYS[0])
    _label(tmp_path, monkeypatch)
    xsmb = pd.read_csv(DATA / "xsmb.csv", dtype=str).set_index("date").loc[DAYS[0]]
    came = {int(v) % 100 for v in xsmb.to_numpy()}
    got = pd.read_csv(ledger)
    assert set(got.loc[got["y"] == 1, "number"]) == came


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_rewriting_the_real_ledger_changes_only_the_label_spelling(tmp_path: Path, mode: str) -> None:
    """Sổ thật đang ghi ``0.0``: lần ghi kế tiếp đổi cách viết nhãn, không đổi giá trị nào."""
    path = DATA / "evaluation" / "history" / f"pred_{mode}.csv"
    out = tmp_path / path.name
    record_pred_history.write_history(pd.read_csv(path), out)
    before = pd.read_csv(path, dtype=str, keep_default_na=False)
    after = pd.read_csv(out, dtype=str, keep_default_na=False)
    assert list(after.columns) == list(before.columns)
    assert set(after["y"]) <= {"0", "1", ""}
    assert after.drop(columns="y").equals(before.drop(columns="y"))
    assert (pd.to_numeric(after["y"]).fillna(-1) == pd.to_numeric(before["y"]).fillna(-1)).all()
    # Ghi lần hai: trùng từng byte.
    again = tmp_path / "again.csv"
    record_pred_history.write_history(pd.read_csv(out), again)
    assert again.read_bytes() == out.read_bytes()
