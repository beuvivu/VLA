from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import norm, spearmanr

from forecast import multi_hit_forecast as forecast
from forecast import multi_hit_pairs as pairs
from core.atomic_io import atomic_write_text
from forecast.multi_hit_vip import (any_multi_chance, base_rate, counts_matrix, draws_from_frame, model_confidence,
                                    number_confidence, random_any_hit, random_pick_null)

OUT_DIR = "forecast/multi_hit"
VIP_FILE = "vip.json"
BENCHMARK_FILE = "benchmark.json"
MEASURE_VERSION = 10
BENCHMARK_VERSION = 6
POWER_SEEDS = tuple(range(7, 27))
POWER_REQUIRED = 0.8
VIP_FROZEN_AT = "2026-10-12"
BET_GRID = (0.05, 0.1, 0.2, 0.4, 0.8)
SECOND_ROUND_UNTIL = "2026-10-12"
RECENT_DRAWS = 10


def wilson(hits: float, n: float, z: float = float(norm.ppf(0.975))) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def draw_level_interval(per_draw_hits, k: int) -> tuple[tuple[float, float], float]:
    hits = np.asarray(per_draw_hits, dtype=float)
    picks = len(hits) * k
    if len(hits) < 2 or picks == 0:
        return wilson(hits.sum(), picks), float("nan")
    rate = hits.sum() / picks
    independent = k * rate * (1 - rate)
    deff = float(hits.var(ddof=1) / independent) if independent > 0 else 1.0
    n_eff = picks / deff if deff > 0 else float(picks)
    return wilson(rate * n_eff, n_eff), deff


def anytime_p(hits, expected, grid: tuple[float, ...] = BET_GRID) -> tuple[float, float]:
    diff = np.asarray(hits, dtype=float) - np.asarray(expected, dtype=float)
    if diff.size == 0:
        return 1.0, 1.0
    lam = np.asarray(grid, dtype=float)[:, None]
    factors = 1.0 + lam * diff[None, :]
    if (factors <= 0).any():
        raise ValueError("hệ số cược làm vốn âm — thu hẹp BET_GRID")
    log_paths = np.cumsum(np.log(factors), axis=1)
    log_mix = logsumexp(log_paths, axis=0) - math.log(len(grid))
    best = max(0.0, float(log_mix.max()))
    return math.exp(-best), math.exp(best)


