"""Soi cầu vị trí: ghép hai chữ số của kỳ hôm trước, xem kỳ sau có về không.

Quy ước (đã đối chiếu từng con số với một trang soi cầu công khai, ngày 29-09-2026)
--------------------------------------------------------------------------------
* 107 vị trí chữ số của bảng kết quả, đánh số từ 0 theo thứ tự ĐB (0-4), G1
  (5-9), G2 (10-19), G3 (20-49), G4 (50-65), G5 (66-89), G6 (90-98), G7
  (99-106). ``vt=6x22`` là chữ số thứ 2 của G1 ghép với chữ số thứ 3 của G3.1.
* Cầu (a, b) ở kỳ t cho số ``10·d[a] + d[b]``. Khi "lộn" thì cho cả cặp
  {ab, ba} và chỉ xét a < b; khi không lộn thì thứ tự có nghĩa (``95x74`` khác
  ``74x95``). Số kép (hai chữ số bằng nhau) là MỘT số.
* Kỳ t+1 "trúng" khi: LOTO — tổng số lần về của các số trong cặp ≥ ``nhay``
  (lộn thì CỘNG GỘP: 45 về một lần và 54 về một lần là 2 nháy); Đặc Biệt — hai
  số cuối của giải ĐB nằm trong cặp.
* Cầu "chạy N ngày" khi N kỳ liên tiếp gần nhất đều trúng. Liên tiếp theo KỲ
  QUAY, không theo lịch — kỳ nghỉ Tết không có kỳ nào để trượt.
* Số kép được hiện KÈM số bóng (0↔5, 1↔6, 2↔7, 3↔8, 4↔9: 44 → 99) cho người
  quen đọc cặp kép–bóng. Số bóng KHÔNG tham gia phép dò: tính nó vào thì dữ
  liệu 28-09 cho 64 cầu LOTO chứ không phải 43 như trang đối chiếu.

Đối chiếu ngày 29-09-2026 (dữ liệu đến 28-09): 43 cầu LOTO ≥ 5 ngày (18 cầu > 5
ngày, 27 cặp số, 16 cặp chạy hơn 5 ngày), 14 cầu 2 nháy ≥ 3 ngày (11 cặp),
132 cầu Đặc Biệt ≥ 1 ngày (29 cặp; 47,74 có 18 cầu), 7 cầu LOTO không lộn ≥ 5
ngày — trùng từng con số, từng vị trí và thứ tự "Thống kê cầu lặp".

Phép tính ở đây là MÔ TẢ. ``streak_backtest`` và ``consensus_backtest`` đo trên
toàn lịch sử xem cầu càng dài, hay càng nhiều cầu cùng báo một cặp, thì kỳ sau
có trúng nhiều hơn không — câu hỏi mà "cầu dài hơn đáng tin hơn" giả định sẵn
câu trả lời.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

#: (cột, số giải, số chữ số) theo đúng thứ tự in trên bảng kết quả.
LAYOUT = [
    ("special", 1, 5), ("prize1", 1, 5), ("prize2", 2, 5), ("prize3", 6, 5),
    ("prize4", 4, 4), ("prize5", 6, 4), ("prize6", 3, 3), ("prize7", 4, 2),
]
PRIZE_LABEL = {"special": "ĐB", "prize1": "G1", "prize2": "G2", "prize3": "G3",
               "prize4": "G4", "prize5": "G5", "prize6": "G6", "prize7": "G7"}
COLUMNS = [p if n == 1 else f"{p}_{i + 1}" for p, n, _ in LAYOUT for i in range(n)]
WIDTHS = [w for _, n, w in LAYOUT for _ in range(n)]
N_POS = sum(WIDTHS)  # 107

#: Số bóng của từng chữ số: 0↔5, 1↔6, 2↔7, 3↔8, 4↔9.
SHADOW = (5, 6, 7, 8, 9, 0, 1, 2, 3, 4)

#: Ba chế độ của ba ô "đẹp nhất" — cùng tham số với trang đối chiếu.
MODES = {
    "lo": {"title": "Cầu Lotto", "nhay": 1, "db": False, "lon": True, "limit": 5},
    "nhay2": {"title": "Cầu 2 nháy", "nhay": 2, "db": False, "lon": True, "limit": 3},
    "db": {"title": "Cầu Đặc Biệt", "nhay": 1, "db": True, "lon": True, "limit": 1},
}
BEST_COUNT = 10
#: Số kỳ nhúng vào trang và số kỳ dùng để đếm độ dài cầu — CÙNG một cửa sổ, để
#: bộ máy trong trình duyệt và bản Python đếm ra cùng một con số.
WINDOW = 60
MAX_STREAK = 10
CONSENSUS_BUCKETS = ((1, 1), (2, 2), (3, 3), (4, 5), (6, 9), (10, None))
OUT = Path("position_bridges")


def positions() -> list[dict]:
    """Nhãn người đọc của 107 vị trí: giải, số thứ mấy trong giải, chữ số thứ mấy."""
    out = []
    for prize, count, width in LAYOUT:
        for i in range(count):
            column = prize if count == 1 else f"{prize}_{i + 1}"
            label = PRIZE_LABEL[prize] + (f".{i + 1}" if count > 1 else "")
            for d in range(width):
                out.append({"index": len(out), "value_index": COLUMNS.index(column),
                            "digit": d, "label": f"{label} · chữ số {d + 1}"})
    return out


def load_draws(raw: pd.DataFrame) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Ngày, ma trận chữ số (T, 107) và giá trị đầy đủ (T, 27) theo thứ tự kỳ."""
    raw = raw.sort_values("date").reset_index(drop=True)
    values = raw[COLUMNS].to_numpy().astype(np.int64)
    digits = np.zeros((len(raw), N_POS), dtype=np.int8)
    col = 0
    for j, width in enumerate(WIDTHS):
        for d in range(width):
            digits[:, col] = (values[:, j] // 10 ** (width - 1 - d)) % 10
            col += 1
    return [str(x)[:10] for x in raw["date"]], digits, values


def pair_index(lon: bool) -> tuple[np.ndarray, np.ndarray]:
    """Mọi cặp vị trí: a < b khi lộn (thứ tự không quan trọng), a ≠ b khi không."""
    a, b = np.meshgrid(np.arange(N_POS), np.arange(N_POS), indexing="ij")
    mask = a < b if lon else a != b
    return a[mask], b[mask]


def _numbers(digits: np.ndarray, pa: np.ndarray, pb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = digits[:, pa].astype(np.int16)
    y = digits[:, pb].astype(np.int16)
    return 10 * x + y, 10 * y + x


def hit_matrix(digits: np.ndarray, values: np.ndarray, *, nhay: int, db: bool,
               lon: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(T-1, P): cầu p dựng từ kỳ t có trúng ở kỳ t+1 không. Kèm chỉ số cặp."""
    pa, pb = pair_index(lon)
    n1, n2 = _numbers(digits[:-1], pa, pb)
    two = values[1:] % 100
    if db:
        special = two[:, :1]
        hit = special == n1
        if lon:
            hit |= special == n2
        return hit, pa, pb
    counts = np.zeros((len(two), 100), dtype=np.int16)
    np.add.at(counts, (np.arange(len(two))[:, None], two), 1)
    rows = np.arange(len(two))[:, None]
    total = counts[rows, n1]
    if lon:
        total = total + np.where(n1 != n2, counts[rows, n2], 0)
    return total >= nhay, pa, pb


def run_lengths(hits: np.ndarray) -> np.ndarray:
    """(T-1, P): số kỳ trúng liên tiếp tính đến hết kỳ t."""
    runs = np.zeros(hits.shape, dtype=np.int16)
    current = np.zeros(hits.shape[1], dtype=np.int16)
    for t in range(hits.shape[0]):
        current = np.where(hits[t], current + 1, 0).astype(np.int16)
        runs[t] = current
    return runs


def predicted(digits_row: np.ndarray, a: int, b: int, lon: bool) -> list[str]:
    """Số cầu (a, b) báo cho kỳ kế tiếp, theo thứ tự trang đối chiếu in ra."""
    x, y = int(digits_row[a]), int(digits_row[b])
    nums = [10 * x + y] if not lon or x == y else [10 * x + y, 10 * y + x]
    return [f"{n:02d}" for n in nums]


def shadow(numbers: list[str]) -> str | None:
    """Số bóng của một số kép (44 → 99); số không kép thì không có."""
    if len(numbers) != 1 or numbers[0][0] != numbers[0][1]:
        return None
    d = SHADOW[int(numbers[0][0])]
    return f"{d}{d}"


def pair_key(nums: list[str]) -> str:
    """Khoá của cặp số: tăng dần, nên 83,38 và 38,83 là MỘT cặp."""
    return ",".join(sorted(nums))


def find_bridges(digits: np.ndarray, values: np.ndarray, *, nhay: int, db: bool, lon: bool,
                 limit: int, exact: bool = False) -> list[dict]:
    """Cầu đang chạy tính đến kỳ cuối, độ dài ≥ ``limit`` (hoặc đúng bằng).

    Xếp như trang đối chiếu: theo số đầu tiên cầu báo, rồi theo vị trí.
    """
    tail = min(len(digits), WINDOW)
    hits, pa, pb = hit_matrix(digits[-tail:], values[-tail:], nhay=nhay, db=db, lon=lon)
    streak = run_lengths(hits)[-1]
    keep = streak == limit if exact else streak >= limit
    out = []
    for p in np.flatnonzero(keep):
        a, b = int(pa[p]), int(pb[p])
        numbers = predicted(digits[-1], a, b, lon)
        out.append({"vt": f"{a}x{b}", "a": a, "b": b, "streak": int(streak[p]),
                    "numbers": numbers, "shadow": shadow(numbers)})
    out.sort(key=lambda r: (r["numbers"][0], r["a"], r["b"]))
    return out


def summarize(bridges: list[dict], limit: int) -> dict:
    """Thống kê như trang đối chiếu: số cầu, cầu dài hơn ngưỡng, cặp số, cầu lặp.

    "Cầu lặp" xếp theo số cầu giảm dần; hoà thì cặp nào xuất hiện trước trong
    danh sách cầu (đã xếp theo số) đứng trước — đúng thứ tự trang đối chiếu.
    """
    by_pair: dict[str, list[dict]] = {}
    for bridge in bridges:
        by_pair.setdefault(pair_key(bridge["numbers"]), []).append(bridge)
    repeats = sorted(by_pair.items(), key=lambda kv: -len(kv[1]))
    return {
        "count": len(bridges),
        "longer": sum(b["streak"] > limit for b in bridges),
        "pairs": len(by_pair),
        "pairs_longer": sum(any(b["streak"] > limit for b in v) for v in by_pair.values()),
        "repeats": [{"pair": k, "bridges": len(v)} for k, v in repeats],
    }


def best(bridges: list[dict]) -> list[dict]:
    """Mười cầu "đẹp nhất": mỗi cặp số một cầu, xếp theo độ dài, rồi số cầu cùng báo
    cặp ấy, rồi vị trí. Quy tắc tự đặt và công khai — trang đối chiếu không nói nó
    xếp thế nào, và ``consensus_backtest`` cho thấy cả hai tiêu chí đều không nâng
    tỉ lệ trúng."""
    counts: dict[str, int] = {}
    for bridge in bridges:
        key = pair_key(bridge["numbers"])
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(bridges, key=lambda b: (-b["streak"], -counts[pair_key(b["numbers"])], b["a"], b["b"]))
    chosen, seen = [], set()
    for bridge in ranked:
        key = pair_key(bridge["numbers"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append({**bridge, "same_pair": counts[key]})
        if len(chosen) == BEST_COUNT:
            break
    return chosen


def history(digits: np.ndarray, values: np.ndarray, *, nhay: int, db: bool, lon: bool) -> tuple:
    """Mỗi (kỳ s, cặp vị trí): độ dài cầu tính đến kỳ s, cầu từ kỳ s có trúng kỳ
    s+1 không, số báo có phải số kép không, và khoá cặp số. Tính MỘT lần cho cả
    hai phép kiểm lịch sử."""
    hits, pa, pb = hit_matrix(digits, values, nhay=nhay, db=db, lon=lon)
    runs = run_lengths(hits)
    n1, n2 = _numbers(digits[1:-1], pa, pb)
    kep = n1 == n2
    key = np.minimum(n1, n2) * 100 + np.maximum(n1, n2) if lon else n1.astype(np.int32)
    return runs[:-1], hits[1:], kep, key


def _type_rates(nxt: np.ndarray, kep: np.ndarray) -> tuple[float, float]:
    """Tỉ lệ trúng của cầu báo số kép và cầu báo số thường, trên MỌI cầu mọi kỳ.

    Số kép chỉ là một số nên dễ trượt hơn nhiều (LOTO ~24% so với ~42%). Kỳ vọng
    của từng hàng tính theo đúng tỉ lệ kép trong hàng ấy, để một hàng nhiều số
    kép không bị đọc nhầm là "cầu yếu".
    """
    n_kep = int(kep.sum())
    rate_kep = float(nxt[kep].sum() / n_kep) if n_kep else 0.0
    n_pair = int((~kep).sum())
    rate_pair = float(nxt[~kep].sum() / n_pair) if n_pair else 0.0
    return rate_kep, rate_pair


def _row(label: dict, n: int, hits: int, expected: float, dev: np.ndarray, days: int) -> dict:
    scale = float(np.sqrt((dev ** 2).sum()))
    return {**label, "n": n, "hits": hits,
            "rate": hits / n if n else None,
            "expected": expected / n if n else None,
            "z": float(dev.sum() / scale) if scale > 0 else 0.0,
            "days": days}


def streak_backtest(history: tuple, max_streak: int = MAX_STREAK) -> dict:
    """Toàn lịch sử: cầu đã chạy k kỳ thì kỳ kế tiếp trúng bao nhiêu phần trăm?

    Nếu cầu dài báo hiệu điều gì, tỉ lệ trúng phải TĂNG theo k. Hàng ``k = 0`` là
    mọi cặp vị trí vừa trượt — mốc so sánh cùng điều kiện. ``z`` so với kỳ vọng
    của chính hàng ấy; mỗi kỳ là một cụm vì các cầu cùng kỳ dùng chung 27 giải.
    """
    prev, nxt, kep, _ = history
    rate_kep, rate_pair = _type_rates(nxt, kep)
    days, width = prev.shape[0], max_streak + 1
    # Một chỉ số (kỳ, k) cho mỗi ô rồi cộng bằng bincount: nhanh gấp chục lần
    # so với dựng mười một mặt nạ trên ma trận 4 000 × 5 700.
    cell = (np.arange(days, dtype=np.int64)[:, None] * width
            + np.minimum(prev, max_streak).astype(np.int64)).ravel()
    size = days * width
    n = np.bincount(cell, minlength=size).reshape(days, width)
    got = np.bincount(cell, weights=nxt.ravel(), minlength=size).reshape(days, width)
    n_kep = np.bincount(cell, weights=kep.ravel(), minlength=size).reshape(days, width)
    exp = n_kep * rate_kep + (n - n_kep) * rate_pair
    rows = []
    for k in range(width):
        rows.append(_row({"k": k, "plus": k == max_streak}, int(n[:, k].sum()), int(round(got[:, k].sum())),
                         float(exp[:, k].sum()), got[:, k] - exp[:, k], int((n[:, k] > 0).sum())))
    return {"base_rate": float(nxt.mean()), "rate_kep": rate_kep, "rate_pair": rate_pair,
            "draws": int(nxt.shape[0]), "rows": rows}


def consensus_backtest(history: tuple, limit: int) -> dict:
    """Toàn lịch sử: một cặp số có m cầu ≥ ``limit`` ngày cùng báo thì kỳ sau trúng
    bao nhiêu phần trăm? Đơn vị là CẶP SỐ trong một kỳ, không phải cầu — m cầu
    cùng báo một cặp chỉ là một lần trúng hoặc trượt."""
    prev, nxt, kep, key = history
    rate_kep, rate_pair = _type_rates(nxt, kep)
    size = int(key.max()) + 1
    buckets = [{"n": 0, "hits": 0, "expected": 0.0, "dev": [], "days": 0} for _ in CONSENSUS_BUCKETS]
    for s in range(prev.shape[0]):
        on = prev[s] >= limit
        if not on.any():
            continue
        keys = key[s][on]
        count = np.bincount(keys, minlength=size)
        outcome = np.zeros(size, dtype=bool)
        outcome[keys] = nxt[s][on]
        is_kep = np.zeros(size, dtype=bool)
        is_kep[keys] = kep[s][on]
        present = np.flatnonzero(count)
        for bucket, (lo, hi) in zip(buckets, CONSENSUS_BUCKETS, strict=True):
            inside = count[present] >= lo
            if hi is not None:
                inside &= count[present] <= hi
            sel = present[inside]
            if not len(sel):
                continue
            exp = float(np.where(is_kep[sel], rate_kep, rate_pair).sum())
            got = int(outcome[sel].sum())
            bucket["n"] += len(sel)
            bucket["hits"] += got
            bucket["expected"] += exp
            bucket["dev"].append(got - exp)
            bucket["days"] += 1
    rows = [_row({"from": lo, "to": hi}, b["n"], b["hits"], b["expected"],
                 np.array(b["dev"], dtype=float), b["days"])
            for b, (lo, hi) in zip(buckets, CONSENSUS_BUCKETS, strict=True)]
    return {"limit": limit, "rows": rows}


def build(data_dir: Path) -> dict:
    raw = pd.read_csv(data_dir / "xsmb.csv", dtype={"date": str})
    dates, digits, values = load_draws(raw)
    last = dates[-1]
    target = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
    report = {"source_date": last, "target_date": target, "window": WINDOW,
              "draws": [{"date": d, "values": [str(int(v)).zfill(w) for v, w in zip(row, WIDTHS, strict=True)]}
                        for d, row in zip(dates[-WINDOW:], values[-WINDOW:], strict=True)],
              "modes": {}}
    for key, cfg in MODES.items():
        params = {"nhay": cfg["nhay"], "db": cfg["db"], "lon": cfg["lon"]}
        bridges = find_bridges(digits, values, limit=cfg["limit"], **params)
        past = history(digits, values, **params)
        report["modes"][key] = {
            **cfg,
            "summary": summarize(bridges, cfg["limit"]),
            "best": best(bridges),
            "streaks": streak_backtest(past),
            "consensus": consensus_backtest(past, cfg["limit"]),
        }
        del past
    return report


def run(data_dir: Path) -> Path:
    path = data_dir / OUT / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(data_dir), ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    print("Wrote:", run(args.data_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
