"""Bố cục Dashboard phải giữ đủ số, chỉ số và dữ liệu kiểm chứng."""

import json

from bs4 import BeautifulSoup
import pandas as pd

from build_dashboard import main
from dashboard_tables import weights_card


def test_weight_label_identifies_cau_keo_model():
    payload = {"weights": {"w_cau": .3, "w_ml": .25}}
    soup = BeautifulSoup(weights_card(payload, "loto"), "html.parser")
    rows = [[cell.get_text() for cell in row.select("td")]
            for row in soup.select(".app-dash-weights tbody tr")]
    assert rows == [["Cầu-kèo AI/ML", "0.3"], ["Học máy", "0.25"]]
    assert json.loads(soup.select_one("details pre").get_text()) == payload


def test_dashboard_separates_readable_panels_without_losing_evidence(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "predict").mkdir(parents=True)
    (data / "ensemble").mkdir()
    picks = {"anchor_date": "2026-10-07", "target_date": "2026-10-08",
             "top4": [0, 3, 8, 9], "top8": list(range(8)), "top10": list(range(10)),
             "online": {"status": "shadow", "n_settled": 0, "journal_sha256": "a" * 64},
             "meta": {"active": False}}
    calibration = {"params": {"a": 1.0, "b": 0.0, "temperature": 1.0},
                   "selection": {"chosen": "identity", "fit_days": 20, "holdout_days": 0}}
    for mode in ("loto", "de"):
        (data / "predict" / f"picks_{mode}.json").write_text(json.dumps(picks))
        (data / "ensemble" / f"calibration_{mode}.json").write_text(json.dumps(calibration))
        pd.DataFrame({"number": [0, 3], "prob": [.123456, .098765]}).to_csv(
            data / "predict" / f"predict_next_{mode}_all_2026-10-08.csv", index=False)
    monkeypatch.chdir(tmp_path)
    main(["--docs-dir", "docs"])
    soup = BeautifulSoup((tmp_path / "docs/dashboard.html").read_text(), "html.parser")
    assert len(soup.select(".app-dash-group")) == 4
    for mode in ("loto", "de"):
        table = soup.select_one(f'[data-picks-mode="{mode}"]')
        assert table is not None
        rows = table.select("tbody tr")
        assert [n.text for n in rows[0].select(".app-dash-code")] == ["00", "03", "08", "09"]
        assert [n.text for n in rows[2].select(".app-dash-code")] == [f"{n:02d}" for n in range(10)]
    assert len(soup.select(".app-dash-ranking tbody tr")) == 4
    assert "0.123456" in soup.select_one(".app-dash-ranking").get_text()
    evidence = [json.loads(n.get_text()) for n in soup.select("details pre")]
    assert evidence.count(picks) == 2 and evidence.count(calibration) == 2
    for d in soup.select("details"):
        d.decompose()
    visible = soup.get_text(" ", strip=True)
    assert "Theo dõi đối chứng" in visible and "Giữ nguyên xác suất" in visible
    assert "20" in visible and "0" in visible
    assert "a" * 64 not in visible
    for path in (data / "predict").glob("picks_*.json"):
        assert json.loads(path.read_text()) == picks


def test_dashboard_missing_data_does_not_invent_active_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["--docs-dir", "docs"])
    soup = BeautifulSoup((tmp_path / "docs/dashboard.html").read_text(), "html.parser")
    assert len(soup.select(".app-dash-group")) == 4
    assert not soup.select("[data-picks-mode] .app-dash-code")
    assert "Chưa có dữ liệu" in soup.get_text()
    assert "Đang áp dụng" not in soup.get_text()
