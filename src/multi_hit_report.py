"""Số đo cho trang «Lô VIP nhiều nháy»: trang chỉ in những gì tệp này đo được.

Hai phần, hai nhịp:

* ``vip.json`` — hằng ngày. Mô hình Lô VIP (``multi_hit_forecast``: kinh nghiệm cầu kèo, cầu hai
  nháy, cầu LOTO và dữ liệu nhiều nháy) dự báo năm con về ≥ 2 nháy ở kỳ kế tiếp, kèm lý do từng con
  và kiểm chứng walk-forward trên MỌI kỳ đã quay: mỗi kỳ chỉ dùng mô hình học trên các kỳ trước nó,
  rồi so với chọn bừa trên CHÍNH các kỳ ấy. Kèm năm cặp xiên 2 (``multi_hit_pairs``) với kiểm chứng
  walk-forward của riêng luật chọn cặp. ~60 giây trên 4 236 kỳ.
* ``benchmark.json`` — đóng băng. Giao thức lượt thử thứ hai (``multi_hit_benchmark``): 22 chiến
  lược chấm trên giai đoạn phát triển, một ứng viên kiểm MỘT lần trên 1 000 kỳ cuối, kèm phép kiểm
  độ nhạy trên lịch sử có cài tín hiệu. Phép kiểm một lần chỉ có nghĩa khi nó thật sự chạy một lần:
  nó đo trên lịch sử đến ``SECOND_ROUND_UNTIL`` (ngày đã chạy và công bố) và KHÔNG đo lại khi có kỳ
  mới. Đo lại mỗi tháng trên 1 000 kỳ cuối trượt dần là nhìn lại gần như cùng một tập kiểm ở cùng
  α, nên xác suất "đạt" chỉ do may cộng dồn quá 1%. Chỉ đo lại khi ``BENCHMARK_VERSION`` đổi hoặc
  khi chính đoạn lịch sử đã đăng ký bị sửa.

Không con số nào ở đây được đặt tay: kết luận "hơn / không hơn chọn bừa" trên trang suy từ ``z``,
``p`` và mức tin mà chính các phép đo trả về.

    python3 src/multi_hit_report.py                    # đo và ghi data/multi_hit/
    python3 src/multi_hit_report.py --force-benchmark  # đo lại cả giao thức lượt hai
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import norm, spearmanr

import multi_hit_forecast as forecast
import multi_hit_pairs as pairs
from atomic_io import atomic_write_text
from multi_hit_vip import (base_rate, counts_matrix, draws_from_frame, model_confidence, number_confidence,
                           random_pick_null)

OUT_DIR = "multi_hit"
VIP_FILE = "vip.json"
BENCHMARK_FILE = "benchmark.json"
#: Đổi định nghĩa một số đo thì tăng phiên bản của TỆP chứa nó: bản cũ bị bỏ và đo lại.
#: 2: thêm dấu vân tay lịch sử và sai số chuẩn GHÉP CẶP của "ít nhất một con về".
#: 3: lượt hai đóng băng ở lịch sử đến SECOND_ROUND_UNTIL, không còn đo lại theo cửa sổ trượt.
#: 4: mức tin của bộ lọc dùng p luôn hợp lệ (e-process), vì trang xem lại kết quả mỗi ngày.
#: 5: e-process chỉ chạy trên kỳ quay SAU VIP_FROZEN_AT (tiến cứu); hồi cứu chỉ còn để mô tả.
#: 6: độ nhạy ước lượng trên POWER_SEEDS lịch sử cài tín hiệu, so với POWER_REQUIRED đặt trước.
#: 7 (chỉ vip.json): thêm cặp xiên 2 cùng về (``multi_hit_pairs``).
#: 8 (chỉ vip.json): năm con chọn bằng luật lô rơi theo tỉ lệ kỳ sau, thay bộ lọc VIP; bộ lọc ấy
#:   đẩy con gan lên đầu (con 32 đứng đầu mười kỳ liền khi gan 10 → 19 kỳ).
#: 9 (chỉ vip.json): năm con là DỰ BÁO của mô hình Lô VIP (``multi_hit_forecast``) từ kinh nghiệm cầu
#:   kèo và cầu hai nháy, kèm lý do từng con; luật lô rơi chỉ liệt kê con vừa về nên đã nghỉ.
MEASURE_VERSION = 9
#: Phiên bản của benchmark.json. Tách khỏi MEASURE_VERSION vì lượt hai là phép kiểm MỘT lần đã
#: đóng băng: đổi số đo hằng ngày không được buộc nó chạy lại. Chỉ tăng khi định nghĩa của chính
#: lượt hai (hay phép kiểm độ nhạy của nó) đổi.
BENCHMARK_VERSION = 6
#: Độ nhạy của giao thức lượt hai: chạy lại trên chừng này lịch sử giả định độc lập (khác hạt giống)
#: và coi là ĐỦ NHẠY khi tỉ lệ đạt ≥ POWER_REQUIRED. Một lịch sử duy nhất có thể may hay rủi.
POWER_SEEDS = tuple(range(7, 27))
POWER_REQUIRED = 0.8
#: Ngày chốt của bộ lọc VIP đã nghỉ (lượt một). Tiến cứu của nó dừng ở 3 kỳ sau ngày này: trúng 0
#: lượt so với 0,55 của chọn bừa. Năm con trên trang nay theo ``multi_hit_forecast.FROZEN_AT``.
VIP_FROZEN_AT = "2026-10-12"
#: Lưới hệ số cược λ của e-process một phía (cược top-k trúng NHIỀU hơn chọn bừa). Với k = 5 và tối
#: đa 13 con về ≥ 2 nháy trong một kỳ, kỳ vọng chọn bừa ≤ 0,65 nên 1 + λ·(H − μ) > 0 với mọi λ ≤ 0,8.
BET_GRID = (0.05, 0.1, 0.2, 0.4, 0.8)
#: Lượt thử thứ hai là phép kiểm MỘT LẦN, đã chạy và công bố trên lịch sử đến ngày này. Muốn kiểm
#: trên kỳ mới thì đăng ký phép kiểm tiến cứu mới với ngày bắt đầu mới, đừng dời ngày này.
SECOND_ROUND_UNTIL = "2026-10-12"
#: Số kỳ gần nhất của walk-forward in lên trang (mỗi kỳ: 5 con đã chọn và con nào trúng).
RECENT_DRAWS = 10


def wilson(hits: float, n: float, z: float = float(norm.ppf(0.975))) -> tuple[float, float]:
    """Khoảng tin cậy Wilson 95% của một tỉ lệ; dùng được cả khi số trúng nhỏ."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def draw_level_interval(per_draw_hits, k: int) -> tuple[tuple[float, float], float]:
    """Khoảng Wilson 95% của tỉ lệ trúng top-k, với cỡ mẫu hiệu dụng tính theo CỤM kỳ.

    k con của cùng một kỳ chấm trên cùng 27 lô nên không phải k phép thử độc lập. Hệ số thiết kế
    deff = phương sai số trúng từng kỳ / (k·p·(1 − p)); cỡ mẫu hiệu dụng = số lượt chọn / deff
    (Kish), rồi Wilson trên cỡ mẫu ấy. Trả về (khoảng, deff).
    """
    hits = np.asarray(per_draw_hits, dtype=float)
    picks = len(hits) * k
    if len(hits) < 2 or picks == 0:
        return wilson(hits.sum(), picks), float("nan")
    rate = hits.sum() / picks
    independent = k * rate * (1 - rate)
    deff = float(hits.var(ddof=1) / independent) if independent > 0 else 1.0
    n_eff = picks / deff if deff > 0 else float(picks)
    return wilson(rate * n_eff, n_eff), deff


