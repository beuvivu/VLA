"""Lượt thử thứ hai cho "lô nhiều nháy" (≥ 2 nháy một kỳ): dò rộng, chọn trước, kiểm một lần.

Lượt đầu (``src/multi_hit_vip.py``, 08-10-2026) cho top-5 trúng 2,91%, đúng bằng chọn bừa. Lượt
này hỏi câu rộng hơn: có CÁCH CHẤM NÀO trong các họ ý tưởng thường gặp — tần suất ở mọi cửa sổ,
lô gan, lặp kỳ trước, theo thứ trong tuần, thiên lệch theo vị trí giải hay theo chữ số, hồi quy
logistic và cây tăng cường trên toàn bộ đặc trưng — đưa top-5 lên trên mức nền không?

Giao thức, cố định TRƯỚC khi chạy trên dữ liệu thật (đổi giao thức sau khi thấy kết quả là tự lừa):

1. Mọi chiến lược cho điểm ``S[t, i]`` chỉ từ các kỳ < t. Hoà điểm được phá bằng nhiễu nhỏ cố
   định theo hạt giống, để không chiến lược nào được lợi vì luôn chọn số nhỏ.
2. Giai đoạn phát triển: kỳ ``WARMUP`` tới ``T − HOLDOUT``. Giai đoạn kiểm: ``HOLDOUT`` kỳ cuối.
3. Chấm: số lượt trúng của top-k so với kỳ vọng khi chọn bừa k trong 100 con CÙNG KỲ ấy. Với
   m_t con về ≥ 2 nháy ở kỳ t, chọn bừa trúng theo phân phối siêu bội: kỳ vọng k·m_t/100, phương
   sai k·(m_t/100)·(1 − m_t/100)·(100 − k)/99. Cộng qua các kỳ ra điểm z. Phép so này giữ nguyên
   độ dao động của chính các kỳ đã quay, nên không cần giả định 27 lô độc lập.
4. Trên giai đoạn phát triển: p một phía của mọi chiến lược, hiệu chỉnh Holm. Chiến lược có z
   cao nhất là ỨNG VIÊN DUY NHẤT.
5. Giai đoạn kiểm chỉ quyết định ứng viên ấy: đạt khi p một phía < ``ALPHA``. Các chiến lược
   khác vẫn được in ở giai đoạn kiểm để minh bạch, nhưng không dùng để kết luận (chọn cái tốt
   nhất trên giai đoạn kiểm là rò rỉ).
6. Độ nhạy: cùng giao thức trên lịch sử giả định có cài tín hiệu nhẹ phải tìm ra và qua được
   giai đoạn kiểm (``--power-check``).

Chạy (``scripts/research/benchmark_multi_hit.py`` là lớp vỏ dòng lệnh của module này):

    python3 scripts/research/benchmark_multi_hit.py --until 2026-10-12                 # dữ liệu thật, ~2 phút
    python3 scripts/research/benchmark_multi_hit.py --until 2026-10-12 --power-check   # thêm kiểm độ nhạy
    python3 scripts/research/benchmark_multi_hit.py --json /tmp/multi.json

Trang «Lô VIP nhiều nháy» in kết quả của giao thức này qua ``multi_hit_report.py``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]

from multi_hit_vip import (  # noqa: E402
    LOTO_PER_DRAW,
    N_NUMBERS,
    RAW_FEATURES,
    VIPConfig,
    VIPMultiHitModel,
    base_rate,
    build_raw_features,
    counts_matrix,
    draws_from_frame,
    mock_history,
    random_pick_null,
    until,
)

WARMUP = 365
HOLDOUT = 1000
TOP_K = 5
ALPHA = 0.01
REFIT_EVERY = 250
TIE_SEED = 20261012
#: Phép kiểm độ nhạy: ba con được cài thêm ≥ 2 nháy với xác suất ``PLANT_RATE`` mỗi kỳ.
PLANTED = (7, 38, 68)
PLANT_RATE = 0.03


# --------------------------------------------------------------------------- các chiến lược

def _window_sums(values: np.ndarray, window: int | None) -> np.ndarray:
    """``out[t] = Σ values[max(0, t − window) : t]`` cho t = 0..T (hàng T là kỳ kế tiếp)."""
    cum = np.vstack([np.zeros((1, values.shape[1])), np.cumsum(values, axis=0)])
    if window is None:
        return cum
    lo = np.maximum(np.arange(len(cum)) - window, 0)
    return cum - cum[lo]


def _gap(counts: np.ndarray) -> np.ndarray:
    """Số kỳ kể từ lần về gần nhất, tính ở đầu kỳ t (chưa về lần nào: t + 1)."""
    out = np.zeros((len(counts) + 1, N_NUMBERS))
    last = np.full(N_NUMBERS, -1)
    for t in range(len(counts) + 1):
        out[t] = np.where(last >= 0, t - last, t + 1)
        if t < len(counts):
            last[counts[t] > 0] = t
    return out


def _same_weekday(counts: np.ndarray, weekdays: np.ndarray, weeks: int) -> np.ndarray:
    """Tổng nháy ở ``weeks`` kỳ gần nhất CÙNG thứ với kỳ t (thứ của kỳ kế tiếp suy từ kỳ cuối + 1)."""
    out = np.zeros((len(counts) + 1, N_NUMBERS))
    history: dict[int, list[np.ndarray]] = {d: [] for d in range(7)}
    days = np.append(weekdays, (weekdays[-1] + 1) % 7 if len(weekdays) else 0)
    for t in range(len(counts) + 1):
        rows = history[int(days[t])]
        if rows:
            out[t] = np.sum(rows[-weeks:], axis=0)
        if t < len(counts):
            rows.append(counts[t])
    return out


def _positional_multi_prob(draws: np.ndarray, window: int | None, prior: float = 100.0) -> np.ndarray:
    """P(con i về ≥ 2 nháy) nếu mỗi vị trí giải có phân phối hai số cuối RIÊNG (Poisson-nhị thức).

    Xác suất của con i ở vị trí p là tần suất quá khứ ở chính vị trí ấy, làm trơn Dirichlet về
    1/100 với độ mạnh ``prior``. Nếu máy quay hay bộ số ở vị trí nào đó lệch thật, đây là cách
    duy nhất trong danh sách khai thác được độ lệch ấy một cách có nguyên tắc.
    """
    n_draws = len(draws)
    onehot = np.zeros((n_draws, LOTO_PER_DRAW, N_NUMBERS), dtype=np.int32)
    onehot[np.arange(n_draws)[:, None], np.arange(LOTO_PER_DRAW)[None, :], draws] = 1
    cum = np.concatenate([np.zeros((1, LOTO_PER_DRAW, N_NUMBERS), dtype=np.int32),
                          np.cumsum(onehot, axis=0, dtype=np.int32)])
    out = np.zeros((n_draws + 1, N_NUMBERS))
    for t in range(n_draws + 1):
        lo = 0 if window is None else max(0, t - window)
        seen = (cum[t] - cum[lo]).astype(float)
        q = (seen + prior / N_NUMBERS) / (t - lo + prior)
        log_none = np.log1p(-q).sum(axis=0)
        p0 = np.exp(log_none)
        p1 = p0 * (q / (1 - q)).sum(axis=0)
        out[t] = 1 - p0 - p1
    return out


def _digit_score(draws: np.ndarray, prior: float = 10.0) -> np.ndarray:
    """log P(chữ số hàng chục) + log P(chữ số hàng đơn vị), ước từ mọi lô quá khứ."""
    n_draws = len(draws)
    tens = np.zeros((n_draws, 10))
    units = np.zeros((n_draws, 10))
    np.add.at(tens, (np.repeat(np.arange(n_draws), LOTO_PER_DRAW), (draws // 10).ravel()), 1)
    np.add.at(units, (np.repeat(np.arange(n_draws), LOTO_PER_DRAW), (draws % 10).ravel()), 1)
    cum_t = np.vstack([np.zeros((1, 10)), np.cumsum(tens, axis=0)])
    cum_u = np.vstack([np.zeros((1, 10)), np.cumsum(units, axis=0)])
    pt = np.log((cum_t + prior / 10) / (cum_t.sum(axis=1, keepdims=True) + prior))
    pu = np.log((cum_u + prior / 10) / (cum_u.sum(axis=1, keepdims=True) + prior))
    numbers = np.arange(N_NUMBERS)
    return pt[:, numbers // 10] + pu[:, numbers % 10]


def _vip_v1(draws: np.ndarray) -> np.ndarray:
    """Điểm của bộ lọc lượt đầu, trọng số chọn trên 30 kỳ ngay trước (walk-forward lồng nhau)."""
    model = VIPMultiHitModel(draws, config=VIPConfig())
    out = np.zeros((len(draws) + 1, N_NUMBERS))
    for t in range(model.cfg.first_evaluated, len(draws) + 1):
        out[t] = model.scores(t, model.select_weights(t))
    return out


def feature_tensor(draws: np.ndarray, weekdays: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Mọi đặc trưng ``F[t, i, f]`` (hàng t chỉ đọc kỳ < t) cho hai mô hình học."""
    counts = counts_matrix(draws)
    multi = (counts >= 2).astype(float)
    raw = build_raw_features(counts, VIPConfig())
    extra = {
        "nhay_7": _window_sums(counts, 7),
        "nhay_100": _window_sums(counts, 100),
        "nhay_365": _window_sums(counts, 365),
        "multi_365": _window_sums(multi, 365),
        "yesterday": np.vstack([np.zeros((1, N_NUMBERS)), counts]),
        "weekday_52": _same_weekday(counts, weekdays, 52),
        "pos_multi_all": _positional_multi_prob(draws, None),
        "digit": _digit_score(draws),
    }
    tensor = np.concatenate([raw, np.stack(list(extra.values()), axis=-1)], axis=-1)
    return tensor, [*RAW_FEATURES, *extra]


