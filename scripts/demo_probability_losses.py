"""Demo ĐO ĐƯỢC: hàm mất mát tùy biến và hiệu chuẩn xác suất, trên dữ liệu thật.

Vì sao là demo chứ không phải mã sản xuất
==========================================
Kho đã có lớp ML hoàn chỉnh (``src/ml_engine/``). Tệp này KHÔNG thay thế nó.
Nó tồn tại để trả lời một câu hỏi cụ thể bằng số đo trên chính ``data/xsmb.csv``
chứ không bằng lý thuyết:

    Đổi hàm mất mát (Focal / Brier) và đổi cách hiệu chuẩn (Platt / Isotonic)
    thì Brier, log-loss và ECE thay đổi bao nhiêu?

Mọi con số nó in ra đều so với ĐƯỜNG NỀN (tần suất cơ sở). Một mô hình không
có tín hiệu sẽ hội tụ về đúng đường nền, và skill score sẽ quanh 0 — đó là kết
quả hợp lệ, không phải lỗi.

Chạy:
    PYTHONPATH=src python3 scripts/demo_probability_losses.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402


# --- Chỉ số ----------------------------------------------------------------


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 15) -> float:
    """ECE: chênh lệch trung bình giữa xác suất DỰ BÁO và tần suất THỰC.

    Đây là chỉ số quan trọng nhất cho bài toán này. Một mô hình có thể xếp hạng
    tốt mà vẫn nói dối về mức độ chắc chắn; ECE bắt đúng điều đó.
    """
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total = 0.0
    for b in range(bins):
        mask = idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        total += n * abs(float(p[mask].mean()) - float(y[mask].mean()))
    return total / len(y)


def skill(metric_model: float, metric_baseline: float) -> float:
    """Skill score: >0 là hơn đường nền, <0 là kém hơn. 0 là ngang."""
    return 1.0 - metric_model / metric_baseline if metric_baseline > 0 else 0.0


# --- Hàm mất mát tùy biến --------------------------------------------------


def focal_loss_objective(gamma: float = 2.0, alpha: float = 0.25):
    """Focal Loss cho bộ tăng cường gradient: trả về (grad, hess).

    Focal Loss hạ trọng số các mẫu ĐÃ dễ, dồn sức vào mẫu khó. Nó sinh ra để
    xử lý mất cân bằng lớp cực đoan trong phát hiện vật thể.

    CẢNH BÁO nghiệp vụ, không phải cảnh báo kỹ thuật: focal loss KHÔNG phải
    proper scoring rule. Nó tối ưu khả năng PHÂN BIỆT chứ không tối ưu tính
    ĐÚNG của xác suất, nên nó làm hỏng hiệu chuẩn một cách có hệ thống. Với
    bài toán ở đây — nơi giá trị nằm ở xác suất đúng chứ không ở nhãn đúng —
    dùng focal loss thì BẮT BUỘC phải hiệu chuẩn lại ở tầng sau.
    """

    def objective(y_true: np.ndarray, raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        p = 1.0 / (1.0 + np.exp(-raw))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        y = y_true.astype(float)
        pt = np.where(y == 1, p, 1 - p)
        at = np.where(y == 1, alpha, 1 - alpha)
        # d(FL)/d(raw), rút gọn từ FL = -at * (1-pt)^gamma * log(pt)
        common = at * (1 - pt) ** gamma
        grad = common * (gamma * pt * np.log(np.clip(pt, 1e-9, None)) / (1 - pt + 1e-9) - 1.0)
        grad = np.where(y == 1, grad, -grad) * -1.0
        hess = np.clip(common * pt * (1 - pt) * (gamma + 1.0), 1e-6, None)
        return grad, hess

    return objective


def brier_objective(y_true: np.ndarray, raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Brier score làm hàm mục tiêu trực tiếp: trả về (grad, hess).

    Brier = (p - y)^2 với p = sigmoid(raw). Đây LÀ proper scoring rule, nên tối
    ưu nó là tối ưu thẳng chất lượng xác suất — khác hẳn focal loss.

        dB/dr  = 2(p-y) * p(1-p)
        d2B/dr2 = 2 * p(1-p) * [ (1-2p)(p-y) + p(1-p) ]

    Đạo hàm bậc hai có thể âm (Brier không lồi theo raw), nên phải kẹp sàn —
    không kẹp thì bộ tăng cường đi ngược hướng ở đúng những mẫu khó nhất.
    """
    p = 1.0 / (1.0 + np.exp(-raw))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    y = y_true.astype(float)
    pq = p * (1 - p)
    grad = 2.0 * (p - y) * pq
    hess = 2.0 * pq * ((1 - 2 * p) * (p - y) + pq)
    return grad, np.clip(hess, 1e-6, None)


