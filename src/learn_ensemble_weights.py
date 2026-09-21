from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from calibration import select_calibration
from ensemble_components import COMPONENT_KEYS, availability_from_history_day
from ensemble_utils import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    PROBABILITY_FLOOR_SHARE,
    EnsembleWeights,
    clip01,
    load_ensemble_weights,
    weight_grid,
)

COMPONENT_COLS = [f"p_{key}" for key in COMPONENT_KEYS]

#: Tỉ lệ ngày dành cho phép KHỚP; phần còn lại là lát thẩm định ngoài mẫu.
TRAIN_FRACTION: Final[float] = 0.6

#: Số ngày thẩm định tối thiểu để phép so sánh có nghĩa. Dưới mức này thì
#: không đề bạt, vì năm trọng số khớp trên vài kỳ thì sai số chuẩn của hiệu
#: logloss lớn hơn chính hiệu đó.
MIN_VALIDATION_DAYS: Final[int] = 8

#: Sàn ĐỘ LỚN HIỆU ỨNG: phải hơn đường cơ sở ít nhất 0,2% logloss tương đối.
#: Có ý nghĩa thống kê không đồng nghĩa với có ý nghĩa thực tế — một khoảng
#: tin cậy hẹp vẫn có thể loại trừ số không với hiệu 1e-8, tức không đổi quyết
#: định nào.
MIN_RELATIVE_GAIN: Final[float] = 0.002

#: Số lần lấy lại mẫu cho khoảng tin cậy bắt cặp. Đơn vị lấy mẫu là NGÀY: các
#: kỳ quay độc lập với nhau, còn 100 con trong cùng một kỳ thì không.
BOOTSTRAP_DRAWS: Final[int] = 2000
BOOTSTRAP_SEED: Final[int] = 20260921


def _select_recent_complete_days(
    df: pd.DataFrame, window_days: int, *, mode: str | None = None
) -> list[str]:
    """Select only fully labeled days with five genuinely available components.

    Explicit ``has_*`` flags are honored for new history.  Legacy history without
    those flags is validated from probability content, so an old all-zero missing
    placeholder can no longer masquerade as a complete model prediction.
    """
    if "target_date" not in df.columns or "y" not in df.columns:
        return []
    if any(c not in df.columns for c in COMPONENT_COLS):
        return []

    complete: list[str] = []
    for day, sub in df.groupby("target_date", sort=True):
        if len(sub) != 100 or not sub["y"].notna().all():
            continue
        numbers = pd.to_numeric(sub.get("number"), errors="coerce")
        if numbers.isna().any() or set(numbers.astype(int).tolist()) != set(range(100)):
            continue
        available = availability_from_history_day(sub, mode=mode)
        if all(available.get(key, False) for key in COMPONENT_KEYS):
            complete.append(str(day))

    complete.sort()
    return complete if window_days <= 0 else complete[-window_days:]


def _stack_days(
    df: pd.DataFrame, days: Sequence[str]
) -> tuple[dict[str, np.ndarray], np.ndarray, list[str]]:
    """Xếp lịch sử thành ma trận ``(số ngày, 100)`` cho từng thành phần.

    Bản trước lọc lại cả bảng bên trong vòng lặp ngày
    (``df[df["target_date"].astype(str) == d]``), tức mỗi ngày quét trọn N hàng
    VÀ dựng lại ``astype(str)`` trên toàn cột. Vì N = số ngày × 100, chi phí là
    O(số ngày²). Đo được: 10 lần nhiều ngày hơn thì chậm 56 lần.

    Ở đây chuẩn hoá khoá MỘT lần rồi gom bằng một lượt ``groupby``, nên chi phí
    tuyến tính theo số hàng. Cùng phép đo: 10 lần nhiều ngày hơn thì chậm 9,5
    lần, và ở 2 000 ngày là nhanh hơn 72 lần với kết quả trùng khít.

    ``_select_recent_complete_days`` đã bảo đảm mỗi ngày đúng 100 hàng mang
    trọn số 00-99, nên phép gán vào ma trận không cần canh lại kích thước.
    """
    wanted = set(days)
    work = df.assign(_day=df["target_date"].astype(str))
    work = work[work["_day"].isin(wanted)].sort_values(["_day", "number"], kind="stable")

    day_list = sorted(wanted.intersection(work["_day"].unique()))
    index_of = {day: i for i, day in enumerate(day_list)}
    arrays = {c: np.zeros((len(day_list), 100), dtype=np.float64) for c in COMPONENT_COLS}
    labels = np.zeros((len(day_list), 100), dtype=np.float64)

    for day, sub in work.groupby("_day", sort=False):
        row = index_of[day]
        for column in COMPONENT_COLS:
            arrays[column][row] = sub[column].to_numpy(dtype=np.float64)
        labels[row] = sub["y"].to_numpy(dtype=np.float64)
    return arrays, labels, day_list


