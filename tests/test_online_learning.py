"""Hợp đồng học trực tuyến: chỉ chấm dự báo đã đóng băng trước kỳ quay."""

from __future__ import annotations

import copy
import importlib
import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from time_policy import VIETNAM_TZ
from xsmb_domain import FIELD_WIDTHS, LOTO_BASELINE_RATE


@pytest.fixture
def online():
    try:
        return importlib.import_module("online_learning")
    except ModuleNotFoundError:

        class MissingImplementation:
            def __getattr__(self, name):
                pytest.fail(f"Chưa có hành vi học trực tuyến: {name}")

        return MissingImplementation()


def history(n=20, *, signal=False):
    rng = np.random.default_rng(441)
    rows = []
    for i in range(n):
        row = {key: int(rng.integers(0, 10**width)) for key, width in FIELD_WIDTHS}
        row["date"] = (date(2025, 1, 1) + timedelta(days=i)).isoformat()
        if signal:
            row["special"] = 12307
        rows.append(row)
    return pd.DataFrame(rows)


def before(target):
    return datetime.combine(date.fromisoformat(str(target)), datetime.min.time(), VIETNAM_TZ)


def uniform(mode="de"):
    return np.full(100, 0.01 if mode == "de" else LOTO_BASELINE_RATE)


def issue(online, state, frame, incumbent=None):
    target = (date.fromisoformat(frame.iloc[-1]["date"]) + timedelta(days=1)).isoformat()
    return online.advance(
        state,
        frame,
        uniform(state["mode"]) if incumbent is None else incumbent,
        target,
        now=before(target),
    )


def test_probability_loss_distinguishes_identical_ranks_and_loto_marginals(online):
    p = np.linspace(1, 2, 100)
    p /= p.sum()
    q = p**5 / (p**5).sum()
    y = np.zeros(100)
    y[0] = 1
    assert np.array_equal(np.argsort(p), np.argsort(q))
    assert online.proper_losses("de", p, y)["brier"] == pytest.approx(((p - y) ** 2).sum() / 2)
    assert online.proper_losses("de", p, y)["logloss"] < online.proper_losses("de", q, y)["logloss"]
    assert online.proper_losses("de", p, y)["brier"] < online.proper_losses("de", q, y)["brier"]
    yl = np.zeros(100)
    yl[:23] = 1
    assert online.proper_losses("loto", uniform("loto"), yl)["brier"] == pytest.approx(
        ((uniform("loto") - yl) ** 2).mean()
    )


def test_shadow_keeps_exact_incumbent_and_no_retrospective_learning(online):
    frame = history(40)
    p = np.linspace(1, 2, 100)
    p /= p.sum()
    state, record = issue(online, online.new_state("de"), frame, p)
    assert np.array_equal(record["published"], p)
    assert state["learning"]["n_settled"] == 0
    assert not record["gate"]["active"]
    assert record["target_date"] == "2025-02-10"
    assert datetime.fromisoformat(record["generated_at"]).utcoffset() is not None
    assert set(record["experts"]) >= {
        "incumbent",
        "constant",
        "bayes_30",
        "bayes_180",
        "bayes_all",
        "lag_special",
        "lag_repeat",
    }


def test_repeated_target_restores_frozen_forecast_and_settles_once(online):
    frame = history(22)
    state, record = issue(online, online.new_state("de"), frame.iloc[:20])
    altered = uniform()
    altered[7] += 0.02
    altered[8] -= 0.009
    altered[9] -= 0.009
    altered[10] -= 0.002
    same, restored = issue(online, state, frame.iloc[:20], altered)
    assert same == state
    assert restored == record
    settled, _ = issue(online, same, frame.iloc[:21])
    again, _ = issue(online, settled, frame.iloc[:21], altered)
    assert again == settled
    assert settled["learning"]["n_settled"] == 1
    assert np.any(np.asarray(settled["learning"]["slow_loss"]) > 0)


