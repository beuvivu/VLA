"""Số đo cho trang «Lô VIP nhiều nháy»: trang chỉ in những gì tệp này đo được.

Hai phần, hai nhịp:

* ``vip.json`` — hằng ngày. Bộ lọc VIP (``multi_hit_vip``) xếp hạng kỳ kế tiếp, kèm kiểm chứng
  walk-forward lồng nhau trên MỌI kỳ đã quay: mỗi kỳ được chấm bằng trọng số chọn trên 30 kỳ ngay
  trước nó, rồi so với chọn bừa trên CHÍNH các kỳ ấy. ~25 giây trên 4 233 kỳ.
* ``benchmark.json`` — đệm. Giao thức lượt thử thứ hai (``multi_hit_benchmark``): 22 chiến lược
  chấm trên giai đoạn phát triển, một ứng viên kiểm MỘT lần trên 1 000 kỳ cuối, kèm phép kiểm độ
  nhạy trên lịch sử có cài tín hiệu. ~4 phút, nên chỉ đo lại khi lịch sử dài thêm
  ``BENCHMARK_REFRESH_DRAWS`` kỳ, khi ``MEASURE_VERSION`` đổi, hoặc khi lịch sử bị viết lại.

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
from scipy.stats import norm, spearmanr

from atomic_io import atomic_write_text
from multi_hit_vip import VIPConfig, VIPMultiHitModel, base_rate, counts_matrix, draws_from_frame

OUT_DIR = "multi_hit"
VIP_FILE = "vip.json"
BENCHMARK_FILE = "benchmark.json"
#: Đổi định nghĩa một số đo thì tăng: bản đệm cũ bị bỏ và đo lại.
#: 2: thêm dấu vân tay lịch sử và sai số chuẩn GHÉP CẶP của "ít nhất một con về".
MEASURE_VERSION = 2
#: Giao thức lượt hai đo lại khi lịch sử dài thêm chừng này kỳ (~ một tháng).
BENCHMARK_REFRESH_DRAWS = 30
#: Số kỳ gần nhất của walk-forward in lên trang (mỗi kỳ: 5 con đã chọn và con nào trúng).
RECENT_DRAWS = 10


def wilson(hits: int, n: int, z: float = float(norm.ppf(0.975))) -> tuple[float, float]:
    """Khoảng tin cậy Wilson 95% của một tỉ lệ; dùng được cả khi số trúng nhỏ."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


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


def vip_section(draws: np.ndarray, labels: list[str], cfg: VIPConfig | None = None) -> dict:
    """Dự báo kỳ kế tiếp và kiểm chứng walk-forward của bộ lọc VIP."""
    cfg = cfg or VIPConfig()
    model = VIPMultiHitModel(draws, labels, cfg)
    report = model.predict_next()
    bt = report.backtest
    lo, hi = wilson(bt.hits, bt.picks)
    counts = counts_matrix(model.draws)
    recent = []
    for row in bt.per_draw.tail(RECENT_DRAWS).iloc[::-1].itertuples(index=False):
        t = labels.index(row.ky)
        recent.append({
            "date": row.ky,
            "picks": [{"number": n, "hits": int(counts[t, int(n)])} for n in row.chon],
            "multi": int(row.trung),
        })
    evaluated = bt.per_draw["ky"]
    return {
        "version": MEASURE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_date": labels[-1],
        "draws": int(len(model.draws)),
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
            "expected": bt.expected,
            "random_rate": bt.random_rate,
            "lift": bt.lift,
            "z": bt.z,
            "p_value": bt.p_value,
        },
        "confidence": report.model_level,
        "picks": [
            {"number": p.number, "vip_score": p.vip_score, "probability": p.probability,
             "x_base": p.lift, "confidence": p.confidence, "reasons": p.reasons()}
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


def benchmark_section(draws: np.ndarray, labels: list[str]) -> dict:
    """Giao thức lượt hai trên lịch sử thật, và cùng giao thức trên lịch sử có cài tín hiệu."""
    import multi_hit_benchmark as bm

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


def benchmark_is_stale(cached: dict | None, draws: np.ndarray, labels: list[str]) -> bool:
    """Đo lại khi: chưa có, khác phiên bản, lịch sử bị viết lại, hoặc đã dài thêm đủ kỳ.

    "Viết lại" so dấu vân tay của đúng đoạn lịch sử bản đệm đã đo: sửa một kỳ cũ mà không đổi số
    kỳ hay ngày cuối vẫn bị bắt, còn kỳ mới nối thêm ở cuối thì không làm bản đệm cũ đi.
    """
    if not cached or cached.get("version") != MEASURE_VERSION:
        return True
    measured = int(cached.get("draws", 0))
    if not 0 < measured <= len(draws):
        return True
    if cached.get("history_sha256") != history_fingerprint(draws, labels, measured):
        return True
    return len(draws) - measured >= BENCHMARK_REFRESH_DRAWS


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
