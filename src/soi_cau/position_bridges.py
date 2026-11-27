from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

LAYOUT = [
    ("special", 1, 5), ("prize1", 1, 5), ("prize2", 2, 5), ("prize3", 6, 5),
    ("prize4", 4, 4), ("prize5", 6, 4), ("prize6", 3, 3), ("prize7", 4, 2),
]
PRIZE_LABEL = {"special": "ĐB", "prize1": "G1", "prize2": "G2", "prize3": "G3",
               "prize4": "G4", "prize5": "G5", "prize6": "G6", "prize7": "G7"}
COLUMNS = [p if n == 1 else f"{p}_{i + 1}" for p, n, _ in LAYOUT for i in range(n)]
WIDTHS = [w for _, n, w in LAYOUT for _ in range(n)]
N_POS = sum(WIDTHS)

SHADOW = (5, 6, 7, 8, 9, 0, 1, 2, 3, 4)

MODES = {
    "lo": {"title": "Cầu Lotto", "nhay": 1, "db": False, "lon": True, "limit": 5},
    "nhay2": {"title": "Cầu 2 nháy", "nhay": 2, "db": False, "lon": True, "limit": 3},
    "db": {"title": "Cầu Đặc Biệt", "nhay": 1, "db": True, "lon": True, "limit": 1},
}
BEST_COUNT = 10
WINDOW = 60
MAX_STREAK = 10
CONSENSUS_BUCKETS = ((1, 1), (2, 2), (3, 3), (4, 5), (6, 9), (10, None))
OUT = Path("soi_cau") / "position_bridges"


def positions() -> list[dict]:
    out = []
    for prize, count, width in LAYOUT:
        for i in range(count):
            column = prize if count == 1 else f"{prize}_{i + 1}"
            label = PRIZE_LABEL[prize] + (f".{i + 1}" if count > 1 else "")
            for d in range(width):
                out.append({"index": len(out), "value_index": COLUMNS.index(column),
                            "digit": d, "label": f"{label} · chữ số {d + 1}"})
    return out