def anytime_p(hits, expected, grid: tuple[float, ...] = BET_GRID) -> tuple[float, float]:
    """p LUÔN HỢP LỆ cho "top-k trúng nhiều hơn chọn bừa", đúng cả khi xem lại sau MỖI kỳ mới.

    Trang chấm lại bộ lọc mỗi ngày trên lịch sử dài thêm một kỳ. So p của một lần xem với cùng ngưỡng
    mỗi ngày thì sớm muộn sẽ vượt ngưỡng chỉ do may. Ở đây: với mỗi kỳ t, Hₜ là số lượt trúng của
    top-k và μₜ = k·mₜ/100 là kỳ vọng của chọn bừa trong CÙNG kỳ; khi bộ lọc không có kỹ năng,
    E[Hₜ − μₜ | các kỳ trước] = 0. Tích Π (1 + λ·(Hₜ − μₜ)) là martingale không âm, trung bình trên
    lưới λ cũng vậy (e-process). Bất đẳng thức Ville: P(có lúc nào e ≥ 1/α) ≤ α, nên
    p = 1 / max e (chặn ở 1) hợp lệ dù xem bao nhiêu lần. Trả về (p, max e).
    """
    diff = np.asarray(hits, dtype=float) - np.asarray(expected, dtype=float)
    if diff.size == 0:
        return 1.0, 1.0
    lam = np.asarray(grid, dtype=float)[:, None]
    factors = 1.0 + lam * diff[None, :]
    if (factors <= 0).any():
        raise ValueError("hệ số cược làm vốn âm — thu hẹp BET_GRID")
    log_paths = np.cumsum(np.log(factors), axis=1)
    log_mix = logsumexp(log_paths, axis=0) - math.log(len(grid))
    best = max(0.0, float(log_mix.max()))
    return math.exp(-best), math.exp(best)


