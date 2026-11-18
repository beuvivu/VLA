"""Thống kê và kiểm định ngẫu nhiên cho TỪNG ĐÀI miền Trung / miền Nam.

Trước module này dữ liệu XSMT/XSMN chỉ được in thành bảng kết quả: không mức nền, không kiểm định,
không kiểm chất lượng ngoài "đủ 18 giá trị". Module trả lời ba câu, theo thứ tự:

1. **Dữ liệu có sạch không** (`quality_report`): cấu trúc 18 giải, khoá trùng, ngày lịch không có
   kỳ, đài vắng mặt so với lịch tuần của chính nó, kỳ chép nhầm (trùng khít kỳ trước hay đài khác).
   Lỗi CẤU TRÚC dừng hẳn bước thống kê — dữ liệu hỏng không được đi vào phép tính nào.
2. **Con số nào ra bao nhiêu** (`frequency_table`): mô tả, kèm mức kỳ vọng và p của CHÍNH con số ấy.
3. **Đài có quay khác một máy công bằng không** (`station_battery`): mỗi đài là một bộ lồng cầu
   riêng nên được kiểm RIÊNG, phân phối null lấy bằng mô phỏng đúng cấu trúc 18 giải, rồi hiệu
   chỉnh đa kiểm trên mọi (đài × phép kiểm) của miền.

Một đài quay mỗi tuần một kỳ, nên một năm dữ liệu chỉ là ~58 kỳ mỗi đài. Bản tóm tắt in luôn độ
lệch NHỎ NHẤT phát hiện được ở cỡ mẫu ấy (`detectable`): "không thấy lệch" chỉ có nghĩa trong
phạm vi con số đó, không phải bằng chứng đài quay đều tuyệt đối.

Không gộp các đài thành một chuỗi: hai đài cùng ngày là hai máy khác nhau, và ghép kỳ của chúng
thành "hôm trước → hôm sau" là nối những kỳ không liên quan.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from core.atomic_io import atomic_to_csv, atomic_write_text
from core.paths import REPO_ROOT
from core.regional_domain import (
    CAGE_NAMES,
    CAGE_OF_DIGIT,
    CAGES,
    DE_BASELINE_RATE,
    LOTO_BASELINE_RATE,
    LOTO_DRAWS_PER_STATION,
    NUMBER_SPACE,
    PAIR_COOCCURRENCE_RATE,
    REGIONS,
    SLOT_WIDTHS,
    SLOTS,
    SPECIAL_SLOT,
    TOTAL_DIGITS,
    distinct_count_distribution,
)
from stats import randomness_battery as battery
from stats.statistical_corrections import benjamini_hochberg

SCHEMA_VERSION = 1
#: Số kỳ gần nhất của MỘT đài cho cột "gần đây". Theo kỳ của đài, không theo ngày lịch: đài quay
#: mỗi tuần một kỳ thì 20 kỳ là 20 tuần, và cửa sổ "30 ngày" chỉ chứa 4 kỳ.
RECENT_DRAWS = 20
#: Sàn của p mô phỏng là 1/(SIMULATIONS + 1). Miền Nam có 21 đài × 8 phép = 168 ô: để MỘT ô lệch
#: đơn lẻ còn qua được Benjamini–Hochberg (cần p ≤ 0,05/168 ≈ 3·10⁻⁴) thì phải ≥ 3 400 lần.
SIMULATIONS = 5000
SEED = 20261116
ALPHA = 0.05
#: Đài có ít kỳ hơn mức này chưa được kiểm định (khoảng cách, tương quan hai nửa đều vô nghĩa).
MIN_DRAWS_FOR_TESTS = 30
OUT_DIR = Path("stats") / "regional"
_SLOT_INDEX = {slot: index for index, slot in enumerate(SLOTS)}
_DIGIT_OFFSETS = np.concatenate([[0], np.cumsum(SLOT_WIDTHS)])
_CAGE_OF_DIGIT = np.array(CAGE_OF_DIGIT)
#: (6, 82): hàng ``c`` chọn các vị trí chữ số in thuộc lồng ``c``.
_CAGE_MEMBERSHIP = (np.arange(CAGES)[:, None] == _CAGE_OF_DIGIT[None, :]).astype(np.int64)
#: Số lồng của phép kiểm theo lồng: năm lồng thấp, mỗi lồng được ≥ 12 giải rút mỗi kỳ. Lồng trăm
#: nghìn chỉ có MỘT lần rút mỗi kỳ (giải Đặc Biệt): quá ít để đuôi χ² còn đúng, và đã có phép kiểm
#: theo vị trí in phủ nó.
MAIN_CAGES = 5


class RegionalDataError(ValueError):
    """Dữ liệu miền sai CẤU TRÚC: không phép thống kê nào được chạy trên nó."""


@dataclass(frozen=True)
class StationHistory:
    """Lịch sử của một đài, theo thứ tự kỳ quay."""

    region: str
    province: str
    dates: tuple[str, ...]
    tails: np.ndarray  # (T, 18) hai số cuối của từng giải, theo thứ tự ``SLOTS``
    digits: np.ndarray  # (T, 82) mọi chữ số in, theo thứ tự ``SLOTS``

    def __len__(self) -> int:
        return len(self.dates)

    @cached_property
    def counts(self) -> np.ndarray:
        """(T, 100): số nháy của mỗi con trong 18 giải của kỳ."""
        out = np.zeros((len(self), NUMBER_SPACE), dtype=np.int16)
        np.add.at(out, (np.arange(len(self))[:, None], self.tails), 1)
        return out

    @property
    def special(self) -> np.ndarray:
        """(T,): hai số cuối giải Đặc Biệt."""
        return self.tails[:, SPECIAL_SLOT].astype(np.int64)

    def hits(self, mode: str) -> np.ndarray:
        """(T, 100) bool: con số "về" theo nghĩa của ``mode`` (``loto`` hoặc ``de``)."""
        if mode == "loto":
            return self.counts > 0
        if mode == "de":
            out = np.zeros((len(self), NUMBER_SPACE), dtype=bool)
            out[np.arange(len(self)), self.special] = True
            return out
        raise ValueError("mode phải là 'loto' hoặc 'de'")


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def structural_issues(rows: list[dict[str, str]], region: str) -> list[str]:
    """Mọi vi phạm cấu trúc của sổ miền; rỗng nghĩa là sổ hợp lệ.

    Đây là hợp đồng của một kỳ: đúng miền, ngày đọc được, giải và vị trí thuộc 18 ô, giá trị là
    chữ số ASCII đúng độ rộng của giải, khoá ``(ngày, đài, giải, vị trí)`` không trùng, và mỗi
    (ngày, đài) có ĐỦ 18 ô.
    """
    issues: list[str] = []
    seen: Counter[tuple[str, str, str, str]] = Counter()
    per_draw: dict[tuple[str, str], set[tuple[str, int]]] = defaultdict(set)
    for line, row in enumerate(rows, start=2):
        where = f"dòng {line}"
        if row.get("region") != region:
            issues.append(f"{where}: miền {row.get('region')!r} khác {region!r}")
        try:
            date.fromisoformat(row.get("date", ""))
        except ValueError:
            issues.append(f"{where}: ngày không hợp lệ {row.get('date')!r}")
            continue
        province = (row.get("province") or "").strip()
        if not province:
            issues.append(f"{where}: thiếu tên đài")
            continue
        try:
            slot = (row.get("prize", ""), int(row.get("position", "")))
        except ValueError:
            issues.append(f"{where}: vị trí không phải số nguyên {row.get('position')!r}")
            continue
        if slot not in _SLOT_INDEX:
            issues.append(f"{where}: giải/vị trí lạ {slot!r}")
            continue
        width = SLOT_WIDTHS[_SLOT_INDEX[slot]]
        value = row.get("value", "")
        if not re.fullmatch(rf"[0-9]{{{width}}}", value):
            issues.append(f"{where}: giá trị {value!r} không phải {width} chữ số")
        seen[(row["date"], province, slot[0], str(slot[1]))] += 1
        per_draw[(row["date"], province)].add(slot)
    issues.extend(f"khoá trùng {key} × {count}" for key, count in seen.items() if count > 1)
    issues.extend(
        f"kỳ {day} đài {province}: có {len(slots)}/{len(SLOTS)} ô"
        for (day, province), slots in per_draw.items()
        if len(slots) != len(SLOTS)
    )
    return issues


def build_stations(rows: list[dict[str, str]], region: str) -> list[StationHistory]:
    """Dựng lịch sử từng đài từ sổ miền; ném `RegionalDataError` nếu sổ sai cấu trúc."""
    issues = structural_issues(rows, region)
    if issues:
        shown = "; ".join(issues[:5])
        raise RegionalDataError(f"sổ miền {region} sai cấu trúc ({len(issues)} lỗi): {shown}")
    draws: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(lambda: [""] * len(SLOTS)))
    for row in rows:
        draws[row["province"].strip()][row["date"]][_SLOT_INDEX[(row["prize"], int(row["position"]))]] = row["value"]
    stations = []
    for province in sorted(draws):
        days = sorted(draws[province])
        values = [draws[province][day] for day in days]
        tails = np.array([[int(v[-2:]) for v in draw] for draw in values], dtype=np.int16)
        digits = np.array([[int(ch) for v in draw for ch in v] for draw in values], dtype=np.int8)
        stations.append(StationHistory(region, province, tuple(days), tails, digits))
    return stations


def load_stations(path: Path, region: str) -> list[StationHistory]:
    return build_stations(read_rows(path), region)


# --------------------------------------------------------------------------
# 1. Chất lượng dữ liệu
# --------------------------------------------------------------------------


def weekly_schedule(stations: list[StationHistory]) -> dict[int, list[str]]:
    """Lịch tuần SUY TỪ DỮ LIỆU: thứ (0 = thứ Hai) → đài quay vào thứ ấy.

    Một đài thuộc lịch của một thứ khi nó có mặt ở ít nhất nửa số ngày của thứ ấy trong sổ; nhờ
    vậy đài quay hai kỳ mỗi tuần thuộc cả hai thứ, và một kỳ lạc lịch không tự thành lịch mới.
    """
    by_weekday: dict[int, Counter[str]] = defaultdict(Counter)
    days_of: dict[int, set[str]] = defaultdict(set)
    for station in stations:
        for day in station.dates:
            weekday = date.fromisoformat(day).weekday()
            by_weekday[weekday][station.province] += 1
            days_of[weekday].add(day)
    return {
        weekday: sorted(p for p, n in by_weekday[weekday].items() if 2 * n >= len(days_of[weekday]))
        for weekday in sorted(by_weekday)
    }


def quality_report(rows: list[dict[str, str]], stations: list[StationHistory]) -> dict:
    """Kiểm chất lượng của một sổ miền ĐÃ hợp lệ về cấu trúc.

    Các mục dưới đây không dừng phép tính mà được in ra để người đọc biết thống kê đứng trên dữ
    liệu nào: ngày lịch không có kỳ (nghỉ Tết hoặc thiếu), đài vắng so với lịch tuần của chính
    nó, kỳ trùng khít kỳ trước của cùng đài hay trùng khít đài khác cùng ngày (dấu hiệu chép nhầm
    cột của nguồn; với kỳ quay thật xác suất ấy là 10⁻⁸² nên một lần trùng đã là lỗi).
    """
    by_day: dict[str, set[str]] = defaultdict(set)
    for station in stations:
        for day in station.dates:
            by_day[day].add(station.province)
    days = sorted(by_day)
    schedule = weekly_schedule(stations)
    calendar_gaps: list[str] = []
    off_schedule: list[dict] = []
    if days:
        cursor, last = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
        while cursor <= last:
            key = cursor.isoformat()
            expected = set(schedule.get(cursor.weekday(), []))
            if key not in by_day:
                calendar_gaps.append(key)
            elif by_day[key] != expected:
                off_schedule.append({
                    "date": key,
                    "missing": sorted(expected - by_day[key]),
                    "unexpected": sorted(by_day[key] - expected),
                })
            cursor += timedelta(days=1)
    repeated = [
        {"province": s.province, "date": s.dates[i]}
        for s in stations
        for i in range(1, len(s))
        if (s.digits[i] == s.digits[i - 1]).all()
    ]
    index_of = {s.province: {day: i for i, day in enumerate(s.dates)} for s in stations}
    by_name = {s.province: s for s in stations}
    cloned = []
    for day in days:
        present = sorted(by_day[day])
        for i, first in enumerate(present):
            for second in present[i + 1 :]:
                a = by_name[first].digits[index_of[first][day]]
                b = by_name[second].digits[index_of[second][day]]
                if (a == b).all():
                    cloned.append({"date": day, "provinces": [first, second]})
    canonical = "\n".join(
        ",".join((r["date"], r["province"], r["prize"], r["position"], r["value"]))
        for r in sorted(rows, key=lambda r: (r["date"], r["province"], _SLOT_INDEX[(r["prize"], int(r["position"]))]))
    )
    return {
        "rows": len(rows),
        "station_draws": int(sum(len(s) for s in stations)),
        "stations": len(stations),
        "first_date": days[0] if days else None,
        "last_date": days[-1] if days else None,
        "draw_dates": len(days),
        "origins": len({r.get("source", "") for r in rows}),
        "calendar_gaps": calendar_gaps,
        "off_schedule": off_schedule,
        "repeated_draws": repeated,
        "cloned_draws": cloned,
        "weekly_schedule": {str(weekday): names for weekday, names in schedule.items()},
        "draws_per_station": {s.province: len(s) for s in stations},
        # Dấu vân tay của NỘI DUNG kết quả (không gồm giờ tải): hai lượt trên cùng kết quả cho cùng mã.
        "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


# --------------------------------------------------------------------------
# 2. Thống kê mô tả
# --------------------------------------------------------------------------


def frequency_table(stations: list[StationHistory]) -> pd.DataFrame:
    """Mỗi (đài, con số) một dòng: số nháy, số kỳ có mặt, kỳ vọng, p hai phía, số kỳ chưa về.

    ``p_value`` là nhị thức CHÍNH XÁC hai phía của số kỳ có mặt so với mức nền một đài
    (1 − 0,99¹⁸). Bảng có 100 dòng mỗi đài, nên riêng do may rủi đã có ~5 dòng p < 0,05 ở MỖI
    đài: p ở đây là mô tả, kết luận đa kiểm nằm ở `summary` (q của Benjamini–Hochberg trên mọi
    dòng của miền). ``gap`` đếm theo kỳ của chính đài; con chưa từng về có ``gap`` bằng số kỳ.
    ``gap`` dài KHÔNG làm con số dễ về hơn ở kỳ sau — phép chấm tiến cứu của
    `evaluation.regional_benchmark` đo đúng điều ấy.
    """
    frames = []
    for station in stations:
        n = len(station)
        present = station.hits("loto")
        seen = present.sum(axis=0)
        # ``argmax`` trên lịch sử đảo ngược = số kỳ tính từ kỳ mới nhất lùi về lần có mặt gần nhất.
        last = np.where(seen > 0, np.argmax(present[::-1], axis=0), n)
        recent = present[-RECENT_DRAWS:]
        p_values = [
            float(scipy_stats.binomtest(int(k), n, LOTO_BASELINE_RATE).pvalue) if n else float("nan") for k in seen
        ]
        frames.append(pd.DataFrame({
            "region": station.region,
            "province": station.province,
            "number": [f"{number:02d}" for number in range(NUMBER_SPACE)],
            "draws": n,
            "nhay": station.counts.sum(axis=0).astype(int),
            "present": seen.astype(int),
            "expected_present": round(n * LOTO_BASELINE_RATE, 6),
            "p_value": np.round(p_values, 10),
            "present_recent": recent.sum(axis=0).astype(int),
            "recent_draws": len(recent),
            "gap": last.astype(int),
            "special_hits": np.bincount(station.special, minlength=NUMBER_SPACE).astype(int),
        }))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------
# 3. Kiểm định ngẫu nhiên từng đài
# --------------------------------------------------------------------------


def position_table(digits: np.ndarray) -> np.ndarray:
    """(82, 10): số lần mỗi chữ số ra ở từng vị trí in."""
    offsets = np.arange(digits.shape[1], dtype=np.int64) * 10
    return np.bincount((offsets + digits).ravel(), minlength=digits.shape[1] * 10).reshape(-1, 10)


def cage_table(digits: np.ndarray) -> np.ndarray:
    """(6, 10): số lần mỗi quả 0–9 ra ở từng LỒNG (hàng đơn vị … trăm nghìn), gộp mọi giải dùng lồng ấy."""
    return _CAGE_MEMBERSHIP @ position_table(digits)


def _chi_square_rows(table: np.ndarray) -> float:
    """Tổng χ² của các hàng, mỗi hàng so với phân bố đều trên mười chữ số của chính tổng hàng ấy."""
    expected = table.sum(axis=1, keepdims=True) / 10.0
    return float(((table - expected) ** 2 / np.where(expected > 0, expected, 1.0)).sum())


def digit_chi_square(digits: np.ndarray) -> float:
    """Tổng χ² của 82 vị trí chữ số in: mỗi vị trí có ra đều mười chữ số không."""
    return _chi_square_rows(position_table(digits))


def cage_chi_square(digits: np.ndarray) -> float:
    """Tổng χ² của năm lồng thấp (``MAIN_CAGES``): mỗi lồng có ra đều mười quả không.

    Đây là phép kiểm sát cơ chế vật lý nhất và mạnh nhất: lồng hàng đơn vị được rút 18 lần mỗi
    kỳ (mọi giải), nên một quả lệch hiện ra ở 18 × số kỳ quan sát thay vì chia nhỏ cho 18 vị trí in.
    Mỗi ô có kỳ vọng ≥ 1,2 × số kỳ (≥ 36 với đài vừa đủ kỳ để kiểm), nên thống kê tuân χ²(45) rất sát
    và p lấy thẳng từ đuôi χ²: p mô phỏng chạm sàn ``1/(số mô phỏng + 1)`` đúng ở những đài lệch
    mạnh nhất, tức đúng nơi cần phân biệt 10⁻⁴ với 10⁻²⁰.
    """
    return _chi_square_rows(cage_table(digits)[:MAIN_CAGES])


def special_digit_chi_square(digits: np.ndarray) -> float:
    """χ² của hàng chục và hàng đơn vị giải Đặc Biệt (hai chữ số cuối của giải)."""
    end = int(_DIGIT_OFFSETS[SPECIAL_SLOT + 1])
    return _chi_square_rows(position_table(digits[:, end - 2 : end]))


def repeat_lift(present: np.ndarray) -> float:
    """P(về | kỳ trước của đài đã về) − P(về | kỳ trước chưa về), gộp 100 con.

    Niềm tin "lô rơi" (con vừa về sẽ về lại) và "lô gan" (con vắng lâu sắp về) đều đòi hiệu này
    khác 0: dương cho lô rơi, âm cho lô gan.
    """
    previous, following = present[:-1], present[1:]
    came, absent = int(previous.sum()), int((~previous).sum())
    if came == 0 or absent == 0:
        return 0.0
    return float((previous & following).sum() / came - (~previous & following).sum() / absent)


def gap_ks(present: np.ndarray) -> float:
    """Khoảng cách Kolmogorov–Smirnov (rời rạc) giữa khoảng cách hai lần về và phân bố hình học.

    Chuỗi độc lập thì số kỳ giữa hai lần một con có mặt tuân theo hình học với mức nền của đài.
    So tại chính các điểm giá đỡ 1, 2, … (xem `randomness_battery.gap_distribution_distance` về lý
    do không dùng ``kstest`` của biến liên tục).
    """
    numbers, draws = np.nonzero(present.T)  # theo từng con, kỳ tăng dần
    gaps = np.diff(draws)[np.diff(numbers) == 0]
    if len(gaps) < 30:
        return 0.0
    support = np.arange(1, int(gaps.max()) + 1)
    empirical = np.cumsum(np.bincount(gaps, minlength=len(support) + 1)[1:]) / len(gaps)
    theoretical = 1.0 - (1.0 - LOTO_BASELINE_RATE) ** support
    return float(np.max(np.abs(empirical - theoretical)))


def _tails_to_counts(tails: np.ndarray) -> np.ndarray:
    offsets = np.arange(tails.shape[0], dtype=np.int64)[:, None] * NUMBER_SPACE
    return np.bincount((offsets + tails).ravel(), minlength=tails.shape[0] * NUMBER_SPACE).reshape(-1, NUMBER_SPACE)


def _digits_to_tails(digits: np.ndarray) -> np.ndarray:
    ends = _DIGIT_OFFSETS[1:]
    return digits[:, ends - 2].astype(np.int64) * 10 + digits[:, ends - 1]


#: (mã, tên, câu hỏi, hai phía?, bậc tự do χ² hoặc None). Thứ tự này là thứ tự cột của `_statistics`.
TESTS: tuple[tuple[str, str, str, bool, int | None], ...] = (
    ("cage_uniformity", "Chữ số theo lồng", "Mỗi lồng (hàng đơn vị … chục nghìn) có ra đều mười quả không?",
     False, MAIN_CAGES * 9),
    ("digit_uniformity", "Chữ số theo vị trí in", "Mỗi vị trí chữ số của từng giải có ra đều không?",
     False, TOTAL_DIGITS * 9),
    ("special_digits", "Chữ số cuối Đặc Biệt", "Hàng chục và hàng đơn vị Đặc Biệt có ra đều không?", False, 18),
    ("loto_uniformity", "Tần suất con lô", "Có con lô nào ra nhiều/ít hơn mức công bằng không?",
     False, NUMBER_SPACE - 1),
    ("dispersion", "Độ phân tán", "Số con khác nhau mỗi kỳ có dao động khác mức công bằng không?", True, None),
    ("repeat_lift", "Lô rơi / lô gan", "Con vừa về ở kỳ trước của đài có về lại nhiều hay ít hơn không?", True, None),
    ("gap_shape", "Nhịp khoảng cách", "Khoảng cách giữa hai lần về có lệch phân bố hình học không?", False, None),
    ("hot_persistence", "Độ bền số nóng", "Con hay về nửa đầu có tiếp tục hay về nửa sau không?", True, None),
)
TEST_CODES: tuple[str, ...] = tuple(test[0] for test in TESTS)
#: Phép kiểm lấy p từ đuôi χ² thay vì từ mô phỏng (xem `cage_chi_square`).
ASYMPTOTIC_TESTS: frozenset[str] = frozenset({"cage_uniformity"})


def _statistics(digits: np.ndarray) -> np.ndarray:
    table = position_table(digits)
    end = int(_DIGIT_OFFSETS[SPECIAL_SLOT + 1])
    counts = _tails_to_counts(_digits_to_tails(digits))
    present = counts > 0
    return np.array([
        _chi_square_rows((_CAGE_MEMBERSHIP @ table)[:MAIN_CAGES]),
        _chi_square_rows(table),
        _chi_square_rows(table[end - 2 : end]),
        battery.marginal_chi_square(counts),
        battery.dispersion_index(counts),
        repeat_lift(present),
        gap_ks(present),
        battery.hot_number_persistence(counts),
    ])


def _seed_for(province: str, seed: int) -> np.random.SeedSequence:
    # Hạt giống theo TÊN đài, không theo thứ tự: thêm một đài không đổi kết quả của đài khác.
    return np.random.SeedSequence([seed, zlib.crc32(province.encode("utf-8"))])


def station_battery(
    station: StationHistory, *, simulations: int = SIMULATIONS, seed: int = SEED
) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """Tám phép kiểm của một đài; trả (kết quả, thống kê quan sát, ma trận null ``(mô phỏng, 8)``).

    Mỗi lịch sử null là MỘT đài công bằng cùng số kỳ: 82 chữ số mỗi kỳ rút đều, độc lập; con lô
    suy từ hai chữ số cuối của từng giải đúng như dữ liệu thật. Tám thống kê tính trên CÙNG lịch
    sử mô phỏng, nên p từng phép hợp lệ và phép gộp cấp miền giữ được tương quan giữa chúng.

    ``p_value`` là p dùng cho hiệu chỉnh đa kiểm; ``p_simulated`` là p mô phỏng (sàn
    ``1/(simulations + 1)``). Hai giá trị trùng nhau ở mọi phép trừ phép theo lồng
    (``ASYMPTOTIC_TESTS``), nơi ``p_value`` là đuôi χ². Bốn phép χ² đều có ``p_asymptotic`` để thấy ĐỘ
    LỚN khi p mô phỏng chạm sàn; ở ba phép còn lại nó chỉ là xấp xỉ (ô chỉ có vài quan sát).
    """
    observed = _statistics(station.digits)
    rng = np.random.default_rng(_seed_for(station.province, seed))
    null = np.empty((simulations, len(TESTS)))
    for i in range(simulations):
        null[i] = _statistics(rng.integers(0, 10, size=(len(station), TOTAL_DIGITS), dtype=np.int8))
    results = []
    for j, (code, name, question, two_sided, dof) in enumerate(TESTS):
        centre, spread = float(null[:, j].mean()), float(null[:, j].std(ddof=1))
        if two_sided:
            extreme = int((np.abs(null[:, j] - centre) >= abs(observed[j] - centre)).sum())
        else:
            extreme = int((null[:, j] >= observed[j]).sum())
        simulated = (extreme + 1) / (simulations + 1)
        result = {
            "test": code,
            "name": name,
            "question": question,
            "two_sided": two_sided,
            "statistic": round(float(observed[j]), 8),
            "null_mean": round(centre, 8),
            "null_sd": round(spread, 8),
            "z": round((float(observed[j]) - centre) / spread, 6) if spread > 0 else 0.0,
            "p_value": simulated,
            "p_simulated": simulated,
        }
        if dof is not None:
            result["p_asymptotic"] = float(scipy_stats.chi2.sf(observed[j], dof))
        if code in ASYMPTOTIC_TESTS:
            result["p_value"] = result["p_asymptotic"]
        results.append(result)
    return results, observed, null


def pooled_tests(observed: list[np.ndarray], nulls: list[np.ndarray]) -> list[dict]:
    """Phép kiểm CẤP MIỀN: cộng điểm z của mọi đài cho từng phép, null là tổng z mô phỏng.

    Một độ lệch nhỏ CHUNG cho các đài (cùng nhà cung cấp lồng cầu, cùng quy trình) có thể không
    đài nào tự phát hiện được nhưng hiện ra khi cộng lại. Các đài độc lập nên lịch sử mô phỏng
    thứ ``i`` của mỗi đài ghép thành một "miền công bằng" thứ ``i``.
    """
    if not observed:
        return []
    centres = [null.mean(axis=0) for null in nulls]
    spreads = [np.where(null.std(axis=0, ddof=1) > 0, null.std(axis=0, ddof=1), 1.0) for null in nulls]
    z_observed = sum((obs - c) / s for obs, c, s in zip(observed, centres, spreads, strict=True))
    z_null = sum((null - c) / s for null, c, s in zip(nulls, centres, spreads, strict=True))
    out = []
    for j, (code, name, _question, two_sided, _dof) in enumerate(TESTS):
        if two_sided:
            extreme = int((np.abs(z_null[:, j]) >= abs(z_observed[j])).sum())
        else:
            extreme = int((z_null[:, j] >= z_observed[j]).sum())
        out.append({
            "test": code,
            "name": name,
            "stations": len(observed),
            "z_sum": round(float(z_observed[j]), 6),
            "z_per_sqrt_station": round(float(z_observed[j] / np.sqrt(len(observed))), 6),
            "p_value": (extreme + 1) / (len(z_null) + 1),
        })
    return out


def detectable(draws: int, hypotheses: int) -> dict:
    """Độ lệch tuyệt đối nhỏ nhất của MỘT con lô mà ``draws`` kỳ phát hiện được (công suất 80%)."""
    power = battery.minimum_detectable_lift(draws, baseline=LOTO_BASELINE_RATE, alpha=ALPHA, hypotheses=hypotheses)
    return {
        "draws": draws,
        "hypotheses": hypotheses,
        "baseline": round(LOTO_BASELINE_RATE, 10),
        "absolute_lift": round(power.detectable_lift, 6),
        "relative_lift": round(power.relative_lift, 6),
    }


def reading(summary: dict) -> str:
    """Câu kết luận của miền, suy TỪ số đo của chính bản tóm tắt."""
    tested = summary["tests"]["cells"]
    if not tested:
        return f"Chưa đài nào đủ {MIN_DRAWS_FOR_TESTS} kỳ để kiểm định."
    stations = summary["tests"]["flagged_stations"]
    pooled = [t for t in summary["tests"]["pooled"] if t["q_value"] < ALPHA]
    numbers = summary["numbers"]["significant"]
    lift = summary["detectable"]["per_station"]["absolute_lift"] * 100
    scope = (
        f"Ở cỡ mẫu hiện có (khoảng {summary['detectable']['per_station']['draws']} kỳ mỗi đài), phép kiểm chỉ "
        f"phát hiện được một con lô lệch khỏi mức nền từ {f'{lift:.1f}'.replace('.', ',')} điểm phần trăm trở lên."
    )
    if not stations and not pooled and not numbers:
        return (
            f"Không phép kiểm nào trong {tested} phép (đài × phép kiểm) lệch khỏi máy quay công bằng sau "
            f"hiệu chỉnh đa kiểm, và không con lô nào có tần suất khác mức nền. {scope}"
        )
    parts = []
    if stations:
        named = "; ".join(f"{block['province']} ({', '.join(name.lower() for name in block['tests'])})"
                          for block in stations)
        parts.append(f"{summary['tests']['significant_cells']}/{tested} phép kiểm (đài × phép kiểm) lệch khỏi "
                     f"máy quay công bằng — {named}")
    if pooled:
        parts.append("phép gộp cấp miền lệch ở: " + ", ".join(t["name"].lower() for t in pooled))
    if numbers:
        parts.append(f"{numbers} dòng (đài, con lô) có tần suất khác mức nền")
    return (
        "Sau hiệu chỉnh đa kiểm: " + "; ".join(parts) + ". Sổ miền chỉ ghi từ một nơi, nên độ lệch này có thể là "
        "của bộ cầu hoặc của cách kết quả được ghi lại; nó chưa phải lợi thế dự báo cho tới khi phép kiểm tiến "
        "cứu trên các kỳ SAU ngày phát hiện xác nhận. " + scope
    )


def summarize(rows: list[dict[str, str]], stations: list[StationHistory], table: pd.DataFrame,
              *, simulations: int = SIMULATIONS, seed: int = SEED) -> dict:
    region = stations[0].region if stations else ""
    quality = quality_report(rows, stations)
    tested = [s for s in stations if len(s) >= MIN_DRAWS_FOR_TESTS]
    per_station, observed, nulls = [], [], []
    for station in tested:
        results, obs, null = station_battery(station, simulations=simulations, seed=seed)
        per_station.append({"province": station.province, "draws": len(station), "tests": results})
        observed.append(obs)
        nulls.append(null)
    # Một họ: mọi (đài × phép kiểm) của miền.
    flat = [test for block in per_station for test in block["tests"]]
    for test, q in zip(flat, benjamini_hochberg([t["p_value"] for t in flat]), strict=True):
        test["q_value"] = round(float(q), 10)
    flagged_stations = []
    for station, block in zip(tested, per_station, strict=True):
        flagged = [t for t in block["tests"] if t["q_value"] < ALPHA]
        if flagged:
            flagged_stations.append({"province": station.province, "tests": [t["name"] for t in flagged]})
        if any(t["test"] == "cage_uniformity" for t in flagged):
            # Bảng đếm theo lồng của đài bị gắn cờ: người đọc thấy QUẢ nào lệch, không chỉ một p.
            block["cage_counts"] = cage_table(station.digits).tolist()
    pooled = pooled_tests(observed, nulls)
    for test, q in zip(pooled, benjamini_hochberg([t["p_value"] for t in pooled]), strict=True):
        test["q_value"] = round(float(q), 10)
    q_numbers = benjamini_hochberg(table["p_value"].to_numpy(dtype=float)) if len(table) else np.array([])
    hot = table.assign(q_value=q_numbers).sort_values(["p_value", "province", "number"], kind="stable").head(10)
    distinct = np.concatenate([s.hits("loto").sum(axis=1) for s in stations]) if stations else np.array([])
    exact = distinct_count_distribution()
    typical = int(np.median([len(s) for s in tested])) if tested else 0
    summary = {
        "schema_version": SCHEMA_VERSION,
        "region": region,
        "region_name": REGIONS.get(region, region),
        "data_through": quality["last_date"],
        "game": {
            "prizes_per_station_draw": LOTO_DRAWS_PER_STATION,
            "digits_per_station_draw": TOTAL_DIGITS,
            "loto_baseline": round(LOTO_BASELINE_RATE, 10),
            "special_baseline": DE_BASELINE_RATE,
            "pair_cooccurrence": round(PAIR_COOCCURRENCE_RATE, 10),
            "expected_distinct_numbers": round(NUMBER_SPACE * LOTO_BASELINE_RATE, 6),
            "observed_distinct_numbers": round(float(distinct.mean()), 6) if len(distinct) else None,
            "distinct_numbers_sd_exact": round(float(np.sqrt(
                sum(d * d * p for d, p in enumerate(exact)) - sum(d * p for d, p in enumerate(exact)) ** 2)), 6),
        },
        "quality": quality,
        "numbers": {
            "tested": int(len(table)),
            "significant": int((q_numbers < ALPHA).sum()) if len(q_numbers) else 0,
            "min_q": round(float(q_numbers.min()), 10) if len(q_numbers) else None,
            "most_extreme": [
                {"province": r.province, "number": r.number, "present": int(r.present), "draws": int(r.draws),
                 "expected_present": float(r.expected_present), "p_value": float(r.p_value),
                 "q_value": round(float(r.q_value), 10)}
                for r in hot.itertuples()
            ],
        },
        "tests": {
            "simulations": simulations,
            "seed": seed,
            "alpha": ALPHA,
            "min_draws": MIN_DRAWS_FOR_TESTS,
            "cells": len(flat),
            "significant_cells": int(sum(t["q_value"] < ALPHA for t in flat)),
            "flagged_stations": flagged_stations,
            "cage_names": list(CAGE_NAMES),
            "per_station": per_station,
            "pooled": pooled,
        },
        "detectable": {
            "per_station": detectable(max(typical, 1), NUMBER_SPACE),
            "pooled_region": detectable(max(quality["station_draws"], 1), NUMBER_SPACE),
        },
    }
    summary["reading"] = reading(summary)
    return summary


def run(repo_root: Path, *, simulations: int = SIMULATIONS, seed: int = SEED) -> list[Path]:
    """Ghi ``data/stats/regional/frequency_<miền>.csv`` và ``summary_<miền>.json`` cho hai miền.

    Tất định (hạt giống cố định, không dấu giờ): chạy lại trên cùng sổ miền cho cùng tệp.
    """
    out_dir = repo_root / "data" / OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for region in REGIONS:
        rows = read_rows(repo_root / "data" / "regions" / f"xs{region}.csv")
        stations = build_stations(rows, region)
        if not stations:
            continue
        table = frequency_table(stations)
        summary = summarize(rows, stations, table, simulations=simulations, seed=seed)
        table_path = out_dir / f"frequency_{region}.csv"
        atomic_to_csv(table, table_path, index=False)
        summary_path = out_dir / f"summary_{region}.json"
        atomic_write_text(summary_path, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        written.extend([table_path, summary_path])
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thống kê và kiểm định ngẫu nhiên từng đài XSMT/XSMN")
    parser.add_argument("--simulations", type=int, default=SIMULATIONS)
    args = parser.parse_args(argv)
    for path in run(REPO_ROOT, simulations=args.simulations):
        print("Wrote:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
