from __future__ import annotations

"""Phòng thí nghiệm cầu bóng trên TOÀN BỘ 107 ô chữ số của bảng kết quả.

Vì sao cần mô-đun này khi đã có :mod:`crosslag_positional_lab`
--------------------------------------------------------------
Mô-đun cũ đọc ``get_2_digits_data()``: mỗi giải chỉ còn HAI chữ số cuối, tức
27 ô. Nhưng cách vẽ cầu trong giới soi cầu nối những chữ số nằm BẤT KỲ đâu
bên trong số đầy đủ — chữ số hàng nghìn của một giải ba, chữ số giữa của giải
nhất. Bảng kết quả đầy đủ có 107 ô chữ số:

    Đặc Biệt 1×5, giải nhất 1×5, giải nhì 2×5, giải ba 6×5,
    giải tư 4×4, giải năm 6×4, giải sáu 3×3, giải bảy 4×2.

Ghép hai ô bất kỳ thành một số hai chữ số cho 107×107 = 11 449 cặp có hướng,
nhiều gấp 15,7 lần họ cũ. Đây là họ cầu chưa từng được quét trong dự án.

Hệ bóng
-------
Mỗi chữ số của cặp được phép đi qua một trong ba phép: giữ nguyên, bóng
dương, bóng âm. Chín tổ hợp cho cả cặp, bao trọn cả "bóng nửa" (chỉ đổi một
chữ số) lẫn bóng kép khi soi ở hai bước lag khác nhau.

    LƯU Ý về Ngũ Hành: Kim 2↔7, Mộc 5↔0, Thủy 1↔6, Hỏa 3↔8, Thổ 4↔9 chính
    là ÁNH XẠ BÓNG DƯƠNG, chỉ khác tên gọi. Nó không sinh thêm giả thuyết
    nào, nên không có phép riêng cho nó.

Rào chắn nghiên cứu
-------------------
Một họ 200 000+ giả thuyết thì CHẮC CHẮN sinh ra những đường cầu đẹp. Cái
quyết định không phải luật mạnh nhất, mà là luật mạnh nhất so với luật mạnh
nhất mà nhiễu thuần tạo ra trên cùng họ ấy. Nên mô-đun luôn chạy kèm:

- tra theo NGÀY LỊCH tuyệt đối, ngày nghỉ bị bỏ qua chứ không lùi tiếp;
- chia train / validation / holdout theo thời gian;
- nền đúng hình dạng cho từng loại đích;
- BH-FDR và Bonferroni trên toàn họ;
- kiểm tra thực tế bằng dịch vòng: giữ nguyên chữ số nguồn, dịch vòng chuỗi
  kết quả, quét lại TOÀN BỘ họ, rồi so thống kê cực đại. Đây là phép duy
  nhất bắt được ảo giác chọn lọc, và nó giữ nguyên tương quan giữa các luật
  vốn có chung ô nguồn.

Không có đường nối tự động nào sang trọng số vận hành.
"""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from dynamic_cau import PRIZE_LAYOUT
from lottery import Lottery
from number_reference import BONG_AM, BONG_DUONG
from research_diagnostics import bh_fdr

SCHEMA_VERSION = 1

#: Thứ tự giải đúng như bảng kết quả in ra.
PRIZE_ORDER: tuple[str, ...] = (
    "special", "prize1", "prize2", "prize3", "prize4", "prize5", "prize6", "prize7",
)

#: Phép biến đổi mức CHỮ SỐ. Tra bằng mảng 10 phần tử cho nhanh và cho đúng.
DIGIT_OPS: dict[str, np.ndarray] = {
    "goc": np.arange(10, dtype=np.int8),
    "duong": np.array([BONG_DUONG[d] for d in range(10)], dtype=np.int8),
    "am": np.array([BONG_AM[d] for d in range(10)], dtype=np.int8),
}

OP_NAMES: tuple[str, ...] = ("goc", "duong", "am")

#: Cặp lag mặc định: (lag của chữ số đầu, lag của chữ số sau), tính bằng NGÀY.
DEFAULT_LAG_PAIRS: tuple[tuple[int, int], ...] = ((1, 1), (1, 2))