def _learned(features: np.ndarray, labels: np.ndarray, start: int, kind: str) -> np.ndarray:
    """Mô hình học, khớp lại mỗi ``REFIT_EVERY`` kỳ trên MỌI kỳ đã quay trước điểm khớp.

    Hàng t của đặc trưng chỉ đọc kỳ < t và nhãn của kỳ t chỉ được dùng khi khớp ở điểm > t, nên
    điểm ở kỳ t không chứa thông tin nào từ kỳ t trở đi.
    """
    n_rows = features.shape[0]
    out = np.zeros((n_rows, N_NUMBERS))
    for fit_at in range(start, n_rows, REFIT_EVERY):
        x_train = features[WARMUP:fit_at].reshape(-1, features.shape[-1])
        y_train = labels[WARMUP:fit_at].ravel()
        if kind == "logit":
            scaler = StandardScaler().fit(x_train)
            model = LogisticRegression(C=0.01, max_iter=500).fit(scaler.transform(x_train), y_train)
            predict = lambda x, m=model, s=scaler: m.predict_proba(s.transform(x))[:, 1]  # noqa: E731
        else:
            model = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
                                                   min_samples_leaf=200, l2_regularization=1.0,
                                                   random_state=0).fit(x_train, y_train)
            predict = lambda x, m=model: m.predict_proba(x)[:, 1]  # noqa: E731
        stop = min(fit_at + REFIT_EVERY, n_rows)
        block = features[fit_at:stop]
        out[fit_at:stop] = predict(block.reshape(-1, block.shape[-1])).reshape(stop - fit_at, N_NUMBERS)
    return out


