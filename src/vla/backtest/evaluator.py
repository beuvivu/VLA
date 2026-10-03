"""Chỉ số chấm dự báo xác suất: logloss, Brier, Top-K, ROI theo luật trả thưởng.

Mọi chỉ số tính TỪNG KỲ rồi mới gộp, để so hai mô hình bằng hiệu từng kỳ
(kỳ quay độc lập nên sai số chuẩn của trung bình hiệu là phép so công bằng).

Luật trả thưởng mặc định (đặt được qua ``Payout``): lô 23 nghìn một điểm, trúng
80 nghìn mỗi nháy; Đặc Biệt 1 ăn 70. Đánh ngẫu nhiên thì kỳ vọng hoàn
``80·0,27/23 ≈ 0,939`` cho lô và ``70/100 = 0,70`` cho Đặc Biệt — tức nhà cái
giữ khoảng 6% và 30%. Không có xác suất hiệu chỉnh nào vượt được mức ấy nếu
không có tín hiệu thật.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from xsmb_domain import LOTO_DRAWS_PER_DAY

Mode = Literal["loto", "de"]
EPS = 1e-6


@dataclass(frozen=True)
class Payout:
    lo_cost: float = 23.0
    lo_win_per_hit: float = 80.0
    de_cost: float = 1.0
    de_win: float = 70.0


def cumulative_reference(mode: Mode, hit: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Dự báo hằng số làm mốc kỹ năng 0, cho từng kỳ đích.

    Đặc Biệt: 1/100. LOTO: tỉ lệ về tích luỹ qua MỌI kỳ trước kỳ đích ấy
    (kỳ 0..target-1) — cập nhật từng kỳ, không đông cứng ở đầu khối.
    """
    targets = np.asarray(targets, dtype=np.int64)
    if mode == "de":
        return np.full((len(targets), 100), 0.01)
    rate = np.cumsum(hit.mean(axis=1))[targets - 1] / targets
    return np.repeat(rate[:, None], 100, axis=1)


def daily_logloss(mode: Mode, p: np.ndarray, hits: np.ndarray) -> np.ndarray:
    if mode == "de":
        q = np.clip(p / p.sum(axis=1, keepdims=True), EPS, 1.0)
        return -np.log((q * hits).sum(axis=1))
    q = np.clip(p, EPS, 1 - EPS)
    return -(hits * np.log(q) + (1 - hits) * np.log(1 - q)).mean(axis=1)


def daily_brier(mode: Mode, p: np.ndarray, hits: np.ndarray) -> np.ndarray:
    """Đặc Biệt: Brier đa lớp chuẩn (TỔNG trên 100 lớp). LOTO: trung bình 100 biên."""
    if mode == "de":
        q = p / p.sum(axis=1, keepdims=True)
        return ((q - hits) ** 2).sum(axis=1)
    return ((p - hits) ** 2).mean(axis=1)


def top_k(p: np.ndarray, k: int) -> np.ndarray:
    """(n, k) chỉ số con số xác suất cao nhất; hoà thì số nhỏ trước."""
    order = np.lexsort((np.broadcast_to(np.arange(p.shape[1]), p.shape), -p), axis=1)
    return order[:, :k]


def expected_hits_per_number(p: np.ndarray) -> np.ndarray:
    """Số nháy kỳ vọng từ xác suất "về ít nhất một lần" của LOTO.

    27 giải độc lập, mỗi giải ra con n với xác suất q: ``P(≥1) = 1-(1-q)^27``
    nên ``q = 1-(1-p)^{1/27}`` và kỳ vọng số nháy là ``27q``.
    """
    q = 1.0 - np.power(np.clip(1.0 - p, EPS, 1.0), 1.0 / LOTO_DRAWS_PER_DAY)
    return LOTO_DRAWS_PER_DAY * q


def roi_top_k(mode: Mode, p: np.ndarray, counts: np.ndarray, special: np.ndarray, k: int, pay: Payout) -> dict:
    """Mỗi kỳ đánh đều k con xác suất cao nhất."""
    chosen = top_k(p, k)
    rows = np.arange(len(p))[:, None]
    if mode == "loto":
        cost = k * pay.lo_cost * len(p)
        win = pay.lo_win_per_hit * counts[rows, chosen].sum()
    else:
        cost = k * pay.de_cost * len(p)
        win = pay.de_win * (chosen == special[:, None]).sum()
    return {"stake": float(cost), "return": float(win), "roi": float(win / cost - 1.0) if cost else 0.0}


