"""Confidence Score ba tầng cho kỳ kế tiếp: Bayes · Markov · cầu, hiệu chỉnh đa kiểm.

Vì sao không lấy thẳng hậu nghiệm Bayes làm "độ tin cậy"
--------------------------------------------------------
Hậu nghiệm P(p > nền | dữ liệu) của MỘT con là đúng về toán. Nhưng ta nhìn 100
con cùng lúc rồi chọn con đẹp nhất, và con đẹp nhất của một lịch sử HOÀN TOÀN
ngẫu nhiên thường vẫn đạt "99 %": đo trên 10 000 lịch sử công bằng cùng cỡ
với kho, 60 % lịch sử có ít nhất một con như thế. Gắn nhãn "tin cậy 99 %" cho
nó là báo động giả gần như chắc chắn.

Cách làm ở đây
--------------
Mỗi thống kê được tính trên dữ liệu thật và trên ``DEFAULT_SIMS`` lịch sử giả
lập công bằng (cùng số kỳ, 27 giải, mỗi giải 00-99 đều nhau). Tin cậy của một
tín hiệu là tỉ lệ lịch sử công bằng mà thống kê LỚN NHẤT của cả họ giả thuyết
còn nhỏ hơn nó — tức 1 − p hiệu chỉnh đa kiểm. Ba thành phần cho mỗi con:

* Bayes  — hậu nghiệm Beta với prior tâm ở tỉ lệ nền.
* Markov — xác suất về theo đúng trạng thái hôm qua của con đó.
* Cầu    — cầu vị trí tốt nhất (54 × 54 chữ số đuôi) ghép ra con đó từ kỳ cuối.

Luật tầng (theo yêu cầu của chủ dự án): High khi CẢ BA > 85 %; Medium khi ít
nhất hai thành phần ≥ 60 %; còn lại Low/Noise.

Phân phối null tốn ~8 phút trên 4 lõi, nên được lưu thành phân vị trong
``data/confidence/null_quantiles.json`` và chỉ tính lại khi số kỳ trôi quá
``REFRESH_DRIFT`` hoặc định nghĩa thống kê đổi (``STAT_VERSION``). Phần dữ liệu
thật chạy mỗi lượt pipeline, vì trạng thái "hôm qua" đổi mỗi ngày.

Mô-đun chỉ ĐỌC dữ liệu và dự báo đã công bố; không đổi phép tính, mô hình hay
hợp đồng dữ liệu nào đang có.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

#: Xác suất một con về ít nhất một lần trong 27 giải của một kỳ công bằng.
BASE = 1 - 0.99**27
#: Prior Beta "ngây thơ": 100 kỳ giả, tâm ở tỉ lệ nền.
PRIOR_N = 100.0
#: Mốc chia mẫu học / mẫu kiểm cho phép kiểm ngoài mẫu.
SPLIT = "2024-01-01"
DEFAULT_SIMS = 10_000
SEED = 20260928
#: Tăng khi đổi định nghĩa bất kỳ thống kê nào trong :func:`stats`.
STAT_VERSION = 2
#: Số kỳ trôi quá tỉ lệ này thì tính lại phân phối null.
REFRESH_DRIFT = 0.02
#: Số điểm phân vị lưu cho mỗi họ: độ phân giải tin cậy 0,1 %.
QUANTILES = 1001
HIGH, MEDIUM = 0.85, 0.60
OUT = Path("confidence")
NULL_FILE = "null_quantiles.json"
REPORT_FILE = "report.json"

NAMES = [
    "freq_absz_max", "freq_chi2", "bayes_post_max", "bayes60_post_max",
    "markov_z_max", "markov_absz_max", "pair_z_max", "cau_loto_max", "cau_de_max",
    "cusum_max", "distinct_cusum", "year_persist", "de_chi2", "de_bayes_post_max",
    "de_markov_z_max", "de_to_loto", "freq_z_max", "markov_state_max",
]

#: Tên hiển thị và cỡ họ của từng thống kê, theo đúng thứ tự trình bày.
FAMILIES = [
    ("freq_z_max", "Tần suất LOTO — con về nhiều nhất (z)", 100),
    ("freq_chi2", "Tần suất LOTO — χ² toàn bảng", 1),
    ("bayes_post_max", "Bayes LOTO — hậu nghiệm cao nhất", 100),
    ("bayes60_post_max", "Bayes LOTO 60 kỳ gần nhất — hậu nghiệm cao nhất", 100),
    ("markov_z_max", "Markov LOTO — về rồi về lại (z)", 100),
    ("pair_z_max", "Bạc nhớ i hôm nay → j ngày mai (z)", 10_000),
    ("cau_loto_max", "Cầu vị trí → LOTO — tỉ lệ trúng cao nhất", 2_916),
    ("cau_de_max", "Cầu vị trí → Đặc Biệt — tỉ lệ trúng cao nhất", 2_916),
    ("de_chi2", "Tần suất Đặc Biệt — χ²", 1),
    ("de_bayes_post_max", "Bayes Đặc Biệt — hậu nghiệm cao nhất", 100),
    ("de_markov_z_max", "Đầu Đặc Biệt hôm qua → Đặc Biệt hôm nay (z)", 1_000),
    ("de_to_loto", "Đặc Biệt hôm nay → về LOTO ngày mai", 1),
    ("cusum_max", "Xu hướng dài hạn / đứt gãy từng con (CUSUM)", 100),
    ("year_persist", "Số nóng năm trước còn nóng năm sau", 1),
    ("distinct_cusum", "Đứt gãy cấu trúc: số con khác nhau mỗi kỳ", 1),
]

PRIZE_COLUMNS = [
    "special", "prize1", "prize2_1", "prize2_2", "prize3_1", "prize3_2", "prize3_3",
    "prize3_4", "prize3_5", "prize3_6", "prize4_1", "prize4_2", "prize4_3", "prize4_4",
    "prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6", "prize6_1",
    "prize6_2", "prize6_3", "prize7_1", "prize7_2", "prize7_3", "prize7_4",
]
#: Số chữ số của từng giải trong bảng kết quả đầy đủ (107 vị trí).
PRIZE_WIDTH = {"special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
               "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2}


# ---------------------------------------------------------------------------
# Thống kê — cùng một hàm cho dữ liệu thật và lịch sử giả lập
# ---------------------------------------------------------------------------


def hits_matrix(draws: np.ndarray) -> np.ndarray:
    """(T, 100) 0/1: con có về trong kỳ hay không."""
    rows = draws.shape[0]
    hits = np.zeros((rows, 100), dtype=np.uint8)
    hits[np.arange(rows)[:, None], draws] = 1
    return hits


def digits(draws: np.ndarray) -> np.ndarray:
    """54 vị trí chữ số: hàng chục rồi hàng đơn vị của 27 giải."""
    return np.concatenate([draws // 10, draws % 10], axis=1).astype(np.int16)


def cau_hits(dig: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Số lần trúng của 54 × 54 cầu vị trí: số = 10·D[t,p] + D[t,q], trúng ở t+1."""
    idx = (10 * dig[:-1, :, None] + dig[:-1, None, :]).reshape(dig.shape[0] - 1, -1)
    return np.take_along_axis(target[1:], idx, axis=1).sum(axis=0, dtype=np.int32)


