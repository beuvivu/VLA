from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

from ml import cau_keo_ml as ck
from soi_cau.bridge_rules import step_matrix
from core.calendar_alignment import known_non_draw_days
from forecast.multi_hit_vip import N_NUMBERS, counts_matrix, draws_from_frame, tie_keys
from soi_cau.position_bridges import COLUMNS, WIDTHS, load_draws, pair_index, run_lengths

RULE = "lo-vip-cau-keo-v1"
FROZEN_AT = "2026-10-15"
TOP_K = 5
C_GRID = (1e-4, 1e-3, 1e-2, 1e-1)
INNER_SHARE = 0.2
MIN_CALIBRATION = 500
IDENTITY = ("number_value", "tens", "ones", "digit_total", "weekday_next", "month_next")
CAU_KEO = tuple(c for c in ck.FEATURE_COLS if c not in IDENTITY)
BRIDGE = ("cau_hai_nhay", "cau_hai_nhay_dai", "cau_loto", "cau_loto_dai")
MULTI = ("nhay_hom_nay", "nhieu_nhay_hom_nay", "ti_le_nhieu_nhay", "nhieu_nhay_30", "nhieu_nhay_100")
FEATURES = CAU_KEO + BRIDGE + MULTI
BRIDGE_BUCKETS = ((0, 0, "không có cầu"), (1, 4, "1–4 cầu"), (5, None, "từ 5 cầu"))


@dataclass(frozen=True)
class ForecastConfig:
    warmup: int = 365
    refit: int = 250
    top_k: int = TOP_K
    min_history_days: int = 60

    def __post_init__(self) -> None:
        if self.warmup < 2 or self.refit < 1 or not 1 <= self.top_k <= N_NUMBERS:
            raise ValueError("cần warmup ≥ 2, refit ≥ 1 và 1 ≤ top_k ≤ 100")


def bridge_features(digits: np.ndarray, values: np.ndarray) -> dict[str, np.ndarray]:
    n_draws = len(digits)
    pa, pb = pair_index(True)
    out: dict[str, np.ndarray] = {}
    for kind, name, min_run, lon in (("hai-nhay", "cau_hai_nhay", 2, False), ("loto", "cau_loto", 3, True)):
        count = np.zeros((n_draws, N_NUMBERS), dtype=np.int32)
        longest = np.zeros((n_draws, N_NUMBERS), dtype=np.int32)
        if n_draws >= 2:
            runs = run_lengths(step_matrix(kind, digits, values))
            for t in range(1, n_draws):
                run = runs[t - 1]
                sel = np.flatnonzero(run >= min_run)
                if not sel.size:
                    continue
                x = digits[t, pa[sel]].astype(int)
                y = digits[t, pb[sel]].astype(int)
                targets = [(10 * x + y, np.ones(sel.size, dtype=bool))]
                if lon:
                    targets.append((10 * y + x, x != y))
                for number, keep in targets:
                    np.add.at(count[t], number[keep], 1)
                    np.maximum.at(longest[t], number[keep], run[sel][keep])
        out[name], out[name + "_dai"] = count, longest
    return out


def multi_features(counts: np.ndarray) -> dict[str, np.ndarray]:
    multi = (counts >= 2).astype(float)
    cum = np.vstack([np.zeros((1, N_NUMBERS)), np.cumsum(multi, axis=0)])
    t = np.arange(len(counts))[:, None]

    def window(w: int) -> np.ndarray:
        return cum[1:] - cum[np.maximum(np.arange(1, len(counts) + 1) - w, 0)]

    return {
        "nhay_hom_nay": np.minimum(counts, 3).astype(float),
        "nhieu_nhay_hom_nay": multi,
        "ti_le_nhieu_nhay": cum[1:] / (t + 1),
        "nhieu_nhay_30": window(30),
        "nhieu_nhay_100": window(100),
    }


def next_draw_date(last: str, closed: frozenset[str] | None = None) -> str:
    closed = known_non_draw_days() if closed is None else closed
    day = pd.Timestamp(last) + pd.Timedelta(days=1)
    for _ in range(366):
        if day.strftime("%Y-%m-%d") not in closed:
            return day.strftime("%Y-%m-%d")
        day += pd.Timedelta(days=1)
    raise ValueError(f"không có kỳ quay nào trong một năm sau {last}")


@dataclass
class Table:

    anchors: np.ndarray
    dates: list[str]
    target_date: str
    X: np.ndarray
    y: np.ndarray
    counts: np.ndarray
    special: np.ndarray