def roi_positive_ev(mode: Mode, p: np.ndarray, counts: np.ndarray, special: np.ndarray, pay: Payout) -> dict:
    """Chỉ đánh con có giá trị kỳ vọng dương THEO CHÍNH xác suất mô hình."""
    if mode == "loto":
        ev = pay.lo_win_per_hit * expected_hits_per_number(p) - pay.lo_cost
        bet = ev > 0
        cost = pay.lo_cost * bet.sum()
        win = pay.lo_win_per_hit * (counts * bet).sum()
    else:
        q = p / p.sum(axis=1, keepdims=True)
        bet = pay.de_win * q - pay.de_cost > 0
        cost = pay.de_cost * bet.sum()
        win = pay.de_win * bet[np.arange(len(p)), special].sum()
    return {
        "bets": int(bet.sum()),
        "days_with_bets": int(bet.any(axis=1).sum()),
        "stake": float(cost),
        "return": float(win),
        "roi": float(win / cost - 1.0) if cost else None,
    }


def calibration_table(mode: Mode, p: np.ndarray, hits: np.ndarray, bins: int = 10) -> list[dict]:
    """Chia theo phân vị xác suất dự báo; so xác suất trung bình với tần suất thật."""
    q = p / p.sum(axis=1, keepdims=True) if mode == "de" else p
    flat, y = q.reshape(-1), hits.reshape(-1)
    edges = np.quantile(flat, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, flat, side="right") - 1, 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if m.any():
            out.append({"bin": b, "count": int(m.sum()), "predicted": float(flat[m].mean()), "observed": float(y[m].mean())})
    return out


def paired(model: np.ndarray, reference: np.ndarray) -> dict:
    """Hiệu logloss từng kỳ (tham chiếu − mô hình): dương = mô hình tốt hơn."""
    d = np.asarray(reference) - np.asarray(model)
    se = float(d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1 else float("nan")
    return {"mean_gain": float(d.mean()), "se": se, "z": float(d.mean() / se) if se and se > 0 else 0.0}


def evaluate(
    mode: Mode,
    p: np.ndarray,
    counts: np.ndarray,
    special: np.ndarray,
    reference: np.ndarray,
    *,
    ks: tuple[int, ...] = (5, 10, 20),
    pay: Payout | None = None,
) -> dict:
    """Bảng chỉ số của một mô hình trên ``n`` kỳ đích.

    ``counts``: (n, 100) số nháy thật; ``special``: (n,) hai số cuối Đặc Biệt;
    ``reference``: (n, 100) dự báo hằng số dùng làm mốc kỹ năng.
    """
    pay = pay or Payout()
    if mode == "loto":
        hits = (counts > 0).astype(np.float64)
    else:
        hits = np.zeros(p.shape)
        hits[np.arange(len(p)), special] = 1.0
    ll = daily_logloss(mode, p, hits)
    ll_ref = daily_logloss(mode, reference, hits)
    br = daily_brier(mode, p, hits)
    br_ref = daily_brier(mode, reference, hits)
    out: dict = {
        "days": int(len(p)),
        "logloss": float(ll.mean()),
        "logloss_reference": float(ll_ref.mean()),
        "logloss_skill": float(1.0 - ll.mean() / ll_ref.mean()),
        "brier": float(br.mean()),
        "brier_reference": float(br_ref.mean()),
        "brier_skill": float(1.0 - br.mean() / br_ref.mean()),
        "vs_reference": paired(ll, ll_ref),
        "calibration": calibration_table(mode, p, hits),
        "top_k": {},
        "roi_top_k": {},
        "roi_positive_ev": roi_positive_ev(mode, p, counts, special, pay),
    }
    rows = np.arange(len(p))[:, None]
    for k in ks:
        chosen = top_k(p, k)
        got = hits[rows, chosen]
        if mode == "loto":
            base = float(hits.mean())
            out["top_k"][str(k)] = {
                "hits_per_day": float(got.sum(axis=1).mean()),
                "hit_rate": float(got.mean()),
                "random_hit_rate": base,
                "any_hit": float((got.sum(axis=1) > 0).mean()),
            }
        else:
            out["top_k"][str(k)] = {"hit_rate": float(got.sum(axis=1).mean()), "random_hit_rate": k / 100.0}
        out["roi_top_k"][str(k)] = roi_top_k(mode, p, counts, special, k, pay)
    return out
