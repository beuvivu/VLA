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

from ensemble_components import COMPONENT_KEYS
from ensemble_utils import EnsembleWeights, clip01, normalize_distribution
from xsmb_domain import baseline_rate

SCHEMA_VERSION = 1

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

    for day, sub in history.groupby("target_date", sort=True):
        sub = sub.sort_values("number")
        if len(sub) != 100 or sub["y"].isna().any():
            continue
        vectors, mask = [], []
        for index, key in enumerate(COMPONENT_KEYS):
            values = pd.to_numeric(sub[columns[key]], errors="coerce").to_numpy(dtype=float)
            usable = bool(np.isfinite(values).all()) and raw[index] > 0.0
            vectors.append(np.nan_to_num(values))
            mask.append(1.0 if usable else 0.0)
        effective = raw * np.asarray(mask)
        if effective.sum() <= 0.0:
            continue
        effective /= effective.sum()
        blend = sum(w * v for w, v in zip(effective, vectors))
        blend = normalize_distribution(blend) if mode == "de" else clip01(blend, eps=1e-6)
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
        return []
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


def skill_series(history: pd.DataFrame, mode: str) -> dict:
    """Chuỗi kỹ năng theo ngày, kèm dải bất định và đường tích luỹ.

    Bảng cũ in kỹ năng từng ngày rồi để người đọc tự đoán con số ±0,08% có đáng
    kể không. Không đáng — nhưng phải nói ra bằng sai số chuẩn chứ không bằng
    cảm giác. Dải ±1,96·SE quanh 0 cho biết mức dao động thuần nhiễu trông như
    thế nào, và kỹ năng trung bình nằm trong hay ngoài dải ấy.
    """
    sub = history[history["mode"].astype(str) == mode].sort_values("target_date")
    # Lịch sử cũ chưa mang cột đối chứng. Trang chẩn đoán mà sập vì thiếu một
    # cột thì đúng lúc cần nhất lại là lúc không có gì để đọc, nên thiếu cột
    # phải thành "chưa đủ lịch sử" chứ không thành lỗi.
    if "logloss_skill" not in sub.columns:
        return {"days": 0}
    values = pd.to_numeric(sub["logloss_skill"], errors="coerce")
    usable = sub[values.notna()]
    series = values.dropna().to_numpy(dtype=float)
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
                usable["target_date"].astype(str),
                series,
                np.cumsum(series) / np.arange(1, len(series) + 1),
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
    """Tính toàn bộ chẩn đoán và ghi ``data/model_quality/report.json``."""
    history_path = data_dir / "prob_eval" / "ensemble_history.csv"
    raw_history = pd.read_csv(history_path)
    history, converted = normalize_brier_scale(raw_history)

    modes = {}
    for mode in MODES:
        predictions = pd.read_csv(data_dir / "history" / f"pred_{mode}.csv")
        weights_blob = json.loads(
            (data_dir / "ensemble" / f"weights_{mode}.json").read_text(encoding="utf-8")
        )["weights"]
        weights = EnsembleWeights(
            w_ml=float(weights_blob.get("w_ml", 0.0)),
            w_cau=float(weights_blob.get("w_cau", 0.0)),
            w_stat=float(weights_blob.get("w_stat", 0.0)),
            w_active=float(weights_blob.get("w_active", 0.0)),
            w_stable=float(weights_blob.get("w_stable", 0.0)),
        )
        days, probabilities, labels = ensemble_probabilities(predictions, weights, mode)
        modes[mode] = {
            "mode": mode,
            "days": len(days),
            "first_day": days[0],
            "last_day": days[-1],
            "murphy": murphy(probabilities, labels),
            "calibration": calibration(probabilities, labels),
            "sharpness": sharpness(probabilities, mode),
            "skill": skill_series(history, mode),
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
        "modes": modes,
    }
    out_dir = data_dir / "model_quality"
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
