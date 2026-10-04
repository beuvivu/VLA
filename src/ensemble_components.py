from __future__ import annotations

"""Availability-aware helpers for ensemble component probability artifacts.

A missing, malformed, or stale component must never be represented as a
legitimate probability vector. These helpers keep availability explicit and
only normalize/weight artifacts that satisfy the 00..99 and date contracts.
"""

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

import numpy as np
import pandas as pd

from ensemble_utils import EnsembleWeights, normalize_distribution

Mode = Literal["loto", "de"]
COMPONENT_KEYS = ("ml", "cau", "stat", "active", "stable")

#: Phiên bản ĐỊNH NGHĨA xác suất của thành phần, cho thành phần từng đổi định
#: nghĩa. Sổ ``data/history/pred_<mode>.csv`` ghi số này vào cột
#: ``policy_<key>`` của mỗi dòng; dòng cũ không có cột ấy.
#:
#: Cầu-kèo: 1 = co về nền theo kỹ năng thẩm định (04-10-2026). Trước đó cột
#: ``p_cau`` là xác suất THÔ — một thành phần khác — nên bộ học trọng số và tầng
#: xếp chồng không được học trên hỗn hợp hai định nghĩa.
COMPONENT_POLICY: Final[dict[str, int]] = {"cau": 1}


def policy_column(key: str) -> str:
    return f"policy_{key}"


#: Phiên bản PHÉP CHỐT tổ hợp (``ensemble_utils.finalize_blend``) đã dùng khi
#: công bố ngày ấy, ghi vào cột ``policy_blend`` của sổ lịch sử. 1 = neo mức
#: LOTO (04-10-2026); dòng cũ không có cột đã được công bố bằng ``clip01``.
BLEND_POLICY: Final[int] = 1
BLEND_POLICY_COLUMN: Final[str] = "policy_blend"


def published_with_level_anchor(sub: pd.DataFrame) -> bool:
    """Ngày này đã được CÔNG BỐ với phép neo mức LOTO hay chưa."""
    if BLEND_POLICY_COLUMN not in sub.columns:
        return False
    versions = pd.to_numeric(sub[BLEND_POLICY_COLUMN], errors="coerce").to_numpy(dtype=float)
    # Phiên bản 1 trở đi đều neo mức; NaN (dòng ghi trước khi có cột) thì không.
    return bool(versions.size and np.all(versions >= float(BLEND_POLICY)))


@dataclass(frozen=True)
class ComponentVector:
    prob: np.ndarray
    available: bool
    reason: str


def _strict_bool_flags(values: pd.Series) -> np.ndarray | None:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).to_numpy(dtype=bool)
    normalized = values.astype("string").str.strip().str.lower()
    mapping = {"true": True, "1": True, "false": False, "0": False}
    if normalized.isna().any() or not normalized.isin(mapping).all():
        return None
    return normalized.map(mapping).to_numpy(dtype=bool)


def _expected_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    return pd.Timestamp(value).date()


def _artifact_date_reason(
    df: pd.DataFrame,
    *,
    expected_target_date: str | date | None,
    expected_anchor_date: str | date | None,
) -> str | None:
    expected_target = _expected_date(expected_target_date)
    expected_anchor = _expected_date(expected_anchor_date)

    target_col = next((c for c in ("target_date", "predict_for_date") if c in df.columns), None)
    if target_col is not None and expected_target is not None:
        values = pd.to_datetime(df[target_col], errors="coerce")
        if values.isna().any():
            return f"invalid_{target_col}"
        unique = set(values.dt.date.tolist())
        if unique != {expected_target}:
            return f"stale_{target_col}"

    if "anchor_date" in df.columns and expected_anchor is not None:
        values = pd.to_datetime(df["anchor_date"], errors="coerce")
        if values.isna().any():
            return "invalid_anchor_date"
        unique = set(values.dt.date.tolist())
        if unique != {expected_anchor}:
            return "stale_anchor_date"
    return None


