"""Kiểm hồi cứu theo tiền tố; không ghi vào bất kỳ sổ tiến cứu nào."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import online_learning as online
from time_policy import VIETNAM_TZ
from xsmb_domain import baseline_rate

from .algorithms import AlgorithmEnsemble
from .knowledge import KnowledgeBaseManager


def walk_forward(frame: pd.DataFrame, *, last: int = 60,
                 prediction_dir: Path | None = None) -> dict:
    """Dựng từng kỳ từ đúng tiền tố, học loss kỳ trước rồi chấm kỳ hiện tại.

    Đồng hồ lịch sử chỉ tồn tại trong bộ nhớ, không ghi/giả timestamp của
    dự báo thật. Mô hình đã thiết kế sau khi xem lịch sử: số đo này chỉ chẩn
    đoán, không phải bằng chứng tiến cứu hoặc giấy phép đề bạt.
    """
    knowledge = KnowledgeBaseManager(frame)
    clean = knowledge.frame
    if not isinstance(last, int) or isinstance(last, bool) or not 1 <= last <= len(clean) - 3:
        raise ValueError("Số kỳ kiểm phải từ 1 đến số kỳ lịch sử trừ 3")
    modes = {}
    for mode in ("de", "loto"):
        state = online.new_state(mode, profile="agents")
        losses = {name: [] for name in (*online.AGENT_EXPERTS, "mixture")}
        dates, recorded = [], 0
        for t in range(len(clean) - last, len(clean)):
            past = clean.iloc[:t]
            target = str(clean.iloc[t]["date"])
            if online._date(target) != online._date(str(past.iloc[-1]["date"])) + timedelta(days=1):
                continue
            incumbent = np.full(100, baseline_rate(mode))
            path = (prediction_dir / f"predict_next_{mode}_all_{target}.csv"
                    if prediction_dir is not None else None)
            if path is not None and path.exists():
                published, incumbent = online._prediction_frame(path, mode)
                for column, expected in (("target_date", target), ("anchor_date", past.iloc[-1]["date"])):
                    if column in published and set(published[column].astype(str)) != {expected}:
                        raise ValueError("Artifact đối chứng sai ngày đích/ngày neo")
                recorded += 1
            ensemble = AlgorithmEnsemble(KnowledgeBaseManager(past)).predict(mode, incumbent)
            state, record = online.advance(state, past, incumbent, target,
                now=datetime.combine(online._date(target), time(0), VIETNAM_TZ),
                expert_predictions=ensemble.probabilities)
            actual = knowledge.outcomes[mode][t]
            for name in losses:
                probability = record["mixture"] if name == "mixture" else record["experts"][name]
                losses[name].append(online.proper_losses(mode, probability, actual))
            dates.append(target)
        measured = {}
        for name, scores in losses.items():
            gain = [a["logloss"] - b["logloss"]
                    for a, b in zip(losses["constant"], scores, strict=True)]
            measured[name] = {
                "brier": float(np.mean([s["brier"] for s in scores])) if scores else None,
                "logloss": float(np.mean([s["logloss"] for s in scores])) if scores else None,
                "gain_vs_constant": online._gain_stats(gain),
            }
        modes[mode] = {"draws": len(dates), "first_date": dates[0] if dates else None,
                       "last_date": dates[-1] if dates else None,
                       "incumbent_recorded_draws": recorded,
                       "incumbent_missing_uses_constant": len(dates) - recorded,
                       "agents": measured}
    return {"schema_version": 1, "evidence_type": "retrospective_diagnostic",
            "prospective_draws": 0, "promotion_allowed": False,
            "input_fingerprint": online._fingerprint(clean), "requested_draws": last,
            "modes": modes}
