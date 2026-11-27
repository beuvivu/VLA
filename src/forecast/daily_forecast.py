from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ensemble.ensemble_components import probability_component
from forecast.multi_hit_forecast import next_draw_date
from ensemble.pick_diversity import diversified_order


def load_daily_forecast(data_dir: Path, anchor_date: str) -> dict | None:
    try:
        if date.fromisoformat(anchor_date).isoformat() != anchor_date:
            return None
        data_dir = Path(data_dir)
        calendar_path = data_dir / "non_draw_days.json"
        closed = []
        if calendar_path.exists():
            calendar = json.loads(calendar_path.read_text(encoding="utf-8"))
            if not isinstance(calendar, dict):
                return None
            closed = calendar.get("ngay_khong_quay", [])
            if not isinstance(closed, list) or any(
                not isinstance(day, str) or date.fromisoformat(day).isoformat() != day
                for day in closed
            ):
                return None
        target_date = next_draw_date(anchor_date, frozenset(closed))
        pred_dir = data_dir / "forecast" / "predict"
        groups = {}
        for mode in ("de", "loto"):
            metadata = json.loads((pred_dir / f"picks_{mode}.json").read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or (
                metadata.get("anchor_date") != anchor_date
                or metadata.get("target_date") != target_date
            ):
                return None
            frame = pd.read_csv(pred_dir / f"predict_next_{mode}_all_{target_date}.csv")
            checked = probability_component(
                frame, mode=mode, expected_target_date=target_date,
                expected_anchor_date=anchor_date,
            )
            if not checked.available:
                return None
            numbers = pd.to_numeric(frame["number"]).to_numpy(dtype=int)
            probabilities = pd.to_numeric(frame["prob"]).to_numpy(dtype=float)[np.argsort(numbers, kind="stable")]
            if mode == "de" and not np.isclose(probabilities.sum(), 1.0, rtol=0, atol=1e-8):
                return None
            order = (
                diversified_order(probabilities, 5) if mode == "loto"
                else np.lexsort((np.arange(100), -probabilities))[:5]
            )
            groups[mode] = [
                {"number": f"{number:02d}", "prob": float(probabilities[number])}
                for number in order
            ]
        return {"anchor_date": anchor_date, "target_date": target_date, "groups": groups}
    except (OSError, ValueError, TypeError):
        return None