def digit_slots() -> tuple[str, ...]:
    """Tên 107 ô chữ số, theo thứ tự cột của bảng kết quả.

    Tên có dạng ``prize3_4.d2`` — giải ba thứ tư, chữ số thứ ba từ trái. Tên
    phải ổn định vì nó là khoá của mọi kết quả ghi ra đĩa.
    """
    names: list[str] = []
    for prize in PRIZE_ORDER:
        count, width = PRIZE_LAYOUT[prize]
        for index in range(1, count + 1):
            column = prize if count == 1 else f"{prize}_{index}"
            names.extend(f"{column}.d{pos}" for pos in range(width))
    return tuple(names)


SLOT_NAMES: tuple[str, ...] = digit_slots()
N_SLOTS: int = len(SLOT_NAMES)


def digit_matrix(raw: pd.DataFrame) -> np.ndarray:
    """Trải bảng kết quả thành ma trận ``(số kỳ, 107)`` chữ số.

    Giá trị trong kho lưu dưới dạng số nguyên nên số 0 đứng đầu đã mất. Phải
    đệm lại theo ĐỘ RỘNG KHAI BÁO của từng giải, không theo độ dài chuỗi: giải
    bảy ``58`` là hai chữ số, còn ``5`` là ``05``. Đệm sai một chữ số là lệch
    toàn bộ hệ toạ độ.
    """
    out = np.empty((len(raw), N_SLOTS), dtype=np.int8)
    cursor = 0
    for prize in PRIZE_ORDER:
        count, width = PRIZE_LAYOUT[prize]
        for index in range(1, count + 1):
            column = prize if count == 1 else f"{prize}_{index}"
            text = raw[column].astype("int64").astype(str).str.zfill(width)
            if (text.str.len() != width).any():
                bad = text[text.str.len() != width].iloc[0]
                raise ValueError(f"{column}: giá trị {bad!r} dài hơn {width} chữ số")
            for pos in range(width):
                out[:, cursor] = text.str[pos].astype(np.int8)
                cursor += 1
    if cursor != N_SLOTS:
        raise ValueError(f"trải được {cursor} ô, chờ {N_SLOTS}")
    return out


