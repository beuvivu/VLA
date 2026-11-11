"""`core.table_cuts.cut_ranked`: bản cắt là một phần của đúng bảng đã xếp, không xếp lại (11-11-2026)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.table_cuts import cut_ranked


def _table(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "rule": [f"r{i:04d}" for i in range(n)],
        "passed": np.isin(np.arange(n), [5, 150, 199]),
        "p": rng.permutation(n) / n,          # mọi giá trị khác nhau: dòng p nhỏ nhất nằm rải khắp bảng
    })


def test_the_cut_is_the_head_when_nothing_else_is_asked() -> None:
    table = _table()
    cut = cut_ranked(table, rows=30)
    assert cut["rule"].tolist() == table["rule"].head(30).tolist()
    assert cut.index.tolist() == list(range(30))


def test_flagged_rows_are_kept_however_deep_they_sit() -> None:
    table = _table()
    cut = cut_ranked(table, rows=10, keep="passed")
    assert cut["rule"].tolist() == [*table["rule"].head(10), "r0150", "r0199"]
    assert cut.index.tolist() == list(range(12))


def test_the_smallest_values_are_kept_and_the_reading_order_is_not_changed() -> None:
    table = _table()
    cut = cut_ranked(table, rows=10, smallest="p")
    smallest = set(table.sort_values("p", kind="stable")["rule"].head(10))
    assert smallest <= set(cut["rule"])
    assert set(cut["rule"]) == smallest | set(table["rule"].head(10))
    # Bản cắt giữ thứ tự của bảng: nó là một dãy con, không phải bảng xếp lại theo p.
    assert cut["rule"].tolist() == sorted(cut["rule"])
    assert not cut["p"].is_monotonic_increasing


def test_ties_on_the_smallest_column_resolve_by_table_order() -> None:
    """Nhiều dòng hoà p: giữ các dòng đứng trước trong bảng, để hai máy cho cùng một bản cắt."""
    table = _table()
    table["p"] = 0.5
    cut = cut_ranked(table.iloc[::-1], rows=10, smallest="p")
    assert cut["rule"].tolist() == table["rule"].iloc[::-1].head(10).tolist()


def test_a_value_that_is_not_a_number_is_never_among_the_smallest() -> None:
    """Ô không phải số (bảng đọc lại từ CSV, ô ghi «—») không làm hỏng phép chọn và không được coi là p nhỏ."""
    table = _table()
    table["p"] = table["p"].astype(object)
    table.loc[100:, "p"] = "—"
    cut = cut_ranked(table.iloc[::-1], rows=20, smallest="p")
    kept_deep = set(cut["rule"]) - set(table["rule"].iloc[::-1].head(20))
    numeric = table.head(100).assign(p=lambda t: t["p"].astype(float))
    assert kept_deep == set(numeric.sort_values("p", kind="stable")["rule"].head(20))


def test_an_empty_table_and_a_short_table_come_back_whole() -> None:
    empty = _table().head(0)
    assert cut_ranked(empty, rows=10, keep="passed", smallest="p").equals(empty)
    short = _table(7)
    assert cut_ranked(short, rows=10, keep="passed", smallest="p").equals(short)


def test_the_cut_does_not_touch_the_table_it_was_given() -> None:
    table = _table().iloc[::-1]
    before = table.copy()
    cut_ranked(table, rows=10, keep="passed", smallest="p")
    assert table.equals(before) and table.index.equals(before.index)
