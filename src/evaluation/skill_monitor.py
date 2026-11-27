from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from core.atomic_io import atomic_to_csv
from core.xsmb_domain import baseline_rate

MODES: tuple[str, ...] = ("loto", "de")

_ARTIFACT = re.compile(r"predict_next_(loto|de)_all_(\d{4}-\d{2}-\d{2})\.csv$")

DEFAULT_WINDOW = 60
MIN_DAYS = 20
DEFAULT_Z = 3.0
MIN_EFFECT = 1e-6


def _outcomes(data_dir: Path) -> pd.DataFrame:
    frame = pd.read_csv(data_dir / "xsmb-2-digits.csv")
    frame["date"] = frame["date"].astype(str)
    return frame.set_index("date")


def published_evaluation(
    data_dir: Path, mode: str
) -> tuple[list[str], np.ndarray, np.ndarray]:
    empty = [], np.empty((0, 100)), np.empty((0, 100))
    if not (data_dir / "xsmb-2-digits.csv").exists() or not (data_dir / "forecast" / "predict").is_dir():
        return empty
    outcomes = _outcomes(data_dir)
    prizes = [column for column in outcomes.columns if column != "date"]
    days: list[str] = []
    probs: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for path in sorted((data_dir / "forecast" / "predict").glob(f"predict_next_{mode}_all_*.csv")):
        found = _ARTIFACT.search(path.name)
        if not found or found.group(1) != mode:
            continue
        day = found.group(2)
        if day not in outcomes.index:
            continue
        frame = pd.read_csv(path).set_index("number").reindex(range(100))
        p = pd.to_numeric(frame["prob"], errors="coerce").to_numpy(dtype=float)
        valid = (
            np.isfinite(p).all()
            and np.all((p >= 0.0) & (p <= 1.0))
            and float(p.sum()) > 0.0
        )
        if not valid:
            raise ValueError(f"{mode} {day}: artifact phải đủ 100 xác suất hữu hạn trong [0, 1], tổng dương")
        row = outcomes.loc[day]
        y = np.zeros(100)
        if mode == "de":
            y[int(row["special"])] = 1.0
            p = p / p.sum()
        else:
            for prize in prizes:
                y[int(row[prize])] = 1.0
        days.append(day)
        probs.append(p)
        labels.append(y)
    if not days:
        return empty
    return days, np.vstack(probs), np.vstack(labels)


def daily_skill(mode: str, probs: np.ndarray, labels: np.ndarray) -> np.ndarray:
    if len(probs) == 0:
        return np.empty(0)
    if mode == "de":
        hit = np.clip(probs[labels > 0.5], 1e-12, 1.0)
        return 1.0 - (-np.log(hit)) / np.log(100.0)
    base = baseline_rate("loto")
    p = np.clip(probs, 1e-6, 1.0 - 1e-6)
    model = -np.mean(labels * np.log(p) + (1 - labels) * np.log(1 - p), axis=1)
    reference = -np.mean(labels * np.log(base) + (1 - labels) * np.log(1 - base), axis=1)
    return 1.0 - model / reference


LEDGER = Path("evaluation") / "model_quality" / "published_skill.csv"


