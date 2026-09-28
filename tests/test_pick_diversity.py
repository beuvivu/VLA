"""Top LOTO không được dồn quá ``MAX_PER_TAIL`` con vào cùng một đuôi.

Ngày 28-09-2026 cả 10 con LOTO công bố đều đuôi 4 — mười con gần như là một
lần đặt. Phép kiểm dựng lại đúng vector xác suất của hôm ấy (đọc từ artifact
đã commit) cùng các vector dựng sẵn.
"""

from __future__ import annotations

import subprocess
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import pick_diversity as pdv
from modeling.bundle import build_picks
from predict_nextday_2d import top_frames

ROOT = Path(__file__).resolve().parents[1]


def _tail_counts(numbers) -> list[int]:
    return np.bincount([int(n) % 10 for n in numbers], minlength=10).tolist()


def _clustered() -> np.ndarray:
    """Mười con đuôi 4 cao nhất, rồi mọi con khác thấp dần."""
    probs = np.linspace(0.20, 0.10, 100)
    probs[4::10] = np.linspace(0.30, 0.25, 10)
    return probs


def test_the_cap_keeps_probability_order_within_the_limit() -> None:
    order = pdv.diversified_order(_clustered(), 10)
    assert order[:3] == [4, 14, 24], "ba con đuôi 4 đầu tiên vẫn đứng đầu"
    assert max(_tail_counts(order)) <= pdv.MAX_PER_TAIL
    assert len(set(order)) == 10


def test_without_clustering_the_order_is_the_pure_probability_order() -> None:
    rng = np.random.default_rng(3)
    probs = rng.random(100)
    probs[[1, 12, 23, 34, 45, 56, 67, 78, 89, 90]] += 5  # mười đuôi khác nhau
    pure = list(np.lexsort((np.arange(100), -probs))[:10])
    assert pdv.diversified_order(probs, 10) == [int(n) for n in pure]


def test_ties_break_by_the_smaller_number_like_build_picks() -> None:
    assert pdv.diversified_order(np.full(100, 0.2), 4) == [0, 1, 2, 3]


def test_a_list_longer_than_the_cap_allows_is_filled_in_probability_order() -> None:
    order = pdv.diversified_order(_clustered(), 35, max_per_tail=3)
    assert len(order) == len(set(order)) == 35


def test_a_nonpositive_cap_is_rejected() -> None:
    with pytest.raises(ValueError):
        pdv.diversified_order(_clustered(), 10, max_per_tail=0)


def test_the_home_page_picks_respect_the_cap() -> None:
    picks = build_picks(
        _clustered(), baseline=0.2377, gaps=np.zeros(100, int), gan_threshold=20,
        reasons={}, top_k=10, max_per_tail=pdv.MAX_PER_TAIL,
    )
    assert max(_tail_counts(p.number for p in picks)) <= pdv.MAX_PER_TAIL
    pure = build_picks(
        _clustered(), baseline=0.2377, gaps=np.zeros(100, int), gan_threshold=20,
        reasons={}, top_k=10,
    )
    assert _tail_counts(p.number for p in pure)[4] == 10, "không giới hạn thì giữ hành vi cũ"


def test_the_published_top_files_respect_the_cap_on_the_real_28_09_vector() -> None:
    """Chính vector xác suất đã công bố cho 28-09-2026 (10/10 con đuôi 4)."""
    commit = subprocess.run(
        ["git", "log", "--format=%H", "--diff-filter=A", "-1", "--",
         "data/predict/predict_next_loto_all_2026-09-28.csv"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not commit:
        pytest.skip("không có lịch sử git của artifact 28-09-2026")
    text = subprocess.run(
        ["git", "show", f"{commit}:data/predict/predict_next_loto_all_2026-09-28.csv"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    df_all = pd.read_csv(StringIO(text)).sort_values("prob", ascending=False).reset_index(drop=True)
    assert _tail_counts(df_all["number"].head(10))[4] == 10, "mẫu phải đúng là cụm đuôi 4"

    frames = top_frames(df_all, "loto")
    for n, frame in frames.items():
        assert len(frame) == n
        assert max(_tail_counts(frame["number"])) <= pdv.MAX_PER_TAIL, n
        assert frame["prob"].is_monotonic_decreasing, "danh sách vẫn xếp theo xác suất"
    assert int(frames[10]["number"].iloc[0]) == int(df_all["number"].iloc[0])
    de = top_frames(df_all, "de")
    assert de[10]["number"].tolist() == df_all["number"].head(10).tolist(), "Đặc Biệt giữ nguyên"
