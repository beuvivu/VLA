"""Bảng thống kê ghi MỘT bản CSV, không kèm bản JSON (04-11-2026).

``_dump_table`` của ``statistical_matrices`` và ``advanced_stats``, cùng ``conditional_matrices`` và
``statistics_ai_overlay``, từng ghi mỗi bảng thêm một bản ``to_json(orient="records", indent=2)``: 52 tệp,
64 MB trong ``data/stats/advanced`` (riêng ``period_frequency_loto_week.json`` 18,5 MB) mà không trang,
Worker, workflow hay mã nào đọc — trang và manifest đọc CSV — trong khi mỗi lượt chốt viết lại chúng vào
git. Tệp JSON thật (manifest, chẩn đoán) không có CSV cùng tên nên không bị luật này bắt.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from stats import advanced_stats, statistical_matrices

ADVANCED = Path(__file__).resolve().parents[2] / "data" / "stats" / "advanced"


def json_twins(folder: Path) -> list[str]:
    """Tệp ``.json`` có ``.csv`` cùng tên trong cùng thư mục."""
    return sorted(path.name for path in folder.glob("*.json") if path.with_suffix(".csv").exists())


def test_the_twin_rule_itself_finds_a_twin(tmp_path: Path) -> None:
    for name in ("bang.csv", "bang.json", "statistics_manifest.json", "chi_csv.csv"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert json_twins(tmp_path) == ["bang.json"]


def test_the_committed_advanced_tables_have_no_json_twin() -> None:
    assert sorted(path.name for path in ADVANCED.glob("*.csv")), "thư mục rỗng — luật đang quét trên tập rỗng"
    assert json_twins(ADVANCED) == []
    # Ba tệp JSON được đọc thật vẫn còn.
    assert {"statistics_manifest.json", "ai_ml_signal_diagnostics.json",
            "conditional_matrices_diagnostics.json"} <= {path.name for path in ADVANCED.glob("*.json")}


def test_each_table_writer_writes_only_the_csv(tmp_path: Path) -> None:
    frame = pd.DataFrame({"number": [0, 7, 42], "count": [3, 1, 2]})
    returned = statistical_matrices._dump_table(frame, out_dir=tmp_path / "a", name="bang")
    advanced_stats._dump_table(frame, out_dir=tmp_path / "b", name="bang")
    assert returned == tmp_path / "a" / "bang.csv"
    assert sorted(p.name for p in (tmp_path / "a").iterdir()) == ["bang.csv"]
    assert sorted(p.name for p in (tmp_path / "b").iterdir()) == ["bang.csv"]
    assert pd.read_csv(tmp_path / "a" / "bang.csv", dtype=str)["number"].tolist() == ["00", "07", "42"]