def strategy_scores(draws: np.ndarray, weekdays: np.ndarray, *, learned: bool = True,
                    include_vip: bool = True) -> dict[str, np.ndarray]:
    """Điểm ``S[t, i]`` cho t = 0..T của mọi chiến lược. Hàng T là kỳ chưa quay."""
    counts = counts_matrix(draws)
    multi = (counts >= 2).astype(float)
    rng = np.random.default_rng(TIE_SEED)
    out: dict[str, np.ndarray] = {"random": rng.random((len(draws) + 1, N_NUMBERS))}
    for window in (30, 100, 365, None):
        out[f"multi_hot_{window or 'all'}"] = _window_sums(multi, window)
    for window in (7, 30, 100, 365, None):
        out[f"nhay_hot_{window or 'all'}"] = _window_sums(counts, window)
    for window in (30, 365):
        out[f"nhay_cold_{window}"] = -_window_sums(counts, window)
    gap = _gap(counts)
    out["gan_longest"] = gap
    out["gan_shortest"] = -gap
    out["repeat_yesterday"] = np.vstack([np.zeros((1, N_NUMBERS)), counts])
    out["repeat_multi_yesterday"] = np.vstack([np.zeros((1, N_NUMBERS)), multi])
    out["weekday_52"] = _same_weekday(counts, weekdays, 52)
    out["position_bias_all"] = _positional_multi_prob(draws, None)
    out["position_bias_365"] = _positional_multi_prob(draws, 365)
    out["digit_bias"] = _digit_score(draws)
    if include_vip:
        out["vip_v1"] = _vip_v1(draws)
    if learned:
        features, _ = feature_tensor(draws, weekdays)
        labels = np.vstack([multi, np.zeros((1, N_NUMBERS))])
        start = WARMUP + REFIT_EVERY
        out["logistic_all_features"] = _learned(features, labels, start, "logit")
        out["gbm_all_features"] = _learned(features, labels, start, "gbm")
    return out


