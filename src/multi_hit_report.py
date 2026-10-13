"""Số đo cho trang «Lô VIP nhiều nháy»: trang chỉ in những gì tệp này đo được.

Hai phần, hai nhịp:

* ``vip.json`` — hằng ngày. Bộ lọc VIP (``multi_hit_vip``) xếp hạng kỳ kế tiếp, kèm kiểm chứng
  walk-forward lồng nhau trên MỌI kỳ đã quay: mỗi kỳ được chấm bằng trọng số chọn trên 30 kỳ ngay
  trước nó, rồi so với chọn bừa trên CHÍNH các kỳ ấy. ~25 giây trên 4 233 kỳ.
* ``benchmark.json`` — đóng băng. Giao thức lượt thử thứ hai (``multi_hit_benchmark``): 22 chiến
  lược chấm trên giai đoạn phát triển, một ứng viên kiểm MỘT lần trên 1 000 kỳ cuối, kèm phép kiểm
  độ nhạy trên lịch sử có cài tín hiệu. Phép kiểm một lần chỉ có nghĩa khi nó thật sự chạy một lần:
  nó đo trên lịch sử đến ``SECOND_ROUND_UNTIL`` (ngày đã chạy và công bố) và KHÔNG đo lại khi có kỳ
  mới. Đo lại mỗi tháng trên 1 000 kỳ cuối trượt dần là nhìn lại gần như cùng một tập kiểm ở cùng
  α, nên xác suất "đạt" chỉ do may cộng dồn quá 1%. Chỉ đo lại khi ``MEASURE_VERSION`` đổi hoặc khi
  chính đoạn lịch sử đã đăng ký bị sửa.

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

from atomic_io import atomic_write_text
from multi_hit_vip import (VIPConfig, VIPMultiHitModel, base_rate, counts_matrix, draws_from_frame,
                           model_confidence, number_confidence)

OUT_DIR = "multi_hit"
VIP_FILE = "vip.json"
BENCHMARK_FILE = "benchmark.json"
#: Đổi định nghĩa một số đo thì tăng: bản đệm cũ bị bỏ và đo lại.
#: 2: thêm dấu vân tay lịch sử và sai số chuẩn GHÉP CẶP của "ít nhất một con về".
#: 3: lượt hai đóng băng ở lịch sử đến SECOND_ROUND_UNTIL, không còn đo lại theo cửa sổ trượt.
#: 4: mức tin của bộ lọc dùng p luôn hợp lệ (e-process), vì trang xem lại kết quả mỗi ngày.
#: 5: e-process chỉ chạy trên kỳ quay SAU VIP_FROZEN_AT (tiến cứu); hồi cứu chỉ còn để mô tả.
MEASURE_VERSION = 5
#: Bộ lọc VIP được thiết kế SAU khi đã xem lịch sử đến ngày này (đặc trưng, tham số, cách chọn trọng
#: số), nên phần kiểm chứng hồi cứu không phải bằng chứng "chưa từng thấy". Mức tin chỉ tính trên các
#: kỳ quay sau ngày ấy. Đừng dời ngày; đổi bộ lọc thì đăng ký ngày mới.
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


# --------------------------------------------------------------------------- bộ lọc VIP


def vip_section(draws: np.ndarray, labels: list[str], cfg: VIPConfig | None = None, *,
                prospective_after: str | None = None) -> dict:
    """Dự báo kỳ kế tiếp và kiểm chứng walk-forward của bộ lọc VIP.

    Toàn bộ walk-forward là MÔ TẢ hồi cứu. Mức tin (và vì vậy kết luận "hơn") chỉ suy từ e-process
    trên các kỳ có ngày > ``prospective_after`` (mặc định ``VIP_FROZEN_AT``): một e-process chỉ
    kiểm soát báo nhầm khi quy tắc cược được chốt TRƯỚC khi thấy dữ liệu nó chấm.
    """
    cfg = cfg or VIPConfig()
    after = VIP_FROZEN_AT if prospective_after is None else prospective_after
    model = VIPMultiHitModel(draws, labels, cfg)
    report = model.predict_next()
    bt = report.backtest
    (lo, hi), deff = draw_level_interval(bt.per_draw["trung"], cfg.top_k)
    counts = counts_matrix(model.draws)
    index = {label: t for t, label in enumerate(labels)}
    rows = [index[k] for k in bt.per_draw["ky"]]
    per_draw_expected = cfg.top_k * (counts[rows] >= 2).sum(axis=1) / 100
    later = (bt.per_draw["ky"].astype(str) > after).to_numpy()
    pro_hits = bt.per_draw["trung"].to_numpy()[later]
    pro_expected = per_draw_expected[later]
    p_anytime, e_max = anytime_p(pro_hits, pro_expected)
    pro_lift = float(pro_hits.sum() / pro_expected.sum()) if pro_expected.sum() > 0 else float("nan")
    # Mức tin lấy p luôn hợp lệ của phần TIẾN CỨU: trang xem lại mỗi ngày (anytime_p), và bộ lọc
    # được thiết kế sau khi đã xem phần hồi cứu.
    level = model_confidence(p_anytime, pro_lift)
    base = base_rate()
    recent = []
    for row in bt.per_draw.tail(RECENT_DRAWS).iloc[::-1].itertuples(index=False):
        t = index[row.ky]
        multi_today = int((counts[t] >= 2).sum())
        recent.append({
            "date": row.ky,
            "picks": [{"number": n, "hits": int(counts[t, int(n)])} for n in row.chon],
            "multi": int(row.trung),
            # Chọn bừa k con trong CÙNG kỳ có m con về ≥ 2 nháy: kỳ vọng k·m/100 (siêu bội).
            "numbers_multi": multi_today,
            "expected": cfg.top_k * multi_today / 100,
        })
    evaluated = bt.per_draw["ky"]
    return {
        "version": MEASURE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_date": labels[-1],
        "draws": int(len(model.draws)),
        "history_sha256": history_fingerprint(draws, labels),
        "base_theory": base_rate(),
        "config": {"top_k": cfg.top_k, "window": cfg.window, "weight_window": cfg.weight_window,
                   "normalisation": cfg.normalisation},
        "weights": {k: float(v) for k, v in report.weights.items()},
        "backtest": {
            "first_date": str(evaluated.iloc[0]),
            "last_date": str(evaluated.iloc[-1]),
            "draws": bt.draws,
            "picks": bt.picks,
            "hits": bt.hits,
            "rate": bt.hit_rate,
            "ci95": [lo, hi],
            "design_effect": deff,
            "expected": bt.expected,
            "random_rate": bt.random_rate,
            "lift": bt.lift,
            "z": bt.z,
            "p_value": bt.p_value,
        },
        "prospective": {
            "after": after,
            "draws": int(later.sum()),
            "picks": int(later.sum()) * cfg.top_k,
            "hits": int(pro_hits.sum()),
            "expected": float(pro_expected.sum()),
            "lift": pro_lift if later.any() else None,     # chưa có kỳ tiến cứu: không có lift
            "p_anytime": p_anytime,
            "e_max": e_max,
        },
        "confidence": level,
        "picks": [
            {"number": p.number, "vip_score": p.vip_score, "probability": p.probability,
             "x_base": p.lift, "confidence": number_confidence(level, p.probability, base),
             "reasons": p.reasons()}
            for p in report.picks
        ],
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
    fake_draws, fake_weekdays = bm.planted_history(len(draws))
    planted = bm.run_protocol(fake_draws, fake_weekdays)
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
        "version": MEASURE_VERSION,
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
        "power_check": {
            "planted": [f"{n:02d}" for n in bm.PLANTED],
            "plant_rate": bm.PLANT_RATE,
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
    if not cached or cached.get("version") != MEASURE_VERSION:
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


def run(data_dir: Path, *, force_benchmark: bool = False) -> dict[str, Path]:
    draws, labels = load_history(data_dir)
    out = data_dir / OUT_DIR
    written = {"vip": out / VIP_FILE}
    _write(written["vip"], vip_section(draws, labels))
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