def build_table(raw: pd.DataFrame, two: pd.DataFrame, cfg: ForecastConfig | None = None, *,
                closed: frozenset[str] | None = None) -> Table:
    cfg = cfg or ForecastConfig()
    ck_cfg = ck.CauKeoConfig(min_history_days=cfg.min_history_days, window_days=10**7)
    two_sorted = two.assign(date=pd.to_datetime(two["date"]).dt.strftime("%Y-%m-%d")).sort_values("date", kind="stable")
    draws, dates = draws_from_frame(two_sorted.reset_index(drop=True))
    target = next_draw_date(dates[-1], closed)
    hist, _ = ck.build_cau_keo_feature_frame("loto", include_target=True, config=ck_cfg, raw=raw, two=two)
    nxt, _ = ck.build_cau_keo_feature_frame("loto", include_target=False, config=ck_cfg, raw=raw, two=two,
                                            next_date=target)
    frame = pd.concat([hist, nxt], ignore_index=True)
    counts = counts_matrix(draws)
    index = {d: i for i, d in enumerate(dates)}
    frame["t"] = pd.to_datetime(frame["anchor_date"]).dt.strftime("%Y-%m-%d").map(index)
    if frame["t"].isna().any():
        raise ValueError("kỳ neo của cầu kèo không có trong sổ hai số")
    frame = frame.sort_values(["t", "number"]).reset_index(drop=True)
    anchors = frame["t"].to_numpy(dtype=int)[::N_NUMBERS]
    if len(frame) != len(anchors) * N_NUMBERS:
        raise ValueError("mỗi kỳ neo phải có đủ 100 con")
    raw_dates, digits, values = load_draws(raw.assign(date=pd.to_datetime(raw["date"]).dt.strftime("%Y-%m-%d")))
    if raw_dates != dates:
        raise ValueError("sổ kết quả đầy đủ và sổ hai số lệch ngày")
    extra = {**bridge_features(digits, values), **multi_features(counts)}
    ck_part = frame[list(CAU_KEO)].to_numpy(dtype=float).reshape(len(anchors), N_NUMBERS, len(CAU_KEO))
    own = np.stack([extra[name][anchors] for name in BRIDGE + MULTI], axis=-1).astype(float)
    X = np.concatenate([ck_part, own], axis=-1)
    y = np.full((len(anchors), N_NUMBERS), np.nan)
    labelled = anchors + 1 < len(counts)
    y[labelled] = (counts[anchors[labelled] + 1] >= 2).astype(float)
    special = (values[:, 0] % 100).astype(int)
    return Table(anchors, dates, target, X, y, counts, special)


@dataclass
class Model:
    scaler: StandardScaler
    model: LogisticRegression
    C: float
    inner_gain: float

    def score(self, X: np.ndarray) -> np.ndarray:
        flat = X.reshape(-1, X.shape[-1])
        return self.model.decision_function(self.scaler.transform(flat)).reshape(X.shape[:-1])

    def contributions(self, x: np.ndarray) -> np.ndarray:
        return self.model.coef_[0] * self.scaler.transform(x.reshape(1, -1))[0]


def fit(X: np.ndarray, y: np.ndarray) -> Model:
    n = len(X)
    cut = max(1, min(n - 1, int(round(n * (1 - INNER_SHARE)))))
    flat = lambda a: a.reshape(-1, a.shape[-1]) if a.ndim == 3 else a.reshape(-1)
    if len(np.unique(flat(y))) < 2:
        raise ValueError("nhãn huấn luyện chỉ có một lớp: chưa có kỳ nào về ≥ 2 nháy để học")
    best = None
    if len(np.unique(y[:cut])) == 2 and len(np.unique(y[cut:])) == 2:
        inner = StandardScaler().fit(flat(X[:cut]))
        fit_x, val_x = inner.transform(flat(X[:cut])), inner.transform(flat(X[cut:]))
        base = log_loss(flat(y[cut:]), np.full(flat(y[cut:]).size, flat(y[:cut]).mean()), labels=[0, 1])
        for c in C_GRID:
            model = LogisticRegression(C=c, max_iter=2000).fit(fit_x, flat(y[:cut]))
            loss = log_loss(flat(y[cut:]), model.predict_proba(val_x)[:, 1], labels=[0, 1])
            if best is None or loss < best[1]:
                best = (c, loss, base - loss)
    c, gain = (best[0], best[2]) if best else (C_GRID[0], 0.0)
    scaler = StandardScaler().fit(flat(X))
    model = LogisticRegression(C=c, max_iter=2000).fit(scaler.transform(flat(X)), flat(y))
    return Model(scaler, model, c, float(gain))


