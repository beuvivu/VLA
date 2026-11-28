from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.paths import TEMPLATES
from pages import build_docs
from ensemble.hierarchical_pooling import random_effects_posterior
from core.path_models import PathParams
from soi_cau.path_prob import (
    STREAK_BUCKETS,
    PathStats,
    _select_rule_indices,
    _streak_walk,
    fit_paths_with_evidence,
    paths_to_dataframe,
    predict_from_fitted_paths_full,
    prepare_path_history,
    rule_next_probability,
    streak_experience,
)
from core.xsmb_domain import FIELD_WIDTHS

PARAMS = PathParams(lag_max=3, window_days=300, min_trials=60, min_max_streak=3,
                    min_current_streak=3, top_rules_per_lag=100)
COLUMNS = [name for name, _ in FIELD_WIDTHS]
WIDTHS = [width for _, width in FIELD_WIDTHS]
LAST_TWO = [(sum(WIDTHS[:k]) + w - 2, sum(WIDTHS[:k]) + w - 1) for k, w in enumerate(WIDTHS)]


def _history(n_draws: int = 300, *, persist: float = 0.0, momentum: tuple[float, float] | None = None,
             seed: int = 7):
    rng = np.random.default_rng(seed)
    values = np.column_stack([rng.integers(0, 10**w, size=n_draws) for w in WIDTHS]).astype(np.int64)
    kept = np.zeros(len(WIDTHS), dtype=bool)
    count = len(WIDTHS)
    for t in range(1, n_draws):
        for k in range(count):
            chance = persist if momentum is None else momentum[0 if kept[k] else 1]
            kept[k] = rng.random() < chance
            if kept[k]:
                source = k if momentum is not None else (k + 1) % count
                values[t, k] = values[t, k] // 100 * 100 + values[t - 1, source] % 100
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
    totals = hit.sum(axis=0)
    max_streak, current, row_hits, row_trials, row_expected = _streak_walk(
        hit, buckets=buckets, rule_hits=totals
    )
    n = hit.shape[0]
    want_hits = np.zeros((n, buckets), dtype=int)
    want_trials = np.zeros((n, buckets), dtype=int)
    want_expected = np.zeros((n, buckets))
    for r in range(hit.shape[1]):
        run = best = 0
        for t in range(n):
            group = min(run, buckets - 1)
            want_trials[t, group] += 1
            want_hits[t, group] += int(hit[t, r])
            want_expected[t, group] += (totals[r] - run - int(hit[t, r])) / (n - run - 1)
            run = run + 1 if hit[t, r] else 0
            best = max(best, run)
        assert max_streak[r] == best
        assert current[r] == run
    np.testing.assert_array_equal(row_trials, want_trials)
    np.testing.assert_array_equal(row_hits, want_hits)
    np.testing.assert_allclose(row_expected, want_expected)


def test_a_fair_history_pools_every_bridge_to_the_common_rate(fair) -> None:
    stats, raw_by_date, dates, ev = fair
    assert ev.rules == 5671 * PARAMS.lag_max
    assert 0.85 < ev.variance_ratio < 1.15
    assert ev.rule_shrinkage > 0.9
    p_mean = np.array([s.p_mean for s in stats])
    p_post = np.array([s.p_post for s in stats])
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
    for s in stats:
        keep = s.trials / (s.trials + ev.rule_prior_strength)
        want = ev.base_rate + keep * (s.hits / s.trials - ev.base_rate)
        assert s.p_post == pytest.approx(want, rel=1e-12, abs=0)
    assert len({s.trials for s in stats}) > 1
    for s in real:
        assert s.p_post > ev.base_rate + 0.05
        assert s.p_post < s.hits / s.trials

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
    raw_top = planted_ev.streak_hits[-1] / planted_ev.streak_trials[-1]
    assert raw_top > planted_ev.base_rate + 0.02
    assert abs(planted_ev.streak_posterior[-1] - planted_ev.base_rate) < 0.005