def _safe(values: np.ndarray) -> np.ndarray:
    return np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)


def stats(draws: np.ndarray) -> dict[str, np.ndarray | float]:
    """Mọi thống kê của một lịch sử (T kỳ × 27 giải, giá trị 0-99)."""
    from scipy.stats import beta

    rows = draws.shape[0]
    hits = hits_matrix(draws)
    special = np.zeros((rows, 100), dtype=np.uint8)
    special[np.arange(rows), draws[:, 0]] = 1
    dig = digits(draws)
    out: dict[str, np.ndarray | float] = {}

    with np.errstate(divide="ignore", invalid="ignore"):
        k = hits.sum(axis=0).astype(float)
        out["freq_z"] = (k - rows * BASE) / np.sqrt(rows * BASE * (1 - BASE))
        out["freq_chi2"] = float(((k - rows * BASE) ** 2 / (rows * BASE)).sum())
        a0, b0 = PRIOR_N * BASE, PRIOR_N * (1 - BASE)
        out["bayes_post"] = beta.sf(BASE, a0 + k, b0 + rows - k)
        recent = min(60, rows)
        k60 = hits[-recent:].sum(axis=0).astype(float)
        out["bayes60_post"] = beta.sf(BASE, a0 + k60, b0 + recent - k60)

        prev, nxt = hits[:-1].astype(float), hits[1:].astype(float)
        n1 = prev.sum(axis=0)
        n0 = (rows - 1) - n1
        p11 = (prev * nxt).sum(axis=0) / n1
        p01 = ((1 - prev) * nxt).sum(axis=0) / n0
        pp = nxt.mean(axis=0)
        se = np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n0))
        out["markov_z"] = _safe((p11 - p01) / se)
        out["markov_p11"], out["markov_p01"] = _safe(p11), _safe(p01)
        # Điểm Markov THEO TRẠNG THÁI KỲ CUỐI: về thì z, trượt thì −z. Thành
        # phần Markov của ma trận chấm đúng điểm này, nên null phải là max của
        # CHÍNH nó — review PR #104: so −z với max z chưa đổi dấu là so hai
        # thống kê khác nhau.
        out["markov_state"] = np.where(hits[-1] == 1, out["markov_z"], -out["markov_z"])

        pairs = prev.T @ nxt
        expected = np.outer(n1, pp)
        out["pair_z"] = _safe((pairs - expected) / np.sqrt(expected * (1 - pp)[None, :]))

        out["cau_loto"] = cau_hits(dig, hits) / (rows - 1)
        out["cau_de"] = cau_hits(dig, special) / (rows - 1)

        walk = np.cumsum(hits - BASE, axis=0)
        out["cusum"] = np.abs(walk).max(axis=0) / np.sqrt(rows * BASE * (1 - BASE))
        distinct = hits.sum(axis=1).astype(float)
        spread = distinct.var() if distinct.var() > 0 else 1.0
        out["distinct_cusum"] = float(
            np.abs(np.cumsum(distinct - 100 * BASE)).max() / np.sqrt(rows * spread)
        )

        blocks = [hits[i : i + 365].sum(axis=0) for i in range(0, rows - 364, 365)]
        cors = [np.corrcoef(blocks[i], blocks[i + 1])[0, 1] for i in range(len(blocks) - 1)]
        out["year_persist"] = float(np.nan_to_num(np.mean(cors))) if cors else 0.0

        ks = special.sum(axis=0).astype(float)
        out["de_chi2"] = float(((ks - rows / 100) ** 2 / (rows / 100)).sum())
        out["de_bayes_post"] = beta.sf(0.01, 1 + ks, 99 + rows - ks)
        tens = draws[:, 0] // 10
        moves = np.zeros((10, 100))
        np.add.at(moves, (tens[:-1], draws[1:, 0]), 1)
        row_totals = moves.sum(axis=1, keepdims=True)
        moves_expected = row_totals / 100
        out["de_markov_z"] = _safe((moves - moves_expected) / np.sqrt(moves_expected * 0.99))
        out["de_to_loto"] = float(hits[1:][np.arange(rows - 1), draws[:-1, 0]].mean())
    return out


