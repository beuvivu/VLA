from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from core.atomic_io import atomic_write_text
from core.paths import REPO_ROOT
from core.regional_domain import LOTO_DRAWS_PER_STATION, NUMBER_SPACE, REGIONS, baseline_rate
from ensemble.hierarchical_pooling import fit_shrinkage_to_prior
from evaluation.forecast_metrics import (
    chance_reciprocal_rank,
    cluster_bootstrap_ci,
    paired_sign_flip_p,
    rank_of_truth,
    top_k_mass,
)
from stats.regional_stats import StationHistory, cage_table, load_stations
from stats.statistical_corrections import holm

SCHEMA_VERSION = 1
BENCHMARK_VERSION = 2
WARMUP = 20
ROLLING = 20
RECENT = 10
SMOOTHING = 1.0
CAGE_PRIOR = 50.0
REFIT_DAYS = 14
MIN_TRAIN_DRAWS = 5
MIN_TRAIN_ROWS = 2000
TOP_K = 10
ALPHA = 0.05
MODES: tuple[str, ...] = ("loto", "de")
PROBABILITY_MODELS: tuple[str, ...] = (
    "deu", "tan_suat", "tan_suat_truot", "bayes_thuc_nghiem", "long_chu_so", "long_bayes", "hoi_quy_logistic",
)
POST_HOC_MODELS: frozenset[str] = frozenset({"long_bayes"})
RANKINGS: tuple[str, ...] = ("nong", "gan", "lap")
MODEL_NAMES: dict[str, str] = {
    "deu": "Dự báo đều",
    "tan_suat": "Tần suất lịch sử",
    "tan_suat_truot": f"Tần suất {ROLLING} kỳ gần nhất",
    "bayes_thuc_nghiem": "Bayes thực nghiệm",
    "long_chu_so": "Chữ số theo lồng",
    "long_bayes": "Chữ số theo lồng (Bayes thực nghiệm)",
    "hoi_quy_logistic": "Hồi quy logistic",
    "nong": "Số nóng",
    "gan": "Lô gan",
    "lap": "Lặp kỳ trước",
}
CONFIG: dict[str, float | int] = {
    "benchmark_version": BENCHMARK_VERSION,
    "warmup_draws": WARMUP,
    "rolling_draws": ROLLING,
    "recent_draws": RECENT,
    "smoothing": SMOOTHING,
    "cage_prior": CAGE_PRIOR,
    "refit_days": REFIT_DAYS,
    "top_k": TOP_K,
    "alpha": ALPHA,
}
OUT = Path("evaluation") / "regional_benchmark" / "benchmark.json"
_EPS = 1e-12


@dataclass(frozen=True)
class StationState:

    station: StationHistory
    hit: np.ndarray
    cum: np.ndarray
    window: np.ndarray
    recent: np.ndarray
    gap: np.ndarray
    last: np.ndarray
    cage: np.ndarray


def station_state(station: StationHistory, mode: str) -> StationState:
    hit = station.hits(mode)
    n = len(station)
    before = np.vstack([np.zeros((1, NUMBER_SPACE), dtype=np.int64), np.cumsum(hit, axis=0)])
    index = np.arange(n)
    window = before[index] - before[np.maximum(index - ROLLING, 0)]
    recent = before[index] - before[np.maximum(index - RECENT, 0)]
    gap = np.empty((n, NUMBER_SPACE), dtype=np.int64)
    running = np.zeros(NUMBER_SPACE, dtype=np.int64)
    seen = np.zeros(NUMBER_SPACE, dtype=bool)
    for t in range(n):
        gap[t] = np.where(seen, running, t)
        running = np.where(hit[t], 0, running + 1)
        seen |= hit[t]
    last = np.vstack([np.zeros((1, NUMBER_SPACE), dtype=bool), hit[:-1]])
    per_draw = np.stack([cage_table(station.digits[t : t + 1]) for t in range(n)]) if n else np.zeros((0, 6, 10))
    cage = np.concatenate([np.zeros((1, *per_draw.shape[1:]), dtype=np.int64), np.cumsum(per_draw, axis=0)])[:n]
    return StationState(station, hit, before[:n], window, recent, gap, last, cage)