def test_a_real_streak_effect_survives_the_rule_quality_adjustment() -> None:
    *_, ev = _fit(*_history(momentum=(0.85, 0.05)))
    assert ev.streak_posterior[-1] > ev.base_rate + 0.01


def _rule(p_post: float, shift: float, *, i: int, j: int) -> PathStats:
    return PathStats(lag=1, i=i, j=j, trials=100, hits=30, p_mean=0.9, max_streak=3,
                     current_streak=3, special_touch=0, special_both=0,
                     p_post=p_post, streak_shift=shift)


def test_branches_average_rule_posteriors_and_only_active_adds_streak_experience() -> None:
    digits = np.zeros(107, dtype=np.uint8)
    digits[[10, 20]] = 4
    day = date(2026, 1, 1)
    stats = [_rule(0.30, 0.10, i=10, j=20), _rule(0.50, 0.10, i=20, j=10)]
    common = dict(stats=stats, raw_by_date={day: digits}, dates=[day], params=PARAMS, mode="loto")
    stable = predict_from_fitted_paths_full(kind="stable", **common).set_index("number")["prob"]
    active = predict_from_fitted_paths_full(kind="active", **common).set_index("number")["prob"]
    assert stable[44] == pytest.approx(0.40)
    assert active[44] == pytest.approx(0.50)
    assert stable.drop(44).nunique() == 1


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
    exp = build_docs._bridge_experience(tmp_path, mode="loto", kind="active", anchor_date="2025-10-27")
    assert exp["rules"] == "17.013"
    assert exp["scope_text"] == "mọi cặp vị trí × độ trễ 1–3"
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
    frame = paths_to_dataframe(stats).head(2).assign(streak_shift=0.0125)
    frame["p_next"] = rule_next_probability(frame, kind="active")
    ui = frame.assign(**{"2025-10-27_num": 12, "2025-10-27_hit": 1, "2025-10-27_is_de": 0})
    picks = pd.DataFrame({"number": [12, 34], "prob": [0.2381, 0.2379], "support_paths_count": [3, 2]})
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(["html", "xml"]))
    out = tmp_path / "soi-path-loto-active.html"
    build_docs._render_page(
        env, out_path=out, title="SOI CẦU", mode="loto", kind="active", other_link=None,
        other_kind_label="", other_mode_label="", index_link="index.html",
        anchor_date="2025-10-27", display_days=1, ui_df=ui, picks_df=picks,
        experience=build_docs._bridge_experience(tmp_path, mode="loto", kind="active",
                                                 anchor_date="2025-10-27"),
    )
    html = out.read_text(encoding="utf-8")
    assert "Kinh nghiệm học từ mọi đường cầu" in html
    assert "không có phần vượt nào" in html
    assert "Dự báo kỳ tới" in html
    want = frame["p_next"].iloc[0] * 100
    assert want == pytest.approx((frame["p_post"] + 0.0125).iloc[0] * 100)
    assert f"<td>{round(want, 2)}</td>" in html
    assert "không phải xác suất đã hiệu chuẩn" not in html


def test_random_effects_pools_fully_about_half_the_time_without_real_differences() -> None:
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
    np.testing.assert_allclose(post[:30], hits[:30] / trials[:30], atol=0.002)


def test_the_page_names_the_configured_scope_and_lags(tmp_path, fair) -> None:
    *_, ev = fair
    payload = _payload(ev, pooled=True) | {"scope": "special_only", "lag_max": 7}
    (tmp_path / "bridge_evidence_de.json").write_text(json.dumps(payload), encoding="utf-8")
    exp = build_docs._bridge_experience(tmp_path, mode="de", kind="stable", anchor_date="2025-10-27")
    assert exp["scope_text"] == "các cặp vị trí trong giải Đặc Biệt × độ trễ 1–7"


