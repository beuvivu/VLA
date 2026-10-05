"""Phương pháp "tổng – bóng – chạm" học từ chuyên mục bài dự đoán XSMB tham chiếu.

Chủ dự án yêu cầu (05-10-2026) đọc kỹ các bài trong chuyên mục, học cách phân
tích của từng bài và hệ thống hoá thành thuật toán riêng. Đã đọc trọn 10 bài
(28-09 → 05-10-2026) qua ``.github/workflows/inspect-reference-articles.yml``.

Hai loạt bài, hai mức tái lập được:

* **Loạt bài tuần** viết rõ công thức, và mọi con số in trong bài tính lại
  ĐÚNG từ bảng kết quả của kho (ghim trong ``tests/test_digit_sum_rules.py``).
  Đó là năm quy tắc dưới đây.
* **Loạt bài hằng ngày** gọi tên phương pháp ("bạch thủ theo cầu chạy 7 ngày",
  "lô rơi liên tiếp 3 ngày") nhưng con số in ra KHÔNG khớp chính phương pháp ấy
  khi tính lại; đầu – đuôi đề của 7 bài không khớp bất kỳ luật tổng hai vị trí
  cố định nào. Phần ấy không tái lập được nên không thành quy tắc ở đây —
  ``documentation/research/2026-10-05-phuong-phap-bai-du-doan.md`` ghi chi tiết.

Mọi quy tắc đọc ĐÚNG MỘT kỳ gốc và chỉ dùng tổng hai chữ số (mod 10) và bóng
(x ↔ x + 5 mod 10). Kiểm lịch sử (``backtest``) chấm mỗi quy tắc trên từng kỳ
kế tiếp với xác suất trúng chính xác của một bộ số cùng cỡ chọn ngẫu nhiên.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from xsmb_domain import FIELD_WIDTHS, LOTO_DRAWS_PER_DAY

#: Thứ tự giải đúng như bảng kết quả, kèm số chữ số của mỗi giải.
_WIDTH = dict(FIELD_WIDTHS)


def bong(digit: int) -> int:
    """Bóng dương – âm: 0↔5, 1↔6, 2↔7, 3↔8, 4↔9."""
    return (int(digit) + 5) % 10


def tong(text: str) -> int:
    """Tổng các chữ số, lấy hàng đơn vị (``"82"`` → 0, ``"35"`` → 8)."""
    return sum(int(c) for c in text) % 10


def giai(row: pd.Series, field: str) -> str:
    """Chuỗi chữ số đủ độ dài của một giải (``566`` của G5 → ``"0566"``)."""
    return f"{int(row[field]):0{_WIDTH[field]}d}"


def cap_lon(x: int, y: int) -> list[int]:
    """Cặp lộn ``xy`` và ``yx`` (bài viết ghi ``xyx``, ví dụ ``676`` = 67 và 76)."""
    return sorted({10 * x + y, 10 * y + x})


@dataclass(frozen=True)
class Rule:
    """Một quy tắc: tên, loại đích, và hàm từ kỳ gốc ra bộ số/chữ số."""

    key: str
    label: str
    target: str  # "dau_db" | "duoi_db" | "db" | "loto"
    make: Callable[[pd.Series], list[int]]
    formula: str


def dau_db(row: pd.Series) -> list[int]:
    """Đầu Đặc Biệt: tổng 2 số CUỐI giải Đặc Biệt, kèm bóng."""
    t = tong(giai(row, "special")[-2:])
    return sorted({t, bong(t)})


def duoi_db(row: pd.Series) -> list[int]:
    """Đuôi Đặc Biệt: tổng 2 số ĐẦU giải Đặc Biệt, kèm bóng."""
    t = tong(giai(row, "special")[:2])
    return sorted({t, bong(t)})


def cham(row: pd.Series) -> list[int]:
    """Chạm: tổng 2 số cuối giải nhất, kèm bóng."""
    t = tong(giai(row, "prize1")[-2:])
    return sorted({t, bong(t)})


def dan_cham(row: pd.Series) -> list[int]:
    """Dàn đề chạm: mỗi chạm ghép thẳng và lộn với 3 số đầu Đặc Biệt cùng bóng của chúng.

    Ví dụ kỳ 04-10-2026: chạm 8 và 3; ba số đầu 829 cùng bóng 374 cho 8x/x8 và
    3x/x3 với x ∈ {8, 2, 9, 3, 7, 4}.
    """
    digits = {int(c) for c in giai(row, "special")[:3]}
    digits |= {bong(d) for d in digits}
    out: set[int] = set()
    for c in cham(row):
        for d in digits:
            out.update(cap_lon(c, d))
    return sorted(out)


def lo_g5(row: pd.Series) -> list[int]:
    """Lô cặp: tổng 2 số đầu G5.2 ghép tổng 2 số cuối G5.4, lấy cả lộn."""
    return cap_lon(tong(giai(row, "prize5_2")[:2]), tong(giai(row, "prize5_4")[-2:]))


def lo_vip(row: pd.Series) -> list[int]:
    """Song thủ lô: tổng 2 số cuối G2.1 ghép tổng 2 số đầu giải nhất, lấy cả lộn."""
    return cap_lon(tong(giai(row, "prize2_1")[-2:]), tong(giai(row, "prize1")[:2]))


RULES: tuple[Rule, ...] = (
    Rule("dau_db", "Đầu Đặc Biệt", "dau_db", dau_db,
         "tổng 2 số cuối Đặc Biệt và bóng"),
    Rule("duoi_db", "Đuôi Đặc Biệt", "duoi_db", duoi_db,
         "tổng 2 số đầu Đặc Biệt và bóng"),
    Rule("dan_cham", "Dàn đề chạm", "db", dan_cham,
         "chạm = tổng 2 số cuối giải nhất và bóng; ghép thẳng/lộn với 3 số đầu Đặc Biệt và bóng"),
    Rule("lo_g5", "Lô cặp G5", "loto", lo_g5,
         "tổng 2 số đầu G5.2 ghép tổng 2 số cuối G5.4, lấy lộn"),
    Rule("lo_vip", "Song thủ lô G2–G1", "loto", lo_vip,
         "tổng 2 số cuối G2.1 ghép tổng 2 số đầu giải nhất, lấy lộn"),
)


def tong_hop_ky(row: pd.Series) -> dict:
    """Các "điểm nhấn" mà mọi bài dùng để tóm tắt kỳ trước.

    Đề đầu/đuôi/tổng; lô kép; lô về ≥ 2 nháy; cặp lô về cả hai chiều (bài ghi
    ``xyx``); đầu, đuôi không về con nào (câm); đầu, đuôi về nhiều nhất.
    """
    special = giai(row, "special")[-2:]
    lotos = [int(row[field]) % 100 for field, _ in FIELD_WIDTHS]
    counts = np.bincount(lotos, minlength=100)
    present = {n for n in range(100) if counts[n]}
    heads = np.bincount([n // 10 for n in lotos], minlength=10)
    tails = np.bincount([n % 10 for n in lotos], minlength=10)
    return {
        "de": special,
        "de_dau": int(special[0]),
        "de_duoi": int(special[1]),
        "de_tong": tong(special),
        "lo_kep": sorted(n for n in present if n // 10 == n % 10),
        "lo_nhay": {f"{n:02d}": int(counts[n]) for n in range(100) if counts[n] >= 2},
        "lo_ca_cap": sorted(n for n in present if n // 10 < n % 10 and (n % 10) * 10 + n // 10 in present),
        "cam_dau": [d for d in range(10) if heads[d] == 0],
        "cam_duoi": [d for d in range(10) if tails[d] == 0],
        "dau_nhieu_nhat": [d for d in range(10) if heads[d] == heads.max()],
        "duoi_nhieu_nhat": [d for d in range(10) if tails[d] == tails.max()],
    }


def _hit_and_chance(rule: Rule, picks: list[int], nxt: pd.Series) -> tuple[bool, float]:
    """Trúng hay không ở kỳ kế, và xác suất trúng của một bộ ngẫu nhiên cùng cỡ."""
    k = len(picks)
    special = int(nxt["special"]) % 100
    if rule.target == "dau_db":
        return special // 10 in picks, k / 10
    if rule.target == "duoi_db":
        return special % 10 in picks, k / 10
    if rule.target == "db":
        return special in picks, k / 100
    lotos = {int(nxt[field]) % 100 for field, _ in FIELD_WIDTHS}
    return bool(lotos & set(picks)), 1.0 - (1.0 - k / 100) ** LOTO_DRAWS_PER_DAY


def backtest(raw: pd.DataFrame) -> list[dict]:
    """Chấm mỗi quy tắc: kỳ gốc t → kỳ t+1, trên toàn bộ lịch sử.

    ``expected`` cộng xác suất trúng chính xác của một bộ ngẫu nhiên cùng cỡ ở
    từng kỳ (bộ đổi cỡ khi có số kép), nên z so đúng với "chọn bừa".
    """
    raw = raw.sort_values("date").reset_index(drop=True)
    rows = [raw.iloc[i] for i in range(len(raw))]
    out = []
    for rule in RULES:
        hits = 0
        expected = 0.0
        variance = 0.0
        for t in range(len(rows) - 1):
            hit, p = _hit_and_chance(rule, rule.make(rows[t]), rows[t + 1])
            hits += int(hit)
            expected += p
            variance += p * (1.0 - p)
        n = len(rows) - 1
        out.append({
            "rule": rule.key,
            "label": rule.label,
            "formula": rule.formula,
            "draws": n,
            "hits": hits,
            "hit_rate": hits / n,
            "expected_rate": expected / n,
            "z": (hits - expected) / sqrt(variance) if variance > 0 else 0.0,
        })
    return out


#: Khung áp dụng theo đúng loạt bài tuần: kỳ gốc (thứ, 0 = thứ Hai) → các thứ
#: của kỳ được chấm. Chủ Nhật mở khung đầu tuần, thứ Năm mở khung cuối tuần.
FRAMES: dict[str, dict[int, tuple[int, ...]]] = {
    "dau_db": {6: (0, 1, 2, 3, 4, 5, 6)},
    "duoi_db": {6: (0, 1, 2, 3, 4, 5, 6)},
    "dan_cham": {6: (0, 1, 2, 3), 3: (4, 5, 6)},
    "lo_g5": {6: (0, 1), 3: (4, 5, 6)},
    "lo_vip": {6: (0,), 3: (4,)},
}


def frame_backtest(raw: pd.DataFrame) -> list[dict]:
    """Chấm kiểu bài viết: "nổ" nếu trúng ÍT NHẤT MỘT lần trong cả khung.

    Khung dài làm tỉ lệ "nổ" cao dù quy tắc không có kỹ năng: hai chữ số đầu
    Đặc Biệt trong 7 kỳ "nổ" với xác suất 1 − 0,8⁷ ≈ 79%. ``expected_rate`` là
    xác suất ấy của một bộ ngẫu nhiên cùng cỡ, tính kỳ theo kỳ.
    """
    raw = raw.sort_values("date").reset_index(drop=True)
    dates = pd.to_datetime(raw["date"])
    rows = [raw.iloc[i] for i in range(len(raw))]
    by_key = {rule.key: rule for rule in RULES}
    out = []
    for key, frames in FRAMES.items():
        rule = by_key[key]
        n = hits = 0
        expected = variance = 0.0
        for t in range(len(rows) - 1):
            days = frames.get(int(dates[t].weekday()))
            if days is None:
                continue
            picks = rule.make(rows[t])
            miss_all, hit_any, span = 1.0, False, 0
            for u in range(t + 1, min(t + 8, len(rows))):
                gap = (dates[u] - dates[t]).days
                if gap > 7 or int(dates[u].weekday()) not in days:
                    continue
                span += 1
                hit, p = _hit_and_chance(rule, picks, rows[u])
                hit_any |= hit
                miss_all *= 1.0 - p
            if span == 0:
                continue
            n += 1
            hits += int(hit_any)
            expected += 1.0 - miss_all
            variance += (1.0 - miss_all) * miss_all
        out.append({
            "rule": key,
            "label": rule.label,
            "frames": n,
            "hits": hits,
            "hit_rate": hits / n if n else 0.0,
            "expected_rate": expected / n if n else 0.0,
            "z": (hits - expected) / sqrt(variance) if variance > 0 else 0.0,
        })
    return out


def next_picks(raw: pd.DataFrame) -> dict:
    """Bộ số mỗi quy tắc báo cho kỳ kế tiếp, từ kỳ cuối của lịch sử."""
    last = raw.sort_values("date").iloc[-1]
    return {
        "base_date": str(last["date"])[:10],
        "tong_hop": tong_hop_ky(last),
        "picks": {rule.key: rule.make(last) for rule in RULES},
        "cham": cham(last),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default="data/xsmb.csv")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    raw = pd.read_csv(args.data)
    report = {"backtest": backtest(raw), "frames": frame_backtest(raw), "next": next_picks(raw)}
    text = json.dumps(report, ensure_ascii=False, indent=2, default=int)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
