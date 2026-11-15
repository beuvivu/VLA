"""Bảng thống kê ghi MỘT bản CSV, không kèm bản JSON (04-11-2026).

``_dump_table`` của ``statistical_matrices`` và ``advanced_stats``, cùng ``conditional_matrices`` và
``statistics_ai_overlay``, từng ghi mỗi bảng thêm một bản ``to_json(orient="records", indent=2)``: 52 tệp,
64 MB trong ``data/stats/advanced`` (riêng ``period_frequency_loto_week.json`` 18,5 MB) mà không trang,
Worker, workflow hay mã nào đọc — trang và manifest đọc CSV — trong khi mỗi lượt chốt viết lại chúng vào
git. Tệp JSON thật (manifest, chẩn đoán) không có CSV cùng tên nên không bị luật này bắt.

Đến 15-11-2026 phép kiểm chỉ quét ``data/stats/advanced``, nên ``significance_stats`` vẫn ghi sáu bản
``number_significance_*.json`` (348 KB mỗi lượt) mà trang tổng quan chỉ đọc bản CSV. Nay quét MỌI thư mục
có bảng CSV dưới ``data/stats``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from stats import advanced_stats, significance_stats, statistical_matrices

ROOT = Path(__file__).resolve().parents[2]
STATS = ROOT / "data" / "stats"
ADVANCED = ROOT / "data" / "stats" / "advanced"
SIGNIFICANCE = ROOT / "data" / "stats" / "significance"


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


def test_no_committed_stats_table_anywhere_has_a_json_twin() -> None:
    folders = sorted({path.parent for path in STATS.rglob("*.csv")})
    assert SIGNIFICANCE in folders, "thư mục bảng ý nghĩa thống kê vắng — luật đang quét thiếu"
    assert {str(folder.relative_to(STATS)): json_twins(folder) for folder in folders if json_twins(folder)} == {}


def test_the_significance_writer_writes_only_csv_tables(tmp_path: Path) -> None:
    days = pd.date_range("2026-01-01", periods=40, freq="D")
    rng = pd.Series(range(40 * 27)).mul(37).mod(100).to_numpy().reshape(40, 27)
    two = pd.DataFrame(rng, columns=[f"c{i}" for i in range(27)])
    two.insert(0, "date", days)
    two = two.rename(columns={"c0": "special"})
    sparse = pd.DataFrame(0, index=range(40), columns=list(range(100)))
    for row, values in enumerate(rng):
        for value in values:
            sparse.loc[row, int(value)] += 1
    sparse.insert(0, "date", days)
    written = significance_stats.write_outputs(two, sparse, tmp_path, [30])
    names = sorted(path.name for path in tmp_path.iterdir())
    assert names == sorted(path.name for path in written)
    assert json_twins(tmp_path) == []
    assert "number_significance_loto_30d.csv" in names and "global_diagnostics.json" in names
