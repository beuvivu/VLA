"""Chấm xác suất ĐÃ CÔNG BỐ với kết quả quay thật, và báo động khi rời vùng 0.

Vì sao chấm artifact chứ không dựng lại
=======================================

``model_quality`` từng dựng lại tổ hợp từ ``data/history/pred_<mode>.csv``.
Bản dựng ấy bỏ qua bước hiệu chỉnh và tầng xếp chồng, tức là chấm một mô hình
KHÁC mô hình người xem nhận: nó cho Đặc Biệt tới 25,9% và kỹ năng −2,0%, trong
khi xác suất thật sự công bố cao nhất 1,28% và kỹ năng −0,03%. Mỗi ngày
pipeline ghi đúng vector đã công bố vào
``data/predict/predict_next_<mode>_all_<ngày>.csv`` TRƯỚC kỳ quay, nên chấm
chính tệp ấy là phép đo không thể rò rỉ và không thể lệch khỏi production.

Vì sao báo động cả khi "tốt hơn"
================================

Kỳ quay đã được kiểm là ngẫu nhiên. Kỹ năng ngoài mẫu nằm ngoài vùng 0 theo
hướng NÀO cũng là tin cần người xem xét: tệ hơn là hồi quy; tốt hơn thì hoặc
là tín hiệu thật đầu tiên — phải kiểm lại trước khi tin — hoặc là lỗi ghi
ngày của artifact.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from xsmb_domain import baseline_rate

MODES: tuple[str, ...] = ("loto", "de")

#: Tên tệp artifact đã công bố. Ngày trong tên là KỲ ĐÍCH, không phải ngày chạy.
_ARTIFACT = re.compile(r"predict_next_(loto|de)_all_(\d{4}-\d{2}-\d{2})\.csv$")

#: Số kỳ gần nhất mà bộ báo động xét.
DEFAULT_WINDOW = 60
#: Ít hơn ngần này kỳ thì chưa kết luận gì cả.
MIN_DAYS = 20
#: Ngưỡng z cho khoảng tin cậy hai phía. Phép kiểm chạy MỖI NGÀY trên cửa sổ
#: trượt chồng lấn, nên 1,96 sẽ báo giả vài lần mỗi năm; 3,0 (≈99,7%) giữ báo
#: giả hiếm mà vẫn bắt được một mô hình tệ đi thật.
DEFAULT_Z = 3.0
#: Lệch nhỏ hơn ngần này (0,0001%) không có ý nghĩa thực tế, dù khoảng tin
#: cậy có hẹp tới đâu. Không có sàn này, một dự báo trùng đúng mốc cho kỹ năng
#: ±1e-16 (nhiễu dấu phẩy động) với sai số chuẩn còn nhỏ hơn, và bộ theo dõi
#: báo động giả — phép kiểm dựng sẵn đã bắt được đúng điều đó.
MIN_EFFECT = 1e-6


def _outcomes(data_dir: Path) -> pd.DataFrame:
    frame = pd.read_csv(data_dir / "xsmb-2-digits.csv")
    frame["date"] = frame["date"].astype(str)
    return frame.set_index("date")


def published_evaluation(
    data_dir: Path, mode: str
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Vector xác suất đã công bố và nhãn thật của mọi kỳ đã quay.

    Returns:
        ``(ngày, P, Y)`` với ``P``, ``Y`` dạng ``(số kỳ, 100)``. LOTO: ``Y`` là
        1 nếu con ấy về ít nhất một lần. Đặc Biệt: ``Y`` là one-hot của giải.
    """
    empty = [], np.empty((0, 100)), np.empty((0, 100))
    # Thiếu kết quả quay hoặc thư mục artifact thì "chưa có gì để chấm", không
    # phải lỗi: trang Chất lượng lùi về bản dựng lại, bộ theo dõi báo chưa đủ.
    # Ném ngoại lệ ở đây từng làm sập cả bước chẩn đoán.
    if not (data_dir / "xsmb-2-digits.csv").exists() or not (data_dir / "predict").is_dir():
        return empty
    outcomes = _outcomes(data_dir)
    prizes = [column for column in outcomes.columns if column != "date"]
    days: list[str] = []
    probs: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for path in sorted((data_dir / "predict").glob(f"predict_next_{mode}_all_*.csv")):
        found = _ARTIFACT.search(path.name)
        if not found or found.group(1) != mode:
            continue
        day = found.group(2)
        if day not in outcomes.index:
            continue  # kỳ chưa quay, hoặc ngày không quay
        frame = pd.read_csv(path).set_index("number").reindex(range(100))
        p = pd.to_numeric(frame["prob"], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(p).all():
            continue  # artifact thiếu con: không chấm nửa vời
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
    """Kỹ năng logloss từng kỳ so với dự báo không thông tin (0 = bằng cơ sở)."""
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


@dataclass(frozen=True)
class SkillStatus:
    """Trạng thái kỹ năng ngoài mẫu của một chế độ trên cửa sổ gần nhất."""

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
        """``chua_du``, ``vung_0``, ``te_hon`` hoặc ``hon``."""
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
    """Kỹ năng trung bình và khoảng tin cậy trên ``window`` kỳ gần nhất."""
    recent = np.asarray(skills, dtype=float)[-window:]
    recent_days = list(days)[-window:]
    n = len(recent)
    mean = float(recent.mean()) if n else 0.0
    stderr = float(recent.std(ddof=1) / np.sqrt(n)) if n > 1 else float("inf")
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
        days, probs, labels = published_evaluation(data_dir, mode)
        out.append(status(days, daily_skill(mode, probs, labels), mode, window=window, z=z))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--z", type=float, default=DEFAULT_Z)
    args = parser.parse_args()

    checks = evaluate(Path(args.data_dir), window=args.window, z=args.z)
    for check in checks:
        print(check.describe())
    alarms = [check for check in checks if check.alarm]
    for check in alarms:
        print(f"::error::Kỹ năng ngoài mẫu {check.mode} rời vùng 0: {check.describe()}")
    return 1 if alarms else 0


if __name__ == "__main__":
    sys.exit(main())
