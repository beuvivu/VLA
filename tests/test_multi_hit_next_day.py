"""Luật lô rơi nhiều nháy: chỉ chọn con vừa về, xếp theo tỉ lệ về ≥ 2 nháy kỳ sau ĐẾM được.

Lỗi được sửa (15-10-2026): bộ lọc VIP chấm "dị thường Poisson" bằng phương sai/trung bình số nháy,
chỉ số ấy cao nhất ở con về thưa nhưng dồn cục, nên con 32 đứng đầu mười kỳ liền khi đang gan
10 → 19 kỳ. Các phép kiểm dưới đây ghim từng mắt xích của luật thay thế trên dữ liệu dựng sẵn, và
ghim trên số đo đã xuất bản rằng không con nào được chọn khi nó không về ở kỳ mới nhất.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import multi_hit_next_day as nd
import multi_hit_vip as m

ROOT = Path(__file__).resolve().parents[1]
PLANTED = (7, 38, 68)


def _counts(frame) -> np.ndarray:
    return m.counts_matrix(m.draws_from_frame(frame)[0])


@pytest.fixture(scope="module")
def planted() -> np.ndarray:
    return _counts(m.mock_history(400, seed=2026, planted=PLANTED))


@pytest.fixture(scope="module")
def fair() -> np.ndarray:
    return _counts(m.mock_history(2000, seed=31))


def test_each_row_reads_only_earlier_draws() -> None:
    """Sửa kỳ t chỉ được đổi ước lượng của các kỳ SAU t; hàng t trở về trước giữ nguyên."""
    counts = _counts(m.mock_history(80, seed=4))
    changed = counts.copy()
    changed[50] = 0
    changed[50, :25] = 1                    # 27 lô, khác hẳn kỳ gốc
    changed[50, 98] = 2
    a, b = nd.estimate(counts), nd.estimate(changed)
    for name in ("prob", "state", "factor", "propensity", "seen", "observed"):
        before, after = getattr(a, name), getattr(b, name)
        assert np.array_equal(before[:51], after[:51]), name
    assert not np.array_equal(a.prob[51], b.prob[51])


def _brute_states(counts: np.ndarray, t: int) -> tuple[np.ndarray, np.ndarray]:
    """Đếm thẳng: mọi cặp (τ, τ + 1) với τ + 1 < t, nhóm theo min(nháy ở τ, 2)."""
    seen, observed = np.zeros(3), np.zeros(3)
    for tau in range(t - 1):
        for i in range(100):
            s = min(int(counts[tau, i]), 2)
            seen[s] += 1
            observed[s] += counts[tau + 1, i] >= 2
    return seen, observed


@pytest.mark.parametrize("t", [1, 2, 3, 17, 40])
def test_the_state_rates_count_every_pair_of_consecutive_draws(t) -> None:
    counts = _counts(m.mock_history(40, seed=12))
    est = nd.estimate(counts)
    seen, observed = _brute_states(counts, t)
    assert np.array_equal(est.seen[t], seen) and np.array_equal(est.observed[t], observed)
    assert est.seen[t].sum() == 100 * max(t - 1, 0)
    assert np.array_equal(est.state[t], np.minimum(counts[t - 1], 2))


def test_the_group_factor_divides_by_the_expectation_of_each_number_s_own_rate(planted) -> None:
    """Không đếm hai lần: con có xu hướng cao cũng hay rơi vào nhóm ≥ 2 nháy. Nhân tỉ lệ thô của nhóm
    với xu hướng riêng thì xác suất in ra vượt xa tỉ lệ trúng thật; chia cho kỳ vọng thì khớp."""
    est = nd.estimate(planted)
    wf = nd.walk_forward(planted, est)
    realised = wf.hits.sum() / wf.hits.size / nd.TOP_K
    assert realised > 0.08                                     # tín hiệu cài sẵn thật sự được bắt
    assert wf.predicted.mean() == pytest.approx(realised, rel=0.15)
    raw = est.observed / np.maximum(est.seen, 1) / est.pooled[:, None]
    naive = np.take_along_axis(
        np.clip(est.pooled[:, None] * est.propensity
                * np.take_along_axis(raw, np.maximum(est.state, 0), axis=1), 0, 1)[wf.rows], wf.picks, axis=1)
    assert naive.mean() > 1.3 * realised


def test_a_fair_history_shrinks_the_own_rates_towards_the_common_level(fair) -> None:
    """Chênh lệch giữa các con chỉ cỡ dao động nhị thức thì xu hướng riêng co gần hết về mức chung."""
    est = nd.estimate(fair)
    t = len(fair)
    raw = est.own_multi[t] / t / est.pooled[t]
    assert np.ptp(est.propensity[t]) < 0.5 * np.ptp(raw)
    assert est.shrink[t] < 0.5


def test_a_planted_number_keeps_its_own_rate(planted) -> None:
    est = nd.estimate(planted)
    t = len(planted)
    assert est.shrink[t] > 0.9
    assert min(est.propensity[t, list(PLANTED)]) > 5 > max(np.delete(est.propensity[t], PLANTED))


def test_only_numbers_that_came_in_the_latest_draw_are_picked(planted) -> None:
    """Con không về ở kỳ mới nhất không được chọn, kể cả con có xác suất cao nhất (con cài sẵn)."""
    est = nd.estimate(planted)
    wf = nd.walk_forward(planted, est)
    came = planted[wf.rows - 1] >= 1
    assert np.take_along_axis(came, wf.picks, axis=1).all()
    # Luật có răng: có những kỳ con xác suất cao nhất KHÔNG về kỳ trước và vì vậy không được chọn.
    best = est.prob[wf.rows].argmax(axis=1)
    skipped = ~came[np.arange(len(best)), best]
    assert skipped.any() and not (wf.picks[skipped] == best[skipped, None]).any()


def test_candidates_are_ranked_by_probability_then_by_the_draw_s_fixed_permutation() -> None:
    counts = np.zeros((3, 100), dtype=int)
    counts[:, :27] = 1                      # mọi kỳ: 00–26 về 1 nháy, không con nào khác biệt
    est = nd.estimate(counts)
    t = 3
    ranked = nd.order(counts, est, t)
    assert set(ranked[:27]) == set(range(27))
    keys = m.tie_keys(t)
    assert list(ranked[:27]) == sorted(range(27), key=lambda i: keys[i])
    assert est.prob[t, ranked[0]] == est.prob[t, ranked[26]]


def test_the_walk_forward_prints_the_probability_of_each_pick(planted) -> None:
    est = nd.estimate(planted)
    wf = nd.walk_forward(planted, est, k=3, warmup=10)
    assert wf.rows[0] == 10 and wf.rows[-1] == len(planted) - 1 and wf.picks.shape == (len(wf.rows), 3)
    for j, t in enumerate(wf.rows):
        assert list(wf.picks[j]) == list(nd.order(planted, est, t)[:3])
        assert wf.hits[j] == int((planted[t, wf.picks[j]] >= 2).sum())
        assert np.allclose(wf.predicted[j], est.prob[t, wf.picks[j]])


# --------------------------------------------------------------------------- số đo đã xuất bản


def test_the_published_picks_all_came_in_the_latest_draw() -> None:
    """Lời phàn nàn 15-10-2026: không con nào trong năm con (và mười kỳ gần nhất) là con không về."""
    vip = json.loads((ROOT / "data" / "multi_hit" / "vip.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(ROOT / "data" / "xsmb-2-digits.csv", dtype=str)
    draws, labels = m.draws_from_frame(frame)
    counts = m.counts_matrix(draws)
    n = vip["draws"]
    assert vip["rule"] == nd.RULE and labels[n - 1] == vip["source_date"]
    assert len(vip["picks"]) == vip["config"]["top_k"]
    for pick in vip["picks"]:
        assert pick["today"] == counts[n - 1, int(pick["number"])] >= 1, pick
    assert vip["recent"]
    for row in vip["recent"]:
        t = labels.index(row["date"])
        for pick in row["picks"]:
            assert counts[t - 1, int(pick["number"])] >= 1, (row["date"], pick)
