from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from core.atomic_io import atomic_to_csv
from evaluation.backfill_baseline_skill import brier_is_comparable
from ensemble.ensemble_components import probability_component
from ensemble.ensemble_utils import (
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    skill_score,
)
from core.xsmb_domain import baseline_rate


# Đơn vị của cột ``brier`` trong sổ, ghi ngay trên từng dòng. Ngày 05-09-2026
# ``categorical_brier`` đổi từ TRUNG BÌNH sang TỔNG trên 100 lớp (định nghĩa
# chuẩn), nên Brier Đặc Biệt trong sổ nhảy từ ~0,0099 lên ~0,99: đổi đơn vị,
# không phải mô hình kém đi 100 lần. Giá trị cũ giữ nguyên — sổ là bằng chứng
# ghi theo thời gian — còn nhãn cho người đọc tệp thô biết phải nhân 100.
BRIER_UNIT = {"loto": "mean_100_bernoulli", "de": "sum_100_classes"}
LEGACY_DE_BRIER_UNIT = "mean_100_classes"
BRIER_UNIT_COLUMN = "brier_unit"


def label_brier_units(frame: pd.DataFrame) -> pd.DataFrame:
    """Điền ``brier_unit`` cho dòng chưa có nhãn; nhãn đã ghi không bị đè.

    Dòng Đặc Biệt cũ được nhận ra bằng bất biến toán học
    (:func:`backfill_baseline_skill.brier_is_comparable`), không bằng mốc ngày:
    Brier theo quy ước tổng không bao giờ nhỏ hơn ``(1 − e^−logloss)²``.
    Cột đứng ngay sau ``brier``.
    """
    out = frame.copy()
    if BRIER_UNIT_COLUMN not in out.columns:
        out[BRIER_UNIT_COLUMN] = pd.Series(pd.NA, index=out.index, dtype="object")
    out[BRIER_UNIT_COLUMN] = out[BRIER_UNIT_COLUMN].astype("object")
    missing = out[BRIER_UNIT_COLUMN].isna() | (out[BRIER_UNIT_COLUMN].astype(str).str.strip() == "")
    for position in out.index[missing]:
        mode = str(out.at[position, "mode"])
        if mode not in BRIER_UNIT:
            continue
        logloss = pd.to_numeric(out.at[position, "logloss"], errors="coerce")
        brier = pd.to_numeric(out.at[position, "brier"], errors="coerce")
        if pd.isna(logloss) or pd.isna(brier):
            continue
        if brier_is_comparable(mode, float(logloss), float(brier)):
            out.at[position, BRIER_UNIT_COLUMN] = BRIER_UNIT[mode]
        else:
            out.at[position, BRIER_UNIT_COLUMN] = LEGACY_DE_BRIER_UNIT
    columns = [c for c in out.columns if c != BRIER_UNIT_COLUMN]
    at = columns.index("brier") + 1 if "brier" in columns else len(columns)
    return out[columns[:at] + [BRIER_UNIT_COLUMN] + columns[at:]]


def _latest_fully_labeled_day(df: pd.DataFrame) -> str | None:
    required = {"target_date", "number", "y"}
    if not required.issubset(df.columns):
        return None

    valid_days: list[str] = []
    for day, sub in df.groupby("target_date", sort=True):
        if len(sub) != 100 or not sub["y"].notna().all():
            continue
        numbers = pd.to_numeric(sub["number"], errors="coerce")
        y = pd.to_numeric(sub["y"], errors="coerce")
        if numbers.isna().any() or y.isna().any():
            continue
        n = numbers.to_numpy(dtype=float)
        if not np.all(np.isfinite(n)) or not np.all(n == np.floor(n)):
            continue
        if set(numbers.astype(int).tolist()) != set(range(100)):
            continue
        yi = y.to_numpy(dtype=float)
        if not np.all(np.isin(yi, [0.0, 1.0])):
            continue
        valid_days.append(str(day))
    return valid_days[-1] if valid_days else None


def _load_exact_emitted_prediction(
    predict_dir: Path,
    *,
    mode: str,
    target_date: str,
) -> np.ndarray | None:
    """Load the exact ensemble artifact that was emitted for ``target_date``.

    Historical evaluation must never reconstruct a prediction using today's
    weights, a reduced component subset, or a different calibration contract.
    If the exact artifact was not retained, the honest result is "not evaluable".
    """
    pred_file = predict_dir / f"predict_next_{mode}_all_{target_date}.csv"
    if not pred_file.exists() or pred_file.stat().st_size == 0:
        return None

    pred = pd.read_csv(pred_file)
    component = probability_component(
        pred,
        mode=mode,  # type: ignore[arg-type]
        expected_target_date=target_date,
    )
    if not component.available:
        print(
            f"[SKIP] exact emitted prediction artifact is invalid for {mode} "
            f"{target_date}: {component.reason}"
        )
        return None
    return component.prob