def summarize(values: dict) -> np.ndarray:
    """Thống kê LỚN NHẤT trên mỗi họ giả thuyết — thứ phân phối null cần."""
    return np.array([
        np.abs(values["freq_z"]).max(),
        values["freq_chi2"],
        values["bayes_post"].max(),
        values["bayes60_post"].max(),
        values["markov_z"].max(),
        np.abs(values["markov_z"]).max(),
        values["pair_z"].max(),
        values["cau_loto"].max(),
        values["cau_de"].max(),
        values["cusum"].max(),
        values["distinct_cusum"],
        values["year_persist"],
        values["de_chi2"],
        values["de_bayes_post"].max(),
        values["de_markov_z"].max(),
        values["de_to_loto"],
        values["freq_z"].max(),
        values["markov_state"].max(),
    ])


# ---------------------------------------------------------------------------
# Phân phối null: mô phỏng, nén thành phân vị, lưu và tái dùng
# ---------------------------------------------------------------------------


def _worker(args: tuple[np.random.SeedSequence, int, int]) -> np.ndarray:
    seed, count, rows = args
    rng = np.random.default_rng(seed)
    return np.stack([summarize(stats(rng.integers(0, 100, size=(rows, 27)))) for _ in range(count)])


def simulate_null(rows: int, sims: int = DEFAULT_SIMS, *, workers: int = 4, seed: int = SEED) -> np.ndarray:
    """``sims`` lịch sử công bằng ``rows`` kỳ; trả mảng (sims, len(NAMES))."""
    if sims < 1:
        raise ValueError(f"cần ít nhất 1 lịch sử mô phỏng, nhận {sims}")
    chunks = min(40, sims)
    sizes = [sims // chunks + (1 if i < sims % chunks else 0) for i in range(chunks)]
    seeds = np.random.SeedSequence(seed).spawn(chunks)
    jobs = [(s, n, rows) for s, n in zip(seeds, sizes, strict=True) if n]
    if workers <= 1:
        parts = [_worker(job) for job in jobs]
    else:
        with Pool(workers) as pool:
            parts = pool.map(_worker, jobs)
    return np.concatenate(parts)


def null_quantiles(null: np.ndarray, rows: int) -> dict:
    """Nén phân phối null thành ``QUANTILES`` phân vị mỗi họ."""
    levels = np.linspace(0.0, 1.0, QUANTILES)
    # Phân vị lấy đúng GIÁ TRỊ MẪU ("inverted_cdf") để mỗi điểm lưới là một
    # giá trị null có thật; nội suy chỉ lệch tối đa một điểm lưới (0,1%).
    return {
        "version": STAT_VERSION,
        "draws": int(rows),
        "sims": int(len(null)),
        "seed": SEED,
        "quantiles": {
            # Đủ độ chính xác, KHÔNG làm tròn. Tỉ lệ trúng cầu nhảy bậc 1/T nên
            # null đầy giá trị HOÀ, và thống kê thật hoà với chúng đúng từng bit
            # vì đi cùng một phép tính. Làm tròn 7 chữ số đặt cả khối hoà ngay
            # dưới tín hiệu nên nó bị đếm là "nhỏ hơn": đo trên kho thật, cầu
            # Đặc Biệt lên 66,5% thay vì 50,7% — báo tin cậy cao hơn thật.
            name: [float(v) for v in np.quantile(null[:, i], levels, method="inverted_cdf")]
            for i, name in enumerate(NAMES)
        },
    }


def needs_refresh(cached: dict | None, rows: int, sims: int = DEFAULT_SIMS) -> bool:
    """Tính lại khi chưa có, khác phiên bản thống kê, khác số mô phỏng được yêu
    cầu (review PR #104: ``--sims`` từng bị lặng lẽ bỏ qua), hay số kỳ trôi quá
    ngưỡng."""
    if not cached or cached.get("version") != STAT_VERSION:
        return True
    if cached.get("sims") != sims:
        return True
    if set(cached.get("quantiles", {})) != set(NAMES):
        return True
    drawn = cached.get("draws") or 0
    return drawn <= 0 or abs(rows - drawn) / drawn > REFRESH_DRIFT


def load_null(data_dir: Path, rows: int, *, sims: int = DEFAULT_SIMS, workers: int = 4,
              force: bool = False) -> dict:
    """Đọc phân vị null đã lưu, tính lại khi cần."""
    path = data_dir / OUT / NULL_FILE
    cached = None
    if path.exists() and not force:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
    if force or needs_refresh(cached, rows, sims):
        cached = null_quantiles(simulate_null(rows, sims, workers=workers), rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cached, ensure_ascii=False) + "\n", encoding="utf-8")
    return cached


