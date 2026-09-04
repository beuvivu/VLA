"""Nhóm đặc trưng miền thử nghiệm cho mô hình cầu-kèo.

Các phép biến đổi trong mô-đun này chỉ kết hợp thông tin đã biết tại cùng một
ngày neo. Chúng mô tả quan hệ số học/nghiệp vụ, không tự tạo ra bằng chứng dự
báo. Mỗi nhóm mặc định tắt và chỉ được phép vào production sau khi vượt qua
gate kiểm định thời gian trong :mod:`cau_keo_domain_challenger`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from number_reference import (
    bo,
    bo_family_id,
    bong_am,
    bong_duong,
    cap_loto_50_kind,
    cap_loto_50_partner,
    dan_cham,
    dan_tong_mod10,
)

FEATURE_GROUP_SCHEMA_VERSION = 3
_ORDER_COLUMN = "__domain_original_order"
_ANCHOR_COLUMN = "__domain_normalized_anchor"


@dataclass(frozen=True)
class FeatureGroupSpec:
    """Hợp đồng bất biến của một nhóm đặc trưng thử nghiệm."""

    columns: tuple[str, ...]
    provenance: str
    temporal_requirement: str = "same_anchor_only"
    default_enabled: bool = False


NUMBERS = np.arange(100, dtype=np.int16)
CAP50_PARTNER = np.array(
    [int(cap_loto_50_partner(int(number))) for number in NUMBERS],
    dtype=np.int16,
)
BONG_DUONG_PARTNER = np.array(
    [int(bong_duong(int(number))) for number in NUMBERS],
    dtype=np.int16,
)
BONG_AM_PARTNER = np.array(
    [int(bong_am(int(number))) for number in NUMBERS],
    dtype=np.int16,
)
CAP50_IS_KEP_BONG = np.array(
    [1 if cap_loto_50_kind(int(number)) == "kep_bong" else 0 for number in NUMBERS],
    dtype=np.int8,
)
BO_FAMILY_IDS = np.array(
    [bo_family_id(int(number)) for number in NUMBERS],
    dtype=object,
)
BO_MEMBERS = [
    np.array(sorted(int(item) for item in bo(int(number))), dtype=np.int16)
    for number in NUMBERS
]
CHAM_MEMBERS = [
    np.array(
        sorted(
            int(item)
            for item in set(dan_cham(int(number) // 10))
            | set(dan_cham(int(number) % 10))
        ),
        dtype=np.int16,
    )
    for number in NUMBERS
]
TONG_MEMBERS = [
    np.array(
        [
            int(item)
            for item in dan_tong_mod10(
                (int(number) // 10 + int(number) % 10) % 10
            )
        ],
        dtype=np.int16,
    )
    for number in NUMBERS
]


def _mean_matrix(groups: list[np.ndarray]) -> np.ndarray:
    matrix = np.zeros((100, 100), dtype=np.float32)
    for number, members in enumerate(groups):
        matrix[number, members] = 1.0 / float(len(members))
    return matrix


BO_MEAN = _mean_matrix(BO_MEMBERS)
CHAM_MEAN = _mean_matrix(CHAM_MEMBERS)
TONG_MEAN = _mean_matrix(TONG_MEMBERS)

PARTNER_FEATURES = (
    "cap50_partner_hit_today",
    "cap50_partner_freq_7d",
    "cap50_partner_freq_30d",
    "cap50_partner_freq_90d",
    "cap50_partner_freq_365d",
    "cap50_partner_gap",
)
CAP_50_FEATURES = (
    "cap50_pair_freq_30_mean",
    "cap50_pair_freq_90_mean",
    "cap50_pair_freq_365_mean",
    "cap50_pair_balance_30d",
    "cap50_pair_balance_90d",
    "cap50_pair_balance_365d",
    "cap50_is_kep_bong",
)
BO_FEATURES = (
    "bo_family_size",
    "bo_hit_today_rate",
    "bo_freq_7d_mean",
    "bo_freq_30d_mean",
    "bo_freq_90d_mean",
    "bo_freq_365d_mean",
    "bo_gap_mean",
    "bo_path_support_mean",
)
BONG_FEATURES = (
    "bong_duong_hit_today",
    "bong_duong_freq_7d",
    "bong_duong_freq_30d",
    "bong_duong_gap",
    "bong_am_hit_today",
    "bong_am_freq_7d",
    "bong_am_freq_30d",
    "bong_am_gap",
)
CHAM_FEATURES = (
    "cham_hit_today_rate",
    "cham_freq_7d_mean",
    "cham_freq_30d_mean",
    "cham_freq_90d_mean",
    "cham_gap_mean",
    "cham_path_support_mean",
)
TONG_FEATURES = (
    "tong_hit_today_rate",
    "tong_freq_7d_mean",
    "tong_freq_30d_mean",
    "tong_freq_90d_mean",
    "tong_gap_mean",
    "tong_path_support_mean",
)

DOMAIN_FEATURE_SPECS: dict[str, FeatureGroupSpec] = {
    "partner": FeatureGroupSpec(
        columns=PARTNER_FEATURES,
        provenance="number_reference.cap_loto_50_partner",
    ),
    "cap_50": FeatureGroupSpec(
        columns=CAP_50_FEATURES,
        provenance="number_reference.cap_loto_50",
    ),
    "bo": FeatureGroupSpec(
        columns=BO_FEATURES,
        provenance="number_reference.bo",
    ),
    "bong": FeatureGroupSpec(
        columns=BONG_FEATURES,
        provenance="number_reference.bong_duong|bong_am",
    ),
    "cham": FeatureGroupSpec(
        columns=CHAM_FEATURES,
        provenance="number_reference.dan_cham",
    ),
    "tong": FeatureGroupSpec(
        columns=TONG_FEATURES,
        provenance="number_reference.dan_tong_mod10",
    ),
}
DOMAIN_FEATURE_GROUPS: dict[str, list[str]] = {
    name: list(spec.columns) for name, spec in DOMAIN_FEATURE_SPECS.items()
}
ALL_DOMAIN_FEATURES = [
    column
    for spec in DOMAIN_FEATURE_SPECS.values()
    for column in spec.columns
]


def _balance(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    denominator = np.maximum(np.maximum(left.astype(float), right.astype(float)), 1.0)
    return np.clip(
        1.0 - np.abs(left.astype(float) - right.astype(float)) / denominator,
        0.0,
        1.0,
    )


def _validate_anchor_layout(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "anchor_date",
        "number",
        "freq_7d",
        "freq_30d",
        "freq_90d",
        "freq_365d",
        "gap",
        "hit_today",
        "path_support",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"Thiếu cột đặc trưng nền cho challenger miền: {sorted(missing)}"
        )
    if {_ORDER_COLUMN, _ANCHOR_COLUMN} & set(frame.columns):
        raise ValueError("Dữ liệu đầu vào trùng tên cột nội bộ của nhóm đặc trưng")

    ordered = frame.copy()
    ordered[_ORDER_COLUMN] = np.arange(len(ordered), dtype=np.int64)
    ordered[_ANCHOR_COLUMN] = pd.to_datetime(
        ordered["anchor_date"],
        errors="raise",
    ).dt.normalize()
    if ordered[_ANCHOR_COLUMN].isna().any():
        raise ValueError("Ngày neo không được để trống")

    numeric = pd.to_numeric(ordered["number"], errors="raise")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("Cột number chứa giá trị không hữu hạn")
    if not np.equal(numeric, np.floor(numeric)).all():
        raise ValueError("Cột number phải chứa số nguyên từ 00 đến 99")
    ordered["number"] = numeric.astype(int)
    if not ordered["number"].between(0, 99).all():
        raise ValueError("Cột number phải nằm trong miền 00..99")
    if ordered.duplicated([_ANCHOR_COLUMN, "number"]).any():
        raise ValueError("Mỗi ngày neo chỉ được có một dòng cho từng số")

    ordered = ordered.sort_values([_ANCHOR_COLUMN, "number"]).copy()
    counts = ordered.groupby(_ANCHOR_COLUMN, sort=False)["number"].nunique()
    if counts.empty or not bool((counts == 100).all()):
        raise ValueError("Mỗi ngày neo phải có đủ đúng 100 số khác nhau")
    expected = np.tile(np.arange(100, dtype=int), len(counts))
    if not np.array_equal(ordered["number"].to_numpy(dtype=int), expected):
        raise ValueError("Mỗi ngày neo phải chứa trọn miền số 00..99 theo thứ tự")
    return ordered


def augment_domain_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Thêm quan hệ cùng ngày neo mà không đọc kết quả của ngày mục tiêu."""

    if frame.empty:
        return frame.copy()

    ordered = _validate_anchor_layout(frame)
    anchor_count = ordered[_ANCHOR_COLUMN].nunique()

    def matrix(column: str) -> np.ndarray:
        values = pd.to_numeric(ordered[column], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"Cột {column} chứa giá trị không hữu hạn")
        return values.reshape(anchor_count, 100)

    hit = matrix("hit_today")
    frequency_7 = matrix("freq_7d")
    frequency_30 = matrix("freq_30d")
    frequency_90 = matrix("freq_90d")
    frequency_365 = matrix("freq_365d")
    gap = matrix("gap")
    path = matrix("path_support")

    def put(name: str, values: np.ndarray) -> None:
        ordered[name] = np.asarray(values).reshape(-1)

    partner_frequency_7 = frequency_7[:, CAP50_PARTNER]
    partner_frequency_30 = frequency_30[:, CAP50_PARTNER]
    partner_frequency_90 = frequency_90[:, CAP50_PARTNER]
    partner_frequency_365 = frequency_365[:, CAP50_PARTNER]
    put("cap50_partner_hit_today", hit[:, CAP50_PARTNER])
    put("cap50_partner_freq_7d", partner_frequency_7)
    put("cap50_partner_freq_30d", partner_frequency_30)
    put("cap50_partner_freq_90d", partner_frequency_90)
    put("cap50_partner_freq_365d", partner_frequency_365)
    put("cap50_partner_gap", gap[:, CAP50_PARTNER])

    put("cap50_pair_freq_30_mean", (frequency_30 + partner_frequency_30) / 2.0)
    put("cap50_pair_freq_90_mean", (frequency_90 + partner_frequency_90) / 2.0)
    put(
        "cap50_pair_freq_365_mean",
        (frequency_365 + partner_frequency_365) / 2.0,
    )
    put("cap50_pair_balance_30d", _balance(frequency_30, partner_frequency_30))
    put("cap50_pair_balance_90d", _balance(frequency_90, partner_frequency_90))
    put(
        "cap50_pair_balance_365d",
        _balance(frequency_365, partner_frequency_365),
    )
    put("cap50_is_kep_bong", np.tile(CAP50_IS_KEP_BONG, (anchor_count, 1)))

    family_sizes = np.array([len(members) for members in BO_MEMBERS], dtype=float)
    put("bo_family_size", np.tile(family_sizes, (anchor_count, 1)))
    put("bo_hit_today_rate", hit @ BO_MEAN.T)
    put("bo_freq_7d_mean", frequency_7 @ BO_MEAN.T)
    put("bo_freq_30d_mean", frequency_30 @ BO_MEAN.T)
    put("bo_freq_90d_mean", frequency_90 @ BO_MEAN.T)
    put("bo_freq_365d_mean", frequency_365 @ BO_MEAN.T)
    put("bo_gap_mean", gap @ BO_MEAN.T)
    put("bo_path_support_mean", path @ BO_MEAN.T)

    put("bong_duong_hit_today", hit[:, BONG_DUONG_PARTNER])
    put("bong_duong_freq_7d", frequency_7[:, BONG_DUONG_PARTNER])
    put("bong_duong_freq_30d", frequency_30[:, BONG_DUONG_PARTNER])
    put("bong_duong_gap", gap[:, BONG_DUONG_PARTNER])
    put("bong_am_hit_today", hit[:, BONG_AM_PARTNER])
    put("bong_am_freq_7d", frequency_7[:, BONG_AM_PARTNER])
    put("bong_am_freq_30d", frequency_30[:, BONG_AM_PARTNER])
    put("bong_am_gap", gap[:, BONG_AM_PARTNER])

    put("cham_hit_today_rate", hit @ CHAM_MEAN.T)
    put("cham_freq_7d_mean", frequency_7 @ CHAM_MEAN.T)
    put("cham_freq_30d_mean", frequency_30 @ CHAM_MEAN.T)
    put("cham_freq_90d_mean", frequency_90 @ CHAM_MEAN.T)
    put("cham_gap_mean", gap @ CHAM_MEAN.T)
    put("cham_path_support_mean", path @ CHAM_MEAN.T)

    put("tong_hit_today_rate", hit @ TONG_MEAN.T)
    put("tong_freq_7d_mean", frequency_7 @ TONG_MEAN.T)
    put("tong_freq_30d_mean", frequency_30 @ TONG_MEAN.T)
    put("tong_freq_90d_mean", frequency_90 @ TONG_MEAN.T)
    put("tong_gap_mean", gap @ TONG_MEAN.T)
    put("tong_path_support_mean", path @ TONG_MEAN.T)

    ordered["cap50_partner"] = np.tile(
        [f"{number:02d}" for number in CAP50_PARTNER],
        anchor_count,
    )
    ordered["cap50_pair_kind"] = np.tile(
        [cap_loto_50_kind(int(number)) for number in NUMBERS],
        anchor_count,
    )
    ordered["bo_family_id"] = np.tile(BO_FAMILY_IDS, anchor_count)
    ordered["bong_duong_partner"] = np.tile(
        [f"{number:02d}" for number in BONG_DUONG_PARTNER],
        anchor_count,
    )
    ordered["bong_am_partner"] = np.tile(
        [f"{number:02d}" for number in BONG_AM_PARTNER],
        anchor_count,
    )

    return (
        ordered.sort_values(_ORDER_COLUMN)
        .drop(columns=[_ORDER_COLUMN, _ANCHOR_COLUMN])
    )
