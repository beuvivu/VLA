"""Kiểm TIẾN CỨU năm quy tắc "tổng – bóng – chạm" — đăng ký ngày 05-10-2026.

Vì sao cần
----------
Năm quy tắc trong ``digit_sum_rules`` được học từ loạt bài tuần SAU khi chúng đã
được viết ra, và kiểm hồi cứu trên 4 225 kỳ không quy tắc nào hơn chọn bừa (p
Holm nhỏ nhất 0,966). Hồi cứu không bao giờ bác hẳn được câu "dạo này cầu chạy":
cách duy nhất là chấm trên những kỳ CHƯA TỒN TẠI lúc chốt quy tắc. Đây là phần
"tự học tích luỹ" của hệ: mỗi lượt pipeline ghi bộ số mỗi quy tắc báo cho từng
kỳ mới vào sổ cái, chấm với kết quả thật, và bằng chứng cộng dồn theo ngày.

Mọi tham số dưới đây chốt trước kỳ đầu tiên được chấm và KHÔNG được sửa để vừa
kết quả: sửa thì đăng ký giả thuyết mới với ngày bắt đầu mới (như
``hot_tail_test``). Quy tắc nào được XÁC NHẬN cũng không tự vào tổ hợp xác suất:
nó vẫn phải qua ``scripts/benchmark_probability_models.py`` và thắng cả hằng số
lẫn mô hình đang chạy.

Thống kê, mỗi quy tắc r và mỗi kỳ t từ ``FIRST_TARGET``:
    bộ số    = quy tắc r đọc kỳ quay ngay trước t
    trúng_t  = bộ số có về ở kỳ t (LOTO: về ở bất kỳ giải nào; Đặc Biệt: 2 số
               cuối; đầu/đuôi: chữ số hàng chục/đơn vị của 2 số cuối)
    p_t      = xác suất một bộ ngẫu nhiên CÙNG CỠ trúng ở đúng kỳ t
Dưới giả thuyết công bằng, số kỳ trúng theo phân phối Poisson-nhị thức(p_t).
Sau ``MIN_DRAWS`` kỳ: p một phía P(X ≥ trúng), hiệu chỉnh Holm cho năm quy tắc;
xác nhận quy tắc nào có p Holm ≤ ``ALPHA``.

Kết luận chỉ dùng ĐÚNG ``MIN_DRAWS`` kỳ đầu từ ``FIRST_TARGET`` rồi đóng băng. Sổ
vẫn ghi tiếp, nhưng tính lại kết luận mỗi ngày trên sổ dài dần là nhìn nhiều lần:
một quy tắc bác bỏ ở kỳ 180 có thể "xác nhận" ở kỳ 230 do may, và α = 0,01 không
còn giữ.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pandas as pd

import digit_sum_rules as dsr
from atomic_io import atomic_write_text

#: Tham số ĐÃ ĐĂNG KÝ. Không sửa — xem docstring.
REGISTERED_ON = "2026-10-05"
FIRST_TARGET = "2026-10-06"
MIN_DRAWS = 180
ALPHA = 0.01
LEDGER = Path("hypotheses") / "digit_sum_rules.csv"
FIELDS = ["date", "rule", "base_date", "picks", "hit", "chance"]

#: Bằng chứng HỒI CỨU (01-01-2015 → 05-10-2026) — chỉ để đối chiếu, không dùng
#: để kết luận. Nguồn: ``data/research/digit_sum_rules.json``.
RETROSPECTIVE = {
    "draws": 4225,
    "last_draw": "2026-10-05",
    "hit_rate": {"dau_db": 0.2054, "duoi_db": 0.1976, "dan_cham": 0.1806,
                 "lo_g5": 0.4005, "lo_vip": 0.3983},
    "expected_rate": {"dau_db": 0.2000, "duoi_db": 0.2000, "dan_cham": 0.1760,
                      "lo_g5": 0.4033, "lo_vip": 0.4025},
    "min_p_holm": 0.966,
}


def scored_draws(raw: pd.DataFrame) -> list[dict]:
    """Mọi cặp (kỳ, quy tắc) từ ``FIRST_TARGET``, mỗi kỳ chấm bằng kỳ ngay trước nó."""
    raw = raw.sort_values("date").reset_index(drop=True)
    rows = []
    for t in range(1, len(raw)):
        day = str(raw["date"].iloc[t])[:10]
        if day < FIRST_TARGET:
            continue
        base, today = raw.iloc[t - 1], raw.iloc[t]
        for rule in dsr.RULES:
            picks = rule.make(base)
            hit, chance = dsr.hit_and_chance(rule, picks, today)
            width = 1 if rule.target in ("dau_db", "duoi_db") else 2
            rows.append({
                "date": day,
                "rule": rule.key,
                "base_date": str(base["date"])[:10],
                "picks": " ".join(f"{n:0{width}d}" for n in picks),
                "hit": int(hit),
                "chance": repr(float(chance)),
            })
    return rows


def update_ledger(data_dir: Path) -> Path:
    """Ghi các kỳ mới vào sổ cái. Dòng đã ghi giữ nguyên, không bị đè."""
    path = data_dir / LEDGER
    known: dict[tuple[str, str], dict] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            known = {(row["date"], row["rule"]): row for row in csv.DictReader(fh)}
    raw = pd.read_csv(data_dir / "xsmb.csv", dtype={"date": str})
    for row in scored_draws(raw):
        known.setdefault((row["date"], row["rule"]), row)
    order = {rule.key: i for i, rule in enumerate(dsr.RULES)}
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for key in sorted(known, key=lambda k: (k[0], order.get(k[1], 99))):
        writer.writerow({field: known[key][field] for field in FIELDS})
    atomic_write_text(path, buffer.getvalue())
    return path


def evaluate(data_dir: Path) -> dict:
    """Trạng thái phép kiểm tiến cứu từ sổ cái, kèm bộ số cho kỳ kế tiếp."""
    path = data_dir / LEDGER
    ledger = (
        pd.read_csv(path, dtype={"date": str, "picks": str}) if path.exists()
        else pd.DataFrame(columns=FIELDS)
    )
    dates = sorted(ledger["date"].unique()) if len(ledger) else []
    frozen = set(dates[:MIN_DRAWS])
    rules = []
    for rule in dsr.RULES:
        part = ledger[(ledger["rule"] == rule.key) & ledger["date"].isin(frozen)]
        n = len(part)
        chances = part["chance"].astype(float).tolist()
        hits = int(part["hit"].astype(int).sum()) if n else 0
        rules.append({"rule": rule.key, "label": rule.label, "formula": rule.formula,
                      "draws": n, **dsr.verdict(n, hits, chances)})
    dsr.with_holm(rules)
    draws = min((r["draws"] for r in rules), default=0)
    for r in rules:
        if draws < MIN_DRAWS:
            r["state"] = "dang_thu"
        elif r["p_holm"] <= ALPHA:
            r["state"] = "xac_nhan"
        else:
            r["state"] = "bac_bo"
    states = {r["state"] for r in rules}
    state = ("dang_thu" if "dang_thu" in states
             else "xac_nhan" if "xac_nhan" in states else "bac_bo")
    raw_path = data_dir / "xsmb.csv"
    upcoming = dsr.next_picks(pd.read_csv(raw_path, dtype={"date": str})) if raw_path.exists() else None
    return {
        "registered_on": REGISTERED_ON, "first_target": FIRST_TARGET,
        "min_draws": MIN_DRAWS, "alpha": ALPHA,
        "draws": draws, "recorded": len(dates),
        "first": dates[0] if dates else None,
        "last": dates[min(len(dates), MIN_DRAWS) - 1] if dates else None,
        "rules": rules, "state": state, "next": upcoming,
        "retrospective": RETROSPECTIVE,
    }