def confidence(null: dict, name: str, value: float) -> float:
    """Tỉ lệ lịch sử công bằng có thống kê lớn nhất của họ nhỏ hơn ``value``."""
    grid = np.asarray(null["quantiles"][name])
    return float(np.searchsorted(grid, value, side="left") / len(grid))


def cm_grid_len(null: dict) -> int:
    """Số điểm lưới phân vị đã lưu (mọi họ cùng một lưới)."""
    return len(next(iter(null["quantiles"].values())))


def tier(components: dict[str, float]) -> tuple[str, float]:
    """Luật ba tầng. Score = thành phần yếu nhất (High) hoặc mạnh thứ hai."""
    ranked = sorted(components.values(), reverse=True)
    if ranked[-1] > HIGH:
        return "High", ranked[-1]
    second = ranked[1] if len(ranked) > 1 else 0.0
    if second >= MEDIUM:
        return "Medium", second
    return "Low/Noise", second


# ---------------------------------------------------------------------------
# Giả thuyết can thiệp: nếu kỳ quay bị sắp đặt, dấu vết nào phải hiện ra?
# ---------------------------------------------------------------------------


def _raw_digit_counts(raw: pd.DataFrame) -> list[tuple[str, np.ndarray]]:
    """Đếm chữ số 0-9 ở từng vị trí trong 107 vị trí của bảng kết quả đầy đủ."""
    out = []
    for column in PRIZE_COLUMNS:
        width = PRIZE_WIDTH[column.split("_")[0]]
        text = raw[column].astype(int).astype(str).str.zfill(width)
        for pos in range(width):
            counts = np.bincount(text.str[pos].astype(int), minlength=10)[:10]
            out.append((f"{column}[{pos + 1}]", counts))
    return out


#: Số lịch sử công bằng để hiệu chỉnh các phép kiểm "né" (rẻ: vài giây).
INTERVENTION_SIMS = 10_000
REPEAT_WINDOW = 7


def repeat_counts(special: np.ndarray, window: int = REPEAT_WINDOW) -> np.ndarray:
    """Số kỳ mà Đặc Biệt trùng một trong ``window`` Đặc Biệt ngay trước nó.

    Nhận (T,) hoặc (S, T). Các cửa sổ chồng lên nhau, nên các chỉ báo KHÔNG
    độc lập — review PR #104: tổng của chúng không theo phân phối nhị thức.
    """
    seq = np.atleast_2d(special)
    rows = seq.shape[1]
    hit = np.zeros((seq.shape[0], max(rows - window, 0)), dtype=bool)
    for k in range(1, window + 1):
        hit |= seq[:, window:] == seq[:, window - k : rows - k]
    return hit.sum(axis=1)


def hot_counts(draws: np.ndarray) -> np.ndarray:
    """Số kỳ mà Đặc Biệt là một con vừa về LOTO kỳ trước. Nhận (T, 27) hoặc (S, T, 27)."""
    arr = draws if draws.ndim == 3 else draws[None]
    return (arr[:, :-1, :] == arr[:, 1:, 0:1]).any(axis=-1).sum(axis=-1)


def intervention_null(rows: int, sims: int = INTERVENTION_SIMS, *, seed: int = SEED + 1) -> dict:
    """Phân phối của hai số đếm "né" trên ``sims`` lịch sử công bằng ``rows`` kỳ."""
    if sims < 1:
        raise ValueError(f"cần ít nhất 1 lịch sử mô phỏng, nhận {sims}")
    rng = np.random.default_rng(seed)
    repeat, hot = [], []
    for start in range(0, sims, 500):
        size = min(500, sims - start)
        batch = rng.integers(0, 100, size=(size, rows, 27), dtype=np.int8)
        repeat.append(repeat_counts(batch[:, :, 0]))
        hot.append(hot_counts(batch))
    return {"repeat": np.concatenate(repeat), "hot": np.concatenate(hot)}