def _day_weights(days: list[str], half_life_draws: int) -> np.ndarray:
    """Trọng số giảm dần theo độ tuổi, tính bằng SỐ KỲ chứ không phải ngày lịch.

    Args:
        days: Danh sách ngày quay đã sắp tăng dần; chỉ độ DÀI được dùng.
        half_life_draws: Sau ngần này KỲ thì trọng số còn một nửa.

    Returns:
        Mảng trọng số đã chuẩn hoá về trung bình 1.

    Cờ dòng lệnh mang tên ``--half-life-days`` nhưng ``age`` ở đây là khoảng
    cách CHỈ SỐ HÀNG, tức số kỳ quay. Hai đơn vị không đổi lẫn nhau được: lịch
    sử trải 2 446 ngày lịch trên 2 397 kỳ, và tuổi theo lịch lớn hơn tuổi theo
    kỳ trung vị 12 đơn vị, tối đa 50. Đo trên chính dữ liệu này, đặt nửa đời 30
    thì hai cách cho trọng số lệch trung vị 9,6 % và tối đa 44,6 %.

    Đếm theo kỳ là lựa chọn hợp lý cho xổ số — mỗi kỳ là một quan sát, và một
    đợt nghỉ Tết không làm quan sát nào cũ đi. Nhưng ``meta_predictor
    ._recency_row_weights`` nhận tham số CÙNG TÊN mà lại tính
    ``(latest - d).days``, tức ngày lịch thật. Ghi rõ ở cả hai nơi để không ai
    đọc một chỗ rồi suy ra chỗ kia.
    """
    if half_life_draws <= 0:
        return np.ones(len(days), dtype=float)
    age = np.arange(len(days) - 1, -1, -1, dtype=float)
    lam = np.log(2.0) / float(half_life_draws)
    w = np.exp(-lam * age)
    return w / np.mean(w)


def _weight_vector(w: EnsembleWeights) -> np.ndarray:
    return np.array([w.w_ml, w.w_cau, w.w_stat, w.w_active, w.w_stable], dtype=float)


def _weights_from_vector(x: np.ndarray) -> EnsembleWeights:
    return EnsembleWeights(
        w_ml=float(x[0]),
        w_cau=float(x[1]),
        w_stat=float(x[2]),
        w_active=float(x[3]),
        w_stable=float(x[4]),
    ).normalized()


#: Điểm khởi đầu và tâm của hình phạt co về. Lấy thẳng từ trọng số mặc định
#: của kho thay vì chép lại con số — trước đây vector này nằm cứng ở hai chỗ
#: trong tệp, nên sửa mặc định ở ``ensemble_utils`` mà quên ở đây là hai nguồn
#: sự thật lệch nhau.
PRIOR_VECTOR: Final[np.ndarray] = _weight_vector(DEFAULT_ENSEMBLE_WEIGHTS)


