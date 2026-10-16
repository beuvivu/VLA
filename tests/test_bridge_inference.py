"""Suy luận cầu vị trí bằng Bayes thực nghiệm (``path_prob.BridgeEvidence``).

Mỗi đường cầu nhận xác suất trúng kỳ tới theo kinh nghiệm học từ MỌI cầu: tỉ
lệ chung + phần riêng co theo mức chênh thật giữa các cầu; nhánh "đang chạy"
cộng kinh nghiệm theo độ dài chuỗi. Các phép kiểm ghim cả hai chiều: lịch sử
công bằng thì mọi cầu co về tỉ lệ chung (hết lời nguyền người thắng), lịch sử
có cầu thật thì cầu ấy giữ được phần tỉ lệ riêng.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

import build_docs
from hierarchical_pooling import random_effects_posterior
from path_models import PathParams
from path_prob import (
    STREAK_BUCKETS,
    PathStats,
    _streak_walk,
    fit_paths_with_evidence,
    paths_to_dataframe,
    predict_from_fitted_paths_full,
    prepare_path_history,
)
from xsmb_domain import FIELD_WIDTHS

PARAMS = PathParams(lag_max=3, window_days=240, min_trials=60, min_max_streak=3,
                    min_current_streak=3, top_rules_per_lag=100)
COLUMNS = [name for name, _ in FIELD_WIDTHS]
WIDTHS = [width for _, width in FIELD_WIDTHS]
# Vị trí hai chữ số cuối của từng giải trong dải 107 chữ số.
LAST_TWO = [(sum(WIDTHS[:k]) + w - 2, sum(WIDTHS[:k]) + w - 1) for k, w in enumerate(WIDTHS)]


def _history(n_draws: int = 300, *, persist: float = 0.0, seed: int = 7):
    """Lịch sử giả định; ``persist``: mỗi giải giữ hai số cuối của kỳ trước với xác suất ấy.

    Khi ``persist > 0``, 27 đường cầu (trễ 1, hai chữ số cuối của cùng một giải)
    là cầu THẬT: chúng trúng với xác suất ≈ persist + (1 − persist)·nền.
    """
    rng = np.random.default_rng(seed)
    values = np.column_stack([rng.integers(0, 10**w, size=n_draws) for w in WIDTHS]).astype(np.int64)
    for t in range(1, n_draws):
        for k in range(len(WIDTHS)):
            if rng.random() < persist:
                values[t, k] = values[t, k] // 100 * 100 + values[t - 1, k] % 100
    dates = pd.date_range("2025-01-01", periods=n_draws, freq="D").date
    raw = pd.DataFrame(values, columns=COLUMNS)
    raw.insert(0, "date", dates)
    two = raw.copy()
    two[COLUMNS] = values % 100
    return raw, two


def _fit(raw, two, mode="loto"):
    prepared = prepare_path_history(raw, two)
    return fit_paths_with_evidence(params=PARAMS, mode=mode, prepared=prepared)


@pytest.fixture(scope="module")
def fair():
    return _fit(*_history(persist=0.0))


@pytest.fixture(scope="module")
def planted():
    return _fit(*_history(persist=0.5))


def test_streak_walk_counts_match_brute_force() -> None:
    rng = np.random.default_rng(3)
    hit = rng.random((60, 25)) < 0.45
    buckets = 4
    max_streak, current, exp_hits, exp_trials = _streak_walk(hit, buckets=buckets)
    want_hits = np.zeros(buckets, dtype=int)
    want_trials = np.zeros(buckets, dtype=int)
    for r in range(hit.shape[1]):
        run = best = 0
        for t in range(hit.shape[0]):
            group = min(run, buckets - 1)
            want_trials[group] += 1
            want_hits[group] += int(hit[t, r])
            run = run + 1 if hit[t, r] else 0
            best = max(best, run)
        assert max_streak[r] == best
        assert current[r] == run
    np.testing.assert_array_equal(exp_trials, want_trials)
    np.testing.assert_array_equal(exp_hits, want_hits)


def test_a_fair_history_pools_every_bridge_to_the_common_rate(fair) -> None:
    stats, raw_by_date, dates, ev = fair
    assert ev.rules == 5671 * PARAMS.lag_max
    assert 0.85 < ev.variance_ratio < 1.15
    assert ev.rule_shrinkage > 0.9
    p_mean = np.array([s.p_mean for s in stats])
    p_post = np.array([s.p_post for s in stats])
    # Lời nguyền người thắng: tỉ lệ lịch sử của cầu được chọn cao hơn hẳn tỉ lệ
    # chung, còn hậu nghiệm thì không.
    assert p_mean.mean() - ev.base_rate > 0.02
    assert abs(p_post.mean() - ev.base_rate) < 0.004
    for kind in ("active", "stable"):
        frame = predict_from_fitted_paths_full(stats=stats, raw_by_date=raw_by_date, dates=dates,
                                               params=PARAMS, kind=kind, mode="loto")
        assert abs(frame["prob"].sum() - 100 * ev.base_rate) < 0.3


def test_real_bridges_keep_part_of_their_own_rate(planted) -> None:
    stats, raw_by_date, dates, ev = planted
    assert ev.variance_ratio > 1.2
    assert not ev.rules_fully_pooled
    assert ev.rule_shrinkage < 0.95
    real = [s for s in stats if s.lag == 1 and (s.i, s.j) in LAST_TWO]
    assert len(real) >= 20
    for s in real:
        assert s.p_post > ev.base_rate + 0.05
        assert s.p_post < s.hits / s.trials  # vẫn co một phần về tỉ lệ chung

    # Con mà cầu thật báo cho kỳ tới: hai số cuối của các giải ở kỳ mới nhất.
    last = raw_by_date[dates[-1]]
    fired = {int(10 * last[i] + last[j]) for i, j in LAST_TWO}
    frame = predict_from_fitted_paths_full(stats=stats, raw_by_date=raw_by_date, dates=dates,
                                           params=PARAMS, kind="stable", mode="loto")
    prob = frame.set_index("number")["prob"]
    others = [n for n in range(100) if n not in fired]
    assert prob[list(fired)].mean() > prob[others].mean() + 0.02


def test_streak_experience_follows_the_data(fair, planted) -> None:
    *_, fair_ev = fair
    *_, planted_ev = planted
    assert len(fair_ev.streak_posterior) == STREAK_BUCKETS
    fair_post = np.array(fair_ev.streak_posterior)
    assert np.abs(fair_post - fair_ev.base_rate).max() < 0.01
    # Cầu thật trúng thành chuỗi dài, nên "đang chạy lâu" có nghĩa ở lịch sử ấy.
    assert planted_ev.streak_posterior[-1] > planted_ev.base_rate + 0.01


def _rule(p_post: float, shift: float, *, i: int, j: int) -> PathStats:
    return PathStats(lag=1, i=i, j=j, trials=100, hits=30, p_mean=0.9, max_streak=3,
                     current_streak=3, special_touch=0, special_both=0,
                     p_post=p_post, streak_shift=shift)


def test_branches_average_rule_posteriors_and_only_active_adds_streak_experience() -> None:
    digits = np.zeros(107, dtype=np.uint8)
    digits[[10, 20]] = 4  # cả hai cầu cùng báo 44
    day = date(2026, 1, 1)
    stats = [_rule(0.30, 0.10, i=10, j=20), _rule(0.50, 0.10, i=20, j=10)]
    common = dict(stats=stats, raw_by_date={day: digits}, dates=[day], params=PARAMS, mode="loto")
    stable = predict_from_fitted_paths_full(kind="stable", **common).set_index("number")["prob"]
    active = predict_from_fitted_paths_full(kind="active", **common).set_index("number")["prob"]
    assert stable[44] == pytest.approx(0.40)
    assert active[44] == pytest.approx(0.50)
    assert stable.drop(44).nunique() == 1  # con không có cầu nào báo giữ tỉ lệ nền


def test_a_rule_without_a_posterior_is_refused() -> None:
    digits = np.zeros(107, dtype=np.uint8)
    day = date(2026, 1, 1)
    rule = _rule(0.3, 0.0, i=10, j=20)
    rule.p_post = float("nan")
    with pytest.raises(ValueError, match="p_post"):
        predict_from_fitted_paths_full(stats=[rule], raw_by_date={day: digits}, dates=[day],
                                       params=PARAMS, kind="stable", mode="loto")


def _payload(ev, *, pooled: bool) -> dict:
    out = {"anchor_date": "2025-10-27", **ev.as_dict()}
    out["rules_fully_pooled"] = pooled
    out["rule_shrinkage"] = 0.99964 if pooled else 0.75
    return out


@pytest.mark.parametrize("pooled", [True, False])
def test_the_page_states_what_the_measurement_says(tmp_path, fair, pooled) -> None:
    *_, ev = fair
    (tmp_path / "bridge_evidence_loto.json").write_text(json.dumps(_payload(ev, pooled=pooled)),
                                                       encoding="utf-8")
    exp = build_docs._bridge_experience(tmp_path, mode="loto", kind="active")
    assert exp["rules"] == "17.013"
    if pooled:
        assert "không có phần vượt nào" in exp["verdict"]
        assert "giữ" not in exp["verdict"]
    else:
        assert "giữ 25,0% chênh lệch riêng" in exp["verdict"]
        assert "không có phần vượt" not in exp["verdict"]
    shown = [row for row in exp["streak_rows"]]
    assert [row["label"] for row in shown][-1] == f"{STREAK_BUCKETS - 1}+"
    assert len(shown) == sum(1 for n in ev.streak_trials if n)
    first = shown[0]
    assert first["post"] == f"{ev.streak_posterior[0] * 100:.2f}".replace(".", ",")


def test_the_soi_path_page_prints_the_forecast_and_the_experience(tmp_path, fair) -> None:
    stats, *_, ev = fair
    (tmp_path / "bridge_evidence_loto.json").write_text(json.dumps(_payload(ev, pooled=True)),
                                                       encoding="utf-8")
    frame = paths_to_dataframe(stats).head(2)
    ui = frame.assign(**{"2025-10-27_num": 12, "2025-10-27_hit": 1, "2025-10-27_is_de": 0})
    picks = pd.DataFrame({"number": [12, 34], "prob": [0.2381, 0.2379], "support_paths_count": [3, 2]})
    env = Environment(loader=FileSystemLoader(str(build_docs.Path(build_docs.__file__).parent / "templates")),
                      autoescape=select_autoescape(["html", "xml"]))
    out = tmp_path / "soi-path-loto-active.html"
    build_docs._render_page(
        env, out_path=out, title="SOI CẦU", mode="loto", kind="active", other_link=None,
        other_kind_label="", other_mode_label="", index_link="index.html",
        anchor_date="2025-10-27", display_days=1, ui_df=ui, picks_df=picks,
        experience=build_docs._bridge_experience(tmp_path, mode="loto", kind="active"),
    )
    html = out.read_text(encoding="utf-8")
    assert "Kinh nghiệm học từ mọi đường cầu" in html
    assert "không có phần vượt nào" in html
    assert "Dự báo kỳ tới" in html
    want = (frame["p_post"] + frame["streak_shift"]).iloc[0] * 100
    assert f"<td>{round(want, 2)}</td>" in html
    assert "không phải xác suất đã hiệu chuẩn" not in html


def test_random_effects_pools_fully_about_half_the_time_without_real_differences() -> None:
    """DerSimonian–Laird: không có khác biệt thật thì τ² = 0 khi Q ≤ k − 1 (≈ 54% với k = 20)."""
    rng = np.random.default_rng(11)
    trials = np.full(20, 1000)
    zero = [random_effects_posterior(rng.binomial(trials, 0.3), trials)[2] == 0.0 for _ in range(400)]
    assert 0.45 < np.mean(zero) < 0.65


def test_random_effects_keeps_real_differences_and_gives_empty_groups_the_mean() -> None:
    rng = np.random.default_rng(12)
    true = np.clip(rng.normal(0.3, 0.05, 30), 0.01, 0.99)
    trials = np.append(np.full(30, 20_000), 0)
    hits = np.append(rng.binomial(trials[:30], true), 0)
    post, mean, tau2 = random_effects_posterior(hits, trials)
    assert tau2 == pytest.approx(true.var(), rel=0.5)
    assert post[-1] == mean
    # Nhóm nhiều dữ liệu và khác thật thì gần như giữ nguyên tỉ lệ của mình.
    np.testing.assert_allclose(post[:30], hits[:30] / trials[:30], atol=0.002)
