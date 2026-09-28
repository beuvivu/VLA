"""Confidence Score ba tầng: luật tầng, hiệu chỉnh đa kiểm, bộ nhớ null, trang.

Mọi phép kiểm dựng kho nhỏ trong thư mục tạm với hành vi biết trước. Không
phép nào đọc ``data/`` thật: kho thật hôm nay cho 200/200 con ở tầng thấp, nên
dựa vào nó thì nhánh "phát hiện được tín hiệu thật" không bao giờ được chạy.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import confidence_matrix as cm

#: Mười con như dự báo thật: đủ để có kỳ về từ 6 con trở lên.
PICKS = (7, 11, 22, 33, 44, 55, 66, 77, 88, 99)
TOP10_LOTO = [3, 13, 23, 34, 45, 56, 67, 78, 89, 90]
TOP10_DE = [4, 40]
WIDTHS = [cm.PRIZE_WIDTH[c.split("_")[0]] for c in cm.PRIZE_COLUMNS]


def _store(root: Path, days: int, *, seed: int, rig: bool = False,
           rig_digit_column: str | None = None, picks: bool = False,
           top10: bool = False) -> np.ndarray:
    """Kho giả ``days`` kỳ bắt đầu 01-06-2022 (đủ để tách mẫu ở 2024).

    ``rig``: con 07 về theo KHỐI 5 kỳ về / 5 kỳ trượt qua giải 7.4, và kỳ cuối
    là kỳ về — đủ để Bayes, Markov và cầu cùng thấy nó.
    ``rig_digit_column``: chữ số đầu của giải ấy luôn thuộc {1, 2} — dấu vết
    của một kỳ quay bị sắp đặt trên bảng đầy đủ.
    """
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, 100, size=(days, 27))
    if rig:
        offset = (days - 1) % 10  # kỳ cuối rơi vào khối "về"
        for t in range(days):
            if ((t - offset) // 5) % 2 == 0 or t == days - 1:
                draws[t, 26] = 7
    start = date(2022, 6, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    two = pd.DataFrame(draws, columns=cm.PRIZE_COLUMNS)
    two.insert(0, "date", dates)
    root.mkdir(parents=True, exist_ok=True)
    two.to_csv(root / "xsmb-2-digits.csv", index=False)

    raw = {}
    for j, (column, width) in enumerate(zip(cm.PRIZE_COLUMNS, WIDTHS, strict=True)):
        head = rng.integers(0, 10 ** (width - 2), size=days) if width > 2 else np.zeros(days, int)
        if column == rig_digit_column and width > 2:
            head = rng.integers(1, 3, size=days) * 10 ** (width - 3) + head % 10 ** (width - 3)
        raw[column] = head * 100 + draws[:, j]
    frame = pd.DataFrame(raw)
    frame.insert(0, "date", dates)
    frame.to_csv(root / "xsmb.csv", index=False)

    if top10:
        # Đúng lúc pipeline dựng trang: tệp top-10 cho kỳ tới đã có, còn dự
        # đoán trang chủ vẫn trỏ vào kỳ VỪA quay (workflow dự đoán chạy sau).
        nxt = (start + timedelta(days=days)).isoformat()
        (root / "predict").mkdir(exist_ok=True)
        for mode, nums in (("loto", TOP10_LOTO), ("de", TOP10_DE)):
            pd.DataFrame({"number": nums, "prob": 0.1}).to_csv(
                root / "predict" / f"predict_next_{mode}_top10_{nxt}.csv", index=False)
        (root / "predictions_today.json").write_text(json.dumps({
            "date": dates[-1], "top_lo_to": [{"number": "01"}],
            "top_dac_biet": {"top_numbers": ["02"]},
        }), encoding="utf-8")
    if picks:
        nxt = (start + timedelta(days=days)).isoformat()
        (root / "predictions_today.json").write_text(json.dumps({
            "date": nxt,
            "top_lo_to": [{"number": f"{n:02d}"} for n in PICKS],
            "top_dac_biet": {"top_numbers": ["05", "50"]},
        }), encoding="utf-8")
    return draws


@pytest.fixture(scope="module")
def small_null() -> dict:
    """Null nhỏ (80 lịch sử) cho kho 700 kỳ — đủ để phân tầng, đủ nhanh cho CI."""
    return cm.null_quantiles(cm.simulate_null(700, 80, workers=1), 700)


# ---------------------------------------------------------------------------
# Luật tầng
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        ({"bayes": 0.90, "markov": 0.95, "cau": 0.86}, ("High", 0.86)),
        ({"bayes": 0.90, "markov": 0.95, "cau": 0.85}, ("Medium", 0.90)),  # 85% chưa "> 85%"
        ({"bayes": 0.99, "markov": 0.60, "cau": 0.00}, ("Medium", 0.60)),
        ({"bayes": 0.99, "markov": 0.59, "cau": 0.59}, ("Low/Noise", 0.59)),
        ({"bayes": 0.00, "markov": 0.00, "cau": 0.00}, ("Low/Noise", 0.00)),
    ],
)
def test_the_three_tier_rule_is_exactly_the_one_the_owner_set(components, expected) -> None:
    """High: cả ba > 85%. Medium: hai trong ba ≥ 60%. Còn lại: nhiễu."""
    assert cm.tier(components) == expected


def test_confidence_reads_the_share_of_fair_histories_below_the_signal() -> None:
    null = {"quantiles": {"x": list(np.linspace(0.0, 1.0, cm.QUANTILES))}}
    assert cm.confidence(null, "x", -1.0) == 0.0
    assert cm.confidence(null, "x", 0.5) == pytest.approx(0.5, abs=1e-3)
    assert cm.confidence(null, "x", 2.0) == 1.0


def test_stored_quantiles_reproduce_the_exact_null_share_for_discrete_statistics() -> None:
    """Tỉ lệ trúng cầu nhảy bậc 1/T, nên phân phối null đầy giá trị HOÀ.

    Bản đầu làm tròn phân vị còn 7 chữ số: cả khối giá trị hoà nằm ngay dưới
    tín hiệu và bị đếm là "nhỏ hơn", thổi tin cậy cầu Đặc Biệt trên kho thật
    từ 50,7% lên 66,5%. Đi qua JSON như bản lưu thật.
    """
    rng = np.random.default_rng(4)
    null = np.zeros((10_000, len(cm.NAMES)))
    column = cm.NAMES.index("cau_de_max")
    null[:, column] = rng.binomial(4217, 0.0157, size=10_000) / 4217
    stored = json.loads(json.dumps(cm.null_quantiles(null, 4218)))
    for value in np.unique(null[:, column]):
        exact = float((null[:, column] < value).mean())
        assert cm.confidence(stored, "cau_de_max", value) == pytest.approx(exact, abs=1.1e-3), value


# ---------------------------------------------------------------------------
# Hiệu chỉnh đa kiểm: nhiễu ở lại tầng thấp, tín hiệu thật lên tầng cao
# ---------------------------------------------------------------------------


def test_a_fair_history_puts_no_number_in_the_high_tier(tmp_path: Path, small_null: dict) -> None:
    _store(tmp_path, 700, seed=11)
    report = cm.build_report(tmp_path, small_null)

    assert report["counts"]["loto"]["High"] == 0
    assert report["counts"]["de"]["High"] == 0
    assert len(report["matrix"]) == 200


def test_a_rigged_number_is_found_by_all_three_models(tmp_path: Path, small_null: dict) -> None:
    """Con 07 bị sắp theo khối: phải lên tầng Cao, và CHỈ nó."""
    _store(tmp_path, 700, seed=11, rig=True)
    report = cm.build_report(tmp_path, small_null)
    rows = {(r["mode"], r["number"]): r for r in report["matrix"]}

    rigged = rows[("loto", "07")]
    assert rigged["tier"] == "High", rigged
    assert min(rigged["c_bayes"], rigged["c_markov"], rigged["c_cau"]) > cm.HIGH
    others = [r for key, r in rows.items() if key != ("loto", "07") and r["tier"] == "High"]
    assert not others, others


def test_a_high_naive_posterior_in_a_fair_history_is_not_high_confidence(
    tmp_path: Path, small_null: dict
) -> None:
    """Con có hậu nghiệm thô cao nhất của một lịch sử CÔNG BẰNG trông như "chắc
    chắn"; tin cậy hiệu chỉnh đa kiểm của nó phải thấp hơn hẳn."""
    _store(tmp_path, 700, seed=11)
    rows = [r for r in cm.build_report(tmp_path, small_null)["matrix"] if r["mode"] == "loto"]
    top = max(rows, key=lambda r: r["naive_bayes"])
    assert top["naive_bayes"] > 0.9, top
    assert top["c_bayes"] < cm.HIGH, top
    assert top["c_bayes"] < top["naive_bayes"] - 0.2, top


