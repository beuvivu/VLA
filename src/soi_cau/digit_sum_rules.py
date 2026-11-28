from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from math import comb, sqrt
from pathlib import Path
from collections.abc import Callable

import numpy as np
import pandas as pd

from core.xsmb_domain import FIELD_WIDTHS
from stats.statistical_corrections import holm

_WIDTH = dict(FIELD_WIDTHS)


def bong(digit: int) -> int:
    return (int(digit) + 5) % 10


def tong(text: str) -> int:
    return sum(int(c) for c in text) % 10


def giai(row: pd.Series, field: str) -> str:
    return f"{int(row[field]):0{_WIDTH[field]}d}"


def cap_lon(x: int, y: int) -> list[int]:
    return sorted({10 * x + y, 10 * y + x})


@dataclass(frozen=True)
class Rule:

    key: str
    label: str
    target: str
    make: Callable[[pd.Series], list[int]]
    formula: str


def dau_db(row: pd.Series) -> list[int]:
    t = tong(giai(row, "special")[-2:])
    return sorted({t, bong(t)})


def duoi_db(row: pd.Series) -> list[int]:
    t = tong(giai(row, "special")[:2])
    return sorted({t, bong(t)})


def cham(row: pd.Series) -> list[int]:
    t = tong(giai(row, "prize1")[-2:])
    return sorted({t, bong(t)})


def dan_cham(row: pd.Series) -> list[int]:
    digits = {int(c) for c in giai(row, "special")[:3]}
    digits |= {bong(d) for d in digits}
    out: set[int] = set()
    for c in cham(row):
        for d in digits:
            out.update(cap_lon(c, d))
    return sorted(out)


def lo_g5(row: pd.Series) -> list[int]:
    return cap_lon(tong(giai(row, "prize5_2")[:2]), tong(giai(row, "prize5_4")[-2:]))


def lo_vip(row: pd.Series) -> list[int]:
    return cap_lon(tong(giai(row, "prize2_1")[-2:]), tong(giai(row, "prize1")[:2]))


RULES: tuple[Rule, ...] = (
    Rule("dau_db", "Đầu Đặc Biệt", "dau_db", dau_db,
         "tổng 2 số cuối Đặc Biệt và bóng"),
    Rule("duoi_db", "Đuôi Đặc Biệt", "duoi_db", duoi_db,
         "tổng 2 số đầu Đặc Biệt và bóng"),
    Rule("dan_cham", "Dàn đề chạm", "db", dan_cham,
         "chạm = tổng 2 số cuối giải nhất và bóng; ghép thẳng/lộn với 3 số đầu Đặc Biệt và bóng"),
    Rule("lo_g5", "Lô cặp G5", "loto", lo_g5,
         "tổng 2 số đầu G5.2 ghép tổng 2 số cuối G5.4, lấy lộn"),
    Rule("lo_vip", "Song thủ lô G2–G1", "loto", lo_vip,
         "tổng 2 số cuối G2.1 ghép tổng 2 số đầu giải nhất, lấy lộn"),
)


