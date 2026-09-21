from __future__ import annotations

"""Mô phỏng một kỳ XSMB theo xác suất của mô hình — phần DỮ LIỆU.

Đây là nửa dữ liệu của ``build_fun_prediction.py`` cũ, vốn vừa lấy mẫu vừa
dựng HTML rồi chèn vào ba trang. Tầng trình bày đã bị xóa theo yêu cầu, nhưng
phép lấy mẫu không phải markup: nó dùng xác suất thật của mô hình làm trọng số
cho hai số cuối, và gieo hạt tất định theo ngày mốc nên cùng một ngày luôn cho
cùng một bảng.

Giữ lại vì nó sinh ``data/predict/fun_draw_next.{json,csv}``. Hiện CHƯA ai đọc
hai tệp đó — nơi đọc duy nhất là bảng HTML đã bị xóa — nên nó đang là bộ sinh
dữ liệu không người dùng, chờ giao diện mới. Phần đã bỏ: ``_render_board``,
``_prob_badges``, ``inject_into_html``, ``FUN_CSS``, và bước chèn vào HTML
trong ``main``.

Tiền tố các giải là MÔ PHỎNG tất định, không phải xác suất do mô hình tính:
mô hình chỉ dự đoán không gian hai chữ số. Tải trọng mang
``kind="entertainment_simulation"`` để nơi đọc không thể nhầm.
"""

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
SCHEMA_VERSION = 1
PRIZE_GROUPS: list[tuple[str, str, list[str], int]] = [
    ("special", "Đặc Biệt", ["special"], 5),
    ("prize1", "Giải nhất", ["prize1"], 5),
    ("prize2", "Giải nhì", ["prize2_1", "prize2_2"], 5),
    (
        "prize3",
        "Giải ba",
        ["prize3_1", "prize3_2", "prize3_3", "prize3_4", "prize3_5", "prize3_6"],
        5,
    ),
    ("prize4", "Giải tư", ["prize4_1", "prize4_2", "prize4_3", "prize4_4"], 4),
    (
        "prize5",
        "Giải năm",
        ["prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6"],
        4,
    ),
    ("prize6", "Giải sáu", ["prize6_1", "prize6_2", "prize6_3"], 3),
    ("prize7", "Giải bảy", ["prize7_1", "prize7_2", "prize7_3", "prize7_4"], 2),
]
@dataclass(frozen=True)
class PredictionInputs:
    anchor_date: str
    target_date: str
    loto: pd.DataFrame
    de: pd.DataFrame
    picks_loto: dict[str, Any]
    picks_de: dict[str, Any]
