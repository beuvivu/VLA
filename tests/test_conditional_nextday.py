from __future__ import annotations

import numpy as np
import pandas as pd

from conditional_nextday import compute_loto_nextday_given_special


def _two(dates: list[str]) -> pd.DataFrame:
    cols = ["special"] + [f"p{i}" for i in range(1, 27)]
    rows = []
    for t, d in enumerate(dates):
        vals = [(10 * t + i) % 100 for i in range(27)]
        vals[0] = t % 2  # two repeating special states 00/01
        rows.append({"date": d, **dict(zip(cols, vals, strict=True))})
    return pd.DataFrame(rows)


def test_conditional_matrix_has_probabilities_and_fdr():
    dates = pd.date_range("2026-01-01", periods=50, freq="D").strftime("%Y-%m-%d").tolist()
    out = compute_loto_nextday_given_special(_two(dates), prior_strength=20.0)
    assert not out.empty
    assert set(out["special"].unique()) == {0, 1}
    assert out["p_raw"].between(0, 1).all()
    assert out["p_eb"].between(0, 1).all()
    assert out["baseline"].between(0, 1).all()
    assert out["p_value"].between(0, 1).all()
    assert out["q_value_fdr"].between(0, 1).all()
    assert np.allclose(out["p"], out["p_raw"])


def test_missing_calendar_day_is_not_treated_as_next_day_pair():
    full_dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    gap_dates = ["2026-01-01", "2026-01-02", "2026-01-04"]
    full = compute_loto_nextday_given_special(_two(full_dates), prior_strength=0.0)
    gap = compute_loto_nextday_given_special(_two(gap_dates), prior_strength=0.0)

    # State 01 occurs at source row 1. In the gapped history its following row is
    # Jan-04, which must NOT be counted as a t+1 trial for Jan-02.
    full_trials = int(full.loc[full["special"] == 1, "trials"].iloc[0])
    gap_state = gap[gap["special"] == 1]
    assert full_trials == 1
    assert gap_state.empty


def test_empirical_bayes_probability_shrinks_toward_baseline():
    dates = pd.date_range("2026-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    raw = compute_loto_nextday_given_special(_two(dates), prior_strength=0.0)
    shrunk = compute_loto_nextday_given_special(_two(dates), prior_strength=100.0)
    key = ["special", "number"]
    merged = raw.merge(shrunk, on=key, suffixes=("_raw0", "_shrunk"))
    distance_raw = (merged["p_eb_raw0"] - merged["baseline_raw0"]).abs()
    distance_shrunk = (merged["p_eb_shrunk"] - merged["baseline_shrunk"]).abs()
    assert (distance_shrunk <= distance_raw + 1e-12).all()


def _noise_two(days: int, seed: int = 4) -> pd.DataFrame:
    """Lịch sử vô tín hiệu: đề và LOTO ngày hôm sau độc lập hoàn toàn."""
    rng = np.random.default_rng(seed)
    cols = ["special"] + [f"p{i}" for i in range(1, 27)]
    dates = pd.date_range("2020-01-01", periods=days, freq="D").strftime("%Y-%m-%d")
    rows = []
    for d in dates:
        vals = rng.integers(0, 100, size=27).tolist()
        rows.append({"date": d, **dict(zip(cols, vals, strict=True))})
    return pd.DataFrame(rows)


def test_learning_is_the_default_and_is_reported_per_special() -> None:
    out = compute_loto_nextday_given_special(_noise_two(500))
    assert "prior_strength" in out.columns
    # Mỗi con đề là một câu hỏi riêng nên κ phải khác nhau giữa các hàng.
    per_special = out.groupby("special")["prior_strength"].nunique()
    assert (per_special == 1).all(), "trong một hàng κ phải là một giá trị"
    assert out.groupby("special")["prior_strength"].first().nunique() > 1


def test_an_explicit_number_is_used_verbatim_for_every_special() -> None:
    out = compute_loto_nextday_given_special(_noise_two(300), prior_strength=60.0)
    assert (out["prior_strength"] == 60.0).all()
    merged = out.set_index(["special", "number"])
    expected = (merged["hits"] + 60.0 * merged["baseline"]) / (merged["trials"] + 60.0)
    np.testing.assert_allclose(merged["p_eb"].to_numpy(), expected.to_numpy())


def test_learned_beats_the_hand_picked_60_on_pairs_it_never_saw() -> None:
    """Chốt lại con số đã biện minh cho thay đổi này.

    Bảng này không vào bộ hợp thành nên không có Brier của bộ hợp thành để
    gác — phải chấm điểm chính ``p_eb`` trên phần đuôi. Số đầy đủ (1 792 cặp
    khớp, 598 cặp chấm điểm) ghi trong tài liệu của ``LEARN_CONDITIONAL_PRIOR``:
    κ = 60 cho Brier 0,18208903, phép học cho 0,18166797, t = -6,15.

    Ở đây dùng lịch sử tổng hợp ngắn hơn cho nhanh, và chỉ đòi đúng dấu.
    """
    frame = _noise_two(900, seed=11)
    cut = 700
    fit = frame.iloc[:cut]
    learned = compute_loto_nextday_given_special(fit)
    hand = compute_loto_nextday_given_special(fit, prior_strength=60.0)

    dates = pd.to_datetime(frame["date"])
    specials = (frame["special"].astype(int) % 100).to_numpy()
    later = frame.iloc[cut:]
    later_idx = later.index.to_numpy()

    def table(df: pd.DataFrame) -> np.ndarray:
        grid = np.full((100, 100), np.nan)
        grid[df["special"].to_numpy(), df["number"].to_numpy()] = df["p_eb"].to_numpy()
        return grid

    grids = {"học": table(learned), "đặt tay": table(hand)}
    marginal = float(learned["baseline"].mean())
    errors = {k: [] for k in grids}
    for i in later_idx[:-1]:
        if (dates[i + 1] - dates[i]).days != 1:
            continue
        s = int(specials[i])
        nxt = {int(v) % 100 for k, v in frame.loc[i + 1].items() if k != "date"}
        y = np.zeros(100)
        for x in nxt:
            y[x] = 1.0
        for name, grid in grids.items():
            row = grid[s]
            row = np.where(np.isnan(row), marginal, row)
            errors[name].append(float(np.mean((row - y) ** 2)))

    assert len(errors["học"]) > 50
    assert np.mean(errors["học"]) < np.mean(errors["đặt tay"])


def test_manifest_records_whether_the_strength_was_learned(tmp_path) -> None:
    import json
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    out = tmp_path / "cond"
    subprocess.run(
        [sys.executable, str(repo / "src" / "conditional_nextday.py"),
         "--out-dir", str(out), "--top", "3"],
        cwd=repo, check=True, capture_output=True,
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prior_strength_learned"] is True
    assert manifest["prior_strength_median"] is not None
