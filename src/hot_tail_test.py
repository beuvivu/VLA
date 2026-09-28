"""Kiểm TIẾN CỨU giả thuyết "đuôi nóng 7 kỳ" — đăng ký trước ngày 28-09-2026.

Nguồn gốc
---------
Điều tra vì sao cả 10 con LOTO công bố cho 28-09-2026 đều đuôi 4 tìm ra đặc
trưng ``tail_freq_7d`` của mô hình cầu kèo. Soi lại lịch sử thì đuôi xuất hiện
nhiều nhất trong 7 kỳ trước về nhiều hơn trung bình các đuôi trong cùng kỳ:
đúng theo định nghĩa dưới đây, +0,456 điểm % trên 4 212 kỳ (z 2,43, p Monte
Carlo hai phía 0,011 trên 2 000 lịch sử công bằng), trong khi "đầu nóng" —
nhóm đối chứng — không có gì (+0,135 điểm %, p 0,475). Nhưng giả thuyết được đặt
SAU khi nhìn dữ liệu, và đã thử bốn độ dài cửa sổ: bằng chứng hồi cứu không đủ.

Cách duy nhất phân biệt tín hiệu thật với tín hiệu tìm ra sau khi nhìn là chấm
nó trên những kỳ CHƯA TỒN TẠI lúc đặt giả thuyết. Mọi tham số dưới đây được
chốt trước kỳ đầu tiên được chấm và KHÔNG được sửa để vừa kết quả: sửa thì phải
đăng ký một giả thuyết mới với ngày bắt đầu mới.

Thống kê cho mỗi kỳ t (từ ``FIRST_TARGET``):
    đuôi nóng = đuôi có tổng số kỳ-về của 10 con lớn nhất trong 7 kỳ trước t
                (hoà thì lấy trung bình các đuôi hoà)
    d_t       = tỉ lệ về của 10 con đuôi nóng ở kỳ t
                − tỉ lệ về trung bình của cả 10 đuôi ở kỳ t
Dưới giả thuyết công bằng E[d_t] = 0 và các kỳ độc lập. Kết luận sau
``MIN_DRAWS`` kỳ: xác nhận nếu z một phía của trung bình d_t ≥ ``Z_CRITICAL``
(α = 0,01), ngược lại bác bỏ.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd

#: Tham số ĐÃ ĐĂNG KÝ. Không sửa — xem docstring.
REGISTERED_ON = "2026-09-28"
FIRST_TARGET = "2026-09-29"
WINDOW = 7
MIN_DRAWS = 180
ALPHA = 0.01
Z_CRITICAL = 2.326  # z một phía cho α = 0,01
LEDGER = Path("hypotheses") / "hot_tail.csv"
FIELDS = ["date", "hot_tails", "hot_rate", "all_rate", "diff"]

#: Bằng chứng HỒI CỨU đã dẫn tới giả thuyết — chỉ để đối chiếu, không dùng để kết luận.
RETROSPECTIVE = {
    "draws": 4212,
    "last_draw": "2026-09-28",
    "effect_pp": 0.456,
    "z": 2.43,
    "p_two_sided_mc": 0.011,
    "control_head_effect_pp": 0.135,
    "control_head_p": 0.475,
}

PRIZES = [
    "special", "prize1", "prize2_1", "prize2_2", "prize3_1", "prize3_2", "prize3_3",
    "prize3_4", "prize3_5", "prize3_6", "prize4_1", "prize4_2", "prize4_3", "prize4_4",
    "prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6", "prize6_1",
    "prize6_2", "prize6_3", "prize7_1", "prize7_2", "prize7_3", "prize7_4",
]


def _hits(draws: np.ndarray) -> np.ndarray:
    hits = np.zeros((len(draws), 100), dtype=np.int32)
    hits[np.arange(len(draws))[:, None], draws] = 1
    return hits


def score_draw(history: np.ndarray, today: np.ndarray) -> dict:
    """Chấm MỘT kỳ: ``history`` là (≥7, 27) các kỳ trước, ``today`` là (27,)."""
    past = _hits(history[-WINDOW:]).sum(axis=0)          # số kỳ-về của từng con
    per_tail = past.reshape(10, 10).sum(axis=0)          # cột j = đuôi j
    hot = np.flatnonzero(per_tail == per_tail.max())
    hit = np.zeros(100, dtype=int)
    hit[today] = 1
    rate = hit.reshape(10, 10).mean(axis=0)              # tỉ lệ về theo đuôi
    hot_rate = float(rate[hot].mean())
    all_rate = float(rate.mean())
    return {"hot_tails": "".join(str(int(t)) for t in hot), "hot_rate": hot_rate,
            "all_rate": all_rate, "diff": hot_rate - all_rate}


def scored_draws(frame: pd.DataFrame) -> list[dict]:
    """Mọi kỳ từ ``FIRST_TARGET`` trở đi, mỗi kỳ chấm bằng 7 kỳ ngay trước nó."""
    frame = frame.sort_values("date").reset_index(drop=True)
    draws = frame[PRIZES].to_numpy().astype(int)
    rows = []
    for t in range(WINDOW, len(frame)):
        day = str(frame["date"].iloc[t])[:10]
        if day < FIRST_TARGET:
            continue
        rows.append({"date": day, **score_draw(draws[t - WINDOW : t], draws[t])})
    return rows


def update_ledger(data_dir: Path) -> Path:
    """Ghi các kỳ mới vào sổ cái. Kỳ đã ghi thì giữ nguyên, không bị đè."""
    path = data_dir / LEDGER
    known: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            known = {row["date"]: row for row in csv.DictReader(fh)}
    frame = pd.read_csv(data_dir / "xsmb-2-digits.csv", dtype={"date": str})
    for row in scored_draws(frame):
        known.setdefault(row["date"], {k: row[k] for k in FIELDS})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for day in sorted(known):
            writer.writerow({k: known[day][k] for k in FIELDS})
    return path


def evaluate(data_dir: Path) -> dict:
    """Trạng thái phép kiểm tiến cứu từ sổ cái."""
    path = data_dir / LEDGER
    diffs = []
    first = last = None
    if path.exists():
        ledger = pd.read_csv(path, dtype={"date": str, "hot_tails": str})
        diffs = ledger["diff"].astype(float).tolist()
        if len(ledger):
            first, last = str(ledger["date"].iloc[0]), str(ledger["date"].iloc[-1])
    n = len(diffs)
    mean = float(np.mean(diffs)) if n else 0.0
    se = float(np.std(diffs, ddof=1) / math.sqrt(n)) if n > 1 else 0.0
    z = mean / se if se > 0 else 0.0
    if n < MIN_DRAWS:
        state = "dang_thu"
    elif z >= Z_CRITICAL:
        state = "xac_nhan"
    else:
        state = "bac_bo"
    return {
        "registered_on": REGISTERED_ON, "first_target": FIRST_TARGET, "window": WINDOW,
        "min_draws": MIN_DRAWS, "alpha": ALPHA, "z_critical": Z_CRITICAL,
        "draws": n, "first": first, "last": last,
        "mean_diff": mean, "stderr": se, "z": z, "state": state,
        "retrospective": RETROSPECTIVE,
    }