def mc_two_sided_p(observed: float, simulated: np.ndarray) -> float:
    """p hai phía: tỉ lệ lịch sử công bằng lệch khỏi trung bình ít nhất bằng thật."""
    centre = float(np.mean(simulated))
    far = np.abs(simulated - centre) >= abs(observed - centre) - 1e-9
    return float((far.sum() + 1) / (len(simulated) + 1))


def intervention_tests(raw: pd.DataFrame, draws: np.ndarray, *,
                       sims: int = INTERVENTION_SIMS) -> dict:
    """Những dấu vết mà một kỳ quay bị sắp đặt THƯỜNG để lại trên kết quả công bố.

    Không phép kiểm nào chứng minh được "không có can thiệp". Chúng trả lời câu
    hỏi hẹp hơn nhưng là câu duy nhất có ích cho người đọc: can thiệp, nếu có,
    có để lại dấu vết nào trên kết quả công bố mà người ngoài khai thác được
    không.
    """
    from scipy.stats import chi2

    rows = len(draws)
    tests = []

    positions = _raw_digit_counts(raw)
    per = []
    for label, counts in positions:
        expect = counts.sum() / 10
        per.append((label, float(((counts - expect) ** 2 / expect).sum())))
    worst_label, worst = max(per, key=lambda item: item[1])
    p_single = float(chi2.sf(worst, 9))
    p_family = float(1 - (1 - p_single) ** len(per))
    total = sum(value for _, value in per)
    p_total = float(chi2.sf(total, 9 * len(per)))
    tests.append({
        "key": "digits",
        "label": f"Chữ số 0-9 đều nhau ở cả {len(per)} vị trí",
        "detail": f"vị trí lệch nhất {worst_label}: χ²={worst:.1f} (9 bậc tự do); "
                  f"tổng χ²={total:.0f} ({9 * len(per)} bậc tự do)",
        # Hai thống kê (lệch nhất và tổng) cho cùng một câu hỏi: Bonferroni ×2.
        "p": min(1.0, 2 * min(p_family, p_total)),
    })

    special = draws[:, 0]
    # Hai số đếm dưới đây dùng cửa sổ/kỳ chồng nhau nên không phải tổng của
    # phép thử độc lập: p lấy từ chính phân phối của chúng trên lịch sử công bằng.
    null = intervention_null(rows, sims)
    repeats = int(repeat_counts(special)[0])
    trials = rows - REPEAT_WINDOW
    tests.append({
        "key": "special_repeat",
        "label": f"Đặc Biệt né con đã ra trong {REPEAT_WINDOW} kỳ trước",
        "detail": f"{repeats}/{trials} kỳ lặp lại ({repeats / trials:.2%}), "
                  f"lịch sử công bằng trung bình {float(null['repeat'].mean()) / trials:.2%}",
        "p": mc_two_sided_p(repeats, null["repeat"]),
    })

    observed = int(hot_counts(draws)[0])
    tests.append({
        "key": "special_avoids_hot",
        "label": "Đặc Biệt né con vừa về LOTO hôm trước",
        "detail": f"{observed}/{rows - 1} kỳ ({observed / (rows - 1):.2%}), "
                  f"lịch sử công bằng trung bình {float(null['hot'].mean()) / (rows - 1):.2%}",
        "p": mc_two_sided_p(observed, null["hot"]),
    })

    weekdays = pd.to_datetime(raw["date"]).dt.weekday.to_numpy()
    table = np.zeros((7, 10))
    np.add.at(table, (weekdays, special // 10), 1)
    expected = table.sum(axis=1, keepdims=True) * table.sum(axis=0, keepdims=True) / table.sum()
    stat = float(((table - expected) ** 2 / expected).sum())
    tests.append({
        "key": "weekday",
        "label": "Đầu Đặc Biệt theo thứ trong tuần",
        "detail": f"χ²={stat:.1f} (54 bậc tự do)",
        "p": float(chi2.sf(stat, 54)),
    })

    # Holm cho 4 phép kiểm của nhóm này.
    order = sorted(range(len(tests)), key=lambda i: tests[i]["p"])
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, tests[i]["p"] * (len(tests) - rank)))
        tests[i]["p_holm"] = running
    return {"tests": tests, "positions": len(per)}


# ---------------------------------------------------------------------------
# Báo cáo
# ---------------------------------------------------------------------------


def cluster_z(hits: np.ndarray, trials: np.ndarray, p: float) -> float:
    """z của tổng lượt trúng, với phương sai ước lượng THEO TỪNG KỲ QUAY.

    Các lượt trúng trong cùng một kỳ không độc lập: mười con LOTO cùng chia 27
    giải, còn các cầu Đặc Biệt loại trừ nhau hoặc trùng nhau khi ghép ra cùng
    một con. ``sqrt(n·p·(1−p))`` vì thế đo sai phương sai (review PR #104).
    Dưới giả thuyết công bằng các KỲ độc lập với nhau, nên lấy mỗi kỳ làm một
    cụm: z = Σ(h_t − n_t·p) / sqrt(Σ(h_t − n_t·p)²).
    """
    dev = np.asarray(hits, dtype=float) - np.asarray(trials, dtype=float) * p
    scale = float(np.sqrt((dev**2).sum()))
    return float(dev.sum() / scale) if scale > 0 else 0.0


