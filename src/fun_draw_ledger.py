"""Sổ nhật ký bảng mô phỏng: bảng đã HIỆN trước giờ quay so với kết quả thật.

Mỗi kỳ đích một dòng. Phần mô phỏng chỉ được ghi (hoặc thay) khi còn TRƯỚC giờ
khoá của kỳ đó — 18:10 giờ Việt Nam, trước khi bắt đầu quay lúc 18:15. Sau giờ
khoá, dòng ấy đóng băng: một lượt pipeline chạy muộn không thể viết lại "dự
đoán" khi đã biết kết quả. Phần chấm (Đặc Biệt thật, trúng đúng, trúng lộn,
số vị trí LOTO có về) tính lại được bất cứ lúc nào từ ``data/xsmb.csv``.

Sổ nằm ở ``data/fun_draw/ledger.csv``, ngoài các thư mục ``cleanup_artifacts``
dọn, nên giữ được lâu hơn hạn 45 ngày của artifact.

Lịch sử trước khi có sổ được nạp lại từ các phiên bản
``data/predict/fun_draw_next.json`` trong git bằng ĐÚNG luật khoá ấy
(``python3 src/fun_draw_ledger.py --backfill-from-git``).
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from xsmb_domain import DE_BASELINE_RATE, LOTO_BASELINE_RATE, PRIZE_FIELDS

LEDGER = Path("fun_draw") / "ledger.csv"
VN = timezone(timedelta(hours=7))
#: Giờ khoá theo giờ Việt Nam; kỳ quay XSMB bắt đầu 18:15.
CUTOFF_HOUR, CUTOFF_MINUTE = 18, 10

SIM_COLUMNS = [
    "target_date",
    "anchor_date",
    "special",
    "suffix",
    "model_prob",
    "model_rank",
    "loto",
    "source",
    "recorded_at_utc",
]
OUTCOME_COLUMNS = ["actual_special", "exact", "reversed", "loto_hits"]
COLUMNS = SIM_COLUMNS + OUTCOME_COLUMNS


def cutoff_utc(target_date: str) -> datetime:
    """Giờ khoá của kỳ ``target_date`` (UTC)."""
    y, m, d = (int(part) for part in target_date.split("-"))
    local = datetime(y, m, d, CUTOFF_HOUR, CUTOFF_MINUTE, tzinfo=VN)
    return local.astimezone(timezone.utc)


def reverse_of(suffix: str) -> str:
    return suffix[::-1]


def simulation_row(
    payload: dict[str, Any],
    de_probs: dict[int, float] | None,
    *,
    source: str,
    recorded_at: datetime,
) -> dict[str, Any]:
    """Một dòng sổ từ payload của ``build_fun_prediction.build_fun_draw``."""
    special = payload["groups"][0]["values"][0]
    loto = [item["suffix"] for group in payload["groups"][1:] for item in group["values"]]
    rank: int | str = ""
    if de_probs:
        suffix = int(special["suffix"])
        # Hạng 1 = xác suất cao nhất; hoà thì số nhỏ đứng trước, như top_de.
        ordered = sorted(de_probs, key=lambda n: (-de_probs[n], n))
        rank = ordered.index(suffix) + 1
    return {
        "target_date": str(payload["target_date"]),
        "anchor_date": str(payload["anchor_date"]),
        "special": str(special["value"]),
        "suffix": str(special["suffix"]),
        "model_prob": float(special["model_prob"]),
        "model_rank": rank,
        "loto": " ".join(loto),
        "source": source,
        "recorded_at_utc": recorded_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def empty_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def read_ledger(data_dir: Path) -> pd.DataFrame:
    path = data_dir / LEDGER
    if not path.exists() or path.stat().st_size == 0:
        return empty_ledger()
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[COLUMNS]


def write_ledger(frame: pd.DataFrame, data_dir: Path) -> Path:
    path = data_dir / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = frame[COLUMNS].sort_values("target_date").reset_index(drop=True)
    frame.to_csv(path, index=False)
    return path


def record(frame: pd.DataFrame, row: dict[str, Any], now: datetime) -> pd.DataFrame:
    """Ghi bảng mô phỏng của một kỳ nếu còn trước giờ khoá; sau giờ khoá thì bỏ qua.

    Trước giờ khoá, bảng mới THAY bảng cũ của cùng kỳ: người xem lúc quay thấy
    bản cuối cùng, nên đó là bản phải chấm.
    """
    if now >= cutoff_utc(row["target_date"]):
        return frame
    kept = frame[frame["target_date"] != row["target_date"]]
    fresh = pd.DataFrame([{**{c: "" for c in COLUMNS}, **{k: str(v) for k, v in row.items()}}])
    return pd.concat([kept, fresh], ignore_index=True)[COLUMNS]


def load_results(xsmb_csv: Path) -> dict[str, list[str]]:
    """Ngày -> 27 giải theo thứ tự in (chuỗi, đã đệm đủ chữ số)."""
    from xsmb_domain import FIELD_WIDTH_MAP

    frame = pd.read_csv(xsmb_csv, dtype=str, keep_default_na=False)
    results: dict[str, list[str]] = {}
    for record_ in frame.to_dict("records"):
        values = []
        for field in PRIZE_FIELDS:
            raw = str(record_.get(field, "")).strip()
            if not raw.isdigit():
                break
            values.append(raw.zfill(FIELD_WIDTH_MAP[field]))
        else:
            results[str(record_["date"])] = values
    return results


def score(frame: pd.DataFrame, results: dict[str, list[str]]) -> pd.DataFrame:
    """Điền phần chấm cho mọi kỳ đã có kết quả. Chạy lại cho cùng kết quả."""
    frame = frame.copy()
    for i, row in frame.iterrows():
        prizes = results.get(row["target_date"])
        if prizes is None:
            for column in OUTCOME_COLUMNS:
                frame.at[i, column] = ""
            continue
        actual = prizes[0][-2:]
        suffix = row["suffix"]
        loto_actual = {p[-2:] for p in prizes}
        frame.at[i, "actual_special"] = prizes[0]
        frame.at[i, "exact"] = str(int(actual == suffix))
        frame.at[i, "reversed"] = str(int(actual != suffix and actual == reverse_of(suffix)))
        frame.at[i, "loto_hits"] = str(sum(n in loto_actual for n in row["loto"].split()))
    return frame


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    """Tổng hợp các kỳ đã chấm, kèm kỳ vọng nếu chỉ là ngẫu nhiên."""
    scored = frame[frame["actual_special"] != ""]
    positions = int(sum(len(r.split()) for r in scored["loto"]))
    not_double = int(sum(s != reverse_of(s) for s in scored["suffix"]))
    return {
        "days": len(scored),
        "exact": int(scored["exact"].astype(int).sum()) if len(scored) else 0,
        "reversed": int(scored["reversed"].astype(int).sum()) if len(scored) else 0,
        "expected_exact": len(scored) * DE_BASELINE_RATE,
        "expected_reversed": not_double * DE_BASELINE_RATE,
        "loto_hits": int(scored["loto_hits"].astype(int).sum()) if len(scored) else 0,
        "loto_positions": positions,
        "expected_loto_hits": positions * LOTO_BASELINE_RATE,
        "first_day": str(scored["target_date"].min()) if len(scored) else "",
        "last_day": str(scored["target_date"].max()) if len(scored) else "",
    }


def recent(frame: pd.DataFrame, limit: int = 10) -> list[dict[str, str]]:
    """Các kỳ mới nhất trước (kể cả kỳ chưa quay)."""
    rows = frame.sort_values("target_date", ascending=False).head(limit)
    return [{c: str(r[c]) for c in COLUMNS} for _, r in rows.iterrows()]


def update(
    data_dir: Path,
    payload: dict[str, Any],
    de_probs: dict[int, float] | None,
    now: datetime,
) -> pd.DataFrame:
    """Ghi bảng vừa dựng (nếu còn trước giờ khoá), chấm mọi kỳ đã quay, lưu sổ."""
    frame = read_ledger(data_dir)
    row = simulation_row(payload, de_probs, source="pipeline", recorded_at=now)
    frame = record(frame, row, now)
    frame = score(frame, load_results(data_dir / "xsmb.csv"))
    write_ledger(frame, data_dir)
    return frame


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def backfill_from_git(repo: Path, data_dir: Path, ref: str = "HEAD") -> pd.DataFrame:
    """Nạp lại các kỳ chưa có trong sổ từ lịch sử git của ``fun_draw_next.json``.

    Đi theo thời gian commit, áp đúng ``record``: bản cuối cùng commit TRƯỚC giờ
    khoá của kỳ là bản được ghi; bản commit sau giờ khoá bị bỏ.
    """
    existing = read_ledger(data_dir)
    known = set(existing["target_date"])
    frame = empty_ledger()
    rel = "data/predict/fun_draw_next.json"
    log = _git(repo, "log", ref, "--reverse", "--format=%H %cI", "--", rel)
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, stamp = line.split()
        when = datetime.fromisoformat(stamp)
        try:
            payload = json.loads(_git(repo, "show", f"{sha}:{rel}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        target = str(payload.get("target_date", ""))
        if not target or target in known:
            continue
        de_probs = None
        try:
            de = pd.read_csv(
                io.StringIO(
                    _git(repo, "show", f"{sha}:data/predict/predict_next_de_all_{target}.csv")
                )
            )
            de_probs = {int(n): float(p) for n, p in zip(de["number"], de["prob"], strict=True)}
        except (subprocess.CalledProcessError, KeyError, ValueError):
            pass
        row = simulation_row(payload, de_probs, source="git", recorded_at=when)
        frame = record(frame, row, when)
    merged = pd.concat([existing, frame], ignore_index=True)[COLUMNS]
    merged = score(merged, load_results(data_dir / "xsmb.csv"))
    write_ledger(merged, data_dir)
    return merged


def main() -> None:
    ap = argparse.ArgumentParser(description="Sổ nhật ký bảng mô phỏng so với kết quả thật.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--backfill-from-git", action="store_true")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ref", default="HEAD")
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    if args.backfill_from_git:
        frame = backfill_from_git(Path(args.repo), data_dir, args.ref)
    else:
        frame = score(read_ledger(data_dir), load_results(data_dir / "xsmb.csv"))
        write_ledger(frame, data_dir)
    print(json.dumps(summarize(frame), ensure_ascii=False))


if __name__ == "__main__":
    main()