def test_the_markov_component_is_scored_against_the_null_of_the_same_statistic(
    tmp_path: Path, small_null: dict
) -> None:
    """Review PR #104: điểm Markov gắn trạng thái kỳ cuối (z hoặc −z) phải so
    với max của CHÍNH điểm ấy, không với max z chưa đổi dấu. Dựng null mà hai
    họ đối nghịch nhau: chấm nhầm họ thì mọi thành phần Markov về 0."""
    _store(tmp_path, 700, seed=11)
    null = json.loads(json.dumps(small_null))
    null["quantiles"]["markov_state_max"] = [-100.0] * cm.QUANTILES
    null["quantiles"]["markov_z_max"] = [100.0] * cm.QUANTILES
    rows = [r for r in cm.build_report(tmp_path, null)["matrix"] if r["mode"] == "loto"]
    assert all(r["c_markov"] == 1.0 for r in rows)


def test_out_of_sample_z_treats_each_draw_as_one_cluster() -> None:
    """Review PR #104: mười con cùng một kỳ không phải mười phép thử độc lập.
    Khi chúng về hoặc trượt CÙNG NHAU, thông tin chỉ bằng một phép thử mỗi kỳ,
    nên z phải bằng z của chuỗi một-phép-thử — không lớn gấp √10 lần."""
    rng = np.random.default_rng(8)
    together = (rng.random(900) < 0.30).astype(int)
    z_cluster = cm.cluster_z(10 * together, np.full(900, 10), cm.BASE)
    z_single = cm.cluster_z(together, np.ones(900), cm.BASE)
    assert z_cluster == pytest.approx(z_single)
    naive = (10 * together.sum() - 9000 * cm.BASE) / np.sqrt(9000 * cm.BASE * (1 - cm.BASE))
    assert naive > 2 * z_cluster > 0


