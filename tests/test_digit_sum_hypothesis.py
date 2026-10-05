"""Phép kiểm tiến cứu "tổng – bóng – chạm": chỉ chấm kỳ SAU ngày đăng ký, sổ cái
giữ lần ghi đầu, kết luận theo đúng luật đã chốt, và trang in đúng trạng thái.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import digit_sum_hypothesis as dh
import digit_sum_rules as dsr
from xsmb_domain import FIELD_WIDTHS


def test_the_registered_parameters_are_not_edited_to_fit_the_result() -> None:
    """Sửa tham số sau khi thấy kết quả là phá phép kiểm tiến cứu. Muốn đổi thì
    đăng ký giả thuyết MỚI với ngày bắt đầu mới."""
    assert (dh.REGISTERED_ON, dh.FIRST_TARGET) == ("2026-10-05", "2026-10-06")
    assert (dh.MIN_DRAWS, dh.ALPHA) == (180, 0.01)
    assert dh.FIRST_TARGET > dh.REGISTERED_ON == dh.RETROSPECTIVE["last_draw"]
    assert [rule.key for rule in dsr.RULES] == ["dau_db", "duoi_db", "dan_cham", "lo_g5", "lo_vip"]


def _history(start: str, days: int, seed: int, *, planted: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = {field: rng.integers(0, 10**width, size=days) for field, width in FIELD_WIDTHS}
    data["date"] = pd.date_range(start, periods=days, freq="D").strftime("%Y-%m-%d")
    frame = pd.DataFrame(data)
    if planted:
        # Đầu Đặc Biệt kỳ sau LUÔN là tổng 2 số cuối Đặc Biệt kỳ trước.
        special = frame["special"].to_numpy().copy()
        for t in range(1, days):
            head = dsr.tong(f"{special[t - 1]:05d}"[-2:])
            special[t] = special[t] // 100 * 100 + head * 10 + special[t] % 10
        frame["special"] = special
    return frame


def _write(tmp_path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(tmp_path / "xsmb.csv", index=False)


def test_only_draws_after_registration_are_scored(tmp_path: Path) -> None:
    _write(tmp_path, _history("2026-09-26", 20, seed=1))
    path = dh.update_ledger(tmp_path)
    ledger = pd.read_csv(path, dtype={"date": str, "picks": str})
    assert ledger["date"].min() == dh.FIRST_TARGET
    assert len(ledger) == 5 * len(ledger["date"].unique())
    first = ledger[ledger["date"] == dh.FIRST_TARGET]
    assert set(first["base_date"]) == {"2026-10-05"}, "kỳ gốc là kỳ NGAY TRƯỚC kỳ được chấm"


def test_the_ledger_keeps_the_first_write(tmp_path: Path) -> None:
    """Sổ cái là bằng chứng: lượt sau không được viết lại dòng đã chấm."""
    _write(tmp_path, _history("2026-10-01", 15, seed=2))
    path = dh.update_ledger(tmp_path)
    ledger = pd.read_csv(path, dtype={"date": str, "picks": str})
    ledger.loc[0, "hit"] = 1 - int(ledger.loc[0, "hit"])
    ledger.loc[0, "picks"] = "edited"
    ledger.to_csv(path, index=False)
    dh.update_ledger(tmp_path)
    again = pd.read_csv(path, dtype={"date": str, "picks": str})
    assert again.loc[0, "picks"] == "edited"
    assert len(again) == len(ledger)


def test_each_row_records_the_exact_chance_of_a_same_size_random_pick(tmp_path: Path) -> None:
    frame = _history("2026-10-03", 6, seed=3)
    _write(tmp_path, frame)
    ledger = pd.read_csv(dh.update_ledger(tmp_path), dtype={"date": str, "picks": str})
    row = ledger[(ledger["date"] == "2026-10-07") & (ledger["rule"] == "lo_vip")].iloc[0]
    today = frame[frame["date"] == "2026-10-07"].iloc[0]
    lotos = {int(today[field]) % 100 for field, _ in FIELD_WIDTHS}
    k = len(row["picks"].split())
    assert float(row["chance"]) == pytest.approx(1 - math.comb(100 - len(lotos), k) / math.comb(100, k))
    assert int(row["hit"]) == int(bool(lotos & {int(x) for x in row["picks"].split()}))


@pytest.mark.parametrize(
    "days, planted, state",
    [
        (60, False, "dang_thu"),     # chưa đủ MIN_DRAWS
        (200, True, "xac_nhan"),     # đầu Đặc Biệt cài sẵn: luôn trúng
        (200, False, "bac_bo"),      # ngẫu nhiên: không quy tắc nào qua Holm
    ],
)
def test_the_verdict_follows_the_registered_rule(tmp_path: Path, days, planted, state) -> None:
    _write(tmp_path, _history("2026-10-05", days, seed=4, planted=planted))
    dh.update_ledger(tmp_path)
    result = dh.evaluate(tmp_path)
    assert result["state"] == state, [(r["rule"], r["p_holm"]) for r in result["rules"]]
    assert result["draws"] == days - 1
    by_rule = {r["rule"]: r for r in result["rules"]}
    if planted:
        assert by_rule["dau_db"]["state"] == "xac_nhan"
        assert by_rule["dau_db"]["hit_rate"] == pytest.approx(1.0)
        assert by_rule["lo_vip"]["state"] == "bac_bo"


def test_the_page_shows_the_prospective_state(tmp_path: Path) -> None:
    import build_confidence_page as page

    _write(tmp_path, _history("2026-10-05", 13, seed=5))
    dh.update_ledger(tmp_path)
    card = page.digit_sum_card({"digit_sum": dh.evaluate(tmp_path)})
    assert "12/180" in card
    assert "Đang thu thập" in card
    assert "2026-10-06 → 2026-10-17" in card
    assert "không phải dự báo" in card
    assert "Chưa có dữ liệu" in page.digit_sum_card({})
