"""Kiểm thành phần tín hiệu thống kê — module trước đó ở mức phủ 0 %.

Đây là một trong những khối nuôi thẳng vào bảng xếp hạng dự đoán, nên thứ
đáng khoá nhất không phải con số cụ thể mà là các tính chất AN TOÀN: trọng số
phải nghiêng về kỳ GẦN, hậu nghiệm thứ phải đọc thứ của NGÀY ĐÍCH chứ không
phải ngày neo, xác suất đề phải cộng đúng 1, và lịch gãy phải báo lỗi to chứ
không lặng lẽ chạy tiếp.

Không phép kiểm nào ở đây khẳng định mô hình dự đoán đúng. Chúng chỉ khẳng
định nó không tự mâu thuẫn và không đọc ngược thời gian.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import statistical_signal  # noqa: E402
from statistical_signal import (  # noqa: E402
    _de_posterior,
    _de_signal,
    _effective_n,
    _exp_weights,
    _js_divergence,
    _logit,
    _loto_signal,
    build_statistical_signal,
)


# --- Trọng số theo tuổi ----------------------------------------------------


def test_exponential_weights_favour_the_most_recent_draw() -> None:
    """Kỳ GẦN NHẤT có trọng số 1.0, càng lùi về quá khứ càng nhẹ.

    Đảo chiều dãy này là lỗi không bao giờ nổ: mô hình vẫn chạy, vẫn ra số,
    chỉ là nó học lịch sử xa nhất và bỏ qua hiện tại.
    """
    w = _exp_weights(5, half_life=2)

    assert w[-1] == pytest.approx(1.0), "kỳ mới nhất là mốc"
    assert np.all(np.diff(w) > 0), "trọng số phải tăng dần về phía hiện tại"
    assert w[-3] / w[-1] == pytest.approx(0.5), "lùi đúng một chu kỳ bán rã thì còn một nửa"
    assert w[-5] / w[-1] == pytest.approx(0.25), "lùi hai chu kỳ thì còn một phần tư"


def test_half_life_is_floored_at_one_so_weights_stay_finite() -> None:
    """Chu kỳ bán rã 0 sẽ chia cho 0; hàm phải kẹp sàn thay vì trả inf/NaN."""
    w = _exp_weights(4, half_life=0)
    assert np.all(np.isfinite(w))
    assert w[-1] == pytest.approx(1.0)


def test_effective_sample_size_equals_n_only_when_weights_are_flat() -> None:
    """ESS trả lời "thực chất có bao nhiêu kỳ đang đóng góp".

    Trọng số đều thì bằng đúng số kỳ; càng dồn vào ít kỳ thì càng nhỏ hơn.
    Dùng thẳng n thay cho ESS sẽ thổi phồng độ tin cậy của khoảng khả tín.
    """
    assert _effective_n(np.ones(10)) == pytest.approx(10.0)

    skewed = np.array([1e-9, 1e-9, 1e-9, 1.0])
    assert _effective_n(skewed) < 1.1, "gần như chỉ một kỳ đóng góp"
    assert _effective_n(np.zeros(5)) == 0.0, "không trọng số thì không có mẫu"


# --- Biến đổi số học -------------------------------------------------------


def test_logit_clips_the_ends_instead_of_returning_infinity() -> None:
    """0 và 1 là giá trị hợp lệ của xác suất thực nghiệm.

    Không kẹp thì logit ra +/-inf, và độ lệch chuẩn của ba cửa sổ — vốn dùng
    để đo độ ổn định — biến thành NaN cho đúng những con cực đoan nhất.
    """
    out = _logit(np.array([0.0, 0.5, 1.0]))
    assert np.all(np.isfinite(out))
    assert out[1] == pytest.approx(0.0)
    assert out[0] < 0 < out[2]


def test_js_divergence_is_zero_for_identical_and_maximal_for_disjoint() -> None:
    """JS đo mức trôi giữa hai phân phối: 0 khi trùng, ln2 khi rời hẳn nhau."""
    p = np.full(100, 0.01)
    assert _js_divergence(p, p) == pytest.approx(0.0, abs=1e-12)

    a = np.zeros(100)
    a[3] = 1.0
    b = np.zeros(100)
    b[77] = 1.0
    assert _js_divergence(a, b) == pytest.approx(np.log(2.0), rel=1e-6)
    assert _js_divergence(a, b) == pytest.approx(_js_divergence(b, a)), "JS đối xứng"


def test_divergence_is_computed_on_normalised_distributions() -> None:
    """Nhân đôi mọi thành phần không làm phân phối thay đổi, nên JS phải bằng 0."""
    p = np.arange(1, 101, dtype=float)
    assert _js_divergence(p, p * 2.0) == pytest.approx(0.0, abs=1e-12)


# --- Hậu nghiệm đề ---------------------------------------------------------


def test_de_posterior_is_a_proper_distribution_over_the_hundred_numbers() -> None:
    """Đề là bài toán một-trong-một-trăm: xác suất phải cộng đúng 1."""
    onehot = np.zeros((5, 100))
    onehot[np.arange(5), [3, 3, 7, 7, 7]] = 1.0
    p, low, high = _de_posterior(onehot, np.ones(5), prior_strength=10.0)

    assert p.sum() == pytest.approx(1.0)
    assert np.all(p > 0), "tiên nghiệm giữ cho con chưa về vẫn có xác suất dương"
    assert p[7] > p[3] > p[0], "về nhiều hơn thì xác suất cao hơn"
    assert np.all(low <= p) and np.all(p <= high), "khoảng khả tín phải bao lấy ước lượng"


def test_de_posterior_shrinks_toward_uniform_as_the_prior_grows() -> None:
    """Tiên nghiệm mạnh kéo hậu nghiệm về đều — đó là chốt chống khớp quá mức."""
    onehot = np.zeros((5, 100))
    onehot[np.arange(5), 7] = 1.0

    weak = _de_posterior(onehot, np.ones(5), prior_strength=1.0)[0]
    strong = _de_posterior(onehot, np.ones(5), prior_strength=10_000.0)[0]

    assert weak[7] > strong[7]
    assert strong[7] == pytest.approx(0.01, abs=2e-3), "gần như đều hẳn"


# --- Hậu nghiệm thứ trong tuần ---------------------------------------------


def _weekday_history(weekday_only: int, number: int, *, weeks: int = 20) -> tuple[np.ndarray, pd.Series]:
    """Lịch sử mà ``number`` CHỈ về vào đúng một thứ trong tuần."""
    dates = pd.date_range("2026-01-05", periods=weeks * 7, freq="D")  # bắt đầu thứ Hai
    hit = np.zeros((len(dates), 100), dtype=np.int8)
    hit[:, 50] = 1  # một con nền để baseline khác 0
    for i, day in enumerate(dates):
        if day.weekday() == weekday_only:
            hit[i, number] = 1
    return hit, pd.Series(dates)


def test_weekday_posterior_reads_the_weekday_it_is_given() -> None:
    """Con chỉ về thứ Hai phải có hậu nghiệm thứ cao ở thứ Hai và thấp ở thứ Ba."""
    hit, dates = _weekday_history(weekday_only=0, number=7)

    monday = _loto_signal(hit, dates, 0, half_life=45, prior_strength=10.0)
    tuesday = _loto_signal(hit, dates, 1, half_life=45, prior_strength=10.0)

    assert float(monday.loc[7, "weekday_prob"]) > 0.6
    assert float(tuesday.loc[7, "weekday_prob"]) < 0.1
    assert int(monday.loc[7, "weekday_trials"]) == 20


# --- Co về nền -------------------------------------------------------------


def test_loto_probability_is_shrunk_toward_the_baseline_never_past_it() -> None:
    """``stability`` nằm trong (0, 1], nên xác suất chỉ CO về nền chứ không vọt qua.

    Nếu hệ số ấy vượt 1, một con lô hiếm có thể bị đẩy sang phía bên kia nền —
    đổi hẳn dấu của bằng chứng.
    """
    rng = np.random.default_rng(11)
    dates = pd.Series(pd.date_range("2026-01-01", periods=200, freq="D"))
    hit = (rng.random((200, 100)) < 0.22).astype(np.int8)

    out = _loto_signal(hit, dates, 2, half_life=45, prior_strength=80.0)
    baseline = float(out["baseline_prob"].iloc[0])

    assert np.all(out["stability"].to_numpy() > 0.0)
    assert np.all(out["stability"].to_numpy() <= 1.0)
    assert np.all(out["prob"].to_numpy() > 0.0)
    assert np.all(out["prob"].to_numpy() < 1.0)

    raw = 0.55 * out["ewm_prob"] + 0.25 * out["weekday_prob"] + 0.20 * out["p90"]
    assert np.all(
        np.abs(out["prob"] - baseline) <= np.abs(raw - baseline) + 1e-12
    ), "co về nền, không được nới ra xa"
    assert np.all(np.sign(out["prob"] - baseline) * np.sign(raw - baseline) >= 0), (
        "co về nền không được đổi dấu bằng chứng"
    )


def test_de_signal_stays_a_distribution_after_shrinkage() -> None:
    onehot = np.zeros((120, 100))
    onehot[np.arange(120), np.arange(120) % 100] = 1.0
    dates = pd.Series(pd.date_range("2026-01-01", periods=120, freq="D"))

    out = _de_signal(onehot, dates, 3, half_life=45, prior_strength=80.0)
    assert out["prob"].sum() == pytest.approx(1.0)
    assert float(out["stability"].iloc[0]) <= 1.0


# --- Toàn tuyến ------------------------------------------------------------


class _FakeLottery:
    def __init__(self, two: pd.DataFrame, sparse: pd.DataFrame) -> None:
        self._two, self._sparse = two, sparse

    def load(self) -> None:
        return None

    def get_2_digits_data(self) -> pd.DataFrame:
        return self._two.copy()

    def get_sparse_data(self) -> pd.DataFrame:
        return self._sparse.copy()


def _synthetic_history(
    *, start: str = "2025-01-01", days: int = 400, monday_only: int | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lịch sử giả liền ngày, hai khung khớp trục thời gian."""
    rng = np.random.default_rng(7)
    dates = pd.date_range(start, periods=days, freq="D")
    two_rows, sparse_rows = [], []
    for day in dates:
        numbers = rng.integers(0, 100, size=27)
        if monday_only is not None and day.weekday() == 0:
            numbers[5] = monday_only
        two_rows.append(
            {
                "date": day,
                "special": int(numbers[0]),
                **{f"p{i}": int(v) for i, v in enumerate(numbers[1:], start=1)},
            }
        )
        counts = np.bincount(numbers, minlength=100)
        sparse_rows.append({"date": day, **{n: int(counts[n]) for n in range(100)}})
    return pd.DataFrame(two_rows), pd.DataFrame(sparse_rows)