def _normalise(mode: str, p: np.ndarray) -> np.ndarray:
    return p / p.sum(axis=1, keepdims=True) if mode == "de" else p


def uniform(state: StationState, mode: str) -> np.ndarray:
    return np.full(state.hit.shape, baseline_rate(mode))


def cumulative_frequency(state: StationState, mode: str) -> np.ndarray:
    n = np.arange(len(state.hit))[:, None]
    return (state.cum + SMOOTHING * baseline_rate(mode)) / (n + SMOOTHING)


def rolling_frequency(state: StationState, mode: str) -> np.ndarray:
    n = np.minimum(np.arange(len(state.hit)), ROLLING)[:, None]
    return (state.window + SMOOTHING * baseline_rate(mode)) / (n + SMOOTHING)


def cage_law(counts: np.ndarray) -> np.ndarray:
    return (counts + CAGE_PRIOR / 10.0) / (counts.sum(axis=-1, keepdims=True) + CAGE_PRIOR)


def cage_digits(state: StationState, mode: str) -> np.ndarray:
    per_prize = _per_prize(cage_law(state.cage))
    if mode == "de":
        return per_prize
    return 1.0 - (1.0 - per_prize) ** LOTO_DRAWS_PER_STATION


def _per_prize(law: np.ndarray) -> np.ndarray:
    return (law[:, 1, :, None] * law[:, 0, None, :]).reshape(len(law), NUMBER_SPACE)


def cage_empirical_bayes(state: StationState, mode: str) -> np.ndarray:
    law = np.empty(state.cage.shape, dtype=float)
    for t in range(len(law)):
        counts = state.cage[t].astype(float)
        totals = counts.sum(axis=1)
        used = totals > 0
        kappa = (
            fit_shrinkage_to_prior(counts[used].ravel(), np.repeat(totals[used], 10), 0.1)
            if used.any() else np.inf
        )
        law[t] = (counts + kappa * 0.1) / (totals[:, None] + kappa) if np.isfinite(kappa) else 0.1
    per_prize = _per_prize(law)
    if mode == "de":
        return per_prize
    return 1.0 - (1.0 - per_prize) ** LOTO_DRAWS_PER_STATION


def _draws_before(station: StationHistory, day: str) -> int:
    return int(np.searchsorted(np.array(station.dates), day, side="left"))


def empirical_bayes(states: list[StationState], mode: str) -> list[np.ndarray]:
    base = baseline_rate(mode)
    days = sorted({day for state in states for day in state.station.dates})
    kappa: dict[str, float] = {}
    for day in days:
        successes, trials = [], []
        for state in states:
            seen = _draws_before(state.station, day)
            if seen:
                row = state.cum[seen] if seen < len(state.hit) else state.cum[-1] + state.hit[-1]
                successes.append(row)
                trials.append(np.full(NUMBER_SPACE, seen))
        kappa[day] = (
            fit_shrinkage_to_prior(np.concatenate(successes), np.concatenate(trials), base) if successes else np.inf
        )
    out = []
    for state in states:
        n = np.arange(len(state.hit))[:, None]
        k = np.array([kappa[day] for day in state.station.dates])[:, None]
        with np.errstate(invalid="ignore"):
            p = np.where(np.isfinite(k), (state.cum + k * base) / (n + k), base)
        out.append(_normalise(mode, p))
    return out


def _features(state: StationState, mode: str) -> np.ndarray:
    base = baseline_rate(mode)
    cap = 3.0 / base
    return np.stack([
        cumulative_frequency(state, mode) - base,
        state.recent / RECENT - base,
        state.last.astype(float),
        np.minimum(state.gap, cap) / cap,
    ], axis=-1)


