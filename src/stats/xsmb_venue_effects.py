"""Đài quay miền Bắc: kết quả có khác nhau theo đài không, và xác suất riêng từng đài có chuẩn hơn không.

Câu hỏi
-------
Mỗi ngày XSMB mang tên một «đài» theo lịch luân phiên (``core.xsmb_schedule``). Từ 01-09-2005 mọi đài
dùng MỘT lần quay chung do Công ty XSKT Thủ Đô tổ chức, nên giả thuyết gốc là: tên đài không đổi cách
ra số. Module này đo giả thuyết ấy trên sổ chuẩn và chỉ cho phép xác suất theo đài thay xác suất chung
khi nó thắng ngoài mẫu.

Ba phần, mỗi phần trả lời một câu
---------------------------------
1. **Phân phối có khác nhau giữa các đài (và giữa các thứ) không?** Năm thống kê: số lần ra của 100 con
   LOTO, 2 số cuối Đặc Biệt, chữ số ở từng vị trí trong 107 vị trí, chữ số theo lồng (cột đơn vị, chục,
   trăm, nghìn, chục nghìn của mỗi giải), và số con LOTO khác nhau mỗi kỳ. Giá trị p bằng HOÁN VỊ nhãn
   đài giữa các kỳ: giữ nguyên mọi phụ thuộc bên trong một kỳ, không cần giả định phân phối. Holm trên
   cả họ (5 thống kê × 2 cách gom: theo đài, theo thứ).
2. **Lồng cầu của từng đài có đều không, và có lúc nào lệch đi không?** Một quá trình e (e-process) cho
   mỗi đài, tính từ kỳ đầu tiên của thời kỳ lịch: tỉ số giữa xác suất KT (Krichevsky–Trofimov, tự học
   từ chính các kỳ của đài) và phân bố đều, trên 5 lồng × 10 chữ số. Dưới giả thuyết đều, xác suất nó
   TỪNG vượt ``số đài / ALPHA`` không quá ``ALPHA`` (bất đẳng thức Ville), dù xem lúc nào. Vì tự học
   theo thời gian, nó tự nhạy với một đài BẮT ĐẦU lệch (ví dụ đổi máy quay); lịch đổi thì đài của thời
   kỳ mới bắt đầu một quá trình mới.
3. **Xác suất riêng từng đài có dự báo tốt hơn không?** Walk-forward trên ``TEST_DRAWS`` kỳ cuối: mỗi kỳ
   chỉ dùng các kỳ trước nó. Ba mô hình cho xác suất mỗi con về: hằng số (``1 − 0,99²⁷``), tần suất
   gộp mọi kỳ, và tần suất riêng đài CO về tần suất gộp (Bayes thực nghiệm, độ co ``κ`` học bằng hợp lý
   biên Dirichlet–đa thức trên các kỳ TRƯỚC cửa sổ kiểm). Điểm là log-loss; mô hình theo đài chỉ được
   đề bạt khi thắng CẢ hằng số LẪN tần suất gộp với z ≥ ``PROMOTE_Z`` (một phía, α = 0,01).

Hồ sơ từng đài (CSV) in tỉ lệ thô cạnh mức nền, z, q (BH trên mọi ô) và xác suất đã co: đó là "xác suất
chuẩn cho từng đài" mà dữ liệu cho phép nói. Khi không có hiệu ứng, xác suất đã co trùng mức chung.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import gammaln
from scipy.stats import chi2

from core.atomic_io import atomic_to_csv, atomic_write_text
from core.paths import REPO_ROOT
from core.xsmb_domain import FIELD_WIDTHS, LOTO_BASELINE_RATE, LOTO_DRAWS_PER_DAY, TOTAL_DIGITS, raw_digit_matrix
from core.xsmb_schedule import ERAS, WEEKDAY_NAMES, era_for, venue_for
from stats.statistical_corrections import holm

SCHEMA_VERSION = 1
#: Đổi định nghĩa thống kê, mô hình hay hằng số dưới đây thì tăng số này.
STAT_VERSION = 1
SEED = 20261123
#: Số hoán vị. p nhỏ nhất đạt được là 1/(B+1), và sau Holm trên ``HETEROGENEITY_TESTS`` phép kiểm là
#: ``HETEROGENEITY_TESTS/(B+1)``: với 999 hoán vị con số ấy là 0,01, KHÔNG BAO GIỜ nhỏ hơn ``ALPHA`` — module
#: sẽ không bao giờ kết luận "khác nhau" dù hiệu ứng mạnh đến đâu. 1 999 cho mức nhỏ nhất 0,005.
PERMUTATIONS = 1999
#: 5 thống kê × 2 cách gom (theo đài, theo thứ).
HETEROGENEITY_TESTS = 10
ALPHA = 0.01
#: Số kỳ cuối dùng để chấm walk-forward (≈ 2 năm).
TEST_DRAWS = 730
#: z một phía cho α = 0,01.
PROMOTE_Z = 2.326
#: Lưới độ co κ (số quan sát giả, đơn vị: số con LOTO) cho mô hình theo đài.
KAPPA_GRID = tuple(10.0 ** k for k in np.arange(1.0, 8.01, 0.25))
#: Trí nhớ của e-detector (số kỳ của MỘT đài, ≈ 2 năm với đài quay mỗi tuần).
DETECTOR_MEMORY = 104.0
#: Tầm hoạch định của e-detector, tính bằng NĂM. Một dãy quay ``k`` ngày mỗi tuần có ``H = năm · 52,18 · k``
#: kỳ trong tầm ấy (đài quay mỗi tuần: ≈ 2 000 kỳ; toàn miền Bắc: ≈ 13 900). Vì ``E[R_t] = t`` dưới giả
#: thuyết đều, bất đẳng thức Doob cho ``P(R vượt c trong H kỳ đầu) ≤ H / c``; ngưỡng ``c = H · số dãy /
#: ALPHA`` chặn xác suất báo nhầm của CẢ họ trong tầm ấy ở ``ALPHA``. Đừng đặt ngưỡng bằng ARL mong muốn:
#: ARL chỉ bảo đảm THỜI GIAN TRUNG BÌNH tới báo nhầm, và với ngưỡng 2 000 bản đầu báo động ở 3/6 đài trên
#: lịch sử thật, khớp hoàn toàn với kỳ quay công bằng (n/c tới 0,6 mỗi đài).
DETECTOR_YEARS = 38.0
#: Nhãn của dãy giám sát gộp mọi kỳ: mọi đài dùng chung một lần quay, nên lỗi của bộ máy chung hiện ở dãy
#: này nhanh gấp ≈ 7 lần (tính theo ngày) so với dãy của một đài.
POOLED = "Toàn miền Bắc"
CAGES = 5
CAGE_NAMES = ("đơn vị", "chục", "trăm", "nghìn", "chục nghìn")
OUT_DIR = Path("stats") / "venue"
SUMMARY = "xsmb_venue_effects.json"
PROFILE = "xsmb_venue_profile.csv"
LEDGER = Path("xsmb.csv")


def _cage_of_digit() -> np.ndarray:
    """Lồng của từng vị trí trong 107: 0 = cột đơn vị của giải, 4 = cột chục nghìn."""
    out: list[int] = []
    for _, width in FIELD_WIDTHS:
        out.extend(width - 1 - k for k in range(width))
    return np.array(out, dtype=np.int64)


CAGE_OF_DIGIT = _cage_of_digit()
_TAIL_INDEX = np.cumsum([width for _, width in FIELD_WIDTHS]) - 1


@dataclass(frozen=True)
class Draws:
    """Sổ chuẩn đã chuẩn hoá cho phép phân tích theo đài."""

    dates: tuple[date, ...]
    digits: np.ndarray  # (n, 107), giá trị 0..9
    venue: tuple[str, ...]

    @property
    def n(self) -> int:
        return len(self.dates)

    @property
    def weekday(self) -> np.ndarray:
        return np.array([day.weekday() for day in self.dates], dtype=np.int64)

    @property
    def loto(self) -> np.ndarray:
        """27 con LOTO mỗi kỳ (hai chữ số cuối của từng giải)."""
        return self.digits[:, _TAIL_INDEX - 1].astype(np.int64) * 10 + self.digits[:, _TAIL_INDEX]

    @property
    def special(self) -> np.ndarray:
        return self.loto[:, 0]


def from_frame(frame: pd.DataFrame) -> Draws:
    """Bảng sổ chuẩn (cột ``date`` và 27 giải) → ``Draws``; kỳ xếp theo ngày, nhãn đài theo lịch có hiệu lực."""
    frame = frame.assign(_day=pd.to_datetime(frame["date"]).dt.date).sort_values("_day", kind="stable")
    dates = tuple(frame["_day"])
    if len(set(dates)) != len(dates):
        raise ValueError("sổ chuẩn có ngày trùng")
    venues = tuple(venue_for(day) for day in dates)
    if not all(venues):
        raise ValueError("có kỳ trước thời kỳ đầu của lịch đài")
    return Draws(dates=dates, digits=raw_digit_matrix(frame.reset_index(drop=True)), venue=venues)


def load(repo_root: Path = REPO_ROOT) -> Draws:
    return from_frame(pd.read_csv(repo_root / "data" / LEDGER, dtype=str))


# ---------------------------------------------------------------------------- đặc trưng mỗi kỳ
def _one_hot_counts(values: np.ndarray, width: int) -> np.ndarray:
    out = np.zeros((values.shape[0], width), dtype=np.float64)
    rows = np.repeat(np.arange(values.shape[0]), values.shape[1])
    np.add.at(out, (rows, values.ravel()), 1.0)
    return out


def features(draws: Draws) -> dict[str, tuple[np.ndarray, list[np.ndarray]]]:
    """Mỗi thống kê χ²: ma trận đếm theo kỳ và các khối cột là một phân phối riêng."""
    loto = _one_hot_counts(draws.loto, 100)
    special = _one_hot_counts(draws.special[:, None], 100)
    position = _one_hot_counts(draws.digits.astype(np.int64) + 10 * np.arange(TOTAL_DIGITS)[None, :], 10 * TOTAL_DIGITS)
    cage = _one_hot_counts(draws.digits.astype(np.int64) + 10 * CAGE_OF_DIGIT[None, :], 10 * CAGES)
    return {
        "loto": (loto, [np.arange(100)]),
        "special": (special, [np.arange(100)]),
        "position_digits": (position, [np.arange(p * 10, p * 10 + 10) for p in range(TOTAL_DIGITS)]),
        "cage_digits": (cage, [np.arange(c * 10, c * 10 + 10) for c in range(CAGES)]),
    }


STAT_LABELS = {
    "loto": "số lần ra của 100 con LOTO",
    "special": "2 số cuối Đặc Biệt",
    "position_digits": "chữ số ở 107 vị trí",
    "cage_digits": "chữ số theo 5 lồng",
    "distinct": "số con LOTO khác nhau mỗi kỳ",
}


def _codes(labels: tuple | np.ndarray) -> tuple[np.ndarray, list]:
    names: list = []
    for value in labels:
        if value not in names:
            names.append(value)
    index = {name: i for i, name in enumerate(names)}
    return np.array([index[value] for value in labels], dtype=np.int64), names


def groupings(draws: Draws) -> dict[str, tuple[np.ndarray, list[str]]]:
    venue_codes, venue_names = _codes(draws.venue)
    weekday = draws.weekday
    return {
        "đài": (venue_codes, [str(v) for v in venue_names]),
        "thứ": (weekday, list(WEEKDAY_NAMES)),
    }


def _chi_square(sums: np.ndarray, blocks: list[np.ndarray]) -> float:
    """Tổng χ² đồng nhất G × K trên các khối (mỗi khối một bảng ngẫu nhiên riêng)."""
    total = 0.0
    for block in blocks:
        observed = sums[:, block]
        grand = observed.sum()
        if grand <= 0:
            continue
        expected = observed.sum(axis=1, keepdims=True) * observed.sum(axis=0, keepdims=True) / grand
        mask = expected > 0
        total += float((((observed - expected) ** 2)[mask] / expected[mask]).sum())
    return total


def _between_groups(values: np.ndarray, membership: np.ndarray) -> float:
    """Tổng bình phương giữa các nhóm của một đại lượng mỗi kỳ (thống kê của ANOVA một chiều)."""
    sizes = membership.sum(axis=1)
    means = membership @ values / np.where(sizes > 0, sizes, 1)
    return float((sizes * (means - values.mean()) ** 2).sum())


def _membership(codes: np.ndarray, groups: int) -> np.ndarray:
    out = np.zeros((groups, codes.size))
    out[codes, np.arange(codes.size)] = 1.0
    return out


def _group_statistics(labels: np.ndarray, groups: int, feats: dict, distinct: np.ndarray) -> dict[str, float]:
    member = _membership(labels, groups)
    out = {name: _chi_square(member @ matrix, blocks) for name, (matrix, blocks) in feats.items()}
    out["distinct"] = _between_groups(distinct, member)
    return out


def heterogeneity_tests(draws: Draws, *, permutations: int = PERMUTATIONS, seed: int = SEED) -> list[dict]:
    """Năm thống kê × hai cách gom, p bằng hoán vị nhãn giữa các kỳ (cùng một hoán vị cho mọi thống kê)."""
    feats = features(draws)
    distinct = (feats["loto"][0] > 0).sum(axis=1).astype(np.float64)
    results: list[dict] = []
    for grouping, (codes, names) in groupings(draws).items():
        groups = len(names)
        rng = np.random.default_rng(np.random.SeedSequence([seed, len(grouping)]))
        observed = _group_statistics(codes, groups, feats, distinct)
        exceed = dict.fromkeys(observed, 0)
        null_values: dict[str, list[float]] = {name: [] for name in observed}
        for _ in range(permutations):
            permuted = _group_statistics(rng.permutation(codes), groups, feats, distinct)
            for name, value in permuted.items():
                null_values[name].append(value)
                exceed[name] += value >= observed[name] - 1e-9
        sizes = np.bincount(codes, minlength=groups)
        for name, value in observed.items():
            results.append({
                "grouping": grouping,
                "statistic": name,
                "label": STAT_LABELS[name],
                "groups": groups,
                "group_sizes": {names[g]: int(sizes[g]) for g in range(groups)},
                "observed": round(value, 6),
                "null_median": round(float(np.median(null_values[name])), 6),
                "p_value": (1 + exceed[name]) / (1 + permutations),
            })
    if len(results) != HETEROGENEITY_TESTS:
        raise AssertionError("số phép kiểm đồng nhất đổi: cập nhật HETEROGENEITY_TESTS và mức p nhỏ nhất")
    for row, adjusted in zip(results, holm([row["p_value"] for row in results]), strict=True):
        row["p_holm"] = float(adjusted)
        row["rejected"] = bool(adjusted < ALPHA)
        row["min_attainable_p_holm"] = HETEROGENEITY_TESTS / (permutations + 1)
    return results


# ---------------------------------------------------------------------------- lồng cầu từng đài
def _kt_log_e(counts: np.ndarray) -> np.ndarray:
    """log e của KT (Dirichlet ½) so với phân bố đều, cho từng tiền tố. ``counts``: (t, lồng, 10) cộng dồn."""
    k = counts.shape[-1]
    totals = counts.sum(axis=-1)
    log_kt = (gammaln(k / 2) - gammaln(k / 2 + totals)
              + (gammaln(counts + 0.5) - gammaln(0.5)).sum(axis=-1)).sum(axis=-1)
    return log_kt + totals.sum(axis=-1) * math.log(k)


def change_detector(per_draw: np.ndarray, *, memory: float = DETECTOR_MEMORY) -> np.ndarray:
    """log R_t của e-detector Shiryaev–Roberts cho một đài: ``R_t = (1 + R_{t−1}) · L_t``.

    ``L_t = Π q_t(lồng, chữ số) / 0,1`` trên mọi chữ số của kỳ t, với ``q_t`` là ước lượng KT từ các kỳ
    TRƯỚC t, đếm có quên dần (mỗi kỳ nhân ``1 − 1/memory``). ``q_t`` chỉ nhìn quá khứ nên dưới giả thuyết
    đều ``E[L_t] = 1``, và ``R_t`` là tổng các quá trình e bắt đầu ở từng kỳ: thời gian trung bình tới
    lần ``R`` vượt ``c`` đầu tiên không dưới ``c`` kỳ (ngưỡng thật dùng ``DETECTOR_HORIZON``, xem ở đó). Khi
    đài bắt đầu lệch, ``q_t`` học lại trong vài
    chục kỳ và ``R`` tăng theo cấp số nhân. Đó là phần "thích nghi" mà e-process tính từ đầu thời kỳ
    không có: nó phải trả giá học của cả mười năm trước khi lệch.
    """
    decay = 1.0 - 1.0 / memory
    counts = np.zeros(per_draw.shape[1:])
    log_r = np.empty(per_draw.shape[0])
    previous = -np.inf
    for t, observed in enumerate(per_draw):
        q = (counts + 0.5) / (counts.sum(axis=1, keepdims=True) + 0.5 * counts.shape[1])
        log_l = float((observed * np.log(q * counts.shape[1])).sum())
        previous = float(np.logaddexp(0.0, previous)) + log_l
        log_r[t] = previous
        counts = decay * counts + observed
    return log_r


def cage_monitor(draws: Draws, *, alpha: float = ALPHA) -> list[dict]:
    """Mỗi (thời kỳ lịch, đài): χ² đều của 5 lồng (mô tả), e-process KT từ kỳ đầu của thời kỳ (đài có
    từng lệch khỏi phân bố đều không) và e-detector có quên dần (đài có BẮT ĐẦU lệch không)."""
    per_draw = _cage_counts(draws)
    eras = [era_for(day) for day in draws.dates]
    starts = np.array([era.start.toordinal() for era in eras])
    venues = np.array(draws.venue)
    sequences: list[tuple[date, str, np.ndarray]] = []
    for era in dict.fromkeys(eras):
        in_era = starts == era.start.toordinal()
        sequences.append((era.start, POOLED, np.flatnonzero(in_era)))
        for venue in dict.fromkeys(venues[in_era]):
            sequences.append((era.start, str(venue), np.flatnonzero(in_era & (venues == venue))))
    threshold = math.log10(len(sequences) / alpha)
    weekdays = draws.weekday
    rows: list[dict] = []
    for era_start, venue, idx in sequences:
        per_week = len(set(weekdays[idx].tolist()))
        horizon = DETECTOR_YEARS * 52.18 * per_week
        detector_threshold = math.log10(horizon * len(sequences) / alpha)
        cumulative = np.cumsum(per_draw[idx], axis=0)
        log10_e = _kt_log_e(cumulative) / math.log(10)
        final = cumulative[-1]
        expected = final.sum(axis=1, keepdims=True) / 10
        statistic = float(((final - expected) ** 2 / expected).sum())
        z = (final - expected) / np.sqrt(expected * 0.9)
        worst = np.unravel_index(int(np.argmax(np.abs(z))), z.shape)
        crossed = np.flatnonzero(log10_e >= threshold)
        log10_r = change_detector(per_draw[idx]) / math.log(10)
        alarms = np.flatnonzero(log10_r >= detector_threshold)
        rows.append({
            "era_start": era_start.isoformat(),
            "venue": venue,
            "pooled": venue == POOLED,
            "draws": int(idx.size),
            "draws_per_week": per_week,
            "first": draws.dates[idx[0]].isoformat(),
            "last": draws.dates[idx[-1]].isoformat(),
            "chi_square": round(statistic, 4),
            "df": CAGES * 9,
            "p_value": float(chi2.sf(statistic, CAGES * 9)),
            "largest_deviation": {"cage": CAGE_NAMES[worst[0]], "digit": int(worst[1]),
                                  "observed": int(final[worst]), "expected": round(float(expected[worst[0], 0]), 2),
                                  "z": round(float(z[worst]), 3)},
            "log10_e": round(float(log10_e[-1]), 4),
            "log10_e_max": round(float(log10_e.max()), 4),
            "log10_threshold": round(threshold, 4),
            "flagged_on": draws.dates[idx[crossed[0]]].isoformat() if crossed.size else None,
            "detector_log10": round(float(log10_r[-1]), 4),
            "detector_log10_max": round(float(log10_r.max()), 4),
            "detector_log10_threshold": round(detector_threshold, 4),
            "detector_alarm_on": draws.dates[idx[alarms[0]]].isoformat() if alarms.size else None,
            "detector_alarm_last": draws.dates[idx[alarms[-1]]].isoformat() if alarms.size else None,
            "detector_alarm_draws": int(alarms.size),
            "detector_in_alarm": bool(log10_r[-1] >= detector_threshold),
        })
    for row, adjusted in zip(rows, holm([row["p_value"] for row in rows]), strict=True):
        row["p_holm"] = float(adjusted)
    return rows


# ---------------------------------------------------------------------------- xác suất theo đài
def _dirichlet_log_marginal(counts: np.ndarray, base: np.ndarray, kappa: float) -> float:
    """log hợp lý biên Dirichlet–đa thức của các hàng ``counts`` với trung tâm ``base`` và độ co ``kappa``."""
    alpha = kappa * base
    totals = counts.sum(axis=1)
    return float((gammaln(kappa) - gammaln(kappa + totals)).sum()
                 + (gammaln(counts + alpha) - gammaln(alpha)).sum())


def fit_kappa(group_counts: np.ndarray) -> float:
    """Độ co κ chung cho mọi nhóm, cực đại hoá hợp lý biên quanh tần suất gộp của chính các nhóm ấy."""
    pooled = group_counts.sum(axis=0)
    base = (pooled + 0.5) / (pooled.sum() + 0.5 * pooled.size)
    scores = [_dirichlet_log_marginal(group_counts, base, kappa) for kappa in KAPPA_GRID]
    return float(KAPPA_GRID[int(np.argmax(scores))])


def _appear_prob(theta: np.ndarray) -> np.ndarray:
    return 1.0 - (1.0 - theta) ** LOTO_DRAWS_PER_DAY


def _bernoulli_loss(prob: np.ndarray, outcome: np.ndarray) -> np.ndarray:
    prob = np.clip(prob, 1e-12, 1 - 1e-12)
    return -(outcome * np.log(prob) + (1 - outcome) * np.log1p(-prob)).mean(axis=-1)


def _paired(diff: np.ndarray) -> dict:
    mean = float(diff.mean())
    se = float(diff.std(ddof=1) / math.sqrt(diff.size)) if diff.size > 1 else float("nan")
    return {"mean_gain": mean, "se": se, "z": mean / se if se and se > 0 else 0.0}


def _score(mode: str, theta: np.ndarray, counts: np.ndarray, outcome: np.ndarray,
           constant: float | None = None) -> float:
    """Log-loss của một kỳ: LOTO là trung bình 100 log-loss nhị phân, Đặc Biệt là −log xác suất số đã ra."""
    if mode == "loto":
        prob = np.full(100, constant) if constant is not None else _appear_prob(theta)
        return float(_bernoulli_loss(prob, outcome))
    winner = int(np.argmax(counts))
    return float(-math.log(max(theta[winner] / theta.sum(), 1e-12)))


def walk_forward(draws: Draws, *, test_draws: int = TEST_DRAWS, keep_losses: bool = False) -> dict:
    """Chấm ba mô hình (và bản theo thứ) trên ``test_draws`` kỳ cuối; mỗi kỳ chỉ dùng kỳ trước nó."""
    test_draws = min(test_draws, draws.n - 365)
    if test_draws < 30:
        raise ValueError("sổ quá ngắn để chấm walk-forward")
    start = draws.n - test_draws
    feats = features(draws)
    out: dict = {"test_draws": test_draws, "first": draws.dates[start].isoformat(),
                 "last": draws.dates[-1].isoformat(), "modes": {}}
    for mode, matrix in (("loto", feats["loto"][0]), ("de", feats["special"][0])):
        outcome = (matrix > 0).astype(np.float64)
        cumulative = np.vstack([np.zeros((1, 100)), np.cumsum(matrix, axis=0)])
        losses: dict[str, list[float]] = {"constant": [], "pooled": []}
        kappas: dict[str, float] = {}
        group_cum: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for grouping, (codes, names) in groupings(draws).items():
            member = _membership(codes, len(names))
            train = member[:, :start] @ matrix[:start]
            kappas[grouping] = fit_kappa(train)
            stacked = np.stack([np.vstack([np.zeros((1, 100)), np.cumsum(matrix * member[g][:, None], axis=0)])
                                for g in range(len(names))])
            group_cum[grouping] = (codes, stacked)
            losses[grouping] = []
        constant = LOTO_BASELINE_RATE if mode == "loto" else 0.01
        for t in range(start, draws.n):
            prior = cumulative[t]
            pooled_theta = (prior + 0.5) / (prior.sum() + 50.0)
            losses["constant"].append(_score(mode, np.full(100, 0.01), matrix[t], outcome[t], constant))
            losses["pooled"].append(_score(mode, pooled_theta, matrix[t], outcome[t]))
            for grouping, (codes, stacked) in group_cum.items():
                own = stacked[codes[t], t]
                kappa = kappas[grouping]
                theta = (own + kappa * pooled_theta) / (own.sum() + kappa)
                losses[grouping].append(_score(mode, theta, matrix[t], outcome[t]))
        arrays = {name: np.array(values) for name, values in losses.items()}
        models = {}
        for name, values in arrays.items():
            models[name] = {"log_loss": float(values.mean()),
                            "skill_vs_constant": float(1 - values.mean() / arrays["constant"].mean())}
        comparisons = {}
        for grouping in group_cum:
            vs_constant = _paired(arrays["constant"] - arrays[grouping])
            vs_pooled = _paired(arrays["pooled"] - arrays[grouping])
            comparisons[grouping] = {
                "kappa": kappas[grouping],
                "vs_constant": vs_constant,
                "vs_pooled": vs_pooled,
                "promoted": bool(vs_constant["z"] >= PROMOTE_Z and vs_pooled["z"] >= PROMOTE_Z),
            }
        comparisons["pooled"] = {"vs_constant": _paired(arrays["constant"] - arrays["pooled"])}
        out["modes"][mode] = {"models": models, "comparisons": comparisons}
        if keep_losses:
            out["modes"][mode]["losses"] = {name: values.tolist() for name, values in arrays.items()}
    return out


def _cage_counts(draws: Draws) -> np.ndarray:
    per_draw = np.zeros((draws.n, CAGES, 10))
    for cage in range(CAGES):
        cols = np.flatnonzero(CAGE_OF_DIGIT == cage)
        per_draw[:, cage, :] = _one_hot_counts(draws.digits[:, cols].astype(np.int64), 10)
    return per_draw


def adaptive_cage_benchmark(draws: Draws, monitor: list[dict], *, warmup: int = 365,
                            memory: float = DETECTOR_MEMORY) -> dict:
    """Mô hình THÍCH NGHI theo lồng có kiếm lời được không, chấm walk-forward từ kỳ ``warmup``.

    ``q_t`` của lồng chục và lồng đơn vị (KT, quên dần như e-detector) cho xác suất một giải kết thúc bằng
    ``ab`` là ``q_chục(a) · q_đơn vị(b)``; xác suất con về là ``1 − (1 − ·)²⁷``. Hai biến thể: luôn bật,
    và chỉ bật khi e-detector của dãy gộp đang báo động ở kỳ TRƯỚC (không nhìn kỳ được chấm). Chỉ đề bạt
    khi thắng hằng số với z ≥ ``PROMOTE_Z``.
    """
    per_draw = _cage_counts(draws)
    outcome = (features(draws)["loto"][0] > 0).astype(np.float64)
    pooled = [row for row in monitor if row["pooled"]]
    eras = np.array([era_for(day).start.toordinal() for day in draws.dates])
    log10_r = np.empty(draws.n)
    thresholds = np.empty(draws.n)
    for row in pooled:
        mask = eras == date.fromisoformat(row["era_start"]).toordinal()
        log10_r[mask] = change_detector(per_draw[mask], memory=memory) / math.log(10)
        thresholds[mask] = row["detector_log10_threshold"]
    decay = 1.0 - 1.0 / memory
    counts = np.zeros((CAGES, 10))
    constant = np.full(100, LOTO_BASELINE_RATE)
    losses: dict[str, list[float]] = {"constant": [], "always": [], "gated": []}
    for t in range(draws.n):
        q = (counts + 0.5) / (counts.sum(axis=1, keepdims=True) + 5.0)
        adaptive = _appear_prob(np.outer(q[1], q[0]).ravel())
        alarm = t > 0 and log10_r[t - 1] >= thresholds[t - 1]
        if t >= warmup:
            losses["constant"].append(float(_bernoulli_loss(constant, outcome[t])))
            losses["always"].append(float(_bernoulli_loss(adaptive, outcome[t])))
            losses["gated"].append(float(_bernoulli_loss(adaptive if alarm else constant, outcome[t])))
        counts = decay * counts + per_draw[t]
    arrays = {name: np.array(values) for name, values in losses.items()}
    result = {"first": draws.dates[warmup].isoformat(), "last": draws.dates[-1].isoformat(),
              "draws": int(arrays["constant"].size), "memory": memory}
    for name in ("always", "gated"):
        paired = _paired(arrays["constant"] - arrays[name])
        result[name] = {**paired, "promoted": bool(paired["z"] >= PROMOTE_Z)}
    return result


# ---------------------------------------------------------------------------- hồ sơ từng đài
def _bh(p_values: np.ndarray) -> np.ndarray:
    order = np.argsort(p_values, kind="stable")
    ranked = p_values[order] * p_values.size / np.arange(1, p_values.size + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.minimum(q, 1.0)
    return out


def venue_profile(draws: Draws, kappas: dict[str, float]) -> pd.DataFrame:
    """Mỗi (đài, con): tỉ lệ thô, mức nền, z, q và xác suất đã co về mức chung (Bayes thực nghiệm)."""
    feats = features(draws)
    codes, names = groupings(draws)["đài"]
    member = _membership(codes, len(names))
    rows = []
    for mode, matrix, base in (("loto", feats["loto"][0], LOTO_BASELINE_RATE), ("de", feats["special"][0], 0.01)):
        appeared = (matrix > 0).astype(np.float64)
        hits = member @ appeared
        counts = member @ matrix
        pooled = counts.sum(axis=0)
        pooled_theta = (pooled + 0.5) / (pooled.sum() + 50.0)
        kappa = kappas[mode]
        theta = (counts + kappa * pooled_theta) / (counts.sum(axis=1, keepdims=True) + kappa)
        shrunk = _appear_prob(theta) if mode == "loto" else theta / theta.sum(axis=1, keepdims=True)
        sizes = member.sum(axis=1)
        for g, venue in enumerate(names):
            n = sizes[g]
            z = (hits[g] - n * base) / math.sqrt(n * base * (1 - base))
            for number in range(100):
                rows.append({"mode": mode, "venue": venue, "number": f"{number:02d}", "draws": int(n),
                             "hits": int(hits[g, number]), "rate": hits[g, number] / n, "baseline_rate": base,
                             "z": float(z[number]), "posterior_rate": float(shrunk[g, number])})
    table = pd.DataFrame(rows)
    p = 2 * (1 - pd.Series(np.abs(table["z"].to_numpy())).map(lambda v: 0.5 * (1 + math.erf(v / math.sqrt(2)))))
    table["p_value"] = p.to_numpy()
    for mode in ("loto", "de"):
        mask = table["mode"] == mode
        table.loc[mask, "q_value"] = _bh(table.loc[mask, "p_value"].to_numpy())
    return table


# ---------------------------------------------------------------------------- tóm tắt
def _num(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",").replace("-", "−")


def _signed(value: float) -> str:
    return ("+" if value >= 0 else "") + _num(value, 2)


def _day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def reading(summary: dict) -> str:
    """Câu kết luận in TỪ số đo của chính tệp."""
    tests = summary["heterogeneity"]
    smallest = min(tests, key=lambda row: row["p_holm"])
    rejected = [row for row in tests if row["rejected"]]
    monitor = summary["cage_monitor"]
    flagged = [row for row in monitor if row["flagged_on"]]
    alarms = [row for row in monitor if row["detector_alarm_on"]]
    adaptive = summary["benchmark"]["adaptive_cage"]["gated"]
    comparisons = summary["benchmark"]["modes"]["loto"]["comparisons"]
    venue, pooled = comparisons["đài"], comparisons["pooled"]
    parts = [f"Trên {summary['draws']} kỳ ({_day(summary['first'])} → {_day(summary['last'])}),"]
    if rejected:
        names = ", ".join(f"{row['label']} theo {row['grouping']}" for row in rejected)
        parts.append(f"phân phối KHÁC NHAU có ý nghĩa ở: {names} (Holm, α = {_num(ALPHA, 2)}).")
    else:
        parts.append(
            f"không thống kê nào cho thấy kết quả khác nhau giữa các đài hay các thứ: p sau Holm nhỏ nhất là "
            f"{_num(smallest['p_holm'], 3)} ({smallest['label']} theo {smallest['grouping']}).")
    if flagged:
        parts.append("Lồng cầu lệch khỏi phân bố đều ở: " + ", ".join(
            f"{row['venue']} (từ {_day(row['flagged_on'])})" for row in flagged) + ".")
    else:
        parts.append("Tính trên toàn quãng từ kỳ đầu, chưa dãy nào lệch khỏi phân bố đều theo lồng.")
    if alarms:
        described = []
        for row in alarms:
            span = f"từ {_day(row['detector_alarm_on'])}"
            span += " tới nay" if row["detector_in_alarm"] else f" tới {_day(row['detector_alarm_last'])}, nay đã về dưới ngưỡng"
            described.append(f"{row['venue']} ({span}, đỉnh 10^{_num(row['detector_log10_max'], 1)}, "
                             f"ngưỡng 10^{_num(row['detector_log10_threshold'], 1)})")
        parts.append("Bộ phát hiện thay đổi theo lồng từng báo động ở: " + "; ".join(described) + ". Mô hình lồng "
                     f"thích nghi chỉ bật khi báo động {'thắng' if adaptive['promoted'] else 'không thắng'} hằng số "
                     f"trên toàn lịch sử (z = {_signed(adaptive['z'])}).")
    else:
        parts.append("Bộ phát hiện thay đổi theo lồng chưa báo động ở dãy nào.")
    if venue["promoted"]:
        parts.append("Xác suất riêng từng đài thắng cả hằng số lẫn tần suất gộp ngoài mẫu.")
    else:
        parts.append(
            f"Xác suất riêng từng đài không thắng ngoài mẫu: so với tần suất gộp z = {_signed(venue['vs_pooled']['z'])}, "
            f"so với hằng số z = {_signed(venue['vs_constant']['z'])} (chính tần suất gộp đã kém hằng số, "
            f"z = {_signed(pooled['vs_constant']['z'])}). Vì vậy xác suất cho mọi đài giữ mức chung: mỗi con LOTO "
            f"{_num(LOTO_BASELINE_RATE * 100, 2)}%, mỗi số Đặc Biệt 1%.")
    return " ".join(parts)


def summarize(draws: Draws, *, permutations: int = PERMUTATIONS, seed: int = SEED,
              test_draws: int = TEST_DRAWS) -> tuple[dict, pd.DataFrame]:
    heterogeneity = heterogeneity_tests(draws, permutations=permutations, seed=seed)
    monitor = cage_monitor(draws)
    benchmark = walk_forward(draws, test_draws=test_draws)
    benchmark["adaptive_cage"] = adaptive_cage_benchmark(draws, monitor)
    feats = features(draws)
    codes, names = groupings(draws)["đài"]
    member = _membership(codes, len(names))
    kappas = {"loto": fit_kappa(member @ feats["loto"][0]), "de": fit_kappa(member @ feats["special"][0])}
    profile = venue_profile(draws, kappas)
    schedule = [{"start": era.start.isoformat(), "venues": list(era.venues), "basis": era.basis} for era in ERAS]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "stat_version": STAT_VERSION,
        "draws": draws.n,
        "first": draws.dates[0].isoformat(),
        "last": draws.dates[-1].isoformat(),
        "alpha": ALPHA,
        "permutations": permutations,
        "seed": seed,
        "schedule": schedule,
        "venue_draws": {name: int(n) for name, n in zip(names, member.sum(axis=1), strict=True)},
        "heterogeneity": heterogeneity,
        "cage_monitor": monitor,
        "benchmark": benchmark,
        "profile_kappa": kappas,
    }
    summary["reading"] = reading(summary)
    return summary, profile


def run(repo_root: Path = REPO_ROOT, **kwargs) -> list[Path]:
    draws = load(repo_root)
    summary, profile = summarize(draws, **kwargs)
    out_dir = repo_root / "data" / OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path, profile_path = out_dir / SUMMARY, out_dir / PROFILE
    atomic_write_text(summary_path, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_to_csv(profile.round(10), profile_path, index=False)
    return [summary_path, profile_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--permutations", type=int, default=PERMUTATIONS)
    args = parser.parse_args(argv)
    for path in run(args.repo_root, permutations=args.permutations):
        print(f"đã ghi {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