@pytest.fixture()
def _install(monkeypatch: pytest.MonkeyPatch):
    def _install_history(two: pd.DataFrame, sparse: pd.DataFrame) -> None:
        monkeypatch.setattr(
            statistical_signal, "Lottery", lambda: _FakeLottery(two, sparse)
        )

    return _install_history


def test_target_is_the_day_after_the_anchor(_install) -> None:
    """Neo là kỳ cuối đã có; đích là ngày kế tiếp — chưa ai biết kết quả."""
    two, sparse = _synthetic_history(start="2025-01-01", days=400)
    _install(two, sparse)

    _df, diag = build_statistical_signal("loto")
    last = two["date"].max().date()
    assert diag["anchor_date"] == last.isoformat()
    assert diag["target_date"] == (last + pd.Timedelta(days=1)).isoformat()


def test_weekday_posterior_follows_the_target_day_not_the_anchor_day(_install) -> None:
    """Đây là bẫy lệch một ngày cổ điển của mọi đặc trưng theo thứ.

    Lịch sử kết thúc đúng Chủ nhật, nên NGÀY ĐÍCH là thứ Hai còn NGÀY NEO là
    Chủ nhật. Con 42 được cài chỉ về vào thứ Hai. Đọc đúng thứ của ngày đích
    thì hậu nghiệm thứ của nó phải vọt lên; đọc nhầm thứ của ngày neo thì nó
    tụt xuống mức nền.

    Ngưỡng ở đây không phải 1.0 dù 42 về đủ MỌI thứ Hai: tiên nghiệm mạnh
    (``prior_strength`` 80) cố tình kéo hậu nghiệm xuống, và đó là chủ ý chống
    khớp quá mức. Cái đáng khoá là khoảng cách, nên phép kiểm so 42 với chính
    99 con còn lại thay vì với một hằng số tự đặt.
    """
    two, sparse = _synthetic_history(start="2025-01-06", days=364, monday_only=42)
    assert two["date"].max().weekday() == 6, "lịch sử phải kết thúc vào Chủ nhật"
    _install(two, sparse)

    df, _diag = build_statistical_signal("loto")
    row = df[df["number"] == 42].iloc[0]
    others = df[df["number"] != 42]["weekday_prob"].to_numpy(dtype=float)

    assert float(row["weekday_prob"]) > float(others.max()) * 1.5, (
        "42 phải tách hẳn khỏi 99 con không có nhịp thứ Hai"
    )
    assert float(row["weekday_prob"]) > float(row["p365"]) * 1.5, (
        "nhịp thứ Hai phải nổi lên trên chính tần suất chung của con ấy"
    )