def logistic(states: list[StationState], mode: str) -> list[np.ndarray]:
    base = baseline_rate(mode)
    features = [_features(state, mode) for state in states]
    out = [np.full(state.hit.shape, base) for state in states]
    days = sorted({day for state in states for day in state.station.dates})
    fitted_on: date | None = None
    model: LogisticRegression | None = None
    for day in days:
        today = date.fromisoformat(day)
        if fitted_on is None or today >= fitted_on + timedelta(days=REFIT_DAYS):
            rows, labels = [], []
            for state, x in zip(states, features, strict=True):
                seen = _draws_before(state.station, day)
                if seen > MIN_TRAIN_DRAWS:
                    rows.append(x[MIN_TRAIN_DRAWS:seen].reshape(-1, x.shape[-1]))
                    labels.append(state.hit[MIN_TRAIN_DRAWS:seen].reshape(-1))
            fitted_on, model = today, None
            if rows:
                y = np.concatenate(labels)
                if len(y) >= MIN_TRAIN_ROWS and 0 < y.sum() < len(y):
                    model = LogisticRegression(C=1.0, max_iter=300).fit(np.concatenate(rows), y)
        if model is None:
            continue
        for state, x, p in zip(states, features, out, strict=True):
            for t in np.flatnonzero(np.array(state.station.dates) == day):
                p[t] = model.predict_proba(x[t])[:, 1]
    return [_normalise(mode, p) for p in out]


def forecasts(states: list[StationState], mode: str) -> dict[str, list[np.ndarray]]:
    return {
        "deu": [uniform(s, mode) for s in states],
        "tan_suat": [_normalise(mode, cumulative_frequency(s, mode)) for s in states],
        "tan_suat_truot": [_normalise(mode, rolling_frequency(s, mode)) for s in states],
        "bayes_thuc_nghiem": empirical_bayes(states, mode),
        "long_chu_so": [cage_digits(s, mode) for s in states],
        "long_bayes": [cage_empirical_bayes(s, mode) for s in states],
        "hoi_quy_logistic": logistic(states, mode),
    }


def ranking_scores(states: list[StationState]) -> dict[str, list[np.ndarray]]:
    return {
        "nong": [s.window.astype(float) for s in states],
        "gan": [s.gap.astype(float) for s in states],
        "lap": [s.last.astype(float) for s in states],
    }


def log_loss(mode: str, p: np.ndarray, hit: np.ndarray) -> np.ndarray:
    if mode == "de":
        return -np.log(np.clip((p * hit).sum(axis=1), _EPS, 1.0))
    q = np.clip(p, _EPS, 1.0 - _EPS)
    return -(hit * np.log(q) + (~hit) * np.log(1.0 - q)).mean(axis=1)


def _round(value: float) -> float | None:
    return round(float(value), 10) if np.isfinite(value) else None


def _gain_block(gain: np.ndarray, dates: np.ndarray) -> dict:
    low, high = cluster_bootstrap_ci(gain, clusters=dates)
    stderr = float(gain.std(ddof=1) / np.sqrt(len(gain))) if len(gain) > 1 else float("nan")
    half = len(gain) // 2
    order = np.argsort(dates, kind="stable")
    return {
        "mean_gain": _round(gain.mean()),
        "ci_low": _round(low),
        "ci_high": _round(high),
        "p_value": paired_sign_flip_p(gain, clusters=dates),
        "detectable_gain": _round(2.8 * stderr),
        "halves": [_round(gain[order[:half]].mean()), _round(gain[order[half:]].mean())],
    }


