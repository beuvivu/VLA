from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.conditional_matrices import build_conditional_tables


def _frames(dates: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "special": [10000 + i for i in range(len(dates))],
        }
    )
    sparse = pd.DataFrame(0, index=np.arange(len(dates)), columns=["date", *range(100)])
    sparse["date"] = pd.to_datetime(dates)
    for i in range(len(dates)):
        sparse.loc[i, (10 + i) % 100] = 1
    return raw, sparse


def test_gap_is_not_counted_as_next_day_transition() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-04"])
    de_loto, de_de, loto_loto, diag = build_conditional_tables(raw, sparse, top=500)

    assert diag["exact_next_day_pairs"] == 1
    assert diag["skipped_nonconsecutive_boundaries"] == 1

    # Only 00 on Aug-01 may condition Aug-02. 01 on Aug-02 must not condition
    # Aug-04 because that boundary is two calendar days.
    assert set(de_de["prev_special_2d"].tolist()) == {"00"}
    assert set(de_de["next_special_2d"].tolist()) == {"01"}
    assert set(de_loto["prev_special_2d"].tolist()) == {"00"}
    assert set(loto_loto["prev_loto"].tolist()) == {"10"}


def test_contiguous_history_counts_every_boundary() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"])
    _, de_de, _, diag = build_conditional_tables(raw, sparse, top=500)
    assert diag["exact_next_day_pairs"] == 3
    assert diag["skipped_nonconsecutive_boundaries"] == 0
    assert len(de_de) == 3


def test_raw_sparse_date_axes_must_match() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-03"])
    sparse.loc[2, "date"] = pd.Timestamp("2026-08-04")
    with pytest.raises(ValueError, match="same ordered date axis"):
        build_conditional_tables(raw, sparse)


def test_duplicate_dates_are_rejected() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-03"])
    raw.loc[2, "date"] = pd.Timestamp("2026-08-02")
    with pytest.raises(ValueError, match="duplicates"):
        build_conditional_tables(raw, sparse)


# --- Mức nền, co ngót và đa kiểm (31-10-2026) -------------------------------------------------
#
# Bảng cũ xếp 10 000 ô theo tỉ lệ thô: ô đầu bảng LOTO sau Đặc Biệt in 21/40 = 52,5% trong khi
# mức nền là 23,8%. Các phép kiểm dưới đây dựng lịch sử quay công bằng (và lịch sử cài sẵn một
# quan hệ thật) rồi đòi bảng nói đúng điều lịch sử ấy chứa.