def _blend(arrays: dict[str, np.ndarray], x: np.ndarray) -> np.ndarray:
    out = x[0] * arrays[COMPONENT_COLS[0]]
    for i in range(1, len(COMPONENT_COLS)):
        out = out + x[i] * arrays[COMPONENT_COLS[i]]
    return out


def _daily_scores(mode: str, p_blend: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """LogLoss và Brier THEO TỪNG NGÀY, chưa lấy trung bình.

    Trả về theo ngày chứ không trả về một con số, vì cổng đề bạt cần bắt cặp
    từng ngày để lấy khoảng tin cậy bootstrap. Trung bình hoá là việc của người
    gọi.

    Đề dùng ``floor_distribution`` — ĐÚNG phép biến đổi mà đường dự đoán thật
    áp lên vector đề ở ``predict_nextday_2d``. Bản trước chỉ chặn ở 1e-12, tức
    bộ tối ưu học một hàm mục tiêu KHÁC hàm mà hệ thống thật phải trả giá: một
    ngày mà con về bị thành phần nào đó gán 0 sẽ vào logloss là 27,6 trong khi
    thực tế chỉ là 7,6. Chênh lệch ấy đủ để kéo trọng số về phía thành phần
    tình cờ không gán 0, chứ không phải thành phần dự đoán đúng.
    """
    probs = np.asarray(p_blend, dtype=np.float64)
    labels = np.asarray(y, dtype=np.float64)
    n_outcomes = probs.shape[1]
    rows = np.arange(probs.shape[0])

    if mode == "de":
        totals = probs.sum(axis=1, keepdims=True)
        safe = np.where(totals > 0.0, totals, 1.0)
        q = np.where(totals > 0.0, probs / safe, 1.0 / n_outcomes)
        q = (1.0 - PROBABILITY_FLOOR_SHARE) * q + PROBABILITY_FLOOR_SHARE / n_outcomes
        hit = q[rows, np.argmax(labels, axis=1)]
        logloss = -np.log(np.clip(hit, 1e-12, 1.0))
        brier = np.sum(q * q, axis=1) - 2.0 * hit + 1.0
        return logloss, brier

    p = clip01(probs, eps=1e-6)
    logloss = -np.mean(labels * np.log(p) + (1.0 - labels) * np.log(1.0 - p), axis=1)
    brier = np.mean((p - labels) ** 2, axis=1)
    return logloss, brier


def _optimize_weights_continuous(
    mode: str,
    arrays: dict[str, np.ndarray],
    y: np.ndarray,
    w_day: np.ndarray,
) -> tuple[EnsembleWeights, float, float]:
    """Optimize five non-negative weights on the simplex using recent LogLoss."""
    try:
        from scipy.optimize import minimize
    except Exception:  # pragma: no cover
        minimize = None

    def eval_scores(w: np.ndarray) -> tuple[float, float]:
        w = np.clip(w, 0.0, 1.0)
        total = float(np.sum(w))
        w = PRIOR_VECTOR if total <= 0 else w / total
        logloss, brier = _daily_scores(mode, _blend(arrays, w), y)
        return float(np.average(logloss, weights=w_day)), float(np.average(brier, weights=w_day))

    if minimize is None:
        best_w: EnsembleWeights | None = None
        best_ll, best_br = float("inf"), float("inf")
        for w in weight_grid(step=0.10):
            ll, br = eval_scores(_weight_vector(w))
            if ll < best_ll - 1e-9 or (abs(ll - best_ll) <= 1e-9 and br < best_br):
                best_w, best_ll, best_br = w, ll, br
        if best_w is None:
            raise RuntimeError("ensemble weight grid unexpectedly produced no candidates")
        return best_w.normalized(), best_ll, best_br

    def obj(x: np.ndarray) -> float:
        return eval_scores(x)[0] + 0.025 * float(np.square(x - PRIOR_VECTOR).sum())

    res = minimize(
        obj,
        x0=PRIOR_VECTOR.copy(),
        bounds=[(0.0, 0.60)] * 5,
        constraints=({"type": "eq", "fun": lambda x: np.sum(x) - 1.0},),
        method="SLSQP",
        options={"maxiter": 250},
    )
    x = res.x if res.success else PRIOR_VECTOR.copy()
    x = np.clip(x, 0.0, 1.0)
    x = x / max(float(x.sum()), 1e-12)
    ll, br = eval_scores(x)
    return _weights_from_vector(x), ll, br


@dataclass(frozen=True)
class PromotionAudit:
    """Dấu vết của quyết định đề bạt, để lời TỪ CHỐI cũng nhìn thấy được."""

    promoted: bool
    reason: str
    baseline: str
    train_days: int
    validation_days: int
    train_last_day: str
    validation_first_day: str
    validation_logloss: dict[str, float]
    relative_gain: float
    delta_ci95_low: float
    delta_ci95_high: float

    def describe(self) -> str:
        if not self.promoted:
            return (
                f"KHÔNG đề bạt trọng số mới ({self.reason}); giữ '{self.baseline}'. "
                f"Thẩm định {self.validation_days} kỳ: "
                f"{self.validation_logloss} — lợi tương đối {self.relative_gain:+.4%}, "
                f"KTC95 hiệu [{self.delta_ci95_low:+.6f}; {self.delta_ci95_high:+.6f}]"
            )
        return (
            f"ĐỀ BẠT trọng số mới; đường cơ sở '{self.baseline}'. "
            f"Khớp {self.train_days} kỳ, thẩm định {self.validation_days} kỳ: "
            f"{self.validation_logloss} — lợi tương đối {self.relative_gain:+.4%}, "
            f"KTC95 hiệu [{self.delta_ci95_low:+.6f}; {self.delta_ci95_high:+.6f}]"
        )


def _paired_bootstrap_ci(
    diff: np.ndarray, *, draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED
) -> tuple[float, float]:
    """Khoảng tin cậy 95% của hiệu logloss trung bình, lấy lại mẫu THEO NGÀY.

    Bắt cặp theo ngày nên nhiễu chung của ngày (kỳ dễ, kỳ khó) bị triệt tiêu.
    Lấy lại mẫu theo ngày mà không theo con là bắt buộc: tổng biên của một kỳ
    bị luật trò chơi chặn ở 27 giải, nên 100 con trong cùng kỳ phụ thuộc nhau
    và lấy mẫu theo con sẽ cho khoảng hẹp giả tạo.
    """
    values = np.asarray(diff, dtype=np.float64)
    if values.size == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, values.size, size=(int(draws), values.size))
    means = values[picks].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def _promotion_verdict(gain: float, ci_high: float) -> tuple[bool, str]:
    """Ba điều kiện đề bạt, tách riêng khỏi phần lấy dữ liệu.

    Tách ra vì đây là chỗ DUY NHẤT mang quyết định, và chỉ ở dạng tách rời mới
    ghim được hai ca đối nghịch mà dữ liệu tổng hợp không dựng nổi:

    * lợi 1e-7 với khoảng tin cậy siêu hẹp — CÓ ý nghĩa thống kê, KHÔNG đổi
      quyết định nào. Đây là lý do sàn độ lớn hiệu ứng tồn tại. Đo được: trên
      dữ liệu tổng hợp tới 120 kỳ, không hạt giống nào rơi vào ca này vì
      khoảng tin cậy trên 8-48 kỳ còn rộng hơn 0,2% logloss, nên nếu chỉ kiểm
      qua dữ liệu thì bỏ sàn đi cũng không phép kiểm nào đỏ.
    * lợi 20% với khoảng tin cậy chạm 0 — biên lớn nhưng chưa loại trừ được
      may mắn.

    Args:
        gain: Phần logloss giảm được so với đường cơ sở, tính tương đối.
        ci_high: Cận TRÊN của khoảng tin cậy 95% cho hiệu logloss trung bình
            (ứng viên trừ đường cơ sở), nên âm mới là tốt hơn.

    Returns:
        Quyết định và lý do bằng tiếng Việt để ghi vào dấu vết.
    """
    if gain < MIN_RELATIVE_GAIN:
        return False, f"biên thắng {gain:+.4%} chưa đạt sàn {MIN_RELATIVE_GAIN:.2%}"
    if not ci_high < 0.0:
        return False, f"KTC95 của hiệu chưa loại trừ số không (cận trên {ci_high:+.6f})"
    return True, "thắng đường cơ sở ngoài mẫu, đạt sàn hiệu ứng và KTC loại trừ số không"


