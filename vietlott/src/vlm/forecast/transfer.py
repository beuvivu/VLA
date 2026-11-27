from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from vietlott_engine.core.products import ProductCode, write_text_atomic
from vietlott_engine.forecast.data import CONFIGS, DigitSpec, Series
from vietlott_engine.forecast.engine import Forecaster
from vlm.forecast.bayes_expert import BayesMixtureExpert
from vlm.forecast.service import _same_up_to_float_noise

VERSION = 1
PRODUCTS: tuple[ProductCode, ...] = (ProductCode.MAX3D, ProductCode.MAX3D_PRO)
COMPONENT = "digits"
PRIOR_POOLED = 0.5
REGISTERED_ON = date(2026, 11, 25)
PROMOTE_Z = 2.326
SUMMARY = "transfer.json"
LEDGER = "transfer-ledger.jsonl"
SCHEMA_VERSION = 1


def share(product: ProductCode) -> float:
    return 1.0 / (Forecaster.SWITCH_YEARS * CONFIGS[product].draws_per_year)


def _spec() -> DigitSpec:
    specs = {CONFIGS[p].components[COMPONENT] for p in PRODUCTS}
    if len(specs) != 1:
        raise ValueError("Các sản phẩm học chung phải cùng khuôn chữ số")
    return specs.pop()


