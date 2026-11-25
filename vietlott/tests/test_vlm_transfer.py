"""Học chuyển giao Max 3D ↔ Max 3D Pro (``vlm.forecast.transfer``): có cận tất định, học nhanh hơn khi lệch chung,
lùi về luật riêng khi hai sản phẩm khác nhau, không nhìn kỳ cùng ngày, sổ tiến cứu chỉ nối thêm.

Lịch sử giả lập: 20 số ba chữ số mỗi kỳ; "lệch" là chữ số 6 ở hàng đơn vị ra với xác suất cao hơn 1/10.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from vietlott_engine.core.products import ProductCode
from vietlott_engine.forecast.data import Series, digit_counts
from vlm.forecast import transfer as tr

ROOT = Path(__file__).resolve().parents[1]
A, B = tr.PRODUCTS


def _series(product: ProductCode, start: date, n: int, seed: int, *, six: float = 0.1, step: int = 2) -> Series:
    """``n`` kỳ cách nhau ``step`` ngày; chữ số hàng đơn vị là 6 với xác suất ``six``, chữ số khác chia đều."""
    rng = np.random.default_rng(seed)
    digits = rng.integers(0, 10, size=(n, 20, 3))
    units = np.where(rng.random((n, 20)) < six, 6, rng.choice([d for d in range(10) if d != 6], size=(n, 20)))
    if six != 0.1:
        digits[:, :, 2] = units
    dates = np.array([np.datetime64(start + timedelta(days=step * i), "D") for i in range(n)])
    return Series(product, np.arange(1, n + 1), dates, {"digits": {"C": digit_counts(digits, 10)}})


def _by_product(steps: list[tr.Step], product: ProductCode) -> list[tr.Step]:
    return [s for s in steps if s.product == product]


def test_the_two_products_share_one_digit_layout_and_the_engine_switch_rate() -> None:
    spec = tr._spec()
    assert (spec.positions, spec.alphabet, spec.per_draw) == (3, 10, 20)
    assert tr.share(A) == pytest.approx(1 / (10 * 156)) and tr.share(B) == pytest.approx(1 / (10 * 156))


def test_the_mixture_never_trails_the_own_law_by_more_than_the_bound() -> None:
    series = {A: _series(A, date(2020, 1, 1), 300, seed=1, six=0.13),
              B: _series(B, date(2020, 1, 2), 300, seed=2, six=0.1)}
    steps, _ = tr.walk_forward(series)
    for product in (A, B):
        mine = _by_product(steps, product)
        regret = np.cumsum([s.sep - s.mix for s in mine])
        for t, value in enumerate(regret, start=1):
            assert value <= tr.fixed_share_bound(t, product) + 1e-9


def test_a_shared_bias_is_learned_faster_together() -> None:
    """Sản phẩm B ra đời muộn: học chung với lịch sử dài của A thì B dự báo tốt hơn ngay từ đầu."""
    series = {A: _series(A, date(2020, 1, 1), 500, seed=3, six=0.13),
              B: _series(B, date(2022, 9, 1), 150, seed=4, six=0.13)}
    steps, model = tr.walk_forward(series)
    late = _by_product(steps, B)
    gain = np.array([s.mix - s.sep for s in late])
    assert gain.sum() > 2.0 and gain.mean() / (gain.std(ddof=1) / math.sqrt(gain.size)) > 2.0
    own, pooled, w_pool = model.laws(B)
    assert w_pool > 0.5  # trọng số luật gộp của B
    mixed = model.mixed(B)
    assert int(np.argmax(mixed[2])) == 6 and mixed.sum(axis=1) == pytest.approx([1.0, 1.0, 1.0])
    assert np.abs(mixed - pooled).max() < np.abs(mixed - own).max()  # luật kỳ tới nghiêng về luật gộp


def test_diverging_products_fall_back_to_their_own_law() -> None:
    """A lệch, B đều: luật gộp mang độ lệch của A sang B, nên B phải lùi về luật riêng."""
    series = {A: _series(A, date(2020, 1, 1), 500, seed=5, six=0.14),
              B: _series(B, date(2020, 1, 2), 500, seed=6, six=0.1)}
    steps, model = tr.walk_forward(series)
    own = _by_product(steps, B)
    pooled_loss = sum(s.sep - s.pool for s in own)
    mixed_loss = sum(s.sep - s.mix for s in own)
    assert pooled_loss > 5.0 and mixed_loss < tr.fixed_share_bound(len(own), B)
    assert model.laws(B)[2] < 0.1


def test_draws_of_the_same_day_do_not_see_each_other() -> None:
    """Hai sản phẩm quay cùng ngày: điểm của B ngày ấy không đổi khi kết quả của A ngày ấy đổi."""
    a = _series(A, date(2021, 1, 1), 60, seed=7, six=0.13, step=1)
    b = _series(B, date(2021, 1, 1), 60, seed=8, six=0.13, step=1)
    base, _ = tr.walk_forward({A: a, B: b})
    changed = a.obs["digits"]["C"].copy()
    changed[40] = np.roll(changed[40], 1, axis=-1)
    altered = Series(A, a.draw_ids, a.dates, {"digits": {"C": changed}})
    other, _ = tr.walk_forward({A: altered, B: b})
    b_base, b_other = _by_product(base, B), _by_product(other, B)
    assert [s.mix for s in b_base[:41]] == [s.mix for s in b_other[:41]]
    assert b_base[41].pool != b_other[41].pool  # ngày hôm sau thì luật gộp đã học kỳ ấy


def test_prospective_scores_only_later_draws_and_never_rewrites_a_row(tmp_path: Path) -> None:
    start = tr.REGISTERED_ON - timedelta(days=20)
    series = {A: _series(A, start, 20, seed=9, step=2), B: _series(B, start + timedelta(days=1), 20, seed=10, step=2)}
    ledger = tmp_path / tr.LEDGER
    steps, _ = tr.walk_forward(series)
    first = tr.prospective(steps, ledger)
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows and all(date.fromisoformat(r["date"]) > tr.REGISTERED_ON for r in rows)
    later = [s for s in steps if s.day > tr.REGISTERED_ON]
    assert len(rows) == len(later) and first["ledger_consistent"]
    assert first["products"][A.value]["draws"] == len(_by_product(later, A))
    text = ledger.read_text(encoding="utf-8")
    assert tr.prospective(steps, ledger) == first and ledger.read_text(encoding="utf-8") == text
    shifted = [tr.Step(s.product, s.draw_id, s.day, s.sep, s.pool, s.mix + 1.0, s.w_pool) for s in steps]
    third = tr.prospective(shifted, ledger)
    assert not third["ledger_consistent"] and ledger.read_text(encoding="utf-8") == text


def test_write_is_deterministic_and_keeps_an_unchanged_summary(tmp_path: Path) -> None:
    series = {A: _series(A, date(2020, 1, 1), 120, seed=11, six=0.13),
              B: _series(B, date(2020, 1, 2), 120, seed=12, six=0.13)}
    path = tr.write(series, tmp_path)
    first = path.read_bytes()
    stamp = path.stat().st_mtime_ns
    tr.write(series, tmp_path)
    assert path.read_bytes() == first and path.stat().st_mtime_ns == stamp
    summary = json.loads(first)
    assert summary["deployment"] == "shadow" and summary["version"] == tr.VERSION
    block = summary["walk_forward"][A.value]
    assert block["draws"] == 120 and len(block["next"]["mixed"]) == 3
    assert block["log10_wealth"]["mixed"] - block["log10_wealth"]["separate"] == pytest.approx(
        block["mixed_vs_separate"]["log10"], abs=1e-8)


def test_the_committed_summary_carries_the_frozen_rule() -> None:
    summary = json.loads((ROOT / "data" / "forecast" / tr.SUMMARY).read_text(encoding="utf-8"))
    assert summary["version"] == tr.VERSION and summary["products"] == [p.value for p in tr.PRODUCTS]
    assert summary["rule"]["registered_on"] == tr.REGISTERED_ON.isoformat()
    assert summary["rule"]["prior_pooled"] == tr.PRIOR_POOLED
    assert all(v["last_date"] <= "2026-11-25" or summary["prospective"]["products"][k]["draws"] > 0
               for k, v in summary["walk_forward"].items())


def test_fixed_share_keeps_a_floor_under_the_losing_law() -> None:
    """Sau một kỳ mà luật gộp sai thảm, trọng số của nó vẫn còn ít nhất share × tiên nghiệm, để còn hồi lại được."""
    model = tr.TransferModel()
    counts = np.zeros((3, 10))
    counts[:, 6] = 20  # cả 20 số đều có 6 ở mọi vị trí
    model.pool.learn(np.tile(np.eye(10)[3] * 20, (3, 1)), 1)  # luật gộp đã nghiêng hẳn về chữ số 3
    for _ in range(40):
        model.score(B, counts, 1, date(2020, 1, 1))
    w_pool = model.laws(B)[2]
    floor = tr.share(B) * tr.PRIOR_POOLED
    assert floor * 0.999 <= w_pool < 3 * floor  # không có chia sẻ thì trọng số đã rơi xa dưới sàn
