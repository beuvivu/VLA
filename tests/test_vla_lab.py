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
    """Mô hình hằng số trùng từng giá trị với mốc kỹ năng 0 của bộ chấm."""
    hit = np.zeros((10, 100), dtype=bool)
    hit[:5, :20] = True
    hit[5:, :40] = True
    rows = np.arange(2, 9)
    model = ConstantModel("loto").fit(None, hit, np.arange(2))
    assert np.allclose(model.predict(None, hit, rows), evaluator.cumulative_reference("loto", hit, rows + 1))


def test_the_prior_is_tuned_without_the_early_stopping_block(monkeypatch) -> None:
    """Nhãn của khối dừng sớm không được chạm vào việc chọn (h, α) của tiên nghiệm."""
    seen: list[np.ndarray] = []
    real_fit = DirichletPrior.fit.__func__

    def spy(cls, mode, hit, rows, *args, **kwargs):
        seen.append(np.asarray(rows))
        return real_fit(cls, mode, hit, rows, *args, **kwargs)

    monkeypatch.setattr(DirichletPrior, "fit", classmethod(spy))
    history = synthetic_history(400, seed=13, loto_signal=0.0, de_signal=0.0)
    feats = build_features(history, "de", PARAMS)
    cfg = replace(ModelConfig(), calib_rows=50, valid_share=0.2, threads=2)
    rows = np.arange(len(history) - 1)
    BayesianLGBModel("de", cfg).fit(feats.X, history.hits("de"), rows)
    learn = rows[:-50]
    first_valid = learn[-max(int(len(learn) * 0.2), 10)]
    assert len(seen) == 1
    assert seen[0].max() < first_valid


def test_pmi_treats_missing_evidence_as_no_association() -> None:
    """Cặp chưa từng gặp (và con chưa từng về) phải ra PMI ≈ 0, không phải log N."""
    from vla.features.engineer import _pmi

    left = np.array([0.0, 500.0, 500.0])
    right = np.array([0.0, 500.0, 500.0])
    joint = np.array([[0.0, 0.0, 0.0], [0.0, 500.0, 250.0], [0.0, 250.0, 100.0]])
    pmi = _pmi(joint, left, right, total=1000.0)
    assert abs(pmi[0, 0]) < 1e-12 and abs(pmi[0, 1]) < 1e-12
    assert pmi[1, 2] == pytest.approx(0.0, abs=1e-12)  # 250 = 500·500/1000: độc lập
    assert pmi[1, 1] > 0.6  # 500 so với kỳ vọng 250: gắn kết
    assert pmi[2, 2] < -0.8  # 100 so với kỳ vọng 250: tránh nhau


def test_target_weekday_follows_the_next_recorded_draw_across_a_break() -> None:
    """Qua quãng nghỉ, thứ của kỳ đích là thứ của kỳ quay kế tiếp thật."""
    from vla.features.engineer import weekday_features

    dates = ("2026-02-15", "2026-02-21", "2026-02-22")  # CN → (nghỉ Tết) → T7 → CN
    sin, cos = weekday_features(dates)
    angle = np.arctan2(sin, cos) % (2 * np.pi)
    weekday = np.rint(angle * 7 / (2 * np.pi)).astype(int) % 7
    assert weekday.tolist() == [5, 6, 0]  # thứ Bảy, Chủ Nhật, rồi giả định thứ Hai


def test_the_constant_reference_is_updated_through_each_target_draw() -> None:
    """Mốc LOTO của kỳ đích k là tỉ lệ về qua kỳ 0..k-1, không đông cứng ở đầu khối."""
    hit = np.zeros((6, 100), dtype=bool)
    hit[:3, :10] = True  # kỳ 0..2: 10% con về
    hit[3:, :30] = True  # kỳ 3..5: 30% con về
    ref = evaluator.cumulative_reference("loto", hit, np.array([3, 5]))
    assert ref[0] == pytest.approx(np.full(100, 0.10))
    assert ref[1] == pytest.approx(np.full(100, (0.1 * 3 + 0.3 * 2) / 5))
    assert np.allclose(evaluator.cumulative_reference("de", hit, np.array([4])), 0.01)