def test_restart_has_identical_memory_and_probabilities(online, tmp_path):
    frame = history(28)
    continuous = online.new_state("loto")
    resumed = online.new_state("loto")
    for end in range(20, 28):
        continuous, result = issue(online, continuous, frame.iloc[:end])
        resumed, restart_result = issue(online, resumed, frame.iloc[:end])
        path = tmp_path / "state.json"
        online.save_state(path, resumed)
        resumed = online.load_state(path, "loto")
        assert continuous == resumed
        assert result == restart_result
    assert continuous["learning"]["n_settled"] == 7
    assert min(result["weights"].values()) > 0


def test_candidates_ignore_future_rows(online):
    frame = history(40)
    past = frame.iloc[:20]
    changed = frame.copy()
    changed.loc[changed.index[20:], "special"] = 12307
    one = online.build_experts("de", past, uniform(), "2025-01-21")
    two = online.build_experts("de", changed, uniform(), "2025-01-21")
    for name in one:
        np.testing.assert_array_equal(one[name], two[name])


def test_conditional_loto_respects_twenty_seven_prize_slots(online):
    frame = history(201)
    fields = [name for name, _ in FIELD_WIDTHS]
    for i in range(200):
        frame.loc[i, fields] = np.arange(27) + 27 * (i % 2)
    frame.loc[200, fields] = np.arange(54, 81)
    experts = online.build_experts("loto", frame, uniform("loto"), "2025-07-21")
    assert max(float(p.sum()) for p in experts.values()) <= 27 + 1e-9
    assert experts["lag_repeat"].sum() > 1
    bad = np.full(100, 0.9)
    with pytest.raises(ValueError, match="27|biên|marginal"):
        issue(online, online.new_state("loto"), frame, bad)


def test_known_target_and_after_cutoff_cannot_create_a_forecast(online):
    frame = history(20)
    with pytest.raises(ValueError, match="biết|known|target|đích"):
        online.advance(
            online.new_state("de"), frame, uniform(), "2025-01-20", now=before("2025-01-21")
        )
    with pytest.raises(ValueError, match="cutoff|giờ|hạn"):
        online.advance(
            online.new_state("de"),
            frame,
            uniform(),
            "2025-01-21",
            now=datetime(2025, 1, 21, 18, 20, tzinfo=VIETNAM_TZ),
        )
    with pytest.raises(ValueError, match="timezone|múi"):
        online.advance(
            online.new_state("de"),
            frame,
            uniform(),
            "2025-01-21",
            now=before("2025-01-21").replace(tzinfo=None),
        )


def test_historical_mutation_and_conflicting_duplicate_are_rejected(online):
    frame = history(21)
    state, _ = issue(online, online.new_state("de"), frame.iloc[:20])
    altered = frame.copy()
    altered.loc[0, "prize1"] += 1
    with pytest.raises(ValueError, match="lịch sử|history|prefix"):
        issue(online, state, altered)
    conflict = pd.concat([frame, frame.iloc[[0]].assign(special=99999)])
    with pytest.raises(ValueError, match="trùng|duplicate|conflict"):
        issue(online, state, conflict)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -0.1])
def test_invalid_probability_is_rejected_without_mutating_state(online, bad):
    state = online.new_state("de")
    unchanged = copy.deepcopy(state)
    p = uniform()
    p[0] = bad
    with pytest.raises(ValueError):
        issue(online, state, history(), p)
    assert state == unchanged


def test_corrupt_state_is_rejected(online, tmp_path):
    state, _ = issue(online, online.new_state("de"), history())
    path = tmp_path / "state.json"
    online.save_state(path, state)
    data = json.loads(path.read_text())
    data["learning"]["slow_loss"][0] = 100
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="checksum|toàn vẹn|corrupt"):
        online.load_state(path, "de")
    state["records"][0]["experts"]["constant"][0] = float("nan")
    with pytest.raises(ValueError):
        online.save_state(path, state)


def test_record_requires_valid_anchor_provenance(online, tmp_path):
    state, _ = issue(online, online.new_state("de"), history())
    del state["records"][0]["anchor_fingerprint"]
    with pytest.raises(ValueError, match="corrupt|neo|anchor"):
        online.save_state(tmp_path / "broken.json", state)


