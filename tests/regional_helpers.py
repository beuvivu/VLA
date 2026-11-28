from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from core.regional_domain import PRIZE_SPECS

FIELDS = ("date", "region", "province", "prize", "position", "value", "source", "fetched_at")
FIRST_DAY = date(2025, 10, 6)


def biased_law(short: dict[int, int] | None = None, share: float = 0.03) -> np.ndarray:
    law = np.full((6, 10), 0.1)
    for cage, digit in (short or {}).items():
        law[cage] = (1.0 - share) / 9.0
        law[cage, digit] = share
    return law


def station_rows(
    region: str,
    province: str,
    draws: int,
    rng: np.random.Generator,
    *,
    weekday: int = 0,
    law: np.ndarray | None = None,
    first_day: date = FIRST_DAY,
    start_week: int = 0,
) -> list[dict[str, str]]:
    table = np.full((6, 10), 0.1) if law is None else law
    rows = []
    for week in range(start_week, start_week + draws):
        day = (first_day + timedelta(days=7 * week + weekday)).isoformat()
        for prize, count, width in PRIZE_SPECS:
            for position in range(1, count + 1):
                value = "".join(str(rng.choice(10, p=table[width - 1 - i])) for i in range(width))
                rows.append({"date": day, "region": region, "province": province, "prize": prize,
                             "position": str(position), "value": value, "source": "noi-ghi",
                             "fetched_at": "2026-01-01T00:00:00+07:00"})
    return rows


def write_region(root: Path, region: str, rows: list[dict[str, str]]) -> Path:
    path = root / "data" / "regions" / f"xs{region}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def fair_region(region: str, stations: int, draws: int, seed: int) -> list[dict[str, str]]:
    rng = np.random.default_rng(seed)
    rows = []
    for index in range(stations):
        rows.extend(station_rows(region, f"Đài {index + 1}", draws, rng, weekday=index % 7))
    return rows
