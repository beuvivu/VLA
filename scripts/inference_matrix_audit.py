"""Phân tích 4 bước: làm sạch -> tần suất/cầu/tương quan -> Bayes/Markov -> Confidence.

Mọi thống kê được tính một lần trên dữ liệu thật và N lần trên lịch sử giả lập
CÔNG BẰNG cùng kích thước (27 giải x T kỳ, mỗi con 00-99 đều nhau). Giá trị
"tin cậy" của một tín hiệu = tỉ lệ lịch sử công bằng có thống kê LỚN NHẤT
(trên cả họ giả thuyết) còn nhỏ hơn tín hiệu ấy — tức 1 - p hiệu chỉnh đa kiểm.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Thống kê, phân phối null và kiểm ngoài mẫu dùng CHUNG với trang production
# (src/confidence_matrix.py). Bản chép riêng từng lệch khỏi bản production:
# review PR #104 bắt được script vẫn chấm Markov với null của thống kê khác.
from confidence_matrix import (  # noqa: E402
    NAMES,
    SPLIT,
    digits,
    forecast_scores,
    hits_matrix,
    out_of_sample,
    simulate_null,
    stats,
    summarize,
)


def load(data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(data_dir / "xsmb-2-digits.csv")


def report(null: np.ndarray, data_dir: Path, out_dir: Path) -> dict:
    """Chạy phần dữ liệu thật, so với phân phối null, ghi report.json + decision_matrix.csv."""
    sys.path.insert(0, str(ROOT / "src"))
    N = len(null)
    col = {n: i for i, n in enumerate(NAMES)}

    def fw_conf(name: str, value: float) -> float:
        """Tin cậy hiệu chỉnh đa kiểm: tỉ lệ lịch sử công bằng có max < value."""
        return float((null[:, col[name]] < value).mean())

    def p_upper(name: str, value: float) -> float:
        return float(((null[:, col[name]] >= value).sum() + 1) / (N + 1))

    out: dict = {"n_sims": N}

    # ---------------- Bước 1: làm sạch ----------------
    df = load(data_dir)
    raw = pd.read_csv(data_dir / "xsmb.csv")
    dates = pd.to_datetime(df["date"])
    full = pd.date_range(dates.min(), dates.max())
    missing = full.difference(dates)
    gaps = []
    if len(missing):
        run = [missing[0]]
        for d in missing[1:]:
            if (d - run[-1]).days == 1:
                run.append(d)
            else:
                gaps.append(run)
                run = [d]
        gaps.append(run)
    vals = df.drop(columns="date")
    out["clean"] = {
        "rows": len(df),
        "first": str(dates.min().date()),
        "last": str(dates.max().date()),
        "calendar_days": len(full),
        "missing_days": len(missing),
        "gap_runs": len(gaps),
        "longest_gap": max((len(g) for g in gaps), default=0),
        "dup_dates": int(dates.duplicated().sum()),
        "sorted": bool(dates.is_monotonic_increasing),
        "nan": int(vals.isna().sum().sum()),
        "out_of_range": int(((vals < 0) | (vals > 99)).sum().sum()),
        "raw_rows": len(raw),
        "tails_match_raw": bool(
            (raw.set_index("date").drop(columns=[]) % 100)
            .astype(int)
            .equals(df.set_index("date").astype(int))
        ),
        "gap_examples": [
            f"{g[0].date()}..{g[-1].date()} ({len(g)})" for g in sorted(gaps, key=len)[-4:]
        ],
    }
    draws = vals.to_numpy()
    T = len(draws)

    # ---------------- Bước 2-3 trên toàn lịch sử ----------------
    s = stats(draws)
    summ = summarize(s)
    out["families"] = {
        n: {
            "obs": float(summ[i]),
            "null_p50": float(np.median(null[:, i])),
            "null_p95": float(np.quantile(null[:, i], 0.95)),
            "p_mc": p_upper(n, summ[i]),
        }
        for i, n in enumerate(NAMES)
    }
    # tỉ lệ lịch sử công bằng có "Bayes ngây thơ" > 0,99 cho ít nhất một con
    out["naive_bayes_false_alarm"] = {
        t: float((null[:, col["bayes_post_max"]] > t).mean()) for t in (0.85, 0.95, 0.99)
    }
    out["naive_bayes60_false_alarm"] = {
        t: float((null[:, col["bayes60_post_max"]] > t).mean()) for t in (0.85, 0.95)
    }
    out["naive_de_bayes_false_alarm"] = {
        t: float((null[:, col["de_bayes_post_max"]] > t).mean()) for t in (0.85, 0.95)
    }

    H = hits_matrix(draws)
    k = H.sum(axis=0)
    order = np.argsort(-k)
    out["freq_top"] = [
        (f"{i:02d}", int(k[i]), float(k[i] / T), float(s["bayes_post"][i])) for i in order[:5]
    ]
    out["freq_bottom"] = [
        (f"{i:02d}", int(k[i]), float(k[i] / T), float(s["bayes_post"][i])) for i in order[-5:]
    ]
    mz = s["markov_z"]
    out["markov_top"] = [
        (f"{i:02d}", float(s["markov_p11"][i]), float(s["markov_p01"][i]), float(mz[i]))
        for i in np.argsort(-mz)[:5]
    ]
    pz = s["pair_z"]
    flat = np.argsort(-pz, axis=None)[:5]
    out["pair_top"] = [
        (f"{a:02d}->{b:02d}", float(pz[a, b]))
        for a, b in zip(*np.unravel_index(flat, pz.shape), strict=True)
    ]
    out["pair_share_abs_gt2"] = float((np.abs(pz) > 2).mean())
    pos = [f"{p}.{d}" for d in ("chuc", "donvi") for p in vals.columns]
    cl = s["cau_loto"]
    ci = np.argsort(-cl)[:5]
    out["cau_top"] = [(f"{pos[i // 54]}+{pos[i % 54]}", float(cl[i])) for i in ci]
    cd = s["cau_de"]
    out["cau_de_top"] = [
        (f"{pos[i // 54]}+{pos[i % 54]}", float(cd[i])) for i in np.argsort(-cd)[:3]
    ]
    out["year_blocks_corr"] = float(s["year_persist"])

    # ---------------- Kiểm ngoài mẫu: chọn trên 2015-2023, đo trên 2024-nay ----------------
    # z tính với phương sai theo từng kỳ quay (các lượt trúng cùng kỳ không độc lập).
    cut = int((dates < SPLIT).sum())
    Tte = T - cut
    out["oos"] = {
        r["key"]: (r["hits"], r["n"], r["rate"], r["z"], r["in_sample"])
        for r in out_of_sample(draws, df["date"].astype(str))
    }
    out["oos_span"] = (str(dates.iloc[cut].date()), str(dates.iloc[-1].date()), Tte)

    # ---------------- Bước 4: ma trận quyết định cho kỳ kế tiếp ----------------
    last = draws[-1]
    Dl = digits(draws)[-1]
    best_loto = np.zeros(100)
    best_de = np.zeros(100)
    clm, cdm = cl.reshape(54, 54), cd.reshape(54, 54)
    for p in range(54):
        for q in range(54):
            num = 10 * Dl[p] + Dl[q]
            best_loto[num] = max(best_loto[num], clm[p, q])
            best_de[num] = max(best_de[num], cdm[p, q])

    def cnull(name, x):
        return float((null[:, col[name]] < x).mean())

    rows = []
    for i in range(100):
        msig = s["markov_state"][i]
        comps = {
            "bayes": cnull("bayes_post_max", s["bayes_post"][i]),
            "markov": cnull("markov_state_max", msig),
            "cau": cnull("cau_loto_max", best_loto[i]) if best_loto[i] > 0 else 0.0,
        }
        rows.append(("loto", f"{i:02d}", s["bayes_post"][i], msig, best_loto[i], comps))
    tens_y = last[0] // 10
    for i in range(100):
        comps = {
            "bayes": cnull("de_bayes_post_max", s["de_bayes_post"][i]),
            "markov": cnull("de_markov_z_max", s["de_markov_z"][tens_y, i]),
            "cau": cnull("cau_de_max", best_de[i]) if best_de[i] > 0 else 0.0,
        }
        rows.append(
            (
                "de",
                f"{i:02d}",
                s["de_bayes_post"][i],
                s["de_markov_z"][tens_y, i],
                best_de[i],
                comps,
            )
        )

    def tier(c):
        vals_ = sorted(c.values(), reverse=True)
        if vals_[-1] > 0.85:
            return "High", vals_[-1]
        if vals_[1] >= 0.60:
            return "Medium", vals_[1]
        return "Low/Noise", vals_[1]

    table = []
    for mode, num, bp, ms, cr, comps in rows:
        t, score = tier(comps)
        table.append(
            {
                "mode": mode,
                "num": num,
                "naive_bayes": float(bp),
                "markov_sig": float(ms),
                "cau_rate": float(cr),
                **{f"c_{k}": vv for k, vv in comps.items()},
                "tier": t,
                "score": float(score),
            }
        )
    tab = pd.DataFrame(table)
    out["tiers"] = tab.groupby(["mode", "tier"]).size().to_dict()
    out["tiers"] = {f"{a}/{b}": int(c) for (a, b), c in out["tiers"].items()}
    out["top_scores"] = {
        m: tab[tab["mode"] == m]
        .sort_values("score", ascending=False)
        .head(5)
        .round(4)
        .to_dict("records")
        for m in ("loto", "de")
    }
    out["max_component"] = {
        m: {c: float(tab[tab["mode"] == m][f"c_{c}"].max()) for c in ("bayes", "markov", "cau")}
        for m in ("loto", "de")
    }
    # các con VLA đang công bố cho kỳ 2026-09-28
    pred = json.load(open(data_dir / "predictions_today.json", encoding="utf-8"))
    vla_lo = [r["number"] for r in pred["top_lo_to"]]
    vla_de = pred["top_dac_biet"]["top_numbers"]
    out["vla_target"] = pred["date"]
    out["vla_lo"] = (
        tab[(tab["mode"] == "loto") & tab["num"].isin(vla_lo)].round(4).to_dict("records")
    )
    out["vla_de"] = tab[(tab["mode"] == "de") & tab["num"].isin(vla_de)].round(4).to_dict("records")
    out["vla_lo_probs"] = {r["number"]: r["probability"] for r in pred["top_lo_to"]}
    tab.to_csv(out_dir / "decision_matrix.csv", index=False)

    # ---------------- Rủi ro/lợi nhuận: 10 000 kỳ kế tiếp giả lập ----------------
    rng = np.random.default_rng(928)
    sim = rng.integers(0, 100, size=(10_000, 27))
    picks = np.array([int(x) for x in vla_lo])
    occ = (sim[:, :, None] == picks[None, None, :]).sum(axis=(1, 2))
    days_any = (sim[:, :, None] == picks[None, None, :]).any(axis=1).sum(axis=1)
    out["fwd"] = {
        "k": len(picks),
        "mean_occurrences": float(occ.mean()),
        "p_zero_numbers_hit": float((days_any == 0).mean()),
        "p_ge_half": float((days_any >= len(picks) / 2).mean()),
        # 0, 1, 2, 3, 4 và "≥ 5": ô cuối gộp MỌI kỳ có từ 5 con về trở lên.
        "dist_numbers_hit": np.bincount(days_any, minlength=6)[:5].tolist()
        + [int((days_any >= 5).sum())],
        "breakeven_loto_multiple_per_occurrence": 100 / 27,
        "breakeven_de_multiple": 100.0,
    }
    de_picks = np.array([int(x) for x in vla_de])
    out["fwd"]["p_de_in_top10"] = float(np.isin(sim[:, 0], de_picks).mean())

    # ---------------- Vòng phản hồi: vector đã công bố vs kết quả ----------------
    import skill_monitor as sm

    fb = {}
    for mode in sm.MODES:
        days, P, Y = sm.published_evaluation(data_dir, mode)
        if not len(days):
            continue
        # Cùng quy ước chấm với trang production (Đặc Biệt theo 100 lớp).
        model = forecast_scores(mode, P, Y)
        base = forecast_scores(mode, np.full_like(P, sm.baseline_rate(mode)), Y)
        fb[mode] = {
            "days": len(days),
            "first": days[0],
            "last": days[-1],
            **{f"{k}_model": v for k, v in model.items()},
            **{f"{k}_base": v for k, v in base.items()},
            "prob_std_mean": float(P.std(axis=1).mean()),
        }
        d2, sk = sm.graded_series(data_dir, mode)
        sk = np.asarray(sk)
        fb[mode]["ledger_days"] = len(sk)
        fb[mode]["skill_mean"] = float(sk.mean())
        fb[mode]["skill_std_first_half"] = float(sk[: len(sk) // 2].std())
        fb[mode]["skill_std_second_half"] = float(sk[len(sk) // 2 :].std())
    out["feedback"] = fb
    out["monitor"] = [c.as_dict() for c in sm.evaluate(data_dir)]

    (out_dir / "report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sims", type=int, default=10_000)
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--out-dir", type=Path, default=Path("."))
    ap.add_argument("--null", type=Path, help="dùng lại phân phối null đã lưu (.npy)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.null:
        null = np.load(args.null)
    else:
        T = len(load(args.data_dir))
        if args.sims < 1:
            ap.error("--sims phải ≥ 1")
        null = simulate_null(T, args.sims, workers=args.workers)
        np.save(args.out_dir / "null.npy", null)
    out = report(null, args.data_dir, args.out_dir)
    print(
        json.dumps(
            {k: out[k] for k in ("n_sims", "families", "oos", "tiers")},
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