def _clustered_null(seed: int):
    rng = np.random.default_rng(seed)
    rate = np.clip(0.24 + rng.normal(0, 0.03, 250), 0.05, 0.9)
    expected = np.array([5000, 1200, 300, 70, 17, 4, 1, 0.3, 0.1])
    trials = rng.poisson(expected[None, :] * rng.lognormal(0, 0.6, (250, 9)))
    return rng.binomial(trials, rate[:, None]), trials


def test_streak_experience_treats_one_draw_as_one_cluster() -> None:
    pooled = [streak_experience(*_clustered_null(seed))[2] == 0.0 for seed in range(60)]
    assert np.mean(pooled) > 0.45


def test_streak_experience_variance_is_the_cluster_sandwich() -> None:
    hits = np.array([[3, 1], [0, 0], [5, 2]])
    trials = np.array([[10, 4], [6, 0], [10, 5]])
    post, base, _ = streak_experience(hits, trials)
    assert base == pytest.approx(11 / 35)
    single = streak_experience(np.array([[2, 0]]), np.array([[9, 0]]))
    assert np.isfinite(single[0]).all()


def test_a_streak_group_seen_in_one_draw_only_pools_to_the_common_rate() -> None:
    rng = np.random.default_rng(5)
    trials = rng.poisson([4000, 900, 200], size=(200, 3))
    hits = rng.binomial(trials, 0.24)
    rare_hits = np.zeros((200, 1), dtype=int)
    rare_trials = np.zeros((200, 1), dtype=int)
    rare_trials[17], rare_hits[17] = 3000, 2700
    post, base, _ = streak_experience(np.hstack([hits, rare_hits]), np.hstack([trials, rare_trials]))
    assert post[-1] == base


def test_evidence_from_another_anchor_is_not_shown(tmp_path, fair) -> None:
    *_, ev = fair
    (tmp_path / "bridge_evidence_loto.json").write_text(json.dumps(_payload(ev, pooled=True)),
                                                       encoding="utf-8")
    assert build_docs._bridge_experience(tmp_path, mode="loto", kind="stable", anchor_date="2025-10-26") == {}
    assert build_docs._bridge_experience(tmp_path, mode="loto", kind="stable", anchor_date="2025-10-27")


def test_the_displayed_rule_probability_is_the_one_the_picks_use() -> None:
    digits = np.zeros(107, dtype=np.uint8)
    digits[[3, 4]] = 7
    day = date(2026, 1, 1)
    rule = _rule(0.02, 0.0, i=3, j=4)
    rule.special_touch = rule.special_both = 1
    frame = paths_to_dataframe([rule])
    shown = rule_next_probability(frame, kind="stable", scope="special_only", bias_special_both=1.5)
    assert shown[0] == pytest.approx(0.03)
    picked = predict_from_fitted_paths_full(
        stats=[rule], raw_by_date={day: digits}, dates=[day], params=PARAMS, kind="stable",
        mode="loto", scope="special_only", bias_special_both=1.5,
    ).set_index("number")["prob"]
    assert picked[77] == pytest.approx(shown[0])


def test_random_effects_centres_q_on_the_inverse_variance_mean() -> None:
    hits = np.array([300.0, 2.0])
    trials = np.array([1000.0, 10.0])
    post, mean, tau2 = random_effects_posterior(hits, trials, variances=np.array([1e-2, 1e-4]))
    assert tau2 == 0.0
    assert mean == pytest.approx(302 / 1010)
    np.testing.assert_allclose(post, mean)