def load_raw(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (pd.read_csv(data_dir / "xsmb.csv", dtype={"date": str}),
            pd.read_csv(data_dir / "xsmb-2-digits.csv", dtype=str))


def load_history(data_dir: Path) -> tuple[np.ndarray, list[str]]:
    frame = pd.read_csv(data_dir / "xsmb-2-digits.csv", dtype=str)
    return draws_from_frame(frame)


def history_fingerprint(draws: np.ndarray, labels: list[str], n: int | None = None) -> str:
    n = len(draws) if n is None else n
    digest = hashlib.sha256()
    digest.update("\n".join(labels[:n]).encode("utf-8"))
    digest.update(np.ascontiguousarray(np.asarray(draws[:n], dtype=np.int16)).tobytes())
    return digest.hexdigest()


def vip_section(raw: pd.DataFrame, two: pd.DataFrame, *, cfg: forecast.ForecastConfig | None = None,
                prospective_after: str | None = None) -> dict:
    cfg = cfg or forecast.ForecastConfig()
    after = forecast.FROZEN_AT if prospective_after is None else prospective_after
    table = forecast.build_table(raw, two, cfg)
    if len(table.anchors) <= cfg.warmup + 1:
        raise ValueError(f"cần hơn {cfg.warmup + 1} kỳ có đặc trưng để chấm mô hình")
    wf = forecast.walk_forward(table, cfg)
    ordered = two.assign(date=pd.to_datetime(two["date"]).dt.strftime("%Y-%m-%d")).sort_values("date", kind="stable")
    draws, labels = draws_from_frame(ordered.reset_index(drop=True))
    counts = table.counts
    k = cfg.top_k
    evaluated = table.anchors[wf.rows] + 1
    n_multi = (counts[evaluated] >= 2).sum(axis=1)
    hits = wf.hits
    picks_total = len(wf.rows) * k
    expected, variance = random_pick_null(n_multi, k)
    z = float((hits.sum() - expected) / math.sqrt(variance)) if variance > 0 else 0.0
    (lo, hi), deff = draw_level_interval(hits, k)
    per_draw_expected = k * n_multi / 100
    dates = [labels[t] for t in evaluated]
    later = np.array([str(d) > after for d in dates], dtype=bool)
    pro_hits = hits[later]
    pro_expected = per_draw_expected[later]
    p_anytime, e_max = anytime_p(pro_hits, pro_expected)
    pro_lift = float(pro_hits.sum() / pro_expected.sum()) if pro_expected.sum() > 0 else float("nan")
    day_hit = hits > 0
    day_random = random_any_hit(n_multi, k)
    day_var = float((day_random * (1 - day_random)).sum())
    day_z = float((day_hit.sum() - day_random.sum()) / math.sqrt(day_var)) if day_var > 0 else 0.0
    level = model_confidence(p_anytime, pro_lift)
    base = base_rate()
    recent = []
    for j in range(len(wf.rows) - 1, max(len(wf.rows) - RECENT_DRAWS, 0) - 1, -1):
        t = int(evaluated[j])
        multi_today = int((counts[t] >= 2).sum())
        recent.append({
            "date": labels[t],
            "picks": [{"number": f"{i:02d}", "hits": int(counts[t, i])} for i in wf.picks[j]],
            "multi": int(hits[j]),
            "numbers_multi": multi_today,
            "expected": k * multi_today / 100,
        })
    fc = wf.forecast
    model = fc.model
    last = len(table.anchors) - 1
    special = int(table.special[table.anchors[last]])
    picks = []
    for i, prob in zip(fc.picks, fc.printed, strict=True):
        picks.append({
            "number": f"{i:02d}",
            "probability": float(prob),
            "x_base": float(prob) / base,
            "confidence": number_confidence(level, float(prob), base),
            "reasons": forecast.reasons(model, table.X[last, i], int(i), special),
        })
    return {
        "version": MEASURE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_date": labels[-1],
        "target_date": table.target_date,
        "draws": int(len(draws)),
        "history_sha256": history_fingerprint(draws, labels),
        "base_theory": base,
        "rule": forecast.RULE,
        "config": {"top_k": k, "warmup": cfg.warmup, "refit": cfg.refit, "c_grid": list(forecast.C_GRID),
                   "features": len(forecast.FEATURES)},
        "model": {"C": model.C, "inner_gain": model.inner_gain,
                  "blocks": [{"start_date": labels[int(table.anchors[b["start"]]) + 1], "C": b["C"],
                              "inner_gain": b["inner_gain"]} for b in wf.blocks]},
        "experience": forecast.bridge_experience(table),
        "backtest": {
            "first_date": str(dates[0]),
            "last_date": str(dates[-1]),
            "draws": int(len(wf.rows)),
            "picks": int(picks_total),
            "hits": int(hits.sum()),
            "rate": float(hits.sum() / picks_total),
            "ci95": [_finite(lo), _finite(hi)],
            "design_effect": _finite(deff),
            "expected": float(expected),
            "random_rate": float(expected / picks_total),
            "lift": _finite(hits.sum() / expected) if expected > 0 else None,
            "z": z,
            "p_value": float(norm.sf(z)),
            "predicted": float(wf.printed.mean()),
            "days_hit": int(day_hit.sum()),
            "day_rate": float(day_hit.mean()),
            "day_random_rate": float(day_random.mean()),
            "day_z": day_z,
            "day_fair": any_multi_chance(k),
        },
        "prospective": {
            "after": after,
            "draws": int(later.sum()),
            "picks": int(later.sum()) * k,
            "hits": int(pro_hits.sum()),
            "expected": float(pro_expected.sum()),
            "lift": pro_lift if later.any() and math.isfinite(pro_lift) else None,
            "p_anytime": p_anytime,
            "e_max": e_max,
            "days_hit": int(day_hit[later].sum()),
            "days_expected": float(day_random[later].sum()),
        },
        "confidence": level,
        "picks": picks,
        "recent": recent,
        "pairs": pairs_section(draws, labels, prospective_after=prospective_after),
    }


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def pairs_section(draws: np.ndarray, labels: list[str], *,
                  prospective_after: str | None = None) -> dict | None:
    after = pairs.FROZEN_AT if prospective_after is None else prospective_after
    if len(draws) <= pairs.WINDOW:
        return None
    present = counts_matrix(draws) >= 1
    wf = pairs.walk_forward(present)
    k = pairs.TOP_K
    hits, expected = wf["hits"], wf["expected"]
    n = len(hits)
    diff = hits - expected
    se = float(diff.std(ddof=1) * math.sqrt(n)) if n > 1 else float("nan")
    z = float(diff.sum() / se) if se > 0 else float("nan")
    (lo, hi), deff = draw_level_interval(hits, k)
    dates = [labels[t] for t in wf["rows"]]
    later = np.array([str(d) > after for d in dates], dtype=bool)
    p_anytime, e_max = anytime_p(hits[later], expected[later])
    pro_expected = float(expected[later].sum())
    pro_lift = float(hits[later].sum() / pro_expected) if pro_expected > 0 else float("nan")
    level = model_confidence(p_anytime, pro_lift)
    recent = []
    for j in range(n - 1, max(n - RECENT_DRAWS, 0) - 1, -1):
        t = wf["rows"][j]
        row = present[t]
        recent.append({
            "date": labels[t],
            "picks": [{"pair": pairs.pair_label(i),
                       "hit": bool(row[pairs.PAIR_A[i]] and row[pairs.PAIR_B[i]])}
                      for i in wf["picks"][j]],
            "hits": int(hits[j]),
            "expected": float(expected[j]),
        })
    return {
        "frozen_at": after,
        "base_theory": pairs.base_rate(),
        "config": {"window": pairs.WINDOW, "top_k": k, "max_per_number": pairs.MAX_PER_NUMBER},
        "picks": [
            {"pair": pairs.pair_label(i), "together": together,
             "last_date": labels[last] if last >= 0 else None}
            for i, together, last in zip(wf["picks"][-1], wf["together"], wf["last"], strict=True)
        ],
        "backtest": {
            "first_date": str(dates[0]),
            "last_date": str(dates[-1]),
            "draws": n,
            "picks": n * k,
            "hits": int(hits.sum()),
            "rate": float(hits.sum() / (n * k)),
            "ci95": [_finite(lo), _finite(hi)],
            "design_effect": _finite(deff),
            "expected": float(expected.sum()),
            "random_rate": float(expected.sum() / (n * k)),
            "lift": _finite(hits.sum() / expected.sum()) if expected.sum() > 0 else None,
            "z": _finite(z),
            "p_value": _finite(float(norm.sf(z))) if math.isfinite(z) else None,
        },
        "prospective": {
            "after": after,
            "draws": int(later.sum()),
            "picks": int(later.sum()) * k,
            "hits": int(hits[later].sum()),
            "expected": pro_expected,
            "lift": pro_lift if later.any() and math.isfinite(pro_lift) else None,
            "p_anytime": p_anytime,
            "e_max": e_max,
        },
        "confidence": level,
        "recent": recent,
    }


def _range_dates(span: tuple[int, int], labels: list[str]) -> list[str]:
    start, stop = span
    return [labels[start], labels[stop - 1]]


def _rank_correlation(result: dict) -> float:
    names = [n for n in result["dev_scores"] if n != "random"]
    dev = [result["dev_scores"][n].z for n in names]
    test = [result["test_scores"][n].z for n in names]
    return float(spearmanr(dev, test).statistic)


def _score(s) -> dict:
    return {"hits": s.hits, "picks": s.picks, "rate": s.rate, "expected": s.expected,
            "lift": s.lift, "z": s.z, "p": s.p_one_sided}


def paired_any_hit_se(candidate: np.ndarray, rival: np.ndarray, counts: np.ndarray, rows: range,
                      ks: tuple[int, ...] = (1, 3, 5, 10, 20)) -> dict[str, dict[str, float]]:
    from forecast import multi_hit_benchmark as bm

    rows = np.asarray(list(rows))
    got_a = np.take_along_axis(counts[rows], bm.top_k(candidate[rows], max(ks)), axis=1)
    got_b = np.take_along_axis(counts[rows], bm.top_k(rival[rows], max(ks)), axis=1)
    out: dict[str, dict[str, float]] = {"multi": {}, "single": {}}
    for kind, need in (("multi", 2), ("single", 1)):
        for k in ks:
            diff = ((got_a[:, :k] >= need).any(axis=1).astype(float)
                    - (got_b[:, :k] >= need).any(axis=1).astype(float))
            out[kind][str(k)] = float(diff.std(ddof=1) / math.sqrt(len(diff))) if len(diff) > 1 else float("nan")
    return out


def registered_draws(labels: list[str]) -> int:
    return sum(1 for label in labels if str(label) <= SECOND_ROUND_UNTIL)


def _planted_run(job: tuple[int, int]) -> dict:
    from forecast import multi_hit_benchmark as bm

    n_draws, seed = job
    fake_draws, fake_weekdays = bm.planted_history(n_draws, seed=seed)
    return bm.run_protocol(fake_draws, fake_weekdays)


def power_estimate(n_draws: int, seeds: tuple[int, ...] = POWER_SEEDS, run=_planted_run,
                   workers: int | None = None) -> tuple[list[dict], dict]:
    jobs = [(n_draws, seed) for seed in seeds]
    if workers == 1 or len(jobs) <= 1:
        runs = [run(job) for job in jobs]
    else:
        import multiprocessing
        import os
        from concurrent.futures import ProcessPoolExecutor

        saved = os.environ.get("OMP_NUM_THREADS")
        os.environ["OMP_NUM_THREADS"] = "1"
        try:
            with ProcessPoolExecutor(max_workers=workers,
                                     mp_context=multiprocessing.get_context("spawn")) as pool:
                runs = list(pool.map(run, jobs))
        finally:
            if saved is None:
                os.environ.pop("OMP_NUM_THREADS", None)
            else:
                os.environ["OMP_NUM_THREADS"] = saved
    passes = sum(bool(r["candidate_passes"]) for r in runs)
    total = len(runs)
    rate = passes / total if total else float("nan")
    lo, hi = wilson(passes, total)
    return runs, {"runs": total, "passes": passes, "rate": rate, "ci95": [lo, hi],
                  "required": POWER_REQUIRED, "sensitive": bool(total and rate >= POWER_REQUIRED),
                  "seeds": list(seeds)}


def benchmark_section(draws: np.ndarray, labels: list[str]) -> dict:
    from forecast import multi_hit_benchmark as bm

    n = registered_draws(labels)
    draws, labels = draws[:n], list(labels[:n])
    weekdays = pd.to_datetime(pd.Series(labels)).dt.day_of_week.to_numpy()
    scores = bm.strategy_scores(draws, weekdays)
    real = bm.run_protocol(draws, weekdays, scores=scores)
    planted_runs, power = power_estimate(len(draws))
    planted = planted_runs[0]
    cand = real["candidate"]
    strategies = [
        {"name": name, "dev": _score(real["dev_scores"][name]), "dev_holm": real["dev_holm"][name],
         "test": _score(real["test_scores"][name])}
        for name in sorted(real["dev_scores"], key=lambda n: -real["dev_scores"][n].z)
    ]
    any_hit = {side: {kind: {str(k): v for k, v in rates.items()} for kind, rates in table.items()}
               for side, table in real["any_hit"].items()}
    any_hit["paired_se"] = paired_any_hit_se(scores[cand], scores["random"], counts_matrix(draws),
                                             range(*real["test"]))
    return {
        "version": BENCHMARK_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_date": labels[-1],
        "draws": int(real["draws"]),
        "history_sha256": history_fingerprint(draws, labels),
        "registered_until": SECOND_ROUND_UNTIL,
        "top_k": bm.TOP_K,
        "alpha": bm.ALPHA,
        "dev": _range_dates(real["dev"], labels),
        "test": _range_dates(real["test"], labels),
        "dev_draws": real["dev"][1] - real["dev"][0],
        "test_draws": real["test"][1] - real["test"][0],
        "base_theory": real["base_theory"],
        "base_dev": real["base_dev"],
        "base_test": real["base_test"],
        "candidate": cand,
        "candidate_passes": real["candidate_passes"],
        "candidate_test": _score(real["test_scores"][cand]),
        "rank_correlation": _rank_correlation(real),
        "strategies": strategies,
        "any_hit": any_hit,
        "power": power,
        "power_check": {
            "planted": [f"{n:02d}" for n in bm.PLANTED],
            "plant_rate": bm.PLANT_RATE,
            "seed": power["seeds"][0],
            "candidate": planted["candidate"],
            "candidate_passes": planted["candidate_passes"],
            "candidate_dev_z": planted["dev_scores"][planted["candidate"]].z,
            "candidate_test": _score(planted["test_scores"][planted["candidate"]]),
            "base_test": planted["base_test"],
            "rank_correlation": _rank_correlation(planted),
        },
    }


def benchmark_is_valid(cached: dict | None, draws: np.ndarray, labels: list[str]) -> bool:
    if not cached or cached.get("version") != BENCHMARK_VERSION:
        return False
    measured = int(cached.get("draws", 0))
    if measured <= 0 or measured != registered_draws(labels):
        return False
    return cached.get("history_sha256") == history_fingerprint(draws, labels, measured)


def vip_status(vip: dict | None, draws: np.ndarray, labels: list[str]) -> str:
    if not vip or vip.get("version") != MEASURE_VERSION:
        return "invalid"
    measured = int(vip.get("draws", 0))
    if not 0 < measured <= len(draws):
        return "invalid"
    if vip.get("history_sha256") != history_fingerprint(draws, labels, measured):
        return "invalid"
    return "current" if measured == len(draws) else "behind"


def benchmark_is_stale(cached: dict | None, draws: np.ndarray, labels: list[str]) -> bool:
    return not benchmark_is_valid(cached, draws, labels)


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def run(data_dir: Path, *, force_benchmark: bool = False,
        cfg: forecast.ForecastConfig | None = None) -> dict[str, Path]:
    draws, labels = load_history(data_dir)
    out = data_dir / OUT_DIR
    written = {"vip": out / VIP_FILE}
    _write(written["vip"], vip_section(*load_raw(data_dir), cfg=cfg))
    bench_path = out / BENCHMARK_FILE
    if force_benchmark or benchmark_is_stale(_read(bench_path), draws, labels):
        _write(bench_path, benchmark_section(draws, labels))
        written["benchmark"] = bench_path
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--force-benchmark", action="store_true",
                        help="đo lại giao thức lượt hai dù bản đệm còn mới")
    args = parser.parse_args(argv)
    for name, path in run(Path(args.data_dir), force_benchmark=args.force_benchmark).items():
        print(f"[OK] {name} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
