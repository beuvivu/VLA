"""So sánh mô hình cũ và mới trên N kỳ quay gần nhất bằng walk-forward không rò rỉ.

Chạy:  PYTHONPATH=src python3 scripts/benchmark_probability_models.py --last 1000

Các mô hình (mỗi khối ``--refit-every`` kỳ được huấn luyện lại trên dữ liệu
TRƯỚC khối):

* ``hang_so``        — tỉ lệ nền (LOTO) / 1/100 (Đặc Biệt). Mốc kỹ năng 0.
* ``ml_production``  — thành phần ML đang chạy production, tái dựng nguyên quy
  trình huấn luyện (xem ``vla.backtest.production_ml``).
* ``tien_nghiem``    — tầng 1 (Dirichlet/Beta) + hiệu chỉnh Platt.
* ``bayes_lgb``      — tầng 1 + LightGBM phần dư + Platt (mô hình mới).
* ``bayes_lgb_focal_iso`` — như trên nhưng focal loss + isotonic.

Thêm: tổ hợp production ĐÃ GHI SỔ (``data/prob_eval/ensemble_history.csv``)
được so với các mô hình trên đúng những kỳ có trong sổ.

Kiểm độ nhạy (``--power-check``): chạy mô hình mới trên lịch sử tổng hợp có
cài sẵn tín hiệu, để chứng minh công cụ đo KHÔNG mù — nếu thắng ở đó mà hoà
trên dữ liệu thật thì kết luận "không có tín hiệu" là của dữ liệu.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vla.backtest import evaluator, walk_forward  # noqa: E402
from vla.backtest.production_ml import ProductionMLModel  # noqa: E402
from vla.backtest.synthetic import power_history  # noqa: E402
from vla.features.engineer import History, build_features, load_history  # noqa: E402
from vla.models.bayesian_lgb import BayesianLGBModel, ConstantModel, ModelConfig, PriorOnlyModel  # noqa: E402

OUT = ROOT / "data" / "research" / "model_overhaul"


def factories(mode: str, history: History, include_production: bool) -> dict:
    out = {
        "hang_so": lambda: ConstantModel(mode),
        "tien_nghiem": lambda: PriorOnlyModel(mode),
        "bayes_lgb": lambda: BayesianLGBModel(mode),
        "bayes_lgb_focal_iso": lambda: BayesianLGBModel(
            mode, replace(ModelConfig(), loss="focal", calibration="isotonic")
        ),
    }
    if include_production:
        pack = ProductionMLModel(mode, history)
        out["ml_production"] = lambda: pack
    return out


def run_mode(
    mode: str,
    history: History,
    last: int,
    refit_every: int,
    include_production: bool,
    production_refit_every: int | None = None,
) -> tuple[dict, pd.DataFrame]:
    started = time.perf_counter()
    feats = build_features(history, mode)
    hit = history.hits(mode)
    T = len(history)
    first, final = T - last, T - 1
    targets = np.arange(first, final + 1)
    counts = history.counts[targets]
    special = history.special[targets]
    # Kỳ ngay sau một quãng nghỉ (Tết): bảng production bỏ hàng ấy, nên mọi mô
    # hình đều được chấm trên CÙNG tập kỳ còn lại.
    dates = pd.to_datetime(list(history.dates))
    consecutive = np.asarray((dates[targets] - dates[targets - 1]).days == 1)
    reference = evaluator.cumulative_reference(mode, hit, targets)

    results, daily = {}, []
    for name, factory in factories(mode, history, include_production).items():
        t0 = time.perf_counter()
        # Production học lại MỖI kỳ (``ml_predict`` coi mô hình cũ là hết hạn);
        # ``--production-refit-every 1`` tái dựng đúng điều đó, giá ~7 giây/kỳ.
        every = (production_refit_every or refit_every) if name == "ml_production" else refit_every
        res = walk_forward.run(factory, feats.X, hit, first, final, refit_every=every)
        m = consecutive
        summary = evaluator.evaluate(mode, res.probs[m], counts[m], special[m], reference[m])
        summary["seconds"] = round(time.perf_counter() - t0, 1)
        summary["refit_every"] = every
        summary["refits"] = res.refits
        results[name] = summary
        hits = (counts > 0).astype(float) if mode == "loto" else np.eye(100)[special]
        ll = evaluator.daily_logloss(mode, res.probs, hits)
        br = evaluator.daily_brier(mode, res.probs, hits)
        for k in np.flatnonzero(m):
            daily.append({"mode": mode, "model": name, "target_date": history.dates[targets[k]],
                          "logloss": float(ll[k]), "brier": float(br[k])})
        print(f"[{mode}] {name}: logloss={summary['logloss']:.6f} skill={summary['logloss_skill']:+.5f} "
              f"z={summary['vs_reference']['z']:+.2f} ({summary['seconds']}s)", flush=True)
    frame = pd.DataFrame(daily)
    meta = {"targets": int(m.sum()), "excluded_after_break": int((~consecutive).sum()),
            "first_target": history.dates[first], "last_target": history.dates[final],
            "features": list(feats.names), "seconds": round(time.perf_counter() - started, 1)}
    return {"meta": meta, "models": results, "pairwise": pairwise(frame, mode)}, frame


def pairwise(frame: pd.DataFrame, mode: str) -> dict:
    """Mô hình mới so với ML production và với tiên nghiệm, từng kỳ."""
    wide = frame[frame["mode"] == mode].pivot(index="target_date", columns="model", values="logloss")
    out = {}
    for new in ("bayes_lgb", "bayes_lgb_focal_iso"):
        for old in ("ml_production", "tien_nghiem", "hang_so"):
            if new in wide and old in wide:
                out[f"{new}_vs_{old}"] = evaluator.paired(wide[new].to_numpy(), wide[old].to_numpy())
    return out


def against_recorded_production(frame: pd.DataFrame) -> dict:
    """So với tổ hợp production đã ghi sổ, trên đúng các kỳ trong sổ."""
    path = ROOT / "data" / "prob_eval" / "ensemble_history.csv"
    if not path.exists():
        return {}
    book = pd.read_csv(path, dtype={"target_date": str})
    out = {}
    for mode, group in frame.groupby("mode"):
        rec = book[book["mode"] == mode].set_index("target_date")["logloss"]
        wide = group.pivot(index="target_date", columns="model", values="logloss")
        common = wide.index.intersection(rec.index)
        exact = book[(book["mode"] == mode) & (book.get("evaluation_source") == "exact_emitted_prediction_artifact")]
        block = {"days": int(len(common)), "exact_artifact_days": int(exact["target_date"].isin(common).sum()),
                 "production_recorded_logloss": float(rec[common].mean()) if len(common) else None}
        for name in wide.columns:
            block[f"{name}_logloss"] = float(wide.loc[common, name].mean()) if len(common) else None
            if len(common) > 1:
                block[f"{name}_vs_production"] = evaluator.paired(wide.loc[common, name].to_numpy(), rec[common].to_numpy())
        out[mode] = block
    return out


def power_check(refit_every: int) -> dict:
    out = {}
    for mode in ("loto", "de"):
        # Mỗi chế độ một lịch sử, chỉ cài tín hiệu của chính nó.
        hist = power_history(mode, 2600, seed=11)
        feats = build_features(hist, mode)
        hit = hist.hits(mode)
        T = len(hist)
        targets = np.arange(T - 600, T)
        ref = evaluator.cumulative_reference(mode, hit, targets)
        res = walk_forward.run(lambda m=mode: BayesianLGBModel(m), feats.X, hit, T - 600, T - 1, refit_every=refit_every * 3)
        summary = evaluator.evaluate(mode, res.probs, hist.counts[targets], hist.special[targets], ref)
        out[mode] = {"logloss_skill": summary["logloss_skill"], "vs_reference": summary["vs_reference"],
                     "top_k": summary["top_k"]}
        print(f"[kiểm độ nhạy {mode}] skill={summary['logloss_skill']:+.4f} z={summary['vs_reference']['z']:+.1f}", flush=True)
    return out


def production_refit_check(history: History, last: int, refit_every: int) -> dict:
    """ML production học lại mỗi kỳ so với mỗi ``refit_every`` kỳ, trên ``last`` kỳ cuối.

    Đo xem đối chứng "học lại theo khối" lệch bao nhiêu so với production thật
    (học lại mỗi kỳ). Cùng tập kỳ, cùng mã; chỉ khác nhịp học lại.
    """
    out = {}
    T = len(history)
    for mode in ("loto", "de"):
        feats = build_features(history, mode)
        hit = history.hits(mode)
        pack = ProductionMLModel(mode, history)
        targets = np.arange(T - last, T)
        # Cùng luật với run_mode: kỳ ngay sau quãng nghỉ không có hàng production
        # (predict trả tỉ lệ nền thay vào), nên bị loại khỏi MỌI phép chấm.
        dates = pd.to_datetime(list(history.dates))
        keep = np.asarray((dates[targets] - dates[targets - 1]).days == 1)
        hits = (history.counts[targets] > 0).astype(float) if mode == "loto" else np.eye(100)[history.special[targets]]
        losses = {}
        for every in (1, refit_every):
            res = walk_forward.run(lambda p=pack: p, feats.X, hit, T - last, T - 1, refit_every=every)
            losses[every] = evaluator.daily_logloss(mode, res.probs, hits)[keep]
        const = evaluator.daily_logloss(mode, evaluator.cumulative_reference(mode, hit, targets), hits)[keep]
        out[mode] = {
            "days": int(keep.sum()),
            "logloss_refit_1": float(losses[1].mean()),
            f"logloss_refit_{refit_every}": float(losses[refit_every].mean()),
            "refit_1_vs_block": evaluator.paired(losses[1], losses[refit_every]),
            "refit_1_vs_constant": evaluator.paired(losses[1], const),
            "max_abs_daily_gap": float(np.abs(losses[1] - losses[refit_every]).max()),
        }
        print(f"[học lại mỗi kỳ {mode}] {out[mode]['logloss_refit_1']:.6f} vs khối "
              f"{out[mode][f'logloss_refit_{refit_every}']:.6f}", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--last", type=int, default=1000)
    ap.add_argument("--refit-every", type=int, default=50)
    ap.add_argument("--modes", default="loto,de")
    ap.add_argument("--skip-production", action="store_true")
    ap.add_argument("--power-check", action="store_true")
    ap.add_argument("--production-refit-every", type=int, default=None,
                    help="nhịp học lại riêng cho ml_production (1 = đúng production, chậm)")
    ap.add_argument("--refit-check", type=int, default=0,
                    help="so ml_production học lại mỗi kỳ với mỗi --refit-every kỳ trên N kỳ cuối")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    history = load_history(Path(args.data_dir))
    report = {"generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "history_draws": len(history), "last": args.last, "refit_every": args.refit_every,
              "payout": evaluator.Payout().__dict__, "modes": {}}
    frames = []
    for mode in args.modes.split(","):
        report["modes"][mode], frame = run_mode(
            mode, history, args.last, args.refit_every, not args.skip_production, args.production_refit_every
        )
        frames.append(frame)
    daily = pd.concat(frames, ignore_index=True)
    report["recorded_production"] = against_recorded_production(daily)
    if args.power_check:
        report["power_check"] = power_check(args.refit_every)
    if args.refit_check:
        report["production_refit_check"] = production_refit_check(history, args.refit_check, args.refit_every)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    daily.to_csv(out / "daily_logloss.csv", index=False, float_format="%.8f")
    print(f"[OK] {out / 'benchmark.json'}")


if __name__ == "__main__":
    main()
