"""Kiểm thử kiến trúc plugin phỏng đoán và bộ thuật toán nâng cao.

Trọng tâm là ba bảo đảm của khung: không rò rỉ dữ liệu tương lai, mọi đầu ra là
xác suất hợp lệ đã co về đường cơ sở, và một thuật toán hỏng không làm sập
luồng đánh giá.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from predictor_algorithms import (
    GapHazardStrategy,
    MarkovFollowStrategy,
    RecencyDecayStrategy,
    WeekdaySeasonalStrategy,
    WeightedEnsembleStrategy,
    default_ensemble,
    register_defaults,
)
from predictor_strategies import (
    NUMBER_SPACE,
    REGISTRY,
    BaselineStrategy,
    PredictionContext,
    PredictorStrategy,
    StrategyRegistry,
    finalize,
    predict,
)
from strategy_evaluation import build_hit_matrix, evaluate_strategy
from xsmb_domain import baseline_rate


def _history(days: int = 120, seed: int = 7) -> tuple[list[date], np.ndarray]:
    """Lịch sử giả lập tất định: mỗi ngày rút 27 số từ 00..99."""
    rng = np.random.default_rng(seed)
    start = date(2025, 1, 1)
    dates = [start + timedelta(days=i) for i in range(days)]
    hits = np.zeros((days, NUMBER_SPACE), dtype=np.float64)
    for i in range(days):
        for n in rng.integers(0, NUMBER_SPACE, size=27):
            hits[i, int(n)] = 1.0
    return dates, hits


def _context(mode: str = "loto", days: int = 120) -> PredictionContext:
    dates, hits = _history(days)
    return PredictionContext(
        mode=mode, dates=dates, hits=hits, anchor_index=days - 2, target_date=dates[-1]
    )


ALL_STRATEGIES: list[PredictorStrategy] = [
    BaselineStrategy(),
    RecencyDecayStrategy(),
    WeekdaySeasonalStrategy(),
    GapHazardStrategy(),
    MarkovFollowStrategy(),
    default_ensemble(),
]


# --- Context: không rò rỉ tương lai ---------------------------------------


def test_context_rejects_malformed_history() -> None:
    dates, hits = _history(10)
    with pytest.raises(ValueError):
        PredictionContext(
            mode="loto", dates=dates, hits=hits[:, :50], anchor_index=5, target_date=dates[-1]
        )
    with pytest.raises(ValueError):
        PredictionContext(
            mode="loto", dates=dates, hits=hits, anchor_index=99, target_date=dates[-1]
        )
    with pytest.raises(ValueError):
        PredictionContext(
            mode="loto", dates=dates[:5], hits=hits, anchor_index=1, target_date=dates[-1]
        )


def test_window_never_exposes_days_after_the_anchor() -> None:
    """Bảo đảm nhân quả: mọi lát cắt đều dừng đúng tại ngày neo."""
    dates, hits = _history(50)
    anchor = 30
    ctx = PredictionContext(
        mode="loto", dates=dates, hits=hits, anchor_index=anchor, target_date=dates[anchor + 1]
    )
    assert ctx.window().shape[0] == anchor + 1
    assert ctx.window(10).shape[0] == 10
    assert np.array_equal(ctx.window()[-1], hits[anchor])
    assert np.array_equal(ctx.last_row(), hits[anchor])
    # Cửa sổ rộng hơn lịch sử vẫn bị chặn tại ngày neo.
    assert ctx.window(10_000).shape[0] == anchor + 1


def test_weekday_rows_only_return_matching_weekdays() -> None:
    dates, hits = _history(60)
    ctx = PredictionContext(
        mode="loto", dates=dates, hits=hits, anchor_index=58, target_date=dates[59]
    )
    for weekday in range(7):
        rows = ctx.weekday_rows(weekday)
        expected = sum(1 for d in dates[:59] if d.weekday() == weekday)
        assert rows.shape[0] == expected


# --- finalize: xác suất hợp lệ + co về baseline ----------------------------


def test_finalize_returns_a_normalised_distribution_for_de() -> None:
    ctx = _context("de")
    out = finalize(np.arange(NUMBER_SPACE, dtype=np.float64), ctx, confidence=1.0)
    assert out.shape == (NUMBER_SPACE,)
    assert out.sum() == pytest.approx(1.0)
    assert (out > 0).all()


def test_finalize_keeps_loto_around_the_base_rate() -> None:
    ctx = _context("loto")
    out = finalize(np.full(NUMBER_SPACE, 5.0), ctx, confidence=1.0)
    assert out.mean() == pytest.approx(baseline_rate("loto"), rel=1e-6)


def test_zero_confidence_collapses_onto_the_baseline() -> None:
    """Đây là lớp lọc nhiễu: không tin cậy thì không được phát biểu gì."""
    for mode in ("loto", "de"):
        ctx = _context(mode)
        out = finalize(np.arange(NUMBER_SPACE, dtype=np.float64), ctx, confidence=0.0)
        expected = baseline_rate(mode) if mode == "loto" else 1.0 / NUMBER_SPACE
        assert np.allclose(out, expected)


def test_confidence_monotonically_controls_deviation_from_baseline() -> None:
    ctx = _context("loto")
    scores = np.linspace(0.0, 10.0, NUMBER_SPACE)
    spreads = [
        float(finalize(scores, ctx, confidence=c).std()) for c in (0.0, 0.25, 0.5, 1.0)
    ]
    assert spreads == sorted(spreads)


def test_finalize_rejects_invalid_scores() -> None:
    ctx = _context("loto")
    with pytest.raises(ValueError):
        finalize(np.zeros(5), ctx, confidence=1.0)
    with pytest.raises(ValueError):
        finalize(np.full(NUMBER_SPACE, np.nan), ctx, confidence=1.0)


# --- Từng strategy ---------------------------------------------------------


@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
@pytest.mark.parametrize("mode", ["loto", "de"])
def test_every_strategy_emits_a_valid_distribution(
    strategy: PredictorStrategy, mode: str
) -> None:
    ctx = _context(mode)
    out = predict(strategy, ctx)
    assert out.shape == (NUMBER_SPACE,)
    assert np.all(np.isfinite(out))
    assert (out > 0).all() and (out < 1).all()
    if mode == "de":
        assert out.sum() == pytest.approx(1.0)


@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
def test_confidence_stays_within_unit_interval(strategy: PredictorStrategy) -> None:
    assert 0.0 <= strategy.confidence(_context("loto")) <= 1.0


@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
def test_strategies_survive_an_empty_history(strategy: PredictorStrategy) -> None:
    """Ngày đầu tiên chưa có gì để học; không thuật toán nào được ném lỗi."""
    dates, hits = _history(2)
    ctx = PredictionContext(
        mode="loto", dates=dates, hits=hits, anchor_index=0, target_date=dates[1]
    )
    out = predict(strategy, ctx)
    assert np.all(np.isfinite(out))


def test_baseline_strategy_is_exactly_the_base_rate() -> None:
    ctx = _context("loto")
    assert np.allclose(predict(BaselineStrategy(), ctx), baseline_rate("loto"))


def test_strategies_are_deterministic() -> None:
    """Cùng đầu vào phải cho cùng đầu ra: báo cáo mới tái lập được."""
    ctx = _context("loto")
    for strategy in ALL_STRATEGIES:
        assert np.array_equal(predict(strategy, ctx), predict(strategy, ctx))


def test_ensemble_without_components_falls_back_to_baseline() -> None:
    ctx = _context("loto")
    empty = WeightedEnsembleStrategy(components=[])
    assert empty.confidence(ctx) == 0.0
    assert np.allclose(predict(empty, ctx), baseline_rate("loto"))


# --- Registry --------------------------------------------------------------


def test_registry_add_replace_and_remove() -> None:
    registry = StrategyRegistry()
    strategy = BaselineStrategy()
    registry.register(strategy)
    assert "baseline" in registry and len(registry) == 1
    assert registry.get("baseline") is strategy

    with pytest.raises(ValueError):
        registry.register(BaselineStrategy())  # trùng tên

    replacement = BaselineStrategy()
    registry.replace(replacement)
    assert registry.get("baseline") is replacement
    assert len(registry) == 1

    registry.unregister("baseline")
    assert len(registry) == 0
    with pytest.raises(KeyError):
        registry.get("baseline")


def test_registry_rejects_a_nameless_strategy() -> None:
    registry = StrategyRegistry()
    nameless = BaselineStrategy()
    nameless.name = ""
    with pytest.raises(ValueError):
        registry.register(nameless)


def test_default_registry_exposes_baseline_and_the_algorithms() -> None:
    register_defaults()
    names = REGISTRY.names()
    assert "baseline" in names
    for expected in (
        "recency_decay",
        "weekday_seasonal",
        "gap_hazard",
        "markov_follow",
        "weighted_ensemble",
    ):
        assert expected in names


def test_registering_a_new_strategy_needs_no_framework_change() -> None:
    """Yêu cầu mở rộng: thêm thuật toán chỉ là thêm một lớp."""

    class Contrarian:
        name = "contrarian"
        description = "Đảo ngược tần suất gần đây"

        def score(self, ctx: PredictionContext) -> np.ndarray:
            recent = ctx.window(30).sum(axis=0)
            return float(recent.max()) + 1.0 - recent

        def confidence(self, ctx: PredictionContext) -> float:
            return 0.1

    registry = StrategyRegistry()
    registry.register(Contrarian())
    ctx = _context("loto")
    out = predict(registry.get("contrarian"), ctx)
    assert out.shape == (NUMBER_SPACE,)
    assert np.all(np.isfinite(out))


# --- Bộ đánh giá -----------------------------------------------------------


def test_evaluation_reports_skill_against_the_baseline() -> None:
    dates, hits = _history(90)
    score = evaluate_strategy(
        RecencyDecayStrategy(), dates=dates, hits=hits, mode="loto", eval_days=30
    )
    assert score.days == 30
    assert score.baseline_logloss > 0
    # Baseline tự chấm chính nó phải ra đúng 0 điểm kỹ năng.
    base = evaluate_strategy(
        BaselineStrategy(), dates=dates, hits=hits, mode="loto", eval_days=30
    )
    assert base.logloss == pytest.approx(base.baseline_logloss)
    assert base.logloss_skill == pytest.approx(0.0, abs=1e-12)


def test_a_broken_strategy_degrades_to_baseline_instead_of_crashing() -> None:
    """Tự phục hồi: lỗi thuật toán không được làm sập luồng đánh giá."""

    class Broken:
        name = "broken"
        description = "Luôn ném lỗi"

        def score(self, ctx: PredictionContext) -> np.ndarray:
            raise RuntimeError("hỏng có chủ đích")

        def confidence(self, ctx: PredictionContext) -> float:
            return 1.0

    dates, hits = _history(60)
    score = evaluate_strategy(Broken(), dates=dates, hits=hits, mode="loto", eval_days=20)
    assert score.days == 20
    # Đã lùi về baseline nên điểm trùng khớp baseline.
    assert score.logloss == pytest.approx(score.baseline_logloss)


def test_build_hit_matrix_matches_the_declared_targets() -> None:
    dates = [date(2025, 1, 1), date(2025, 1, 2)]
    matrix = build_hit_matrix(dates, [{1, 2}, {3}], [7, 9], "loto")
    assert matrix[0, 1] == 1 and matrix[0, 2] == 1 and matrix[0, 3] == 0
    assert matrix[1, 3] == 1
    special = build_hit_matrix(dates, [{1}, {2}], [7, 9], "de")
    assert special[0].sum() == 1 and special[0, 7] == 1
    assert special[1, 9] == 1
    with pytest.raises(ValueError):
        build_hit_matrix(dates, [{1}], [7], "xoso")
