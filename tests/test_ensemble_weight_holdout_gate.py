from __future__ import annotations

"""Bộ học trọng số phải CHỨNG MINH được trước khi xuất bản.

Trước đây ``learn_ensemble_weights`` khớp năm trọng số trên TOÀN BỘ ngày rồi
ghi tệp vô điều kiện. Hậu quả đo được trên dữ liệu thật, chế độ đề: vector "đã
học" hơn mặc định 0,30 điểm ở nơi nó được khớp và kém 2,89 điểm ở 214 kỳ nó
chưa từng thấy — và CI đã xuất bản nó.

Hai nhóm phép kiểm ở đây, và cần cả hai mới có nghĩa:

* NHÓM CHỨNG MINH — cắm một tín hiệu đã biết vào lịch sử tổng hợp rồi đòi bộ
  tối ưu tìm ra nó, cổng đề bạt nó, và trọng số đã học thắng mặc định trên một
  lát thứ ba mà cả bộ tối ưu lẫn cổng đều chưa từng thấy.
* NHÓM TỪ CHỐI — cùng bộ sinh ấy với biên độ tín hiệu bằng 0 thì cổng phải từ
  chối.

Thiếu nhóm đầu thì một cổng luôn nói "không" cũng xanh. Thiếu nhóm sau thì một
cổng luôn nói "có" cũng xanh.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from ensemble_utils import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    EnsembleWeights,
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    clip01,
    floor_distribution,
)
from learn_ensemble_weights import (
    COMPONENT_COLS,
    MIN_RELATIVE_GAIN,
    MIN_VALIDATION_DAYS,
    PRIOR_VECTOR,
    _blend,
    _daily_scores,
    _promotion_verdict,
    _weight_vector,
    learn_with_holdout,
)

LOTO_RATE = 23.7657 / 100.0
SRC = Path(__file__).resolve().parents[1] / "src"


def _synthetic(
    mode: str, days: int, *, signal: float, seed: int
) -> tuple[dict[str, np.ndarray], np.ndarray, list[str]]:
    """Lịch sử tổng hợp trong đó CHỈ ``p_cau`` mang tín hiệu, bốn cột kia là nhiễu.

    ``signal`` là phần thông tin thật trộn vào ``p_cau``. Đặt 0 thì cả năm cột
    phải VÔ DỤNG NHƯ NHAU — đó mới là đối chứng âm.

    Tính đối xứng ấy không tự có. Bản đầu của bộ sinh này dựng bốn cột nhiễu
    bằng một phân phối rải đều rồi nhân lên (mỗi ô trong [0; 0,475]) nhưng
    dựng ``p_cau`` quanh đúng tỉ lệ nền, nên ở ``signal=0`` ``p_cau`` là một bộ
    dự đoán HẰNG SỐ tốt hơn hẳn bốn cột kia. Cổng đề bạt 11 trong 12 hạt giống
    — và nó ĐÚNG, vì tỉ lệ nền thật sự tổng quát hoá được. Lỗi nằm ở phép kiểm.
    Ở đây cả năm cột dùng CÙNG bộ sinh, chỉ ``p_cau`` được cộng thêm tín hiệu.
    """
    rng = np.random.default_rng(seed)
    day_list = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(days)]

    if mode == "loto":
        y = (rng.random((days, 100)) < LOTO_RATE).astype(float)
        arrays = {
            c: np.clip(LOTO_RATE + 0.02 * rng.standard_normal((days, 100)), 0.01, 0.99)
            for c in COMPONENT_COLS
        }
        arrays["p_cau"] = np.clip(arrays["p_cau"] + signal * (y - LOTO_RATE), 0.01, 0.99)
        return arrays, y, day_list

    winners = rng.integers(0, 100, size=days)
    y = np.zeros((days, 100), dtype=float)
    y[np.arange(days), winners] = 1.0
    arrays = {}
    for column in COMPONENT_COLS:
        base = np.full((days, 100), 0.01) + 0.002 * rng.standard_normal((days, 100))
        arrays[column] = np.clip(base, 1e-4, None)
    arrays["p_cau"][np.arange(days), winners] += signal
    for column in COMPONENT_COLS:
        arrays[column] /= arrays[column].sum(axis=1, keepdims=True)
    return arrays, y, day_list


def _mean_logloss(mode: str, arrays: dict[str, np.ndarray], y: np.ndarray, w: EnsembleWeights) -> float:
    return float(np.mean(_daily_scores(mode, _blend(arrays, _weight_vector(w)), y)[0]))


def _slice(arrays: dict[str, np.ndarray], sl: slice) -> dict[str, np.ndarray]:
    return {c: arrays[c][sl] for c in COMPONENT_COLS}


# ---------------------------------------------------------------- điểm chấm


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_daily_scores_match_a_straight_reference(mode: str) -> None:
    """Bản vector hoá phải trùng khít bản viết thẳng bằng chính hàm trợ giúp.

    Đây là bản đã thay vòng lặp ngày bằng phép toán ma trận VÀ đổi phép chặn
    của đề từ ``clip01(..., 1e-12)`` sang ``floor_distribution``. Cả hai thay
    đổi đều phải nhìn thấy được, nên bản tham chiếu dưới đây dựng lại đúng
    ngữ nghĩa MỚI bằng các hàm đã có sẵn.
    """
    arrays, y, _ = _synthetic(mode, 12, signal=0.3, seed=7)
    p_blend = _blend(arrays, PRIOR_VECTOR)
    logloss, brier = _daily_scores(mode, p_blend, y)

    if mode == "de":
        y_idx = np.argmax(y, axis=1)
        ref_ll = [categorical_logloss(floor_distribution(p_blend[i]), int(y_idx[i])) for i in range(len(y))]
        ref_br = [categorical_brier(floor_distribution(p_blend[i]), int(y_idx[i])) for i in range(len(y))]
    else:
        p_clip = clip01(p_blend, eps=1e-6)
        ref_ll = [bernoulli_logloss(p_clip[i], y[i]) for i in range(len(y))]
        ref_br = [bernoulli_brier(p_clip[i], y[i]) for i in range(len(y))]

    np.testing.assert_allclose(logloss, ref_ll, rtol=0, atol=1e-12)
    np.testing.assert_allclose(brier, ref_br, rtol=0, atol=1e-12)


def test_de_scoring_uses_the_floor_the_prediction_path_uses() -> None:
    """Không con nào được coi là bất khả thi khi chấm điểm bộ tối ưu.

    Nếu bộ chấm chỉ chặn ở 1e-12 thì một kỳ mà con về bị gán 0 vào logloss là
    ~27,6; đường dự đoán thật áp sàn nên chỉ trả 7,6. Bộ tối ưu học hàm mục
    tiêu nào thì nó tối ưu hàm ấy, nên hai con số này phải là một.
    """
    p = np.zeros((1, 100))
    p[0, 0] = 1.0
    y = np.zeros((1, 100))
    y[0, 50] = 1.0

    logloss = _daily_scores("de", p, y)[0][0]
    assert logloss == pytest.approx(-np.log(0.05 / 100.0), rel=1e-12)
    assert logloss < 10.0


def test_the_optimizer_prior_is_the_documented_default() -> None:
    """Vector khởi đầu phải LÀ trọng số mặc định, không phải bản chép tay."""
    np.testing.assert_allclose(PRIOR_VECTOR, _weight_vector(DEFAULT_ENSEMBLE_WEIGHTS))


# ------------------------------------------------------- nhóm CHỨNG MINH


@pytest.mark.parametrize(
    ("mode", "signal", "seed"),
    [("loto", 0.45, 11), ("de", 0.06, 11)],
    ids=["loto", "de"],
)
def test_it_recovers_an_injected_signal_and_generalizes(mode: str, signal: float, seed: int) -> None:
    """Cắm tín hiệu vào ``p_cau`` thì phải tìm ra nó VÀ tổng quát hoá được.

    Lát thứ ba (``holdout``) không được bộ tối ưu khớp và cũng không được cổng
    chấm, nên nó là bằng chứng ngoài mẫu thật. Ba điều phải cùng đúng:

    1. cổng đề bạt,
    2. khối lượng dồn về ``p_cau`` chứ không rải đều,
    3. trọng số đã học thắng mặc định TRÊN LÁT THỨ BA.
    """
    arrays, y, day_list = _synthetic(mode, 60, signal=signal, seed=seed)
    fit, holdout = slice(0, 40), slice(40, 60)

    learned, audit = learn_with_holdout(
        mode, _slice(arrays, fit), y[fit], day_list[:40], 45, DEFAULT_ENSEMBLE_WEIGHTS
    )

    assert audit.promoted, f"cổng từ chối một tín hiệu có thật: {audit.describe()}"
    assert learned.as_dict() != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    assert learned.w_cau > 0.5, f"khối lượng không dồn về p_cau: {learned.as_dict()}"

    out_arrays, out_y = _slice(arrays, holdout), y[holdout]
    learned_ll = _mean_logloss(mode, out_arrays, out_y, learned)
    default_ll = _mean_logloss(mode, out_arrays, out_y, DEFAULT_ENSEMBLE_WEIGHTS)
    assert learned_ll < default_ll, (
        f"đề bạt rồi mà lát thứ ba vẫn tệ hơn mặc định: {learned_ll:.6f} >= {default_ll:.6f}"
    )


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_the_promoted_weights_beat_the_default_on_unseen_days_across_seeds(mode: str) -> None:
    """Không phải may một hạt giống: mọi lần đề bạt đều phải tổng quát hoá.

    Đo trên nhiều hạt giống và đòi bất biến "đã đề bạt thì phải thắng ngoài
    mẫu" đúng ở MỌI lần, đồng thời đòi có ít nhất vài lần đề bạt — nếu không
    thì phép kiểm rỗng.
    """
    signal = 0.45 if mode == "loto" else 0.06
    promotions = 0
    for seed in range(20, 32):
        arrays, y, day_list = _synthetic(mode, 60, signal=signal, seed=seed)
        learned, audit = learn_with_holdout(
            mode, _slice(arrays, slice(0, 40)), y[:40], day_list[:40], 45, DEFAULT_ENSEMBLE_WEIGHTS
        )
        if not audit.promoted:
            continue
        promotions += 1
        out = _slice(arrays, slice(40, 60))
        assert _mean_logloss(mode, out, y[40:], learned) < _mean_logloss(
            mode, out, y[40:], DEFAULT_ENSEMBLE_WEIGHTS
        ), f"hạt {seed}: đề bạt mà ngoài mẫu vẫn tệ hơn mặc định"

    assert promotions >= 8, f"chỉ đề bạt {promotions}/12 lần trên tín hiệu có thật"


# ---------------------------------------------------------- nhóm TỪ CHỐI


@pytest.mark.parametrize(
    ("mode", "days", "min_refusals"),
    [("loto", 40, 24), ("de", 20, 22)],
    ids=["loto", "de"],
)
def test_pure_noise_is_not_promoted(mode: str, days: int, min_refusals: int) -> None:
    """Đối chứng âm: không tín hiệu thì không đề bạt, và ghi lại mặc định.

    Đây là chính lỗi đã xuất bản: trên nhiễu, bộ tối ưu vẫn tìm được một vector
    hơn mặc định TRONG MẪU, và bản cũ ghi nó ra.

    Số kỳ và ngưỡng đều lấy từ SỐ ĐO, không đặt tay. Đo 24 hạt giống, so bản
    đúng với bản đột biến "bỏ holdout, khớp trên toàn bộ ngày":

        loto  40 kỳ   đúng từ chối 24/24   đột biến từ chối 24/24
        đề    20 kỳ   đúng từ chối 23/24   đột biến từ chối 17/24

    Hai điều đọc được từ bảng này. Một, chỉ chế độ ĐỀ ở đúng cửa sổ sản xuất
    (20 kỳ) mới phân biệt được có holdout hay không: mỗi kỳ đề chỉ mang MỘT
    quan sát, còn mỗi kỳ loto mang 100, nên năm trọng số không đủ tự do để quá
    khớp 4 000 quan sát nhị phân. Chạy phép kiểm này chỉ với loto là chạy một
    phép kiểm không thể đỏ. Hai, ngưỡng của đề là 22 chứ không phải 24, vì một
    ca dương giả trên 24 lần ở mức tin cậy 95% là đúng như thiết kế; ngưỡng 22
    nằm giữa 17 và 23 nên nó phân biệt được hai bản.
    """
    refusals = 0
    for seed in range(40, 64):
        arrays, y, day_list = _synthetic(mode, days, signal=0.0, seed=seed)
        learned, audit = learn_with_holdout(
            mode, arrays, y, day_list, 45, DEFAULT_ENSEMBLE_WEIGHTS
        )
        if audit.promoted:
            continue
        refusals += 1
        assert learned.as_dict() == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()

    assert refusals >= min_refusals, f"chỉ từ chối {refusals}/24 lần trên nhiễu thuần"


def test_an_overfit_incumbent_is_reverted_not_kept() -> None:
    """Vector quá khớp đã lọt ra phải BỊ TRẢ VỀ mặc định, không nằm lại.

    Đường cơ sở là mặc định chứ không phải đương nhiệm, vì đương nhiệm được
    khớp ở lần chạy trước trên cửa sổ có chứa lát thẩm định lần này. Đo được
    trên dữ liệu thật: lấy đương nhiệm làm cơ sở thì chính vector quá khớp
    ngày 2026-09-20 "thắng" mặc định (4,60488 so với 4,60683) nhờ đã thấy
    trước đúng 8 kỳ ấy.
    """
    overfit = EnsembleWeights(w_ml=0.2813, w_cau=0.367, w_stat=0.0, w_active=0.0235, w_stable=0.3282)
    arrays, y, day_list = _synthetic("de", 40, signal=0.0, seed=99)

    learned, audit = learn_with_holdout("de", arrays, y, day_list, 45, overfit)

    assert not audit.promoted
    assert audit.baseline == "mac_dinh"
    assert learned.as_dict() == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    assert learned.as_dict() != overfit.as_dict()


def test_a_validation_window_below_the_minimum_changes_nothing() -> None:
    """Không đo được thì không sửa: giữ nguyên vector đang có hiệu lực.

    Khác với trường hợp đo được rồi từ chối — ở đó mặc định được ghi lại. Ở đây
    chưa có phép đo nào nên mọi thay đổi đều là đoán.
    """
    in_force = EnsembleWeights(w_ml=0.5, w_cau=0.5, w_stat=0.0, w_active=0.0, w_stable=0.0)
    days = int(np.ceil(MIN_VALIDATION_DAYS / 0.4)) - 2
    arrays, y, day_list = _synthetic("loto", days, signal=0.9, seed=5)

    learned, audit = learn_with_holdout("loto", arrays, y, day_list, 45, in_force)

    assert audit.validation_days < MIN_VALIDATION_DAYS
    assert not audit.promoted
    assert learned.as_dict() == in_force.as_dict()
    assert learned.as_dict() != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()


# ------------------------------------------------------------- đầu ra tệp


def test_the_written_file_records_the_refusal(tmp_path: Path) -> None:
    """Lời từ chối phải NHÌN THẤY ĐƯỢC trên đĩa, không im lặng.

    Một cổng im lặng không phân biệt được với một cổng không tồn tại: cả hai
    đều để lại tệp mang trọng số mặc định.
    """
    days = [f"2026-04-{d:02d}" for d in range(1, 26)]
    rng = np.random.default_rng(3)
    rows = []
    for day in days:
        for number in range(100):
            rows.append(
                {
                    "target_date": day,
                    "number": number,
                    "y": float(rng.random() < LOTO_RATE),
                    **{c: float(rng.random() * 0.4 + 0.05) for c in COMPONENT_COLS},
                }
            )
    hist_dir = tmp_path / "history"
    hist_dir.mkdir()
    import pandas as pd

    pd.DataFrame(rows).to_csv(hist_dir / "pred_loto.csv", index=False)

    out_dir = tmp_path / "data" / "ensemble"
    subprocess.run(
        [
            sys.executable,
            str(SRC / "learn_ensemble_weights.py"),
            "--mode", "loto",
            "--history-dir", str(hist_dir),
            "--out-dir", str(out_dir),
            "--window-days", "180",
            "--min-days", "20",
            "--half-life-days", "45",
        ],
        check=True,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True,
    )

    blob = json.loads((out_dir / "weights_loto.json").read_text(encoding="utf-8"))
    promotion = blob["promotion"]
    assert promotion["promoted"] is False
    assert promotion["baseline"] == "mac_dinh"
    assert promotion["validation_days"] >= MIN_VALIDATION_DAYS
    assert promotion["train_days"] > promotion["validation_days"]
    assert set(promotion["validation_logloss"]) == {"mac_dinh", "dang_hieu_luc", "ung_vien"}
    assert promotion["reason"]
    assert blob["weights"] == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()


# --------------------------------------------------------- luật quyết định


def test_a_tiny_but_certain_gain_is_refused() -> None:
    """CÓ ý nghĩa thống kê mà KHÔNG đổi quyết định nào thì không đề bạt.

    Ca này không dựng được bằng dữ liệu tổng hợp: đo tới 120 kỳ với tám biên
    độ tín hiệu, không hạt giống nào cho "khoảng tin cậy loại trừ 0 mà lợi
    dưới 0,2%", vì khoảng tin cậy trên 8-48 kỳ còn rộng hơn chính ngưỡng ấy.
    Nên nếu chỉ kiểm qua dữ liệu thì bỏ sàn độ lớn hiệu ứng đi cũng không phép
    kiểm nào đỏ — đó là lý do luật quyết định được tách ra và ghim ở đây.
    """
    promoted, reason = _promotion_verdict(1e-7, -1e-9)
    assert not promoted
    assert "sàn" in reason


def test_a_large_but_uncertain_gain_is_refused() -> None:
    """Biên 20% mà khoảng tin cậy còn chạm 0 thì vẫn là may mắn."""
    promoted, reason = _promotion_verdict(0.20, 0.01)
    assert not promoted
    assert "KTC95" in reason


def test_a_gain_exactly_at_the_floor_with_a_clear_interval_is_promoted() -> None:
    """Đúng sàn là ĐẠT, không phải thiếu — ghim cả chiều so sánh ``>=``."""
    assert _promotion_verdict(MIN_RELATIVE_GAIN, -0.01)[0]
    assert not _promotion_verdict(np.nextafter(MIN_RELATIVE_GAIN, 0.0), -0.01)[0]


def test_the_effect_size_floor_is_above_zero() -> None:
    """Sàn độ lớn hiệu ứng phải là số dương thật, không phải 0 trang trí."""
    assert MIN_RELATIVE_GAIN > 0.0


def test_the_fitting_slice_ends_before_the_validation_slice_begins() -> None:
    """Lát khớp phải đứng TRƯỚC lát thẩm định, và điều đó phải kiểm được.

    Đây là bất biến duy nhất ở tệp này không thể kiểm bằng số đo: trên dữ liệu
    dừng, đảo hai lát cho kết quả thống kê không phân biệt nổi — đo thử với
    tín hiệu chỉ có ở nửa đầu, ở nửa sau, hay ở cả hai, cổng đều ra cùng quyết
    định. Nên nó được ghim bằng CẤU TRÚC: ranh giới hai lát nằm trong dấu vết.
    """
    arrays, y, day_list = _synthetic("loto", 40, signal=0.45, seed=13)
    _, audit = learn_with_holdout("loto", arrays, y, day_list, 45, DEFAULT_ENSEMBLE_WEIGHTS)

    assert audit.train_days + audit.validation_days == len(day_list)
    assert audit.train_last_day == day_list[audit.train_days - 1]
    assert audit.validation_first_day == day_list[audit.train_days]
    assert audit.train_last_day < audit.validation_first_day


@pytest.mark.parametrize(
    "scramble",
    [
        lambda d: d[24:] + d[:24],
        lambda d: list(reversed(d)),
        lambda d: d[:20] + [d[20]] + d[20:-1],
    ],
    ids=["xoay vòng", "đảo ngược", "trùng lặp"],
)
def test_an_unsorted_day_list_is_refused_rather_than_leaked(scramble) -> None:
    """Ngày chưa sắp là rò rỉ nhìn-trước im lặng, nên phải nổ chứ không chạy.

    Phép XOAY VÒNG là ca đáng kể: nó vẫn để hai ngày ở ranh giới tăng dần, nên
    một chốt chặn chỉ nhìn ranh giới sẽ cho nó đi qua trong khi lát khớp đã
    chứa 16 kỳ đứng SAU toàn bộ lát thẩm định.
    """
    arrays, y, day_list = _synthetic("loto", 40, signal=0.45, seed=13)

    with pytest.raises(ValueError, match="sắp tăng dần"):
        learn_with_holdout("loto", arrays, y, scramble(day_list), 45, DEFAULT_ENSEMBLE_WEIGHTS)