def cau_hit_matrix(dig: np.ndarray, target: np.ndarray) -> np.ndarray:
    """(T-1, 2916): cầu nào trúng ở kỳ nào — giữ từng kỳ để tính phương sai cụm."""
    idx = (10 * dig[:-1, :, None] + dig[:-1, None, :]).reshape(dig.shape[0] - 1, -1)
    return np.take_along_axis(target[1:], idx, axis=1)


def out_of_sample(draws: np.ndarray, dates: pd.Series) -> list[dict]:
    """Tín hiệu mạnh nhất chọn trên 2015-2023 còn lại gì ở 2024-nay."""
    cut = int((dates < SPLIT).sum())
    if cut < 400 or len(draws) - cut < 60:
        return []
    train = stats(draws[:cut])
    hits = hits_matrix(draws)
    test = hits[cut:].astype(int)
    rows = []

    def add(key, label, per_hit, per_n, base, in_sample=None):
        hit, n = int(np.sum(per_hit)), int(np.sum(per_n))
        rows.append({"key": key, "label": label, "hits": hit, "n": n,
                     "rate": float(hit / n) if n else 0.0, "base": base,
                     "z": cluster_z(per_hit, per_n, base), "in_sample": in_sample})

    top = np.argsort(-train["bayes_post"])[:10]
    add("bayes", "10 con hậu nghiệm Bayes cao nhất", test[:, top].sum(axis=1),
        np.full(len(test), 10), BASE, float(hits[:cut, top].mean()))
    top = np.argsort(-train["markov_z"])[:10]
    prev, nxt = test[:-1, top], test[1:, top]
    add("markov", "10 con Markov mạnh nhất, sau khi vừa về", (prev * nxt).sum(axis=1),
        prev.sum(axis=1), BASE, float(train["markov_p11"][top].mean()))
    flat = np.argsort(-train["pair_z"], axis=None)[:50]
    a, b = np.unravel_index(flat, (100, 100))
    add("pairs", "50 cặp bạc nhớ mạnh nhất", (test[:-1, a] * test[1:, b]).sum(axis=1),
        test[:-1, a].sum(axis=1), BASE)

    dig = digits(draws)[cut - 1 :]
    special = np.zeros_like(hits)
    special[np.arange(len(draws)), draws[:, 0]] = 1
    for key, label, target, base in (
        ("cau_loto", "20 cầu vị trí LOTO tốt nhất", hits[cut - 1 :], BASE),
        ("cau_de", "20 cầu vị trí Đặc Biệt tốt nhất", special[cut - 1 :], 0.01),
    ):
        sel = np.argsort(-train[key])[:20]
        per_day = cau_hit_matrix(dig, target)[:, sel].sum(axis=1)
        add(key, label, per_day, np.full(len(dig) - 1, 20), base, float(train[key][sel].mean()))

    flat = np.argsort(-train["de_markov_z"], axis=None)[:20]
    r, c = np.unravel_index(flat, (10, 100))
    tens = draws[cut - 1 : -1, 0] // 10
    nxt_de = draws[cut:, 0]
    per_n = (tens[:, None] == r[None, :]).sum(axis=1)
    per_hit = ((tens[:, None] == r[None, :]) & (nxt_de[:, None] == c[None, :])).sum(axis=1)
    add("de_markov", "20 ô chuyển đầu Đặc Biệt mạnh nhất", per_hit, per_n, 0.01)
    return rows


#: Nguồn của các con "đang công bố", theo thứ tự ưu tiên.
PICK_SOURCES = {
    "top10": "trang 10 số LOTO / 10 số Đặc Biệt",
    "home": "dự đoán trang chủ",
}


def _top10(data_dir: Path, mode: str, day: str) -> list[str]:
    path = data_dir / "predict" / f"predict_next_{mode}_top10_{day}.csv"
    try:
        frame = pd.read_csv(path, usecols=["number"])
    except (OSError, ValueError):
        return []
    return [str(int(n)).zfill(2) for n in frame["number"]]