#: Số giải trong một kỳ XSMB. Đây là trần CỨNG cho số con phân biệt: 27 giải
#: thì nhiều nhất cũng chỉ ra 27 con khác nhau.
LOTO_PRIZE_SLOTS: Final[int] = 27

#: Số con PHÂN BIỆT kỳ vọng: 27 giải rút từ 100 số hai chữ số, nên
#: ``100 · (1 − (99/100)^27) = 23,7657``. Tổng xác suất biên của một mô hình
#: loto đúng phải bằng chính đại lượng này.
LOTO_EXPECTED_MARGINAL_SUM: Final[float] = 100.0 * (
    1.0 - (99.0 / 100.0) ** LOTO_PRIZE_SLOTS
)


def loto_marginal_sum_is_plausible(total: float) -> bool:
    """Tổng xác suất biên loto có vượt trần luật chơi hay không.

    Trần là 27, suy thẳng từ luật chơi: một kỳ có 27 giải nên nhiều nhất cũng
    chỉ ra 27 con phân biệt, tức tổng ``P(con i về)`` không thể vượt 27.

    CHỈ chặn phía TRÊN, và đó là điều đã cân nhắc. Bản đầu của hàm này còn đặt
    ngưỡng dưới bằng một nửa giá trị kỳ vọng — con số ấy tôi TỰ ĐẶT, không suy
    ra từ đâu, và nó loại oan một mô hình thiếu tự tin (phép kiểm
    ``test_ensemble_renormalizes_weights_over_available_components_only`` với
    vector tổng 10 đã bắt đúng chỗ đó). Tổng THẤP là một lựa chọn mô hình;
    tổng vượt 27 là bất khả thi về mặt vật lý.

    Lỗi cần chặn nằm ở phía trên: 212 trong 231 ngày lịch sử loto ghi
    ``p_active``/``p_stable`` ở thang "gần 1,0 cho mọi con", tổng ≈ 100. Cổng
    canh cũ chỉ kiểm từng phần tử trong ``[0, 1]`` nên vector ấy qua sạch.

    Hệ quả đo được: trang Chất lượng mô hình báo Brier 0,3133 cho loto, trong
    khi trên dữ liệu sạch con số thật là 0,1802.

    Args:
        total: Tổng của vector 100 phần tử.

    Returns:
        ``True`` nếu tổng không vượt trần luật chơi.
    """
    return bool(float(total) <= float(LOTO_PRIZE_SLOTS))


def probability_component(
    df: pd.DataFrame,
    *,
    mode: Mode,
    expected_target_date: str | date | None = None,
    expected_anchor_date: str | date | None = None,
) -> ComponentVector:
    """Validate one full 00..99 probability artifact.

    Missing, partial, duplicate, stale-date, non-finite, out-of-range,
    non-integer-number, or all-zero artifacts are unavailable. For De, a valid
    vector is normalized to a categorical distribution. For Loto, Bernoulli
    marginals are kept as-is.
    """
    missing = np.full(100, np.nan, dtype=np.float64)
    if df is None or df.empty:
        return ComponentVector(missing, False, "missing_or_empty")
    if len(df) != 100:
        return ComponentVector(missing, False, "not_exactly_100_rows")
    if "number" not in df.columns or "prob" not in df.columns:
        return ComponentVector(missing, False, "missing_number_or_prob_column")

    date_reason = _artifact_date_reason(
        df,
        expected_target_date=expected_target_date,
        expected_anchor_date=expected_anchor_date,
    )
    if date_reason is not None:
        return ComponentVector(missing, False, date_reason)

    numbers = pd.to_numeric(df["number"], errors="coerce")
    probs = pd.to_numeric(df["prob"], errors="coerce")
    if numbers.isna().any() or probs.isna().any():
        return ComponentVector(missing, False, "non_numeric_number_or_probability")

    number_values = numbers.to_numpy(dtype=float)
    if not np.isfinite(number_values).all() or not np.all(number_values == np.floor(number_values)):
        return ComponentVector(missing, False, "number_must_be_finite_integer")
    n = number_values.astype(int)
    p = probs.to_numpy(dtype=float)
    if len(np.unique(n)) != 100 or set(n.tolist()) != set(range(100)):
        return ComponentVector(missing, False, "number_universe_not_00_99")
    if not np.isfinite(p).all() or np.any((p < 0.0) | (p > 1.0)):
        return ComponentVector(missing, False, "probability_out_of_range_or_nonfinite")

    p = p[np.argsort(n)]
    total = float(np.sum(p))
    if total <= 0.0:
        return ComponentVector(missing, False, "all_zero_probability_vector")
    if mode == "loto" and not loto_marginal_sum_is_plausible(total):
        return ComponentVector(missing, False, "loto_marginal_sum_implausible")

    if mode == "de":
        p = normalize_distribution(p)
    return ComponentVector(np.asarray(p, dtype=np.float64), True, "ok")


