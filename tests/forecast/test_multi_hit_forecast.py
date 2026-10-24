"""Mô hình Lô VIP: dự báo kỳ SAU từ kinh nghiệm cầu kèo và cầu hai nháy, không nhìn trước, in đúng.

Yêu cầu 15-10-2026: trang phải là phỏng đoán cho kỳ hôm sau dựa trên dữ liệu và kinh nghiệm cầu
kèo, không phải thống kê con đã về hôm nay. Các phép kiểm dưới đây ghim từng mắt xích: cầu hai nháy
đếm khớp trang soi cầu hai nháy, đặc trưng chỉ đọc kỳ đã quay, mỗi khối walk-forward chấm bằng mô
hình chưa thấy nó, xác suất in ra hiệu chỉnh chỉ bằng các khối trước, và lý do in đúng tín hiệu.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from soi_cau import bridge_rules
from forecast import multi_hit_forecast as mf
from forecast import multi_hit_vip as m
from soi_cau.position_bridges import load_draws

ROOT = Path(__file__).resolve().parents[2]
PLANTED = (7, 38, 68)
SMALL = mf.ForecastConfig(warmup=40, refit=40, min_history_days=20)


@pytest.fixture(scope="module")
def planted_table() -> mf.Table:
    return mf.build_table(*mf.mock_raw_history(200, seed=2026, planted=PLANTED), SMALL)


def _digits(history):
    return load_draws(history[0])


@pytest.mark.parametrize("t", [62, 70, 79])
def test_the_bridge_features_count_what_the_bridge_pages_find(t) -> None:
    """Số cầu hai nháy (≥ 2 kỳ) và cầu LOTO (≥ 3 kỳ, báo cả số lộn) đúng như ``bridge_rules.find``."""
    history = mf.mock_raw_history(80, seed=12)
    _, digits, values = _digits(history)
    feats = mf.bridge_features(digits, values)
    hai = bridge_rules.find("hai-nhay", digits[: t + 1], values[: t + 1], count=2)
    expected = np.zeros(100, dtype=int)
    for b in hai["bridges"]:
        expected[int(b["number"])] += 1
    assert hai["bridges"] and np.array_equal(feats["cau_hai_nhay"][t], expected)
    loto = bridge_rules.find("loto", digits[: t + 1], values[: t + 1], count=3)
    expected = np.zeros(100, dtype=int)
    for b in loto["bridges"]:
        n = int(b["number"])
        expected[n] += 1
        if n % 10 != n // 10:
            expected[10 * (n % 10) + n // 10] += 1
    assert loto["bridges"] and np.array_equal(feats["cau_loto"][t], expected)
    assert feats["cau_hai_nhay_dai"][t].max() == max(b["streak"] for b in hai["bridges"])


def test_every_row_reads_only_draws_already_drawn() -> None:
    """Sửa kỳ k chỉ được đổi đặc trưng của kỳ neo ≥ k và nhãn của kỳ neo k − 1."""
    history = mf.mock_raw_history(90, seed=4)
    raw, two = (frame.copy() for frame in history)
    k = 70
    for col in ("special", "prize1", "prize7_1", "prize7_2"):
        raw.loc[k, col] = (int(raw.loc[k, col]) + 37) % (10 ** len(str(int(raw[col].max()))))
        two.loc[k, col] = int(raw.loc[k, col]) % 100
    a, b = mf.build_table(*history, SMALL), mf.build_table(raw, two, SMALL)
    row = int(np.flatnonzero(a.anchors == k)[0])
    assert np.array_equal(a.X[:row], b.X[:row])
    assert not np.array_equal(a.X[row], b.X[row])
    assert np.array_equal(a.y[: row - 1], b.y[: row - 1], equal_nan=True)


def test_the_label_is_the_next_draw_coming_twice(planted_table) -> None:
    t = planted_table
    for a in (0, 10, len(t.anchors) - 2):
        assert np.array_equal(t.y[a], (t.counts[t.anchors[a] + 1] >= 2).astype(float))
    assert np.isnan(t.y[-1]).all() and t.anchors[-1] == len(t.counts) - 1
    assert t.target_date == (pd.Timestamp(t.dates[-1]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def test_the_forecast_skips_registered_non_draw_days() -> None:
    """Dữ liệu đến 15-02 mà 16–19-02 nghỉ Tết: kỳ được dự báo là 20-02, không phải một kỳ không có."""
    tet = frozenset({"2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19"})
    assert mf.next_draw_date("2026-02-15", tet) == "2026-02-20"
    assert mf.next_draw_date("2026-02-14", tet) == "2026-02-15"
    history = mf.mock_raw_history(80, seed=4)           # 01-01 → 21-03-2026
    last = history[1]["date"].iloc[-1]
    closed = frozenset({(pd.Timestamp(last) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")})
    table = mf.build_table(*history, SMALL, closed=closed)
    assert table.target_date == (pd.Timestamp(last) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")


def test_each_block_is_scored_by_a_model_that_never_saw_it(planted_table, monkeypatch) -> None:
    seen = []
    real_fit = mf.fit

    def spy(X, y):
        seen.append(len(X))
        return real_fit(X, y)

    monkeypatch.setattr(mf, "fit", spy)
    wf = mf.walk_forward(planted_table, SMALL)
    assert seen == [b["start"] for b in wf.blocks] == list(range(SMALL.warmup, len(planted_table.anchors),
                                                                 SMALL.refit))
    assert (wf.rows >= SMALL.warmup).all() and wf.rows[-1] == len(planted_table.anchors) - 2
    for j, r in enumerate(wf.rows):
        assert wf.hits[j] == int(planted_table.y[r, wf.picks[j]].sum())


@pytest.mark.parametrize("n", [130, 141])
def test_the_published_picks_are_the_ones_scored_when_the_draw_arrives(n) -> None:
    """Năm con công bố hôm nay (kỳ neo cuối) phải đúng là năm con walk-forward chấm khi kỳ ấy có kết
    quả, cùng xác suất đã in — kể cả khi kỳ neo cuối mở đầu một khối mới (n = 141)."""
    raw, two = mf.mock_raw_history(n + 1, seed=21, planted=PLANTED)
    today = mf.walk_forward(mf.build_table(raw.iloc[:n], two.iloc[:n], SMALL), SMALL)
    tomorrow_table = mf.build_table(raw, two, SMALL)
    tomorrow = mf.walk_forward(tomorrow_table, SMALL)
    row = int(np.flatnonzero(tomorrow.rows == len(tomorrow_table.anchors) - 2)[0])
    assert list(tomorrow.picks[row]) == list(today.forecast.picks)
    assert np.allclose(tomorrow.printed[row], today.forecast.printed)


def test_the_forecast_row_uses_the_real_next_draw_date() -> None:
    """Kỳ tới sau ngày nghỉ: đặc trưng cùng thứ / từ đầu tháng / đầu năm tính theo ngày quay thật."""
    from ml import cau_keo_ml as ck

    raw, two = mf.mock_raw_history(80, seed=4)
    last = pd.Timestamp(two["date"].iloc[-1])
    closed = frozenset((last + pd.Timedelta(days=d)).strftime("%Y-%m-%d") for d in (1, 2, 3))
    table = mf.build_table(raw, two, SMALL, closed=closed)
    target = (last + pd.Timedelta(days=4)).strftime("%Y-%m-%d")
    assert table.target_date == target
    ck_cfg = ck.CauKeoConfig(min_history_days=SMALL.min_history_days, window_days=10**7)
    frame, _ = ck.build_cau_keo_feature_frame("loto", include_target=False, config=ck_cfg, raw=raw, two=two,
                                              next_date=target)
    assert frame["predict_for_date"].iloc[0] == target
    assert int(frame["weekday_next"].iloc[0]) == pd.Timestamp(target).weekday()
    j = mf.FEATURES.index("same_weekday_freq_364")
    assert np.array_equal(table.X[-1, :, j], frame["same_weekday_freq_364"].to_numpy(dtype=float))
    naive, _ = ck.build_cau_keo_feature_frame("loto", include_target=False, config=ck_cfg, raw=raw, two=two)
    assert not np.array_equal(naive["same_weekday_freq_364"].to_numpy(), frame["same_weekday_freq_364"].to_numpy())
    with pytest.raises(ValueError, match="next_date"):
        ck.build_cau_keo_feature_frame("loto", include_target=True, config=ck_cfg, raw=raw, two=two,
                                       next_date=target)


def test_the_printed_rate_is_calibrated_only_on_earlier_blocks(planted_table, monkeypatch) -> None:
    sizes = []
    real = mf.Calibrator

    class Spy(real):
        def __init__(self, scores, hits):
            sizes.append(scores.size)
            super().__init__(scores, hits)

    monkeypatch.setattr(mf, "Calibrator", Spy)
    wf = mf.walk_forward(planted_table, SMALL)
    k = SMALL.top_k
    blocks = [b["start"] for b in wf.blocks]
    assert sizes == [k * (s - blocks[0]) for s in blocks]
    first = wf.rows < blocks[1]
    assert np.allclose(wf.printed[first], 1 / (1 + np.exp(-wf.scores[first])))   # chưa có gì để hiệu chỉnh


def test_a_planted_signal_is_found_and_the_printed_rate_matches_the_real_one(planted_table) -> None:
    wf = mf.walk_forward(planted_table, SMALL)
    realised = wf.hits.sum() / wf.picks.size
    assert realised > 0.15
    late = wf.rows >= wf.blocks[2]["start"]       # khi đã đủ lượt chọn ngoài mẫu để hiệu chỉnh
    n, rate = wf.picks[late].size, wf.hits[late].sum() / wf.picks[late].size
    assert abs(wf.printed[late].mean() - rate) <= 3 * np.sqrt(rate * (1 - rate) / n)
    assert set(PLANTED) <= set(wf.picks[-1]) | set(wf.picks[-2]) | set(wf.picks[-3])


def test_inner_validation_chooses_regularisation_by_held_out_loss() -> None:
    rng = np.random.default_rng(3)
    X = rng.normal(size=(60, 100, 3))
    y = (X[..., 0] > 1.6).astype(float)              # một đặc trưng quyết định nhãn
    strong = mf.fit(X, y)
    assert strong.C == max(mf.C_GRID) and strong.inner_gain > 0.05
    blind = y.copy()
    blind[48:] = 0                                   # lát thẩm định trong không có ca dương nào
    fallback = mf.fit(X, blind)
    assert (fallback.C, fallback.inner_gain) == (mf.C_GRID[0], 0.0)
    with pytest.raises(ValueError, match="một lớp"):
        mf.fit(X, np.zeros((60, 100)))


def test_every_feature_has_a_reader_facing_reason() -> None:
    for name in mf.FEATURES:
        for value in (0.0, 1.0, 3.0):
            text = mf.reason(name, value, 12, 34)
            assert text is None or isinstance(text, str)
    assert mf.reason("is_bong_prev_special", 1, 89, 34) == "bóng của Đặc Biệt 34"
    assert mf.reason("cau_hai_nhay", 0, 12, 34) is None
    assert mf.reason("cau_hai_nhay", 4, 12, 34) == "4 cầu hai nháy đang chạy"


def test_reasons_are_the_largest_positive_contributions(planted_table) -> None:
    model = mf.fit(planted_table.X[:-1], planted_table.y[:-1])
    x = planted_table.X[-1, PLANTED[0]]
    contrib = model.contributions(x)
    got = mf.reasons(model, x, PLANTED[0], 34, limit=len(mf.FEATURES))
    order = [j for j in np.argsort(-contrib) if contrib[j] > 0]
    texts = [t for t in (mf.reason(mf.FEATURES[j], x[j], PLANTED[0], 34) for j in order) if t]
    assert got == texts and got
    assert mf.reasons(model, x, PLANTED[0], 34) == texts[:2]
    assert (contrib <= 0).any()                     # có đặc trưng kéo xuống: phép kiểm có răng


def test_the_bridge_experience_counts_every_labelled_anchor(planted_table) -> None:
    rows = mf.bridge_experience(planted_table)
    assert sum(r["seen"] for r in rows) == (len(planted_table.anchors) - 1) * 100
    assert sum(r["observed"] for r in rows) == int(np.nansum(planted_table.y))
    assert [r["label"] for r in rows] == [label for *_, label in mf.BRIDGE_BUCKETS]


# --------------------------------------------------------------------------- số đo đã xuất bản


def test_the_published_forecast_is_for_the_draw_after_the_latest() -> None:
    """Năm con trên trang là dự báo cho kỳ SAU kỳ mới nhất, mỗi con có lý do, và 10 kỳ gần nhất chấm
    đúng số nháy thật của sổ kết quả."""
    vip = json.loads((ROOT / "data" / "multi_hit" / "vip.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(ROOT / "data" / "xsmb-2-digits.csv", dtype=str)
    draws, labels = m.draws_from_frame(frame)
    counts = m.counts_matrix(draws)
    assert vip["rule"] == mf.RULE and labels[vip["draws"] - 1] == vip["source_date"]
    assert vip["target_date"] == mf.next_draw_date(vip["source_date"])
    assert len(vip["picks"]) == vip["config"]["top_k"]
    assert all(p["reasons"] for p in vip["picks"])
    assert vip["recent"]
    for row in vip["recent"]:
        t = labels.index(row["date"])
        assert [p["hits"] for p in row["picks"]] == [int(counts[t, int(p["number"])]) for p in row["picks"]]