# --------------------------------------------------------------------------- chấm

@dataclass(frozen=True)
class Score:
    """Kết quả của một chiến lược trên một khoảng kỳ."""

    draws: int
    picks: int
    hits: int
    expected: float
    z: float
    p_one_sided: float

    @property
    def rate(self) -> float:
        return self.hits / self.picks if self.picks else float("nan")

    @property
    def lift(self) -> float:
        return self.hits / self.expected if self.expected else float("nan")


def top_k(scores: np.ndarray, k: int = TOP_K) -> np.ndarray:
    """Chỉ số top-k mỗi hàng; hoà phá bằng nhiễu cố định (dưới mọi khác biệt thật của điểm)."""
    jitter = np.random.default_rng(TIE_SEED + 1).random(scores.shape) * 1e-9
    span = np.ptp(scores, axis=1, keepdims=True)
    return np.argsort(-(scores + jitter * np.where(span > 0, span, 1.0)), axis=1, kind="stable")[:, :k]


def evaluate(scores: np.ndarray, multi: np.ndarray, rows: range, k: int = TOP_K) -> Score:
    """Trúng của top-k so với chọn bừa k con trong CÙNG kỳ (siêu bội), cộng qua ``rows``."""
    rows = np.asarray(list(rows))
    picked = top_k(scores[rows], k)
    hits = int(np.take_along_axis(multi[rows], picked, axis=1).sum())
    expected, variance = random_pick_null(multi[rows].sum(axis=1), k)
    z = (hits - expected) / np.sqrt(variance) if variance > 0 else 0.0
    return Score(len(rows), len(rows) * k, hits, expected, float(z), float(norm.sf(z)))


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """p đã hiệu chỉnh Holm–Bonferroni (đơn điệu, chặn ở 1)."""
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m, running, out = len(ordered), 0.0, {}
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        out[name] = running
    return out


def any_hit_rates(scores: np.ndarray, counts: np.ndarray, rows: range,
                  ks: tuple[int, ...] = (1, 3, 5, 10, 20)) -> dict[str, dict[int, float]]:
    """Tỉ lệ kỳ có ÍT NHẤT một con trong top-k trúng, cho "≥ 2 nháy" và cho "≥ 1 nháy"."""
    rows = np.asarray(list(rows))
    order = top_k(scores[rows], max(ks))
    out: dict[str, dict[int, float]] = {"multi": {}, "single": {}}
    for k in ks:
        picked = order[:, :k]
        got = np.take_along_axis(counts[rows], picked, axis=1)
        out["multi"][k] = float((got >= 2).any(axis=1).mean())
        out["single"][k] = float((got >= 1).any(axis=1).mean())
    return out


