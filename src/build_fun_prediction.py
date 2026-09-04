from __future__ import annotations

"""Dựng và chèn bảng mô phỏng XSMB tất định cho ngày kế tiếp.

The production models predict only the two-digit Loto/ĐB universe.  This module
turns those probabilities into a clearly-labelled entertainment simulation of a
full XSMB prize board while preserving the model probabilities as the auditable
part of the output.  Prefix digits are synthetic and must never be interpreted as
modelled five-/four-/three-digit prize probabilities.
"""

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup


SCHEMA_VERSION = 1
STYLE_ID = "fun-prediction-style"
BLOCK_ID = "du-doan-vui"

PRIZE_GROUPS: list[tuple[str, str, list[str], int]] = [
    ("special", "Đặc biệt", ["special"], 5),
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
        raise ValueError(f"Ngày mục tiêu lô tô/ĐB không khớp: {target_loto!r} và {target_de!r}")
    if not anchor_loto or anchor_loto != anchor_de:
        raise ValueError(f"Ngày neo lô tô/ĐB không khớp: {anchor_loto!r} và {anchor_de!r}")

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
            "ĐB: lấy mẫu tất định có trọng số từ phân phối ĐB. Các giải khác: lấy mẫu tất định "
            "có trọng số từ phân phối lô tô. Tiền tố được sinh từ hạt giống cố định theo ảnh chụp "
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


def _prob_badges(rows: list[dict[str, Any]], mode: str, label: str) -> str:
    items: list[str] = []
    for row in rows:
        n = html.escape(str(row["number"]))
        pct = float(row["prob_percent"])
        width = max(4.0, min(100.0, pct * (4.0 if mode == "de" else 1.0)))
        items.append(
            "<button class='fun-prob-row' "
            f"data-mode='{mode}' data-number='{n}' title='{label} {n}: {pct:.3f}%'>"
            f"<span class='fun-rank'>#{int(row['rank'])}</span>"
            f"<b>{n}</b>"
            "<span class='fun-prob-track'>"
            f"<i style='width:{width:.1f}%'></i>"
            "</span>"
            f"<strong>{pct:.3f}%</strong>"
            "</button>"
        )
    return "".join(items)


def _render_board(payload: dict[str, Any]) -> str:
    rows: list[str] = []
    for group in payload["groups"]:
        values = []
        for item in group["values"]:
            cls = " fun-special" if item["mode"] == "de" else ""
            values.append(
                f"<button class='fun-prize-number{cls}' data-mode='{item['mode']}' "
                f"data-number='{html.escape(item['suffix'])}' "
            f"title='2 số cuối {html.escape(item['suffix'])} · xác suất mô hình {float(item['model_prob_percent']):.3f}%'>"
                f"{html.escape(item['value'])}</button>"
            )
        rows.append(
            f"<tr><th>{html.escape(group['label'])}</th>"
            f"<td><div class='fun-prize-list'>{''.join(values)}</div></td></tr>"
        )

    state = payload["model_state"]
    loto_state = (
        f"ML xếp chồng đang bật · độ tin cậy {float(state['loto_meta_trust']) * 100:.0f}%"
        if state["loto_meta_active"]
        else "Mô hình tổ hợp tuyến tính / phương án dự phòng của cổng ML"
    )
    de_state = (
        f"ML xếp chồng đang bật · độ tin cậy {float(state['de_meta_trust']) * 100:.0f}%"
        if state["de_meta_active"]
        else "Mô hình tổ hợp tuyến tính / phương án dự phòng của cổng ML"
    )

    return f"""
<div id="{BLOCK_ID}" class="fun-prediction-block">
  <div class="fun-prediction-head">
    <div>
      <div class="fun-eyebrow">🎲 Dự đoán vui · ngày kế tiếp</div>
      <h3>Bảng mô phỏng XSMB {html.escape(str(payload['target_date']))}</h3>
      <p>Đặt ngay dưới kết quả thực ngày {html.escape(str(payload['anchor_date']))}. Chỉ phần <b>2 số cuối</b> dùng xác suất từ mô hình; tiền tố giải là mô phỏng tất định.</p>
    </div>
    <span class="fun-warning">Không phải kết quả thật</span>
  </div>
  <div class="fun-pred-grid">
    <div class="fun-board-wrap">
      <table class="fun-result-table"><tbody>{''.join(rows)}</tbody></table>
      <p class="fun-method">{html.escape(str(payload['method']))}</p>
    </div>
    <div class="fun-prob-panels">
      <article class="fun-prob-card">
        <div class="fun-prob-title"><span>Lô tô ngày mai</span><small>{html.escape(loto_state)}</small></div>
        <div class="fun-prob-list">{_prob_badges(payload['top_loto'], 'loto', 'Lô tô')}</div>
      </article>
      <article class="fun-prob-card de">
        <div class="fun-prob-title"><span>Đặc biệt ngày mai</span><small>{html.escape(de_state)}</small></div>
        <div class="fun-prob-list">{_prob_badges(payload['top_de'], 'de', 'ĐB')}</div>
      </article>
    </div>
  </div>
  <div class="fun-disclaimer">⚠ {html.escape(str(payload['disclaimer']))}</div>
</div>
"""


FUN_CSS = r"""
#du-doan-vui.fun-prediction-block {
  margin-top: 20px;
  padding: 18px;
  border: 1px solid #fed7aa;
  border-radius: 22px;
  background: linear-gradient(180deg, #fffaf5, #ffffff);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
}
.fun-prediction-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.fun-prediction-head h3 { margin: 3px 0 5px; font-size: 20px; }
.fun-prediction-head p { margin: 0; color: #64748b; font-size: 13px; line-height: 1.5; }
.fun-eyebrow { color: #c2410c; font-size: 11px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }
.fun-warning {
  white-space: nowrap;
  padding: 7px 10px;
  border-radius: 999px;
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fed7aa;
  font-size: 11px;
  font-weight: 900;
}
.fun-pred-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(300px, .85fr); gap: 16px; align-items: start; }
.fun-board-wrap { min-width: 0; overflow-x: auto; }
.fun-result-table { width: 100%; min-width: 520px; border-collapse: separate; border-spacing: 0; border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden; background: #fff; }
.fun-result-table th { width: 112px; padding: 11px 12px; text-align: left; background: #fff7ed; color: #7c2d12; border-bottom: 1px solid #e2e8f0; font-size: 12px; }
.fun-result-table td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }
.fun-result-table tr:last-child th, .fun-result-table tr:last-child td { border-bottom: 0; }
.fun-prize-list { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
.fun-prize-number { border: 0; border-radius: 11px; min-width: 62px; padding: 7px 9px; cursor: pointer; background: #f8fafc; color: #0f172a; font-weight: 900; letter-spacing: .03em; }
.fun-prize-number:hover { background: #e2e8f0; }
.fun-prize-number.fun-special { background: #fff1f2; color: #be123c; font-size: 19px; min-width: 92px; }
.fun-method { margin: 9px 2px 0; color: #94a3b8; font-size: 11px; line-height: 1.45; }
.fun-prob-panels { display: grid; gap: 12px; }
.fun-prob-card { padding: 13px; border-radius: 16px; background: #f5f3ff; border: 1px solid #ddd6fe; }
.fun-prob-card.de { background: #fff7ed; border-color: #fed7aa; }
.fun-prob-title { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; margin-bottom: 9px; }
.fun-prob-title span { font-size: 13px; font-weight: 900; color: #4c1d95; }
.fun-prob-card.de .fun-prob-title span { color: #9a3412; }
.fun-prob-title small { color: #64748b; text-align: right; font-size: 10px; line-height: 1.35; }
.fun-prob-list { display: grid; gap: 6px; }
.fun-prob-row { display: grid; grid-template-columns: 28px 30px minmax(70px, 1fr) 67px; gap: 7px; align-items: center; width: 100%; padding: 6px 7px; border: 0; border-radius: 10px; background: rgba(255,255,255,.82); cursor: pointer; color: #0f172a; }
.fun-rank { color: #94a3b8; font-size: 10px; font-weight: 800; }
.fun-prob-row b { font-size: 14px; }
.fun-prob-row strong { text-align: right; font-size: 11px; font-variant-numeric: tabular-nums; }
.fun-prob-track { height: 7px; overflow: hidden; border-radius: 99px; background: #e2e8f0; }
.fun-prob-track i { display: block; height: 100%; min-width: 3px; border-radius: inherit; background: linear-gradient(90deg, #8b5cf6, #2563eb); }
.fun-prob-card.de .fun-prob-track i { background: linear-gradient(90deg, #fb923c, #e11d48); }
.fun-disclaimer { margin-top: 12px; padding: 10px 12px; border-radius: 13px; background: #fffbeb; border: 1px solid #fde68a; color: #92400e; font-size: 11px; line-height: 1.5; }
@media (max-width: 900px) {
  .fun-pred-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  #du-doan-vui.fun-prediction-block { padding: 13px; border-radius: 18px; }
  .fun-prediction-head { display: block; }
  .fun-warning { display: inline-flex; margin-top: 9px; }
  .fun-prob-row { grid-template-columns: 26px 28px minmax(58px, 1fr) 62px; }
}
"""


def inject_into_html(path: Path, payload: dict[str, Any]) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    target = soup.select_one("section#ket-qua")
    if target is None:
        raise RuntimeError(f"Không tìm thấy section#ket-qua trong {path}")

    old_block = soup.find(id=BLOCK_ID)
    if old_block is not None:
        old_block.decompose()
    old_style = soup.find(id=STYLE_ID)
    if old_style is not None:
        old_style.decompose()

    style = soup.new_tag("style", id=STYLE_ID)
    style.string = FUN_CSS
    if soup.head is None:
        raise RuntimeError(f"Thiếu thẻ <head> trong {path}")
    soup.head.append(style)

    fragment = BeautifulSoup(_render_board(payload), "html.parser")
    block = fragment.find(id=BLOCK_ID)
    if block is None:
        raise RuntimeError("Không dựng được khối HTML mô phỏng vui")
    target.append(block)
    rendered = "\n".join(line.rstrip() for line in str(soup).splitlines()) + "\n"
    path.write_text(rendered, encoding="utf-8")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Dựng và chèn bảng mô phỏng vui XSMB ngày kế tiếp.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--docs-dir", default="docs")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    docs_dir = Path(args.docs_dir)
    inputs = load_prediction_inputs(data_dir)
    payload = build_fun_draw(inputs)
    json_path, csv_path = write_artifacts(payload, data_dir)

    injected: list[str] = []
    for name in ("index.html", "landing.html", "landing_desktop.html"):
        path = docs_dir / name
        if inject_into_html(path, payload):
            injected.append(str(path))

    if not injected:
        raise RuntimeError("Không có trang HTML tổng hợp để chèn bảng mô phỏng vui")

    print(
        f"[OK] mô phỏng vui cho ngày={payload['target_date']} -> {json_path}, {csv_path}; "
        f"đã chèn={', '.join(injected)}"
    )


if __name__ == "__main__":
    main()