def learn_with_holdout(
    mode: str,
    arrays: dict[str, np.ndarray],
    y: np.ndarray,
    day_list: Sequence[str],
    half_life_draws: int,
    incumbent: EnsembleWeights,
) -> tuple[EnsembleWeights, PromotionAudit]:
    """Khớp trên lát đầu, chấm điểm trên lát cuối, chỉ đề bạt khi thắng thật.

    Đây là chỗ hổng mà cả kho không có: ``bong_bridge_lab`` cắt
    train/validation/holdout, ``ml_validation.assert_temporal_partitions`` cấm
    trộn thời gian, ``calibration.select_calibration`` giữ lại một lát để chấm
    điểm — nhưng bộ học trọng số thì khớp trên TOÀN BỘ ngày rồi ghi VÔ ĐIỀU
    KIỆN. Đo được hậu quả trên chính dữ liệu đang chạy, chế độ đề:

        trong mẫu (20 kỳ đã khớp)      mặc định -0,056%   đã học +0,239%
        ngoài mẫu (214 kỳ còn lại)     mặc định -2,240%   đã học -5,126%

    Tức vector "đã học" hơn mặc định 0,30 điểm ở nơi nó được khớp và kém 2,89
    điểm ở nơi nó chưa từng thấy. Đó là dấu hiệu quá khớp sách vở, và CI đã
    xuất bản nó ngày 2026-09-20.

    Ba điều kiện để đề bạt, phải đạt cả ba:

    1. Thắng đường cơ sở về logloss trên lát thẩm định.
    2. Biên thắng đạt sàn độ lớn hiệu ứng ``MIN_RELATIVE_GAIN``.
    3. Khoảng tin cậy bootstrap bắt cặp của hiệu loại trừ số không.

    Đường cơ sở là trọng số MẶC ĐỊNH, không phải trọng số đang có hiệu lực, và
    đây là điểm dễ làm sai nhất. Vector đang có hiệu lực được khớp ở lần chạy
    trước trên một cửa sổ 180 kỳ gần nhất, tức nó ĐÃ THẤY gần hết lát thẩm định
    của lần chạy này. Đo được: lấy nó làm đường cơ sở thì chính vector quá khớp
    ngày 2026-09-20 "thắng" mặc định trên lát thẩm định (4,60488 so với
    4,60683) — nó thắng vì đã khớp trên đúng 8 kỳ ấy, chứ không vì dự đoán
    đúng. Chỉ vector mặc định là chưa từng khớp trên dữ liệu nào, nên chỉ nó
    mới là đường cơ sở sạch.

    Hệ quả là cổng tự chữa: khi không có bằng chứng ngoài mẫu cho vector đã
    học, tệp được ghi lại bằng mặc định. Một vector quá khớp lọt ra trước đó
    biến mất ngay lần chạy sau thay vì nằm lại vì "đang là đương nhiệm". Giá
    phải trả là một vector tốt cũng phải chứng minh lại mỗi lần chạy — đúng
    chiều thận trọng, vì mỗi lần chạy có cửa sổ mới.

    ``dang_hieu_luc`` vẫn được chấm và ghi vào dấu vết, nhưng CHỈ để tham
    khảo: con số ấy có thể là trong mẫu.

    Args:
        mode: ``loto`` hoặc ``de``.
        arrays: Ma trận ``(số kỳ, 100)`` cho từng thành phần.
        y: Nhãn ``(số kỳ, 100)``.
        day_list: Ngày đã sắp TĂNG DẦN, cùng thứ tự với hàng của ``arrays``.
        half_life_draws: Nửa đời theo số kỳ cho trọng số hồi quy gần.
        incumbent: Trọng số đang có hiệu lực trên đĩa.

    Returns:
        Trọng số nên ghi, kèm dấu vết quyết định.
    """
    # Chốt chặn RÒ RỈ NHÌN-TRƯỚC, và đặt TRƯỚC mọi nhánh trả về sớm.
    # `_stack_days` trả về ngày đã sắp, nhưng hàm này nhận `day_list` từ bên
    # ngoài và một danh sách chưa sắp sẽ khiến lát khớp chứa ngày đứng SAU lát
    # thẩm định mà không phép đo thống kê nào phát hiện được — trên dữ liệu
    # dừng, đảo hai lát cho kết quả không phân biệt nổi. Nên bất biến này phải
    # kiểm bằng CẤU TRÚC, và kiểm cả danh sách chứ không chỉ ở ranh giới: một
    # phép xoay vòng vẫn có thể để ranh giới tăng dần trong khi cả dãy thì
    # không.
    keys = [str(d) for d in day_list]
    if any(b <= a for a, b in zip(keys, keys[1:], strict=False)):
        raise ValueError("day_list phải sắp tăng dần và không trùng lặp")

    n_days = len(day_list)
    split = int(round(n_days * TRAIN_FRACTION))
    train = slice(0, split)
    valid = slice(split, n_days)
    n_valid = n_days - split

    if split <= 0 or n_valid < MIN_VALIDATION_DAYS:
        return incumbent, PromotionAudit(
            promoted=False,
            reason=f"lát thẩm định chỉ có {max(n_valid, 0)} kỳ, cần {MIN_VALIDATION_DAYS}",
            baseline="dang_hieu_luc",
            train_days=max(split, 0),
            validation_days=max(n_valid, 0),
            train_last_day="",
            validation_first_day="",
            validation_logloss={},
            relative_gain=float("nan"),
            delta_ci95_low=float("nan"),
            delta_ci95_high=float("nan"),
        )

    train_last, valid_first = keys[split - 1], keys[split]
    arrays_train = {c: arrays[c][train] for c in COMPONENT_COLS}
    arrays_valid = {c: arrays[c][valid] for c in COMPONENT_COLS}
    y_train, y_valid = y[train], y[valid]

    w_train = _day_weights(list(day_list[train]), half_life_draws)
    candidate, _, _ = _optimize_weights_continuous(mode, arrays_train, y_train, w_train)

    def validation_daily(w: EnsembleWeights) -> np.ndarray:
        return _daily_scores(mode, _blend(arrays_valid, _weight_vector(w)), y_valid)[0]

    baseline_name = "mac_dinh"
    daily = {
        baseline_name: validation_daily(DEFAULT_ENSEMBLE_WEIGHTS),
        "dang_hieu_luc": validation_daily(incumbent),
        "ung_vien": validation_daily(candidate),
    }
    logloss = {name: float(np.mean(values)) for name, values in daily.items()}

    base_ll = logloss[baseline_name]
    cand_ll = logloss["ung_vien"]
    gain = (base_ll - cand_ll) / base_ll if base_ll > 0 else 0.0
    low, high = _paired_bootstrap_ci(daily["ung_vien"] - daily[baseline_name])

    promoted, reason = _promotion_verdict(gain, high)
    audit = PromotionAudit(
        promoted=promoted,
        reason=reason,
        baseline=baseline_name,
        train_days=split,
        validation_days=n_valid,
        train_last_day=train_last,
        validation_first_day=valid_first,
        validation_logloss=logloss,
        relative_gain=float(gain),
        delta_ci95_low=low,
        delta_ci95_high=high,
    )
    return (candidate if promoted else DEFAULT_ENSEMBLE_WEIGHTS), audit