def _benchmark_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "research" / "benchmark_bridge_inference.py"
    spec = importlib.util.spec_from_file_location("benchmark_bridge_inference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _benchmark_part(run: dict, part: int, target: list[int], seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = len(target)
    names = [f"{k}_{v}" for k in ("active", "stable", "ensemble") for v in ("old", "new")]

    def block(base: float) -> dict:
        return {"constant": list(rng.normal(1.0, 0.1, n)),
                "logloss": {k: list(rng.normal(1.0, 0.1, n)) for k in names},
                "sums": {k: list(rng.normal(100 * base, 0.1, n)) for k in names},
                "evidence": [{"variance_ratio": 1.0, "rules_fully_pooled": True, "rule_shrinkage": 0.0,
                              "streak_posterior": [base] * STREAK_BUCKETS, "base_rate": base}] * n}

    return {"run": dict(run), "part": part, "target": target,
            "first_target": f"t{target[0]}", "last_target": f"t{target[-1]}",
            "loto": block(0.2377), "de": block(0.01)}


def test_the_benchmark_merges_only_parts_of_the_same_run() -> None:
    bench = _benchmark_script()
    run = {"last": 6, "parts": 2, "window_days": 2000, "draws": 100, "last_date": "2026-10-15",
           "data_sha256": "data", "code_sha256": "code"}
    expected = [94, 95, 96, 97, 98, 99]
    good = [_benchmark_part(run, 1, [94, 95, 96], 1), _benchmark_part(run, 2, [97, 98, 99], 2)]
    report = bench.merge(list(reversed(good)), run=run, expected_target=expected)
    assert report["loto"]["days"] == 6
    assert report["loto"]["first_target"] == "t94" and report["loto"]["last_target"] == "t99"

    stale = _benchmark_part({**run, "data_sha256": "older"}, 2, [97, 98, 99], 2)
    with pytest.raises(ValueError, match="lượt đo khác"):
        bench.merge([good[0], stale], run=run, expected_target=expected)

    shifted = [_benchmark_part(run, 1, [90, 91, 92], 1), _benchmark_part(run, 2, [93, 94, 95], 2)]
    with pytest.raises(ValueError, match="không trùng"):
        bench.merge(shifted, run=run, expected_target=expected)

    with pytest.raises(ValueError, match="cần đúng các phần"):
        bench.merge([good[0], good[0]], run=run, expected_target=expected)


def test_the_benchmark_identity_covers_every_module_it_runs(tmp_path, monkeypatch) -> None:
    bench = _benchmark_script()
    for rel in ("src/soi_cau/path_prob.py", "src/ensemble/ensemble_utils.py", "src/core/xsmb_domain.py",
                "src/research/vla/backtest.py"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    script = tmp_path / "scripts" / "research" / "benchmark.py"
    script.parent.mkdir(parents=True)
    script.write_text("y = 1\n", encoding="utf-8")
    monkeypatch.setattr(bench, "ROOT", tmp_path)
    monkeypatch.setattr(bench, "SCRIPT", script)
    raw = pd.DataFrame({"date": ["2026-10-14", "2026-10-15"], "db": ["12345", "67890"]})
    base = bench.run_identity(raw, last=2, parts=1)
    for path in [*sorted((tmp_path / "src").rglob("*.py")), script]:
        before = path.read_text(encoding="utf-8")
        path.write_text(before + "# đổi\n", encoding="utf-8")
        assert bench.run_identity(raw, last=2, parts=1) != base, path
        path.write_text(before, encoding="utf-8")
    assert bench.run_identity(raw, last=2, parts=1) == base


def test_the_top_rules_per_lag_break_ties_by_position_not_by_the_cpu() -> None:
    params = PathParams(lag_max=1, window_days=300, min_trials=60, min_max_streak=3,
                        min_current_streak=3, top_rules_per_lag=4)
    n = 40
    p_mean = np.full(n, 0.25)
    hits = np.full(n, 50)
    max_streak = np.full(n, 3)
    current_streak = np.zeros(n, dtype=int)
    p_mean[[30, 7]] = [0.40, 0.35]
    kept = _select_rule_indices(p_mean=p_mean, hits=hits, max_streak=max_streak,
                                current_streak=current_streak, params=params, mode="loto")
    assert kept.tolist() == [30, 7, 0, 1]
    again = _select_rule_indices(p_mean=p_mean.copy(), hits=hits.copy(), max_streak=max_streak.copy(),
                                 current_streak=current_streak.copy(), params=params, mode="loto")
    assert again.tolist() == kept.tolist()
