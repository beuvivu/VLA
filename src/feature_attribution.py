from __future__ import annotations

"""Log tầm quan trọng đặc trưng: thành phần nào thật sự lái quyết định, và có ích không.

Hai đại lượng KHÁC NHAU, và trộn chúng là cách một bảng "feature importance"
trở thành vô nghĩa:

**Đóng góp vào QUYẾT ĐỊNH** (``decision_share``) — thành phần nào làm các con
số khác nhau. Trọng số hiệu dụng một mình không nói được điều này: cả năm thành
phần đều có trung bình xấp xỉ tần suất nền, nên thứ quyết định con nào được
chọn là ĐỘ LỆCH khỏi nền, không phải mức tuyệt đối. Đo bằng
``|w_i · (v_i − nền)|`` chuẩn hoá theo tổng.

**Đóng góp vào KỸ NĂNG** (``skill_delta``) — bỏ thành phần ấy ra thì mô hình
tệ đi bao nhiêu. Đây là leave-one-out có chuẩn hoá lại trọng số, kèm khoảng tin
bootstrap ghép cặp theo NGÀY (ngày là đơn vị độc lập, không phải con số).

Một thành phần có thể lái phần lớn quyết định mà đóng góp kỹ năng bằng 0 — trên
xổ số công bằng đó là trường hợp ĐƯỢC KỲ VỌNG. Bảng này nói thẳng điều đó bằng
nhãn ``distinguishable_from_zero``, thay vì in một con số phần trăm trông như
bằng chứng.
"""

import argparse
import json
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from ensemble_components import COMPONENT_KEYS, availability_from_history_day
from ensemble_utils import clip01, floor_distribution, load_ensemble_weights

SCHEMA_VERSION: Final[int] = 1
MODES: Final[tuple[str, ...]] = ("loto", "de")
BOOTSTRAP_DRAWS: Final[int] = 2000

#: Sàn ý nghĩa THỰC TIỄN: |Δ| phải đạt 0,1% của chính metric mới đáng gọi
#: là có ích. Không có sàn này thì một Δ cỡ 1e-8 vẫn được dán nhãn "có ích
#: rõ rệt" chỉ vì khoảng tin bootstrap hẹp hơn nó.
MATERIAL_EFFECT_FLOOR: Final[float] = 0.001
COMPONENT_COLUMN: Final[dict[str, str]] = {key: f"p_{key}" for key in COMPONENT_KEYS}

#: Nhãn tiếng Việt cho từng thành phần, dùng chung với trang hiển thị.
COMPONENT_LABEL: Final[dict[str, str]] = {
    "ml": "Học máy (GBM)",
    "cau": "Cầu kèo AI/ML",
    "stat": "Tín hiệu thống kê",
    "active": "Cầu đang chạy",
    "stable": "Cầu ổn định",
}


def _usable_days(history: pd.DataFrame, mode: str) -> list[tuple[str, pd.DataFrame]]:
    """Các kỳ có đủ 100 con, có nhãn, và qua cổng canh thành phần."""
    out: list[tuple[str, pd.DataFrame]] = []
    for day, group in history.groupby("target_date", sort=True):
        sub = group.sort_values("number")
        if len(sub) != 100 or sub["y"].isna().any():
            continue
        out.append((str(day), sub))
    return out


def _day_matrices(
    history: pd.DataFrame, mode: str
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray]:
    """Trả về ``(ngày, vectors[ngày, thành phần, 100], mask[ngày, thành phần], nhãn)``."""
    days: list[str] = []
    vectors: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    labels: list[np.ndarray] = []

    for day, sub in _usable_days(history, mode):
        available = availability_from_history_day(sub, mode=mode)
        per_component = np.zeros((len(COMPONENT_KEYS), 100), dtype=np.float64)
        mask = np.zeros(len(COMPONENT_KEYS), dtype=np.float64)
        for index, key in enumerate(COMPONENT_KEYS):
            values = pd.to_numeric(sub[COMPONENT_COLUMN[key]], errors="coerce")
            per_component[index] = np.nan_to_num(values.to_numpy(dtype=np.float64))
            mask[index] = 1.0 if available.get(key, False) else 0.0
        days.append(day)
        vectors.append(per_component)
        masks.append(mask)
        labels.append(pd.to_numeric(sub["y"], errors="coerce").to_numpy(dtype=np.float64))

    if not days:
        raise ValueError(f"{mode}: không có kỳ nào đủ điều kiện quy trách")
    return days, np.asarray(vectors), np.asarray(masks), np.asarray(labels)


