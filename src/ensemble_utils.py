from __future__ import annotations

import json
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
from typing import Final, Iterable

import numpy as np
import pandas as pd

from xsmb_domain import LOTO_BASELINE_RATE

#: Trọng số khi CHƯA học được: cầu 0,30 / thống kê 0,20 / ML 0,25 / hai nhánh
#: cầu 0,125 mỗi bên. Đây là giá trị đặt tay, không phải kết quả tối ưu.
#: Phiên bản lược đồ tối thiểu của ``weights_<mode>.json`` được phép dùng.
MIN_WEIGHTS_SCHEMA: Final[int] = 5


def ensure_full_probs(df: pd.DataFrame) -> np.ndarray:
    """Return length-100 probability vector indexed by number 0..99."""
    p = np.zeros(100, dtype=np.float64)
    if df is None or df.empty:
        return p
    nums = df["number"].astype(int).to_numpy()
    probs = df["prob"].astype(float).to_numpy()
    mask = (nums >= 0) & (nums < 100)
    p[nums[mask]] = probs[mask]
    return p


def normalize_distribution(p: np.ndarray) -> np.ndarray:
    values = np.asarray(p, dtype=np.float64)
    if values.size == 0:
        raise ValueError("probability distribution must not be empty")
    if not np.isfinite(values).all() or bool((values < 0.0).any()):
        raise ValueError("probability distribution must be finite and non-negative")
    s = float(np.sum(values))
    if s <= 0:
        return np.full(values.shape, 1.0 / values.size, dtype=np.float64)
    return values / s


#: Sàn xác suất, tính theo tỉ lệ của mức đều. Với 100 con, ``0.05`` nghĩa là
#: không con nào được nhận dưới 5% của 1/100, tức 0,0005.
#:
#: Vì sao cần sàn: một thành phần có thể là ĐIỂM XẾP HẠNG chứ không phải phân
#: phối. Đo được trên lịch sử: ``p_stable`` của Đặc Biệt gán ĐÚNG 0 cho trung
#: vị 58/100 con mỗi kỳ, và trong 128 trong 231 kỳ nó gán 0 cho chính con đã
#: về. Gán xác suất 0 cho biến cố rồi biến cố xảy ra là phát biểu tệ nhất có
#: thể — logloss bằng vô cực.
#:
#: Hôm nay đường dự đoán KHÔNG hỏng: cả 100 con nằm trong [0,009773; 0,010236]
#: vì `p_cau`/`p_stat` đã có từ 2026-08-12 và che hết chỗ 0 của `stable`. Nhưng
#: đó là may, không phải thiết kế — nó đã hỏng suốt 212 kỳ khi hai thành phần
#: ấy vắng, và chỉ cần một tệp thiếu là hỏng lại.
PROBABILITY_FLOOR_SHARE: Final[float] = 0.05


def floor_distribution(
    p: np.ndarray, *, share: float = PROBABILITY_FLOOR_SHARE
) -> np.ndarray:
    """Chuẩn hoá và đặt SÀN, để không kết cục nào bị tuyên bố là bất khả thi.

    Trộn với phân phối đều theo tỉ lệ ``share`` — đúng dạng làm trơn
    Laplace/Jeffreys. Giữ nguyên thứ hạng của mọi con, chỉ chặn đuôi dưới.

    Đo được: là phép KHÔNG LÀM GÌ khi đầu vào đã lành (dự đoán 2026-09-18 đổi
    không quá 5% tương đối), nhưng chặn đứng trường hợp thảm hoạ.

    Args:
        p: Vector xác suất chưa hoặc đã chuẩn hoá.
        share: Tỉ lệ khối lượng dành cho phân phối đều.

    Returns:
        Phân phối đã chuẩn hoá, mọi phần tử ``>= share / n``.
    """
    if not 0.0 <= share < 1.0:
        raise ValueError("share must lie in [0, 1)")
    values = normalize_distribution(p)
    if share == 0.0:
        return values
    return (1.0 - share) * values + share / values.size


