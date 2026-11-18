from __future__ import annotations

"""Chẩn đoán chất lượng mô hình xác suất, sâu hơn một cột LogLoss.

Trang Chất lượng mô hình trước đây in hai bảng số thô: LogLoss, Brier, và kỹ
năng so với đường cơ sở. Nó trả lời được "mô hình hơn hay kém hằng số bao
nhiêu" nhưng không trả lời được câu quan trọng hơn: **vì sao**. Một mô hình có
kỹ năng ~0 có thể vì hai lý do hoàn toàn khác nhau — hiệu chỉnh lệch, hoặc
không phân biệt được gì — và hai lý do ấy đòi hai cách sửa trái ngược.

Phân rã Murphy tách đúng hai thứ đó:

    Brier = độ_tin_cậy − độ_phân_giải + độ_bất_định

- **độ tin cậy** (càng nhỏ càng tốt): nói 30% thì có đúng 30% số lần xảy ra
  không. Đây là thứ sửa được bằng hiệu chỉnh.
- **độ phân giải** (càng lớn càng tốt): mô hình có tách được nhóm khả năng cao
  khỏi nhóm khả năng thấp không. Đây là lợi thế dự báo thật sự.
- **độ bất định**: phương sai của chính kết quả. Không mô hình nào đụng tới
  được; nó là trần của bài toán.

Đo trên lịch sử dự báo của dự án, độ phân giải của mô hình LOTO bằng khoảng
0,007% độ bất định. Con số ấy nói rõ hơn mọi bảng LogLoss: mô hình hiệu chỉnh
tốt và gần như không phân biệt được số nào hơn số nào.

Ngoài ra mô-đun sửa một lỗi đơn vị đã đi vào dữ liệu đã xuất bản. Xem
:func:`normalize_brier_scale`.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ensemble.ensemble_components import (
    COMPONENT_KEYS,
    availability_from_history_day,
    published_with_level_anchor,
)
from ensemble.ensemble_utils import (
    EnsembleWeights,
    finalize_blend,
    load_ensemble_weights,
)
from core.xsmb_domain import LOTO_DRAWS_PER_DAY, baseline_rate
from evaluation.forecast_metrics import (
    auc_by_draw,
    by_period,
    calibration_error,
    chance_reciprocal_rank,
    cluster_bootstrap_ci,
    rank_of_truth,
    within_draw_permutation_p,
)
from evaluation.skill_monitor import MIN_DAYS, graded_series, published_evaluation, update_ledger
from evaluation.skill_monitor import evaluate as evaluate_skill

#: 2 (16-11-2026): thêm ``calibration_error``, ``ranking`` và ``by_month`` cho từng chế độ.
SCHEMA_VERSION = 2

#: Số nhóm của biểu đồ hiệu chỉnh. Mười nhóm theo phân vị giữ cho mỗi nhóm đủ
#: đông để tỉ lệ quan sát được có ý nghĩa; chia đều theo giá trị thì nhóm đuôi
#: chỉ còn vài chục dòng và khoảng tin cậy rộng đến vô dụng.
CALIBRATION_BINS = 10

MODES: tuple[str, ...] = ("loto", "de")


def normalize_brier_scale(history: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Đưa mọi dòng Brier của Đặc Biệt về CÙNG một định nghĩa.

    ``categorical_brier`` từng dùng ``mean`` thay vì ``sum``, nên các dòng ghi
    trước bản sửa nhỏ hơn quy ước hiện hành đúng 100 lần. Bản sửa mã đã vào từ
    lâu nhưng LỊCH SỬ ĐÃ LƯU thì chưa ai chuyển đổi, nên cột Brier của trang
    Chất lượng mô hình chứa hai đơn vị cạnh nhau: 217 dòng quanh 0,0099 rồi
    đột ngột 12 dòng quanh 0,9901. Người đọc thấy một bước nhảy 100 lần và
    không có cách nào biết đó là đổi đơn vị chứ không phải mô hình hỏng.

    Phát hiện bằng bất biến toán học chứ không bằng mốc ngày cứng: với một
    phân phối phân loại hợp lệ, xác suất gán cho kết quả thắng là
    ``exp(−logloss)``, nên Brier theo quy ước tổng không bao giờ nhỏ hơn
    ``(1 − exp(−logloss))²``. Dòng nào thủng cận dưới ấy là dòng thang cũ.

    Phép đổi là chính xác chứ không phải xấp xỉ: quy ước cũ bằng tổng chia
    100, nên nhân 100 trả lại đúng tổng.

    Returns:
        Bảng đã chuẩn hoá, và số dòng đã đổi thang.
    """
    out = history.copy()
    converted = 0
    for column in ("brier", "baseline_brier", "logloss"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")

    is_de = out["mode"].astype(str) == "de"
    winner = np.exp(-out["logloss"].to_numpy(dtype=float))
    lower_bound = (1.0 - winner) ** 2
    stale = is_de.to_numpy() & np.isfinite(lower_bound) & (
        out["brier"].to_numpy(dtype=float) < lower_bound * (1.0 - 1e-6)
    )
    if stale.any():
        out.loc[stale, "brier"] = out.loc[stale, "brier"] * 100.0
        if "baseline_brier" in out.columns:
            baseline = out.loc[stale, "baseline_brier"]
            out.loc[stale, "baseline_brier"] = baseline * 100.0
        converted = int(stale.sum())
    return out, converted


def ensemble_probabilities(history: pd.DataFrame, weights: EnsembleWeights, mode: str):
    """Dựng lại vector xác suất tổ hợp cho từng kỳ, đúng cách production dựng.

    Trọng số được chuẩn hoá lại theo thành phần CÓ MẶT của từng ngày. Không làm
    vậy thì những ngày thiếu thành phần cầu/thống kê — 92% số ngày trong lịch
    sử này — bị hụt tổng trọng số và xác suất tụt xuống thấp một cách giả tạo.
    """
    columns = {"ml": "p_ml", "cau": "p_cau", "stat": "p_stat",
               "active": "p_active", "stable": "p_stable"}
    raw = np.array([getattr(weights, f"w_{key}") for key in COMPONENT_KEYS], dtype=float)
    days, probs, labels = [], [], []

    for day, group in history.groupby("target_date", sort=True):
        sub = group.sort_values("number", kind="stable")
        if len(sub) != 100 or sub["y"].isna().any():
            continue
        # Cùng MỘT cổng canh với đường dự đoán thật. Trước đây chỗ này chỉ đòi
        # hữu hạn, nên 212 trong 231 ngày lịch sử loto ghi p_active/p_stable ở
        # thang "gần 1,0 cho mọi con" vẫn được coi là dùng được — và Brier báo
        # 0,3133 trong khi trên dữ liệu sạch con số thật là 0,1802.
        available = availability_from_history_day(sub, mode=mode)
        vectors, mask = [], []
        for index, key in enumerate(COMPONENT_KEYS):
            values = pd.to_numeric(sub[columns[key]], errors="coerce").to_numpy(dtype=float)
            usable = bool(available.get(key, False)) and raw[index] > 0.0
            vectors.append(np.nan_to_num(values))
            mask.append(1.0 if usable else 0.0)
        effective = raw * np.asarray(mask)
        if effective.sum() <= 0.0:
            continue
        effective /= effective.sum()
        blend = sum(w * v for w, v in zip(effective, vectors, strict=True))
        # Phải dùng ĐÚNG phép chốt đã dùng khi CÔNG BỐ ngày ấy, kể cả sàn xác
        # suất — nếu không, trang Chất lượng lại chấm một mô hình khác mô hình
        # được xuất bản. Ngày trước khi có neo mức LOTO được chốt bằng clip01.
        blend = finalize_blend(blend, mode, anchor_loto=published_with_level_anchor(sub))
        days.append(str(day))
        probs.append(blend)
        labels.append(pd.to_numeric(sub["y"], errors="coerce").to_numpy(dtype=float))

    if not days:
        raise ValueError(f"{mode}: không có kỳ nào đủ điều kiện chấm")
    return days, np.asarray(probs), np.asarray(labels)


def _wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    rate = hits / total
    denom = 1.0 + z * z / total
    centre = (rate + z * z / (2 * total)) / denom
    half = z * np.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def calibration(p: np.ndarray, y: np.ndarray, bins: int = CALIBRATION_BINS) -> list[dict]:
    """Biểu đồ hiệu chỉnh: từng nhóm phân vị, xác suất dự báo so với tỉ lệ thực.

    Kèm khoảng Wilson chứ không kèm khoảng chuẩn: ở chế độ Đặc Biệt tỉ lệ thực
    quanh 0,01 nên khoảng chuẩn tràn xuống dưới 0 và vẽ ra thứ vô nghĩa.
    """
    flat_p, flat_y = p.reshape(-1), y.reshape(-1)
    edges = np.unique(np.quantile(flat_p, np.linspace(0.0, 1.0, bins + 1)))
    if len(edges) < 2:
        # Dự báo hằng vẫn tạo một nhóm chứa TOÀN BỘ quan sát. Bỏ nhóm ấy
        # khiến phân rã Murphy báo độ lệch hiệu chỉnh và Brier nhóm bằng 0.
        edges = np.repeat(edges, 2)
    edges[-1] += 1e-12
    index = np.clip(np.digitize(flat_p, edges) - 1, 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        chosen = index == b
        count = int(chosen.sum())
        if count == 0:
            continue
        hits = int(flat_y[chosen].sum())
        low, high = _wilson(hits, count)
        rows.append(
            {
                "bin": b,
                "count": count,
                "predicted": float(flat_p[chosen].mean()),
                "observed": hits / count,
                "ci_low": low,
                "ci_high": high,
            }
        )
    return rows


def murphy(p: np.ndarray, y: np.ndarray, bins: int = CALIBRATION_BINS) -> dict:
    """Phân rã ``Brier = tin_cậy − phân_giải + bất_định``.

    Phân rã dùng CHÍNH các nhóm của biểu đồ hiệu chỉnh, nên hai phần của báo
    cáo luôn nói về cùng một cách chia. Tính bằng hai cách chia khác nhau thì
    tổng ba thành phần không còn khớp Brier thực tế và cả bảng mất ý nghĩa.
    """
    flat_p, flat_y = p.reshape(-1), y.reshape(-1)
    total = len(flat_p)
    mean_y = float(flat_y.mean())
    rows = calibration(p, y, bins)
    reliability = sum(r["count"] * (r["predicted"] - r["observed"]) ** 2 for r in rows) / total
    resolution = sum(r["count"] * (r["observed"] - mean_y) ** 2 for r in rows) / total
    uncertainty = mean_y * (1.0 - mean_y)

    # Đẳng thức `tin cậy − phân giải + bất định = Brier` đúng CHÍNH XÁC cho dự
    # báo ĐÃ GỘP NHÓM, tức khi mọi ô trong một nhóm được thay bằng trung bình
    # nhóm. Với dự báo thô còn dư một phần do chia nhóm. Bản đầu gọi chênh lệch
    # ấy là "khớp" và in hai số lệch nhau ở chữ số thứ năm ngay cạnh chữ
    # "khớp" — nên ở đây tách ra và gọi đúng tên.
    binned = sum(
        r["count"] * ((r["predicted"] - r["observed"]) ** 2 + r["observed"] * (1 - r["observed"]))
        for r in rows
    ) / total
    direct = float(np.mean((flat_p - flat_y) ** 2))
    return {
        "reliability": float(reliability),
        "resolution": float(resolution),
        "uncertainty": float(uncertainty),
        "brier_binned": float(binned),
        "brier_from_decomposition": float(reliability - resolution + uncertainty),
        "brier_direct": direct,
        "binning_residual": float(direct - binned),
        "resolution_share_of_uncertainty": float(resolution / uncertainty) if uncertainty else 0.0,
        "base_rate": mean_y,
    }


def sharpness(p: np.ndarray, mode: str, bins: int = 24) -> dict:
    """Độ sắc: mô hình dám rời khỏi tỉ lệ nền bao xa.

    Một mô hình hiệu chỉnh hoàn hảo mà luôn trả đúng tỉ lệ nền thì độ sắc bằng
    0 và vô dụng, dù mọi thước đo hiệu chỉnh đều đẹp. Nên độ sắc phải đứng
    cạnh độ tin cậy, không được đọc riêng.
    """
    flat = p.reshape(-1)
    base = baseline_rate(mode)
    counts, edges = np.histogram(flat, bins=bins)
    return {
        "base_rate": float(base),
        "min": float(flat.min()),
        "max": float(flat.max()),
        "std": float(flat.std()),
        "spread_vs_base": float(flat.std() / base) if base else 0.0,
        "histogram": [
            {"lo": float(edges[i]), "hi": float(edges[i + 1]), "count": int(counts[i])}
            for i in range(len(counts))
        ],
    }


#: Số lịch sử mô phỏng cho mốc ECE và hạt giống cố định: báo cáo chỉ đổi khi dữ liệu đổi.
ECE_SIMULATIONS = 500
ECE_SEED = 20261116


def simulate_calibrated_outcomes(p: np.ndarray, mode: str, rng: np.random.Generator) -> np.ndarray:
    """Một bộ kết cục giả mà vector ``p`` là hiệu chỉnh ĐÚNG, giữ cấu trúc của kỳ quay.

    Đặc Biệt: mỗi kỳ đúng một con, rút theo ``p`` của kỳ ấy. LOTO: 27 giải mỗi kỳ rút từ phân phối
    từng-giải ``r`` suy ngược từ ``p = 1 − (1 − r)²⁷`` rồi chuẩn hoá, nên các con của một kỳ tranh
    nhau 27 giải đúng như thật (100 con của một kỳ không độc lập). Vector đã neo mức
    (``Σp ≈ 23,77``) thì bước chuẩn hoá gần như không đổi gì.
    """
    p = np.asarray(p, dtype=float)
    if mode == "de":
        per_slot, slots = p / p.sum(axis=1, keepdims=True), 1
    else:
        per_slot = 1.0 - (1.0 - np.clip(p, 0.0, 1.0 - 1e-12)) ** (1.0 / LOTO_DRAWS_PER_DAY)
        per_slot, slots = per_slot / per_slot.sum(axis=1, keepdims=True), LOTO_DRAWS_PER_DAY
    cumulative = np.cumsum(per_slot, axis=1)
    cumulative[:, -1] = 1.0
    picks = (rng.random((len(p), slots, 1)) >= cumulative[:, None, :]).sum(axis=2)
    outcomes = np.zeros(p.shape)
    outcomes[np.arange(len(p))[:, None], picks] = 1.0
    return outcomes


def calibration_summary(p: np.ndarray, y: np.ndarray, mode: str, *, simulations: int = ECE_SIMULATIONS,
                        seed: int = ECE_SEED) -> dict:
    """ECE của vector đã công bố, đặt cạnh ECE mà một dự báo hiệu chỉnh HOÀN HẢO cũng sẽ có.

    ECE luôn dương kể cả khi hiệu chỉnh hoàn hảo: mỗi nhóm chỉ có vài trăm ô nên tỉ lệ quan sát của
    nó dao động quanh xác suất dự báo. Một con số đứng riêng vì thế không nói được gì, và so với dự
    báo hằng số cũng sai thước (hằng số dồn mọi ô vào MỘT nhóm, nhiễu nhỏ hơn hẳn). Mốc đúng là
    ECE của chính các xác suất này khi kết cục được rút ĐÚNG theo chúng: ``ece_expected`` là trung
    bình, ``ece_upper95`` là phân vị 95%, và ``p_value`` là tỉ lệ lịch sử mô phỏng có ECE không nhỏ
    hơn ECE quan sát. p nhỏ mới là bằng chứng lệch hiệu chỉnh.
    """
    out = calibration_error(calibration(p, y))
    rng = np.random.default_rng(seed)
    null = np.array([
        calibration_error(calibration(p, simulate_calibrated_outcomes(p, mode, rng)))["ece"]
        for _ in range(simulations)
    ])
    out["ece_expected"] = float(null.mean())
    out["ece_upper95"] = float(np.quantile(null, 0.95))
    out["p_value"] = float((int((null >= out["ece"]).sum()) + 1) / (simulations + 1))
    out["simulations"] = simulations
    return out


def ranking(p: np.ndarray, y: np.ndarray, mode: str) -> dict:
    """Vector đã công bố XẾP HẠNG đúng tới đâu, trên toàn bộ 100 con chứ không chỉ Top-K.

    LOTO: AUC — xác suất một con đã về được xếp trên một con không về (0,5 là ngẫu nhiên). Đặc
    Biệt: hạng nghịch đảo trung bình và hạng trung bình của con đã về. Hoà điểm chia đều, nên vector
    phẳng ra đúng mức ngẫu nhiên. p là phép hoán vị nhãn trong từng kỳ. Tỉ lệ trúng của danh sách
    Top 10 từng trang có sổ riêng, chấm theo kỳ quay công bằng mô phỏng (`evaluation.board_record`).
    """
    hits = np.asarray(y) > 0.5
    if len(hits) < 2:
        return {"draws": int(len(hits))}
    if mode == "de":
        truth = hits.argmax(axis=1)
        rank, reciprocal = rank_of_truth(p, truth)
        low, high = cluster_bootstrap_ci(reciprocal)
        return {
            "draws": int(len(hits)),
            "metric": "mrr",
            "value": float(reciprocal.mean()),
            "chance": chance_reciprocal_rank(hits.shape[1]),
            "ci_low": low,
            "ci_high": high,
            "mean_rank": float(rank.mean()),
            "chance_rank": (hits.shape[1] + 1) / 2.0,
            "p_value": within_draw_permutation_p(
                p, hits, lambda s, h: float(rank_of_truth(s, h.argmax(axis=1))[1].mean())
            ),
        }
    per_draw = auc_by_draw(p, hits)
    usable = per_draw[np.isfinite(per_draw)]
    low, high = cluster_bootstrap_ci(usable)
    return {
        "draws": int(len(usable)),
        "metric": "auc",
        "value": float(usable.mean()),
        "chance": 0.5,
        "ci_low": low,
        "ci_high": high,
        "p_value": within_draw_permutation_p(p, hits, lambda s, h: float(np.nanmean(auc_by_draw(s, h)))),
    }


def skill_series(history: pd.DataFrame, mode: str) -> dict:
    """Chuỗi kỹ năng theo ngày, kèm dải bất định và đường tích luỹ.

    Bảng cũ in kỹ năng từng ngày rồi để người đọc tự đoán con số ±0,08% có đáng
    kể không. Không đáng — nhưng phải nói ra bằng sai số chuẩn chứ không bằng
    cảm giác. Dải ±1,96·SE quanh 0 cho biết mức dao động thuần nhiễu trông như
    thế nào, và kỹ năng trung bình nằm trong hay ngoài dải ấy.
    """
    sub = history[history["mode"].astype(str) == mode].sort_values("target_date", kind="stable")
    # Lịch sử cũ chưa mang cột đối chứng. Trang chẩn đoán mà sập vì thiếu một
    # cột thì đúng lúc cần nhất lại là lúc không có gì để đọc, nên thiếu cột
    # phải thành "chưa đủ lịch sử" chứ không thành lỗi.
    if "logloss_skill" not in sub.columns:
        return {"days": 0}
    values = pd.to_numeric(sub["logloss_skill"], errors="coerce")
    usable = sub[values.notna()]
    return summarize_skill(
        usable["target_date"].astype(str).tolist(), values.dropna().to_numpy(dtype=float)
    )


def summarize_skill(dates: list[str], series: np.ndarray) -> dict:
    """Trung bình, sai số chuẩn, dải 95% và đường tích luỹ của chuỗi kỹ năng."""
    series = np.asarray(series, dtype=float)
    if len(series) == 0:
        return {"days": 0}
    mean = float(series.mean())
    stderr = float(series.std(ddof=1) / np.sqrt(len(series))) if len(series) > 1 else 0.0
    return {
        "days": int(len(series)),
        "mean": mean,
        "stderr": stderr,
        "ci_low": mean - 1.96 * stderr,
        "ci_high": mean + 1.96 * stderr,
        "distinguishable_from_zero": bool(abs(mean) > 1.96 * stderr),
        "share_worse_than_baseline": float((series < 0).mean()),
        "points": [
            {"date": str(d), "skill": float(v), "cumulative": float(c)}
            for d, v, c in zip(
                dates,
                series,
                np.cumsum(series) / np.arange(1, len(series) + 1),
                strict=True,
            )
        ],
    }


def coverage(history: pd.DataFrame) -> dict:
    """Bao nhiêu phần lịch sử được chấm từ ARTIFACT THẬT đã phát hành.

    Phân biệt này đổi cách đọc mọi con số phía trên. Dòng chấm từ artifact đã
    phát hành là bằng chứng về thứ người dùng thực sự nhận được; dòng dựng lại
    về sau chỉ là ước lượng, và ở dự án này hai nhóm cho kết quả lệch nhau rất
    xa — nhóm dựng lại báo kỹ năng −7,4% trong khi nhóm artifact thật báo
    −0,02%. In gộp hai nhóm vào một con số là tự lừa mình.
    """
    if "evaluation_source" not in history.columns:
        history = history.assign(evaluation_source="")
    if "logloss_skill" not in history.columns:
        history = history.assign(logloss_skill=np.nan)
    source = history["evaluation_source"].fillna("")
    exact = source == "exact_emitted_prediction_artifact"
    rows = []
    for mode in MODES:
        chosen = history["mode"].astype(str) == mode
        total = int(chosen.sum())
        exact_count = int((chosen & exact).sum())
        rows.append(
            {
                "mode": mode,
                "rows": total,
                "exact_artifact_rows": exact_count,
                "exact_share": (exact_count / total) if total else 0.0,
                "exact_mean_skill": float(
                    pd.to_numeric(history.loc[chosen & exact, "logloss_skill"], errors="coerce").mean()
                )
                if exact_count
                else float("nan"),
                "reconstructed_mean_skill": float(
                    pd.to_numeric(history.loc[chosen & ~exact, "logloss_skill"], errors="coerce").mean()
                )
                if total - exact_count
                else float("nan"),
            }
        )
    return {"by_mode": rows}


def build(data_dir: Path) -> Path:
    """Tính toàn bộ chẩn đoán và ghi ``data/evaluation/model_quality/report.json``."""
    update_ledger(data_dir)
    history_path = data_dir / "evaluation" / "prob_eval" / "ensemble_history.csv"
    raw_history = pd.read_csv(history_path)
    history, converted = normalize_brier_scale(raw_history)

    modes = {}
    for mode in MODES:
        # Chấm CHÍNH vector đã công bố trước kỳ quay (xem skill_monitor). Bản
        # dựng lại từ pred_<mode>.csv bỏ qua hiệu chỉnh và tầng xếp chồng, tức
        # chấm một mô hình khác: nó từng in Đặc Biệt tới 25,9% và kỹ năng
        # −2,0% trong khi thứ người xem nhận cao nhất 1,28% và kỹ năng −0,03%.
        # Chỉ lùi về bản dựng lại khi chưa đủ artifact để kết luận.
        days, probabilities, labels = published_evaluation(data_dir, mode)
        monthly: list[dict] = []
        if len(days) >= MIN_DAYS:
            source = "published"
            # Kỹ năng lấy từ sổ cái để không mất những kỳ mà artifact đã bị dọn;
            # hiệu chỉnh và độ sắc cần cả vector nên chỉ chấm artifact còn trên đĩa.
            graded_days, graded_skill = graded_series(data_dir, mode)
            skill = summarize_skill(graded_days, graded_skill)
            monthly = by_period(graded_days, graded_skill)
        else:
            source = "reconstructed"
            predictions = pd.read_csv(data_dir / "evaluation" / "history" / f"pred_{mode}.csv")
            weights = load_ensemble_weights(data_dir, mode)
            days, probabilities, labels = ensemble_probabilities(predictions, weights, mode)
            skill = skill_series(history, mode)
        modes[mode] = {
            "mode": mode,
            "source": source,
            "days": len(days),
            "first_day": days[0],
            "last_day": days[-1],
            "murphy": murphy(probabilities, labels),
            "calibration": calibration(probabilities, labels),
            "calibration_error": calibration_summary(probabilities, labels, mode),
            "sharpness": sharpness(probabilities, mode),
            "ranking": ranking(probabilities, labels, mode),
            "skill": skill,
            # Kỹ năng theo tháng lịch của chính chuỗi đã công bố (sổ cái + artifact còn trên đĩa).
            "by_month": monthly,
        }

    # Ngày chấm cuối cùng, để trang phát hiện được báo cáo cũ. Bước chẩn đoán
    # chạy với `allow_fail`, nên khi nó hỏng thì builder vẫn dựng trang từ
    # `report.json` của hôm trước và xuất bản mà không có dấu hiệu nào.
    covered = [block["last_day"] for block in modes.values() if block.get("last_day")]
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "covers_through": max(covered) if covered else None,
        "brier_rows_rescaled": converted,
        "coverage": coverage(history),
        "monitor": [check.as_dict() for check in evaluate_skill(data_dir)],
        "modes": modes,
    }
    out_dir = data_dir / "evaluation" / "model_quality"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Chẩn đoán chất lượng mô hình xác suất")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    print("Wrote:", build(Path(args.data_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
