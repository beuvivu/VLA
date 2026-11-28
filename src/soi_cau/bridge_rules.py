from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from soi_cau.position_bridges import (
    SHADOW, WIDTHS, WINDOW, bridge_numbers, load_draws, pair_index, run_lengths, streak_backtest,
)

RULES = {
    "loto": {"slug": "soi-cau-loto", "title": "Cầu LOTO", "kind": "loto", "count": 3,
             "weekday": False, "nav": "Cầu LOTO vị trí"},
    "hai-nhay": {"slug": "soi-cau-hai-nhay", "title": "Cầu LOTO hai nháy", "kind": "hai-nhay",
                 "count": 2, "weekday": False, "nav": "Cầu hai nháy"},
    "bach-thu": {"slug": "soi-cau-bach-thu", "title": "Cầu LOTO bạch thủ", "kind": "bach-thu",
                 "count": 3, "weekday": False, "nav": "Cầu bạch thủ"},
    "dac-biet": {"slug": "soi-cau-dac-biet", "title": "Cầu giải Đặc Biệt", "kind": "dac-biet",
                 "count": 2, "weekday": False, "nav": "Cầu Đặc Biệt vị trí"},
    "bo-so": {"slug": "soi-cau-dac-biet-bo-so", "title": "Cầu Đặc Biệt theo bộ số", "kind": "bo-so",
              "count": 2, "weekday": False, "nav": "Cầu bộ số Đặc Biệt"},
    "dac-biet-theo-thu": {"slug": "soi-cau-dac-biet-theo-thu", "title": "Cầu Đặc Biệt theo thứ",
                          "kind": "dac-biet", "count": 3, "weekday": True, "nav": "Cầu Đặc Biệt theo thứ"},
    "loto-theo-thu": {"slug": "soi-cau-loto-theo-thu", "title": "Cầu LOTO theo thứ", "kind": "loto",
                      "count": 3, "weekday": True, "nav": "Cầu LOTO theo thứ"},
}
EMBED = 14 * WINDOW
OUT = Path("soi_cau") / "bridge_pages"


def _bo_tables() -> tuple[np.ndarray, np.ndarray]:
    members = np.zeros((100, 100), dtype=bool)
    for n in range(100):
        x, y = divmod(n, 10)
        for p in (x, SHADOW[x]):
            for q in (y, SHADOW[y]):
                members[n, 10 * p + q] = members[n, 10 * q + p] = True
    bo_id = np.array([int(np.flatnonzero(members[n])[0]) for n in range(100)])
    return bo_id, members


BO_ID, BO_MEMBERS = _bo_tables()


def bo_members(n: int) -> list[str]:
    return [f"{m:02d}" for m in np.flatnonzero(BO_MEMBERS[n])]


def _loto_counts(values: np.ndarray) -> np.ndarray:
    two = values % 100
    counts = np.zeros((len(values), 100), dtype=np.int16)
    np.add.at(counts, (np.arange(len(values))[:, None], two), 1)
    return counts


def step_matrix(kind: str, digits: np.ndarray, values: np.ndarray, *, both: bool = False) -> np.ndarray:
    pa, pb = pair_index(True)
    n1, n2 = bridge_numbers(digits, pa, pb)
    if kind == "bo-so":
        return BO_ID[n1[:-1]] == BO_ID[n1[1:]]
    src1, src2 = n1[:-1], n2[:-1]
    if kind == "dac-biet":
        special = values[1:, :1] % 100
        tens, units = special // 10, special % 10
        x, y = src1 // 10, src1 % 10
        if both:
            return ((x == tens) & (y == units)) | ((x == units) & (y == tens))
        return (x == tens) | (x == units) | (y == tens) | (y == units)
    counts = _loto_counts(values[1:])
    rows = np.arange(len(counts))[:, None]
    c1 = counts[rows, src1]
    c2 = np.where(src1 != src2, counts[rows, src2], 0)
    if kind == "loto":
        return (c1 + c2) >= 1
    if kind == "hai-nhay":
        return (c1 >= 2) | ((c1 >= 1) & (c2 >= 1))
    if kind == "bach-thu":
        return c1 >= 1
    raise ValueError(f"Kiểu cầu lạ: {kind}")