def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))
def _prob_frame(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    if "number" not in df.columns or "prob" not in df.columns:
        raise ValueError(f"Tệp dự báo thiếu cột number/prob: {path}")
    df = df[["number", "prob"]].copy()
    df["number"] = pd.to_numeric(df["number"], errors="raise").astype(int)
    df["prob"] = pd.to_numeric(df["prob"], errors="raise").astype(float)
    df = df.drop_duplicates("number", keep="last").sort_values("number")
    if df["number"].tolist() != list(range(100)):
        raise ValueError(f"Tệp dự báo phải chứa đủ đúng miền 00..99: {path}")
    if not np.isfinite(df["prob"].to_numpy()).all():
        raise ValueError(f"Tệp có xác suất không hữu hạn: {path}")
    return df.reset_index(drop=True)
def load_prediction_inputs(data_dir: Path) -> PredictionInputs:
    pred_dir = data_dir / "predict"
    picks_loto = _read_json(pred_dir / "picks_loto.json")
    picks_de = _read_json(pred_dir / "picks_de.json")

    target_loto = str(picks_loto.get("target_date", ""))
    target_de = str(picks_de.get("target_date", ""))
    anchor_loto = str(picks_loto.get("anchor_date", ""))
    anchor_de = str(picks_de.get("anchor_date", ""))
    if not target_loto or target_loto != target_de:
        raise ValueError(f"Ngày mục tiêu LOTO/Đặc Biệt không khớp: {target_loto!r} và {target_de!r}")
    if not anchor_loto or anchor_loto != anchor_de:
        raise ValueError(f"Ngày neo LOTO/Đặc Biệt không khớp: {anchor_loto!r} và {anchor_de!r}")

    loto = _prob_frame(pred_dir / f"predict_next_loto_all_{target_loto}.csv")
    de = _prob_frame(pred_dir / f"predict_next_de_all_{target_loto}.csv")
    return PredictionInputs(
        anchor_date=anchor_loto,
        target_date=target_loto,
        loto=loto,
        de=de,
        picks_loto=picks_loto,
        picks_de=picks_de,
    )
def _normalized_sampling_weights(df: pd.DataFrame) -> np.ndarray:
    p = np.clip(df["prob"].to_numpy(dtype=float), 0.0, None)
    total = float(p.sum())
    if total <= 0:
        return np.full(100, 0.01, dtype=float)
    return p / total
def _seed_for(inputs: PredictionInputs) -> int:
    material = (
        f"fun-xsmb-v{SCHEMA_VERSION}|{inputs.anchor_date}|{inputs.target_date}|"
        f"{inputs.loto['prob'].round(12).tolist()}|{inputs.de['prob'].round(12).tolist()}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)
def _synthetic_full_number(rng: np.random.Generator, suffix: int, width: int) -> str:
    if width <= 2:
        return f"{suffix:02d}"
    prefix_width = width - 2
    prefix = int(rng.integers(0, 10**prefix_width))
    return f"{prefix:0{prefix_width}d}{suffix:02d}"
def _prob_lookup(df: pd.DataFrame) -> dict[int, float]:
    return {int(row.number): float(row.prob) for row in df.itertuples(index=False)}
def _top_candidates(df: pd.DataFrame, limit: int = 10) -> list[dict[str, Any]]:
    top = df.sort_values(["prob", "number"], ascending=[False, True]).head(limit)
    return [
        {
            "rank": i,
            "number": f"{int(row.number):02d}",
            "prob": float(row.prob),
            "prob_percent": float(row.prob) * 100.0,
        }
        for i, row in enumerate(top.itertuples(index=False), start=1)
    ]
def build_fun_draw(inputs: PredictionInputs) -> dict[str, Any]:
    seed = _seed_for(inputs)
    rng = np.random.default_rng(seed)
    loto_w = _normalized_sampling_weights(inputs.loto)
    de_w = _normalized_sampling_weights(inputs.de)
    loto_prob = _prob_lookup(inputs.loto)
    de_prob = _prob_lookup(inputs.de)

    groups: list[dict[str, Any]] = []
    flat_rows: list[dict[str, Any]] = []
    for key, label, fields, width in PRIZE_GROUPS:
        values: list[dict[str, Any]] = []
        for field in fields:
            mode = "de" if field == "special" else "loto"
            weights = de_w if mode == "de" else loto_w
            suffix = int(rng.choice(np.arange(100), p=weights))
            prob = (de_prob if mode == "de" else loto_prob)[suffix]
            value = _synthetic_full_number(rng, suffix, width)
            item = {
                "field": field,
                "value": value,
                "suffix": f"{suffix:02d}",
                "mode": mode,
                "model_prob": float(prob),
                "model_prob_percent": float(prob) * 100.0,
            }
            values.append(item)
            flat_rows.append({"prize": label, **item})
        groups.append({"key": key, "label": label, "width": width, "values": values})

    loto_meta = dict(inputs.picks_loto.get("meta") or {})
    de_meta = dict(inputs.picks_de.get("meta") or {})
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "entertainment_simulation",
        "anchor_date": inputs.anchor_date,
        "target_date": inputs.target_date,
        "seed": seed,
        "disclaimer": (
            "Dự đoán vui/mô phỏng để tham khảo. Mô hình chỉ ước lượng xác suất 2 số cuối; "
            "các chữ số tiền tố trong bảng giải đầy đủ là số tổng hợp tất định, không phải "
            "xác suất dự đoán giải 3–5 chữ số và không bảo đảm kết quả thực tế."
        ),
        "method": (
            "Đặc Biệt: lấy mẫu tất định có trọng số từ phân phối Đặc Biệt. Các giải khác: lấy mẫu tất định "
            "có trọng số từ phân phối LOTO. Tiền tố được sinh từ hạt giống cố định theo ảnh chụp "
            "dữ liệu/mô hình để cùng đầu vào luôn cho cùng một bảng mô phỏng."
        ),
        "groups": groups,
        "rows": flat_rows,
        "top_loto": _top_candidates(inputs.loto, 10),
        "top_de": _top_candidates(inputs.de, 10),
        "model_state": {
            "loto_meta_active": bool(loto_meta.get("active", False)),
            "loto_meta_trust": float(loto_meta.get("trust", 0.0) or 0.0),
            "de_meta_active": bool(de_meta.get("active", False)),
            "de_meta_trust": float(de_meta.get("trust", 0.0) or 0.0),
        },
    }
def write_artifacts(payload: dict[str, Any], data_dir: Path) -> tuple[Path, Path]:
    pred_dir = data_dir / "predict"
    pred_dir.mkdir(parents=True, exist_ok=True)
    json_path = pred_dir / "fun_draw_next.json"
    csv_path = pred_dir / "fun_draw_next.csv"

    # Replace both snapshots atomically.  A runner interruption must not leave
    # a truncated JSON/CSV pair that the next page build interprets as a stale
    # simulation.  Temporary files live beside the destination so os.replace
    # remains atomic on the same filesystem.
    json_tmp: str | None = None
    csv_tmp: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=pred_dir,
            prefix=".fun-draw-",
            suffix=".json",
            delete=False,
        ) as fh:
            json_tmp = fh.name
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=pred_dir,
            prefix=".fun-draw-",
            suffix=".csv",
            delete=False,
        ) as fh:
            csv_tmp = fh.name
            pd.DataFrame(payload["rows"]).to_csv(fh, index=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(json_tmp, json_path)
        json_tmp = None
        os.replace(csv_tmp, csv_path)
        csv_tmp = None
    finally:
        for path in (json_tmp, csv_tmp):
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
    return json_path, csv_path
def main() -> None:
    ap = argparse.ArgumentParser(description="Sinh dữ liệu mô phỏng vui XSMB cho kỳ kế tiếp.")
    ap.add_argument("--data-dir", default="data")
    args = ap.parse_args()

    # Cờ `--docs-dir` và bước chèn vào ba trang HTML đã bỏ cùng tầng trình bày.
    # Trước đây main() NÉM LỖI khi không chèn được vào trang nào; giữ lại điều
    # đó bây giờ là làm pipeline đỏ vì một việc đã bị xóa có chủ ý.
    inputs = load_prediction_inputs(Path(args.data_dir))
    payload = build_fun_draw(inputs)
    json_path, csv_path = write_artifacts(payload, Path(args.data_dir))
    print(f"[OK] mô phỏng vui cho kỳ={payload['target_date']} -> {json_path}, {csv_path}")


if __name__ == "__main__":
    main()