def tong_hop_ky(row: pd.Series) -> dict:
    special = giai(row, "special")[-2:]
    lotos = [int(row[field]) % 100 for field, _ in FIELD_WIDTHS]
    counts = np.bincount(lotos, minlength=100)
    present = {n for n in range(100) if counts[n]}
    heads = np.bincount([n // 10 for n in lotos], minlength=10)
    tails = np.bincount([n % 10 for n in lotos], minlength=10)
    return {
        "de": special,
        "de_dau": int(special[0]),
        "de_duoi": int(special[1]),
        "de_tong": tong(special),
        "lo_kep": sorted(n for n in present if n // 10 == n % 10),
        "lo_nhay": {f"{n:02d}": int(counts[n]) for n in range(100) if counts[n] >= 2},
        "lo_ca_cap": sorted(n for n in present if n // 10 < n % 10 and (n % 10) * 10 + n // 10 in present),
        "cam_dau": [d for d in range(10) if heads[d] == 0],
        "cam_duoi": [d for d in range(10) if tails[d] == 0],
        "dau_nhieu_nhat": [d for d in range(10) if heads[d] == heads.max()],
        "duoi_nhieu_nhat": [d for d in range(10) if tails[d] == tails.max()],
    }


def hit_and_chance(rule: Rule, picks: list[int], nxt: pd.Series) -> tuple[bool, float]:
    k = len(picks)
    special = int(nxt["special"]) % 100
    if rule.target == "dau_db":
        return special // 10 in picks, k / 10
    if rule.target == "duoi_db":
        return special % 10 in picks, k / 10
    if rule.target == "db":
        return special in picks, k / 100
    lotos = {int(nxt[field]) % 100 for field, _ in FIELD_WIDTHS}
    return bool(lotos & set(picks)), 1.0 - comb(100 - len(lotos), k) / comb(100, k)


def poisson_binomial_sf(hits: int, chances: list[float]) -> float:
    dist = np.zeros(len(chances) + 1)
    dist[0] = 1.0
    for i, p in enumerate(chances):
        step = dist[: i + 2] * (1.0 - p)
        step[1:] += dist[: i + 1] * p
        dist[: i + 2] = step
    return float(min(1.0, dist[hits:].sum()))


def wilson(hits: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    rate = hits / n
    den = 1 + z * z / n
    centre = (rate + z * z / (2 * n)) / den
    half = z * sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def verdict(n: int, hits: int, chances: list[float]) -> dict:
    expected = float(sum(chances))
    variance = float(sum(p * (1.0 - p) for p in chances))
    low, high = wilson(hits, n)
    return {
        "hits": hits,
        "hit_rate": hits / n if n else 0.0,
        "ci_low": low,
        "ci_high": high,
        "expected_rate": expected / n if n else 0.0,
        "z": (hits - expected) / sqrt(variance) if variance > 0 else 0.0,
        "p_value": poisson_binomial_sf(hits, chances) if n else 1.0,
    }


def with_holm(rows: list[dict]) -> list[dict]:
    for row, adjusted in zip(rows, holm([row["p_value"] for row in rows]), strict=True):
        row["p_holm"] = adjusted
    return rows


def backtest(raw: pd.DataFrame) -> list[dict]:
    raw = raw.sort_values("date", kind="stable").reset_index(drop=True)
    rows = [raw.iloc[i] for i in range(len(raw))]
    out = []
    for rule in RULES:
        hits = 0
        chances = []
        for t in range(len(rows) - 1):
            hit, p = hit_and_chance(rule, rule.make(rows[t]), rows[t + 1])
            hits += int(hit)
            chances.append(p)
        out.append({
            "rule": rule.key,
            "label": rule.label,
            "formula": rule.formula,
            "draws": len(chances),
            **verdict(len(chances), hits, chances),
        })
    return with_holm(out)


FRAMES: dict[str, dict[int, tuple[int, ...]]] = {
    "dau_db": {6: (0, 1, 2, 3, 4, 5, 6)},
    "duoi_db": {6: (0, 1, 2, 3, 4, 5, 6)},
    "dan_cham": {6: (0, 1, 2, 3), 3: (4, 5, 6)},
    "lo_g5": {6: (0, 1), 3: (4, 5, 6)},
    "lo_vip": {6: (0,), 3: (4,)},
}


def frame_backtest(raw: pd.DataFrame) -> list[dict]:
    raw = raw.sort_values("date", kind="stable").reset_index(drop=True)
    dates = pd.to_datetime(raw["date"])
    rows = [raw.iloc[i] for i in range(len(raw))]
    by_key = {rule.key: rule for rule in RULES}
    out = []
    for key, frames in FRAMES.items():
        rule = by_key[key]
        hits = 0
        chances = []
        for t in range(len(rows) - 1):
            days = frames.get(int(dates[t].weekday()))
            if days is None:
                continue
            picks = rule.make(rows[t])
            miss_all, hit_any, span = 1.0, False, 0
            for u in range(t + 1, min(t + 8, len(rows))):
                gap = (dates[u] - dates[t]).days
                if gap > 7 or int(dates[u].weekday()) not in days:
                    continue
                span += 1
                hit, p = hit_and_chance(rule, picks, rows[u])
                hit_any |= hit
                miss_all *= 1.0 - p
            if span == 0:
                continue
            hits += int(hit_any)
            chances.append(1.0 - miss_all)
        out.append({
            "rule": key,
            "label": rule.label,
            "frames": len(chances),
            **verdict(len(chances), hits, chances),
        })
    return with_holm(out)


def next_picks(raw: pd.DataFrame) -> dict:
    last = raw.sort_values("date", kind="stable").iloc[-1]
    return {
        "base_date": str(last["date"])[:10],
        "tong_hop": tong_hop_ky(last),
        "picks": {rule.key: rule.make(last) for rule in RULES},
        "cham": cham(last),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/xsmb.csv")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    raw = pd.read_csv(args.data)
    report = {"backtest": backtest(raw), "frames": frame_backtest(raw), "next": next_picks(raw)}
    text = json.dumps(report, ensure_ascii=False, indent=2, default=int)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