def run_protocol(draws: np.ndarray, weekdays: np.ndarray, *, holdout: int = HOLDOUT,
                 learned: bool = True, include_vip: bool = True,
                 scores: dict[str, np.ndarray] | None = None) -> dict:
    """Toàn bộ giao thức: chấm giai đoạn phát triển, chọn ứng viên, kiểm một lần.

    ``scores`` (dùng trong phép kiểm) thay danh sách chiến lược bằng điểm dựng sẵn; phải có
    khoá ``random``.
    """
    counts = counts_matrix(draws)
    multi = (counts >= 2).astype(float)
    n_draws = len(draws)
    if n_draws - holdout <= WARMUP + REFIT_EVERY:
        raise ValueError("lịch sử quá ngắn cho giai đoạn phát triển")
    dev = range(WARMUP + REFIT_EVERY, n_draws - holdout)
    test = range(n_draws - holdout, n_draws)
    all_scores = scores if scores is not None else strategy_scores(
        draws, weekdays, learned=learned, include_vip=include_vip)
    dev_scores = {name: evaluate(s, multi, dev) for name, s in all_scores.items()}
    test_scores = {name: evaluate(s, multi, test) for name, s in all_scores.items()}
    dev_holm = holm({name: s.p_one_sided for name, s in dev_scores.items()})
    candidate = max((name for name in dev_scores if name != "random"), key=lambda n: dev_scores[n].z)
    verdict = test_scores[candidate].p_one_sided < ALPHA
    return {
        "draws": n_draws,
        "dev": (dev.start, dev.stop),
        "test": (test.start, test.stop),
        "base_theory": base_rate(),
        "base_dev": float(multi[list(dev)].mean()),
        "base_test": float(multi[list(test)].mean()),
        "dev_scores": dev_scores,
        "dev_holm": dev_holm,
        "test_scores": test_scores,
        "candidate": candidate,
        "candidate_passes": bool(verdict),
        "any_hit": {
            "candidate": any_hit_rates(all_scores[candidate], counts, test),
            "random": any_hit_rates(all_scores["random"], counts, test),
        },
    }


# --------------------------------------------------------------------------- in

def _row(name: str, s: Score, holm_p: float | None = None) -> str:
    extra = f"  Holm {holm_p:6.3f}" if holm_p is not None else ""
    return (f"  {name:<24} {s.hits:>5}/{s.picks:<6} {100 * s.rate:6.3f}%  kỳ vọng {s.expected:7.1f}"
            f"  ×{s.lift:5.3f}  z {s.z:+6.2f}  p {s.p_one_sided:6.3f}{extra}")


