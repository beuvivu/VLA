"""Thành tích nhiều kỳ của sổ phỏng đoán (``evaluation.board_record``).

Phép chấm phải (1) trùng nghĩa với luật trúng của trang Live, (2) cho mốc chọn bừa ĐÚNG — trung bình mô
phỏng khớp ``base`` chính xác mà sổ đã ghi —, (3) không báo động nhầm trên lịch sử công bằng và (4) bắt
được một danh sách thật sự có kỹ năng. Tất cả trên dữ liệu dựng sẵn, nên không phép nào quét tập rỗng.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from evaluation import board_record
from evaluation.prediction_board import base_probability

DATA = Path(__file__).resolve().parents[2] / "data"


def _draw(tails: list[int]) -> list[str]:
    """27 giải có đuôi cho trước (giải đầu là Đặc Biệt), phần đầu số tuỳ ý."""
    assert len(tails) == 27
    return [f"{7 * i % 10}{t:02d}" for i, t in enumerate(tails)]


def _item(rule: dict, prob: float | None = None) -> dict:
    return {"label": "x", "rule": rule, "prob": prob, "base": base_probability(rule)}


def _board(target: str, lists: dict[str, list[dict]]) -> dict:
    return {"target_date": target, "lists": [{"id": key, "title": key, "items": items} for key, items in lists.items()]}


# Kỳ mẫu: Đặc Biệt đuôi 46; 13 về hai nháy; 88 về một nháy.
TAILS = [46, 13, 13, 88] + [0] * 23
COUNTS, SPECIAL = board_record.outcome(_draw(TAILS))


@pytest.mark.parametrize(("rule", "hit"), [
    ({"on": "loto", "numbers": ["13"], "need": 1}, True),
    ({"on": "loto", "numbers": ["13"], "need": 2}, True),
    ({"on": "loto", "numbers": ["88"], "need": 2}, False),
    ({"on": "loto", "numbers": ["88", "13"], "need": 2}, True),      # tổng nháy của cả nhóm
    ({"on": "loto", "numbers": ["13", "88"], "all": True}, True),    # xiên: đủ mọi số
    ({"on": "loto", "numbers": ["13", "77"], "all": True}, False),
    ({"on": "special", "numbers": ["46", "64"]}, True),
    ({"on": "special", "numbers": ["64"]}, False),                   # số lộn không tính cho Đặc Biệt
    ({"on": "special_digit", "digits": [6]}, True),                  # chạm đơn vị
    ({"on": "special_digit", "digits": [4]}, True),                  # chạm chục
    ({"on": "special_digit", "digits": [1, 2]}, False),
])
def test_hit_rules_match_the_live_page(rule: dict, hit: bool) -> None:
    assert bool(board_record.item_hits(rule, COUNTS, SPECIAL)[0]) is hit


@pytest.mark.parametrize("rule", [
    {"on": "loto", "numbers": ["13"], "need": 1},
    {"on": "loto", "numbers": ["07", "70"], "need": 2},
    {"on": "loto", "numbers": ["34", "35"], "all": True},
    {"on": "special", "numbers": ["34", "39", "43", "48"]},
    {"on": "special_digit", "digits": [0, 1]},
])
def test_the_fair_simulation_reproduces_the_exact_base_the_board_records(rule: dict) -> None:
    """Luật chấm và ``base_probability`` của sổ là hai bản độc lập: chúng phải nói cùng một xác suất."""
    counts, special = board_record.fair_draws(np.random.default_rng(1), 200_000)
    hits = board_record.item_hits(rule, counts, special)
    p = base_probability(rule)
    assert abs(hits.mean() - p) < 4 * np.sqrt(p * (1 - p) / len(hits))


def _history(rng: np.random.Generator, draws: int, lists: dict, *, cheat: str | None = None):
    """Lịch sử công bằng: mỗi kỳ một kết quả ngẫu nhiên; ``cheat`` là danh sách được nhìn trước đáp án."""
    boards, results = [], {}
    for d in range(draws):
        target = f"2026-01-{d + 1:02d}"
        tails = rng.integers(0, 100, 27).tolist()
        results[target] = _draw(tails)
        day = {key: make(rng) for key, make in lists.items()}
        if cheat:
            day[cheat] = [_item({"on": "loto", "numbers": [f"{t:02d}"], "need": 1}) for t in tails[:10]]
        boards.append(_board(target, day))
    return boards, results


def _random_loto(rng: np.random.Generator) -> list[dict]:
    return [_item({"on": "loto", "numbers": [f"{n:02d}"], "need": 1}) for n in rng.choice(100, 10, replace=False)]


def _random_touch(rng: np.random.Generator) -> list[dict]:
    return [_item({"on": "special_digit", "digits": sorted(rng.choice(10, 2, replace=False).tolist())})
            for _ in range(10)]


def test_fair_histories_rarely_look_better_or_worse_than_chance() -> None:
    """200 lịch sử 10 kỳ không kỹ năng: p < 0,05 không được vượt mức danh nghĩa (cộng sai số Monte Carlo)."""
    rng = np.random.default_rng(7)
    rejected = 0
    trials = 200
    for trial in range(trials):
        boards, results = _history(rng, 10, {"loto": _random_loto, "touch": _random_touch})
        record = board_record.build_record(boards, results, simulations=2_000, replicates=2_000, seed=trial)
        rejected += sum(row["p"] < 0.05 for row in record["lists"])
    rate = rejected / (2 * trials)
    assert rate <= 0.05 + 3 * np.sqrt(0.05 * 0.95 / (2 * trials)), rate


def test_a_list_that_saw_the_answer_is_caught_and_honest_lists_are_not() -> None:
    # Hạt giống cố định: hai danh sách trung thực của lịch sử này nằm giữa phân phối (p 0,50 và 0,52). Tỉ lệ
    # báo nhầm trên lịch sử công bằng do phép kiểm hiệu chỉnh ở trên chặn, không phải phép này.
    rng = np.random.default_rng(100)
    boards, results = _history(rng, 8, {"loto": _random_loto, "touch": _random_touch}, cheat="biet-truoc")
    record = board_record.build_record(boards, results, simulations=4_000, replicates=4_000)
    rows = {row["id"]: row for row in record["lists"]}
    assert rows["biet-truoc"]["hits"] == 80
    # Không lần ghép nào trong 4 000 đạt 80 mục: p chạm sàn Monte Carlo 1/(R + 1).
    assert rows["biet-truoc"]["p_high"] == pytest.approx(1 / 4_001, abs=1e-6)
    assert rows["biet-truoc"]["p_holm"] < 0.01
    assert rows["biet-truoc"]["verdict"] == "trúng nhiều hơn chọn bừa"
    assert record["family"]["verdict"] == "trúng nhiều hơn chọn bừa"
    assert {rows[key]["verdict"] for key in ("loto", "touch")} == {"chưa khác chọn bừa"}


def test_a_list_that_never_hits_is_called_worse() -> None:
    boards, results = [], {}
    for d in range(20):
        target = f"2026-02-{d + 1:02d}"
        results[target] = _draw([0] * 27)        # chỉ số 00 về
        boards.append(_board(target, {"lech": [_item({"on": "loto", "numbers": [f"{n:02d}"], "need": 1})
                                               for n in range(1, 11)]}))
    row = board_record.build_record(boards, results, simulations=4_000, replicates=4_000)["lists"][0]
    assert (row["hits"], row["days_hit"]) == (0, 0)
    assert row["verdict"] == "trúng ít hơn chọn bừa"


def test_holm_steps_down_and_stays_monotone() -> None:
    assert board_record.holm([0.01, 0.04, 0.03, 0.5]) == pytest.approx([0.04, 0.09, 0.09, 0.5])
    assert board_record.holm([0.9, 0.9]) == [1.0, 1.0]


def test_the_record_of_the_real_boards_adds_up_and_is_deterministic() -> None:
    draws = board_record.complete_draws(DATA)
    boards = board_record.scored_boards(DATA, draws)
    assert len(boards) >= 14, "sổ thật phải có ít nhất 14 kỳ đã chấm (21-10 → 03-11-2026)"
    first = board_record.build_record(boards, draws, simulations=2_000, replicates=2_000)
    again = board_record.build_record(boards, draws, simulations=2_000, replicates=2_000)
    assert json.dumps(first, sort_keys=True) == json.dumps(again, sort_keys=True)
    expected = {}
    for board in boards:
        for entry in board["lists"]:
            expected[entry["id"]] = expected.get(entry["id"], 0.0) + sum(item["base"] for item in entry["items"])
    rows = {row["id"]: row for row in first["lists"]}
    assert set(rows) == {key for key, total in expected.items() if total > 0}
    for key, row in rows.items():
        assert row["expected"] == pytest.approx(expected[key], abs=1e-5)
        assert 0 <= row["days_hit"] <= row["draws"] and 0 <= row["hits"] <= row["items"]
    assert first["family"]["hits"] == sum(row["hits"] for row in first["lists"])
    # Holm trên mọi danh sách: đúng bằng phép hiệu chỉnh, và thật sự nâng p (25 danh sách).
    raw = [row["p"] for row in first["lists"]]
    assert [row["p_holm"] for row in first["lists"]] == pytest.approx(board_record.holm(raw), abs=1e-6)
    assert any(row["p_holm"] > row["p"] + 1e-9 for row in first["lists"])


def test_the_simulated_special_is_one_of_the_27_counted_tails() -> None:
    """Đuôi Đặc Biệt cũng là một lượt LOTO: Đặc Biệt 46 thì số 46 về ít nhất một nháy."""
    counts, special = board_record.fair_draws(np.random.default_rng(2), 5_000)
    assert counts.sum(axis=1).tolist() == [27] * 5_000
    assert (counts[np.arange(5_000), special] >= 1).all()


def test_written_record_is_byte_stable(tmp_path: Path) -> None:
    (tmp_path / "evaluation" / "prediction_board").mkdir(parents=True)
    boards, results = _history(np.random.default_rng(5), 4, {"loto": _random_loto})
    for board in boards:
        (tmp_path / "evaluation" / "prediction_board" / f"{board['target_date']}.json").write_text(
            json.dumps(board), encoding="utf-8")
    rows = ["date," + ",".join(board_record.PRIZE_COLUMNS)]
    rows += [target + "," + ",".join(values) for target, values in results.items()]
    (tmp_path / "xsmb.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    first = board_record.write_record(tmp_path).read_bytes()
    assert board_record.write_record(tmp_path).read_bytes() == first
    assert json.loads(first)["draws"] == 4