def _target_date(data_dir: Path, last: str) -> tuple[str, list[str], list[str], str | None]:
    """Kỳ đích và các con đã công bố cho nó.

    Ưu tiên tệp top-10 mà CHÍNH pipeline vừa ghi cho kỳ tới
    (``predict_nextday_2d``, chạy trước bước dựng trang). ``predictions_today.json``
    do workflow dự đoán ghi SAU pipeline, nên lúc pipeline dựng trang nó vẫn trỏ
    vào kỳ vừa quay — review PR #104: đọc nó trước thì sau lượt cập nhật đầu tiên
    trang không còn gắn với dự báo nào. Nó chỉ là dự phòng khi trỏ đúng kỳ tới.
    """
    nxt = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
    pattern = "predict_next_loto_top10_*.csv"
    ahead = sorted(
        day for day in (p.stem.rsplit("_", 1)[-1] for p in (data_dir / "predict").glob(pattern))
        if day > last
    ) if (data_dir / "predict").is_dir() else []
    if ahead:
        day = ahead[0]
        return day, _top10(data_dir, "loto", day), _top10(data_dir, "de", day), "top10"
    try:
        pred = json.loads((data_dir / "predictions_today.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return nxt, [], [], None
    if str(pred.get("date", "")) <= last:
        return nxt, [], [], None
    lo = [str(r["number"]).zfill(2) for r in pred.get("top_lo_to", []) if "number" in r]
    de = [str(n).zfill(2) for n in (pred.get("top_dac_biet") or {}).get("top_numbers", [])]
    return str(pred["date"]), lo, de, "home"


def forecast_scores(mode: str, probs: np.ndarray, labels: np.ndarray) -> dict:
    """Log-loss, Brier và MAE của một dãy dự báo, theo đúng quy ước của kho.

    Đặc Biệt là MỘT kết quả trong 100 lớp: log-loss −log(q con về), Brier và
    MAE cộng qua 100 lớp — cùng thang với trang Chất lượng mô hình và
    ``skill_monitor`` (review PR #104). LOTO là 100 biến nhị phân: trung bình
    theo từng ô. Dùng chung cho trang lẫn script nghiên cứu để hai nơi không
    thể lệch nhau.
    """
    eps = 1e-12
    if mode == "de":
        return {
            "logloss": float(-np.log((probs * labels).sum(axis=1) + eps).mean()),
            "brier": float(((probs - labels) ** 2).sum(axis=1).mean()),
            "mae": float(np.abs(probs - labels).sum(axis=1).mean()),
        }
    return {
        "logloss": float(-(labels * np.log(probs + eps)
                           + (1 - labels) * np.log(1 - probs + eps)).mean()),
        "brier": float(((probs - labels) ** 2).mean()),
        "mae": float(np.abs(probs - labels).mean()),
    }


def published_feedback(data_dir: Path) -> dict:
    """Vòng phản hồi: vector ĐÃ công bố so với kết quả quay thật."""
    import skill_monitor as sm

    out = {"monitor": [check.as_dict() for check in sm.evaluate(data_dir)], "modes": {}}
    for mode in sm.MODES:
        days, probs, labels = sm.published_evaluation(data_dir, mode)
        if not len(days):
            continue
        model = forecast_scores(mode, probs, labels)
        base = forecast_scores(mode, np.full_like(probs, sm.baseline_rate(mode)), labels)
        out["modes"][mode] = {
            "days": len(days), "first": days[0], "last": days[-1],
            **{f"{k}_model": v for k, v in model.items()},
            **{f"{k}_base": v for k, v in base.items()},
        }
    return out


def _hot_tail_status(data_dir: Path) -> dict:
    """Ghi các kỳ mới vào sổ cái giả thuyết "đuôi nóng" rồi trả trạng thái."""
    import hot_tail_test

    hot_tail_test.update_ledger(data_dir)
    return hot_tail_test.evaluate(data_dir)


def _digit_sum_status(data_dir: Path) -> dict:
    """Ghi các kỳ mới vào sổ cái năm quy tắc "tổng – bóng – chạm" rồi trả trạng thái."""
    import digit_sum_hypothesis

    digit_sum_hypothesis.update_ledger(data_dir)
    return digit_sum_hypothesis.evaluate(data_dir)


def build_report(data_dir: Path, null: dict) -> dict:
    """Phần dữ liệu thật: họ giả thuyết, ma trận quyết định, rủi ro, phản hồi."""
    frame = pd.read_csv(data_dir / "xsmb-2-digits.csv", dtype={"date": str})
    draws = frame[PRIZE_COLUMNS].to_numpy().astype(int)
    dates = frame["date"]
    rows = len(draws)
    values = stats(draws)
    observed = summarize(values)
    col = {n: i for i, n in enumerate(NAMES)}

    # p nhỏ nhất đo được: 1/(N+1) với N lịch sử — review PR #104: lưới 1 001
    # phân vị không được cho 100 mô phỏng "đo" tới p ≈ 0,001.
    p_floor = max(1.0 / (int(null.get("sims") or 0) + 1), 1.0 / cm_grid_len(null))
    families = []
    for key, label, size in FAMILIES:
        obs = float(observed[col[key]])
        grid = null["quantiles"][key]
        families.append({
            "key": key, "label": label, "size": size, "observed": obs,
            "null_median": grid[len(grid) // 2], "null_p95": grid[int(0.95 * (len(grid) - 1))],
            "p": max(1.0 - confidence(null, key, obs), p_floor),
        })

    last = str(dates.iloc[-1])
    target, lo_picks, de_picks, pick_source = _target_date(data_dir, last)
    dig_last = digits(draws)[-1]
    best = {"loto": np.zeros(100), "de": np.zeros(100)}
    grids = {"loto": values["cau_loto"].reshape(54, 54), "de": values["cau_de"].reshape(54, 54)}
    for p in range(54):
        for q in range(54):
            num = 10 * dig_last[p] + dig_last[q]
            for mode in best:
                best[mode][num] = max(best[mode][num], grids[mode][p, q])

    tens_y = int(draws[-1, 0] // 10)
    matrix = []
    for mode in ("loto", "de"):
        for i in range(100):
            if mode == "loto":
                bayes = float(values["bayes_post"][i])
                markov = float(values["markov_state"][i])
                comps = {
                    "bayes": confidence(null, "bayes_post_max", bayes),
                    "markov": confidence(null, "markov_state_max", markov),
                    "cau": confidence(null, "cau_loto_max", best["loto"][i]) if best["loto"][i] else 0.0,
                }
            else:
                bayes = float(values["de_bayes_post"][i])
                markov = float(values["de_markov_z"][tens_y, i])
                comps = {
                    "bayes": confidence(null, "de_bayes_post_max", bayes),
                    "markov": confidence(null, "de_markov_z_max", markov),
                    "cau": confidence(null, "cau_de_max", best["de"][i]) if best["de"][i] else 0.0,
                }
            label, score = tier(comps)
            matrix.append({
                "mode": mode, "number": f"{i:02d}", "naive_bayes": bayes, "markov_signal": markov,
                "cau_rate": float(best[mode][i]), **{f"c_{k}": v for k, v in comps.items()},
                "tier": label, "score": score,
                "published": f"{i:02d}" in (lo_picks if mode == "loto" else de_picks),
            })

    counts = {m: {t: 0 for t in ("High", "Medium", "Low/Noise")} for m in ("loto", "de")}
    for row in matrix:
        counts[row["mode"]][row["tier"]] += 1

    rng = np.random.default_rng(int(target.replace("-", "")))
    sim = rng.integers(0, 100, size=(10_000, 27))
    picks = np.array([int(x) for x in lo_picks] or [
        int(r["number"]) for r in sorted(
            (r for r in matrix if r["mode"] == "loto"), key=lambda r: -r["score"])[:10]
    ])
    got = (sim[:, :, None] == picks[None, None, :]).any(axis=1).sum(axis=1)
    occurrences = (sim[:, :, None] == picks[None, None, :]).sum(axis=(1, 2))
    risk = {
        "picks": [f"{p:02d}" for p in picks],
        "picks_source": PICK_SOURCES.get(pick_source) if lo_picks else None,
        "scenarios": int(len(sim)),
        "numbers_hit": np.bincount(got, minlength=len(picks) + 1).tolist(),
        "mean_occurrences": float(occurrences.mean()),
        "breakeven_loto": 100 / 27,
        "breakeven_de": 100.0,
        "de_hit_share": float(np.isin(sim[:, 0], [int(x) for x in de_picks]).mean()) if de_picks else None,
    }

    raw_path = data_dir / "xsmb.csv"
    intervention = None
    if raw_path.exists():
        raw = pd.read_csv(raw_path, dtype={"date": str})
        if len(raw) == rows:
            intervention = intervention_tests(raw, draws)

    naive = {
        "bayes_99": 1 - confidence(null, "bayes_post_max", 0.99),
        "bayes_95": 1 - confidence(null, "bayes_post_max", 0.95),
        "bayes60_85": 1 - confidence(null, "bayes60_post_max", 0.85),
    }
    return {
        "generated_for": target,
        "last_draw": last,
        "draws": rows,
        "first_draw": str(dates.iloc[0]),
        "null": {k: null[k] for k in ("sims", "draws", "seed", "version")},
        "p_floor": p_floor,
        "thresholds": {"high": HIGH, "medium": MEDIUM},
        "families": families,
        "naive_false_alarm": naive,
        "out_of_sample": out_of_sample(draws, pd.Series(dates)),
        "counts": counts,
        "max_component": {
            m: {c: max(r[f"c_{c}"] for r in matrix if r["mode"] == m) for c in ("bayes", "markov", "cau")}
            for m in ("loto", "de")
        },
        "matrix": matrix,
        "risk": risk,
        "intervention": intervention,
        "feedback": published_feedback(data_dir),
        "hot_tail": _hot_tail_status(data_dir),
        "digit_sum": _digit_sum_status(data_dir),
    }


def run(data_dir: Path, *, sims: int = DEFAULT_SIMS, workers: int = 4, force: bool = False) -> Path:
    """Tính (hoặc tái dùng) null, dựng báo cáo, ghi ``data/confidence/report.json``."""
    frame = pd.read_csv(data_dir / "xsmb-2-digits.csv", usecols=["date"])
    null = load_null(data_dir, len(frame), sims=sims, workers=workers, force=force)
    report = build_report(data_dir, null)
    path = data_dir / OUT / REPORT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--sims", type=int, default=DEFAULT_SIMS)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="tính lại phân phối null")
    args = parser.parse_args()
    if args.sims < 1:
        parser.error("--sims phải ≥ 1")
    print("Wrote:", run(args.data_dir, sims=args.sims, workers=args.workers, force=args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