def render(result: dict, title: str) -> str:
    lines = [title, "",
             f"Lịch sử {result['draws']} kỳ. Nền lý thuyết P(≥ 2 nháy) = {100 * result['base_theory']:.3f}%;"
             f" thực đo: phát triển {100 * result['base_dev']:.3f}%, kiểm {100 * result['base_test']:.3f}%.",
             "", f"Giai đoạn phát triển (kỳ {result['dev'][0]}..{result['dev'][1] - 1}), top-{TOP_K}:"]
    for name, s in sorted(result["dev_scores"].items(), key=lambda kv: -kv[1].z):
        lines.append(_row(name, s, result["dev_holm"][name]))
    cand = result["candidate"]
    lines += ["", f"Ứng viên duy nhất (z cao nhất ở giai đoạn phát triển): {cand}",
              f"Giai đoạn kiểm (kỳ {result['test'][0]}..{result['test'][1] - 1}), quyết định một lần:",
              _row(cand, result["test_scores"][cand]),
              f"  → {'ĐẠT' if result['candidate_passes'] else 'KHÔNG ĐẠT'} (ngưỡng p một phía < {ALPHA})",
              "", "Giai đoạn kiểm, mọi chiến lược (chỉ để minh bạch, không dùng để chọn):"]
    for name, s in sorted(result["test_scores"].items(), key=lambda kv: -kv[1].z):
        lines.append(_row(name, s))
    lines += ["", "Tỉ lệ kỳ có ít nhất một con trúng trong top-k (giai đoạn kiểm):",
              "  k    ≥2 nháy: ứng viên / chọn bừa     ≥1 nháy: ứng viên / chọn bừa"]
    cand_hits, rand_hits = result["any_hit"]["candidate"], result["any_hit"]["random"]
    for k in cand_hits["multi"]:
        lines.append(f"  {k:<4} {100 * cand_hits['multi'][k]:6.2f}% / {100 * rand_hits['multi'][k]:6.2f}%"
                     f"          {100 * cand_hits['single'][k]:6.2f}% / {100 * rand_hits['single'][k]:6.2f}%")
    return "\n".join(lines)


def to_json(result: dict) -> dict:
    def score(s: Score) -> dict:
        return {"draws": s.draws, "picks": s.picks, "hits": s.hits, "rate": s.rate,
                "expected": s.expected, "lift": s.lift, "z": s.z, "p_one_sided": s.p_one_sided}
    return {**{k: v for k, v in result.items() if k not in {"dev_scores", "test_scores"}},
            "dev_scores": {n: score(s) for n, s in result["dev_scores"].items()},
            "test_scores": {n: score(s) for n, s in result["test_scores"].items()}}


def planted_history(n_draws: int, planted: tuple[int, ...] = PLANTED, plant_rate: float = PLANT_RATE,
                    seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Lịch sử giả định có tín hiệu NHẸ: ba con nhận thêm ≥ 2 nháy với xác suất ``plant_rate``/kỳ.

    0,03 đưa tỉ lệ ≥ 2 nháy của mỗi con được cài từ ~3% lên ~6%: một tín hiệu mà cả ba con cộng
    lại chỉ chiếm 3 trên 100 số, tức top-5 trúng thêm chừng 0,09 lượt mỗi kỳ.
    """
    frame = mock_history(n_draws, seed=seed, planted=planted, plant_rate=plant_rate)
    draws, labels = draws_from_frame(frame)
    return draws, pd.to_datetime(pd.Series(labels)).dt.weekday.to_numpy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", default=str(ROOT / "data" / "xsmb-2-digits.csv"))
    parser.add_argument("--until", help="chỉ dùng các kỳ tới ngày này (YYYY-MM-DD) — để tái lập một phép đo")
    parser.add_argument("--power-check", action="store_true", help="thêm lịch sử giả định có cài tín hiệu")
    parser.add_argument("--json", help="ghi kết quả JSON ra tệp này")
    args = parser.parse_args(argv)

    frame = pd.read_csv(args.csv, dtype=str)
    if args.until:
        frame = until(frame, args.until)
    draws, labels = draws_from_frame(frame)
    weekdays = pd.to_datetime(pd.Series(labels)).dt.weekday.to_numpy()
    result = run_protocol(draws, weekdays)
    print(render(result, "LÔ NHIỀU NHÁY — LƯỢT THỬ THỨ HAI, DỮ LIỆU THẬT"))
    payload = {"real": to_json(result)}
    if args.power_check:
        fake_draws, fake_weekdays = planted_history(len(draws))
        planted = run_protocol(fake_draws, fake_weekdays)
        planted_names = ", ".join(f"{n:02d}" for n in PLANTED)
        print("\n\n" + render(planted, f"KIỂM ĐỘ NHẠY — LỊCH SỬ GIẢ ĐỊNH, CÀI TÍN HIỆU NHẸ CHO {planted_names}"))
        payload["power_check"] = to_json(planted)
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