def test_compressed_journal_keeps_vectors_and_long_memory(online, tmp_path, monkeypatch):
    monkeypatch.setattr(online, "KEEP_FULL_RECORDS", 10)
    monkeypatch.setattr(online, "ARCHIVE_CHUNK", 5)
    frame = history(40)
    state = online.new_state("loto")
    originals = []
    for end in range(20, 39):
        state, record = issue(online, state, frame.iloc[:end])
        originals.append(record)
    assert len(state["records"]) <= 10
    assert state["learning"]["n_settled"] == 18
    assert state["archive"]
    path = tmp_path / "compressed.json"
    online.save_state(path, state)
    restored = online.load_state(path, "loto")
    assert state == restored
    import base64
    import zlib

    archived = json.loads(zlib.decompress(base64.b64decode(state["archive"][0]["zlib_base64"])))
    for original, compact in zip(originals, archived, strict=False):
        assert compact["experts"] == original["experts"]
        assert compact["published"] == original["published"]
        assert compact["settlement"] is not None
    expected, expected_record = issue(online, state, frame.iloc[:39])
    resumed, resumed_record = issue(online, restored, frame.iloc[:39])
    assert expected == resumed
    assert expected_record == resumed_record


def test_declared_holiday_is_archived_without_becoming_an_observation(
    online, tmp_path, monkeypatch
):
    from calendar_alignment import known_non_draw_days

    assert "2025-01-28" in known_non_draw_days()
    frame = history(45)
    frame = frame.loc[~frame["date"].isin(known_non_draw_days())].reset_index(drop=True)
    monkeypatch.setattr(online, "KEEP_FULL_RECORDS", 5)
    monkeypatch.setattr(online, "ARCHIVE_CHUNK", 3)
    state, holiday = issue(online, online.new_state("de"), frame.iloc[:27])
    assert holiday["target_date"] == "2025-01-28"
    for end in range(28, 36):
        state, record = issue(online, state, frame.iloc[:end])
    assert state["learning"]["n_settled"] == 7
    assert record["gate"]["n_observations"] == 7
    path = tmp_path / "holiday.json"
    online.save_state(path, state)
    restored = online.load_state(path, "de")
    assert restored == state
    import base64
    import zlib

    archived = json.loads(zlib.decompress(base64.b64decode(state["archive"][0]["zlib_base64"])))
    skipped = archived[0]
    assert skipped["experts"] == holiday["experts"]
    assert skipped["published"] == holiday["published"]
    assert skipped["settlement"]["status"] == "non_draw"
    assert skipped["settlement"]["calendar_date"] == "2025-01-28"
    assert "labels" not in skipped["settlement"]
    assert "scores" not in skipped["settlement"]


def test_undeclared_missing_result_blocks_without_erasing_forecast(online):
    frame = history(25)
    state, forecast = issue(online, online.new_state("de"), frame.iloc[:20])
    unchanged = copy.deepcopy(state)
    missing = frame.loc[frame["date"] != "2025-01-21"]
    with pytest.raises(ValueError, match="thiếu|missing|kết quả"):
        issue(online, state, missing)
    assert state == unchanged
    assert state["records"][0] == forecast


def test_gate_rejects_null_and_promotes_frozen_stable_signal(online):
    results = []
    for signal in (False, True):
        frame = history(112, signal=signal)
        state = online.new_state("de")
        early = []
        for end in range(25, 112):
            state, record = issue(online, state, frame.iloc[:end])
            if state["learning"]["n_settled"] < 60:
                early.append(record["gate"]["active"])
        assert not any(early)
        results.append((state, record))
    assert not results[0][1]["gate"]["active"]
    signal_state, signal_record = results[1]
    assert signal_record["gate"]["active"]
    assert signal_record["published"][7] > 0.10
    np.testing.assert_array_equal(signal_record["published"], signal_record["blend"])
    assert signal_state["learning"]["slow_loss"] != signal_state["learning"]["fast_loss"]