def _planted_rates(history: History) -> tuple[float, float]:
    """(tỉ lệ giải bảy thứ nhất = 73 sau kỳ có 37, tỉ lệ Đặc Biệt = kỳ trước + 1)."""
    from xsmb_domain import PRIZE_FIELDS

    seven = PRIZE_FIELDS.index("prize7_1")
    after_37 = np.array([37 in set((history.values[t - 1] % 100).tolist()) for t in range(1, len(history))])
    seventy_three = history.values[1:, seven][after_37] == 73
    plus_one = history.special[1:] == (history.special[:-1] + 1) % 100
    return float(seventy_three.mean()), float(plus_one.mean())


def test_each_power_check_history_plants_only_its_own_signal() -> None:
    from vla.backtest.synthetic import power_history

    loto_73, loto_plus = _planted_rates(power_history("loto", 3000, seed=21))
    de_73, de_plus = _planted_rates(power_history("de", 3000, seed=21))
    # Tín hiệu của chính chế độ có mặt ...
    assert loto_73 > 0.4 and de_plus > 0.12
    # ... còn tín hiệu kia chỉ ở mức ngẫu nhiên (1/100): Đặc Biệt là một giải
    # LOTO, nên cài "Đặc Biệt + 1" vào lịch sử LOTO là thêm một tín hiệu LOTO.
    assert loto_plus < 0.03 and de_73 < 0.03


def test_the_power_check_measures_each_mode_on_its_own_history(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_probability_models.py"
    spec = importlib.util.spec_from_file_location("benchmark_power_check", path)
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)

    made, used = [], []

    class Fake:
        def __init__(self, mode: str) -> None:
            self.planted = mode
            self.counts = self.special = np.zeros((700, 100))

        def __len__(self) -> int:
            return 700

        def hits(self, mode: str) -> np.ndarray:
            return np.zeros((700, 100))

    seeds = []

    def fake_history(mode: str, n: int, seed: int) -> Fake:
        made.append(mode)
        seeds.append(seed)
        return Fake(mode)

    def fake_features(hist: Fake, mode: str) -> SimpleNamespace:
        used.append((hist.planted, mode))
        return SimpleNamespace(X=None)

    monkeypatch.setattr(bench, "power_history", fake_history)
    monkeypatch.setattr(bench, "build_features", fake_features)
    monkeypatch.setattr(bench.walk_forward, "run", lambda *a, **k: SimpleNamespace(probs=None))
    monkeypatch.setattr(bench.evaluator, "cumulative_reference", lambda *a, **k: None)
    monkeypatch.setattr(
        bench.evaluator, "evaluate", lambda *a, **k: {"logloss_skill": 0.0, "vs_reference": {"z": 0.0}, "top_k": {}}
    )
    bench.power_check(50)
    assert sorted(made) == ["de", "loto"]
    assert used == [("loto", "loto"), ("de", "de")]
    # Độ nhạy công bố đo trên lịch sử CHƯA dùng để chọn siêu tham số.
    from vla.backtest.synthetic import TUNING_SEED

    assert TUNING_SEED not in seeds


def _benchmark_module():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_probability_models.py"
    spec = importlib.util.spec_from_file_location("benchmark_recorded", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_recorded_production_comparison_never_mixes_reconstructed_rows() -> None:
    import pandas as pd

    bench = _benchmark_module()
    dates = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]
    exact = "exact_emitted_prediction_artifact"
    book = pd.DataFrame({
        "mode": "loto",
        "target_date": dates,
        "logloss": [0.50, 0.52, 0.90, 0.95, 0.99],
        "evaluation_source": [exact, exact, "reconstructed_history", "", None],
    })
    frame = pd.DataFrame({"mode": "loto", "target_date": dates, "model": "hang_so",
                          "logloss": [0.55, 0.55, 0.55, 0.55, 0.55]})
    out = bench.against_recorded_production(frame, book)["loto"]
    assert out["exact_emitted"]["days"] == 2
    assert out["exact_emitted"]["production_recorded_logloss"] == pytest.approx(0.51)
    assert out["reconstructed"]["days"] == 3
    assert out["reconstructed"]["production_recorded_logloss"] == pytest.approx((0.90 + 0.95 + 0.99) / 3)
