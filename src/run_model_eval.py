"""Chấm điểm cuốn chiếu mô hình xếp chồng so với đường cơ sở.

Dùng ĐÚNG các hàm đo mà sản xuất dùng (``ensemble_utils``) và đúng định nghĩa
điểm kỹ năng mà cổng ``check_baseline_skill`` đọc, nên con số ở đây so sánh trực
tiếp được với lịch sử đánh giá trong ``data/prob_eval/ensemble_history.csv``.

Giao thức cuốn chiếu: huấn luyện trên lịch sử tính tới ngày T, dự đoán ngày T+1,
rồi tiến lên. Huấn luyện lại theo chu kỳ ``refit_every`` ngày thay vì mỗi ngày —
đây là đánh đổi chi phí có chủ đích và được ghi vào báo cáo, không phải chi tiết
giấu đi.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from bridges import DigitTensor
from ensemble_utils import (
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    skill_score,
)
from features import FeatureContext, default_registry
from modeling import DeModel, LotoModel, build_training_data
from xsmb_domain import baseline_rate

SIGNIFICANCE_T = 1.96


def evaluate_mode(
    tensor: DigitTensor,
    *,
    mode: str,
    warmup_days: int = 180,
    refit_every: int = 7,
) -> dict[str, object]:
    registry = default_registry()
    hits = tensor.loto_hits()
    baseline = baseline_rate(mode)
    factory = DeModel if mode == "de" else LotoModel

    model = None
    rows: list[dict[str, float]] = []
    for anchor in range(warmup_days, tensor.n_days - 1):
        if model is None or (anchor - warmup_days) % refit_every == 0:
            data = build_training_data(
                tensor,
                mode=mode,
                warmup_days=warmup_days // 2,
                registry=registry,
                last_anchor=anchor - 1,
            )
            model = factory().fit(data)

        matrix = registry.build_matrix(FeatureContext(tensor=tensor, anchor_index=anchor))
        probability = model.predict_day(matrix)
        constant = np.full_like(probability, baseline)

        if mode == "de":
            index = int(tensor.de_index[anchor + 1])
            model_ll = categorical_logloss(probability, index)
            model_br = categorical_brier(probability, index)
            base_ll = categorical_logloss(constant, index)
            base_br = categorical_brier(constant, index)
        else:
            label = hits[anchor + 1].astype(int)
            model_ll = bernoulli_logloss(probability, label)
            model_br = bernoulli_brier(probability, label)
            base_ll = bernoulli_logloss(constant, label)
            base_br = bernoulli_brier(constant, label)

        rows.append(
            {
                "logloss": float(model_ll),
                "brier": float(model_br),
                "baseline_logloss": float(base_ll),
                "baseline_brier": float(base_br),
            }
        )

    frame = pd.DataFrame(rows)
    # Chênh lệch theo từng ngày cho phép kiểm t ghép cặp — mạnh hơn nhiều so với
    # so sánh hai trung bình độc lập, vì cùng một ngày chi phối cả hai vế.
    delta = frame["baseline_logloss"] - frame["logloss"]
    stderr = float(delta.std(ddof=1) / np.sqrt(len(delta))) if len(delta) > 1 else 0.0
    t_stat = float(delta.mean() / stderr) if stderr > 1e-12 else 0.0

    return {
        "mode": mode,
        "days": int(len(frame)),
        "refit_every": refit_every,
        "logloss": float(frame["logloss"].mean()),
        "baseline_logloss": float(frame["baseline_logloss"].mean()),
        "brier": float(frame["brier"].mean()),
        "baseline_brier": float(frame["baseline_brier"].mean()),
        "logloss_skill": skill_score(
            float(frame["logloss"].mean()), float(frame["baseline_logloss"].mean())
        ),
        "brier_skill": skill_score(
            float(frame["brier"].mean()), float(frame["baseline_brier"].mean())
        ),
        "paired_t_stat": t_stat,
        "beats_baseline": bool(t_stat > SIGNIFICANCE_T),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default="data/xsmb.csv")
    parser.add_argument("--out-dir", default="data/research")
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--refit-every", type=int, default=7)
    args = parser.parse_args()

    tensor = DigitTensor.from_raw(pd.read_csv(args.raw))
    results = [
        evaluate_mode(
            tensor,
            mode=mode,
            warmup_days=args.warmup_days,
            refit_every=args.refit_every,
        )
        for mode in ("loto", "de")
    ]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "significance_t": SIGNIFICANCE_T,
        "modes": {item["mode"]: item for item in results},
    }
    (out_dir / "model_scores.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for item in results:
        verdict = "VƯỢT" if item["beats_baseline"] else "KHÔNG vượt"
        print(
            f"{item['mode']:5} {item['days']:>3} ngày | "
            f"logloss {item['logloss']:.6f} vs nền {item['baseline_logloss']:.6f} | "
            f"kỹ năng {item['logloss_skill']:+.2%} | "
            f"t ghép cặp {item['paired_t_stat']:+.2f} | {verdict} đường cơ sở"
        )


if __name__ == "__main__":
    main()