def _effective_weights(raw: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Trọng số chuẩn hoá lại trên các thành phần CÓ MẶT của một kỳ."""
    effective = raw * mask
    total = float(effective.sum())
    return effective / total if total > 0.0 else effective


def _blend(vectors: np.ndarray, effective: np.ndarray, mode: str) -> np.ndarray:
    mixed = np.tensordot(effective, vectors, axes=(0, 0))
    return floor_distribution(mixed) if mode == "de" else clip01(mixed, eps=1e-6)


def decision_share(
    vectors: np.ndarray, masks: np.ndarray, raw: np.ndarray, *, base_rate: float
) -> dict[str, float]:
    """Tỉ lệ ĐỘ LỆCH khỏi nền mà mỗi thành phần đóng góp.

    Trọng số hiệu dụng không trả lời được "thành phần nào chọn con số": cả năm
    đều có trung bình xấp xỉ nền, nên chỉ ĐỘ LỆCH mới tạo ra thứ hạng.
    """
    totals = np.zeros(len(COMPONENT_KEYS), dtype=np.float64)
    for day in range(len(vectors)):
        effective = _effective_weights(raw, masks[day])
        deviation = np.abs(effective[:, None] * (vectors[day] - base_rate))
        totals += deviation.sum(axis=1)
    grand = float(totals.sum())
    if grand <= 0.0:
        return {key: 0.0 for key in COMPONENT_KEYS}
    return {key: float(totals[i] / grand) for i, key in enumerate(COMPONENT_KEYS)}


def _logloss(probabilities: np.ndarray, labels: np.ndarray, mode: str) -> np.ndarray:
    """Logloss THEO TỪNG NGÀY, để bootstrap ghép cặp được theo ngày."""
    eps = 1e-12
    clipped = np.clip(probabilities, eps, 1.0 - eps)
    if mode == "de":
        # Phân phối phân loại: chỉ con thật sự về mới vào logloss.
        picked = np.where(labels > 0.5, clipped, 1.0)
        return -np.log(picked).sum(axis=1)
    return -(labels * np.log(clipped) + (1.0 - labels) * np.log(1.0 - clipped)).mean(axis=1)


def _brier(probabilities: np.ndarray, labels: np.ndarray) -> np.ndarray:
    return ((probabilities - labels) ** 2).mean(axis=1)


def leave_one_out(
    vectors: np.ndarray,
    masks: np.ndarray,
    labels: np.ndarray,
    raw: np.ndarray,
    *,
    mode: str,
    rng: np.random.Generator,
) -> list[dict[str, object]]:
    """Bỏ từng thành phần, đo mô hình tệ đi bao nhiêu, kèm khoảng tin.

    Bootstrap GHÉP CẶP và lấy mẫu theo NGÀY: ngày là đơn vị độc lập, còn 100
    con trong cùng một kỳ thì không (tổng số con về mỗi kỳ bị luật chơi chặn).
    Lấy mẫu theo con số sẽ cho khoảng tin hẹp giả tạo.
    """
    n_days = len(vectors)
    full = np.asarray([_blend(vectors[d], _effective_weights(raw, masks[d]), mode)
                       for d in range(n_days)])
    full_logloss = _logloss(full, labels, mode)
    full_brier = _brier(full, labels)

    indices = rng.integers(0, n_days, size=(BOOTSTRAP_DRAWS, n_days))
    rows: list[dict[str, object]] = []

    for position, key in enumerate(COMPONENT_KEYS):
        dropped = raw.copy()
        dropped[position] = 0.0
        if dropped.sum() <= 0.0:
            rows.append({
                "component": key,
                "label": COMPONENT_LABEL[key],
                "reason": "là thành phần duy nhất có trọng số; không bỏ ra được",
                "logloss_delta": None,
                "distinguishable_from_zero": False,
            })
            continue

        # Chỉ so trên những kỳ mà việc bỏ thành phần này CÒN LẠI ít nhất một
        # thành phần khác. Không lọc thì trên các kỳ chỉ có `ml` (212/231 kỳ
        # loto, vì cầu/thống kê chỉ có từ 2026-08-12), bỏ `ml` ra làm tổng
        # trọng số về 0, vector về 0, và logloss nổ — đo được Δ = +2,51 trong
        # khi cả metric chỉ ~0,546. Đó là hiện vật của phép đo, không phải
        # đóng góp của thành phần.
        comparable = np.asarray([
            float((raw * masks[d]).sum()) > 0.0 and float((dropped * masks[d]).sum()) > 0.0
            for d in range(n_days)
        ])
        if not comparable.any():
            rows.append({
                "component": key,
                "label": COMPONENT_LABEL[key],
                "days_active": int(masks[:, position].sum()),
                "days_total": n_days,
                "days_comparable": 0,
                "reason": "không kỳ nào còn thành phần khác khi bỏ nó ra",
                "logloss_delta": None,
                "distinguishable_from_zero": False,
                "materially_useful": False,
            })
            continue

        reduced = np.asarray([_blend(vectors[d], _effective_weights(dropped, masks[d]), mode)
                              for d in range(n_days)])
        # Dương = bỏ thành phần ra thì TỆ HƠN, tức thành phần có ích.
        logloss_gain = (_logloss(reduced, labels, mode) - full_logloss)[comparable]
        brier_gain = (_brier(reduced, labels) - full_brier)[comparable]

        n_comparable = int(comparable.sum())
        draws = rng.integers(0, n_comparable, size=(BOOTSTRAP_DRAWS, n_comparable))
        boot = logloss_gain[draws].mean(axis=1)
        low, high = np.percentile(boot, [2.5, 97.5])
        delta = float(logloss_gain.mean())
        reference = float(full_logloss[comparable].mean())
        relative = abs(delta) / reference if reference > 0.0 else 0.0
        rows.append({
            "component": key,
            "label": COMPONENT_LABEL[key],
            "days_active": int(masks[:, position].sum()),
            "days_total": n_days,
            "days_comparable": n_comparable,
            "logloss_delta": delta,
            "logloss_ci_low": float(low),
            "logloss_ci_high": float(high),
            "logloss_relative": relative,
            "brier_delta": float(brier_gain.mean()),
            "distinguishable_from_zero": bool(low > 0.0 or high < 0.0),
            # Ý nghĩa THỐNG KÊ không phải ý nghĩa THỰC TIỄN. Một Δ cỡ 1e-8 có
            # thể loại được 0 khỏi khoảng tin mà vẫn không đổi một quyết định
            # nào. Ngưỡng 0,1% của chính metric là mức tối thiểu đáng gọi tên.
            "materially_useful": bool(
                (low > 0.0 or high < 0.0) and relative >= MATERIAL_EFFECT_FLOOR
            ),
        })
    return rows


def per_number_attribution(
    vectors: np.ndarray,
    masks: np.ndarray,
    raw: np.ndarray,
    *,
    day_position: int,
    base_rate: float,
    top: int = 10,
) -> list[dict[str, object]]:
    """Với các con được xếp cao nhất của MỘT kỳ, thành phần nào đẩy chúng lên."""
    effective = _effective_weights(raw, masks[day_position])
    contribution = effective[:, None] * (vectors[day_position] - base_rate)
    ranking = np.argsort(-contribution.sum(axis=0))[:top]

    out: list[dict[str, object]] = []
    for number in ranking:
        column = contribution[:, number]
        magnitude = float(np.abs(column).sum())
        out.append({
            "number": f"{int(number):02d}",
            "deviation_from_base": float(column.sum()),
            "drivers": [
                {
                    "component": key,
                    "label": COMPONENT_LABEL[key],
                    "signed_contribution": float(column[i]),
                    "share_of_magnitude": float(abs(column[i]) / magnitude) if magnitude else 0.0,
                }
                for i, key in enumerate(COMPONENT_KEYS)
                if masks[day_position][i] > 0.0
            ],
        })
    return out


def build(data_dir: Path, *, seed: int = 20260918) -> Path:
    """Tính log quy trách cho mọi chế độ và ghi ``data/feature_attribution/report.json``."""
    rng = np.random.default_rng(seed)
    modes: dict[str, object] = {}

    for mode in MODES:
        history = pd.read_csv(data_dir / "history" / f"pred_{mode}.csv")
        weights = load_ensemble_weights(data_dir, mode)
        raw = np.asarray([getattr(weights, f"w_{key}") for key in COMPONENT_KEYS], dtype=float)
        days, vectors, masks, labels = _day_matrices(history, mode)
        base_rate = float(labels.mean())

        modes[mode] = {
            "mode": mode,
            "days": len(days),
            "first_day": days[0],
            "last_day": days[-1],
            "base_rate": base_rate,
            "configured_weights": weights.as_dict(),
            "decision_share": decision_share(vectors, masks, raw, base_rate=base_rate),
            "skill_contribution": leave_one_out(
                vectors, masks, labels, raw, mode=mode, rng=rng
            ),
            "latest_day_drivers": per_number_attribution(
                vectors, masks, raw, day_position=len(days) - 1, base_rate=base_rate
            ),
        }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_unit": "ngày quay (không phải con số)",
        "modes": modes,
    }
    out_dir = data_dir / "feature_attribution"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Log tầm quan trọng đặc trưng.")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    print(f"[OK] log quy trách đặc trưng -> {build(Path(args.data_dir))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