# --- Hiệu chuẩn ------------------------------------------------------------


def fit_platt(p_val: np.ndarray, y_val: np.ndarray):
    """Platt scaling: hồi quy logistic một biến trên logit đầu ra."""
    z = np.log(np.clip(p_val, 1e-9, 1 - 1e-9) / np.clip(1 - p_val, 1e-9, 1 - 1e-9))
    model = LogisticRegression(C=1e6, solver="lbfgs")
    model.fit(z.reshape(-1, 1), y_val)
    def apply(p: np.ndarray) -> np.ndarray:
        zz = np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1 - 1e-9))
        return model.predict_proba(zz.reshape(-1, 1))[:, 1]
    return apply


def fit_isotonic(p_val: np.ndarray, y_val: np.ndarray):
    """Isotonic: đơn điệu không tham số, mạnh hơn Platt nhưng dễ khớp quá mức.

    Với ít dữ liệu hiệu chuẩn, isotonic bám theo nhiễu và trông rất đẹp trên
    tập hiệu chuẩn trong khi tệ hơn trên tập kiểm. Vì thế phép so ở đây luôn
    đo trên tập KIỂM tách riêng, không bao giờ trên tập đã dùng để hiệu chuẩn.
    """
    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    model.fit(p_val, y_val)
    return lambda p: np.clip(model.predict(p), 1e-6, 1 - 1e-6)


# --- Dữ liệu ---------------------------------------------------------------


def load_dataset() -> tuple[pd.DataFrame, np.ndarray, pd.Series]:
    """Bảng (ngày, con số) -> có về ở ngày KẾ TIẾP hay không.

    Đặc trưng cố ý ĐƠN GIẢN và chỉ dùng quá khứ: đây là demo về hàm mất mát và
    hiệu chuẩn, không phải về kỹ thuật đặc trưng. Lớp đặc trưng thật nằm ở
    ``src/ml_features.py``.
    """
    sparse = pd.read_json(ROOT / "data" / "xsmb-sparse.json")
    sparse["date"] = pd.to_datetime(sparse["date"])
    sparse = sparse.sort_values("date").reset_index(drop=True)
    cols = [c for c in sparse.columns if c != "date"]
    hit = (sparse[cols].to_numpy(dtype=float) > 0).astype(float)  # (T, 100)

    rows, labels, dates = [], [], []
    windows = (7, 30, 90, 365)
    for t in range(max(windows), hit.shape[0] - 1):
        past = hit[:t + 1]
        feats = {f"rate_{w}": past[-w:].mean(axis=0) for w in windows}
        # Gan: số kỳ kể từ lần về gần nhất.
        gap = np.full(100, t + 1, dtype=float)
        for n in range(100):
            idx = np.flatnonzero(past[:, n])
            if idx.size:
                gap[n] = t - idx[-1]
        feats["gap"] = gap
        feats["nhay"] = sparse[cols].to_numpy(dtype=float)[t]
        feats["weekday"] = np.full(100, sparse["date"].iloc[t + 1].weekday(), dtype=float)
        frame = pd.DataFrame(feats)
        frame["number"] = np.arange(100)
        rows.append(frame)
        labels.append(hit[t + 1])
        dates.append(np.full(100, sparse["date"].iloc[t + 1].value))

    X = pd.concat(rows, ignore_index=True)
    y = np.concatenate(labels)
    d = pd.Series(pd.to_datetime(np.concatenate(dates)))
    return X, y, d


# --- Chạy ------------------------------------------------------------------