def engine_fingerprint() -> str:
    import hashlib

    from vietlott_engine.forecast.data import digit_counts

    spec = _spec()
    rng = np.random.default_rng(20261125)
    counts = digit_counts(rng.integers(0, spec.alphabet, size=(24, spec.per_draw, spec.positions)), spec.alphabet)
    expert = BayesMixtureExpert(PRODUCTS[0], COMPONENT, spec)
    predictions = []
    for index, row in enumerate(counts, start=1):
        predictions.append(expert.predict())
        expert.learn(row, index)
    payload = {
        "switch_years": Forecaster.SWITCH_YEARS,
        "share": {p.value: share(p) for p in PRODUCTS},
        "experts": list(expert.component.names),
        "prior": np.round(expert.component.prior, 12).tolist(),
        "predictions": np.round(np.asarray(predictions), 9).tolist(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def final_through(series: dict[ProductCode, Series]) -> date | None:
    horizons = []
    for product in PRODUCTS:
        s = series[product]
        if len(s) == 0:
            return None
        ids = np.asarray(s.draw_ids)
        days = [np.datetime64(d, "D").astype(object) for d in s.dates]
        last = days[0]
        for index in range(1, len(s)):
            if ids[index] != ids[index - 1] + 1 and days[index] > REGISTERED_ON:
                break
            last = days[index]
        horizons.append(last)
    return min(horizons)


def fixed_share_bound(draws: int, product: ProductCode) -> float:
    return -math.log(1.0 - PRIOR_POOLED) - draws * math.log1p(-share(product))


@dataclass(frozen=True)
class Step:

    product: ProductCode
    draw_id: int
    day: date
    sep: float
    pool: float
    mix: float
    w_pool: float


class TransferModel:

    def __init__(self) -> None:
        spec = _spec()
        self.spec = spec
        self.sep = {p: BayesMixtureExpert(p, COMPONENT, spec) for p in PRODUCTS}
        self.pool = BayesMixtureExpert(PRODUCTS[0], COMPONENT, spec)
        self.log_prior = np.log([1.0 - PRIOR_POOLED, PRIOR_POOLED])
        self.log_w = {p: self.log_prior.copy() for p in PRODUCTS}
        self.pooled_draws = 0
        self.uniform = -spec.per_draw * spec.positions * math.log(spec.alphabet)

    def laws(self, product: ProductCode) -> tuple[np.ndarray, np.ndarray, float]:
        shape = (self.spec.positions, self.spec.alphabet)
        w = np.exp(self.log_w[product] - np.logaddexp.reduce(self.log_w[product]))
        return self.sep[product].predict().reshape(shape), self.pool.predict().reshape(shape), float(w[1])

    def mixed(self, product: ProductCode) -> np.ndarray:
        own, pooled, w_pool = self.laws(product)
        return (1.0 - w_pool) * own + w_pool * pooled

    def score(self, product: ProductCode, counts: np.ndarray, draw_id: int, day: date) -> Step:
        own, pooled, w_pool = self.laws(product)
        c = np.asarray(counts, dtype=float).reshape(own.shape)
        ll = np.array([float((c * np.log(own)).sum()), float((c * np.log(pooled)).sum())])
        mix = float(np.logaddexp.reduce(self.log_w[product] + ll) - np.logaddexp.reduce(self.log_w[product]))
        posterior = self.log_w[product] + ll
        posterior -= np.logaddexp.reduce(posterior)
        a = share(product)
        log_w = np.logaddexp(math.log1p(-a) + posterior, math.log(a) + self.log_prior)
        self.log_w[product] = log_w - np.logaddexp.reduce(log_w)
        return Step(product, int(draw_id), day, ll[0] - self.uniform, ll[1] - self.uniform, mix - self.uniform, w_pool)

    def learn(self, product: ProductCode, counts: np.ndarray, draw_id: int) -> None:
        self.sep[product].learn(np.asarray(counts, dtype=float), int(draw_id))
        self.pooled_draws += 1
        self.pool.learn(np.asarray(counts, dtype=float), self.pooled_draws)


def events_by_day(series: dict[ProductCode, Series]) -> list[tuple[date, list[tuple[ProductCode, int]]]]:
    days: dict[date, list[tuple[ProductCode, int]]] = {}
    for product in PRODUCTS:
        s = series[product]
        for index in range(len(s)):
            day = np.datetime64(s.dates[index], "D").astype(object)
            days.setdefault(day, []).append((product, index))
    return sorted(days.items())


def walk_forward(series: dict[ProductCode, Series]) -> tuple[list[Step], TransferModel]:
    model = TransferModel()
    steps: list[Step] = []
    for day, events in events_by_day(series):
        observed = []
        for product, index in events:
            counts = np.asarray(series[product].obs[COMPONENT]["C"][index], dtype=float)
            draw_id = int(series[product].draw_ids[index])
            steps.append(model.score(product, counts, draw_id, day))
            observed.append((product, counts, draw_id))
        for product, counts, draw_id in observed:
            model.learn(product, counts, draw_id)
    return steps, model


def _paired(values: np.ndarray) -> dict:
    total = float(values.sum() / math.log(10))
    if values.size < 2 or float(values.std(ddof=1)) == 0.0:
        return {"draws": int(values.size), "log10": total, "z": 0.0}
    z = float(values.mean() / (values.std(ddof=1) / math.sqrt(values.size)))
    return {"draws": int(values.size), "log10": total, "z": z}


def _law_view(law: np.ndarray, spec: DigitSpec) -> list[dict]:
    out = []
    for position, row in enumerate(law):
        top = np.argsort(-row, kind="stable")[:3]
        out.append({"position": spec.position_labels[position],
                    "symbols": [{"symbol": int(a) + spec.symbol_offset, "p": float(row[a]),
                                 "lift": float(row[a] * spec.alphabet)} for a in top]})
    return out


def product_summary(product: ProductCode, steps: list[Step], model: TransferModel) -> dict:
    mine = [s for s in steps if s.product == product]
    sep = np.array([s.sep for s in mine])
    pool = np.array([s.pool for s in mine])
    mix = np.array([s.mix for s in mine])
    years = sorted({s.day.year for s in mine})
    by_year = []
    for year in years:
        idx = np.array([s.day.year == year for s in mine])
        by_year.append({"year": year, **_paired(mix[idx] - sep[idx])})
    own, pooled, w_pool = model.laws(product)
    return {
        "draws": len(mine),
        "last_date": mine[-1].day.isoformat() if mine else None,
        "log10_wealth": {"separate": float(sep.sum() / math.log(10)), "pooled": float(pool.sum() / math.log(10)),
                         "mixed": float(mix.sum() / math.log(10))},
        "mixed_vs_separate": _paired(mix - sep),
        "by_year": by_year,
        "w_pooled": w_pool,
        "fixed_share_bound_log10": fixed_share_bound(len(mine), product) / math.log(10),
        "next": {"mixed": _law_view(model.mixed(product), model.spec), "separate": _law_view(own, model.spec)},
    }


def prospective(steps: list[Step], ledger_path: Path, through: date | None, fingerprint: str) -> dict:
    rows = []
    if ledger_path.exists():
        rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    recorded = {(r["version"], r["product"], r["draw_id"]): r for r in rows}
    consistent = True
    engine_consistent = all(r.get("engine") == fingerprint for r in rows if r["version"] == VERSION)
    for step in steps:
        if step.day <= REGISTERED_ON or through is None or step.day > through:
            continue
        key = (VERSION, step.product.value, step.draw_id)
        gain_sep = round(step.mix - step.sep, 9)
        gain_uniform = round(step.mix, 9)
        if key in recorded:
            consistent = consistent and abs(recorded[key]["gain_vs_separate"] - gain_sep) <= 1e-6
            continue
        if not engine_consistent:
            continue
        row = {"version": VERSION, "product": step.product.value, "draw_id": step.draw_id, "engine": fingerprint,
               "date": step.day.isoformat(), "gain_vs_separate": gain_sep, "gain_vs_uniform": gain_uniform}
        rows.append(row)
        recorded[key] = row
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    if not ledger_path.exists() or ledger_path.read_text(encoding="utf-8") != text:
        write_text_atomic(ledger_path, text)
    out = {"version": VERSION, "registered_on": REGISTERED_ON.isoformat(),
           "ledger_through": through.isoformat() if through is not None else None,
           "engine_fingerprint": fingerprint, "ledger_consistent": consistent,
           "engine_consistent": engine_consistent, "products": {}}
    for product in PRODUCTS:
        mine = [r for r in rows if r["version"] == VERSION and r["product"] == product.value]
        gains = np.array([r["gain_vs_separate"] for r in mine], dtype=float)
        uniform = float(sum(r["gain_vs_uniform"] for r in mine) / math.log(10))
        paired = _paired(gains)
        eligible = consistent and engine_consistent and gains.size >= 2 and paired["z"] >= PROMOTE_Z
        out["products"][product.value] = {**paired, "log10_e_vs_fair": uniform, "eligible": bool(eligible)}
    return out


def _rounded(value: object) -> object:
    if isinstance(value, float):
        return round(value, 10) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def summarize(series: dict[ProductCode, Series], ledger_path: Path) -> dict:
    steps, model = walk_forward(series)
    return _rounded({
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "products": [p.value for p in PRODUCTS],
        "rule": {"prior_pooled": PRIOR_POOLED, "share": {p.value: share(p) for p in PRODUCTS},
                 "registered_on": REGISTERED_ON.isoformat(), "promote_z": PROMOTE_Z,
                 "pooled_law": "Component của engine, tham số theo kỳ của Max 3D, nạp dòng kỳ gộp"},
        "walk_forward": {p.value: product_summary(p, steps, model) for p in PRODUCTS},
        "prospective": prospective(steps, ledger_path, final_through(series), engine_fingerprint()),
        "deployment": "shadow",
    })


def write(series: dict[ProductCode, Series], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    summary = summarize(series, directory / LEDGER)
    path = directory / SUMMARY
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if old is None or not _same_up_to_float_noise(summary, old):
        write_text_atomic(path, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return path


def latest_series() -> dict[ProductCode, Series]:
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.api.main import _seed
    from vietlott_engine.core.config import get_settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vietlott_engine.forecast.data import load_series
    from vlm.updates.service import replay_results
    import asyncio

    settings = get_settings()
    seed_settings = settings.model_copy(update={"seed_file_dir": settings.seed_file_dir or settings.product_seed_dir})
    state = AppState(seed_settings, InMemoryRepository())
    asyncio.run(_seed(state))
    replay_results(state)
    store = state.product_store()
    return {p: load_series(p, None, store, settings.product_seed_dir) for p in PRODUCTS}


def main(argv: list[str] | None = None) -> int:
    from vietlott_engine.paths import enter_project

    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path("data/forecast"), help="thư mục ghi tóm tắt và sổ tiến cứu")
    args = parser.parse_args(argv)
    enter_project()
    path = write(latest_series(), args.dir)
    summary = json.loads(path.read_text(encoding="utf-8"))
    report = {p: {"draws": v["draws"], "last_date": v["last_date"],
                  "mixed_vs_separate_log10": v["mixed_vs_separate"]["log10"], "w_pooled": v["w_pooled"]}
              for p, v in summary["walk_forward"].items()}
    print(json.dumps({"summary": str(path), "products": report,
                      "prospective": summary["prospective"]["products"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