def main() -> None:
    ap = argparse.ArgumentParser(description="Learn five-component ensemble weights from labeled walk-forward history.")
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--history-dir", default="data/history")
    ap.add_argument("--out-dir", default="data/ensemble")
    ap.add_argument("--window-days", type=int, default=180)
    ap.add_argument("--min-days", type=int, default=20)
    # Tên cờ giữ nguyên vì pipeline.py và scripts/release_check.sh đang truyền
    # nó; đơn vị THẬT là số kỳ quay, xem chú thích của _day_weights.
    ap.add_argument("--half-life-days", type=int, default=45)
    args = ap.parse_args()

    hist = Path(args.history_dir) / f"pred_{args.mode}.csv"
    if not hist.exists():
        print(f"[SKIP] history not found: {hist}")
        return
    df = pd.read_csv(hist)
    days = _select_recent_complete_days(df, args.window_days, mode=args.mode)
    if len(days) < args.min_days:
        print(f"[SKIP] five-component labeled history not mature: {len(days)} < {args.min_days}; keeping current/default weights")
        return

    arrays, y, day_list = _stack_days(df, days)
    out_dir = Path(args.out_dir)
    incumbent = load_ensemble_weights(out_dir.parent, args.mode)
    final_w, audit = learn_with_holdout(
        args.mode, arrays, y, day_list, args.half_life_days, incumbent
    )

    w_day = _day_weights(day_list, args.half_life_days)
    in_sample_ll, in_sample_br = (
        float(np.average(values, weights=w_day))
        for values in _daily_scores(args.mode, _blend(arrays, _weight_vector(final_w)), y)
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    weights_path = out_dir / f"weights_{args.mode}.json"
    payload = {
        "schema_version": 7,
        "mode": args.mode,
        "learned_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window_days": args.window_days,
        "half_life_days": args.half_life_days,
        "days_used": day_list,
        "component_availability_required": True,
        "metric": {"logloss": in_sample_ll, "brier": in_sample_br},
        "promotion": asdict(audit),
        "weights": final_w.as_dict(),
    }
    weights_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] five-component weights for {args.mode} -> {weights_path}")
    print(f"[OK] {audit.describe()}")

    # Chọn phương pháp hiệu chuẩn bằng SỐ ĐO thay vì mặc định cứng.
    #
    # Ứng viên `identity` là điểm chính: trước đây không gì kiểm xem phép hiệu
    # chuẩn có LÀM TỆ ĐI hay không, và một cửa sổ lệch hoặc trôi khái niệm có
    # thể khiến nó đẩy xác suất đi sai hướng mãi mà không ai biết. Cửa sổ quá
    # ngắn thì bộ chọn tự giữ nguyên hành vi cũ và ghi `selected: false`.
    #
    # Hiệu chuẩn khớp trên CHÍNH trọng số sắp được xuất bản, nên phải dùng
    # `final_w` chứ không phải ứng viên: khi cổng từ chối đề bạt, khớp theo ứng
    # viên bị loại sẽ cho một phép hiệu chuẩn lệch khỏi vector đang chạy.
    calib, calib_audit = select_calibration(
        args.mode, _blend(arrays, _weight_vector(final_w)), y, w_day
    )
    calib_path = out_dir / f"calibration_{args.mode}.json"
    calib_payload = {
        "schema_version": 7,
        "mode": args.mode,
        "learned_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window_days": args.window_days,
        "half_life_days": args.half_life_days,
        "component_availability_required": True,
        "params": calib.as_dict(),
        "selection": {
            "chosen": calib_audit.chosen,
            "selected": calib_audit.selected,
            "brier_by_candidate": calib_audit.brier_by_candidate,
            "fit_days": calib_audit.fit_days,
            "holdout_days": calib_audit.holdout_days,
        },
    }
    calib_path.write_text(json.dumps(calib_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] calibration -> {calib_path}")
    print(f"[OK] {calib_audit.describe()}")


if __name__ == "__main__":
    main()
