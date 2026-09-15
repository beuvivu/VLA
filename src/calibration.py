from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Literal

import numpy as np

from ensemble_utils import clip01, logit, sigmoid, normalize_distribution, softmax_from_logp


Mode = Literal["loto", "de"]


@dataclass(frozen=True)
class CalibParams:
    mode: Mode
    # loto: sigmoid(a*logit(p)+b)
    a: float = 1.0
    b: float = 0.0
    # de: temperature scaling on log probs
    temperature: float = 1.0
    # Ánh xạ đơn điệu không tham số, dạng các nút (x tăng dần, y tăng dần).
    # Rỗng nghĩa là không dùng isotonic — đó là mặc định, nên mọi tệp hiệu
    # chuẩn ghi trước khi có trường này vẫn nạp được nguyên vẹn.
    isotonic_x: tuple[float, ...] = ()
    isotonic_y: tuple[float, ...] = ()

    @property
    def uses_isotonic(self) -> bool:
        return len(self.isotonic_x) > 0

    def __post_init__(self) -> None:
        # Chuẩn hoá về tuple TRƯỚC mọi phép kiểm.
        #
        # Tệp hiệu chuẩn là JSON, và json.loads trả về list. Không chuẩn hoá thì
        # bản nạp lại KHÁC bản đã ghi theo `==` dù mọi con số giống hệt — kiểu
        # lệch không bao giờ nổ, chỉ âm thầm làm mọi phép so sánh tham số sai.
        object.__setattr__(self, "isotonic_x", tuple(float(v) for v in self.isotonic_x))
        object.__setattr__(self, "isotonic_y", tuple(float(v) for v in self.isotonic_y))
        if any(
            isinstance(value, bool) or not isinstance(value, Real)
            for value in (self.a, self.b, self.temperature)
        ):
            raise ValueError("calibration parameters must be real numbers")
        values = np.array([self.a, self.b, self.temperature], dtype=float)
        if self.mode not in {"loto", "de"}:
            raise ValueError("calibration mode must be 'loto' or 'de'")
        if not np.isfinite(values).all():
            raise ValueError("calibration parameters must be finite")
        if self.temperature <= 0.0:
            raise ValueError("calibration temperature must be > 0")
        if len(self.isotonic_x) != len(self.isotonic_y):
            raise ValueError("isotonic knots must come in pairs")
        if self.isotonic_x:
            xs = np.asarray(self.isotonic_x, dtype=float)
            ys = np.asarray(self.isotonic_y, dtype=float)
            if not (np.isfinite(xs).all() and np.isfinite(ys).all()):
                raise ValueError("isotonic knots must be finite")
            if np.any(np.diff(xs) < 0.0) or np.any(np.diff(ys) < 0.0):
                raise ValueError("isotonic knots must be non-decreasing")
            if bool(((ys < 0.0) | (ys > 1.0)).any()):
                raise ValueError("isotonic outputs must lie inside [0, 1]")

    def as_dict(self) -> dict:
        payload = {
            "mode": self.mode,
            "a": float(self.a),
            "b": float(self.b),
            "temperature": float(self.temperature),
        }
        # Chỉ ghi nút khi thực sự dùng, để tệp hiệu chuẩn của cấu hình tham số
        # giữ nguyên hình dạng cũ và người đọc không phải đoán.
        if self.isotonic_x:
            payload["isotonic_x"] = [float(v) for v in self.isotonic_x]
            payload["isotonic_y"] = [float(v) for v in self.isotonic_y]
        return payload


