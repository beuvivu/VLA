"""Sinh ``data/predictions_today.json`` cho kỳ kế tiếp.

Bổ sung cho ``picks_loto.json`` / ``picks_de.json`` chứ không thay thế; các trang
trong ``docs/`` vẫn đọc hai tệp cũ.

Tệp này KHÔNG được nối vào trọng số sản xuất. Lý do nằm ngay trong dữ liệu mà
chính nó mang theo: qua ba cổng đo, không có bằng chứng nào cho thấy đường soi
cầu hơn được đường cơ sở. Trường ``evidence`` chở đúng các con số đó để người
đọc tệp không phải đi tìm, và ``disclaimer`` nói thẳng điều đó bằng tiếng Việt.

Tự khôi phục: nếu dữ liệu kỳ mới nhất chưa về, quy trình dừng sạch và báo lý do
thay vì phát ra một dự đoán dựng trên lịch sử cũ — một dự đoán cũ mang dấu thời
gian mới là dạng hỏng khó phát hiện nhất.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from bridges import DigitTensor
from features import FeatureContext, SpecialSetExtractor, default_registry
from modeling import (
    DEFAULT_GAN_THRESHOLD_DAYS,
    DeModel,
    Explainer,
    GanFilter,
    LotoModel,
    PredictionBundle,
    build_picks,
    build_training_data,
    local_stamp,
    utc_stamp,
)
from number_reference import digit_sum_mod10, head, tail
from time_policy import DEFAULT_DRAW_CUTOFF, now_vietnam, vietnam_date
from utils import RetryPolicy, with_retry

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Qua ba cổng đo trên dữ liệu thật của kho, không có bằng chứng nào cho thấy "
    "các đường soi cầu hoặc mô hình hơn được đường cơ sở. Các con số dưới đây là "
    "kết quả phân tích thống kê, không phải dự báo đáng tin cậy và không phải "
    "lời khuyên đặt cược."
)


def _research_evidence(research_dir: Path) -> dict[str, object]:
    """Gom kết quả ba cổng đo, nếu đã chạy."""
    evidence: dict[str, object] = {}
    scan = research_dir / "bridge_scan_summary.json"
    if scan.exists():
        payload = json.loads(scan.read_text(encoding="utf-8"))
        evidence["bridge_scan"] = {
            mode: {
                "hypotheses": item["hypotheses"],
                "running_unscreened": item.get("running_at_least_5_unscreened"),
                "survived_fdr": item["survived_fdr"],
            }
            for mode, item in payload.get("modes", {}).items()
        }
    scores = research_dir / "model_scores.json"
    if scores.exists():
        payload = json.loads(scores.read_text(encoding="utf-8"))
        evidence["model_walk_forward"] = {
            mode: {
                "logloss_skill": item["logloss_skill"],
                "paired_t_stat": item["paired_t_stat"],
                "beats_baseline": item["beats_baseline"],
            }
            for mode, item in payload.get("modes", {}).items()
        }
    return evidence


def _special_axes(ctx: FeatureContext, probabilities: np.ndarray) -> dict[str, object]:
    """Chạm, tổng và dàn đề rút ra từ phân phối ĐB."""
    extractor = SpecialSetExtractor()
    order = np.lexsort((np.arange(100), -probabilities))
    top = order[:10]
    return {
        "top_numbers": [f"{int(n):02d}" for n in top],
        "cham": sorted({head(int(n)) for n in top} | {tail(int(n)) for n in top}),
        "tong": sorted({digit_sum_mod10(int(n)) for n in top}),
        "dan_36": extractor.build_dan(ctx, 36),
        "dan_64": extractor.build_dan(ctx, 64),
    }


def build_bundle(tensor: DigitTensor, *, warmup_days: int, research_dir: Path) -> PredictionBundle:
    registry = default_registry()
    anchor = tensor.n_days - 1
    ctx = FeatureContext(tensor=tensor, anchor_index=anchor)
    matrix = registry.build_matrix(ctx)
    target_date = (tensor.dates[anchor] + timedelta(days=1)).date().isoformat()

    picks: list = []
    special: dict[str, object] = {}
    gan = GanFilter(threshold_days=DEFAULT_GAN_THRESHOLD_DAYS)
    gaps = gan.gaps(ctx)

    for mode, factory in (("loto", LotoModel), ("de", DeModel)):
        data = build_training_data(tensor, mode=mode, warmup_days=warmup_days, registry=registry)
        model = factory().fit(data)
        probabilities = model.predict_day(matrix)

        if mode == "loto":
            explainer = Explainer.from_training(model, data.features)
            order = np.lexsort((np.arange(100), -probabilities))[:10]
            reasons = {int(n): explainer.group_shares(matrix, int(n)) for n in order}
            picks = build_picks(
                probabilities,
                baseline=model.baseline,
                gaps=gaps,
                gan_threshold=gan.threshold_days,
                reasons=reasons,
                top_k=10,
            )
        else:
            special = _special_axes(ctx, probabilities)
            special["baseline"] = model.baseline

    return PredictionBundle(
        date=target_date,
        generated_at_local=local_stamp(),
        generated_at_utc=utc_stamp(),
        top_lo_to=picks,
        top_dac_biet=special,
        # Chưa đường cầu nào qua được cổng kiểm định, nên danh sách này rỗng —
        # và rỗng là kết quả, không phải lỗi.
        active_bridges=[],
        disclaimer=DISCLAIMER,
        evidence=_research_evidence(research_dir),
        gan_flagged=[f"{n:02d}" for n in np.flatnonzero(gaps > gan.threshold_days)],
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default="data/xsmb.csv")
    parser.add_argument("--out", default="data/predictions_today.json")
    parser.add_argument("--research-dir", default="data/research")
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument(
        "--max-staleness-days",
        type=int,
        default=2,
        help="Dừng sạch nếu kỳ mới nhất cũ hơn ngần này ngày.",
    )
    args = parser.parse_args()

    raw = with_retry(
        lambda: pd.read_csv(args.raw),
        policy=RetryPolicy(attempts=3),
        description=f"đọc {args.raw}",
    )
    tensor = DigitTensor.from_raw(raw)

    latest = tensor.dates[-1].date()
    staleness = (vietnam_date() - latest).days
    if staleness > args.max_staleness_days:
        # Một dự đoán cũ mang dấu thời gian mới là dạng hỏng khó phát hiện nhất.
        logger.error(
            "kỳ mới nhất là %s, cũ hơn %d ngày so với hôm nay theo giờ Việt Nam; "
            "dừng thay vì phát ra dự đoán dựng trên lịch sử cũ",
            latest,
            staleness,
        )
        return 1

    # Kỳ được dự đoán là kỳ kế tiếp kỳ mới nhất đã có kết quả. Nếu kỳ đó đã
    # quay xong rồi thì đây không còn là dự đoán — đó là hậu đoán mang nhãn dự
    # đoán, dạng sai lệch nặng nhất mà một hệ thống như thế này có thể phát ra.
    target = latest + timedelta(days=1)
    now = now_vietnam()
    already_drawn = target < now.date() or (
        target == now.date() and now.time() >= DEFAULT_DRAW_CUTOFF
    )
    if already_drawn:
        logger.error(
            "kỳ %s đã quay xong (bây giờ là %s giờ Việt Nam) nhưng kết quả chưa "
            "vào kho; dừng thay vì phát ra hậu đoán mang nhãn dự đoán",
            target,
            now.strftime("%Y-%m-%d %H:%M"),
        )
        return 1

    bundle = build_bundle(
        tensor, warmup_days=args.warmup_days, research_dir=Path(args.research_dir)
    )
    path = bundle.to_json(Path(args.out))
    logger.info(
        "đã ghi %s cho ngày %s: %d con lô tô, %d con bị đánh dấu gan",
        path,
        bundle.date,
        len(bundle.top_lo_to),
        len(bundle.gan_flagged),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