def test_drift_rolls_back_next_forecast_and_shadow_keeps_learning(online):
    frame = history(150, signal=True)
    frame.loc[115:, "special"] = 12300 + (np.arange(35) * 17 + 9) % 100
    state = online.new_state("de")
    active_before = False
    for end in range(25, 150):
        state, record = issue(online, state, frame.iloc[:end])
        if end == 115:
            active_before = record["gate"]["active"]
    assert active_before
    assert not record["gate"]["active"]
    assert np.array_equal(record["published"], uniform())
    assert state["learning"]["n_settled"] == 124


def test_cli_artifacts_keep_columns_and_restore_original_probability(online, tmp_path):
    data = tmp_path / "data"
    out = data / "predict"
    out.mkdir(parents=True)
    history().to_csv(data / "xsmb.csv", index=False)
    target = "2025-01-21"
    path = out / f"predict_next_de_all_{target}.csv"
    frame = pd.DataFrame(
        {
            "number": np.arange(100),
            "prob": uniform(),
            "custom": np.arange(100) * 2,
            "number_str": [f"{n:02d}" for n in range(100)],
        }
    )
    frame.to_csv(path, index=False)
    original = path.read_bytes()
    (out / "picks_de.json").write_text(
        json.dumps({"mode": "de", "target_date": target, "weights": {"kept": 1}})
    )
    report = online.run_online("de", data, out, now=before(target))
    assert report["status"] == "shadow"
    assert path.read_bytes() == original
    assert (data / "research" / "online_de_report.json").exists()
    picks = json.loads((out / "picks_de.json").read_text())
    assert picks["weights"] == {"kept": 1}
    assert picks["online"]["status"] == "shadow"
    stale_top = out / f"predict_next_de_top4_{target}.csv"
    frame.tail(4).to_csv(stale_top, index=False)
    online.run_online("de", data, out, now=before(target))
    assert pd.read_csv(stale_top)["number"].tolist() == [0, 1, 2, 3]
    frame["prob"] = np.linspace(1, 2, 100) / 150
    frame.to_csv(path, index=False)
    online.run_online("de", data, out, now=before(target))
    restored = pd.read_csv(path)
    np.testing.assert_array_equal(restored.sort_values("number")["prob"], uniform())
    assert restored["custom"].tolist() == frame["custom"].tolist()
    assert len(pd.read_csv(out / f"predict_next_de_top4_{target}.csv")) == 4


def _settled_state(online):
    frame = history(24)
    state = online.new_state("loto")
    for end in (21, 22):
        state, _ = issue(online, state, frame.iloc[:end])
    scored = [r for r in state["records"] if r["settlement"] is not None]
    assert scored, "phải có ít nhất một kỳ đã chốt để kiểm phép so điểm"
    return state, scored[0]["settlement"]["scores"]


def test_rounding_noise_in_a_settled_score_does_not_reject_the_journal(online, tmp_path):
    """Runner khác CPU chấm lại cùng vector lệch 1 ULP; sổ vẫn phải đọc được.

    Ngày 04-10-2026 logloss chốt ...7733 nhưng chấm lại ra ...7734, phép so
    bằng tuyệt đối từ chối sổ và pipeline hoàn tất đỏ hai ngày liền.
    """
    state, scores = _settled_state(online)
    value = scores["bayes_30"]["logloss"]
    scores["bayes_30"]["logloss"] = float(np.nextafter(value, np.inf))
    assert scores["bayes_30"]["logloss"] != value
    path = tmp_path / "ulp.json"
    online.save_state(path, state)
    assert online.load_state(path, "loto")["learning"] == state["learning"]


def test_a_real_change_to_a_settled_score_is_still_rejected(online, tmp_path):
    state, scores = _settled_state(online)
    scores["mixture"]["logloss"] *= 1 + 1e-9
    with pytest.raises(ValueError, match="lệch khỏi vector đóng băng"):
        online.save_state(tmp_path / "tampered.json", state)
