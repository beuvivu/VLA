"""Đo ngoài mẫu hai sửa chữa của tổ hợp production: độ tin cầu-kèo và neo mức LOTO.

1. **Cầu-kèo** (``cau_keo_ml``, trọng số tổ hợp 0,30) phát xác suất THÔ của cây
   tăng cường + Platt, không co về nền khi không có kỹ năng — khác thành phần
   ML, vốn đã có ``ml_train.model_trust``. Ứng viên: cùng luật ấy,
   ``p = trust·thô + (1 − trust)·nền`` với trust = clip(20·s, 0, 1).
2. **Neo mức LOTO**: hai nhánh cầu vị trí (``path_prob``) chọn top quy tắc nên
   mang lời nguyền người thắng ở MỨC. Ứng viên: chốt tổ hợp LOTO bằng
   ``Σp = 100·nền`` (``ensemble_utils.anchor_loto_level``).

Walk-forward trên ``--last`` kỳ cuối. Cầu-kèo học lại mỗi ``--refit-every`` kỳ
bằng đúng ``cau_keo_ml._train_model`` (cùng khối thời gian, cùng siêu tham số);
cầu vị trí dựng lại mỗi kỳ như production. Kỳ ngay sau quãng nghỉ (Tết) bị loại.

Tổ hợp được MÔ PHỎNG với trọng số mặc định: ML và thống kê lấy đúng tỉ lệ nền —
walk-forward 03-10-2026 đo trust của ML bằng 0 ở gần như mọi lần học, và tín
hiệu thống kê co hoàn toàn về nền từ 14-09-2026 — còn cầu-kèo và cầu vị trí
lấy từ walk-forward ở trên.

Luật quyết định chốt TRƯỚC khi đo (cùng luật với ``benchmark_model_trust``):
chỉ đổi khi bản mới không kém bản hiện hành ở cả hai chế độ và thắng với z ≥ 2
ở ít nhất một chế độ; đồng thời không kém dự báo hằng số có ý nghĩa thống kê.

    PYTHONPATH=src python3 scripts/benchmark_component_trust.py --last 1000
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cau_keo_ml as ck  # noqa: E402
from calendar_alignment import consecutive_next_pairs, normalize_dates  # noqa: E402
from ensemble_utils import (  # noqa: E402
    DEFAULT_ENSEMBLE_WEIGHTS,
    clip01,
    finalize_blend,
    floor_distribution,
)
from lottery import Lottery  # noqa: E402
from path_models import PathParams, build_daily_targets  # noqa: E402
from path_prob import fit_paths, predict_from_fitted_paths_full, prepare_path_history  # noqa: E402
from vla.backtest import evaluator  # noqa: E402
from xsmb_domain import baseline_rate  # noqa: E402

OUT = ROOT / "data" / "research" / "model_overhaul" / "component_trust.json"
MODES = ("loto", "de")
#: Đúng tham số ``run_path_ui`` dùng trong pipeline.
PATH_PARAMS = PathParams(lag_max=30, window_days=365, min_trials=60, min_max_streak=3,
                         min_current_streak=3, top_rules_per_lag=300)
TRAIN_WINDOW = 2000

_PREPARED = None


def _cau_walk_forward(mode: str, last: int, refit_every: int) -> tuple[dict[str, dict], list[dict]]:
    """Xác suất THÔ của cầu-kèo cho ``last`` neo cuối, kèm trust/nền của lần học phủ neo ấy."""
    config = ck.CauKeoConfig(window_days=last + TRAIN_WINDOW + 10)
    X, y = ck.build_cau_keo_feature_frame(mode, include_target=True, config=config)
    X["anchor_date"] = pd.to_datetime(X["anchor_date"])
    anchors = pd.DatetimeIndex(sorted(X["anchor_date"].unique()))
    y_np = y.to_numpy(dtype=int)
    anchor_of_row = X["anchor_date"].to_numpy()
    out: dict[str, dict] = {}
    refits: list[dict] = []
    scored = anchors[-last:]
    for start in range(0, last, refit_every):
        block = scored[start:start + refit_every]
        # Nhãn của neo s−1 là kỳ s, đã biết tại neo s: học trên mọi neo < neo đầu khối.
        window = anchors[anchors < block[0]][-TRAIN_WINDOW:]
        mask = (anchor_of_row >= window[0].to_datetime64()) & (anchor_of_row < block[0].to_datetime64())
        with tempfile.TemporaryDirectory() as scratch:
            pack, _, _ = ck._train_model(mode, X.loc[mask].reset_index(drop=True),
                                         pd.Series(y_np[mask]), Path(scratch))
        rows = np.isin(anchor_of_row, block.to_numpy())
        frame = X.loc[rows]
        raw = pack["model"].predict_proba(frame[ck.FEATURE_COLS].astype(np.float32).to_numpy())[:, 1]
        for i, anchor in enumerate(block):
            sl = slice(100 * i, 100 * i + 100)
            numbers = frame["number"].to_numpy(dtype=int)[sl]
            p = np.empty(100)
            p[numbers] = raw[sl]
            out[str(anchor.date())] = {"raw": p, "trust": float(pack["model_trust"]),
                                       "base": float(pack["base_rate"]),
                                       "skill": min(pack["logloss_skill"], pack["brier_skill"])}
        refits.append({"first_anchor": str(block[0].date()), "model_trust": float(pack["model_trust"]),
                       "logloss_skill": float(pack["logloss_skill"]), "brier_skill": float(pack["brier_skill"])})
        print(f"[cầu-kèo {mode}] {block[0].date()} trust={pack['model_trust']:.3f}", flush=True)
    return out, refits


def _init_worker(prepared) -> None:
    global _PREPARED
    _PREPARED = prepared


def _path_day(anchor) -> dict[tuple[str, str], np.ndarray]:
    out = {}
    for mode in MODES:
        stats, raw_by_date, dates = fit_paths(params=PATH_PARAMS, mode=mode, anchor_date=anchor,
                                              prepared=_PREPARED)
        for kind in ("active", "stable"):
            frame = predict_from_fitted_paths_full(stats=stats, raw_by_date=raw_by_date, dates=dates,
                                                   params=PATH_PARAMS, kind=kind, mode=mode,
                                                   anchor_date=anchor)
            out[(mode, kind)] = frame.sort_values("number")["prob"].to_numpy(dtype=float)
    return out


def _paired(new: np.ndarray, old: np.ndarray) -> dict:
    half = len(new) // 2
    return {**evaluator.paired(new, old),
            "halves_z": [evaluator.paired(new[:half], old[:half])["z"],
                         evaluator.paired(new[half:], old[half:])["z"]]}


def run(last: int, refit_every: int, workers: int) -> dict:
    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    dates = normalize_dates(raw["date"])
    source, target = consecutive_next_pairs(dates)
    source, target = source[-last:], target[-last:]
    _, loto_targets, de_targets = build_daily_targets(two)
    hit_loto = np.zeros((len(two), 100))
    for t, numbers in enumerate(loto_targets):
        hit_loto[t, list(numbers)] = 1.0
    hit_de = np.eye(100)[np.asarray(de_targets, dtype=int)]

    prepared = prepare_path_history(raw, two)
    anchors = [dates[i].date() for i in source]
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(prepared,)) as pool:
        path = list(pool.map(_path_day, anchors, chunksize=8))
    print(f"[cầu vị trí] {len(path)} kỳ", flush=True)

    weights = DEFAULT_ENSEMBLE_WEIGHTS
    report: dict = {}
    for mode in MODES:
        cau, refits = _cau_walk_forward(mode, last + 5, refit_every)
        keep = [k for k, a in enumerate(anchors) if str(a) in cau]
        tgt = target[keep]
        hits = (hit_loto if mode == "loto" else hit_de)[tgt]
        ref = evaluator.daily_logloss(mode, evaluator.cumulative_reference(
            mode, hit_loto if mode == "loto" else hit_de, tgt), hits)
        base = baseline_rate(mode)
        c = [cau[str(anchors[k])] for k in keep]
        cau_raw = np.vstack([r["raw"] for r in c])
        cau_new = np.vstack([ck.trusted_probability(r["raw"], mode=mode, trust=r["trust"],
                                                    base_rate=r["base"]) for r in c])
        active = np.vstack([path[k][(mode, "active")] for k in keep])
        stable = np.vstack([path[k][(mode, "stable")] for k in keep])
        if mode == "de":
            cau_raw = cau_raw / cau_raw.sum(axis=1, keepdims=True)
            active = active / active.sum(axis=1, keepdims=True)
            stable = stable / stable.sum(axis=1, keepdims=True)
        flat = (weights.w_ml + weights.w_stat) * base
        mix_old = flat + weights.w_cau * cau_raw + weights.w_active * active + weights.w_stable * stable
        mix_new = flat + weights.w_cau * cau_new + weights.w_active * active + weights.w_stable * stable
        old = (np.vstack([floor_distribution(r) for r in mix_old]) if mode == "de"
               else clip01(mix_old, eps=1e-6))
        new = np.vstack([finalize_blend(r, mode) for r in mix_new])

        ll = {name: evaluator.daily_logloss(mode, p, hits) for name, p in {
            "cau_raw": cau_raw, "cau_trusted": cau_new, "path_active": active, "path_stable": stable,
            "path_active_anchored": np.vstack([finalize_blend(r, mode) for r in active]),
            "path_stable_anchored": np.vstack([finalize_blend(r, mode) for r in stable]),
            "ensemble_current": old, "ensemble_new": new,
            "ensemble_current_plus_anchor": np.vstack([finalize_blend(r, mode) for r in mix_old]),
            "ensemble_cau_trusted_only": (np.vstack([floor_distribution(r) for r in mix_new])
                                          if mode == "de" else clip01(mix_new, eps=1e-6)),
        }.items()}
        report[mode] = {
            "days": len(keep),
            "first_target": str(dates[tgt[0]].date()),
            "last_target": str(dates[tgt[-1]].date()),
            "constant_logloss": float(ref.mean()),
            "logloss": {k: float(v.mean()) for k, v in ll.items()},
            "vs_constant": {k: _paired(v, ref) for k, v in ll.items()},
            "cau_trusted_vs_raw": _paired(ll["cau_trusted"], ll["cau_raw"]),
            "ensemble_new_vs_current": _paired(ll["ensemble_new"], ll["ensemble_current"]),
            # Tách hai sửa chữa: neo mức một mình, rồi độ tin cầu-kèo khi đã neo.
            "anchor_only_vs_current": _paired(ll["ensemble_current_plus_anchor"], ll["ensemble_current"]),
            "cau_trust_given_anchor": _paired(ll["ensemble_new"], ll["ensemble_current_plus_anchor"]),
            "cau_mean_trust": float(np.mean([r["trust"] for r in c])),
            "cau_refits": refits,
            "cau_refits_with_skill": int(sum(min(r["logloss_skill"], r["brier_skill"]) > 0 for r in refits)),
            "median_sum": {"path_active": float(np.median(active.sum(axis=1))),
                           "path_stable": float(np.median(stable.sum(axis=1))),
                           "cau_raw": float(np.median(cau_raw.sum(axis=1))),
                           "ensemble_current": float(np.median(old.sum(axis=1))),
                           "ensemble_new": float(np.median(new.sum(axis=1))),
                           "expected": float(100 * base) if mode == "loto" else 1.0},
        }
        d = report[mode]["ensemble_new_vs_current"]
        print(f"[{mode}] tổ hợp mới so với hiện hành: z = {d['z']:+.2f}; "
              f"so với hằng số: z = {report[mode]['vs_constant']['ensemble_new']['z']:+.2f}", flush=True)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--last", type=int, default=1000)
    ap.add_argument("--refit-every", type=int, default=50)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "last": args.last, "refit_every": args.refit_every,
              "assumptions": ("Tổ hợp mô phỏng: ML và thống kê bằng tỉ lệ nền; cầu-kèo và cầu vị trí "
                              "từ walk-forward; trọng số mặc định; không hiệu chỉnh, không xếp chồng."),
              **run(args.last, args.refit_every, args.workers)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {OUT}")


if __name__ == "__main__":
    main()