def clip01(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.clip(p, eps, 1.0 - eps)


#: Biên của mọi xác suất LOTO đã chốt — cùng ``eps`` với ``clip01``.
_PROB_LO: Final[float] = 1e-6
_PROB_HI: Final[float] = 1.0 - 1e-6


def anchor_loto_level(p: np.ndarray) -> np.ndarray:
    """Neo TỔNG xác suất LOTO về số con khác nhau kỳ vọng mỗi kỳ: ``Σp = 100·nền``.

    Mỗi kỳ có đúng 27 giải, nên số con 00–99 khác nhau về là ``Σ_n y_n`` với kỳ
    vọng ``100·(1 − 0,99²⁷) ≈ 23,77`` — 4 225 kỳ lịch sử đo 23,83 ± 0,02; chênh
    0,3% ấy đổi logloss chưa tới 10⁻⁶ nats mỗi số, nên neo theo mức lý thuyết.
    Vector nào có tổng khác con số ấy là SAI MỨC ở mọi con cùng lúc, bất kể
    thứ hạng đúng hay sai. Đặc Biệt có ràng buộc tương tự là tổng bằng 1
    (``floor_distribution``); LOTO trước đây không có.

    Đo walk-forward 1 000 kỳ (kỳ đích 25-12-2023 → 04-10-2026): hai nhánh cầu vị
    trí có tổng trung vị 24,49 (active) và 26,47 (stable) — lời nguyền người thắng
    của việc chọn top quy tắc — nên tổ hợp trọng số mặc định ra tổng 24,22 và kém
    dự báo hằng số z = −3,33. Chỉ neo mức đã đưa nó về z = +1,76; neo xong, từng
    nhánh cầu vị trí cũng về ngang hằng số (z = −0,06 và −0,03;
    ``scripts/benchmark_component_trust.py``).

    Nhân cùng một hệ số nên giữ nguyên thứ hạng của mọi con. Nhận vector 100 số
    hoặc ma trận ``(kỳ, 100)``; hàng có tổng 0 nhận đúng tỉ lệ nền. Hàng mà phép
    nhân đẩy một số ra ngoài ``[1e-6, 1 − 1e-6]`` đi qua ``_bounded_level``, để
    phép chặn biên không âm thầm phá tổng đã hứa.
    """
    values = np.asarray(p, dtype=np.float64)
    total = values.sum(axis=-1, keepdims=True)
    target = values.shape[-1] * LOTO_BASELINE_RATE
    safe = np.where(total > 0.0, total, 1.0)
    scaled = np.where(total > 0.0, values * (target / safe), LOTO_BASELINE_RATE)
    inside = np.all((scaled >= _PROB_LO) & (scaled <= _PROB_HI), axis=-1)
    if np.all(inside):
        return scaled
    rows = scaled.reshape(-1, values.shape[-1])
    raw = values.reshape(-1, values.shape[-1])
    for index in np.flatnonzero(~np.asarray(inside).reshape(-1)):
        rows[index] = _bounded_level(raw[index], target)
    return rows.reshape(values.shape)


def _bounded_level(row: np.ndarray, target: float) -> np.ndarray:
    """``clip(c·row, lo, hi)`` với hệ số ``c`` chọn để tổng đúng bằng ``target``.

    Tổng ấy tăng đơn điệu theo ``c`` nên tìm ``c`` bằng chia đôi; thứ hạng vẫn
    giữ (không nghiêm ở chỗ chạm biên). Khi chính phép nhân không đủ — các số
    dương đều chạm trần mà tổng vẫn thiếu, như vector ``[1, 0, …, 0]`` — phần còn
    thiếu chia đều cho các số bằng 0: không có bằng chứng nào phân biệt chúng.
    """
    positive = row > 0.0
    ceiling = positive.sum() * _PROB_HI + (~positive).sum() * _PROB_LO
    if ceiling < target:
        out = np.where(positive, _PROB_HI, 0.0)
        out[~positive] = (target - out.sum()) / max(int((~positive).sum()), 1)
        return out
    low, high = 0.0, _PROB_HI / float(row[positive].min())
    for _ in range(200):
        middle = 0.5 * (low + high)
        if np.clip(middle * row, _PROB_LO, _PROB_HI).sum() < target:
            low = middle
        else:
            high = middle
    return np.clip(high * row, _PROB_LO, _PROB_HI)


def finalize_blend(p: np.ndarray, mode: str) -> np.ndarray:
    """Phép chốt của tổ hợp tuyến tính TRƯỚC hiệu chuẩn — một nguồn cho mọi nơi.

    Đường dự đoán thật (``predict_nextday_2d``), bộ học trọng số và hiệu chuẩn,
    tầng xếp chồng, trang Chất lượng và bảng đóng góp thành phần đều phải chấm
    ĐÚNG vector mà hệ thống xuất bản. Trước đây năm nơi ấy tự chép phép chốt;
    chép là để chúng trôi khỏi nhau.
    """
    if mode == "de":
        return floor_distribution(p)
    if mode == "loto":
        return anchor_loto_level(p)
    raise ValueError("mode must be 'loto' or 'de'")


def sigmoid(x: np.ndarray) -> np.ndarray:
    """Numerically stable logistic.

    ``1/(1+exp(-x))`` evaluates ``exp(+|x|)`` for negative inputs and overflows
    to a RuntimeWarning (and, on some builds, a spurious ``inf``) once
    ``x < -709``.  Branching on the sign keeps every exponent negative.
    """
    values = np.asarray(x, dtype=np.float64)
    out = np.empty_like(values)
    positive = values >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_x = np.exp(values[~positive])
    out[~positive] = exp_x / (1.0 + exp_x)
    return out


def logit(p: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    p = np.clip(p, eps, 1.0 - eps)
    return np.log(p / (1.0 - p))


def softmax_from_logp(logp: np.ndarray) -> np.ndarray:
    m = np.max(logp)
    ex = np.exp(logp - m)
    s = np.sum(ex)
    if s <= 0:
        return np.full_like(ex, 1.0 / len(ex))
    return ex / s


@dataclass(frozen=True)
class EnsembleWeights:
    w_ml: float
    w_cau: float = 0.0
    w_stat: float = 0.0
    w_active: float = 0.0
    w_stable: float = 0.0

    def normalized(self) -> "EnsembleWeights":
        arr = np.array(
            [self.w_ml, self.w_cau, self.w_stat, self.w_active, self.w_stable],
            dtype=float,
        )
        if not np.isfinite(arr).all():
            raise ValueError("ensemble weights must be finite")
        arr = np.clip(arr, 0.0, 1.0)
        total = float(arr.sum())
        if total <= 0:
            arr[:] = 0.20
        else:
            arr /= total
        return EnsembleWeights(w_ml=float(arr[0]), w_cau=float(arr[1]), w_stat=float(arr[2]), w_active=float(arr[3]), w_stable=float(arr[4]))

    def as_dict(self) -> dict:
        w = self.normalized()
        return {"w_ml": w.w_ml, "w_cau": w.w_cau, "w_stat": w.w_stat, "w_active": w.w_active, "w_stable": w.w_stable}


DEFAULT_ENSEMBLE_WEIGHTS = EnsembleWeights(
    w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125
)


def load_ensemble_weights(data_dir: Path, mode: str) -> EnsembleWeights:
    """Trọng số tổ hợp đang có hiệu lực cho ``mode``, hoặc mặc định.

    NGUỒN SỰ THẬT DUY NHẤT, và đó là toàn bộ lý do hàm này tồn tại. Trước đây
    hai nơi tự đọc tệp theo hai cách: ``predict_nextday_2d`` canh
    ``schema_version >= 5`` và đòi có ``w_stat``, còn ``model_quality`` đọc
    thẳng không canh gì. Tệp trên đĩa là bản cũ 3 thành phần không có
    ``schema_version``, nên hai nơi nhận hai vector khác nhau:

        trang Chất lượng   w_ml 0,9987  cầu 0     thống kê 0
        dự đoán thật       w_ml 0,2500  cầu 0,30  thống kê 0,20

    Lệch 0,75 — ba phần tư khối lượng trọng số. Hệ quả: trang Chất lượng mô
    hình chấm điểm hiệu chuẩn, độ nhọn và phân rã Murphy cho một mô hình
    KHÔNG được xuất bản.

    Args:
        data_dir: Thư mục ``data`` của kho.
        mode: ``loto`` hoặc ``de``.

    Returns:
        Trọng số đã chuẩn hoá; mặc định nếu tệp thiếu, sai lược đồ, hoặc hỏng.
    """
    path = Path(data_dir) / "ensemble" / f"weights_{mode}.json"
    if not path.exists():
        return DEFAULT_ENSEMBLE_WEIGHTS

    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        weights = blob.get("weights", {})
        schema = blob.get("schema_version")
        if (
            isinstance(schema, bool)
            or not isinstance(schema, Integral)
            or schema < MIN_WEIGHTS_SCHEMA
            or "w_stat" not in weights
        ):
            return DEFAULT_ENSEMBLE_WEIGHTS
        return EnsembleWeights(
            w_ml=float(weights.get("w_ml", DEFAULT_ENSEMBLE_WEIGHTS.w_ml)),
            w_cau=float(weights.get("w_cau", DEFAULT_ENSEMBLE_WEIGHTS.w_cau)),
            w_stat=float(weights.get("w_stat", DEFAULT_ENSEMBLE_WEIGHTS.w_stat)),
            w_active=float(weights.get("w_active", DEFAULT_ENSEMBLE_WEIGHTS.w_active)),
            w_stable=float(weights.get("w_stable", DEFAULT_ENSEMBLE_WEIGHTS.w_stable)),
        ).normalized()
    except (AttributeError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return DEFAULT_ENSEMBLE_WEIGHTS


def weights_provenance(data_dir: Path, mode: str) -> dict:
    """Trọng số đang có hiệu lực, kèm LÝ DO vì sao nó là nó.

    Ba xuất xứ, không phải hai, và phải đọc từ hồ sơ chứ không suy từ giá trị:

    * ``da_hoc`` — vector đã học và đã vượt cổng thẩm định ngoài mẫu.
    * ``bi_tu_choi`` — cổng ĐÃ ĐO rồi từ chối đề bạt, nên tệp mang đúng trọng
      số mặc định. Tệp hoàn toàn lành.
    * ``khong_co_ho_so`` — không có tệp, sai lược đồ, hoặc tệp ghi trước khi
      có cổng.

    Hai trạng thái giữa cho CÙNG một bộ trọng số hiển thị, nên phép suy từ giá
    trị không phân biệt được chúng: nó báo "tệp trọng số thiếu hoặc sai lược
    đồ" cho một tệp hợp lệ lược đồ 7 — đổ lỗi cho tệp trong khi tệp không có
    lỗi gì, và che mất việc hệ thống đã đo và đã từ chối.

    Hàm này sống ở tầng dữ liệu chứ không ở tầng trình bày. Nó từng là
    ``build_dashboard._effective_weights``, nên nó biến mất cùng giao diện —
    trong khi sự thật nó mô tả thì không phụ thuộc vào giao diện nào.

    Args:
        data_dir: Thư mục ``data`` của kho.
        mode: ``loto`` hoặc ``de``.

    Returns:
        Trọng số đang hiệu lực, mã xuất xứ, lý do, và số đo thẩm định nếu có.
    """
    effective = load_ensemble_weights(data_dir, mode)
    path = Path(data_dir) / "ensemble" / f"weights_{mode}.json"
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}

    out: dict = {"mode": mode, "weights": effective.as_dict()}
    promotion = stored.get("promotion")

    if not isinstance(promotion, dict):
        out["xuat_xu"] = "khong_co_ho_so"
        out["ly_do"] = (
            "tep trong so thieu hoac sai luoc do" if stored else "chua co tep trong so"
        )
        return out

    if promotion.get("promoted"):
        out["xuat_xu"] = "da_hoc"
    else:
        out["xuat_xu"] = "bi_tu_choi"
    out["ly_do"] = str(promotion.get("reason", ""))

    for key in ("learned_at_utc", "window_days", "half_life_days", "metric"):
        if key in stored:
            out[key] = stored[key]
    days_used = stored.get("days_used")
    out["days_used"] = len(days_used) if isinstance(days_used, list) else 0
    out["tham_dinh"] = {
        "so_ky_khop": promotion.get("train_days"),
        "so_ky_tham_dinh": promotion.get("validation_days"),
        "logloss_ngoai_mau": promotion.get("validation_logloss"),
        "loi_tuong_doi": promotion.get("relative_gain"),
    }
    return out


def weight_grid(step: float = 0.10) -> Iterable[EnsembleWeights]:
    """Simplex grid for five ensemble components (fallback when scipy is absent)."""
    k = int(round(1.0 / step))
    for i in range(k + 1):
        for j in range(k + 1 - i):
            for m in range(k + 1 - i - j):
                for n in range(k + 1 - i - j - m):
                    q = k - i - j - m - n
                    yield EnsembleWeights(
                        w_ml=i * step,
                        w_cau=j * step,
                        w_stat=m * step,
                        w_active=n * step,
                        w_stable=q * step,
                    )


def bernoulli_logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = clip01(p, eps=1e-6)
    return float(np.mean(-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))))