def _train(objective, X_fit, y_fit, X_cal, X_test):
    """Huấn luyện LightGBM với hàm mục tiêu tùy biến (hoặc mặc định).

    Khi truyền `objective` là một hàm, LightGBM bỏ qua liên kết sigmoid nội bộ
    và trả về điểm THÔ, nên phải tự áp sigmoid. Quên bước này là lỗi im lặng
    kinh điển: mô hình vẫn chạy, chỉ là "xác suất" nằm ngoài khoảng [0, 1].
    """
    import lightgbm as lgb

    params = {
        "num_leaves": 15,
        "learning_rate": 0.05,
        "min_data_in_leaf": 200,
        "lambda_l2": 1.0,
        "verbosity": -1,
        "seed": 0,
        "deterministic": True,
    }
    if objective is None:
        params["objective"] = "binary"
        booster = lgb.train(params, lgb.Dataset(X_fit, label=y_fit), num_boost_round=150)
        to_p = lambda raw: raw
    else:
        # LightGBM gọi hàm mục tiêu theo thứ tự (dự đoán_thô, Dataset), ngược
        # với quy ước (y_thật, thô) quen thuộc của sklearn. Nhầm thứ tự này
        # không nổ ngay mà nổ ở dòng đầu tiên chạm tới dữ liệu — dễ mất nửa
        # tiếng để lần ra, nên bọc lại cho rõ ràng.
        def adapter(raw, dataset):
            return objective(dataset.get_label(), raw)

        params["objective"] = adapter
        booster = lgb.train(params, lgb.Dataset(X_fit, label=y_fit), num_boost_round=150)
        to_p = lambda raw: 1.0 / (1.0 + np.exp(-raw))
    return to_p(booster.predict(X_cal)), to_p(booster.predict(X_test))


def main() -> None:
    X, y, dates = load_dataset()
    order = np.argsort(dates.to_numpy())
    X = X.iloc[order].reset_index(drop=True)
    y, dates = y[order], dates.iloc[order].reset_index(drop=True)

    # Ba lát CẮT THEO THỜI GIAN, không bao giờ trộn ngẫu nhiên: huấn luyện ->
    # hiệu chuẩn -> kiểm. Trộn ngẫu nhiên ở đây là rò rỉ nhìn-trước kinh điển.
    n = len(y)
    i_fit, i_cal = int(n * 0.70), int(n * 0.85)
    sl_fit, sl_cal, sl_test = slice(0, i_fit), slice(i_fit, i_cal), slice(i_cal, n)

    print(f"Dữ liệu : {n:,} hàng (ngày, con số) từ {dates.iloc[0].date()} tới {dates.iloc[-1].date()}")
    print(f"Lát cắt : huấn luyện {i_fit:,} | hiệu chuẩn {i_cal - i_fit:,} | kiểm {n - i_cal:,}")

    y_test = y[sl_test]
    base_rate = float(y[sl_fit].mean())
    p_base = np.full(len(y_test), base_rate)
    b0 = brier(y_test, p_base)
    l0 = logloss(y_test, p_base)
    e0 = expected_calibration_error(y_test, p_base)
    print(f"\nĐƯỜNG NỀN (hằng số = tần suất cơ sở {base_rate:.4f} học từ tập huấn luyện)")
    print(f"  Brier {b0:.6f}   LogLoss {l0:.6f}   ECE {e0:.6f}")

    losses = {
        "log-loss (mặc định)": None,
        "Focal (γ=2, α=0.25)": focal_loss_objective(),
        "Brier (proper)": brier_objective,
    }

    print(f"\n{'hàm mục tiêu':22} {'hiệu chuẩn':12} {'Brier':>10} {'LogLoss':>10} {'ECE':>9} "
          f"{'skill Brier':>12} {'skill LL':>10}")
    print("-" * 92)

    for name, objective in losses.items():
        p_cal, p_test = _train(objective, X.iloc[sl_fit], y[sl_fit], X.iloc[sl_cal], X.iloc[sl_test])
        for cal_name, fitter in (("không", None), ("Platt", fit_platt), ("Isotonic", fit_isotonic)):
            p = p_test if fitter is None else fitter(p_cal, y[sl_cal])(p_test)
            b, l, e = brier(y_test, p), logloss(y_test, p), expected_calibration_error(y_test, p)
            print(f"{name:22} {cal_name:12} {b:10.6f} {l:10.6f} {e:9.6f} "
                  f"{skill(b, b0):12.5f} {skill(l, l0):10.5f}")

    print("\nĐọc bảng: skill > 0 là hơn đường nền, < 0 là KÉM hơn.")
    print("Skill quanh 0 nghĩa là mô hình không tìm thấy tín hiệu — đó là kết quả")
    print("hợp lệ và đúng với kỳ vọng cho một quá trình ngẫu nhiên độc lập.")


if __name__ == "__main__":
    main()
