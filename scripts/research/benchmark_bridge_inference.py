"""Đo ngoài mẫu phép suy luận cầu vị trí bằng Bayes thực nghiệm (16-10-2026).

Bản cũ (``path_prob`` trước 16-10-2026): xác suất của một con là trung bình tỉ
lệ trúng LỊCH SỬ của các cầu báo nó — các cầu được chọn top 300 trên khoảng
5 671 cầu mỗi độ trễ — rồi co về nền với độ mạnh đặt tay
``6·√(1 + 2·ln(5671/300))``. Tỉ lệ lịch sử của cầu được chọn mang lời nguyền
người thắng: tổng LOTO của nhánh ổn định là 24,40 con mỗi kỳ, trong khi kỳ
vọng thật là 23,77.

Bản mới: mỗi cầu nhận xác suất trúng kỳ tới theo kinh nghiệm học từ MỌI cầu
trong cửa sổ (``path_prob.BridgeEvidence``): tỉ lệ chung + phần riêng của cầu
co theo mức chênh THẬT giữa các cầu (Bayes thực nghiệm, phương pháp mô men);
nhánh "đang chạy" cộng phần kinh nghiệm theo độ dài chuỗi, học trên mọi cầu.

Walk-forward trên ``--last`` kỳ cuối, cầu dựng lại mỗi kỳ bằng đúng tham số của
pipeline — cửa sổ lấy từ mặc định của ``pipeline.py`` (``--window-days`` 2000, cũng là
giá trị ``update-data.yml`` truyền vào), không viết cứng 365 như phép đo 04-10-2026. Mốc hằng số: tỉ lệ nền tích luỹ (LOTO), 1/100 (Đặc Biệt) — cùng mốc
với ``benchmark_component_trust``.

Luật quyết định chốt TRƯỚC khi đo:

1. Nhánh cầu (vector in trên trang soi cầu): bản mới không kém bản cũ ở bất kỳ
   ô nào trong bốn ô (LOTO/Đặc Biệt × đang chạy/ổn định) với z ≤ −2, và thắng
   với z ≥ 2 ở ít nhất một ô.
2. Tổ hợp (trọng số mặc định, ML/thống kê/cầu-kèo bằng tỉ lệ nền như đo
   04-10-2026, chốt bằng ``finalize_blend``): bản mới không kém bản cũ với
   z ≤ −2 ở cả hai chế độ.
3. Tổ hợp mới không kém dự báo hằng số với z ≤ −2.

    PYTHONPATH=src python3 scripts/research/benchmark_bridge_inference.py --last 2000

Với cửa sổ 2 000 kỳ, một lượt mất khoảng 2,6 giờ trên 4 lõi; chạy theo phần rồi gộp::

    for k in 1 2 3 4; do PYTHONPATH=src python3 scripts/research/benchmark_bridge_inference.py \\
        --last 2000 --parts 4 --part $k; done
    PYTHONPATH=src python3 scripts/research/benchmark_bridge_inference.py --last 2000 --parts 4 --merge
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.calendar_alignment import consecutive_next_pairs, normalize_dates  # noqa: E402
from ensemble.ensemble_utils import DEFAULT_ENSEMBLE_WEIGHTS, finalize_blend  # noqa: E402
from ingest.lottery import Lottery  # noqa: E402
from core.path_models import PathParams, build_daily_targets, enumerate_position_pairs  # noqa: E402
from soi_cau.path_prob import (  # noqa: E402
    fit_paths_with_evidence,
    paths_to_dataframe,
    predict_from_fitted_paths_full,
    prepare_path_history,
)
from vla.backtest import evaluator  # noqa: E402
from core.xsmb_domain import TOTAL_DIGITS, baseline_rate  # noqa: E402

OUT = ROOT / "data" / "research" / "model_overhaul" / "bridge_inference.json"
MODES = ("loto", "de")
KINDS = ("active", "stable")
#: Cửa sổ production: ``pipeline.py`` mặc định ``--window-days 2000`` và truyền nó cho
#: ``run_path_ui``; ``update-data.yml`` cũng truyền 2000. ``path_manifest_<mode>.json`` ghi lại.
PRODUCTION_WINDOW_DAYS = 2000
PATH_PARAMS = PathParams(lag_max=30, window_days=PRODUCTION_WINDOW_DAYS, min_trials=60,
                         min_max_streak=3, min_current_streak=3, top_rules_per_lag=300)

_PREPARED = None


def legacy_prior_strength(n_screened: int, n_kept: int, base: float = 6.0) -> float:
    """Độ co đặt tay của bản cũ (``selection_shrinkage_strength`` trước 16-10-2026)."""
    screened = max(int(n_screened), 1)
    kept = max(int(n_kept), 1)
    if kept >= screened:
        return float(base)
    return float(base) * float(np.sqrt(1.0 + 2.0 * np.log(screened / kept)))


def legacy_branch(stats_df: pd.DataFrame, raw_by_date: dict, anchor, *, kind: str, mode: str) -> np.ndarray:
    """Tái lập đúng ``predict_from_fitted_paths_full`` trước 16-10-2026 (phạm vi "all")."""
    base = baseline_rate(mode)
    params = PATH_PARAMS
    paths = stats_df[stats_df["trials"] >= params.min_trials]
    if kind == "active":
        paths = paths[paths["current_streak"] >= params.min_current_streak]
    else:
        paths = paths[paths["max_streak"] >= params.min_max_streak]
    if paths.empty:
        return np.full(100, base)
    next_date = anchor + timedelta(days=1)
    lags = paths["lag"].to_numpy(dtype=int)
    i_arr = paths["i"].to_numpy(dtype=int)
    j_arr = paths["j"].to_numpy(dtype=int)
    nums = np.full(len(paths), -1, dtype=int)
    for lag in np.unique(lags):
        digits = raw_by_date.get(next_date - timedelta(days=int(lag)))
        if digits is None:
            continue
        rows = lags == lag
        digits = np.asarray(digits)
        nums[rows] = 10 * digits[i_arr[rows]].astype(int) + digits[j_arr[rows]].astype(int)
    ok = (nums >= 0) & (nums < 100)
    if not ok.any():
        return np.full(100, base)
    p = np.clip(paths["p_mean"].to_numpy(dtype=float)[ok], 1e-6, 1 - 1e-6)
    trials = paths["trials"].to_numpy(dtype=float)[ok]
    reliability = trials / (trials + 120.0)
    if kind == "active":
        streak_weight = 1.0 + 0.05 * np.minimum(paths["current_streak"].to_numpy(dtype=float)[ok], 8.0)
    else:
        streak_weight = 1.0 + 0.02 * np.minimum(paths["max_streak"].to_numpy(dtype=float)[ok], 15.0)
    w = reliability * streak_weight
    n = nums[ok]
    support = np.bincount(n, minlength=100)
    weight_sum = np.bincount(n, weights=w, minlength=100)
    weighted_p = np.bincount(n, weights=w * p, minlength=100)
    ps = legacy_prior_strength(len(enumerate_position_pairs(TOTAL_DIGITS)[0]), params.top_rules_per_lag)
    prob = (weighted_p + ps * base) / (weight_sum + ps)
    prob = np.where(support > 0, prob, base)
    if mode == "de":
        prob = prob / prob.sum()
    return prob


def _init_worker(prepared) -> None:
    global _PREPARED
    _PREPARED = prepared


def _day(anchor) -> dict:
    out = {}
    for mode in MODES:
        stats, raw_by_date, dates, evidence = fit_paths_with_evidence(
            params=PATH_PARAMS, mode=mode, anchor_date=anchor, prepared=_PREPARED
        )
        frame = paths_to_dataframe(stats)
        for kind in KINDS:
            new = predict_from_fitted_paths_full(stats=stats, raw_by_date=raw_by_date, dates=dates,
                                                 params=PATH_PARAMS, kind=kind, mode=mode,
                                                 anchor_date=anchor)
            out[(mode, kind, "new")] = new.sort_values("number")["prob"].to_numpy(dtype=float)
            out[(mode, kind, "old")] = legacy_branch(frame, raw_by_date, anchor, kind=kind, mode=mode)
        out[(mode, "evidence")] = {
            "variance_ratio": evidence.variance_ratio,
            "rules_fully_pooled": evidence.rules_fully_pooled,
            "rule_shrinkage": evidence.rule_shrinkage,
            "streak_posterior": list(evidence.streak_posterior),
            "base_rate": evidence.base_rate,
        }
    return out


def _paired(new: np.ndarray, old: np.ndarray) -> dict:
    half = len(new) // 2
    return {**evaluator.paired(new, old),
            "halves_z": [evaluator.paired(new[:half], old[:half])["z"],
                         evaluator.paired(new[half:], old[half:])["z"]]}


def decide(report: dict) -> dict:
    """Áp luật quyết định đã chốt ở docstring lên báo cáo."""
    branch = [report[m]["branch_new_vs_old"][k]["z"] for m in MODES for k in KINDS]
    ensemble = [report[m]["ensemble_new_vs_old"]["z"] for m in MODES]
    constant = [report[m]["vs_constant"]["ensemble_new"]["z"] for m in MODES]
    rule1 = min(branch) > -2.0 and max(branch) >= 2.0
    rule2 = min(ensemble) > -2.0
    rule3 = min(constant) > -2.0
    return {"rule1_branch": rule1, "rule2_ensemble": rule2, "rule3_constant": rule3,
            "adopt": bool(rule1 and rule2 and rule3)}


def _history():
    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    dates = normalize_dates(raw["date"])
    _, loto_targets, de_targets = build_daily_targets(two)
    hit_loto = np.zeros((len(two), 100))
    for t, numbers in enumerate(loto_targets):
        hit_loto[t, list(numbers)] = 1.0
    hit_de = np.eye(100)[np.asarray(de_targets, dtype=int)]
    return raw, two, dates, {"loto": hit_loto, "de": hit_de}


#: Đổi khuôn danh tính thì tăng số này: phần ghi theo khuôn cũ không gộp được với phần mới.
IDENTITY_VERSION = 2
SCRIPT = Path(__file__).resolve()


def _code_digest(root: Path, script: Path) -> str:
    """Băm MỌI mã có thể chạy trong phép đo: toàn bộ ``src/**/*.py`` và chính kịch bản này.

    Không liệt kê tay vài module: phép đo còn chạy ``ensemble_utils``,
    ``vla.backtest.evaluator``, ``xsmb_domain``… và một danh sách tay sẽ sót
    module mới. Băm rộng hơn cần thiết chỉ làm bước gộp từ chối thừa, không
    bao giờ để lọt hai phần tính bằng hai logic khác nhau.
    """
    digest = hashlib.sha256()
    for path in [*sorted((root / "src").rglob("*.py")), script]:
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def run_identity(raw: pd.DataFrame, *, last: int, parts: int) -> dict:
    """Danh tính một lượt đo: tham số, ảnh chụp dữ liệu, mã nguồn và thư viện số.

    Mọi phần của cùng một lượt phải mang đúng danh tính này; bước gộp từ chối
    phần cũ (dữ liệu hay mã đã đổi) hoặc phần chạy với ``--last``/``--parts`` khác.
    """
    data = hashlib.sha256(raw.to_csv(index=False).encode("utf-8")).hexdigest()
    return {"identity_version": IDENTITY_VERSION,
            "last": int(last), "parts": int(parts), "window_days": PRODUCTION_WINDOW_DAYS,
            "draws": int(len(raw)), "last_date": str(pd.Timestamp(raw["date"].iloc[-1]).date()),
            "data_sha256": data, "code_sha256": _code_digest(ROOT, SCRIPT),
            "libraries": {"numpy": np.__version__, "pandas": pd.__version__}}


def expected_targets(dates, last: int) -> list[int]:
    """Chỉ số kỳ đích của ``last`` cặp (kỳ neo, kỳ kế) cuối — thứ tự mà các phần phải ghép lại thành."""
    return [int(t) for t in consecutive_next_pairs(dates)[1][-last:]]


def run_part(last: int, workers: int, part: int, parts: int) -> dict:
    """Chấm một phần (liên tiếp) của ``last`` kỳ cuối; trả về logloss TỪNG KỲ để gộp sau.

    Với cửa sổ 2 000 kỳ, mỗi kỳ neo mất ~19 giây cho cả hai chế độ, nên 2 000 kỳ
    vượt giới hạn thời gian của một lượt chạy; chia phần không đổi phép đo — bước
    gộp nối đúng các kỳ theo thứ tự rồi mới tính z.
    """
    raw, two, dates, hit = _history()
    source, target = consecutive_next_pairs(dates)
    source, target = source[-last:], target[-last:]
    bounds = np.linspace(0, len(source), parts + 1).astype(int)
    lo, hi = bounds[part - 1], bounds[part]
    source, target = source[lo:hi], target[lo:hi]
    prepared = prepare_path_history(raw, two)
    anchors = [dates[i].date() for i in source]
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(prepared,)) as pool:
        days = list(pool.map(_day, anchors, chunksize=8))
    print(f"[cầu vị trí] phần {part}/{parts}: {len(days)} kỳ", flush=True)

    weights = DEFAULT_ENSEMBLE_WEIGHTS
    out: dict = {"run": run_identity(raw, last=last, parts=parts),
                 "part": int(part),
                 "target": [int(t) for t in target],
                 "first_target": str(dates[target[0]].date()),
                 "last_target": str(dates[target[-1]].date())}
    for mode in MODES:
        hits = hit[mode][target]
        ref = evaluator.daily_logloss(mode, evaluator.cumulative_reference(mode, hit[mode], target), hits)
        base = baseline_rate(mode)
        vec = {(k, v): np.vstack([d[(mode, k, v)] for d in days]) for k in KINDS for v in ("old", "new")}
        flat = (weights.w_ml + weights.w_stat + weights.w_cau) * base
        ens = {v: np.vstack([finalize_blend(r, mode) for r in
                             flat + weights.w_active * vec[("active", v)] + weights.w_stable * vec[("stable", v)]])
               for v in ("old", "new")}
        ll = {f"{k}_{v}": evaluator.daily_logloss(mode, p, hits) for (k, v), p in vec.items()}
        ll.update({f"ensemble_{v}": evaluator.daily_logloss(mode, p, hits) for v, p in ens.items()})
        sums = {f"{k}_{v}": p.sum(axis=1) for (k, v), p in vec.items()}
        sums.update({f"ensemble_{v}": p.sum(axis=1) for v, p in ens.items()})
        out[mode] = {
            "constant": [float(x) for x in ref],
            "logloss": {k: [float(x) for x in v] for k, v in ll.items()},
            "sums": {k: [float(x) for x in v] for k, v in sums.items()},
            "evidence": [d[(mode, "evidence")] for d in days],
        }
    return out


def merge(parts: list[dict], *, run: dict, expected_target: list[int]) -> dict:
    """Nối các phần theo thứ tự kỳ đích rồi tính z và luật quyết định như một lượt liền.

    Chỉ gộp khi mọi phần mang đúng danh tính ``run`` của lượt hiện tại (tham số,
    dữ liệu, mã), đủ các phần 1..``parts``, và các kỳ đích nối lại TRÙNG từng
    phần tử với ``expected_target``: các kỳ có thứ tự và không trùng chưa đủ —
    một phần cũ hay chạy với ``--last`` khác vẫn qua được phép ấy.
    """
    for p in parts:
        if p.get("run") != run:
            raise ValueError(f"phần {p.get('part')} thuộc lượt đo khác: {p.get('run')} ≠ {run}")
    if sorted(p["part"] for p in parts) != list(range(1, run["parts"] + 1)):
        raise ValueError(f"cần đúng các phần 1..{run['parts']}, có {sorted(p['part'] for p in parts)}")
    parts = sorted(parts, key=lambda p: p["part"])
    targets = [t for p in parts for t in p["target"]]
    if targets != list(expected_target):
        raise ValueError("các kỳ đích ghép lại không trùng dãy kỳ đích của lượt đo")
    report: dict = {}
    for mode in MODES:
        ref = np.concatenate([p[mode]["constant"] for p in parts])
        names = list(parts[0][mode]["logloss"])
        ll = {k: np.concatenate([p[mode]["logloss"][k] for p in parts]) for k in names}
        sums = {k: np.concatenate([p[mode]["sums"][k] for p in parts]) for k in parts[0][mode]["sums"]}
        ev = [e for p in parts for e in p[mode]["evidence"]]
        base = baseline_rate(mode)
        report[mode] = {
            "days": int(len(ref)),
            "first_target": parts[0]["first_target"],
            "last_target": parts[-1]["last_target"],
            "constant_logloss": float(ref.mean()),
            "logloss": {k: float(v.mean()) for k, v in ll.items()},
            "vs_constant": {k: _paired(v, ref) for k, v in ll.items()},
            "branch_new_vs_old": {k: _paired(ll[f"{k}_new"], ll[f"{k}_old"]) for k in KINDS},
            "ensemble_new_vs_old": _paired(ll["ensemble_new"], ll["ensemble_old"]),
            "median_sum": {k: float(np.median(v)) for k, v in sums.items()},
            "expected_sum": float(100 * base) if mode == "loto" else 1.0,
            "evidence": {
                "variance_ratio_median": float(np.median([e["variance_ratio"] for e in ev])),
                "variance_ratio_range": [float(min(e["variance_ratio"] for e in ev)),
                                         float(max(e["variance_ratio"] for e in ev))],
                "share_fully_pooled": float(np.mean([e["rules_fully_pooled"] for e in ev])),
                "min_rule_shrinkage": float(min(e["rule_shrinkage"] for e in ev)),
                "streak_posterior_minus_base_max_abs": float(max(
                    max(abs(s - e["base_rate"]) for s in e["streak_posterior"]) for e in ev)),
            },
        }
        r = report[mode]
        print(f"[{mode}] nhánh mới so với cũ: "
              + ", ".join(f"{k} z = {r['branch_new_vs_old'][k]['z']:+.2f}" for k in KINDS)
              + f"; tổ hợp mới so với cũ z = {r['ensemble_new_vs_old']['z']:+.2f}"
              + f"; tổ hợp mới so với hằng số z = {r['vs_constant']['ensemble_new']['z']:+.2f}",
              flush=True)
    report["decision"] = decide(report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--last", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--parts", type=int, default=1, help="chia --last kỳ thành ngần ấy phần liên tiếp")
    ap.add_argument("--part", type=int, default=0,
                    help="chỉ chấm phần này (1..parts) và ghi vào --parts-dir; 0 = chấm mọi phần rồi gộp")
    # Tệp từng phần là sản phẩm trung gian: để ở data/tmp (đã .gitignore).
    ap.add_argument("--parts-dir", type=Path, default=ROOT / "data" / "tmp" / "bridge_inference_parts")
    ap.add_argument("--merge", action="store_true", help="chỉ gộp các phần đã có trong --parts-dir")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    if args.part:
        args.parts_dir.mkdir(parents=True, exist_ok=True)
        part = run_part(args.last, args.workers, args.part, args.parts)
        dest = args.parts_dir / f"part_{args.part}_of_{args.parts}.json"
        dest.write_text(json.dumps(part, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[OK] {dest}")
        return
    if args.merge:
        parts = [json.loads(f.read_text(encoding="utf-8"))
                 for f in sorted(args.parts_dir.glob(f"part_*_of_{args.parts}.json"))]
    else:
        parts = [run_part(args.last, args.workers, k, args.parts) for k in range(1, args.parts + 1)]
    raw, _, dates, _ = _history()
    run = run_identity(raw, last=args.last, parts=args.parts)
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "last": args.last,
              "window_days": PRODUCTION_WINDOW_DAYS,
              "run": run,
              "assumptions": ("Tổ hợp mô phỏng: ML, thống kê và cầu-kèo bằng tỉ lệ nền; cầu vị trí "
                              "từ walk-forward; trọng số mặc định; không hiệu chỉnh, không xếp chồng."),
              **merge(parts, run=run, expected_target=expected_targets(dates, args.last))}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {args.out}  quyết định: {report['decision']}")


if __name__ == "__main__":
    main()