def evaluate_mode(states: list[StationState], mode: str) -> dict:
    scored = [np.arange(WARMUP, len(s.hit)) for s in states]
    total = int(sum(len(rows) for rows in scored))
    if total < 2:
        return {"station_draws": total, "models": {}, "rankings": {}, "edge": []}
    hit = np.concatenate([s.hit[rows] for s, rows in zip(states, scored, strict=True)])
    dates = np.concatenate([np.array(s.station.dates)[rows] for s, rows in zip(states, scored, strict=True)])
    province = np.concatenate([np.full(len(rows), s.station.province) for s, rows in zip(states, scored, strict=True)])
    base = baseline_rate(mode)
    truth = hit.argmax(axis=1) if mode == "de" else None
    hit_float = hit.astype(float)

    def stacked(per_station: list[np.ndarray]) -> np.ndarray:
        return np.concatenate([p[rows] for p, rows in zip(per_station, scored, strict=True)])

    def ranking_block(scores: np.ndarray) -> dict:
        in_top = top_k_mass(scores, hit_float, TOP_K)
        if mode == "de":
            chance = TOP_K / NUMBER_SPACE
            rank, reciprocal = rank_of_truth(scores, truth)
            extra = {"mean_rank": _round(rank.mean()), "chance_rank": (NUMBER_SPACE + 1) / 2,
                     "mrr": _round(reciprocal.mean()), "chance_mrr": _round(chance_reciprocal_rank(NUMBER_SPACE))}
            per_draw = in_top
        else:
            chance = base
            extra = {"hits_per_draw": _round(in_top.mean())}
            per_draw = in_top / TOP_K
        low, high = cluster_bootstrap_ci(per_draw, clusters=dates)
        own = hit_float.mean(axis=1) if mode == "loto" else np.full(len(per_draw), chance)
        return {"top_k": TOP_K, "hit_rate": _round(per_draw.mean()), "chance": _round(chance),
                "ci_low": _round(low), "ci_high": _round(high),
                "p_value": paired_sign_flip_p(per_draw - own, clusters=dates), **extra}

    probabilities = {name: stacked(per_station) for name, per_station in forecasts(states, mode).items()}
    reference = log_loss(mode, probabilities["deu"], hit)
    models: dict[str, dict] = {}
    for name in PROBABILITY_MODELS:
        p = probabilities[name]
        loss = log_loss(mode, p, hit)
        block = {
            "name": MODEL_NAMES[name],
            "post_hoc": name in POST_HOC_MODELS,
            "log_loss": _round(loss.mean()),
            "log_loss_uniform": _round(reference.mean()),
            "skill": _round(1.0 - loss.mean() / reference.mean()),
            "level": _round(p.sum(axis=1).mean()),
            "ranking": ranking_block(p),
        }
        if name != "deu":
            gain = reference - loss
            block.update(_gain_block(gain, dates))
            stations = []
            for name_of in sorted(set(province)):
                chosen = province == name_of
                if chosen.sum() >= 2:
                    stations.append({"province": str(name_of), "draws": int(chosen.sum()),
                                     "mean_gain": _round(gain[chosen].mean()),
                                     "p_value": paired_sign_flip_p(gain[chosen])})
            block["stations"] = stations
        models[name] = block
    candidates = [name for name in PROBABILITY_MODELS if name != "deu"]
    family = [row for name in candidates for row in models[name]["stations"]]
    for row, adjusted in zip(family, holm([r["p_value"] for r in family]), strict=True):
        row["p_holm"] = adjusted
    for name in candidates:
        models[name]["stations_with_edge"] = [r["province"] for r in models[name]["stations"]
                                              if r["p_holm"] < ALPHA and (r["mean_gain"] or 0) > 0]
    for name, adjusted in zip(candidates, holm([models[n]["p_value"] for n in candidates]), strict=True):
        models[name]["p_holm"] = adjusted
        models[name]["edge"] = bool(adjusted < ALPHA and (models[name]["mean_gain"] or 0) > 0)
    rankings = {name: {"name": MODEL_NAMES[name], **ranking_block(stacked(per_station))}
                for name, per_station in ranking_scores(states).items()}
    for name, adjusted in zip(RANKINGS, holm([rankings[n]["p_value"] for n in RANKINGS]), strict=True):
        rankings[name]["p_holm"] = adjusted
        rankings[name]["edge"] = bool(adjusted < ALPHA and rankings[name]["hit_rate"] > rankings[name]["chance"])
    return {
        "station_draws": total,
        "stations": len(states),
        "first_scored": min(dates.tolist()),
        "last_scored": max(dates.tolist()),
        "baseline": _round(base),
        "models": models,
        "rankings": rankings,
        "edge": [name for name in candidates if models[name]["edge"]]
        + [name for name in RANKINGS if rankings[name]["edge"]],
    }


def _vn(value: float, spec: str) -> str:
    return format(value, spec).replace(".", ",")


