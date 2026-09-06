"""Gói dự đoán và schema JSON đầu ra.

Bổ sung cho ``picks_loto.json`` / ``picks_de.json`` chứ không thay thế — các
trang trong ``docs/`` đang đọc hai tệp đó.

Mọi con số đưa ra đều mang theo bối cảnh của nó: xác suất đi kèm đường cơ sở,
danh sách cầu đi kèm số giả thuyết đã thử. Một xác suất 0,26 không có đường cơ
sở 0,2377 bên cạnh sẽ được đọc là "cao", và đó là cách trình bày sai lệch nhất
có thể ở miền này.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from number_reference import normalize_two_digit
from time_policy import iso_local

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class NumberPick:
    """Một con số kèm xác suất và lý do đóng góp."""

    number: str
    probability: float
    baseline: float
    lift: float
    contribution_reasons: dict[str, float]
    gan_days: int
    gan_flagged: bool


@dataclass(frozen=True)
class PredictionBundle:
    """Đầu ra hằng ngày, ghi ra ``data/predictions_today.json``."""

    date: str
    generated_at_local: str
    generated_at_utc: str
    top_lo_to: list[NumberPick]
    top_dac_biet: dict[str, Any]
    active_bridges: list[dict[str, Any]]
    disclaimer: str
    schema_version: str = SCHEMA_VERSION
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["top_lo_to"] = [asdict(pick) for pick in self.top_lo_to]
        return payload

    def to_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def build_picks(
    probabilities: np.ndarray,
    *,
    baseline: float,
    gaps: np.ndarray,
    gan_threshold: int,
    reasons: dict[int, dict[str, float]],
    top_k: int = 10,
) -> list[NumberPick]:
    """Lấy ``top_k`` con có xác suất cao nhất, kèm bối cảnh đầy đủ."""
    order = np.lexsort((np.arange(len(probabilities)), -probabilities))[:top_k]
    return [
        NumberPick(
            number=normalize_two_digit(int(n)),
            probability=float(probabilities[n]),
            baseline=float(baseline),
            lift=float(probabilities[n] - baseline),
            contribution_reasons={k: round(v, 4) for k, v in reasons.get(int(n), {}).items()},
            gan_days=int(gaps[n]),
            gan_flagged=bool(gaps[n] > gan_threshold),
        )
        for n in order
    ]


def utc_stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_stamp() -> str:
    """Dấu thời gian theo giờ Việt Nam, dùng lại chính sách múi giờ của kho."""
    return iso_local()