def availability_from_history_day(
    sub: pd.DataFrame, *, mode: Mode | None = None, current_policy: bool = False
) -> dict[str, bool]:
    """Thành phần nào của một ngày trong sổ lịch sử là vector xác suất hợp lệ.

    ``current_policy=True`` dành cho nơi HỌC từ lịch sử (trọng số, hiệu chỉnh,
    tầng xếp chồng): thành phần có trong ``COMPONENT_POLICY`` chỉ được tính khi
    mọi dòng của ngày ghi đúng phiên bản hiện hành. Nơi dựng lại thứ ĐÃ công bố
    (trang Chất lượng) giữ mặc định, vì ngày cũ đã công bố theo định nghĩa cũ.
    """
    if len(sub) != 100 or "number" not in sub.columns:
        return {key: False for key in COMPONENT_KEYS}

    numbers = pd.to_numeric(sub["number"], errors="coerce")
    number_values = numbers.to_numpy(dtype=float)
    universe_ok = (
        not numbers.isna().any()
        and np.isfinite(number_values).all()
        and np.all(number_values == np.floor(number_values))
        and set(numbers.astype(int).tolist()) == set(range(100))
    )
    if not universe_ok:
        return {key: False for key in COMPONENT_KEYS}

    out: dict[str, bool] = {}
    for key in COMPONENT_KEYS:
        p_col = f"p_{key}"
        has_col = f"has_{key}"
        if p_col not in sub.columns:
            out[key] = False
            continue
        values = pd.to_numeric(sub[p_col], errors="coerce").to_numpy(dtype=float)
        valid = (
            values.shape == (100,)
            and np.isfinite(values).all()
            and np.all((values >= 0.0) & (values <= 1.0))
            and float(values.sum()) > 0.0
        )
        if valid and mode == "loto":
            valid = loto_marginal_sum_is_plausible(float(values.sum()))
        if has_col in sub.columns:
            flags = _strict_bool_flags(sub[has_col])
            valid = valid and flags is not None and bool(flags.all())
        if valid and current_policy and key in COMPONENT_POLICY:
            column = policy_column(key)
            versions = (
                pd.to_numeric(sub[column], errors="coerce").to_numpy(dtype=float)
                if column in sub.columns
                else np.full(len(sub), np.nan)
            )
            valid = bool(np.all(versions == float(COMPONENT_POLICY[key])))
        out[key] = bool(valid)
    return out


def renormalize_available_weights(
    weights: EnsembleWeights, available: dict[str, bool]
) -> EnsembleWeights:
    raw = np.array(
        [weights.w_ml, weights.w_cau, weights.w_stat, weights.w_active, weights.w_stable],
        dtype=float,
    )
    if not np.isfinite(raw).all() or np.any(raw < 0.0):
        raise ValueError("Configured ensemble weights must be finite and non-negative")
    mask = np.array([bool(available.get(key, False)) for key in COMPONENT_KEYS], dtype=float)
    effective = raw * mask
    total = float(effective.sum())
    if total <= 0.0:
        raise ValueError("No valid ensemble component is available")
    effective /= total
    return EnsembleWeights(
        w_ml=float(effective[0]),
        w_cau=float(effective[1]),
        w_stat=float(effective[2]),
        w_active=float(effective[3]),
        w_stable=float(effective[4]),
    )