def bernoulli_brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def skill_score(model: float, baseline: float) -> float:
    """Phần cải thiện tương đối so với đường cơ sở.

    Dương nghĩa là mô hình tốt hơn baseline, âm là tệ hơn. Trả 0 khi baseline
    không dương để tránh chia cho số không.
    """
    if not np.isfinite(model) or not np.isfinite(baseline) or baseline <= 0.0:
        return 0.0
    return float((baseline - model) / baseline)


def categorical_logloss(p: np.ndarray, y_true_idx: int) -> float:
    p = clip01(p, eps=1e-12)
    return float(-np.log(p[int(y_true_idx)]))


def categorical_brier(p: np.ndarray, y_true_idx: int) -> float:
    """Multi-class Brier score, ``sum_k (p_k - y_k)^2``.

    This used ``np.mean`` rather than ``np.sum``, reporting a value 100x smaller
    than the standard definition.  Rankings were unaffected (the two differ by a
    constant factor), but two things were not:

      * every published Đặc Biệt Brier figure was off by two orders of magnitude, and
      * ``meta_predictor`` mixes the two in ``logloss + 0.20 * brier``, so the
        Brier term contributed ~0.002 of its intended weight for Đặc Biệt while
        contributing fully for LOTO (whose ``bernoulli_brier`` is genuinely a
        mean over the 100 Bernoulli marginals).

    ``bernoulli_brier`` is deliberately left as a mean: for LOTO the target is
    100 independent Bernoulli marginals, and the mean is the conventional
    per-marginal score there.
    """
    values = np.asarray(p, dtype=np.float64)
    y = np.zeros_like(values)
    y[int(y_true_idx)] = 1.0
    return float(np.sum((values - y) ** 2))
