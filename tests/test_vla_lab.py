"""Phòng thử thách mô hình xác suất: không nhìn trước, đúng công thức, có độ nhạy."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

import bridge_rules
from vla.backtest import evaluator, walk_forward
from vla.backtest.synthetic import synthetic_history
from vla.features.engineer import (
    FeatureParams,
    History,
    build_features,
    gap_zscore,
    targets,
)
from vla.models.bayesian_lgb import (
    BayesianLGBModel,
    Calibrator,
    ConstantModel,
    DirichletPrior,
    ModelConfig,
    row_logloss,
)

PARAMS = FeatureParams(community_every=60)


def _perturb_after(history: History, t: int, seed: int) -> History:
    """Thay mọi kỳ SAU ``t`` bằng kỳ ngẫu nhiên khác hẳn."""
    other = synthetic_history(len(history), seed, loto_signal=0.0, de_signal=0.0)
    values = history.values.copy()
    digits = history.digits.copy()
    values[t + 1 :] = other.values[t + 1 :]
    digits[t + 1 :] = other.digits[t + 1 :]
    return History(history.dates, digits, values)


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_features_never_look_at_the_draw_they_predict(mode: str) -> None:
    history = synthetic_history(240, seed=3)
    t = 150
    before = build_features(history, mode, PARAMS)
    after = build_features(_perturb_after(history, t, seed=99), mode, PARAMS)
    assert before.names == after.names
    for k, name in enumerate(before.names):
        assert np.array_equal(before.X[: t + 1, :, k], after.X[: t + 1, :, k]), name
    # Và phép kiểm không rỗng: đổi tương lai thì hàng tương lai phải đổi.
    assert not np.array_equal(before.X[t + 1 :], after.X[t + 1 :])


def test_the_label_of_row_t_is_the_draw_after_t() -> None:
    history = synthetic_history(30, seed=4)
    for mode in ("loto", "de"):
        y = targets(history, mode)
        assert np.array_equal(y[:-1], history.hits(mode)[1:].astype(np.float32))
        assert np.isnan(y[-1]).all()


def test_gap_zscore_shrinks_toward_the_geometric_cycle_and_learns_completed_cycles() -> None:
    hit = np.zeros((7, 1), dtype=bool)
    hit[[0, 2, 6], 0] = True  # chu kỳ hoàn tất: 2 (kỳ 0→2) và 4 (kỳ 2→6)
    base = np.full(7, 0.5)
    z = gap_zscore(hit, base, prior_cycles=1.0)
    # Kỳ 6: hai chu kỳ thật (2, 4) + một chu kỳ ảo mean 2, var 2 → mean 8/3.
    mean = (2 + 4 + 2) / 3
    second = (4 + 16 + (2 + 4)) / 3
    assert z[6, 0] == pytest.approx((0 - mean) / np.sqrt(second - mean**2))
    # Kỳ 5: gan 3, chỉ có chu kỳ 2 + chu kỳ ảo.
    mean5, second5 = (2 + 2) / 2, (4 + 6) / 2
    assert z[5, 0] == pytest.approx((3 - mean5) / np.sqrt(second5 - mean5**2))


def test_bridge_counts_agree_with_the_reference_verified_bridge_engine() -> None:
    history = synthetic_history(80, seed=5, loto_signal=0.0, de_signal=0.0)
    feats = build_features(history, "loto", PARAMS)
    found = bridge_rules.find("loto", history.digits, history.values, count=3)["bridges"]
    expected = np.zeros(100)
    for b in found:
        n1 = int(b["number"])
        n2 = 10 * (n1 % 10) + n1 // 10
        expected[n1] += 1
        if n2 != n1:
            expected[n2] += 1
    assert expected.sum() > 0
    assert np.array_equal(feats.column("bridge_count")[-1], expected)


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_dirichlet_prior_is_the_posterior_predictive(mode: str) -> None:
    hit = np.zeros((3, 100), dtype=bool)
    hit[0, 5] = hit[1, 5] = hit[2, 7] = True
    prior = DirichletPrior(mode, half_life=np.inf, alpha=50.0).matrix(hit)
    if mode == "de":
        assert prior[2, 5] == pytest.approx((0.5 + 2) / (50 + 3))
        assert prior.sum(axis=1) == pytest.approx(np.ones(3))
    else:
        mu0 = 3 / 300
        assert prior[2, 5] == pytest.approx((50 * mu0 + 2) / (50 + 3))
        assert prior[2, 0] == pytest.approx((50 * mu0) / (50 + 3))


def test_calibration_repairs_an_overconfident_forecast() -> None:
    rng = np.random.default_rng(0)
    true = rng.uniform(0.1, 0.4, size=(4000, 1))
    y = (rng.random(true.shape) < true).astype(float)
    sharp = 1 / (1 + np.exp(-3 * np.log(true / (1 - true))))  # nhọn gấp 3 lần
    cal = Calibrator("platt").fit(sharp[:2000], y[:2000])
    fixed = cal.transform(sharp[2000:])
    before = row_logloss("loto", sharp[2000:], y[2000:]).mean()
    after = row_logloss("loto", fixed, y[2000:]).mean()
    assert after < before - 0.02


class _Spy:
    calls: list[tuple[int, int]] = []

    def fit(self, X, hit, rows):
        self.last_label = int(rows.max()) + 1 if len(rows) else -1
        return self

    def predict(self, X, hit, rows):
        _Spy.calls.append((self.last_label, int(rows.min()) + 1))
        return np.full((len(rows), 100), 0.2)


def test_walk_forward_never_trains_on_a_draw_it_scores() -> None:
    _Spy.calls = []
    hit = np.zeros((300, 100), dtype=bool)
    walk_forward.run(_Spy, np.zeros((300, 100, 1)), hit, 100, 299, refit_every=40)
    assert len(_Spy.calls) == 5
    for last_label, first_scored in _Spy.calls:
        assert last_label == first_scored - 1


def test_the_model_finds_a_planted_special_prize_signal() -> None:
    """Công cụ đo không mù: Đặc Biệt kỳ sau = kỳ trước + 1 với xác suất 15%."""
    history = synthetic_history(1300, seed=11, loto_signal=0.0, de_signal=0.15)
    feats = build_features(history, "de", FeatureParams())
    hit = history.hits("de")
    T = len(history)
    model = lambda: BayesianLGBModel("de", replace(ModelConfig(), threads=2))  # noqa: E731
    res = walk_forward.run(model, feats.X, hit, T - 300, T - 1, refit_every=150)
    report = evaluator.evaluate("de", res.probs, history.counts[res.targets], history.special[res.targets],
                                np.full(res.probs.shape, 0.01))
    assert report["logloss_skill"] > 0.02
    assert report["vs_reference"]["z"] > 3


def test_on_pure_noise_the_model_does_not_invent_skill() -> None:
    history = synthetic_history(900, seed=12, loto_signal=0.0, de_signal=0.0)
    feats = build_features(history, "de", FeatureParams())
    hit = history.hits("de")
    T = len(history)
    res = walk_forward.run(lambda: BayesianLGBModel("de"), feats.X, hit, T - 200, T - 1, refit_every=100)
    assert np.allclose(res.probs.sum(axis=1), 1.0)
    report = evaluator.evaluate("de", res.probs, history.counts[res.targets], history.special[res.targets],
                                np.full(res.probs.shape, 0.01))
    # Không "phát hiện" kỹ năng giả, và dừng sớm + hiệu chỉnh giữ thiệt hại nhỏ.
    assert report["vs_reference"]["z"] < 2
    assert report["logloss_skill"] > -0.005


def test_scoring_rules_match_hand_computation() -> None:
    p = np.full((1, 100), 0.01)
    p[0, 3] = 0.02
    hits = np.zeros((1, 100))
    hits[0, 3] = 1
    q = p / p.sum()
    assert evaluator.daily_logloss("de", p, hits)[0] == pytest.approx(-np.log(q[0, 3]))
    assert evaluator.daily_brier("de", p, hits)[0] == pytest.approx(((q - hits) ** 2).sum())
    pl = np.full((1, 100), 0.25)
    assert evaluator.daily_logloss("loto", pl, hits)[0] == pytest.approx(
        -(np.log(0.25) + 99 * np.log(0.75)) / 100
    )


def test_top_k_breaks_ties_by_the_smaller_number() -> None:
    p = np.array([[0.1, 0.3, 0.3, 0.2]])
    assert evaluator.top_k(p, 3).tolist() == [[1, 2, 3]]


def test_roi_follows_the_payout_rules() -> None:
    pay = evaluator.Payout()
    p = np.zeros((2, 100))
    p[:, 7] = 0.9
    p[:, 8] = 0.8
    counts = np.zeros((2, 100), dtype=int)
    counts[0, 7] = 2  # hai nháy
    special = np.array([8, 1])
    lo = evaluator.roi_top_k("loto", p, counts, special, 2, pay)
    assert lo["stake"] == 2 * 2 * 23 and lo["return"] == 2 * 80
    de = evaluator.roi_top_k("de", p, counts, special, 2, pay)
    assert de["stake"] == 4 and de["return"] == 70


def test_a_calibrated_base_rate_never_places_a_positive_ev_bet() -> None:
    """Ở đúng tỉ lệ nền, lô hoàn 0,94 và Đặc Biệt 0,70: không con nào đáng đánh."""
    pay = evaluator.Payout()
    counts = np.zeros((5, 100), dtype=int)
    special = np.zeros(5, dtype=int)
    lo = evaluator.roi_positive_ev("loto", np.full((5, 100), 0.2365), counts, special, pay)
    de = evaluator.roi_positive_ev("de", np.full((5, 100), 0.01), counts, special, pay)
    assert lo["bets"] == 0 and de["bets"] == 0
    hot = np.full((5, 100), 0.2365)
    hot[:, 4] = 0.30  # vượt ngưỡng 80·E[nháy] > 23
    assert evaluator.roi_positive_ev("loto", hot, counts, special, pay)["bets"] == 5


def test_constant_model_is_the_skill_zero_reference() -> None:
    hit = np.zeros((10, 100), dtype=bool)
    hit[:, :20] = True
    model = ConstantModel("loto").fit(None, hit, np.arange(8))
    assert np.allclose(model.predict(None, hit, np.arange(3)), 0.2)