def test_de_output_is_a_distribution_and_loto_output_is_not(_install) -> None:
    """Hai chế độ trả lời hai câu hỏi khác nhau, nên chuẩn hoá khác nhau.

    Đề: một trong một trăm — tổng phải bằng 1. Lô: mỗi con về hay không là
    một câu hỏi riêng — tổng vượt 1 là đúng, ép nó về 1 mới là sai.
    """
    two, sparse = _synthetic_history()
    _install(two, sparse)

    de, _ = build_statistical_signal("de")
    assert de["prob"].sum() == pytest.approx(1.0)

    loto, _ = build_statistical_signal("loto")
    assert loto["prob"].sum() > 5.0
    assert np.all((loto["prob"] > 0) & (loto["prob"] < 1))


def test_rows_come_back_ranked_by_probability(_install) -> None:
    two, sparse = _synthetic_history()
    _install(two, sparse)

    df, _ = build_statistical_signal("loto")
    probs = df["prob"].to_numpy()
    assert np.all(np.diff(probs) <= 1e-15), "bảng phải đã xếp hạng sẵn"
    assert df["number_str"].tolist() == [f"{int(n):02d}" for n in df["number"]]


def test_a_calendar_hole_fails_closed_instead_of_being_silently_spanned(
    _install,
) -> None:
    """Mọi cách diễn giải ngày/độ trễ/cửa sổ ở đây đều giả định lịch liền ngày.

    Lịch thủng mà vẫn chạy thì "30 ngày gần nhất" lặng lẽ trở thành một quãng
    dài hơn 30 ngày, và mọi con số phía sau đều lệch mà không dấu vết.

    ``number_dynamics`` phía dưới cũng có chốt riêng, nên một lỗ lịch không lọt
    được đằng nào. Chính vì thế phép kiểm bám vào CHUỖI NGỮ CẢNH: nó phải
    chứng minh module NÀY tự chặn ở đầu vào, chứ không phải nó chạy nửa đường
    rồi mới bị lớp dưới bắt lại.
    """
    two, sparse = _synthetic_history(days=120)
    two = two.drop(index=60).reset_index(drop=True)
    sparse = sparse.drop(index=60).reset_index(drop=True)
    _install(two, sparse)

    with pytest.raises(
        ValueError, match="statistical signal two-digit history requires contiguous"
    ):
        build_statistical_signal("loto")


def test_two_histories_that_disagree_on_dates_are_rejected(_install) -> None:
    """Hai khung lệch trục thời gian thì mọi phép ghép hàng đều so sai kỳ."""
    two, sparse = _synthetic_history(days=120)
    sparse["date"] = sparse["date"] + pd.Timedelta(days=1)
    _install(two, sparse)

    with pytest.raises(ValueError, match="not date-aligned"):
        build_statistical_signal("loto")


def test_empty_history_is_refused_rather_than_producing_a_prior_only_ranking(
    _install,
) -> None:
    """Không có dữ liệu thì bảng phát ra sẽ thuần tiên nghiệm — vô nghĩa mà
    trông y hệt một bảng thật."""
    _install(pd.DataFrame(columns=["date", "special"]), pd.DataFrame(columns=["date"]))
    with pytest.raises(RuntimeError, match="No lottery data"):
        build_statistical_signal("loto")


def test_an_unknown_mode_is_rejected(_install) -> None:
    two, sparse = _synthetic_history(days=120)
    _install(two, sparse)
    with pytest.raises(ValueError):
        build_statistical_signal("dac_biet")
