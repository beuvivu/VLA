"""Mã số phải giữ độ rộng qua bảng, CSV và lần cập nhật tiếp theo."""

import csv

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from build_docs_ml import _prediction_table
from build_research_lab import _conditional_table


def test_ml_table_restores_codes_after_csv_type_inference():
    frame = pd.DataFrame({"number": [0, 3, 9, 10], "prob": [.01] * 4})
    table, _ = _prediction_table(frame)
    rows = BeautifulSoup(table, "html.parser").select("tbody tr")
    assert [r.select("td")[1].text for r in rows] == ["00", "03", "09", "10"]
    assert rows[0].select("td")[0].text == "1"
    assert rows[0].select("td")[2].text == "0.010000"


def test_research_conditional_restores_code_including_zero():
    frame = pd.DataFrame({"special": [8, 8], "number": [0, 3],
                          "number_str": [0, 3], "p_eb": [.3, .2],
                          "q_value_fdr": [.1, .2], "hits": [2, 1], "trials": [9, 9]})
    rows = BeautifulSoup(_conditional_table(frame, "08"), "html.parser").select("tr")
    assert [r.select_one("td").text for r in rows] == ["00", "03"]


def test_csv_normalization_is_lossless_and_idempotent(tmp_path):
    from lottery_codes import normalize_csv

    path = tmp_path / "forecast.csv"
    path.write_text('number,number_str,prob,count,note\n0,0,0.123456789012345,3,"a,b"\n3,03,,0,\n')
    assert normalize_csv(path)
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows == [dict(number="00", number_str="00", prob="0.123456789012345", count="3", note="a,b"),
                    dict(number="03", number_str="03", prob="", count="0", note="")]
    before = path.read_bytes()
    assert not normalize_csv(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("value,expected", [(0, "00"), (3.0, "03"), ("03", "03"),
                                           (None, ""), (float("nan"), ""), (pd.NA, ""), ("", "")])
def test_code_formatter_distinguishes_missing_from_zero(value, expected):
    from lottery_codes import lottery_code
    assert lottery_code(value) == expected


@pytest.mark.parametrize("value", [-1, 100, 1.5, True, "-1", "abc", "003", "1e1"])
def test_code_formatter_rejects_invalid_codes(value):
    from lottery_codes import lottery_code
    with pytest.raises(ValueError):
        lottery_code(value)


def test_csv_prize_widths_and_conditional_tail_are_distinct(tmp_path):
    from lottery_codes import normalize_csv
    from excel_export import FIELD_WIDTHS

    raw = tmp_path / "xsmb.csv"
    raw.write_text(",".join(FIELD_WIDTHS) + "\n" + ",".join("0" for _ in FIELD_WIDTHS) + "\n")
    normalize_csv(raw)
    with raw.open() as fh:
        row = next(csv.DictReader(fh))
    assert row == {field: "0" * width for field, width in FIELD_WIDTHS.items()}
    two = tmp_path / "xsmb-2-digits.csv"
    two.write_text("special,prize6_1,prize7_1\n0,3,9\n")
    normalize_csv(two)
    assert two.read_text().splitlines()[1] == "00,03,09"
    conditional = tmp_path / "conditional" / "current_special_next_loto.csv"
    conditional.parent.mkdir()
    conditional.write_text("special,number,trials\n3,0,9\n")
    normalize_csv(conditional)
    assert conditional.read_text().splitlines()[1] == "03,00,9"


def test_invalid_csv_is_not_partly_overwritten(tmp_path):
    from lottery_codes import normalize_csv
    path = tmp_path / "forecast.csv"
    original = "number,prob\n3,0.1\n-1,0.2\n"
    path.write_text(original)
    with pytest.raises(ValueError):
        normalize_csv(path)
    assert path.read_text() == original


def test_csv_writer_preserves_internal_types_and_metrics(tmp_path):
    from lottery_codes import write_code_csv
    frame = pd.DataFrame({"number": [0, 3], "prob": [.0123456789012345, .2], "count": [3, 0]})
    original = frame.copy(deep=True)
    path = tmp_path / "prediction.csv"
    write_code_csv(frame, path, index=False)
    output = pd.read_csv(path, dtype=str)
    assert output["number"].tolist() == ["00", "03"]
    assert output["count"].tolist() == ["3", "0"]
    assert output["prob"].tolist() == ["0.0123456789012345", "0.2"]
    pd.testing.assert_frame_equal(frame, original)
    assert write_code_csv(frame, index=False) == path.read_text()


def test_dashboard_formats_csv_codes_without_padding_rank(tmp_path, monkeypatch):
    import build_dashboard
    monkeypatch.chdir(tmp_path)
    pred = tmp_path / "data" / "predict"
    pred.mkdir(parents=True)
    for mode in ("loto", "de"):
        (pred / f"predict_next_{mode}_all_2026-10-08.csv").write_text("number,prob\n0,0.3\n3,0.2\n")
    build_dashboard.main(["--docs-dir", str(tmp_path / "docs")])
    page = BeautifulSoup((tmp_path / "docs" / "dashboard.html").read_text(), "html.parser")
    for ident in ("app-lab-loto", "app-lab-de"):
        rows = page.select(f"#{ident} tbody tr")
        assert [r.select("td")[1].text for r in rows] == ["00", "03"]
        assert [r.select("td")[0].text for r in rows] == ["1", "2"]


def test_dump_preserves_csv_widths_and_numeric_model_contract(tmp_path, monkeypatch):
    import json
    import lottery
    from excel_export import FIELD_WIDTHS
    paths = lottery.RepoPaths(tmp_path, tmp_path / "data", tmp_path / "images")
    paths.data_dir.mkdir()
    raw = {"date": "2026-10-07", **dict.fromkeys(FIELD_WIDTHS, 3)}
    (paths.data_dir / "xsmb.json").write_text(json.dumps([raw]))
    lot = lottery.Lottery(paths=paths)
    lot.load()
    monkeypatch.setattr(lottery, "export_excel_outputs", lambda **kw: None)
    lot.dump()
    with (paths.data_dir / "xsmb.csv").open() as fh:
        row = next(csv.DictReader(fh))
    assert all(row[name] == "3".zfill(width) for name, width in FIELD_WIDTHS.items())
    with (paths.data_dir / "xsmb-2-digits.csv").open() as fh:
        row = next(csv.DictReader(fh))
    assert all(row[name] == "03" for name in FIELD_WIDTHS)
    assert json.loads((paths.data_dir / "xsmb.json").read_text())[0]["special"] == 3
    assert int(lot.get_raw_data().iloc[0]["special"]) == 3


@pytest.mark.parametrize("skip_docs", [False, True])
def test_pipeline_formats_exports_as_a_hard_gate(monkeypatch, skip_docs):
    import pipeline
    calls = []
    monkeypatch.setattr("sys.argv", ["pipeline.py"] + (["--skip-docs"] if skip_docs else []))
    monkeypatch.setattr(pipeline, "_run", lambda cmd, **kw: calls.append((cmd[1], kw)))
    pipeline.main()
    names = [name for name, _ in calls]
    idx = names.index("src/lottery_codes.py")
    assert calls[idx][1]["allow_fail"] is False
    assert names.index("src/online_learning.py") < idx
    if not skip_docs:
        assert idx < names.index("src/build_docs.py")