class Calibrator:

    def __init__(self, scores: np.ndarray, hits: np.ndarray) -> None:
        self.model = None
        if scores.size >= MIN_CALIBRATION and 0 < hits.sum() < hits.size:
            self.model = LogisticRegression(C=1.0).fit(scores.reshape(-1, 1), hits)

    def __call__(self, scores: np.ndarray) -> np.ndarray:
        scores = np.asarray(scores, dtype=float)
        if self.model is None:
            return 1 / (1 + np.exp(-scores))
        return self.model.predict_proba(scores.reshape(-1, 1))[:, 1].reshape(scores.shape)


def rank(scores: np.ndarray, t: int) -> np.ndarray:
    return np.lexsort((tie_keys(t), -scores))


@dataclass
class Forecast:

    picks: np.ndarray
    scores: np.ndarray
    printed: np.ndarray
    model: Model


@dataclass
class WalkForward:
    rows: np.ndarray
    picks: np.ndarray
    hits: np.ndarray
    printed: np.ndarray
    scores: np.ndarray
    blocks: list[dict] = field(default_factory=list)
    forecast: Forecast | None = None


def walk_forward(table: Table, cfg: ForecastConfig | None = None) -> WalkForward:
    cfg = cfg or ForecastConfig()
    last = len(table.anchors) - 1
    rows, picks, hits, printed, scores, blocks = [], [], [], [], [], []
    forecast = None
    for start in range(cfg.warmup, last + 1, cfg.refit):
        model = fit(table.X[:start], table.y[:start])
        calibrate = Calibrator(np.concatenate(scores).ravel() if scores else np.empty(0),
                               np.concatenate([table.y[r, p] for r, p in zip(rows, picks, strict=True)]).ravel()
                               if rows else np.empty(0))
        stop = min(start + cfg.refit, last + 1)
        block_scores = model.score(table.X[start:stop])
        for j, r in enumerate(range(start, stop)):
            top = rank(block_scores[j], int(table.anchors[r]) + 1)[: cfg.top_k]
            if r == last:
                forecast = Forecast(top, block_scores[j, top], calibrate(block_scores[j, top]), model)
                continue
            rows.append(r)
            picks.append(top)
            hits.append(int(table.y[r, top].sum()))
            scores.append(block_scores[j, top])
            printed.append(calibrate(block_scores[j, top]))
        blocks.append({"start": int(start), "C": model.C, "inner_gain": model.inner_gain})
    k = cfg.top_k
    return WalkForward(np.array(rows, dtype=int), np.array(picks, dtype=int).reshape(-1, k),
                       np.array(hits, dtype=int), np.array(printed, dtype=float).reshape(-1, k),
                       np.array(scores, dtype=float).reshape(-1, k), blocks, forecast)


def _ab(n: int) -> str:
    return f"{n:02d}"


