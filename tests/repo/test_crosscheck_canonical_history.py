"""Bộ đối chiếu sổ chuẩn với nơi ghi khác (`scripts/ops/crosscheck_canonical_history.py`).

Trang dựng sẵn theo hình dạng hai nơi ghi đã đọc trên runner ngày 23-11-2026: Minh Ngọc in bảy kỳ trên
một trang theo ngày (tiêu đề «KẾT QUẢ XỔ SỐ Miền Bắc - dd/mm/yyyy», rồi «Ngày:» và ngày ở một liên kết),
mketqua in một kỳ dưới dòng «… ngày dd-mm-yyyy». Số liệu là bảy kỳ thật 09 → 15-06-2024 của sổ chuẩn.
Đảo luật được canh (tách kỳ sai chỗ, so lệch cột, bỏ trang) thì phép kiểm tương ứng đỏ.
"""

from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "crosscheck_canonical_history.py"
WORKFLOW = ROOT / ".github" / "workflows" / "diagnose-live-sources.yml"

_spec = importlib.util.spec_from_file_location("crosscheck_canonical_history", SCRIPT)
cc = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(cc)

LABELS = ("Giải ĐB", "Giải nhất", "Giải nhì", "Giải ba", "Giải tư", "Giải năm", "Giải sáu", "Giải bảy")
WEEK = (date(2024, 6, 9), date(2024, 6, 15))


@pytest.fixture(scope="module")
def ledger() -> dict[date, dict[str, str]]:
    return cc.read_ledger(ROOT / "data" / "xsmb.csv", *WEEK)


def _prize_rows(row: dict[str, str]) -> str:
    cells, offset = [], 0
    for label, key in zip(LABELS, cc.PRIZE_ORDER, strict=True):
        count = cc.EXPECTED_COUNTS[key]
        values = "".join(f"<div>{row[f]}</div>" for f in cc.FIELDS[offset:offset + count])
        cells.append(f"<tr><td>{label}</td><td>{values}</td></tr>")
        offset += count
    return "".join(cells)


def _minhngoc_page(rows: dict[date, dict[str, str]], heading: bool = True) -> str:
    blocks = [
        (f"<div class='title'>KẾT QUẢ XỔ SỐ Miền Bắc - {day:%d/%m/%Y}</div>" if heading else "")
        + "<table><tr><td>Thứ</td>"
        f"<td>Ngày: <a href='#'>{day:%d/%m/%Y}</a> 8NQ-2NQ Ký hiệu trúng Đặc Biệt:</td></tr>"
        f"{_prize_rows(row)}</table><p>Normal 2 số 3 Số 0 1 2 3 4 5 6 7 8 9 Xem Bảng Loto</p>"
        for day, row in sorted(rows.items(), reverse=True)
    ]
    return ("<html><head><title>Minh Ngọc</title></head><body><table><tr><td>Ngày:</td><td></td></tr></table>"
            "<p>&lt;&lt;&lt;&lt; &lt;&lt;&lt; &lt;&lt; &lt;</p>" + "".join(blocks)
            + "<p>Lịch mở thưởng XSMB : Thứ 2: Xổ số kiến thiết Hà Nội</p></body></html>")


def _mketqua_page(day: date, row: dict[str, str], today: date = date(2026, 11, 23)) -> str:
    return (f"<html><head><title>Kết Quả Xổ Số Truyền Thống Hôm Nay ngày {today:%d-%m-%Y}</title></head><body>"
            f"<table><tr><th>Xổ số Truyền Thống Thứ bảy ngày {day:%d-%m-%Y}</th></tr>"
            f"<tr><td>Ký tự</td><td>8NQ-2NQ</td></tr>{_prize_rows(row)}</table>"
            "<table><tr><th>Lô tô trực tiếp</th></tr><tr><td>06</td><td>12</td></tr></table></body></html>")


def test_the_ledger_columns_follow_the_prize_order(ledger: dict[date, dict[str, str]]) -> None:
    assert len(cc.FIELDS) == 27 and cc.FIELDS[:4] == ("special", "prize1", "prize2_1", "prize2_2")
    june15 = ledger[date(2024, 6, 15)]
    # Số 0 đầu được giữ (05118, 00383, 026) và giải bảy là hai chữ số.
    assert (june15["prize3_2"], june15["prize3_4"], june15["prize6_2"]) == ("05118", "00383", "026")
    assert [june15[f"prize7_{i}"] for i in range(1, 5)] == ["13", "77", "96", "52"]


@pytest.mark.parametrize("heading", [True, False], ids=["tiêu đề", "chỉ «Ngày:» và liên kết ngày"])
def test_a_minhngoc_page_yields_each_of_its_seven_draws(ledger: dict[date, dict[str, str]], heading: bool) -> None:
    days = cc.split_days(cc.text_lines(_minhngoc_page(ledger, heading)), cc._MN_DAY)
    assert sorted(days) == sorted(ledger)
    assert days == ledger  # từng kỳ đúng 27 ô của chính nó, không lẫn kỳ bên cạnh