def test_naive_bayes_false_alarms_are_reported_from_the_null(small_null: dict) -> None:
    """Chính lời phản biện của trang: hậu nghiệm cao nhất trong 100 con của
    một lịch sử CÔNG BẰNG thường vẫn vượt 95%."""
    share = 1 - cm.confidence(small_null, "bayes_post_max", 0.95)
    assert share > 0.5


# ---------------------------------------------------------------------------
# Phân phối null: đúng số mô phỏng, lưu và tái dùng
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sims", [1, 7, 41, 83])
def test_exactly_the_requested_number_of_histories_is_simulated(sims: int) -> None:
    """Review PR #104: chia đều cho 40 khối từng lặng lẽ bỏ phần dư."""
    assert len(cm.simulate_null(60, sims, workers=1)) == sims


def test_p_values_never_claim_more_resolution_than_the_simulations_have(
    tmp_path: Path, small_null: dict
) -> None:
    """Review PR #104: 80 lịch sử không đo được p dưới 1/81, dù lưới phân vị
    có 1 001 điểm. Con bị sắp đặt vượt MỌI lịch sử, nên p của nó chạm sàn."""
    _store(tmp_path, 700, seed=11, rig=True)
    report = cm.build_report(tmp_path, small_null)
    floor = 1 / (small_null["sims"] + 1)
    assert report["p_floor"] == pytest.approx(floor)
    assert min(f["p"] for f in report["families"]) == pytest.approx(floor)


@pytest.mark.parametrize("sims", [0, -3])
def test_a_nonpositive_simulation_count_is_rejected(sims: int) -> None:
    with pytest.raises(ValueError, match="ít nhất 1"):
        cm.simulate_null(60, sims, workers=1)