def reason(name: str, value: float, number: int, special: int) -> str | None:
    v = float(value)
    head, tail = divmod(number, 10)
    db = _ab(special)
    windows = {"freq_3d": 3, "freq_7d": 7, "freq_14d": 14, "freq_30d": 30, "freq_90d": 90, "freq_365d": 365}
    if name in windows:
        return f"về {v:.0f}/{windows[name]} kỳ gần nhất" if v else None
    flags = {
        "hit_today": "về ở kỳ mới nhất", "hit_yesterday": "về ở kỳ trước nữa", "hit_2d_ago": "về cách đây 2 kỳ",
        "reverse_hit_today": "số lộn về ở kỳ mới nhất", "is_prev_special": f"trùng Đặc Biệt {db}",
        "is_reverse_prev_special": f"lộn của Đặc Biệt {db}", "is_bong_prev_special": f"bóng của Đặc Biệt {db}",
        "share_head_prev_special": f"cùng đầu với Đặc Biệt {db}",
        "share_tail_prev_special": f"cùng đuôi với Đặc Biệt {db}",
        "same_total_prev_special": f"cùng tổng với Đặc Biệt {db}",
        "cham_overlap_prev_special": f"chạm Đặc Biệt {db}", "nhieu_nhay_hom_nay": "về ≥ 2 nháy ở kỳ mới nhất",
    }
    if name in flags:
        return flags[name] if v else None
    text = {
        "gap": lambda: f"gan {v:.0f} kỳ", "gap_log": lambda: f"gan {math.expm1(v):.0f} kỳ",
        "loto_occ_today": lambda: f"{v:.0f} nháy ở kỳ mới nhất", "loto_occ_7d": lambda: f"{v:.0f} nháy trong 7 kỳ",
        "same_weekday_freq_364": lambda: f"cùng thứ: về {v:.0f}/52 tuần",
        "month_to_date_freq": lambda: f"về {v:.0f} kỳ từ đầu tháng",
        "year_to_date_freq": lambda: f"về {v:.0f} kỳ từ đầu năm",
        "path_support": lambda: f"{v:.0f} đường chữ số nối tới",
        "path_support_log": lambda: f"{math.expm1(v):.0f} đường chữ số nối tới",
        "reverse_freq_7d": lambda: f"số lộn về {v:.0f}/7 kỳ",
        "cond_de_rate": lambda: f"sau Đặc Biệt {db} từng về {100 * v:.0f}%",
        "cond_loto_mean_rate": lambda: f"xác suất chuyển từ lô kỳ mới nhất {100 * v:.1f}%",
        "cond_loto_max_rate": lambda: f"xác suất chuyển cao nhất {100 * v:.1f}%",
        "head_freq_7d": lambda: f"đầu {head} về {v:.0f} lần/7 kỳ",
        "tail_freq_7d": lambda: f"đuôi {tail} về {v:.0f} lần/7 kỳ",
        "trend_7_vs_30": lambda: f"đà 7 kỳ so với 30 kỳ {v:+.1f}",
        "cau_hai_nhay": lambda: f"{v:.0f} cầu hai nháy đang chạy",
        "cau_hai_nhay_dai": lambda: f"cầu hai nháy dài {v:.0f} kỳ",
        "cau_loto": lambda: f"{v:.0f} cầu LOTO đang chạy", "cau_loto_dai": lambda: f"cầu LOTO dài {v:.0f} kỳ",
        "nhay_hom_nay": lambda: f"{v:.0f} nháy ở kỳ mới nhất",
        "ti_le_nhieu_nhay": lambda: f"về ≥ 2 nháy {100 * v:.1f}% số kỳ",
        "nhieu_nhay_30": lambda: f"{v:.0f} kỳ ≥ 2 nháy trong 30 kỳ",
        "nhieu_nhay_100": lambda: f"{v:.0f} kỳ ≥ 2 nháy trong 100 kỳ",
    }
    if name not in text:
        raise KeyError(name)
    zero_means_absent = name.startswith(("cau_", "nhay", "nhieu", "loto", "path", "reverse_freq"))
    return None if zero_means_absent and not v else text[name]()


def reasons(model: Model, x: np.ndarray, number: int, special: int, limit: int = 2) -> list[str]:
    out = []
    for j in np.argsort(-model.contributions(x), kind="stable"):
        if model.contributions(x)[j] <= 0 or len(out) >= limit:
            break
        text = reason(FEATURES[j], x[j], number, special)
        if text:
            out.append(text)
    return out


def bridge_experience(table: Table) -> list[dict]:
    j = FEATURES.index("cau_hai_nhay")
    bridges = table.X[:-1, :, j]
    outcome = table.y[:-1]
    out = []
    for lo, hi, label in BRIDGE_BUCKETS:
        mask = bridges >= lo if hi is None else (bridges >= lo) & (bridges <= hi)
        seen, observed = int(mask.sum()), int(outcome[mask].sum())
        out.append({"label": label, "seen": seen, "observed": observed,
                    "rate": observed / seen if seen else None})
    return out


def mock_raw_history(n_draws: int = 200, seed: int = 2026, planted: tuple[int, ...] = (),
                     plant_rate: float = 0.3) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    values = np.column_stack([rng.integers(0, 10 ** w, size=n_draws) for w in WIDTHS]).astype(np.int64)
    for t in range(n_draws):
        for number in planted:
            if rng.random() < plant_rate:
                for j in rng.choice(len(WIDTHS), size=2, replace=False):
                    values[t, j] = values[t, j] // 100 * 100 + number
    dates = pd.date_range("2026-01-01", periods=n_draws, freq="D").strftime("%Y-%m-%d")
    raw = pd.DataFrame(values, columns=COLUMNS)
    raw.insert(0, "date", dates)
    two = raw.copy()
    two[COLUMNS] = values % 100
    return raw, two
