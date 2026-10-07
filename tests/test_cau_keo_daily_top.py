"""Trang trực tiếp hiện 10 số đứng đầu bảng Cầu Kèo — đúng bộ trang chủ hiện,
đúng ngày quay đang diễn ra (yêu cầu 07-10-2026)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

import build_landing_page
import cau_keo_daily_top as daily

ROOT = Path(__file__).resolve().parents[1]


def _table(tmp_path: Path, mode: str, rows: list[tuple[str, str, float]]) -> None:
    path = tmp_path / "ai_ml" / f"cau_keo_{mode}_top20.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"predict_for_date": d, "number_str": n, "cau_score": s, "prob": 0.01} for d, n, s in rows]
    ).to_csv(path, index=False)


def _numbers(path: Path) -> list[str]:
    return list(pd.read_csv(path, dtype={"number": str})["number"])


def test_the_snapshot_is_the_top_ten_by_cau_score_keyed_to_its_target_day(tmp_path: Path) -> None:
    scores = [("2026-10-07", str(n), float(n % 17)) for n in range(20)]
    _table(tmp_path, "de", scores)
    path = daily.write_daily_top(tmp_path, "de")
    assert path == tmp_path / "ai_ml" / "daily" / "cau_keo_de_top10_2026-10-07.csv"
    frame = pd.read_csv(path, dtype={"number": str})
    assert list(frame["rank"]) == list(range(1, 11))
    assert list(frame["cau_score"]) == sorted(frame["cau_score"], reverse=True)
    assert frame["cau_score"].min() >= sorted((s for _, _, s in scores), reverse=True)[9]
    assert all(re.fullmatch(r"\d\d", n) for n in frame["number"]), "số phải đủ hai chữ số"
    assert set(frame["predict_for_date"]) == {"2026-10-07"}


def test_ties_keep_the_order_of_the_table(tmp_path: Path) -> None:
    """Sắp xếp phải ỔN ĐỊNH: số hoà điểm giữ thứ tự trong bảng, để trang chủ và
    trang trực tiếp không thể ra hai top-10 khác nhau từ cùng một bảng."""
    # Đủ 100 dòng như bảng thật: mảng nhỏ được numpy xếp bằng sắp xếp chèn (tình
    # cờ ổn định), nên mẫu ngắn không bắt được quicksort.
    order = [(37 * i + 11) % 100 for i in range(100)]
    rows = [("2026-10-07", f"{n:02d}", 50.0 if k % 3 else 60.0) for k, n in enumerate(order)]
    _table(tmp_path, "loto", rows)
    path = daily.write_daily_top(tmp_path, "loto")
    expected = [f"{n:02d}" for k, n in enumerate(order) if k % 3 == 0][:10]
    assert _numbers(path) == expected


def test_a_table_aimed_at_two_days_is_refused(tmp_path: Path) -> None:
    _table(tmp_path, "de", [("2026-10-07", "01", 9.0), ("2026-10-08", "02", 8.0)])
    with pytest.raises(ValueError, match="nhiều ngày"):
        daily.write_daily_top(tmp_path, "de")


def test_no_table_writes_nothing(tmp_path: Path) -> None:
    assert daily.write_daily_top(tmp_path, "de") is None
    assert not (tmp_path / "ai_ml" / "daily").exists()


def test_the_home_page_ranks_with_the_same_function() -> None:
    """Khối «ngày mai» của trang chủ và trang trực tiếp phải ra cùng bộ số."""
    assert build_landing_page.top_by_cau_score is daily.top_by_cau_score
    source = (ROOT / "src" / "build_landing_page.py").read_text(encoding="utf-8")
    assert '_sort_top(\n        _read_csv(repo_root / "data" / "ai_ml" / "cau_keo_' not in source


def test_the_pipeline_snapshots_after_the_challenger_rewrites_the_table() -> None:
    """Domain challenger ghi đè bảng top20, nên bản chụp phải chạy SAU nó."""
    source = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    assert source.index('"src/cau_keo_domain_challenger.py"') < source.index('"src/cau_keo_daily_top.py"')


def test_the_live_page_reads_the_daily_snapshot() -> None:
    script = (ROOT / "src" / "assets" / "live-predictions.js").read_text(encoding="utf-8")
    assert "/data/ai_ml/daily/" in script
    assert "'cau_keo_' + mode + '_top10_' + date + '.csv'" in script
    assert "predict_next_" not in script
    live = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    assert "đứng đầu bảng Cầu Kèo" in live
    assert "không phải xác suất" in live


def test_old_snapshots_are_pruned_with_the_other_dated_artifacts(tmp_path: Path, monkeypatch) -> None:
    """Mỗi lượt pipeline thêm hai tệp; không dọn thì thư mục phình mãi."""
    import sys

    import cleanup_artifacts

    monkeypatch.setattr(cleanup_artifacts, "update_ledger", lambda data_dir: None)
    pd.DataFrame({"date": ["2026-10-06"]}).to_csv(tmp_path / "xsmb.csv", index=False)
    old = daily.daily_path(tmp_path, "de", "2026-08-01")
    new = daily.daily_path(tmp_path, "loto", "2026-10-07")
    for path in (old, new):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("number\n01\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanup", "--data-dir", str(tmp_path)])
    cleanup_artifacts.main()
    assert not old.exists() and new.exists()