def apply_calibration(mode: Mode, p: np.ndarray, params: CalibParams) -> np.ndarray:
    if params.mode != mode:
        raise ValueError("calibration mode does not match prediction mode")
    values = np.asarray(p, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("probabilities to calibrate must be finite")
    if bool(((values < 0.0) | (values > 1.0)).any()):
        raise ValueError("probabilities to calibrate must be inside [0, 1]")
    if params.uses_isotonic:
        # Ánh xạ đơn điệu THAY hẳn phép hiệu chuẩn tham số, không chồng lên.
        # Chồng hai phép hiệu chuẩn là cách chắc chắn để không ai còn giải
        # thích được con số cuối cùng đến từ đâu.
        mapped = np.interp(values, np.asarray(params.isotonic_x, dtype=float),
                           np.asarray(params.isotonic_y, dtype=float))
        mapped = clip01(mapped, eps=1e-6)
        return normalize_distribution(mapped) if mode == "de" else mapped
    if mode == "de":
        # temperature scaling
        t = float(max(1e-6, params.temperature))
        logp = np.log(clip01(values, eps=1e-12)) / t
        return normalize_distribution(softmax_from_logp(logp))
    # loto
    x = logit(clip01(values, eps=1e-6))
    z = params.a * x + params.b
    return clip01(sigmoid(z), eps=1e-6)


def learn_calibration(
    mode: Mode,
    probs_by_day: np.ndarray,  # shape (D,100)
    y_by_day: np.ndarray,      # shape (D,100) (Bernoulli for loto) OR one-hot for de
    sample_weight_by_day: np.ndarray | None = None,  # shape (D,)
) -> CalibParams:
    """Learn calibration parameters on recent window.

    - de: optimize temperature T to minimize mean categorical logloss.
    - loto: optimize (a,b) to minimize mean Bernoulli logloss across all numbers.
    """
    try:
        from scipy.optimize import minimize
    except Exception:  # pragma: no cover
        minimize = None

    D = probs_by_day.shape[0]
    w_day = sample_weight_by_day if sample_weight_by_day is not None else np.ones(D, dtype=float)

    if probs_by_day.ndim != 2 or probs_by_day.shape != y_by_day.shape:
        raise ValueError("probs_by_day and y_by_day must share shape (days, 100)")
    if D == 0:
        # Nothing to fit: identity calibration rather than a degenerate optimum.
        return CalibParams(mode=mode) if mode == "de" else CalibParams(mode="loto")

    if mode == "de":
        # y_by_day expected one-hot (exactly one 1 per day)
        y_idx = np.argmax(y_by_day, axis=1).astype(int)
        # Temperature scaling is p**(1/T) renormalised. Doing it for all days at
        # once removes a D-iteration Python loop from *every* objective and
        # finite-difference gradient evaluation the optimizer makes.
        log_p = np.log(clip01(np.asarray(probs_by_day, dtype=float), eps=1e-12))
        rows = np.arange(log_p.shape[0])

        def loss_T(x: np.ndarray) -> float:
            T = float(np.clip(x[0], 0.3, 5.0))
            scaled = log_p / T
            scaled -= scaled.max(axis=1, keepdims=True)  # softmax stabilisation
            expo = np.exp(scaled)
            pT = expo / expo.sum(axis=1, keepdims=True)
            ll = -np.log(np.clip(pT[rows, y_idx], 1e-12, 1.0))
            return float(np.average(ll, weights=w_day))

        if minimize is None:
            # fallback coarse scan
            Ts = np.linspace(0.5, 3.0, 26)
            bestT, bestL = 1.0, float("inf")
            for T in Ts:
                L = loss_T(np.array([T]))
                if L < bestL:
                    bestL, bestT = L, float(T)
            return CalibParams(mode="de", temperature=bestT)

        res = minimize(loss_T, x0=np.array([1.0]), bounds=[(0.3, 5.0)], method="L-BFGS-B")
        T = float(res.x[0]) if res.success else 1.0
        T = float(np.clip(T, 0.3, 5.0))
        return CalibParams(mode="de", temperature=T)

    # loto
    # flatten across day and number (D*100)
    P = clip01(probs_by_day, eps=1e-6).reshape(-1)
    Y = y_by_day.reshape(-1).astype(float)

    # weight each day equally but allow decay via w_day
    W = np.repeat(w_day, 100)

    def loss_ab(x: np.ndarray) -> float:
        a = float(np.clip(x[0], 0.1, 5.0))
        b = float(np.clip(x[1], -5.0, 5.0))
        z = a * logit(P) + b
        p2 = clip01(sigmoid(z), eps=1e-6)
        ll = -(Y * np.log(p2) + (1.0 - Y) * np.log(1.0 - p2))
        return float(np.sum(W * ll) / max(1e-12, np.sum(W)))

    if minimize is None:
        # fallback: keep identity
        return CalibParams(mode="loto", a=1.0, b=0.0)

    res = minimize(
        loss_ab,
        x0=np.array([1.0, 0.0]),
        bounds=[(0.1, 5.0), (-5.0, 5.0)],
        method="L-BFGS-B",
    )
    if not res.success:
        return CalibParams(mode="loto", a=1.0, b=0.0)
    a, b = float(res.x[0]), float(res.x[1])
    return CalibParams(mode="loto", a=a, b=b)


# --- Chọn phương pháp hiệu chuẩn bằng SỐ ĐO --------------------------------


@dataclass(frozen=True)
class CalibrationAudit:
    """Vì sao phương pháp này được chọn — và hai phương pháp kia đạt bao nhiêu.

    Không có bản ghi này, "đã hiệu chuẩn" là một khẳng định không kiểm được.
    """

    chosen: str
    brier_by_candidate: dict[str, float]
    fit_days: int
    holdout_days: int
    selected: bool

    def describe(self) -> str:
        if not self.selected:
            return (
                f"Không chọn được ({self.fit_days + self.holdout_days} kỳ, dưới ngưỡng "
                f"{MIN_SELECTION_DAYS}); giữ hành vi tham số mặc định."
            )
        ranked = sorted(self.brier_by_candidate.items(), key=lambda kv: kv[1])
        detail = ", ".join(f"{name} {score:.6f}" for name, score in ranked)
        return f"Chọn '{self.chosen}' theo Brier trên {self.holdout_days} kỳ giữ riêng ({detail})."


#: Dưới ngưỡng này, cắt thêm một lát giữ riêng sẽ làm hỏng chính phép khớp.
#: Khi ấy giữ nguyên hành vi cũ và nói rõ là không chọn, thay vì chọn bừa.
MIN_SELECTION_DAYS = 60
DEFAULT_SELECTION_HOLDOUT = 0.30


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def _fit_isotonic_params(
    mode: Mode, probs: np.ndarray, labels: np.ndarray, *, max_knots: int = 64
) -> CalibParams | None:
    """Khớp ánh xạ đơn điệu rồi rút gọn về một lưới nút thưa để lưu được.

    Rút gọn chứ không lưu nguyên: bản đầy đủ có một nút mỗi giá trị đầu vào duy
    nhất — hàng chục nghìn nút cho một tệp JSON hiệu chuẩn. Nội suy tuyến tính
    trên lưới thưa sai khác không đáng kể so với bậc thang gốc, và tệp vẫn đọc
    được bằng mắt.
    """
    try:
        from sklearn.isotonic import IsotonicRegression
    except Exception:  # pragma: no cover - sklearn là phụ thuộc bắt buộc
        return None
    flat_p = np.asarray(probs, dtype=float).reshape(-1)
    flat_y = np.asarray(labels, dtype=float).reshape(-1)
    if flat_p.size == 0 or np.unique(flat_p).size < 3:
        return None
    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    model.fit(flat_p, flat_y)
    grid = np.unique(np.quantile(flat_p, np.linspace(0.0, 1.0, max_knots)))
    if grid.size < 2:
        return None
    mapped = np.clip(np.maximum.accumulate(model.predict(grid)), 0.0, 1.0)
    return CalibParams(
        mode=mode,
        isotonic_x=tuple(float(v) for v in grid),
        isotonic_y=tuple(float(v) for v in mapped),
    )


def select_calibration(
    mode: Mode,
    probs_by_day: np.ndarray,
    y_by_day: np.ndarray,
    sample_weight_by_day: np.ndarray | None = None,
    *,
    holdout_fraction: float = DEFAULT_SELECTION_HOLDOUT,
) -> tuple[CalibParams, CalibrationAudit]:
    """Khớp trên lát đầu, chấm điểm trên lát cuối, giữ phương pháp thắng.

    Ba ứng viên, và ứng viên ĐẦU TIÊN mới là điểm chính:

    * ``identity`` — không hiệu chuẩn gì cả. Hiện không nơi nào kiểm xem phép
      hiệu chuẩn có LÀM TỆ ĐI hay không; một cửa sổ lệch hoặc trôi khái niệm
      có thể khiến phép khớp tham số đẩy xác suất đi sai hướng, và không có
      ứng viên này thì điều đó không bao giờ lộ ra.
    * ``parametric`` — Platt (LOTO) hoặc temperature (đề), hành vi hiện tại.
    * ``isotonic`` — đơn điệu không tham số, mạnh hơn nhưng dễ bám nhiễu.

    Chấm bằng Brier vì nó là proper scoring rule: tối ưu nó là tối ưu thẳng
    chất lượng xác suất. Lát giữ riêng cắt theo THỜI GIAN, không trộn ngẫu
    nhiên — trộn ở đây là rò rỉ nhìn-trước.

    Cửa sổ quá ngắn thì không chọn: trả về phép khớp tham số trên toàn bộ dữ
    liệu, đúng hành vi cũ, và nói rõ ``selected=False``.
    """
    probs = np.asarray(probs_by_day, dtype=float)
    labels = np.asarray(y_by_day, dtype=float)
    if probs.ndim != 2 or probs.shape != labels.shape:
        raise ValueError("probs_by_day and y_by_day must share shape (days, 100)")
    if not 0.05 <= holdout_fraction <= 0.6:
        raise ValueError("holdout_fraction phải nằm trong [0.05, 0.6]")

    days = probs.shape[0]
    split = int(round(days * (1.0 - holdout_fraction)))
    if days < MIN_SELECTION_DAYS or split <= 0 or days - split <= 0:
        params = learn_calibration(mode, probs, labels, sample_weight_by_day)
        return params, CalibrationAudit(
            chosen="parametric",
            brier_by_candidate={},
            fit_days=days,
            holdout_days=0,
            selected=False,
        )

    weights = sample_weight_by_day
    fit_weights = None if weights is None else np.asarray(weights, dtype=float)[:split]

    candidates: dict[str, CalibParams] = {
        "identity": CalibParams(mode=mode),
        "parametric": learn_calibration(mode, probs[:split], labels[:split], fit_weights),
    }
    isotonic = _fit_isotonic_params(mode, probs[:split], labels[:split])
    if isotonic is not None:
        candidates["isotonic"] = isotonic

    scores = {
        name: _brier(
            labels[split:],
            np.vstack([apply_calibration(mode, row, params) for row in probs[split:]]),
        )
        for name, params in candidates.items()
    }
    # Hoà điểm thì ưu tiên theo thứ tự chèn: identity trước parametric trước
    # isotonic. Phương pháp đơn giản hơn thắng khi không đo được khác biệt —
    # đó là lựa chọn có chủ ý, không phải ngẫu nhiên theo thứ tự từ điển.
    chosen = min(candidates, key=lambda name: (scores[name], list(candidates).index(name)))
    return candidates[chosen], CalibrationAudit(
        chosen=chosen,
        brier_by_candidate=scores,
        fit_days=split,
        holdout_days=days - split,
        selected=True,
    )