def load_draws(raw: pd.DataFrame) -> tuple[list[str], np.ndarray, np.ndarray]:
    raw = raw.sort_values("date", kind="stable").reset_index(drop=True)
    values = raw[COLUMNS].to_numpy().astype(np.int64)
    digits = np.zeros((len(raw), N_POS), dtype=np.int8)
    col = 0
    for j, width in enumerate(WIDTHS):
        for d in range(width):
            digits[:, col] = (values[:, j] // 10 ** (width - 1 - d)) % 10
            col += 1
    return [str(x)[:10] for x in raw["date"]], digits, values


def pair_index(lon: bool) -> tuple[np.ndarray, np.ndarray]:
    a, b = np.meshgrid(np.arange(N_POS), np.arange(N_POS), indexing="ij")
    mask = a < b if lon else a != b
    return a[mask], b[mask]


def bridge_numbers(digits: np.ndarray, pa: np.ndarray, pb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = digits[:, pa].astype(np.int16)
    y = digits[:, pb].astype(np.int16)
    return 10 * x + y, 10 * y + x


def hit_matrix(digits: np.ndarray, values: np.ndarray, *, nhay: int, db: bool,
               lon: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pa, pb = pair_index(lon)
    n1, n2 = bridge_numbers(digits[:-1], pa, pb)
    two = values[1:] % 100
    if db:
        special = two[:, :1]
        hit = special == n1
        if lon:
            hit |= special == n2
        return hit, pa, pb
    counts = np.zeros((len(two), 100), dtype=np.int16)
    np.add.at(counts, (np.arange(len(two))[:, None], two), 1)
    rows = np.arange(len(two))[:, None]
    total = counts[rows, n1]
    if lon:
        total = total + np.where(n1 != n2, counts[rows, n2], 0)
    return total >= nhay, pa, pb


def run_lengths(hits: np.ndarray) -> np.ndarray:
    runs = np.zeros(hits.shape, dtype=np.int16)
    current = np.zeros(hits.shape[1], dtype=np.int16)
    for t in range(hits.shape[0]):
        current = np.where(hits[t], current + 1, 0).astype(np.int16)
        runs[t] = current
    return runs


def predicted(digits_row: np.ndarray, a: int, b: int, lon: bool) -> list[str]:
    x, y = int(digits_row[a]), int(digits_row[b])
    nums = [10 * x + y] if not lon or x == y else [10 * x + y, 10 * y + x]
    return [f"{n:02d}" for n in nums]


def shadow(numbers: list[str]) -> str | None:
    if len(numbers) != 1 or numbers[0][0] != numbers[0][1]:
        return None
    d = SHADOW[int(numbers[0][0])]
    return f"{d}{d}"


def pair_key(nums: list[str]) -> str:
    return ",".join(sorted(nums))


def find_bridges(digits: np.ndarray, values: np.ndarray, *, nhay: int, db: bool, lon: bool,
                 limit: int, exact: bool = False) -> list[dict]:
    tail = min(len(digits), WINDOW)
    hits, pa, pb = hit_matrix(digits[-tail:], values[-tail:], nhay=nhay, db=db, lon=lon)
    streak = run_lengths(hits)[-1]
    keep = streak == limit if exact else streak >= limit
    out = []
    for p in np.flatnonzero(keep):
        a, b = int(pa[p]), int(pb[p])
        numbers = predicted(digits[-1], a, b, lon)
        out.append({"vt": f"{a}x{b}", "a": a, "b": b, "streak": int(streak[p]),
                    "numbers": numbers, "shadow": shadow(numbers)})
    out.sort(key=lambda r: (r["numbers"][0], r["a"], r["b"]))
    return out


def summarize(bridges: list[dict], limit: int) -> dict:
    by_pair: dict[str, list[dict]] = {}
    for bridge in bridges:
        by_pair.setdefault(pair_key(bridge["numbers"]), []).append(bridge)
    repeats = sorted(by_pair.items(), key=lambda kv: -len(kv[1]))
    return {
        "count": len(bridges),
        "longer": sum(b["streak"] > limit for b in bridges),
        "pairs": len(by_pair),
        "pairs_longer": sum(any(b["streak"] > limit for b in v) for v in by_pair.values()),
        "repeats": [{"pair": k, "bridges": len(v)} for k, v in repeats],
    }


def best(bridges: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for bridge in bridges:
        key = pair_key(bridge["numbers"])
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(bridges, key=lambda b: (-b["streak"], -counts[pair_key(b["numbers"])], b["a"], b["b"]))
    chosen, seen = [], set()
    for bridge in ranked:
        key = pair_key(bridge["numbers"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append({**bridge, "same_pair": counts[key]})
        if len(chosen) == BEST_COUNT:
            break
    return chosen


def history(digits: np.ndarray, values: np.ndarray, *, nhay: int, db: bool, lon: bool) -> tuple:
    hits, pa, pb = hit_matrix(digits, values, nhay=nhay, db=db, lon=lon)
    runs = run_lengths(hits)
    n1, n2 = bridge_numbers(digits[1:-1], pa, pb)
    kep = n1 == n2
    key = np.minimum(n1, n2) * 100 + np.maximum(n1, n2) if lon else n1.astype(np.int32)
    return runs[:-1], hits[1:], kep, key


def _type_rates(nxt: np.ndarray, kep: np.ndarray) -> tuple[float, float]:
    n_kep = int(kep.sum())
    rate_kep = float(nxt[kep].sum() / n_kep) if n_kep else 0.0
    n_pair = int((~kep).sum())
    rate_pair = float(nxt[~kep].sum() / n_pair) if n_pair else 0.0
    return rate_kep, rate_pair


def _row(label: dict, n: int, hits: int, expected: float, dev: np.ndarray, days: int) -> dict:
    scale = float(np.sqrt((dev ** 2).sum()))
    return {**label, "n": n, "hits": hits,
            "rate": hits / n if n else None,
            "expected": expected / n if n else None,
            "z": float(dev.sum() / scale) if scale > 0 else 0.0,
            "days": days}


def streak_backtest(history: tuple, max_streak: int = MAX_STREAK) -> dict:
    prev, nxt, kep, _ = history
    rate_kep, rate_pair = _type_rates(nxt, kep)
    days, width = prev.shape[0], max_streak + 1
    cell = (np.arange(days, dtype=np.int64)[:, None] * width
            + np.minimum(prev, max_streak).astype(np.int64)).ravel()
    size = days * width
    n = np.bincount(cell, minlength=size).reshape(days, width)
    got = np.bincount(cell, weights=nxt.ravel(), minlength=size).reshape(days, width)
    n_kep = np.bincount(cell, weights=kep.ravel(), minlength=size).reshape(days, width)
    exp = n_kep * rate_kep + (n - n_kep) * rate_pair
    rows = []
    for k in range(width):
        rows.append(_row({"k": k, "plus": k == max_streak}, int(n[:, k].sum()), int(round(got[:, k].sum())),
                         float(exp[:, k].sum()), got[:, k] - exp[:, k], int((n[:, k] > 0).sum())))
    return {"base_rate": float(nxt.mean()), "rate_kep": rate_kep, "rate_pair": rate_pair,
            "draws": int(nxt.shape[0]), "rows": rows}


def consensus_backtest(history: tuple, limit: int) -> dict:
    prev, nxt, kep, key = history
    rate_kep, rate_pair = _type_rates(nxt, kep)
    size = int(key.max()) + 1
    buckets = [{"n": 0, "hits": 0, "expected": 0.0, "dev": [], "days": 0} for _ in CONSENSUS_BUCKETS]
    for s in range(prev.shape[0]):
        on = prev[s] >= limit
        if not on.any():
            continue
        keys = key[s][on]
        count = np.bincount(keys, minlength=size)
        outcome = np.zeros(size, dtype=bool)
        outcome[keys] = nxt[s][on]
        is_kep = np.zeros(size, dtype=bool)
        is_kep[keys] = kep[s][on]
        present = np.flatnonzero(count)
        for bucket, (lo, hi) in zip(buckets, CONSENSUS_BUCKETS, strict=True):
            inside = count[present] >= lo
            if hi is not None:
                inside &= count[present] <= hi
            sel = present[inside]
            if not len(sel):
                continue
            exp = float(np.where(is_kep[sel], rate_kep, rate_pair).sum())
            got = int(outcome[sel].sum())
            bucket["n"] += len(sel)
            bucket["hits"] += got
            bucket["expected"] += exp
            bucket["dev"].append(got - exp)
            bucket["days"] += 1
    rows = [_row({"from": lo, "to": hi}, b["n"], b["hits"], b["expected"],
                 np.array(b["dev"], dtype=float), b["days"])
            for b, (lo, hi) in zip(buckets, CONSENSUS_BUCKETS, strict=True)]
    return {"limit": limit, "rows": rows}


def build(data_dir: Path) -> dict:
    raw = pd.read_csv(data_dir / "xsmb.csv", dtype={"date": str})
    dates, digits, values = load_draws(raw)
    last = dates[-1]
    target = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
    report = {"source_date": last, "target_date": target, "window": WINDOW,
              "draws": [{"date": d, "values": [str(int(v)).zfill(w) for v, w in zip(row, WIDTHS, strict=True)]}
                        for d, row in zip(dates[-WINDOW:], values[-WINDOW:], strict=True)],
              "modes": {}}
    for key, cfg in MODES.items():
        params = {"nhay": cfg["nhay"], "db": cfg["db"], "lon": cfg["lon"]}
        bridges = find_bridges(digits, values, limit=cfg["limit"], **params)
        past = history(digits, values, **params)
        report["modes"][key] = {
            **cfg,
            "summary": summarize(bridges, cfg["limit"]),
            "best": best(bridges),
            "streaks": streak_backtest(past),
            "consensus": consensus_backtest(past, cfg["limit"]),
        }
        del past
    return report


def run(data_dir: Path) -> Path:
    path = data_dir / OUT / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(data_dir), ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    print("Wrote:", run(args.data_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