def test_a_draw_missing_a_prize_row_is_dropped_not_borrowed_from_the_next_draw(
        ledger: dict[date, dict[str, str]]) -> None:
    page = _minhngoc_page(ledger)
    june12 = "".join(f"<div>{ledger[date(2024, 6, 12)][f'prize7_{i}']}</div>" for i in range(1, 5))
    assert page.count(f"<tr><td>Giải bảy</td><td>{june12}</td></tr>") == 1
    days = cc.split_days(cc.text_lines(page.replace(f"<tr><td>Giải bảy</td><td>{june12}</td></tr>", "")), cc._MN_DAY)
    assert date(2024, 6, 12) not in days
    assert days == {day: row for day, row in ledger.items() if day != date(2024, 6, 12)}


def test_a_mketqua_page_skips_the_title_date_and_reads_the_draw(ledger: dict[date, dict[str, str]]) -> None:
    day = date(2024, 6, 15)
    days = cc.split_days(cc.text_lines(_mketqua_page(day, ledger[day])), cc._MK_DAY)
    assert days == {day: ledger[day]}


def test_one_minhngoc_page_covers_seven_days() -> None:
    days = [date(2024, 3, 1) + timedelta(days=i) for i in range(306)]
    anchors = cc.minhngoc_anchors(days)
    assert len(anchors) == 44 and anchors[0] == date(2024, 12, 31)
    covered = {anchor - timedelta(days=k) for anchor in anchors for k in range(cc.MINHNGOC_DAYS_PER_PAGE)}
    assert set(days) <= covered


def test_compare_reports_exactly_the_changed_cell(ledger: dict[date, dict[str, str]]) -> None:
    other = {day: dict(row) for day, row in ledger.items()}
    assert cc.compare(ledger, other)["differences"] == []
    other[date(2024, 6, 12)]["prize5_3"] = "0926"
    del other[date(2024, 6, 9)]
    result = cc.compare(ledger, other)
    assert result["differences"] == [(date(2024, 6, 12), "prize5_3", "0925", "0926")]
    assert result["missing"] == [date(2024, 6, 9)]
    assert (result["draws"], result["matching_draws"], result["cells"]) == (6, 5, 6 * 27)


def test_the_readers_fetch_each_page_once_and_exit_nonzero_on_a_difference(
        ledger: dict[date, dict[str, str]], capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[str] = []
    altered = {day: dict(row) for day, row in ledger.items()}
    altered[date(2024, 6, 10)]["special"] = "44466"

    def get(url: str) -> str:
        calls.append(url)
        if "minhngoc" in url:
            return _minhngoc_page(ledger)
        day = date(*reversed([int(part) for part in url.rsplit("/", 1)[1].removesuffix(".html").split("-")]))
        if day == date(2024, 6, 9):  # trang trả kỳ khác ngày hỏi: không được ghi cho ngày hỏi
            return _mketqua_page(date(2024, 6, 8), altered[day])
        return _mketqua_page(day, altered[day])

    days = sorted(ledger)
    assert cc.read_minhngoc(days, get, lambda: None) == ledger
    assert len(calls) == 1
    assert cc.read_mketqua(days, get, lambda: None) == {d: r for d, r in altered.items() if d != date(2024, 6, 9)}
    assert len(calls) == 1 + len(days)
    assert "trang không cho kỳ nào" not in capsys.readouterr().out
    lines = cc.report("mketqua", ledger, altered)
    assert "1 ô khác" in lines[0] and lines[1] == "   KHÁC 2024-06-10 special: sổ=44465 mketqua=44466"
    assert cc.read_mketqua([date(2024, 6, 9)], lambda url: "<html><body>Bảo trì</body></html>", lambda: None) == {}
    assert "trang không cho kỳ nào" in capsys.readouterr().out


def test_units_cage_counts_the_last_digit_of_every_prize(ledger: dict[date, dict[str, str]]) -> None:
    observed, chi2 = cc.units_digits(ledger)
    assert sum(observed) == 27 * len(ledger)
    assert observed[2] == sum(row[f][-1] == "2" for row in ledger.values() for f in cc.FIELDS)
    assert chi2 >= 0
    flat = {date(2024, 1, d): {f: "1" * (cc.WIDTHS[f] - 1) + str(d % 10) for f in cc.FIELDS} for d in range(1, 11)}
    assert cc.units_digits(flat) == ([27] * 10, 0.0)


def test_the_workflow_runs_the_crosscheck_read_only() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["crosscheck"]
    assert "inputs.crosscheck_start" in job["if"]
    run = "\n".join(step.get("run", "") for step in job["steps"])
    assert "scripts/ops/crosscheck_canonical_history.py" in run
    assert "git push" not in run and "upload-artifact" not in str(job["steps"])
    assert "inputs.crosscheck_start == ''" in workflow["jobs"]["diagnose"]["if"]