def load_raw(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sổ kết quả đầy đủ và sổ hai số, đọc dạng chuỗi như mọi bước khác của pipeline."""
    return (pd.read_csv(data_dir / "xsmb.csv", dtype={"date": str}),
            pd.read_csv(data_dir / "xsmb-2-digits.csv", dtype=str))


def load_history(data_dir: Path) -> tuple[np.ndarray, list[str]]:
    frame = pd.read_csv(data_dir / "xsmb-2-digits.csv", dtype=str)
    return draws_from_frame(frame)


def history_fingerprint(draws: np.ndarray, labels: list[str], n: int | None = None) -> str:
    """SHA-256 của ``n`` kỳ đầu (ngày và 27 lô): sửa bất kỳ ô nào trong đoạn ấy là đổi dấu vân tay."""
    n = len(draws) if n is None else n
    digest = hashlib.sha256()
    digest.update("\n".join(labels[:n]).encode("utf-8"))
    digest.update(np.ascontiguousarray(np.asarray(draws[:n], dtype=np.int16)).tobytes())
    return digest.hexdigest()


# --------------------------------------------------------------------------- lô rơi theo tỉ lệ kỳ sau


def vip_section(raw: pd.DataFrame, two: pd.DataFrame, *, cfg: forecast.ForecastConfig | None = None,
                prospective_after: str | None = None) -> dict:
    """Năm con dự báo cho kỳ kế tiếp từ mô hình Lô VIP, và kiểm chứng walk-forward của chính mô hình ấy.

    Toàn bộ walk-forward là MÔ TẢ hồi cứu: mô hình được thiết kế sau khi đã xem lịch sử ấy. Mức tin (và
    vì vậy kết luận "hơn") chỉ suy từ e-process trên các kỳ có ngày > ``prospective_after`` (mặc định
    ``multi_hit_forecast.FROZEN_AT``): một e-process chỉ kiểm soát báo nhầm khi quy tắc cược được chốt
    TRƯỚC khi thấy dữ liệu nó chấm.
    """
    cfg = cfg or forecast.ForecastConfig()
    after = forecast.FROZEN_AT if prospective_after is None else prospective_after
    table = forecast.build_table(raw, two, cfg)
    if len(table.anchors) <= cfg.warmup + 1:
        raise ValueError(f"cần hơn {cfg.warmup + 1} kỳ có đặc trưng để chấm mô hình")
    wf = forecast.walk_forward(table, cfg)
    ordered = two.assign(date=pd.to_datetime(two["date"]).dt.strftime("%Y-%m-%d")).sort_values("date")
    draws, labels = draws_from_frame(ordered.reset_index(drop=True))
    counts = table.counts
    k = cfg.top_k
    evaluated = table.anchors[wf.rows] + 1          # kỳ được dự báo
    n_multi = (counts[evaluated] >= 2).sum(axis=1)
    hits = wf.hits
    picks_total = len(wf.rows) * k
    expected, variance = random_pick_null(n_multi, k)
    z = float((hits.sum() - expected) / math.sqrt(variance)) if variance > 0 else 0.0
    (lo, hi), deff = draw_level_interval(hits, k)
    per_draw_expected = k * n_multi / 100
    dates = [labels[t] for t in evaluated]
    later = np.array([str(d) > after for d in dates], dtype=bool)
    pro_hits = hits[later]
    pro_expected = per_draw_expected[later]
    p_anytime, e_max = anytime_p(pro_hits, pro_expected)
    pro_lift = float(pro_hits.sum() / pro_expected.sum()) if pro_expected.sum() > 0 else float("nan")
    # Mức tin lấy p luôn hợp lệ của phần TIẾN CỨU: trang xem lại mỗi ngày (anytime_p), và mô hình được
    # thiết kế sau khi đã xem phần hồi cứu.
    level = model_confidence(p_anytime, pro_lift)
    base = base_rate()
    recent = []
    for j in range(len(wf.rows) - 1, max(len(wf.rows) - RECENT_DRAWS, 0) - 1, -1):
        t = int(evaluated[j])
        multi_today = int((counts[t] >= 2).sum())
        recent.append({
            "date": labels[t],
            "picks": [{"number": f"{i:02d}", "hits": int(counts[t, i])} for i in wf.picks[j]],
            "multi": int(hits[j]),
            # Chọn bừa k con trong CÙNG kỳ có m con về ≥ 2 nháy: kỳ vọng k·m/100 (siêu bội).
            "numbers_multi": multi_today,
            "expected": k * multi_today / 100,
        })
    # Dự báo kỳ tới: mô hình và hiệu chỉnh của chính khối walk-forward chứa kỳ ấy, để ngày mai phần
    # tiến cứu chấm đúng năm con người đọc đã thấy hôm nay.
    fc = wf.forecast
    model = fc.model
    last = len(table.anchors) - 1
    special = int(table.special[table.anchors[last]])
    picks = []
    for i, prob in zip(fc.picks, fc.printed, strict=True):
        picks.append({
            "number": f"{i:02d}",
            "probability": float(prob),
            "x_base": float(prob) / base,
            "confidence": number_confidence(level, float(prob), base),
            "reasons": forecast.reasons(model, table.X[last, i], int(i), special),
        })
    return {
        "version": MEASURE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_date": labels[-1],
        "target_date": table.target_date,
        "draws": int(len(draws)),
        "history_sha256": history_fingerprint(draws, labels),
        "base_theory": base,
        "rule": forecast.RULE,
        "config": {"top_k": k, "warmup": cfg.warmup, "refit": cfg.refit, "c_grid": list(forecast.C_GRID),
                   "features": len(forecast.FEATURES)},
        "model": {"C": model.C, "inner_gain": model.inner_gain,
                  "blocks": [{"start_date": labels[int(table.anchors[b["start"]]) + 1], "C": b["C"],
                              "inner_gain": b["inner_gain"]} for b in wf.blocks]},
        "experience": forecast.bridge_experience(table),
        "backtest": {
            "first_date": str(dates[0]),
            "last_date": str(dates[-1]),
            "draws": int(len(wf.rows)),
            "picks": int(picks_total),
            "hits": int(hits.sum()),
            "rate": float(hits.sum() / picks_total),
            "ci95": [_finite(lo), _finite(hi)],
            "design_effect": _finite(deff),
            "expected": float(expected),
            "random_rate": float(expected / picks_total),
            "lift": _finite(hits.sum() / expected) if expected > 0 else None,
            "z": z,
            "p_value": float(norm.sf(z)),
            # Xác suất TB đã in cho các con được chọn (hiệu chỉnh bằng các khối trước): so với tỉ lệ trúng.
            "predicted": float(wf.printed.mean()),
        },
        "prospective": {
            "after": after,
            "draws": int(later.sum()),
            "picks": int(later.sum()) * k,
            "hits": int(pro_hits.sum()),
            "expected": float(pro_expected.sum()),
            "lift": pro_lift if later.any() and math.isfinite(pro_lift) else None,
            "p_anytime": p_anytime,
            "e_max": e_max,
        },
        "confidence": level,
        "picks": picks,
        "recent": recent,
        "pairs": pairs_section(draws, labels, prospective_after=prospective_after),
    }


# --------------------------------------------------------------------------- cặp xiên 2


def _finite(value: float) -> float | None:
    """JSON hợp chuẩn không có NaN: số không xác định ghi thành null."""
    return float(value) if math.isfinite(value) else None


def pairs_section(draws: np.ndarray, labels: list[str], *,
                  prospective_after: str | None = None) -> dict | None:
    """Năm cặp xiên 2 cho kỳ kế tiếp và kiểm chứng walk-forward của luật chọn cặp.

    Như bộ lọc VIP: walk-forward trên lịch sử đến ngày chốt luật (``multi_hit_pairs.FROZEN_AT``) là
    mô tả hồi cứu; mức tin chỉ suy từ p luôn hợp lệ trên các kỳ SAU ngày ấy. Lịch sử chưa dài hơn
    cửa sổ của luật thì trả ``None``.
    """
    after = pairs.FROZEN_AT if prospective_after is None else prospective_after
    if len(draws) <= pairs.WINDOW:
        return None
    present = counts_matrix(draws) >= 1
    wf = pairs.walk_forward(present)
    k = pairs.TOP_K
    hits, expected = wf["hits"], wf["expected"]
    n = len(hits)
    diff = hits - expected
    # Các cặp chung một con trúng/trượt cùng nhau: sai số lấy từ hiệu từng kỳ, không giả định độc lập.
    se = float(diff.std(ddof=1) * math.sqrt(n)) if n > 1 else float("nan")
    z = float(diff.sum() / se) if se > 0 else float("nan")
    (lo, hi), deff = draw_level_interval(hits, k)
    dates = [labels[t] for t in wf["rows"]]
    later = np.array([str(d) > after for d in dates], dtype=bool)
    p_anytime, e_max = anytime_p(hits[later], expected[later])
    pro_expected = float(expected[later].sum())
    pro_lift = float(hits[later].sum() / pro_expected) if pro_expected > 0 else float("nan")
    level = model_confidence(p_anytime, pro_lift)
    recent = []
    for j in range(n - 1, max(n - RECENT_DRAWS, 0) - 1, -1):
        t = wf["rows"][j]
        row = present[t]
        recent.append({
            "date": labels[t],
            "picks": [{"pair": pairs.pair_label(i),
                       "hit": bool(row[pairs.PAIR_A[i]] and row[pairs.PAIR_B[i]])}
                      for i in wf["picks"][j]],
            "hits": int(hits[j]),
            "expected": float(expected[j]),
        })
    return {
        "frozen_at": after,
        "base_theory": pairs.base_rate(),
        "config": {"window": pairs.WINDOW, "top_k": k, "max_per_number": pairs.MAX_PER_NUMBER},
        "picks": [
            {"pair": pairs.pair_label(i), "together": together,
             "last_date": labels[last] if last >= 0 else None}
            for i, together, last in zip(wf["picks"][-1], wf["together"], wf["last"], strict=True)
        ],
        "backtest": {
            "first_date": str(dates[0]),
            "last_date": str(dates[-1]),
            "draws": n,
            "picks": n * k,
            "hits": int(hits.sum()),
            "rate": float(hits.sum() / (n * k)),
            "ci95": [_finite(lo), _finite(hi)],
            "design_effect": _finite(deff),
            "expected": float(expected.sum()),
            "random_rate": float(expected.sum() / (n * k)),
            "lift": _finite(hits.sum() / expected.sum()) if expected.sum() > 0 else None,
            "z": _finite(z),
            "p_value": _finite(float(norm.sf(z))) if math.isfinite(z) else None,
        },
        "prospective": {
            "after": after,
            "draws": int(later.sum()),
            "picks": int(later.sum()) * k,
            "hits": int(hits[later].sum()),
            "expected": pro_expected,
            "lift": pro_lift if later.any() and math.isfinite(pro_lift) else None,
            "p_anytime": p_anytime,
            "e_max": e_max,
        },
        "confidence": level,
        "recent": recent,
    }


# --------------------------------------------------------------------------- giao thức lượt hai


def _range_dates(span: tuple[int, int], labels: list[str]) -> list[str]:
    start, stop = span
    return [labels[start], labels[stop - 1]]


def _rank_correlation(result: dict) -> float:
    """Spearman giữa z giai đoạn phát triển và z giai đoạn kiểm, qua mọi chiến lược trừ chọn bừa.

    Có tín hiệu thật thì chiến lược mạnh ở giai đoạn này cũng mạnh ở giai đoạn sau (lịch sử cài
    tín hiệu cho +0,93); dao động ngẫu nhiên cho gần 0.
    """
    names = [n for n in result["dev_scores"] if n != "random"]
    dev = [result["dev_scores"][n].z for n in names]
    test = [result["test_scores"][n].z for n in names]
    return float(spearmanr(dev, test).statistic)


def _score(s) -> dict:
    return {"hits": s.hits, "picks": s.picks, "rate": s.rate, "expected": s.expected,
            "lift": s.lift, "z": s.z, "p": s.p_one_sided}


def paired_any_hit_se(candidate: np.ndarray, rival: np.ndarray, counts: np.ndarray, rows: range,
                      ks: tuple[int, ...] = (1, 3, 5, 10, 20)) -> dict[str, dict[str, float]]:
    """Sai số chuẩn của HIỆU tỉ lệ "ít nhất một con về" giữa hai chiến lược chấm trên CÙNG các kỳ.

    Hai tỉ lệ đo trên cùng kỳ quay (và hai bộ chọn có thể trùng nhau) nên là một cặp: phương sai
    lấy từ hiệu từng kỳ dₜ = 1[ứng viên có con về] − 1[đối thủ có con về], không cộng hai phương sai
    như với hai mẫu độc lập. Chọn top-k đúng như ``multi_hit_benchmark.any_hit_rates``.
    """
    import multi_hit_benchmark as bm

    rows = np.asarray(list(rows))
    got_a = np.take_along_axis(counts[rows], bm.top_k(candidate[rows], max(ks)), axis=1)
    got_b = np.take_along_axis(counts[rows], bm.top_k(rival[rows], max(ks)), axis=1)
    out: dict[str, dict[str, float]] = {"multi": {}, "single": {}}
    for kind, need in (("multi", 2), ("single", 1)):
        for k in ks:
            diff = ((got_a[:, :k] >= need).any(axis=1).astype(float)
                    - (got_b[:, :k] >= need).any(axis=1).astype(float))
            out[kind][str(k)] = float(diff.std(ddof=1) / math.sqrt(len(diff))) if len(diff) > 1 else float("nan")
    return out


def registered_draws(labels: list[str]) -> int:
    """Số kỳ của đoạn lịch sử mà lượt hai đã đăng ký: các kỳ có ngày ≤ ``SECOND_ROUND_UNTIL``."""
    return sum(1 for label in labels if str(label) <= SECOND_ROUND_UNTIL)


def _planted_run(job: tuple[int, int]) -> dict:
    """Một lượt giao thức lượt hai trên một lịch sử cài tín hiệu (hàm cấp module để chạy song song)."""
    import multi_hit_benchmark as bm

    n_draws, seed = job
    fake_draws, fake_weekdays = bm.planted_history(n_draws, seed=seed)
    return bm.run_protocol(fake_draws, fake_weekdays)


def power_estimate(n_draws: int, seeds: tuple[int, ...] = POWER_SEEDS, run=_planted_run,
                   workers: int | None = None) -> tuple[list[dict], dict]:
    """Chạy giao thức trên từng lịch sử cài tín hiệu; trả (các lượt, tóm tắt độ nhạy).

    Độ nhạy = tỉ lệ lượt mà ứng viên qua giai đoạn kiểm; ĐỦ NHẠY khi tỉ lệ ấy ≥ ``POWER_REQUIRED``.
    """
    jobs = [(n_draws, seed) for seed in seeds]
    if workers == 1 or len(jobs) <= 1:
        runs = [run(job) for job in jobs]
    else:
        import multiprocessing
        import os
        from concurrent.futures import ProcessPoolExecutor

        # "spawn", không "fork": tiến trình cha đã khởi động OpenMP (cây tăng cường trên dữ liệu thật),
        # và tách tiến trình bằng fork khi ấy làm tiến trình con kẹt cứng (đo 13-10-2026: 20 phút, 0% CPU).
        # Mỗi tiến trình con một luồng OpenMP để các lượt song song không tranh nhau cùng lõi.
        saved = os.environ.get("OMP_NUM_THREADS")
        os.environ["OMP_NUM_THREADS"] = "1"
        try:
            with ProcessPoolExecutor(max_workers=workers,
                                     mp_context=multiprocessing.get_context("spawn")) as pool:
                runs = list(pool.map(run, jobs))
        finally:
            if saved is None:
                os.environ.pop("OMP_NUM_THREADS", None)
            else:
                os.environ["OMP_NUM_THREADS"] = saved
    passes = sum(bool(r["candidate_passes"]) for r in runs)
    total = len(runs)
    rate = passes / total if total else float("nan")
    lo, hi = wilson(passes, total)
    return runs, {"runs": total, "passes": passes, "rate": rate, "ci95": [lo, hi],
                  "required": POWER_REQUIRED, "sensitive": bool(total and rate >= POWER_REQUIRED),
                  "seeds": list(seeds)}


def benchmark_section(draws: np.ndarray, labels: list[str]) -> dict:
    """Giao thức lượt hai trên đoạn lịch sử đã đăng ký, và cùng giao thức trên lịch sử có cài tín hiệu.

    Chỉ đọc các kỳ đến ``SECOND_ROUND_UNTIL``: kỳ mới hơn không bao giờ vào phép kiểm một lần này.
    """
    import multi_hit_benchmark as bm

    n = registered_draws(labels)
    draws, labels = draws[:n], list(labels[:n])
    weekdays = pd.to_datetime(pd.Series(labels)).dt.weekday.to_numpy()
    scores = bm.strategy_scores(draws, weekdays)
    real = bm.run_protocol(draws, weekdays, scores=scores)
    planted_runs, power = power_estimate(len(draws))
    planted = planted_runs[0]                    # lượt đầu: in chi tiết làm ví dụ
    cand = real["candidate"]
    strategies = [
        {"name": name, "dev": _score(real["dev_scores"][name]), "dev_holm": real["dev_holm"][name],
         "test": _score(real["test_scores"][name])}
        for name in sorted(real["dev_scores"], key=lambda n: -real["dev_scores"][n].z)
    ]
    any_hit = {side: {kind: {str(k): v for k, v in rates.items()} for kind, rates in table.items()}
               for side, table in real["any_hit"].items()}
    any_hit["paired_se"] = paired_any_hit_se(scores[cand], scores["random"], counts_matrix(draws),
                                             range(*real["test"]))
    return {
        "version": BENCHMARK_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_date": labels[-1],
        "draws": int(real["draws"]),
        "history_sha256": history_fingerprint(draws, labels),
        "registered_until": SECOND_ROUND_UNTIL,
        "top_k": bm.TOP_K,
        "alpha": bm.ALPHA,
        "dev": _range_dates(real["dev"], labels),
        "test": _range_dates(real["test"], labels),
        "dev_draws": real["dev"][1] - real["dev"][0],
        "test_draws": real["test"][1] - real["test"][0],
        "base_theory": real["base_theory"],
        "base_dev": real["base_dev"],
        "base_test": real["base_test"],
        "candidate": cand,
        "candidate_passes": real["candidate_passes"],
        "candidate_test": _score(real["test_scores"][cand]),
        "rank_correlation": _rank_correlation(real),
        "strategies": strategies,
        "any_hit": any_hit,
        "power": power,
        "power_check": {
            "planted": [f"{n:02d}" for n in bm.PLANTED],
            "plant_rate": bm.PLANT_RATE,
            "seed": power["seeds"][0],
            "candidate": planted["candidate"],
            "candidate_passes": planted["candidate_passes"],
            "candidate_dev_z": planted["dev_scores"][planted["candidate"]].z,
            "candidate_test": _score(planted["test_scores"][planted["candidate"]]),
            "base_test": planted["base_test"],
            "rank_correlation": _rank_correlation(planted),
        },
    }


def benchmark_is_valid(cached: dict | None, draws: np.ndarray, labels: list[str]) -> bool:
    """Bản đệm là số đo của ĐÚNG đoạn lịch sử đã đăng ký, và đoạn ấy chưa bị sửa.

    Đoạn đã đăng ký là các kỳ đến ``SECOND_ROUND_UNTIL``; so dấu vân tay của đoạn ấy trên lịch sử
    hiện tại. Sửa một kỳ cũ (ô lô hay ngày), cắt lịch sử, hay một bản đệm đo vượt ngày đăng ký đều
    bị bắt; kỳ mới nối thêm sau ngày ấy thì không bao giờ làm bản đệm cũ đi.
    """
    if not cached or cached.get("version") != BENCHMARK_VERSION:
        return False
    measured = int(cached.get("draws", 0))
    if measured <= 0 or measured != registered_draws(labels):
        return False
    return cached.get("history_sha256") == history_fingerprint(draws, labels, measured)


def vip_status(vip: dict | None, draws: np.ndarray, labels: list[str]) -> str:
    """Số đo bộ lọc so với lịch sử hiện tại: ``current``, ``behind`` hay ``invalid``.

    * ``current``: đo trên đúng lịch sử hiện tại.
    * ``behind``: đoạn đã đo còn nguyên nhưng sổ đã có thêm kỳ (bước đo hỏng sau kỳ mới). Kiểm chứng
      vẫn đúng cho đoạn ấy, nhưng top-k là cho một kỳ ĐÃ quay.
    * ``invalid``: thiếu tệp, khác phiên bản, hoặc đoạn đã đo bị sửa/cắt.
    """
    if not vip or vip.get("version") != MEASURE_VERSION:
        return "invalid"
    measured = int(vip.get("draws", 0))
    if not 0 < measured <= len(draws):
        return "invalid"
    if vip.get("history_sha256") != history_fingerprint(draws, labels, measured):
        return "invalid"
    return "current" if measured == len(draws) else "behind"


def benchmark_is_stale(cached: dict | None, draws: np.ndarray, labels: list[str]) -> bool:
    """Đo lại CHỈ khi bản đệm không còn là số đo của đoạn đã đăng ký; kỳ mới không mở lại phép kiểm."""
    return not benchmark_is_valid(cached, draws, labels)


# --------------------------------------------------------------------------- ghi


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def run(data_dir: Path, *, force_benchmark: bool = False,
        cfg: forecast.ForecastConfig | None = None) -> dict[str, Path]:
    draws, labels = load_history(data_dir)
    out = data_dir / OUT_DIR
    written = {"vip": out / VIP_FILE}
    _write(written["vip"], vip_section(*load_raw(data_dir), cfg=cfg))
    bench_path = out / BENCHMARK_FILE
    if force_benchmark or benchmark_is_stale(_read(bench_path), draws, labels):
        _write(bench_path, benchmark_section(draws, labels))
        written["benchmark"] = bench_path
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--force-benchmark", action="store_true",
                        help="đo lại giao thức lượt hai dù bản đệm còn mới")
    args = parser.parse_args(argv)
    for name, path in run(Path(args.data_dir), force_benchmark=args.force_benchmark).items():
        print(f"[OK] {name} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