def outcome_matrix(kind: str, digits: np.ndarray, values: np.ndarray, *, both: bool = False) -> np.ndarray:
    if kind != "bo-so":
        return step_matrix(kind, digits, values, both=both)
    pa, pb = pair_index(True)
    n1, _ = bridge_numbers(digits[:-1], pa, pb)
    special = (values[1:, 0] % 100)[:, None]
    return BO_MEMBERS[n1, special]


def weekday_subset(dates: list[str], digits: np.ndarray, values: np.ndarray,
                   weekday: int | None) -> tuple[list[str], np.ndarray, np.ndarray]:
    if weekday is None:
        return dates, digits, values
    keep = np.array([date.fromisoformat(d).weekday() == weekday for d in dates])
    return [d for d, k in zip(dates, keep, strict=True) if k], digits[keep], values[keep]


def find(kind: str, digits: np.ndarray, values: np.ndarray, *, count: int, both: bool = False) -> dict:
    tail = min(len(digits), WINDOW)
    digits, values = digits[-tail:], values[-tail:]
    streak = run_lengths(step_matrix(kind, digits, values, both=both))[-1]
    pa, pb = pair_index(True)
    n1 = 10 * digits[-1, pa].astype(int) + digits[-1, pb]
    bridges = [{"vt": f"{int(pa[p])}x{int(pb[p])}", "a": int(pa[p]), "b": int(pb[p]),
                "streak": int(streak[p]), "number": f"{int(n1[p]):02d}"}
               for p in np.flatnonzero(streak >= count)]
    bridges.sort(key=lambda r: (r["number"], r["a"], r["b"]))
    return {"bridges": bridges, "longest": int(streak.max()) if len(streak) else 0}


def tally(bridges: list[dict], kind: str) -> dict:
    counts: dict[str, int] = {}
    for bridge in bridges:
        counts[bridge["number"]] = counts.get(bridge["number"], 0) + 1
    groups: dict[str, int] = {}
    for number, n in counts.items():
        value = int(number)
        if kind == "bo-so":
            key = ",".join(bo_members(int(BO_ID[value])))
        else:
            rev = f"{number[1]}{number[0]}"
            key = ",".join(sorted({number, rev}))
        groups[key] = groups.get(key, 0) + n
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"counts": dict(sorted(counts.items())), "total": len(bridges),
            "groups": [{"key": k, "bridges": n} for k, n in ranked]}


def backtest(kind: str, series: list[tuple[np.ndarray, np.ndarray]], *, both: bool = False) -> dict:
    prevs, nexts, flags = [], [], []
    pa, pb = pair_index(True)
    for digits, values in series:
        if len(digits) < 3:
            continue
        runs = run_lengths(step_matrix(kind, digits, values, both=both))
        outcome = outcome_matrix(kind, digits, values, both=both)
        x = digits[1:-1, pa]
        y = digits[1:-1, pb]
        flag = (x == y) if kind != "bo-so" else (x == y) | (x == np.array(SHADOW)[y])
        prevs.append(runs[:-1])
        nexts.append(outcome[1:])
        flags.append(flag)
    history = (np.concatenate(prevs), np.concatenate(nexts), np.concatenate(flags), None)
    return streak_backtest(history)


def build(data_dir: Path) -> dict:
    raw = pd.read_csv(data_dir / "xsmb.csv", dtype={"date": str})
    dates, digits, values = load_draws(raw)
    last = dates[-1]
    target = date.fromisoformat(last) + timedelta(days=1)
    report = {"source_date": last, "target_date": target.isoformat(), "window": WINDOW,
              "draws": ["".join([d, *(str(int(v)).zfill(w) for v, w in zip(row, WIDTHS, strict=True))])
                        for d, row in zip(dates[-EMBED:], values[-EMBED:], strict=True)],
              "rules": {}}
    for key, cfg in RULES.items():
        weekday = target.weekday() if cfg["weekday"] else None
        d, dg, vl = weekday_subset(dates, digits, values, weekday)
        found = find(cfg["kind"], dg, vl, count=cfg["count"])
        series = ([weekday_subset(dates, digits, values, w)[1:] for w in range(7)]
                  if cfg["weekday"] else [(digits, values)])
        report["rules"][key] = {**cfg, "default_weekday": weekday, "longest": found["longest"],
                                **tally(found["bridges"], cfg["kind"]),
                                "backtest": backtest(cfg["kind"], series)}
        if cfg["kind"] == "dac-biet":
            report["rules"][key]["backtest_both"] = backtest(cfg["kind"], series, both=True)
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
