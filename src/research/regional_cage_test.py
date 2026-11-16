"""Phép kiểm TIẾN CỨU cho độ lệch chữ số theo lồng của một đài miền Trung / miền Nam.

Nguồn gốc
---------
Ngày 16-11-2026, phép "chữ số theo lồng" của `stats.regional_stats` gắn cờ hai đài miền Nam trên
sổ một năm (07-10-2025 → 15-11-2026). Ở đài lệch mạnh nhất, mỗi lồng có đúng một quả ra chỉ bằng
30–60% mức đều, ổn định ở cả hai nửa năm (p tiệm cận 4·10⁻²¹), và mô hình chữ số theo lồng thắng dự
báo đều NGOÀI MẪU ở riêng đài ấy (`evaluation.regional_benchmark`). Nhưng phép kiểm theo lồng được
viết SAU khi một phép kiểm khác đã chỉ vào đài này, và sổ miền chỉ ghi từ một nơi: bằng chứng hồi
cứu không đủ, và nó không phân biệt được bộ cầu lệch với kết quả bị ghi sai có hệ thống.

Cách duy nhất phân biệt tín hiệu thật với tín hiệu tìm ra sau khi nhìn là chấm nó trên những kỳ
CHƯA TỒN TẠI lúc đặt giả thuyết.

Luật (mọi hằng số dưới đây đã chốt; đổi thì tăng ``VERSION`` và đăng ký lại với ngày mới)
-----------------------------------------------------------------------------------------
* **Đăng ký tự động, một lần mỗi đài.** Khi bản tóm tắt của miền gắn cờ phép ``cage_uniformity``
  của một đài (q < ``regional_stats.ALPHA``) và đài chưa có đăng ký, luật đối của đài được ĐÓNG
  BĂNG: xác suất từng quả ở từng lồng ``(đếm + PRIOR_STRENGTH/10) / (tổng + PRIOR_STRENGTH)`` trên
  mọi kỳ đã có. Đăng ký không bao giờ bị sửa hay xoá.
* **Chỉ chấm kỳ SAU ngày đăng ký.** Mỗi kỳ mới nhân bằng chứng với tỉ số hợp lý của 82 chữ số của
  kỳ ấy: ``e_t = Π luật[lồng][chữ số] / 0,1``. Dưới giả thuyết "kết quả ghi được là đều và độc
  lập", ``E[e_t] = 1``, nên tích luỹ là một martingale không âm: xác suất nó TỪNG vượt ``1/α`` không
  quá ``α`` (bất đẳng thức Ville), dù nhìn vào lúc nào và dừng lúc nào.
* **Ngưỡng ghi lúc đăng ký**: ``số đài đang được kiểm / ALPHA`` (Bonferroni trên mọi đài của hai
  miền), để việc có nhiều đài không làm tăng xác suất báo nhầm của cả họ.
* Luật đối đóng băng mang lời nguyền người thắng (đài được chọn vì lệch nhất). Điều đó chỉ làm
  phép kiểm KÉM NHẠY đi, không làm nó báo nhầm: tính hợp lệ chỉ cần luật đối không nhìn kỳ được chấm.

"Xác nhận" ở đây nghĩa là: kết quả GHI ĐƯỢC của đài lệch khỏi phân bố đều. Nó không nói nguyên nhân
là bộ cầu hay khâu ghi kết quả; việc ấy cần đối chiếu một nơi ghi độc lập.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from datetime import date
from pathlib import Path

import numpy as np

from core.atomic_io import atomic_write_text
from core.paths import REPO_ROOT
from core.regional_domain import CAGE_OF_DIGIT, REGIONS
from stats import regional_stats
from stats.regional_stats import StationHistory, cage_table, load_stations

VERSION = 1
SCHEMA_VERSION = 1
ALPHA = 0.01
#: Số quan sát giả ở mức đều cho mỗi lồng khi đóng băng luật đối.
PRIOR_STRENGTH = 50.0
TRIGGER_TEST = "cage_uniformity"
REGISTRY = Path("research") / "hypotheses" / "regional_cage_bias.json"
LEDGER = Path("research") / "hypotheses" / "regional_cage_bias.csv"
FIELDS = ["id", "date", "log_e", "log_e_total", "draws"]
_LAW_DECIMALS = 12
_CAGES = np.array(CAGE_OF_DIGIT)


def frozen_law(station: StationHistory) -> list[list[float]]:
    """Luật đối của một đài từ MỌI kỳ đang có: mỗi lồng một phân phối trên mười quả, cộng lại bằng 1."""
    counts = cage_table(station.digits).astype(float)
    law = (counts + PRIOR_STRENGTH / 10.0) / (counts.sum(axis=1, keepdims=True) + PRIOR_STRENGTH)
    return [[round(float(value), _LAW_DECIMALS) for value in row] for row in law]


def log_evidence(law: list[list[float]], digits: np.ndarray) -> float:
    """``ln e`` của MỘT kỳ: tổng trên 82 chữ số của ``ln(luật[lồng][chữ số] / 0,1)``."""
    table = np.asarray(law, dtype=float)
    return float(np.log(table[_CAGES, np.asarray(digits, dtype=np.int64)] * 10.0).sum())


def _read_registry(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "version": VERSION, "alpha": ALPHA, "registrations": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_ledger(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _flagged(summary: dict) -> dict[str, dict]:
    """Đài → kết quả phép ``cage_uniformity`` đã qua ngưỡng gắn cờ của bản tóm tắt."""
    out = {}
    for block in summary.get("tests", {}).get("per_station", []):
        for test in block["tests"]:
            if test["test"] == TRIGGER_TEST and test["q_value"] < regional_stats.ALPHA:
                out[block["province"]] = test
    return out


def register(registry: dict, summaries: dict[str, dict], stations: dict[str, list[StationHistory]]) -> list[dict]:
    """Thêm đăng ký cho đài vừa bị gắn cờ lần đầu; trả các đăng ký MỚI. Đăng ký cũ không bị chạm."""
    held = {(r["region"], r["province"]) for r in registry["registrations"]}
    family = sum(len(summary.get("tests", {}).get("per_station", [])) for summary in summaries.values())
    added = []
    for region in sorted(summaries):
        summary = summaries[region]
        by_name = {s.province: s for s in stations.get(region, [])}
        latest = max((s.dates[-1] for s in by_name.values()), default=None)
        if summary.get("data_through") != latest:
            # Bản tóm tắt không khớp sổ đang đọc: không đóng băng luật trên một cờ của dữ liệu khác.
            continue
        for province, test in sorted(_flagged(summary).items()):
            if (region, province) in held or province not in by_name:
                continue
            station = by_name[province]
            entry = {
                "id": f"{region}:{province}:{station.dates[-1]}",
                "version": VERSION,
                "region": region,
                "province": province,
                "registered_through": station.dates[-1],
                "draws_used": len(station),
                "cage_counts": cage_table(station.digits).tolist(),
                "law": frozen_law(station),
                "prior_strength": PRIOR_STRENGTH,
                "alpha": ALPHA,
                "family": family,
                "threshold": family / ALPHA,
                "trigger": {key: test[key] for key in ("p_value", "q_value", "p_asymptotic") if key in test},
            }
            registry["registrations"].append(entry)
            added.append(entry)
    return added


def score(registry: dict, ledger: list[dict[str, str]], stations: dict[str, list[StationHistory]]) -> list[dict]:
    """Chấm mọi kỳ SAU ngày đăng ký chưa có trong sổ; trả các dòng mới (đã nối vào ``ledger``)."""
    new_rows = []
    for entry in registry["registrations"]:
        own = [row for row in ledger if row["id"] == entry["id"]]
        total = float(own[-1]["log_e_total"]) if own else 0.0
        seen = {row["date"] for row in own}
        last_scored = max(seen, default=entry["registered_through"])
        station = next((s for s in stations.get(entry["region"], []) if s.province == entry["province"]), None)
        if station is None:
            continue
        for index, day in enumerate(station.dates):
            # Chỉ nối TIẾP: một kỳ cũ hơn dòng cuối của sổ không bao giờ được chèn hay chấm lại.
            if day <= last_scored:
                continue
            step = log_evidence(entry["law"], station.digits[index])
            total += step
            row = {"id": entry["id"], "date": day, "log_e": f"{step:.10f}", "log_e_total": f"{total:.10f}",
                   "draws": str(len(own) + 1)}
            own.append(row)
            ledger.append(row)
            new_rows.append(row)
            last_scored = day
    return new_rows


def status(registry: dict, ledger: list[dict[str, str]]) -> list[dict]:
    """Trạng thái của từng đăng ký, suy TỪ sổ: bằng chứng hiện tại, cao nhất, và đã từng vượt ngưỡng chưa."""
    out = []
    for entry in registry["registrations"]:
        own = [row for row in ledger if row["id"] == entry["id"]]
        totals = [float(row["log_e_total"]) for row in own]
        threshold = math.log(entry["threshold"])
        crossed = next((row["date"] for row, value in zip(own, totals, strict=True) if value >= threshold), None)
        out.append({
            "id": entry["id"],
            "region": entry["region"],
            "province": entry["province"],
            "registered_through": entry["registered_through"],
            "draws_scored": len(own),
            "last_scored": own[-1]["date"] if own else None,
            "log10_e": round(totals[-1] / math.log(10), 6) if totals else 0.0,
            "log10_e_max": round(max(totals) / math.log(10), 6) if totals else 0.0,
            "log10_threshold": round(threshold / math.log(10), 6),
            "confirmed": crossed is not None,
            "confirmed_on": crossed,
        })
    return out


def _vn_date(day: str) -> str:
    return date.fromisoformat(day).strftime("%d/%m/%Y")


def _vn(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def reading(row: dict) -> str:
    """Câu trạng thái của một đăng ký, in TỪ số đo của nó."""
    head = f"Đài {row['province']}: giả thuyết đóng băng theo các kỳ đến {_vn_date(row['registered_through'])}"
    if not row["draws_scored"]:
        return f"{head}; chưa có kỳ mới nào để chấm."
    evidence = (f"bằng chứng 10^{_vn(row['log10_e'])} sau {row['draws_scored']} kỳ mới "
                f"(ngưỡng 10^{_vn(row['log10_threshold'])})")
    if row["confirmed"]:
        return (f"{head}; ĐÃ XÁC NHẬN ngày {_vn_date(row['confirmed_on'])}: kết quả ghi được lệch khỏi phân bố "
                f"đều trên các kỳ sau đăng ký ({evidence}).")
    if row["log10_e"] < 0:
        return f"{head}; các kỳ mới KHÔNG ủng hộ độ lệch đã thấy ({evidence})."
    return f"{head}; chưa đủ bằng chứng ({evidence})."


def run(repo_root: Path) -> tuple[Path, Path]:
    """Đăng ký đài mới bị gắn cờ, chấm kỳ mới, ghi sổ và trạng thái.

    Sổ CSV chỉ được NỐI THÊM: dòng cũ giữ nguyên từng byte. Trong tệp đăng ký, phần ``registrations``
    chỉ được thêm; phần ``status`` suy lại từ sổ ở mỗi lượt.
    """
    data = repo_root / "data"
    summaries, stations = {}, {}
    for region in REGIONS:
        summary_path = data / regional_stats.OUT_DIR / f"summary_{region}.json"
        if summary_path.exists():
            summaries[region] = json.loads(summary_path.read_text(encoding="utf-8"))
        stations[region] = load_stations(data / "regions" / f"xs{region}.csv", region)
    registry_path, ledger_path = data / REGISTRY, data / LEDGER
    registry = _read_registry(registry_path)
    ledger = _read_ledger(ledger_path)
    register(registry, summaries, stations)
    new_rows = score(registry, ledger, stations)
    rows = status(registry, ledger)
    for row in rows:
        row["reading"] = reading(row)
    registry["status"] = rows
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing = ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else ""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    if not existing:
        writer.writeheader()
    writer.writerows(new_rows)
    if buffer.getvalue():
        atomic_write_text(ledger_path, existing + buffer.getvalue())
    atomic_write_text(registry_path, json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    return registry_path, ledger_path


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Phép kiểm tiến cứu độ lệch chữ số theo lồng của đài XSMT/XSMN").parse_args(argv)
    for path in run(REPO_ROOT):
        print("Wrote:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