def target_matrix(two_digits: pd.DataFrame, mode: str) -> np.ndarray:
    """Ma trận đích ``(số kỳ, 10, 10)``: ô ``[t, x, y]`` là số ``10x+y``.

    Tách theo ``mode`` vì hai đích có hình dạng nền hoàn toàn khác nhau —
    0,2378 cho lô so với 0,01 cho Đặc Biệt. Dùng chung một nền là sai số gấp
    hai mươi lần.
    """
    columns = [c for c in two_digits.columns if c != "date"]
    rows = len(two_digits)
    out = np.zeros((rows, 10, 10), dtype=np.float32)
    if mode == "loto":
        values = two_digits[columns].to_numpy(dtype=np.int64) % 100
        for t in range(rows):
            for value in values[t]:
                out[t, value // 10, value % 10] = 1.0
    elif mode == "de":
        values = two_digits["special"].to_numpy(dtype=np.int64) % 100
        out[np.arange(rows), values // 10, values % 10] = 1.0
    else:
        raise ValueError(f"mode không hợp lệ: {mode!r}")
    return out


@dataclass(frozen=True)
class ScanResult:
    """Kết quả quét một họ luật trên một lát cắt thời gian."""

    hits: np.ndarray      # (n_op_pairs * n_lag_pairs, 107, 107)
    trials: int
    labels: tuple[tuple[str, str, int, int], ...]


def _one_hot(codes: np.ndarray) -> np.ndarray:
    """``(T, 107)`` chữ số -> ``(107, T*10)`` one-hot đã làm phẳng.

    Làm phẳng trục (kỳ, chữ số) để phép cộng trên mọi cặp ô trở thành MỘT
    phép nhân ma trận. Cách ngây thơ — lặp qua 11 449 cặp — tốn 27 triệu lượt
    tra cho mỗi tổ hợp phép; ở đây còn 275 triệu phép nhân-cộng mà BLAS chạy
    trong khoảng một phần mười giây, nên chạy được cả 32 lần hoán vị.
    """
    days, slots = codes.shape
    flat = np.zeros((slots, days, 10), dtype=np.float32)
    day_index = np.arange(days)
    for slot in range(slots):
        flat[slot, day_index, codes[:, slot]] = 1.0
    return flat.reshape(slots, days * 10)


def scan_family(
    digits: np.ndarray,
    targets: np.ndarray,
    *,
    day_index: np.ndarray,
    lag_pairs: tuple[tuple[int, int], ...] = DEFAULT_LAG_PAIRS,
    op_names: tuple[str, ...] = OP_NAMES,
) -> ScanResult:
    """Đếm số lần trúng của MỌI luật trong họ, trên các kỳ được chỉ định.

    Args:
        digits: Ma trận chữ số ``(T, 107)``.
        targets: Ma trận đích ``(T, 10, 10)``.
        day_index: Chỉ số các kỳ ĐÍCH được tính, đã đảm bảo mọi lag tra được.
        lag_pairs: Các cặp lag theo ngày lịch.
        op_names: Các phép mức chữ số được phép dùng.

    Returns:
        :class:`ScanResult` với ``hits`` chỉ số ``[luật, ô_đầu, ô_sau]``.
    """
    blocks: list[np.ndarray] = []
    labels: list[tuple[str, str, int, int]] = []
    flat_targets = targets[day_index].reshape(len(day_index), 100)

    for lag_a, lag_b in lag_pairs:
        src_a = digits[day_index - lag_a]
        src_b = digits[day_index - lag_b]
        for op_b in op_names:
            hot_b = _one_hot(DIGIT_OPS[op_b][src_b])
            for op_a in op_names:
                coded_a = DIGIT_OPS[op_a][src_a]
                # left[slot, kỳ, y] = đích có số (chữ_số_a, y) ở kỳ ấy không.
                left = flat_targets.reshape(len(day_index), 10, 10)[
                    np.arange(len(day_index))[None, :], coded_a.T
                ]
                blocks.append(left.reshape(N_SLOTS, -1) @ hot_b.T)
                labels.append((op_a, op_b, lag_a, lag_b))

    return ScanResult(np.stack(blocks), len(day_index), tuple(labels))


def usable_days(dates: pd.Series, lag_pairs, warmup: int) -> np.ndarray:
    """Các kỳ mà MỌI lag đều tra được đúng ngày lịch.

    Trả về chỉ số hàng, và một mảng lag đã quy đổi sang khoảng cách hàng chỉ
    khi khoảng cách ấy trùng khít số ngày. XSMB có ngày nghỉ, nên lùi một hàng
    đôi khi là lùi hai ngày — để lọt chuyện đó là tự bịa ra một đường cầu.
    """
    stamps = pd.to_datetime(dates).dt.normalize()
    position = {stamp: i for i, stamp in enumerate(stamps)}
    max_lag = max(max(pair) for pair in lag_pairs)
    keep: list[int] = []
    for i in range(warmup, len(stamps)):
        if all(
            stamps.iloc[i] - pd.Timedelta(days=lag) in position
            and position[stamps.iloc[i] - pd.Timedelta(days=lag)] == i - lag
            for pair in lag_pairs
            for lag in pair
        ):
            keep.append(i)
    if not keep:
        raise ValueError("không còn kỳ nào tra đủ mọi lag")
    del max_lag
    return np.asarray(keep, dtype=np.int64)


def split_days(day_index: np.ndarray, dates: pd.Series, train_end: str, valid_end: str):
    """Chia ba lát theo thời gian. Holdout chỉ được chạm đúng một lần."""
    stamps = pd.to_datetime(dates).dt.normalize().to_numpy()
    picked = stamps[day_index]
    train = day_index[picked <= np.datetime64(train_end)]
    valid = day_index[(picked > np.datetime64(train_end)) & (picked <= np.datetime64(valid_end))]
    holdout = day_index[picked > np.datetime64(valid_end)]
    for name, part in (("train", train), ("validation", valid), ("holdout", holdout)):
        if len(part) == 0:
            raise ValueError(f"lát {name} rỗng — mốc chia nằm ngoài dải dữ liệu")
    return train, valid, holdout


def rule_table(result: ScanResult, base_rate: float) -> pd.DataFrame:
    """Bảng thống kê từng luật kèm p một phía và q của BH-FDR.

    Dùng kiểm định nhị thức chính xác chứ không xấp xỉ chuẩn: ở đích Đặc Biệt
    nền là 0,01 nên ``n·p`` chỉ khoảng 24, vùng mà xấp xỉ chuẩn lệch thấy rõ.
    """
    n_rules, slots_a, slots_b = result.hits.shape
    hits = result.hits.reshape(-1).astype(np.int64)
    trials = result.trials
    rule_id, slot_a, slot_b = np.unravel_index(
        np.arange(hits.size), (n_rules, slots_a, slots_b)
    )
    labels = np.array(result.labels, dtype=object)
    p_value = stats.binom.sf(hits - 1, trials, base_rate)
    table = pd.DataFrame(
        {
            "op_a": labels[rule_id, 0],
            "op_b": labels[rule_id, 1],
            "lag_a": labels[rule_id, 2].astype(int),
            "lag_b": labels[rule_id, 3].astype(int),
            "slot_a": np.asarray(SLOT_NAMES, dtype=object)[slot_a],
            "slot_b": np.asarray(SLOT_NAMES, dtype=object)[slot_b],
            "trials": trials,
            "hits": hits,
            "rate": hits / trials,
            "lift": (hits / trials) / base_rate,
            "p_value": p_value,
        }
    )
    table["q_value_fdr"] = bh_fdr(table["p_value"].to_numpy())
    table["p_bonferroni"] = np.clip(table["p_value"] * len(table), 0.0, 1.0)
    return table


def reality_check(
    digits: np.ndarray,
    targets: np.ndarray,
    *,
    day_index: np.ndarray,
    lag_pairs,
    permutations: int,
    seed: int,
) -> dict:
    """So lift lớn nhất QUAN SÁT được với lift lớn nhất của nhiễu trên CÙNG họ.

    Dịch vòng chuỗi kết quả mà giữ nguyên chữ số nguồn. Phép này phá huỷ mọi
    quan hệ nguồn-đích nhưng GIỮ NGUYÊN tương quan giữa các luật dùng chung ô
    nguồn, nên phân phối cực đại thu được là phân phối đúng để so sánh. Mô
    phỏng nhị thức độc lập sẽ cho đuôi rộng hơn thực tế và làm phép kiểm mất
    hiệu lực theo hướng khó thấy.
    """
    rng = np.random.default_rng(seed)
    base = float(targets[day_index].mean())
    observed = scan_family(digits, targets, day_index=day_index, lag_pairs=lag_pairs)
    observed_max = float(observed.hits.max() / observed.trials / base)

    null_max: list[float] = []
    total = len(targets)
    for _ in range(permutations):
        shift = int(rng.integers(1, total))
        shifted = np.roll(targets, shift, axis=0)
        trial = scan_family(digits, shifted, day_index=day_index, lag_pairs=lag_pairs)
        null_max.append(float(trial.hits.max() / trial.trials / base))

    nulls = np.asarray(null_max)
    return {
        "permutations": permutations,
        "base_rate": base,
        "observed_max_lift": observed_max,
        "null_max_lift_mean": float(nulls.mean()),
        "null_max_lift_p95": float(np.quantile(nulls, 0.95)),
        "null_max_lift_max": float(nulls.max()),
        "p_value": float((nulls >= observed_max).mean()),
        "method": "dịch vòng chuỗi kết quả, giữ nguyên chữ số nguồn",
    }


def rule_hits(digits, targets, day_index, rule) -> tuple[int, int]:
    """Số lần trúng của MỘT luật trên một lát cắt. Dùng để soi ngoài mẫu."""
    slot_a = SLOT_NAMES.index(rule["slot_a"])
    slot_b = SLOT_NAMES.index(rule["slot_b"])
    op_a, op_b = DIGIT_OPS[rule["op_a"]], DIGIT_OPS[rule["op_b"]]
    lag_a, lag_b = int(rule["lag_a"]), int(rule["lag_b"])
    x = op_a[digits[day_index - lag_a, slot_a]]
    y = op_b[digits[day_index - lag_b, slot_b]]
    return int(targets[day_index, x, y].sum()), len(day_index)


def follow_through(digits, targets, splits, table: pd.DataFrame, top: int) -> pd.DataFrame:
    """Lấy các luật MẠNH NHẤT TRÊN TRAIN rồi đo tiếp trên validation và holdout.

    Đây là phép đo trả lời đúng câu hỏi người soi cầu quan tâm: "cầu đang chạy
    thì có chạy tiếp không?". Chọn luật ở một lát và chấm ở lát khác là cách
    duy nhất tách được lợi thế thật khỏi ảo giác chọn lọc — một luật lift 1,18
    chọn bằng hậu nghiệm sẽ rơi về nền ở lát sau nếu nó chỉ là nhiễu.
    """
    train, valid, holdout = splits
    best = table.nlargest(top, "lift").copy()
    base_valid = float(targets[valid].mean())
    base_holdout = float(targets[holdout].mean())
    rows = []
    for _, rule in best.iterrows():
        hits_v, n_v = rule_hits(digits, targets, valid, rule)
        hits_h, n_h = rule_hits(digits, targets, holdout, rule)
        rows.append(
            {
                **{k: rule[k] for k in ("op_a", "op_b", "lag_a", "lag_b", "slot_a", "slot_b")},
                "train_lift": rule["lift"],
                "train_q_fdr": rule["q_value_fdr"],
                "validation_lift": (hits_v / n_v) / base_valid,
                "holdout_lift": (hits_h / n_h) / base_holdout,
                "validation_days": n_v,
                "holdout_days": n_h,
            }
        )
    del train
    return pd.DataFrame(rows)


def build(
    *,
    out_dir: Path,
    train_end: str = "2024-04-03",
    valid_end: str = "2025-06-25",
    lag_pairs=DEFAULT_LAG_PAIRS,
    permutations: int = 60,
    top: int = 50,
    warmup: int = 180,
    seed: int = 20260915,
) -> Path:
    """Chạy toàn bộ phòng thí nghiệm và ghi kết quả ra ``data/research/bong_bridge``."""
    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    if len(raw) != len(two):
        raise ValueError("bảng thô và bảng hai chữ số lệch số hàng")

    digits = digit_matrix(raw)
    day_index = usable_days(raw["date"], lag_pairs, warmup=warmup)
    splits = split_days(day_index, raw["date"], train_end, valid_end)
    out_dir.mkdir(parents=True, exist_ok=True)

    modes = {}
    for mode in ("loto", "de"):
        targets = target_matrix(two, mode)
        train = splits[0]
        scan = scan_family(digits, targets, day_index=train, lag_pairs=lag_pairs)
        base = float(targets[train].mean())
        table = rule_table(scan, base)
        survivors = follow_through(digits, targets, splits, table, top)
        survivors.to_csv(out_dir / f"top_rules_{mode}.csv", index=False)
        check = reality_check(
            digits, targets, day_index=train, lag_pairs=lag_pairs,
            permutations=permutations, seed=seed,
        )
        modes[mode] = {
            "mode": mode,
            "hypotheses": int(len(table)),
            "base_rate": base,
            "train_days": int(len(splits[0])),
            "validation_days": int(len(splits[1])),
            "holdout_days": int(len(splits[2])),
            "fdr_05_count": int((table["q_value_fdr"] < 0.05).sum()),
            "bonferroni_05_count": int((table["p_bonferroni"] < 0.05).sum()),
            "best_train_lift": float(table["lift"].max()),
            "best_train_followed_validation_lift": float(survivors["validation_lift"].iloc[0]),
            "best_train_followed_holdout_lift": float(survivors["holdout_lift"].iloc[0]),
            "top_mean_validation_lift": float(survivors["validation_lift"].mean()),
            "top_mean_holdout_lift": float(survivors["holdout_lift"].mean()),
            "reality_check": check,
        }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "anchor_date": str(pd.Timestamp(raw["date"].iloc[-1]).date()),
        "research_only": True,
        "production_wired": False,
        "digit_slots": N_SLOTS,
        "lag_pairs": [list(pair) for pair in lag_pairs],
        "digit_ops": list(OP_NAMES),
        "top_inspected": top,
        "modes": modes,
        "note": (
            "Họ cầu bóng trên toàn bộ 107 ô chữ số. Không có đường nối tự động "
            "nào sang trọng số vận hành; một luật qua được cổng chỉ có nghĩa là "
            "đáng xem xét thêm."
        ),
    }
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="data/research/bong_bridge")
    parser.add_argument("--permutations", type=int, default=60)
    parser.add_argument("--top", type=int, default=50)
    args = parser.parse_args()
    path = build(out_dir=Path(args.out_dir), permutations=args.permutations, top=args.top)
    print("Wrote:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
