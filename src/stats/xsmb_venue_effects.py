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
STAT_VERSION = 1
SEED = 20261123
PERMUTATIONS = 1999
HETEROGENEITY_TESTS = 10
ALPHA = 0.01
TEST_DRAWS = 730
PROMOTE_Z = 2.326
KAPPA_GRID = tuple(10.0 ** k for k in np.arange(1.0, 8.01, 0.25))
DETECTOR_MEMORY = 104.0
DETECTOR_YEARS = 38.0
POOLED = "Toàn miền Bắc"
CAGES = 5
CAGE_NAMES = ("đơn vị", "chục", "trăm", "nghìn", "chục nghìn")
OUT_DIR = Path("stats") / "venue"
SUMMARY = "xsmb_venue_effects.json"
PROFILE = "xsmb_venue_profile.csv"
LEDGER = Path("xsmb.csv")


def _cage_of_digit() -> np.ndarray:
    out: list[int] = []
    for _, width in FIELD_WIDTHS:
        out.extend(width - 1 - k for k in range(width))
    return np.array(out, dtype=np.int64)


CAGE_OF_DIGIT = _cage_of_digit()
_TAIL_INDEX = np.cumsum([width for _, width in FIELD_WIDTHS]) - 1


@dataclass(frozen=True)
class Draws:

    dates: tuple[date, ...]
    digits: np.ndarray
    venue: tuple[str, ...]

    @property
    def n(self) -> int:
        return len(self.dates)

    @property
    def weekday(self) -> np.ndarray:
        return np.array([day.weekday() for day in self.dates], dtype=np.int64)

    @property
    def loto(self) -> np.ndarray:
        return self.digits[:, _TAIL_INDEX - 1].astype(np.int64) * 10 + self.digits[:, _TAIL_INDEX]

    @property
    def special(self) -> np.ndarray:
        return self.loto[:, 0]


def from_frame(frame: pd.DataFrame) -> Draws:
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


def _one_hot_counts(values: np.ndarray, width: int) -> np.ndarray:
    out = np.zeros((values.shape[0], width), dtype=np.float64)
    rows = np.repeat(np.arange(values.shape[0]), values.shape[1])
    np.add.at(out, (rows, values.ravel()), 1.0)
    return out


def features(draws: Draws) -> dict[str, tuple[np.ndarray, list[np.ndarray]]]:
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


def _kt_log_e(counts: np.ndarray) -> np.ndarray:
    k = counts.shape[-1]
    totals = counts.sum(axis=-1)
    log_kt = (gammaln(k / 2) - gammaln(k / 2 + totals)
              + (gammaln(counts + 0.5) - gammaln(0.5)).sum(axis=-1)).sum(axis=-1)
    return log_kt + totals.sum(axis=-1) * math.log(k)


def change_detector(per_draw: np.ndarray, *, memory: float = DETECTOR_MEMORY) -> np.ndarray:
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


def _dirichlet_log_marginal(counts: np.ndarray, base: np.ndarray, kappa: float) -> float:
    alpha = kappa * base
    totals = counts.sum(axis=1)
    return float((gammaln(kappa) - gammaln(kappa + totals)).sum()
                 + (gammaln(counts + alpha) - gammaln(alpha)).sum())


def fit_kappa(group_counts: np.ndarray) -> float:
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
    if mode == "loto":
        prob = np.full(100, constant) if constant is not None else _appear_prob(theta)
        return float(_bernoulli_loss(prob, outcome))
    winner = int(np.argmax(counts))
    return float(-math.log(max(theta[winner] / theta.sum(), 1e-12)))


def walk_forward(draws: Draws, *, test_draws: int = TEST_DRAWS, keep_losses: bool = False) -> dict:
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


def _bh(p_values: np.ndarray) -> np.ndarray:
    order = np.argsort(p_values, kind="stable")
    ranked = p_values[order] * p_values.size / np.arange(1, p_values.size + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.minimum(q, 1.0)
    return out


def venue_profile(draws: Draws, kappas: dict[str, float]) -> pd.DataFrame:
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


def _num(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",").replace("-", "−")


def _signed(value: float) -> str:
    return ("+" if value >= 0 else "") + _num(value, 2)


def _day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def reading(summary: dict) -> str:
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--permutations", type=int, default=PERMUTATIONS)
    args = parser.parse_args(argv)
    for path in run(args.repo_root, permutations=args.permutations):
        print(f"đã ghi {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