def _fair_frames(
    n_days: int = 4000, *, seed: int = 20261031, plant: tuple[int, int] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lịch sử liên tục ``n_days`` kỳ, 27 lô đều trên 100 số, 2 số cuối ĐB = lô đầu tiên.

    ``plant=(a, b)``: mọi kỳ ngay sau một kỳ có Đặc Biệt đuôi a đều có lô b.
    """
    rng = np.random.default_rng(seed)
    lots = rng.integers(0, 100, size=(n_days, 27))
    if plant is not None:
        a, b = plant
        for t in range(n_days - 1):
            if lots[t, 0] == a:
                lots[t + 1, 1] = b
    dates = pd.date_range("2015-01-01", periods=n_days, freq="D")
    raw = pd.DataFrame({"date": dates, "special": rng.integers(0, 1000, n_days) * 100 + lots[:, 0]})
    counts = np.zeros((n_days, 100), dtype=int)
    for t in range(n_days):
        np.add.at(counts[t], lots[t], 1)
    sparse = pd.DataFrame(counts, columns=list(range(100)))
    sparse.insert(0, "date", dates)
    return raw, sparse


def _bh(p: np.ndarray) -> np.ndarray:
    """BH viết lại độc lập để đối chiếu, không dùng hàm của kho."""
    order = np.argsort(p, kind="stable")
    m = len(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    q_sorted = np.minimum(np.minimum.accumulate(ranked[::-1])[::-1], 1.0)
    out = np.empty(m)
    out[order] = q_sorted
    return out


def test_a_fair_history_puts_no_cell_above_its_baseline() -> None:
    raw, sparse = _fair_frames()
    for table in build_conditional_tables(raw, sparse, top=500)[:3]:
        top = table.iloc[0]
        # Ô đầu bảng vẫn lệch hơn 3 sai số chuẩn nhị thức — đó chính là bẫy của phép chọn
        # trong 10 000 ô, không phải tín hiệu.
        b, n = top["baseline_rate"], top["base_count"]
        assert (top["conditional_rate"] - b) / np.sqrt(b * (1 - b) / n) > 3
        # Nhưng sau co và đa kiểm thì không ô nào khác mức nền.
        assert (table["posterior_rate"] - table["baseline_rate"]).abs().max() < 0.005
        assert table["q_value_fdr"].min() > 0.05


def test_a_planted_dependence_ranks_first_and_passes_fdr() -> None:
    raw, sparse = _fair_frames(plant=(42, 96))
    de_loto = build_conditional_tables(raw, sparse, top=500)[0]
    top = de_loto.iloc[0]
    assert (top["prev_special_2d"], top["next_loto"]) == ("42", "96")
    assert top["conditional_rate"] == 1.0
    assert top["q_value_fdr"] < 0.01
    assert (de_loto["q_value_fdr"] < 0.05).sum() == 1


def test_rows_are_ordered_by_evidence_not_by_raw_rate() -> None:
    raw, sparse = _fair_frames()
    for table in build_conditional_tables(raw, sparse, top=500)[:3]:
        assert table["p_value"].is_monotonic_increasing
        assert not table["conditional_rate"].is_monotonic_decreasing


def test_p_value_is_the_one_sided_binomial_tail_against_the_baseline() -> None:
    from scipy.stats import binom

    raw, sparse = _fair_frames()
    for table in build_conditional_tables(raw, sparse, top=200)[:3]:
        expected = binom.sf(table["count"] - 1, table["base_count"], table["baseline_rate"])
        np.testing.assert_allclose(table["p_value"], expected, rtol=1e-9, atol=0)


def test_fdr_counts_every_tested_cell_not_only_the_written_rows() -> None:
    # Đặc Biệt → Đặc Biệt: mỗi ô trung bình 0,4 lần, phần lớn ô đếm 0. BH phải tính cả ô ấy
    # (p = 1) và cả các ô không được ghi ra: chọn ô nào để in chính là phép đa kiểm.
    raw, sparse = _fair_frames()
    full = build_conditional_tables(raw, sparse, top=10**6)[1]
    short = build_conditional_tables(raw, sparse, top=5)[1]
    tested_rows = full["prev_special_2d"].nunique()
    zeros = 100 * tested_rows - len(full)
    assert zeros > 1000
    p_all = np.concatenate([full["p_value"].to_numpy(), np.ones(zeros)])
    q_all = _bh(p_all)[: len(full)]
    np.testing.assert_allclose(short["q_value_fdr"], q_all[:5], rtol=1e-9)


def test_baseline_is_the_next_day_rate_over_exact_pairs_only() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-04"])
    de_loto, de_de, loto_loto, _ = build_conditional_tables(raw, sparse, top=500)
    # Cặp đúng một ngày duy nhất là 01/08 → 02/08; kỳ 02/08 có lô 11 và Đặc Biệt đuôi 01.
    assert de_loto.loc[0, ["next_loto", "baseline_rate"]].tolist() == ["11", 1.0]
    assert de_de.loc[0, ["next_special_2d", "baseline_rate"]].tolist() == ["01", 1.0]
    assert loto_loto.loc[0, "baseline_rate"] == 1.0


def test_the_reading_note_is_derived_from_the_table() -> None:
    from stats.conditional_reading import reading_note

    fair = build_conditional_tables(*_fair_frames(), top=500)[0]
    planted = build_conditional_tables(*_fair_frames(plant=(42, 96)), top=500)[0]
    assert "Không ô nào khác mức nền" in reading_note(fair)
    assert reading_note(planted).startswith("Xếp theo p tăng dần") and "1 ô khác mức nền" in reading_note(planted)


def test_statistical_matrices_builds_the_same_calendar_safe_tables() -> None:
    from stats.statistical_matrices import _conditional_tables

    # Lịch sử 300 kỳ có một ngày nghỉ: bản đếm theo hàng kề nhau sẽ nối hai kỳ hai bên ngày ấy.
    raw, sparse = _fair_frames(300)
    raw, sparse = raw.drop(index=150).reset_index(drop=True), sparse.drop(index=150).reset_index(drop=True)
    canonical = build_conditional_tables(raw, sparse, top=500)[:3]
    assert all(len(table) > 100 for table in canonical)
    for ours, theirs in zip(_conditional_tables(raw, sparse, top=500), canonical, strict=True):
        pd.testing.assert_frame_equal(ours, theirs)
