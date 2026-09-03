from __future__ import annotations

"""Canonical experimental feature families for the cầu-kèo challenger.

These transforms combine only features already known on the same anchor date.
They define research candidates, not predictive claims. Production may use a
family only when the temporal challenger gate explicitly promotes it.
"""

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

FEATURE_GROUP_SCHEMA_VERSION = 2
NUMBERS = np.arange(100, dtype=np.int16)
CAP50_PARTNER = np.array(
    [int(cap_loto_50_partner(int(n))) for n in NUMBERS], dtype=np.int16
)
BONG_DUONG_PARTNER = np.array(
    [int(bong_duong(int(n))) for n in NUMBERS], dtype=np.int16
)
BONG_AM_PARTNER = np.array(
    [int(bong_am(int(n))) for n in NUMBERS], dtype=np.int16
)
CAP50_IS_KEP_BONG = np.array(
    [1 if cap_loto_50_kind(int(n)) == "kep_bong" else 0 for n in NUMBERS],
    dtype=np.int8,
)
BO_FAMILY_IDS = np.array([bo_family_id(int(n)) for n in NUMBERS], dtype=object)
BO_MEMBERS = [
    np.array(sorted(int(x) for x in bo(int(n))), dtype=np.int16) for n in NUMBERS
]
CHAM_MEMBERS = [
    np.array(
        sorted(int(x) for x in set(dan_cham(int(n) // 10)) | set(dan_cham(int(n) % 10))),
        dtype=np.int16,
    )
    for n in NUMBERS
]
TONG_MEMBERS = [
    np.array(
        [int(x) for x in dan_tong_mod10((int(n) // 10 + int(n) % 10) % 10)],
        dtype=np.int16,
    )
    for n in NUMBERS
]


def _mean_matrix(groups: list[np.ndarray]) -> np.ndarray:
    out = np.zeros((100, 100), dtype=np.float32)
    for n, members in enumerate(groups):
        out[n, members] = 1.0 / float(len(members))
    return out


BO_MEAN = _mean_matrix(BO_MEMBERS)
CHAM_MEAN = _mean_matrix(CHAM_MEMBERS)
TONG_MEAN = _mean_matrix(TONG_MEMBERS)

# Direct relation to the canonical partner number. For 90 non-doubles this is
# the reverse number; for the ten doubles it is the documented kép-bóng partner.
PARTNER_FEATURES = [
    "cap50_partner_hit_today",
    "cap50_partner_freq_7d",
    "cap50_partner_freq_30d",
    "cap50_partner_freq_90d",
    "cap50_partner_freq_365d",
    "cap50_partner_gap",
]

# Pair-level summaries for the canonical 50-pair partition. Kept separate from
# direct partner features so each family must independently prove OOS skill.
CAP_50_FEATURES = [
    "cap50_pair_freq_30_mean",
    "cap50_pair_freq_90_mean",
    "cap50_pair_freq_365_mean",
    "cap50_pair_balance_30d",
    "cap50_pair_balance_90d",
    "cap50_pair_balance_365d",
    "cap50_is_kep_bong",
]

BO_FEATURES = [
    "bo_family_size",
    "bo_hit_today_rate",
    "bo_freq_7d_mean",
    "bo_freq_30d_mean",
    "bo_freq_90d_mean",
    "bo_freq_365d_mean",
    "bo_gap_mean",
    "bo_path_support_mean",
]
BONG_FEATURES = [
    "bong_duong_hit_today",
    "bong_duong_freq_7d",
    "bong_duong_freq_30d",
    "bong_duong_gap",
    "bong_am_hit_today",
    "bong_am_freq_7d",
    "bong_am_freq_30d",
    "bong_am_gap",
]
CHAM_FEATURES = [
    "cham_hit_today_rate",
    "cham_freq_7d_mean",
    "cham_freq_30d_mean",
    "cham_freq_90d_mean",
    "cham_gap_mean",
    "cham_path_support_mean",
]
TONG_FEATURES = [
    "tong_hit_today_rate",
    "tong_freq_7d_mean",
    "tong_freq_30d_mean",
    "tong_freq_90d_mean",
    "tong_gap_mean",
    "tong_path_support_mean",
]

DOMAIN_FEATURE_GROUPS: dict[str, list[str]] = {
    "partner": PARTNER_FEATURES,
    "cap_50": CAP_50_FEATURES,
    "bo": BO_FEATURES,
    "bong": BONG_FEATURES,
    "cham": CHAM_FEATURES,
    "tong": TONG_FEATURES,
}
ALL_DOMAIN_FEATURES = [
    feature for group in DOMAIN_FEATURE_GROUPS.values() for feature in group
]


def _balance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = np.maximum(np.maximum(a.astype(float), b.astype(float)), 1.0)
    return np.clip(1.0 - np.abs(a.astype(float) - b.astype(float)) / denom, 0.0, 1.0)


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
        raise ValueError(f"domain challenger missing base feature columns: {sorted(missing)}")

    ordered = frame.copy()
    ordered["anchor_date"] = pd.to_datetime(ordered["anchor_date"], errors="raise").dt.normalize()
    ordered["number"] = pd.to_numeric(ordered["number"], errors="raise").astype(int)
    if ordered.duplicated(["anchor_date", "number"]).any():
        raise ValueError("duplicate anchor_date/number rows")
    ordered = ordered.sort_values(["anchor_date", "number"]).copy()
    counts = ordered.groupby("anchor_date", sort=False)["number"].nunique()
    if counts.empty or not bool((counts == 100).all()):
        raise ValueError("every anchor_date must contain exactly 100 unique numbers")
    expected = np.tile(np.arange(100, dtype=int), len(counts))
    actual = ordered["number"].to_numpy(dtype=int)
    if not np.array_equal(actual, expected):
        raise ValueError("each anchor_date must contain the complete ordered 00..99 universe")
    return ordered


def augment_domain_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add same-anchor domain transforms without reading any later target date."""
    if frame.empty:
        return frame.copy()

    original_index = frame.index
    ordered = _validate_anchor_layout(frame)
    n_anchors = ordered["anchor_date"].nunique()

    def matrix(col: str) -> np.ndarray:
        return (
            pd.to_numeric(ordered[col], errors="raise")
            .to_numpy(dtype=float)
            .reshape(n_anchors, 100)
        )

    hit = matrix("hit_today")
    f7 = matrix("freq_7d")
    f30 = matrix("freq_30d")
    f90 = matrix("freq_90d")
    f365 = matrix("freq_365d")
    gap = matrix("gap")
    path = matrix("path_support")

    def put(name: str, values: np.ndarray) -> None:
        ordered[name] = np.asarray(values).reshape(-1)

    partner_f7 = f7[:, CAP50_PARTNER]
    partner_f30 = f30[:, CAP50_PARTNER]
    partner_f90 = f90[:, CAP50_PARTNER]
    partner_f365 = f365[:, CAP50_PARTNER]
    put("cap50_partner_hit_today", hit[:, CAP50_PARTNER])
    put("cap50_partner_freq_7d", partner_f7)
    put("cap50_partner_freq_30d", partner_f30)
    put("cap50_partner_freq_90d", partner_f90)
    put("cap50_partner_freq_365d", partner_f365)
    put("cap50_partner_gap", gap[:, CAP50_PARTNER])

    put("cap50_pair_freq_30_mean", (f30 + partner_f30) / 2.0)
    put("cap50_pair_freq_90_mean", (f90 + partner_f90) / 2.0)
    put("cap50_pair_freq_365_mean", (f365 + partner_f365) / 2.0)
    put("cap50_pair_balance_30d", _balance(f30, partner_f30))
    put("cap50_pair_balance_90d", _balance(f90, partner_f90))
    put("cap50_pair_balance_365d", _balance(f365, partner_f365))
    put("cap50_is_kep_bong", np.tile(CAP50_IS_KEP_BONG, (n_anchors, 1)))

    put(
        "bo_family_size",
        np.tile(np.array([len(x) for x in BO_MEMBERS], dtype=float), (n_anchors, 1)),
    )
    put("bo_hit_today_rate", hit @ BO_MEAN.T)
    put("bo_freq_7d_mean", f7 @ BO_MEAN.T)
    put("bo_freq_30d_mean", f30 @ BO_MEAN.T)
    put("bo_freq_90d_mean", f90 @ BO_MEAN.T)
    put("bo_freq_365d_mean", f365 @ BO_MEAN.T)
    put("bo_gap_mean", gap @ BO_MEAN.T)
    put("bo_path_support_mean", path @ BO_MEAN.T)

    put("bong_duong_hit_today", hit[:, BONG_DUONG_PARTNER])
    put("bong_duong_freq_7d", f7[:, BONG_DUONG_PARTNER])
    put("bong_duong_freq_30d", f30[:, BONG_DUONG_PARTNER])
    put("bong_duong_gap", gap[:, BONG_DUONG_PARTNER])
    put("bong_am_hit_today", hit[:, BONG_AM_PARTNER])
    put("bong_am_freq_7d", f7[:, BONG_AM_PARTNER])
    put("bong_am_freq_30d", f30[:, BONG_AM_PARTNER])
    put("bong_am_gap", gap[:, BONG_AM_PARTNER])

    put("cham_hit_today_rate", hit @ CHAM_MEAN.T)
    put("cham_freq_7d_mean", f7 @ CHAM_MEAN.T)
    put("cham_freq_30d_mean", f30 @ CHAM_MEAN.T)
    put("cham_freq_90d_mean", f90 @ CHAM_MEAN.T)
    put("cham_gap_mean", gap @ CHAM_MEAN.T)
    put("cham_path_support_mean", path @ CHAM_MEAN.T)

    put("tong_hit_today_rate", hit @ TONG_MEAN.T)
    put("tong_freq_7d_mean", f7 @ TONG_MEAN.T)
    put("tong_freq_30d_mean", f30 @ TONG_MEAN.T)
    put("tong_freq_90d_mean", f90 @ TONG_MEAN.T)
    put("tong_gap_mean", gap @ TONG_MEAN.T)
    put("tong_path_support_mean", path @ TONG_MEAN.T)

    ordered["cap50_partner"] = np.tile(
        [f"{n:02d}" for n in CAP50_PARTNER], n_anchors
    )
    ordered["cap50_pair_kind"] = np.tile(
        [cap_loto_50_kind(int(n)) for n in NUMBERS], n_anchors
    )
    ordered["bo_family_id"] = np.tile(BO_FAMILY_IDS, n_anchors)
    ordered["bong_duong_partner"] = np.tile(
        [f"{n:02d}" for n in BONG_DUONG_PARTNER], n_anchors
    )
    ordered["bong_am_partner"] = np.tile(
        [f"{n:02d}" for n in BONG_AM_PARTNER], n_anchors
    )

    # Restore the caller's original order/index after deterministic date-number work.
    ordered = ordered.sort_index()
    if not ordered.index.equals(original_index):
        ordered = ordered.reindex(original_index)
    return ordered
