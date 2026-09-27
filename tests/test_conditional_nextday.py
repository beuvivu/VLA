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


def _conditional_oracle_risks(seed: int, *, planted: bool) -> dict[str, float]:
    """Rủi ro Brier dư kỳ vọng trên đủ 100 trạng thái nguồn và 100 số.

    Dùng đúng 700 kỳ khớp của fixture cũ. Các kết quả đặc biệt giữ IID đều;
    khi nguồn là 42, chỉ 26 giải thường ngày sau được lấy từ nhóm 00–19.
    Vì thế việc tiêm không thay chuỗi trạng thái nguồn hay làm sai oracle.
    """
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, 100, size=(900, 27))
    truth = np.full((100, 100), 1.0 - 0.99 ** 27)
    if planted:
        for day in range(len(draws) - 1):
            if draws[day, 0] == 42:
                draws[day + 1, 1:] = rng.integers(0, 20, size=26)
        truth[42, :20] = 1.0 - 0.99 * 0.95 ** 26
        truth[42, 20:] = 0.01
    frame = pd.DataFrame(draws, columns=["special", *[f"p{i}" for i in range(1, 27)]])
    frame["date"] = pd.date_range("2020-01-01", periods=len(frame)).strftime("%Y-%m-%d")
    fitted = compute_loto_nextday_given_special(frame.iloc[:700])
    baseline = fitted.groupby("number")["baseline"].first().reindex(range(100)).to_numpy()
    source = fitted["special"].to_numpy(dtype=int)
    number = fitted["number"].to_numpy(dtype=int)
    hits = fitted["hits"].to_numpy(dtype=float)
    trials = fitted["trials"].to_numpy(dtype=float)
    values = {
        "learned": fitted["p_eb"].to_numpy(),
        "empirical": fitted["p_raw"].to_numpy(),
        "hand60": (hits + 60.0 * fitted["baseline"].to_numpy()) / (trials + 60.0),
    }
    predictions = {"pooled": np.tile(baseline, (100, 1))}
    for name, probabilities in values.items():
        # Nguồn vắng trong tập khớp vẫn được chấm, với fallback về baseline.
        grid = np.tile(baseline, (100, 1))
        grid[source, number] = probabilities
        predictions[name] = grid
    risks = {name: float(np.mean((prob - truth) ** 2)) for name, prob in predictions.items()}
    risks.update({f"{name}_signal_row": float(np.mean((prob[42] - truth[42]) ** 2))
                  for name, prob in predictions.items()})
    return risks


def test_learned_shrinks_null_risk_against_empirical_rates_across_seeds() -> None:
    """Co nhiễu được đo bằng oracle-risk, không bằng dấu của 199 kỳ may rủi.

    Seed 11 vẫn thuộc dải 0–19. Với 700 kỳ, mô men đã hiệu chỉnh KHÔNG luôn
    hơn κ=60: trên 1.000 seed, excess-risk là 0,00057943 so với 0,00053046.
    Đó là đánh đổi giữ tín hiệu, không phải lý do đổi seed hay bỏ hiệu chỉnh.
    """
    risks = [_conditional_oracle_risks(seed, planted=False) for seed in range(20)]
    difference = [row["learned"] - row["empirical"] for row in risks]
    assert np.mean(difference) < 0.0


def test_learned_preserves_planted_conditional_signal_across_seeds() -> None:
    """Co hoàn toàn hoặc ép κ=60 không được thay thế phép học có tín hiệu.

    Chấm cả bảng để trả giá cho nhiễu ở 99 nguồn còn lại; đồng thời chấm riêng
    hàng có quy luật thật. So expected Brier chỉ cần marginal oracle, không
    giả định 100 số trong cùng kỳ độc lập.
    """
    risks = [_conditional_oracle_risks(seed, planted=True) for seed in range(20)]
    for baseline in ("pooled", "hand60"):
        assert np.mean([row["learned"] - row[baseline] for row in risks]) < 0.0
        assert np.mean([row["learned_signal_row"] - row[f"{baseline}_signal_row"]
                        for row in risks]) < 0.0


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