def _read_ledger(data_dir: Path) -> pd.DataFrame:
    path = data_dir / LEDGER
    if not path.exists():
        return pd.DataFrame(columns=["target_date", "mode", "skill"])
    frame = pd.read_csv(path, dtype={"target_date": str, "mode": str})
    skill = pd.to_numeric(frame["skill"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(skill).all():
        raise ValueError(f"{path}: kỹ năng trong sổ phải hữu hạn")
    return frame[["target_date", "mode", "skill"]]


def graded_series(data_dir: Path, mode: str) -> tuple[list[str], np.ndarray]:
    kept = _read_ledger(data_dir)
    kept = kept[kept["mode"] == mode]
    series = dict(zip(kept["target_date"], kept["skill"].astype(float), strict=True))
    days, probs, labels = published_evaluation(data_dir, mode)
    for day, value in zip(days, daily_skill(mode, probs, labels), strict=True):
        series.setdefault(day, float(value))
    ordered = sorted(series)
    return ordered, np.asarray([series[d] for d in ordered], dtype=float)


def update_ledger(data_dir: Path) -> Path:
    rows = []
    for mode in MODES:
        days, skills = graded_series(data_dir, mode)
        rows += [{"target_date": d, "mode": mode, "skill": float(s)} for d, s in zip(days, skills, strict=True)]
    path = data_dir / LEDGER
    frame = pd.DataFrame(rows, columns=["target_date", "mode", "skill"])
    atomic_to_csv(frame.sort_values(["mode", "target_date"]), path, index=False, float_format="%.12g")
    return path


@dataclass(frozen=True)
class SkillStatus:

    mode: str
    days: int
    first_day: str
    last_day: str
    mean: float
    stderr: float
    z: float

    @property
    def low(self) -> float:
        return self.mean - self.z * self.stderr

    @property
    def high(self) -> float:
        return self.mean + self.z * self.stderr

    @property
    def state(self) -> str:
        if self.days < MIN_DAYS:
            return "chua_du"
        if abs(self.mean) < MIN_EFFECT:
            return "vung_0"
        if self.high < 0.0:
            return "te_hon"
        if self.low > 0.0:
            return "hon"
        return "vung_0"

    @property
    def alarm(self) -> bool:
        return self.state in ("te_hon", "hon")

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "days": self.days,
            "first_day": self.first_day,
            "last_day": self.last_day,
            "mean": self.mean,
            "stderr": self.stderr,
            "z": self.z,
            "low": self.low,
            "high": self.high,
            "state": self.state,
            "alarm": self.alarm,
        }

    def describe(self) -> str:
        words = {
            "chua_du": f"chưa đủ {MIN_DAYS} kỳ để kết luận",
            "vung_0": "trong vùng 0 — đúng như một kỳ quay công bằng",
            "te_hon": "TỆ HƠN đường cơ sở có ý nghĩa — hồi quy, cần xem ngay",
            "hon": "HƠN đường cơ sở có ý nghĩa — kiểm lại trước khi tin",
        }
        return (
            f"{self.mode:<5} {self.days:>3} kỳ ({self.first_day} → {self.last_day}): "
            f"kỹ năng {self.mean:+.4%}, khoảng [{self.low:+.4%}, {self.high:+.4%}] "
            f"ở z={self.z:g} — {words[self.state]}"
        )


def status(
    days: list[str],
    skills: np.ndarray,
    mode: str,
    *,
    window: int = DEFAULT_WINDOW,
    z: float = DEFAULT_Z,
) -> SkillStatus:
    values = np.asarray(skills, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{mode}: kỹ năng phải hữu hạn trước khi kết luận")
    recent = values[-window:]
    recent_days = list(days)[-window:]
    n = len(recent)
    with np.errstate(over="ignore", invalid="ignore"):
        mean = float(recent.mean()) if n else 0.0
        stderr = float(recent.std(ddof=1) / np.sqrt(n)) if n > 1 else float("inf")
        bounds = (mean - z * stderr, mean + z * stderr)
    if n >= MIN_DAYS and not np.isfinite((mean, stderr, *bounds)).all():
        raise ValueError(f"{mode}: thống kê kỹ năng và khoảng tin phải hữu hạn trước khi kết luận")
    return SkillStatus(
        mode=mode,
        days=n,
        first_day=recent_days[0] if n else "",
        last_day=recent_days[-1] if n else "",
        mean=mean,
        stderr=stderr,
        z=z,
    )


def evaluate(data_dir: Path, *, window: int = DEFAULT_WINDOW, z: float = DEFAULT_Z) -> list[SkillStatus]:
    out = []
    for mode in MODES:
        days, skills = graded_series(data_dir, mode)
        out.append(status(days, skills, mode, window=window, z=z))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--z", type=float, default=DEFAULT_Z)
    args = parser.parse_args()

    try:
        checks = evaluate(Path(args.data_dir), window=args.window, z=args.z)
    except ValueError as exc:
        print(f"::error::Không thể chấm kỹ năng ngoài mẫu: {exc}")
        return 1
    for check in checks:
        print(check.describe())
    alarms = [check for check in checks if check.alarm]
    for check in alarms:
        print(f"::error::Kỹ năng ngoài mẫu {check.mode} rời vùng 0: {check.describe()}")
    return 1 if alarms else 0


if __name__ == "__main__":
    sys.exit(main())
