"""Kiểm toán tính khả thi của Lô VIP nhiều nháy: trần xác suất theo kỳ và cấu trúc có khai thác được không.

Ba phần, chỉ đọc ``data/xsmb-2-digits.csv`` (và ``vip.json`` cho số đo của mô hình đang chạy):

* **Trần theo kỳ**: tỉ lệ kỳ có ít nhất một trong k con về ≥ 2 nháy khi quay công bằng
  (``multi_hit_vip.any_multi_chance``, chính xác) và khi chọn bừa trên lịch sử thật, k = 1 … 100;
  cùng tỉ lệ kỳ không con nào về ≥ 2 nháy (bài toán ngày sinh).
* **Cấu trúc**: số con ≥ 2 nháy mỗi kỳ so với lý thuyết (từng năm, sai số theo cụm kỳ); độ tản giữa
  100 con so với nhị thức và tương quan nửa đầu – nửa sau; kỳ sau ≥ 2 nháy theo số nháy kỳ này ở
  độ trễ 1, 2, 3, 7.
* **Mô hình đang chạy**: số kỳ đạt của top-k đã chấm walk-forward (từ ``vip.json``) so với chọn bừa.

    python3 scripts/research/audit_multi_hit_vip.py            # in bảng
    python3 scripts/research/audit_multi_hit_vip.py --json out.json

Kết quả 31-10-2026: ``documentation/research/2026-10-31-kiem-toan-lo-vip-nhieu-nhay.md``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from forecast.multi_hit_report import load_history  # noqa: E402
from forecast.multi_hit_vip import (LOTO_PER_DRAW, N_NUMBERS, any_multi_chance, counts_matrix,  # noqa: E402
                                    random_any_hit)

KS = (1, 3, 5, 10, 20, 50, 100)
LAGS = (1, 2, 3, 7)


def ceiling(multi: np.ndarray) -> list[dict]:
    """Từng k: tỉ lệ kỳ đạt khi quay công bằng và khi chọn bừa k con trên chính lịch sử thật."""
    n_multi = multi.sum(axis=1)
    return [{"k": k, "fair": any_multi_chance(k), "random_on_history": float(random_any_hit(n_multi, k).mean()),
             "expected_hits": k * float(binom.sf(1, LOTO_PER_DRAW, 1 / N_NUMBERS))} for k in KS]


def repeat_level(multi: np.ndarray, labels: list[str]) -> dict:
    """Số con ≥ 2 nháy mỗi kỳ so với lý thuyết 100·P(X ≥ 2); z theo cụm kỳ (mỗi kỳ một quan sát)."""
    theory = N_NUMBERS * float(binom.sf(1, LOTO_PER_DRAW, 1 / N_NUMBERS))
    per_draw = multi.sum(axis=1).astype(float)

    def z(values: np.ndarray) -> float:
        return float((values.mean() - theory) / (values.std(ddof=1) / math.sqrt(len(values))))

    years = np.array([label[:4] for label in labels])
    return {"theory": theory, "observed": float(per_draw.mean()), "z": z(per_draw),
            "none_theory": 1 - any_multi_chance(N_NUMBERS), "none_observed": float((per_draw == 0).mean()),
            "years": {y: {"mean": float(per_draw[years == y].mean()), "z": z(per_draw[years == y]),
                          "draws": int((years == y).sum())} for y in sorted(set(years))}}


def heterogeneity(multi: np.ndarray) -> dict:
    """Con nào "hay về nhiều nháy" hơn con khác không: độ tản / nhị thức và tương quan hai nửa lịch sử."""
    rate = multi.mean(axis=0)
    half = len(multi) // 2
    binomial = rate.mean() * (1 - rate.mean()) / len(multi)
    return {"dispersion_ratio": float(rate.var(ddof=1) / binomial),
            "split_half_corr": float(np.corrcoef(multi[:half].mean(0), multi[half:].mean(0))[0, 1])}


def lag_dependence(counts: np.ndarray) -> list[dict]:
    """Kỳ sau (độ trễ ``lag``) về ≥ 2 nháy, theo số nháy của con ấy ở kỳ này."""
    multi = counts >= 2
    base = multi.mean()
    out = []
    for lag in LAGS:
        now, later = counts[:-lag], multi[lag:]
        for label, mask in (("≥2", now >= 2), ("1", now == 1), ("0", now == 0)):
            seen, hit = int(mask.sum()), int(later[mask].sum())
            rate = hit / seen
            out.append({"lag": lag, "today": label, "seen": seen, "hits": hit, "rate": rate,
                        "z": (rate - base) / math.sqrt(base * (1 - base) / seen)})
    return out


def audit(data_dir: Path) -> dict:
    draws, labels = load_history(data_dir)
    counts = counts_matrix(draws)
    multi = counts >= 2
    vip_path = data_dir / "forecast" / "multi_hit" / "vip.json"
    vip = json.loads(vip_path.read_text(encoding="utf-8")) if vip_path.exists() else None
    model = None
    if vip and "days_hit" in vip.get("backtest", {}):
        bt, pro = vip["backtest"], vip["prospective"]
        model = {key: bt[key] for key in ("draws", "days_hit", "day_rate", "day_random_rate", "day_z", "day_fair")}
        model["prospective"] = {key: pro[key] for key in ("after", "draws", "days_hit", "days_expected")}
    return {"draws": len(labels), "first": labels[0], "last": labels[-1], "ceiling": ceiling(multi),
            "repeat_level": repeat_level(multi, labels), "heterogeneity": heterogeneity(multi),
            "lags": lag_dependence(counts), "model": model}


def _print(result: dict) -> None:
    print(f"{result['draws']} kỳ, {result['first']} → {result['last']}")
    print("Trần theo kỳ (≥ 1 trong k con về ≥ 2 nháy):")
    for row in result["ceiling"]:
        print(f"  k = {row['k']:3d}: quay công bằng {row['fair']:.2%} · chọn bừa trên lịch sử thật "
              f"{row['random_on_history']:.2%} · số con trúng TB {row['expected_hits']:.3f}")
    rl = result["repeat_level"]
    print(f"Số con ≥ 2 nháy mỗi kỳ: {rl['observed']:.3f} so với lý thuyết {rl['theory']:.3f} (z = {rl['z']:+.2f}); "
          f"kỳ không con nào: {rl['none_observed']:.2%} so với {rl['none_theory']:.2%}")
    for year, row in rl["years"].items():
        print(f"  {year}: {row['mean']:.3f} (z = {row['z']:+.2f}, {row['draws']} kỳ)")
    h = result["heterogeneity"]
    print(f"Độ tản giữa 100 con / nhị thức = {h['dispersion_ratio']:.2f}; tương quan hai nửa = {h['split_half_corr']:+.2f}")
    for row in result["lags"]:
        print(f"  trễ {row['lag']}, kỳ này {row['today']} nháy: {row['rate']:.3%} ({row['hits']}/{row['seen']}), "
              f"z = {row['z']:+.2f}")
    if result["model"]:
        m, pro = result["model"], result["model"]["prospective"]
        print(f"Mô hình đang chạy: kỳ đạt {m['days_hit']}/{m['draws']} ({m['day_rate']:.2%}) · chọn bừa "
              f"{m['day_random_rate']:.2%} · z = {m['day_z']:+.2f}; sau {pro['after']}: {pro['days_hit']}/"
              f"{pro['draws']} kỳ, chọn bừa {pro['days_expected']:.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--json", type=Path, default=None, help="ghi kết quả ra tệp JSON")
    args = parser.parse_args(argv)
    result = audit(args.data_dir)
    _print(result)
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
