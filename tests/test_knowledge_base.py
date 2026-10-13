"""Kho tri thức: không nhìn trước, luật chỉ được chấm tiến cứu, giải thích cộng đúng ra con số đã công bố."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import knowledge_base as kb
import multi_hit_vip as m
from xsmb_domain import baseline_rate


def _fair(n: int, seed: int = 1) -> np.ndarray:
    return m.counts_matrix(m.draws_from_frame(m.mock_history(n, seed=seed))[0]) >= 1


def _labels(n: int) -> list[str]:
    return list(m.mock_history(n, seed=0)["date"])


def _planted_lag(n: int, a: int, b: int, rate: float, seed: int = 3, start: int = 0) -> np.ndarray:
    """Lịch sử công bằng, cộng: từ kỳ ``start``, hễ a về ở kỳ t−1 thì b được cài về ở kỳ t với xác suất ``rate``."""
    present = _fair(n, seed)
    rng = np.random.default_rng(seed + 100)
    for t in range(max(1, start), n):
        if present[t - 1, a] and rng.random() < rate:
            present[t, b] = True
    return present


# --------------------------------------------------------------------------- bộ nhớ ngữ cảnh


def test_a_context_reads_only_earlier_draws() -> None:
    present = _fair(150)
    before = kb.context_vectors(present)
    t = 100
    changed = present.copy()
    changed[t:] = ~changed[t:]
    after = kb.context_vectors(changed)
    assert np.allclose(before[: t + 1], after[: t + 1])
    assert not np.allclose(before[t + 1], after[t + 1])


def test_neighbours_skip_the_overlapping_window_and_rank_by_similarity() -> None:
    memory = kb.ContextMemory(_fair(300))
    t = 250
    idx, sims = memory.neighbours(t, k=20)
    assert len(idx) == 20
    assert idx.min() >= memory.window and idx.max() < t - memory.window
    assert np.all(np.diff(sims) <= 1e-6)
    pool = np.arange(memory.window, t - memory.window)
    best = pool[np.argmax(memory.ctx[pool] @ memory.ctx[t])]
    assert idx[0] == best


def test_the_analog_forecast_is_the_neighbours_outcomes_shrunk_to_the_base() -> None:
    memory = kb.ContextMemory(_fair(300))
    p, idx = memory.predict(260, k=40, prior=25.0)
    base = baseline_rate("loto")
    expected = (memory.present[idx].sum(axis=0) + 25.0 * base) / (len(idx) + 25.0)
    assert np.allclose(p, expected)
    p0, _ = memory.predict(260, k=40, prior=1e9)
    assert np.allclose(p0, base)


def test_the_analog_evaluation_scores_against_the_constant_on_the_same_draws() -> None:
    present = _fair(400, seed=4)
    res = kb.evaluate_analog(present, _labels(400), last=200)
    assert res["draws"] == 200
    analog = res["analog"]
    assert analog["skill"] == pytest.approx(1 - analog["logloss"] / res["constant_logloss"])
    assert res["top_k"]["random_rate"] == pytest.approx(res["top_k"]["expected"] / (200 * kb.TOP_K))
    json.dumps(res, allow_nan=False)


# --------------------------------------------------------------------------- luật


def test_a_short_history_registers_no_rule_rather_than_an_unsupported_one() -> None:
    present = _fair(150)
    assert kb.mine_lag_rules(present, len(present), min_support=200) == []


def test_mining_finds_a_planted_lag_rule_and_ignores_rare_antecedents() -> None:
    present = _planted_lag(1500, a=12, b=34, rate=0.6)
    rules = kb.mine_lag_rules(present, len(present), k=3, min_support=200)
    assert (rules[0]["if"], rules[0]["then"]) == (12, 34)
    assert rules[0]["lift"] > 1.5
    rare = present.copy()
    rare[:, 12] = False
    rare[::50, 12] = True                         # a hiếm: chưa đủ số lần làm tiền đề
    assert all(r["if"] != 12 for r in kb.mine_lag_rules(rare, len(rare), k=20, min_support=200))


def test_a_rule_is_scored_only_on_draws_after_its_registration() -> None:
    present, labels = _fair(300), _labels(300)
    rule = {"if": 5, "then": 7, "registered_at": labels[199]}
    score = kb.score_rule(rule, present, labels)
    changed = present.copy()
    changed[:200] = ~changed[:200]               # sửa mọi kỳ đến ngày đăng ký (trừ tiền đề kỳ 199)
    changed[199] = present[199]
    assert kb.score_rule(rule, changed, labels) == score
    fired = [t for t in range(200, 300) if present[t - 1, 5]]
    assert score["fired"] == len(fired) and score["draws_after"] == 100
    assert score["hits"] == int(present[fired, 7].sum())
    assert score["expected"] == pytest.approx(sum(present[t].sum() / 100 for t in fired))
    assert kb.score_rule(rule, present, labels, horizon=30)["draws_after"] == 30


def test_the_e_process_on_a_hand_path() -> None:
    present = np.zeros((3, 100), dtype=bool)
    present[0, 1] = True                          # a = 1 về ở kỳ 0
    present[1, 2:27] = True                       # kỳ 1: 25 con về, gồm b = 2, không gồm a → y = 1, μ = 0,25
    labels = ["2026-01-01", "2026-01-02", "2026-01-03"]
    score = kb.score_rule({"if": 1, "then": 2, "registered_at": "2026-01-01"}, present, labels)
    expected = np.mean([1 + lam * (1 - 0.25) for lam in kb.RULE_BETS])
    assert score["fired"] == 1 and score["e_value"] == pytest.approx(expected)
    assert score["p_anytime"] == pytest.approx(1 / expected)


def test_the_rule_e_process_keeps_its_promise_under_fair_draws() -> None:
    """Xem lại mỗi kỳ: trên lịch sử công bằng, e-value chạm 1/α ở không quá α lịch sử."""
    hits = 0
    n_hist = 300
    for seed in range(n_hist):
        present = _fair(181, seed=seed)
        labels = _labels(181)
        rule = {"if": 3, "then": 9, "registered_at": labels[0]}
        hits += kb.score_rule(rule, present, labels)["e_max"] >= 1 / 0.05
    assert hits / n_hist <= 0.05


def test_a_real_rule_registered_before_it_shows_earns_evidence() -> None:
    present = _planted_lag(900, a=12, b=34, rate=0.8, start=400)
    labels = _labels(900)
    rule = {"if": 12, "then": 34, "registered_at": labels[399]}
    score = kb.score_rule(rule, present, labels, horizon=500)
    assert kb.rule_status(score, kb.RULES_PER_BATCH / kb.batch_alpha(1), horizon=500) == "co-bang-chung"


@pytest.mark.parametrize(("e_max", "draws", "status"), [
    (2000.0, 10, "co-bang-chung"), (1999.0, 10, "dang-kiem"), (1999.0, 180, "het-han"), (2000.0, 180, "co-bang-chung"),
])
def test_rule_status_uses_the_rules_own_e_threshold_and_a_horizon(e_max, draws, status) -> None:
    score = {"e_max": e_max, "draws_after": draws}
    assert kb.rule_status(score, 2000.0, horizon=180) == status


def test_the_batches_split_alpha_once_and_never_spend_more_than_alpha() -> None:
    """Phần của lô k cố định từ đầu và cộng mọi lô không vượt α — Bonferroni theo thời gian."""
    shares = [kb.batch_alpha(k) for k in range(1, 200_001)]
    assert sum(shares) <= kb.ALPHA and sum(shares) > kb.ALPHA * (1 - 1e-5)
    assert shares[0] == pytest.approx(kb.ALPHA * 6 / np.pi ** 2)
    assert np.all(np.diff(shares) < 0)


def test_registered_rules_are_frozen_and_a_new_batch_waits_its_turn() -> None:
    present, labels = _fair(1300), _labels(1300)
    first = kb.update_rules(None, present[:1200], labels[:1200])
    assert len(first["batches"]) == 1 and len(first["rules"]) == kb.RULES_PER_BATCH
    frozen = {r["id"]: (r["registered_at"], r["in_sample"], r["if"], r["then"]) for r in first["rules"]}
    early = kb.update_rules(first, present[:1200 + kb.DISCOVERY_EVERY - 1], labels[:1200 + kb.DISCOVERY_EVERY - 1])
    assert len(early["batches"]) == 1
    due = kb.update_rules(early, present[:1200 + kb.DISCOVERY_EVERY], labels[:1200 + kb.DISCOVERY_EVERY])
    assert len(due["batches"]) == 2 and len(due["rules"]) == 2 * kb.RULES_PER_BATCH
    for r in due["rules"]:
        if r["id"] in frozen:
            assert (r["registered_at"], r["in_sample"], r["if"], r["then"]) == frozen[r["id"]]
    # Ngưỡng ghi lúc đăng ký: lô mới không nâng ngưỡng của lô cũ (không rút lại kết luận đã báo).
    first_batch = set(frozen)
    for r in due["rules"]:
        k = 1 if r["id"] in first_batch else 2
        assert r["alpha"] == pytest.approx(kb.batch_alpha(k) / kb.RULES_PER_BATCH)
        assert r["threshold_e"] == pytest.approx(1 / r["alpha"])
    assert [b["alpha"] for b in due["batches"]] == pytest.approx([kb.batch_alpha(1), kb.batch_alpha(2)])
    assert sum(r["alpha"] for r in due["rules"]) <= kb.ALPHA
    assert {r["id"]: r["threshold_e"] for r in first["rules"]} == \
        {r["id"]: r["threshold_e"] for r in due["rules"] if r["id"] in first_batch}


def test_a_reported_rule_stays_reported_when_a_later_batch_is_registered(monkeypatch) -> None:
    """Kết luận của lô 1 không bị rút lại chỉ vì lô 2 ra đời: trạng thái đọc ngưỡng ghi lúc đăng ký."""
    present, labels = _fair(1300), _labels(1300)
    own = kb.RULES_PER_BATCH / kb.batch_alpha(1)
    monkeypatch.setattr(kb, "score_rule", lambda rule, *_: {"e_max": own * 1.001, "draws_after": 1})
    first = kb.update_rules(None, present[:1200], labels[:1200])
    due = kb.update_rules(first, present[:1200 + kb.DISCOVERY_EVERY], labels[:1200 + kb.DISCOVERY_EVERY])
    batch_one = set(due["batches"][0]["rules"])
    assert {r["status"] for r in due["rules"] if r["id"] in batch_one} == {"co-bang-chung"}
    assert {r["status"] for r in due["rules"] if r["id"] not in batch_one} == {"dang-kiem"}


def test_a_new_experiment_keeps_counting_batches_so_config_changes_cannot_respend_alpha(tmp_path: Path,
                                                                                       monkeypatch) -> None:
    frame = m.mock_history(1270, seed=8)
    for upto in (1230, 1230 + kb.DISCOVERY_EVERY):                  # thí nghiệm đầu: hai lô
        frame.iloc[:upto].to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
        first = json.loads(kb.run(tmp_path).read_text(encoding="utf-8"))
    assert [b["index"] for b in first["batches"]] == [1, 2]
    for step, name in enumerate(("HORIZON", "SHRINK"), start=1):
        monkeypatch.setattr(kb, name, getattr(kb, name) + 1)
        frame.iloc[:1230 + kb.DISCOVERY_EVERY + step].to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
        later = json.loads(kb.run(tmp_path).read_text(encoding="utf-8"))
        assert [b["index"] for b in later["batches"]] == [step + 2]
        assert later["batches"][0]["alpha"] == pytest.approx(kb.batch_alpha(step + 2))
    spent = [b["alpha"] for r in later["retired"] for b in r["batches"]] + [b["alpha"] for b in later["batches"]]
    assert spent == pytest.approx([kb.batch_alpha(k) for k in (1, 2, 3, 4)]) and sum(spent) <= kb.ALPHA


@pytest.mark.parametrize("factor", [0.5, 2.0])
def test_the_alpha_budget_is_fixed_for_the_life_of_the_knowledge_base(tmp_path: Path, monkeypatch, factor) -> None:
    """Hạ α sau khi lô 1 đã tiêu thì tổng vượt ngân sách mới; nâng α là xem kết quả rồi mới nới: cả hai bị từ chối."""
    frame = m.mock_history(1235, seed=8)
    frame.iloc[:1230].to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    first = json.loads(kb.run(tmp_path).read_text(encoding="utf-8"))
    assert first["alpha_budget"] == kb.ALPHA
    monkeypatch.setattr(kb, "ALPHA", kb.ALPHA * factor)
    frame.to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    with pytest.raises(ValueError, match="ngân sách α"):
        kb.run(tmp_path)
    assert json.loads((tmp_path / "knowledge" / "kb.json").read_text(encoding="utf-8")) == first


# --------------------------------------------------------------------------- giải thích


def _record(seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    base = baseline_rate("loto")
    experts = {name: list(np.clip(base + rng.normal(0, 0.01, 100), 0.01, 0.99))
               for name in ("incumbent", "constant", "bayes_30", "lag_repeat")}
    experts["constant"] = [base] * 100
    w = rng.dirichlet(np.ones(4))
    weights = dict(zip(experts, map(float, w), strict=True))
    mixture = sum(weights[k] * np.asarray(v) for k, v in experts.items())
    published = list(np.asarray(experts["incumbent"]))
    return {"target_date": "2026-10-13", "experts": experts, "weights": weights,
            "mixture": list(mixture), "published": published, "gate": {"active": False}}


def test_the_explanation_adds_up_to_the_mixture_and_quotes_the_published_number() -> None:
    record = _record()
    rules = [{"id": "r1", "if": 1, "then": 7, "text": "01 về hôm nay → 07 về kỳ sau", "status": "dang-kiem",
              "prospective": {"e_value": 1.5}},
             {"id": "r2", "if": 1, "then": 8, "text": "x", "status": "dang-kiem", "prospective": {"e_value": 1.0}}]
    out = kb.explain(7, "loto", record=record, confidence_row={"tier": "Low/Noise", "c_bayes": 0.1},
                     rules=rules, analog={"k": 50, "hits": 13, "similar_dates": []})
    base = baseline_rate("loto")
    assert out["probability"] == record["published"][7]
    assert base + sum(c["delta"] for c in out["contributions"]) == pytest.approx(record["mixture"][7])
    deltas = [abs(c["delta"]) for c in out["contributions"]]
    assert deltas == sorted(deltas, reverse=True)
    assert [r["id"] for r in out["rules"]] == ["r1"]
    text = " ".join(out["reasons"])
    assert "Thấp / nhiễu" in text and "bóng mờ" in text and "13/50" in text
    assert "," in out["reasons"][0] and "." not in out["reasons"][0].rstrip(".")


def test_an_active_online_learner_is_not_called_shadow() -> None:
    record = _record()
    record["gate"] = {"active": True}
    out = kb.explain(3, "loto", record=record, confidence_row=None, rules=[], analog=None)
    assert out["online_active"] and "bóng mờ" not in " ".join(out["reasons"])


def test_measured_knowledge_follows_the_measurements(tmp_path: Path) -> None:
    assert kb.measured_knowledge(tmp_path) == []
    (tmp_path / "confidence").mkdir()
    report = {"families": [{"key": "a", "label": "A", "p": 0.004}, {"key": "b", "label": "B", "p": 0.3}]}
    (tmp_path / "confidence" / "report.json").write_text(json.dumps(report), encoding="utf-8")
    status = {e["id"]: e["status"] for e in kb.measured_knowledge(tmp_path)}
    assert status == {"ho-a": "tin-hieu-anh-chup", "ho-b": "khong-hon-ngau-nhien"}


@pytest.mark.parametrize(("p_best", "status"), [(0.0, "tin-hieu-anh-chup"), (0.0005, "tin-hieu-anh-chup"),
                                                (0.00799, "chua-co-bang-chung")])
def test_confidence_families_are_holm_classified_snapshots_never_evidence(tmp_path: Path, p_best, status) -> None:
    """Mười lăm họ, mỗi họ ở α = 0,01: một họ p = 0,008 là điều thường thấy dưới giả thuyết không.
    Và p tính lại mỗi ngày trên lịch sử dồn thì dù nhỏ đến đâu cũng chỉ là ảnh chụp, không là bằng chứng."""
    (tmp_path / "confidence").mkdir()
    families = [{"key": f"h{i}", "label": f"H{i}", "p": 0.5} for i in range(14)]
    families.append({"key": "best", "label": "Best", "p": p_best})
    (tmp_path / "confidence" / "report.json").write_text(json.dumps({"families": families}), encoding="utf-8")
    entries = {e["id"]: e for e in kb.measured_knowledge(tmp_path)}
    assert entries["ho-best"]["status"] == status
    assert entries["ho-best"]["p_holm"] == pytest.approx(min(1.0, 15 * p_best))
    assert {entries[f"ho-h{i}"]["status"] for i in range(14)} == {"khong-hon-ngau-nhien"}
    assert {e["kind"] for e in entries.values()} == {"snapshot"}


@pytest.mark.parametrize(("state", "status"), [("dang_thu", "dang-kiem"), ("xac_nhan", "co-bang-chung"),
                                               ("bac_bo", "khong-dat")])
def test_a_registered_hypothesis_keeps_its_own_verdict_and_sample_size(tmp_path: Path, state, status) -> None:
    """14 kỳ của một phép kiểm 180 kỳ là đang thử, dù cửa sổ đặc trưng chỉ 7 ngày."""
    (tmp_path / "confidence").mkdir()
    hot = {"window": 7, "min_draws": 180, "draws": 14, "z": 0.83, "state": state}
    (tmp_path / "confidence" / "report.json").write_text(json.dumps({"hot_tail": hot}), encoding="utf-8")
    entry = {e["id"]: e for e in kb.measured_knowledge(tmp_path)}["gia-thuyet-duoi-nong"]
    assert entry["status"] == status
    assert entry["summary"].startswith("14/180 kỳ tiến cứu") and "0,83" in entry["summary"]


def test_run_writes_strict_json_and_keeps_rules_across_runs(tmp_path: Path) -> None:
    frame = m.mock_history(1260, seed=8)
    frame.iloc[:1230].to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    path = kb.run(tmp_path)
    first = json.loads(path.read_text(encoding="utf-8"))
    assert first["source_date"] == frame["date"].iloc[1229] and len(first["batches"]) == 1
    assert len(first["rules"]) == kb.RULES_PER_BATCH
    frame.to_csv(tmp_path / "xsmb-2-digits.csv", index=False)     # thêm 30 kỳ: đến hạn lô mới
    second = json.loads(kb.run(tmp_path).read_text(encoding="utf-8"))
    assert [b["registered_at"] for b in second["batches"]] == [first["batches"][0]["registered_at"],
                                                              frame["date"].iloc[-1]]
    old = {r["id"] for r in first["rules"]}
    assert old <= {r["id"] for r in second["rules"]}
    assert second["insights"] == {"loto": None, "de": None}        # chưa có sổ tự học: không bịa


_RULE_CHANGES = {"VERSION": kb.VERSION + 1, "DISCOVERY_EVERY": kb.DISCOVERY_EVERY + 1,
                 "RULES_PER_BATCH": kb.RULES_PER_BATCH + 1, "MIN_SUPPORT": kb.MIN_SUPPORT + 1,
                 "SHRINK": kb.SHRINK * 2, "HORIZON": kb.HORIZON + 1,
                 "RULE_BETS": kb.RULE_BETS + (3.0,)}


@pytest.mark.parametrize("name", sorted(_RULE_CHANGES))
def test_rules_carry_over_only_under_the_definition_they_were_registered_with(name, monkeypatch) -> None:
    rule = {"id": "tre-01-02-2026-01-01", "registered_at": "2026-01-01", "prospective": {"e_max": 3.0}}
    previous = json.loads(json.dumps({"version": kb.VERSION, "rule_config": kb.rule_config(),
                                      "source_date": "2026-02-01",
                                      "batches": [{"registered_at": "2026-01-01", "rules": [rule["id"]]}],
                                      "rules": [rule], "retired": [{"rules": ["cũ hơn"]}]}))
    kept, retired = kb.carry_over(previous)
    assert kept is previous and retired == [{"rules": ["cũ hơn"]}]
    monkeypatch.setattr(kb, name, _RULE_CHANGES[name])
    kept, retired = kb.carry_over(previous)
    assert kept is None
    assert retired[0] == {"rules": ["cũ hơn"]}
    assert retired[1]["rules"] == [rule] and retired[1]["last_scored"] == "2026-02-01"
    assert retired[1]["rule_config"] == previous["rule_config"] != kb.rule_config()


def test_a_changed_rule_definition_retires_the_old_batch_unscored_and_registers_now(tmp_path: Path,
                                                                                   monkeypatch) -> None:
    frame = m.mock_history(1240, seed=8)
    frame.iloc[:1230].to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    first = json.loads(kb.run(tmp_path).read_text(encoding="utf-8"))
    assert first["retired"] == [] and first["rule_config"] == kb.rule_config()
    frame.iloc[:1235].to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    same = json.loads(kb.run(tmp_path).read_text(encoding="utf-8"))
    assert same["batches"] == first["batches"] and same["retired"] == []     # cùng luật, chưa đến hạn
    monkeypatch.setattr(kb, "HORIZON", kb.HORIZON + 1)
    frame.to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    changed = json.loads(kb.run(tmp_path).read_text(encoding="utf-8"))
    assert [b["registered_at"] for b in changed["batches"]] == [frame["date"].iloc[-1]]
    assert changed["retired"][0]["rules"] == same["rules"]                   # cất nguyên, không chấm lại
    assert changed["retired"][0]["rule_config"]["horizon"] == kb.HORIZON - 1
    assert {r["id"] for r in changed["rules"]}.isdisjoint({r["id"] for r in same["rules"]})


def test_the_pipeline_builds_the_knowledge_base_after_what_it_reads() -> None:
    """Kho tri thức đọc sổ tự học, báo cáo Confidence và số đo Lô VIP của CÙNG lượt chạy: đứng sau cả ba."""
    source = (Path(__file__).resolve().parents[1] / "src" / "pipeline.py").read_text(encoding="utf-8")
    at = source.index('"src/knowledge_base.py"')
    for producer in ("online_learning", "confidence_matrix", "multi_hit_report"):
        assert source.index(f'"src/{producer}.py"') < at, producer