def test_the_null_is_reused_until_the_draw_count_drifts() -> None:
    cached = {"version": cm.STAT_VERSION, "draws": 1000, "sims": cm.DEFAULT_SIMS,
              "quantiles": {name: [0.0] for name in cm.NAMES}}
    assert not cm.needs_refresh(cached, 1000)
    assert not cm.needs_refresh(cached, 1020)
    assert cm.needs_refresh(cached, 1021)
    assert cm.needs_refresh({**cached, "version": cm.STAT_VERSION + 1}, 1000)
    assert cm.needs_refresh({**cached, "quantiles": {"freq_chi2": [0.0]}}, 1000)
    assert cm.needs_refresh(None, 1000)
    # Review PR #104: đổi số mô phỏng mà vẫn dùng lại bản cũ là lặng lẽ bỏ qua --sims.
    assert cm.needs_refresh(cached, 1000, sims=100)
    assert not cm.needs_refresh(cached, 1000, sims=cm.DEFAULT_SIMS)


def test_load_null_computes_once_then_reads_the_cache(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake(rows, sims, *, workers=4, seed=cm.SEED):
        calls.append(rows)
        return np.zeros((5, len(cm.NAMES)))

    monkeypatch.setattr(cm, "simulate_null", fake)
    first = cm.load_null(tmp_path, 500, sims=5)
    second = cm.load_null(tmp_path, 505, sims=5)
    cm.load_null(tmp_path, 600, sims=5)
    assert calls == [500, 600]
    assert first == second
    assert (tmp_path / cm.OUT / cm.NULL_FILE).exists()


# ---------------------------------------------------------------------------
# Rủi ro, giả thuyết can thiệp, ngày đích
# ---------------------------------------------------------------------------


def test_every_simulated_draw_lands_in_the_risk_table(tmp_path: Path, small_null: dict) -> None:
    """Review PR #104: ô cuối từng chỉ đếm ĐÚNG 5 con về, bỏ rơi 6 trở lên."""
    _store(tmp_path, 700, seed=3, picks=True)
    risk = cm.build_report(tmp_path, small_null)["risk"]
    assert sum(risk["numbers_hit"]) == risk["scenarios"] == 10_000
    assert risk["picks"] == [f"{n:02d}" for n in PICKS]
    assert sum(risk["numbers_hit"][6:]) > 0, "mẫu phải có kỳ về từ 6 con trở lên"


def test_the_published_picks_and_target_date_come_from_the_forecast(tmp_path: Path, small_null: dict) -> None:
    _store(tmp_path, 700, seed=3, picks=True)
    report = cm.build_report(tmp_path, small_null)
    assert report["generated_for"] == (date(2022, 6, 1) + timedelta(days=700)).isoformat()
    published = {(r["mode"], r["number"]) for r in report["matrix"] if r["published"]}
    assert published == {("loto", f"{n:02d}") for n in PICKS} | {("de", "05"), ("de", "50")}


def test_picks_come_from_the_top10_the_pipeline_just_wrote_not_a_stale_forecast(
    tmp_path: Path, small_null: dict
) -> None:
    """Review PR #104: lúc pipeline dựng trang, ``predictions_today.json`` còn
    trỏ vào kỳ vừa quay. Đọc nó thì trang mất mọi con "đang công bố"."""
    _store(tmp_path, 700, seed=3, top10=True)
    report = cm.build_report(tmp_path, small_null)
    published = {(r["mode"], r["number"]) for r in report["matrix"] if r["published"]}
    assert published == ({("loto", f"{n:02d}") for n in TOP10_LOTO}
                         | {("de", f"{n:02d}") for n in TOP10_DE})
    assert report["generated_for"] == (date(2022, 6, 1) + timedelta(days=700)).isoformat()
    assert report["risk"]["picks_source"] == cm.PICK_SOURCES["top10"]


def test_repeat_counts_match_a_plain_loop() -> None:
    rng = np.random.default_rng(12)
    seq = rng.integers(0, 12, size=300)
    loop = sum(int(seq[t] in set(seq[t - 7 : t])) for t in range(7, len(seq)))
    assert int(cm.repeat_counts(seq)[0]) == loop
    draws = rng.integers(0, 30, size=(200, 27))
    loop = sum(int(draws[t, 0] in set(draws[t - 1])) for t in range(1, 200))
    assert int(cm.hot_counts(draws)[0]) == loop


def test_the_avoidance_checks_use_their_own_fair_distribution(tmp_path: Path) -> None:
    """Review PR #104: cửa sổ 7 kỳ chồng nhau nên số lần lặp không theo nhị
    thức. p phải lấy từ chính phân phối của số đếm trên lịch sử công bằng."""
    draws = _store(tmp_path, 700, seed=5)
    raw = pd.read_csv(tmp_path / "xsmb.csv")
    tests = {t["key"]: t for t in cm.intervention_tests(raw, draws, sims=400)["tests"]}
    null = cm.intervention_null(700, 400)
    assert tests["special_repeat"]["p"] == pytest.approx(
        cm.mc_two_sided_p(int(cm.repeat_counts(draws[:, 0])[0]), null["repeat"]))
    assert tests["special_avoids_hot"]["p"] == pytest.approx(
        cm.mc_two_sided_p(int(cm.hot_counts(draws)[0]), null["hot"]))


def test_special_feedback_is_scored_as_one_outcome_in_a_hundred(tmp_path: Path) -> None:
    """Review PR #104: Đặc Biệt từng chấm như 100 biến nhị phân (log-loss ~0,056)
    thay vì một kết quả trong 100 lớp như trang Chất lượng mô hình (log 100)."""
    _store(tmp_path, 60, seed=2)
    frame = pd.read_csv(tmp_path / "xsmb-2-digits.csv", dtype={"date": str})
    (tmp_path / "predict").mkdir(exist_ok=True)
    for day in frame["date"].iloc[-25:]:
        for mode, prob in (("de", 0.01), ("loto", cm.BASE)):
            pd.DataFrame({"number": range(100), "prob": prob}).to_csv(
                tmp_path / "predict" / f"predict_next_{mode}_all_{day}.csv", index=False)
    de = cm._feedback(tmp_path)["modes"]["de"]
    assert de["logloss_base"] == pytest.approx(np.log(100), rel=1e-6)
    assert de["brier_base"] == pytest.approx(0.99)
    assert de["logloss_model"] == pytest.approx(de["logloss_base"])


def test_a_rigged_digit_position_is_flagged_and_a_fair_table_is_not(tmp_path: Path) -> None:
    fair = _store(tmp_path / "fair", 700, seed=5)
    raw = pd.read_csv(tmp_path / "fair" / "xsmb.csv")
    tests = {t["key"]: t for t in cm.intervention_tests(raw, fair, sims=400)["tests"]}
    assert tests["digits"]["p_holm"] > 0.05

    rigged = _store(tmp_path / "rig", 700, seed=5, rig_digit_column="prize3_2")
    raw = pd.read_csv(tmp_path / "rig" / "xsmb.csv")
    tests = {t["key"]: t for t in cm.intervention_tests(raw, rigged, sims=400)["tests"]}
    assert tests["digits"]["p_holm"] < 0.001
    assert "prize3_2[1]" in tests["digits"]["detail"]


# ---------------------------------------------------------------------------
# Trang
# ---------------------------------------------------------------------------


def test_the_page_states_every_tier_and_links_back_to_quality(tmp_path: Path, small_null: dict) -> None:
    import build_confidence_page as page

    data = tmp_path / "data"
    _store(data, 700, seed=11, rig=True, picks=True)
    report = cm.build_report(data, small_null)
    (data / cm.OUT).mkdir(parents=True, exist_ok=True)
    (data / cm.OUT / cm.REPORT_FILE).write_text(json.dumps(report), encoding="utf-8")

    out = page.build(data, tmp_path / "docs")
    text = out.read_text(encoding="utf-8")

    assert out.name == "do-tin-cay.html"
    assert "<title>Độ tin cậy dự báo" in text
    for word in ("Cao", "Trung bình", "Thấp / nhiễu"):
        assert word in text
    from bs4 import BeautifulSoup

    content = BeautifulSoup(text, "html.parser").select_one(".ui-grid")
    # Khung điều hướng cũng trỏ tới trang ấy; chỉ đếm liên kết trong NỘI DUNG.
    assert content.select('a[href="model-quality.html"]')
    assert "(đang công bố)" in text
    assert "vla" not in text.lower()