def evaluate_latest_emitted(
    *,
    mode: str,
    history_path: Path,
    predict_dir: Path,
) -> dict[str, object] | None:
    if not history_path.exists() or history_path.stat().st_size == 0:
        return None

    df = pd.read_csv(history_path)
    tdate = _latest_fully_labeled_day(df)
    if tdate is None:
        return None

    p = _load_exact_emitted_prediction(
        predict_dir,
        mode=mode,
        target_date=tdate,
    )
    if p is None:
        return None

    sub = df[df["target_date"].astype(str) == tdate].copy()
    sub["number"] = pd.to_numeric(sub["number"], errors="raise").astype(int)
    sub = sub.sort_values("number", kind="stable")
    y = pd.to_numeric(sub["y"], errors="raise").astype(int).to_numpy()

    # Đường cơ sở không thông tin, chấm bằng ĐÚNG các hàm đo dùng cho mô hình
    # nên hai con số so sánh được trực tiếp. Thiếu nó thì không thể biết mô
    # hình có hơn được một hằng số hay không — đợt hỏng 12/2025–01/2026 đã
    # trôi qua tám tháng mà không ai phát hiện chính vì lý do này.
    const = np.full_like(p, baseline_rate(mode), dtype=np.float64)

    if mode == "de":
        if int(y.sum()) != 1:
            print(
                f"[SKIP] invalid De label contract for {tdate}: "
                f"expected exactly one positive label, got {int(y.sum())}"
            )
            return None
        y_idx = int(np.argmax(y))
        ll = categorical_logloss(p, y_idx)
        br = categorical_brier(p, y_idx)
        base_ll = categorical_logloss(const, y_idx)
        base_br = categorical_brier(const, y_idx)
    else:
        ll = bernoulli_logloss(p, y)
        br = bernoulli_brier(p, y)
        base_ll = bernoulli_logloss(const, y)
        base_br = bernoulli_brier(const, y)

    return {
        "mode": mode,
        "target_date": tdate,
        "logloss": float(ll),
        "brier": float(br),
        BRIER_UNIT_COLUMN: BRIER_UNIT[mode],
        "baseline_logloss": float(base_ll),
        "baseline_brier": float(base_br),
        "logloss_skill": skill_score(float(ll), float(base_ll)),
        "brier_skill": skill_score(float(br), float(base_br)),
        "evaluation_source": "exact_emitted_prediction_artifact",
    }


def _same_metrics(previous: pd.Series, row: dict) -> bool:
    """Dòng đã ghi trùng mọi số đo của dòng mới (bỏ qua giờ ghi). Số so đúng bằng nhau sau khi đọc lại CSV."""
    for key, value in row.items():
        if key == "updated_at_utc":
            continue
        if key not in previous.index:
            return False
        before = previous[key]
        if isinstance(value, float):
            try:
                if float(before) != value:
                    return False
            except (TypeError, ValueError):
                return False
        elif str(before) != str(value):
            return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Append honest metrics for the latest retained emitted ensemble prediction."
    )
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--history-dir", default="data/evaluation/history")
    ap.add_argument("--predict-dir", default="data/forecast/predict")
    ap.add_argument("--out", default="data/evaluation/prob_eval/ensemble_history.csv")
    args = ap.parse_args()

    hist_path = Path(args.history_dir) / f"pred_{args.mode}.csv"
    if not hist_path.exists():
        print("[SKIP] history not found:", hist_path)
        return

    row = evaluate_latest_emitted(
        mode=args.mode,
        history_path=hist_path,
        predict_dir=Path(args.predict_dir),
    )
    if row is None:
        print(
            f"[SKIP] no exact evaluable emitted prediction for {args.mode}; "
            "historical ensemble metrics are never reconstructed from components"
        )
        return

    row["updated_at_utc"] = (
        datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 0:
        old = pd.read_csv(out)
        same = (old["mode"].astype(str) == str(row["mode"])) & (
            old["target_date"].astype(str) == str(row["target_date"])
        )
        if same.any() and "updated_at_utc" in old.columns and _same_metrics(old[same].iloc[-1], row):
            # Chạy lại trên cùng dữ liệu (pipeline chạy lại trong ngày) ra đúng số đo cũ: giữ giờ ghi
            # đầu để sổ không đổi byte nào. Trước 06-11-2026 mỗi lượt chạy lại ghi lại dòng chỉ để đổi giờ.
            row["updated_at_utc"] = old[same].iloc[-1]["updated_at_utc"]
        result = pd.concat([old[~same], pd.DataFrame([row])], ignore_index=True)
    else:
        result = pd.DataFrame([row])
    result = label_brier_units(result)
    result = result.sort_values(["mode", "target_date"], kind="stable")
    atomic_to_csv(result, out, index=False)
    print(
        f"[OK] exact emitted ensemble metrics {row['mode']} {row['target_date']}: "
        f"logloss={row['logloss']:.6f} brier={row['brier']:.6f} -> {out}"
    )


if __name__ == "__main__":
    main()