def reading(region_name: str, modes: dict[str, dict]) -> str:
    labels = {"loto": "lô", "de": "đuôi Đặc Biệt"}
    if not any(block.get("models") for block in modes.values()):
        return f"{region_name}: chưa đủ kỳ để chấm (mỗi đài cần hơn {WARMUP} kỳ)."
    wins, ties = [], []
    for mode, block in modes.items():
        if not block.get("models"):
            continue
        if block["edge"]:
            for name in block["edge"]:
                source = block["models"].get(name) or block["rankings"][name]
                where = source.get("stations_with_edge") or []
                tail = f" (phần thắng nằm ở đài: {', '.join(where)})" if where else ""
                wins.append(f"{MODEL_NAMES[name]} cho {labels[mode]}{tail}")
        else:
            ties.append(labels[mode])
    draws = max(block.get("station_draws", 0) for block in modes.values())
    parts = []
    if ties:
        parts.append(
            f"CHƯA CHỨNG MINH ĐƯỢC LỢI THẾ DỰ BÁO cho {' và '.join(ties)}: không cách nào trong "
            f"{len(PROBABILITY_MODELS) - 1} mô hình xác suất và {len(RANKINGS)} cách xếp hạng thắng dự báo đều "
            f"trên {draws} kỳ ngoài mẫu sau hiệu chỉnh Holm."
        )
    if wins:
        parts.append(
            "Thắng dự báo đều ngoài mẫu: " + "; ".join(wins) + ". Mô hình được chọn sau khi đã nhìn dữ liệu, nên "
            "kết quả này chỉ được coi là lợi thế khi phép kiểm tiến cứu đã đăng ký xác nhận trên các kỳ mới."
        )
    single = station_edges(modes)
    if single:
        listed = "; ".join(
            f"{row['province']} — {row['model_name']} cho {labels[row['mode']]} (lợi "
            f"{_vn(row['mean_gain'], '+.4f')} log-loss mỗi kỳ trên {row['draws']} kỳ, p Holm "
            f"{_vn(row['p_holm'], '.3f')})"
            for row in single
        )
        parts.append(
            f"Riêng từng đài (hiệu chỉnh Holm trên mọi cặp đài × mô hình của miền): {listed}. Đây là số đo hồi cứu trên một "
            "sổ chỉ ghi từ một nơi; nó chỉ thành lợi thế khi phép kiểm tiến cứu đã đăng ký xác nhận trên kỳ mới."
        )
    return f"{region_name}: " + " ".join(parts)


def station_edges(modes: dict[str, dict]) -> list[dict]:
    best: dict[tuple[str, str], dict] = {}
    for mode, block in modes.items():
        for name, model in (block.get("models") or {}).items():
            for row in model.get("stations", []):
                if row["province"] not in model.get("stations_with_edge", []):
                    continue
                key = (row["province"], mode)
                candidate = {"province": row["province"], "mode": mode, "model": name,
                             "model_name": MODEL_NAMES[name], "post_hoc": name in POST_HOC_MODELS,
                             "mean_gain": row["mean_gain"], "draws": row["draws"], "p_holm": row["p_holm"]}
                held = best.get(key)
                if held is None or (candidate["post_hoc"], -candidate["mean_gain"]) < (
                    held["post_hoc"], -held["mean_gain"]
                ):
                    best[key] = candidate
    return [best[key] for key in sorted(best)]


def build(repo_root: Path) -> dict:
    regions = {}
    for region, name in REGIONS.items():
        stations = load_stations(repo_root / "data" / "regions" / f"xs{region}.csv", region)
        if not stations:
            continue
        modes = {mode: evaluate_mode([station_state(s, mode) for s in stations], mode) for mode in MODES}
        regions[region] = {
            "region_name": name,
            "data_through": max(s.dates[-1] for s in stations),
            "modes": modes,
            "station_edges": station_edges(modes),
            "reading": reading(name, modes),
        }
    return {"schema_version": SCHEMA_VERSION, "config": CONFIG, "regions": regions}


def run(repo_root: Path) -> Path:
    path = repo_root / "data" / OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(build(repo_root), ensure_ascii=False, indent=2) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Chấm walk-forward các cách dự báo cho đài XSMT/XSMN").parse_args(argv)
    print("Wrote:", run(REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
