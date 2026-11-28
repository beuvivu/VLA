from __future__ import annotations

import argparse
import csv
import io
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = "data/xsmb.csv"
PREDICT_DIR = "data/forecast/predict"
MODES: tuple[str, ...] = ("loto", "de")
MAX_WINDOW = timedelta(minutes=60)
_FORECAST = re.compile(r"predict_next_(loto|de)_all_(\d{4}-\d{2}-\d{2})\.csv$")


@dataclass(frozen=True)
class Decision:
    deploy: bool
    reason: str


def latest_draw(ledger_text: str) -> str | None:
    try:
        days = [row["date"][:10] for row in csv.DictReader(io.StringIO(ledger_text)) if row.get("date")]
    except (csv.Error, KeyError):
        return None
    return max(days, default=None)


def forecast_days(names: Iterable[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {mode: set() for mode in MODES}
    for name in names:
        match = _FORECAST.search(name)
        if match:
            out[match.group(1)].add(match.group(2))
    return out


def decide(ledger_text: str, predict_names: Iterable[str], canonical_at: datetime | None,
           now: datetime) -> Decision:
    latest = latest_draw(ledger_text)
    if latest is None:
        return Decision(True, "không đọc được sổ chuẩn XSMB; không có trang XSMB nào để giữ")
    days = forecast_days(predict_names)
    if all(any(day > latest for day in days[mode]) for mode in MODES):
        return Decision(True, f"XSMB không đang chốt kỳ (kỳ {latest} đã có dự báo kỳ sau)")
    if canonical_at is None:
        return Decision(False, f"XSMB đang chốt kỳ {latest} (chưa có dự báo kỳ sau), không rõ giờ chốt; "
                               "nhường lần triển khai cho pipeline XSMB")
    age = now - canonical_at
    minutes = int(age.total_seconds() // 60)
    if age > MAX_WINDOW:
        return Decision(True, f"XSMB chốt kỳ {latest} đã {minutes} phút mà chưa xong (trần "
                              f"{int(MAX_WINDOW.total_seconds() // 60)} phút); pipeline XSMB có thể đã kẹt, "
                              "triển khai lại trang Vietlott")
    return Decision(False, f"XSMB đang chốt kỳ {latest} ({minutes} phút trước, chưa có dự báo kỳ sau); "
                           "nhường lần triển khai cho pipeline XSMB, lần ấy mang luôn trang Vietlott")


def parse_time(text: str) -> datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def read_ref(ref: str, root: Path = REPO_ROOT) -> tuple[str, list[str]]:
    ledger = _git(root, "show", f"{ref}:{LEDGER}")
    names = _git(root, "ls-tree", "--name-only", f"{ref}:{PREDICT_DIR}")
    return (ledger.stdout if ledger.returncode == 0 else "",
            names.stdout.split() if names.returncode == 0 else [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="HEAD", help="ref git để đọc sổ chuẩn và dự báo (mặc định HEAD)")
    parser.add_argument("--canonical-at", default="", help="giờ commit gần nhất chạm data/xsmb.csv (ISO 8601)")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="thư mục kho git (mặc định: kho chứa kịch bản)")
    args = parser.parse_args(argv)
    ledger, names = read_ref(args.ref, args.repo)
    decision = decide(ledger, names, parse_time(args.canonical_at), datetime.now(timezone.utc))
    print(("Triển khai: " if decision.deploy else "Nhường: ") + decision.reason)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"deploy={'true' if decision.deploy else 'false'}\n")
            handle.write(f"reason={decision.reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
