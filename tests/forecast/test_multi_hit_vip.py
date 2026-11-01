"""Bộ lọc lô nhiều nháy: không nhìn trước, bắt được tín hiệu cài sẵn, không báo tin cậy giả.

Kết luận đo trên 4 228 kỳ thật (top-5 trúng 2,91%, chọn bừa trên cùng các kỳ 2,91%) nằm ở
``documentation/research/2026-10-08-lo-nhieu-nhay.md``. Các phép kiểm dưới đây ghim các LUẬT
khiến con số ấy đáng tin: đặc trưng chỉ đọc quá khứ, trọng số chọn trên các kỳ trước, và bộ lọc
đủ nhạy để thấy tín hiệu khi tín hiệu có thật.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from forecast import multi_hit_vip as m


def _model(frame, **cfg) -> m.VIPMultiHitModel:
    draws, labels = m.draws_from_frame(frame)
    return m.VIPMultiHitModel(draws, labels, m.VIPConfig(**cfg))


def test_the_base_rate_is_the_binomial_tail() -> None:
    expected = 1 - 0.99**27 - 27 * 0.01 * 0.99**26
    assert m.base_rate() == pytest.approx(expected, rel=1e-12)
    assert m.base_rate() == pytest.approx(0.02975, abs=5e-5)


def test_the_any_multi_chance_counts_every_fair_draw_exactly() -> None:
    """Đếm thẳng mọi kỳ quay của một xổ số tí hon: n con, mỗi kỳ ``per_draw`` lô."""
    from itertools import product

    for n, per_draw, k in ((5, 3, 2), (6, 4, 3), (4, 5, 1), (4, 5, 4)):
        draws = list(product(range(n), repeat=per_draw))
        good = sum(any(d.count(x) >= 2 for x in range(k)) for d in draws)
        assert m.any_multi_chance(k, per_draw, n) == pytest.approx(good / len(draws), rel=1e-12)
    assert m.any_multi_chance(1) == pytest.approx(m.base_rate(), rel=1e-12)
    # Cả 100 con: kỳ có ít nhất một con về hai lần — phần bù của bài toán ngày sinh.
    birthday = np.prod([1 - i / 100 for i in range(m.LOTO_PER_DRAW)])
    assert m.any_multi_chance(100) == pytest.approx(1 - birthday, rel=1e-12)
    assert m.any_multi_chance(5) == pytest.approx(0.1411, abs=1e-4)


def test_random_any_hit_is_the_hypergeometric_zero_complement() -> None:
    from scipy.stats import hypergeom

    n_multi = np.array([0, 1, 3, 7, 13, 95, 100])
    for k in (1, 5, 10):
        expected = 1 - hypergeom.pmf(0, m.N_NUMBERS, n_multi, k)
        assert m.random_any_hit(n_multi, k) == pytest.approx(expected, abs=1e-12)


def test_counts_matrix_counts_every_nhay() -> None:
    draw = [5, 5, 5] + list(range(10, 34))
    counts = m.counts_matrix([draw])
    assert counts[0, 5] == 3
    assert counts.sum() == 27


def test_a_draw_s_features_never_read_that_draw_or_later() -> None:
    draws, _ = m.draws_from_frame(m.mock_history(80, seed=3))
    cfg = m.VIPConfig()
    t = 50
    changed = draws.copy()
    changed[t:] = (changed[t:] + 37) % 100
    before = m.build_raw_features(m.counts_matrix(draws), cfg)
    after = m.build_raw_features(m.counts_matrix(changed), cfg)
    assert np.array_equal(before[: t + 1], after[: t + 1])
    # Không rỗng: hàng ngay sau kỳ bị đổi PHẢI thấy sự thay đổi.
    assert not np.array_equal(before[t + 1], after[t + 1])


def test_weights_are_chosen_only_from_the_draws_before() -> None:
    model = _model(m.mock_history(100, seed=4))
    t = model.cfg.first_evaluated + 5
    lure = 17
    model._hits[t, lure] = 10_000          # kỳ t "trúng" khổng lồ với vector trọng số 17
    assert model.select_weights(t) != lure
    assert model.select_weights(t + 1) == lure


def test_rhythm_needs_equal_spacing_and_to_be_due_now() -> None:
    cfg = m.VIPConfig()
    assert m._rhythm([2, 6, 10], 14, cfg) == (3, 4)
    assert m._rhythm([2, 6, 10], 13, cfg) == (0, 0)
    assert m._rhythm([2, 6, 9], 12, cfg) == (0, 0)
    assert m._rhythm([0, 4, 8, 12, 16], 20, cfg) == (5, 4)
    assert m._rhythm([6, 10], 14, cfg) == (0, 0)


def test_co_occurrence_learns_a_lagged_pair() -> None:
    # 11 về kỳ trước thì 77 về 2 nháy kỳ sau. Hai lịch sử giống hệt nhau trừ kỳ cuối: một bản có
    # 11 về 10 nháy, bản kia thay bằng 12. Chỉ phép ghép cặp CÓ ĐỘ TRỄ mới làm co_lift của 77
    # tăng rõ ở bản có 11; ghép cùng kỳ thì chênh lệch chỉ là nhiễu (đo: dưới 0,07).
    rng = np.random.default_rng(9)
    draws = rng.integers(0, 100, size=(300, 27))
    for t in range(1, 300):
        if 11 in draws[t - 1]:
            draws[t, :2] = 77
    with_11 = draws.copy()
    with_11[-1, :10] = 11
    without_11 = draws.copy()
    without_11[-1, :10] = 12
    without_11[-1][without_11[-1] == 11] = 12

    def co_lift_of_77(history: np.ndarray) -> float:
        raw = m.build_raw_features(m.counts_matrix(history), m.VIPConfig())
        return float(raw[-1, 77, m._F["co_lift"]])

    assert co_lift_of_77(with_11) - co_lift_of_77(without_11) > 0.3


def test_a_planted_signal_is_found_and_earns_high_confidence() -> None:
    planted = {7, 38, 68}
    report = _model(m.mock_history(120, seed=2026, planted=tuple(planted))).predict_next()
    assert report.model_level == "High"
    assert report.backtest.p_value < 1e-6
    top = {int(p.number) for p in report.picks}
    assert planted <= top
    best = max(p.probability for p in report.picks if int(p.number) in planted)
    assert best > 2 * report.base


def test_a_fair_history_earns_no_confidence() -> None:
    report = _model(m.mock_history(100, seed=2026)).predict_next()
    assert report.model_level == "Low"
    assert {p.confidence for p in report.picks} == {"Low"}
    for p in report.picks:
        assert abs(p.probability - report.base) < 0.01


def test_weight_grid_is_the_whole_simplex() -> None:
    grid = m.weight_grid(0.1)
    assert grid.shape == (286, 4)
    assert np.allclose(grid.sum(axis=1), 1) and (grid >= 0).all()
    assert len(np.unique(grid.round(9), axis=0)) == 286


@pytest.mark.parametrize("method", ["zscore", "minmax"])
def test_a_constant_feature_carries_no_information(method: str) -> None:
    assert np.array_equal(m.normalise(np.full((2, 100), 3.0), method), np.zeros((2, 100)))


def test_confidence_comes_from_the_test_not_from_a_hand_threshold() -> None:
    assert m.model_confidence(0.005, 1.5) == "High"
    assert m.model_confidence(0.03, 1.2) == "Medium"
    assert m.model_confidence(0.001, 0.8) == "Low"     # "có ý nghĩa" nhưng KÉM nền
    assert m.number_confidence("Low", 0.5, 0.03) == "Low"
    assert m.number_confidence("High", 0.04, 0.03) == "Low"


def test_the_cli_runs_on_mock_data_and_writes_the_report(tmp_path, capsys) -> None:
    out = tmp_path / "vip.json"
    assert m.main(["--mock", "--json", str(out)]) == 0
    assert "BÁO CÁO LÔ NHIỀU NHÁY" in capsys.readouterr().out
    report = json.loads(out.read_text(encoding="utf-8"))
    assert len(report["top"]) == 5
    assert all(0 <= row["xac_suat"] <= 1 for row in report["top"])
    assert sum(report["trong_so"].values()) == pytest.approx(1)


def test_ties_are_broken_the_same_unbiased_way_in_every_path() -> None:
    """Mọi thành phần bằng 0 thì mọi con hoà. Chọn trọng số, backtest và dự báo đều phải phá hoà
    bằng ``rank_order``, không phải thứ tự số: phá theo thứ tự số thì hoà nào cũng chọn 00–04,
    và phép chọn trọng số thưởng cho một chiến lược "chọn 00–04" không ai khai báo."""
    model = _model(m.mock_history(150, seed=11))
    model.components[:] = 0.0
    model._hits, model._auc = model._score_all_weights()
    k = model.cfg.top_k
    zeros = np.zeros(m.N_NUMBERS)
    for t in range(model.cfg.warmup, len(model.draws)):
        expected = model.labels_y[t, m.rank_order(zeros, t)[:k]].sum()
        assert np.all(model._hits[t] == expected), f"kỳ {t}: chọn trọng số xếp hoà khác rank_order"
    picks = [[int(x) for x in row] for row in model.backtest().per_draw["chon"]]
    for t, row in zip(range(model.cfg.first_evaluated, len(model.draws)), picks, strict=True):
        assert row == m.rank_order(zeros, t)[:k].tolist(), f"kỳ {t}: backtest xếp hoà khác rank_order"
    assert len({x for row in picks for x in row}) > 50
    report = model.predict_next()
    assert [int(p.number) for p in report.picks] == m.rank_order(zeros, len(model.draws))[:k].tolist()


def test_until_pins_the_history_a_published_measurement_used(tmp_path) -> None:
    """CSV lịch sử dài thêm mỗi ngày; ``--until`` phải cắt đúng các kỳ tới ngày chốt."""
    frame = m.mock_history(120, seed=12)
    csv = tmp_path / "history.csv"
    frame.to_csv(csv, index=False)
    cutoff = frame["date"].iloc[99]
    out = tmp_path / "vip.json"
    assert m.main(["--csv", str(csv), "--until", cutoff, "--json", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["so_ky_dung"] == 100
    assert report["sau_ky"] == cutoff
    with pytest.raises(ValueError):
        m.until(frame, "1999-01-01")


def test_the_backtest_compares_with_random_picks_on_the_same_draws() -> None:
    """Mỗi kỳ chỉ quay trong 60 con nên tỉ lệ ≥ 2 nháy thật (~4,5%) cao hơn lý thuyết 2,975%. Bộ
    lọc bị ép chọn ngẫu nhiên (mọi thành phần bằng 0, hoà phá bằng hoán vị) thì trúng đúng như
    chọn bừa — so với mức nền lý thuyết nó sẽ trông "hơn nền" ×1,5 và nhận Confidence High."""
    rng = np.random.default_rng(14)
    draws = rng.integers(0, 60, size=(400, m.LOTO_PER_DRAW))
    model = m.VIPMultiHitModel(draws)
    model.components[:] = 0.0
    model._hits, model._auc = model._score_all_weights()
    bt = model.backtest()
    n_multi = model.labels_y[model.cfg.first_evaluated:].sum(axis=1)
    assert bt.random_rate > 0.04 > model.base
    assert bt.expected == pytest.approx(bt.top_k * n_multi.sum() / m.N_NUMBERS)
    assert m.model_confidence(bt.p_value, bt.lift) == "Low"
    assert 0.8 < bt.lift < 1.2
