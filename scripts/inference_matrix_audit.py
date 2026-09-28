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
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = 1 - 0.99**27
PRIOR_N = 100.0  # Beta prior "ngây thơ": 100 kỳ giả, tâm ở tỉ lệ nền
SPLIT = "2024-01-01"


def load(data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(data_dir / "xsmb-2-digits.csv")


def hits_matrix(draws: np.ndarray) -> np.ndarray:
    T = draws.shape[0]
    H = np.zeros((T, 100), dtype=np.uint8)
    H[np.arange(T)[:, None], draws] = 1
    return H


def digits(draws: np.ndarray) -> np.ndarray:
    # 54 vị trí chữ số: hàng chục rồi hàng đơn vị của 27 giải
    return np.concatenate([draws // 10, draws % 10], axis=1).astype(np.int16)


def cau_hits(D: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Số lần trúng của 54x54 cầu vị trí: số = 10*D[t,p] + D[t,q] -> trúng ở t+1.

    target: (T,100) 0/1 của kỳ t (LOTO: có về; ĐB: đúng giải ĐB).
    """
    idx = (10 * D[:-1, :, None] + D[:-1, None, :]).reshape(D.shape[0] - 1, -1)
    return np.take_along_axis(target[1:], idx, axis=1).sum(axis=0, dtype=np.int32)


def stats(draws: np.ndarray) -> dict[str, np.ndarray | float]:
    T = draws.shape[0]
    H = hits_matrix(draws)
    S = np.zeros((T, 100), dtype=np.uint8)
    S[np.arange(T), draws[:, 0]] = 1
    D = digits(draws)
    out: dict[str, np.ndarray | float] = {}

    # --- tần suất LOTO (số kỳ có về) ---
    k = H.sum(axis=0).astype(float)
    z = (k - T * BASE) / np.sqrt(T * BASE * (1 - BASE))
    out["freq_z"] = z
    out["freq_chi2"] = float(((k - T * BASE) ** 2 / (T * BASE)).sum())
    # Bayes ngây thơ: P(p_i > nền | dữ liệu), prior Beta tâm nền, 100 kỳ giả
    from scipy.stats import beta as B

    a0, b0 = PRIOR_N * BASE, PRIOR_N * (1 - BASE)
    out["bayes_post"] = B.sf(BASE, a0 + k, b0 + T - k)
    # Bayes ngắn hạn: 60 kỳ gần nhất, prior từ toàn lịch sử trước đó (nặng 100)
    k60 = H[-60:].sum(axis=0).astype(float)
    out["bayes60_post"] = B.sf(BASE, a0 + k60, b0 + 60 - k60)

    # --- Markov 2 trạng thái cho từng con: P(về | hôm qua về) - P(về | hôm qua trượt) ---
    prev, nxt = H[:-1].astype(float), H[1:].astype(float)
    n1 = prev.sum(axis=0)
    n0 = (T - 1) - n1
    p11 = (prev * nxt).sum(axis=0) / n1
    p01 = ((1 - prev) * nxt).sum(axis=0) / n0
    pp = nxt.mean(axis=0)
    se = np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n0))
    out["markov_z"] = (p11 - p01) / se
    out["markov_p11"], out["markov_p01"] = p11, p01

    # --- bạc nhớ: con i hôm nay -> con j ngày mai, 100x100 ---
    C = prev.T @ nxt
    E = np.outer(n1, pp)
    out["pair_z"] = (C - E) / np.sqrt(E * (1 - pp)[None, :])

    # --- cầu vị trí 54x54, đích LOTO và ĐB ---
    out["cau_loto"] = cau_hits(D, H) / (T - 1)
    out["cau_de"] = cau_hits(D, S) / (T - 1)

    # --- đứt gãy cấu trúc / xu hướng dài hạn: CUSUM từng con ---
    cs = np.cumsum(H - BASE, axis=0)
    out["cusum"] = np.abs(cs).max(axis=0) / np.sqrt(T * BASE * (1 - BASE))
    distinct = H.sum(axis=1).astype(float)
    mu = 100 * BASE
    var = distinct.var() if distinct.var() > 0 else 1.0
    out["distinct_cusum"] = float(np.abs(np.cumsum(distinct - mu)).max() / np.sqrt(T * var))

    # --- bền vững của "số nóng" theo năm (khối 365 kỳ) ---
    blocks = [H[i : i + 365].sum(axis=0) for i in range(0, T - 364, 365)]
    cors = [np.corrcoef(blocks[i], blocks[i + 1])[0, 1] for i in range(len(blocks) - 1)]
    out["year_persist"] = float(np.mean(cors))

    # --- Đặc Biệt ---
    ks = S.sum(axis=0).astype(float)
    out["de_chi2"] = float(((ks - T / 100) ** 2 / (T / 100)).sum())
    out["de_bayes_post"] = B.sf(0.01, 1 + ks, 99 + T - ks)  # prior Beta(1,99)
    tens = draws[:, 0] // 10
    M = np.zeros((10, 100))
    np.add.at(M, (tens[:-1], draws[1:, 0]), 1)
    rows = M.sum(axis=1, keepdims=True)
    Em = rows / 100
    out["de_markov_z"] = (M - Em) / np.sqrt(Em * 0.99)
    out["de_to_loto"] = float(H[1:][np.arange(T - 1), draws[:-1, 0]].mean())
    return out


def summarize(s: dict) -> np.ndarray:
    """Thống kê LỚN NHẤT trên mỗi họ giả thuyết — thứ phân phối null cần."""
    return np.array(
        [
            np.abs(s["freq_z"]).max(),
            s["freq_chi2"],
            s["bayes_post"].max(),
            s["bayes60_post"].max(),
            s["markov_z"].max(),
            np.abs(s["markov_z"]).max(),
            s["pair_z"].max(),
            s["cau_loto"].max(),
            s["cau_de"].max(),
            s["cusum"].max(),
            s["distinct_cusum"],
            s["year_persist"],
            s["de_chi2"],
            s["de_bayes_post"].max(),
            s["de_markov_z"].max(),
            s["de_to_loto"],
            s["freq_z"].max(),
        ]
    )


NAMES = [
    "freq_absz_max",
    "freq_chi2",
    "bayes_post_max",
    "bayes60_post_max",
    "markov_z_max",
    "markov_absz_max",
    "pair_z_max",
    "cau_loto_max",
    "cau_de_max",
    "cusum_max",
    "distinct_cusum",
    "year_persist",
    "de_chi2",
    "de_bayes_post_max",
    "de_markov_z_max",
    "de_to_loto",
    "freq_z_max",
]


def worker(args):
    seed, n, T = args
    rng = np.random.default_rng(seed)
    return np.stack([summarize(stats(rng.integers(0, 100, size=(T, 27)))) for _ in range(n)])


def _logloss(q: np.ndarray, y: np.ndarray) -> float:
    eps = 1e-12
    return float(-(y * np.log(q + eps) + (1 - y) * np.log(1 - q + eps)).mean())


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
    cut = int((dates < SPLIT).sum())
    tr = stats(draws[:cut])
    Hte = H[cut:]
    Tte = len(Hte)

    def binom_z(hits, n, p):
        return (hits - n * p) / np.sqrt(n * p * (1 - p))

    oos = {}
    top = np.argsort(-tr["bayes_post"])[:10]
    h = Hte[:, top].sum()
    oos["bayes_top10"] = (
        int(h),
        int(Tte * 10),
        float(h / (Tte * 10)),
        float(binom_z(h, Tte * 10, BASE)),
    )
    top = np.argsort(-tr["markov_z"])[:10]
    prev, nxt = Hte[:-1, top], Hte[1:, top]
    n = int(prev.sum())
    h = int((prev * nxt).sum())
    oos["markov_top10_after_hit"] = (h, n, h / n, float(binom_z(h, n, BASE)))
    flat = np.argsort(-tr["pair_z"], axis=None)[:50]
    a, b = np.unravel_index(flat, (100, 100))
    n = int(Hte[:-1, a].sum())
    h = int((Hte[:-1, a] * Hte[1:, b]).sum())
    oos["pair_top50"] = (h, n, h / n, float(binom_z(h, n, BASE)))
    D = digits(draws)
    Dte = D[cut - 1 :]  # kỳ cuối của tập học dự báo cho kỳ đầu của tập thử
    Hx = H[cut - 1 :]
    S = np.zeros((T, 100), dtype=np.uint8)
    S[np.arange(T), draws[:, 0]] = 1
    Sx = S[cut - 1 :]
    for name, key, tgt, base, K in (
        ("cau_loto_top20", "cau_loto", Hx, BASE, 20),
        ("cau_de_top20", "cau_de", Sx, 0.01, 20),
    ):
        sel = np.argsort(-tr[key])[:K]
        hits = cau_hits(Dte, tgt)[sel].sum()
        nn = (len(Dte) - 1) * K
        oos[name] = (
            int(hits),
            int(nn),
            float(hits / nn),
            float(binom_z(hits, nn, base)),
            float(tr[key][sel].mean()),
        )
    flat = np.argsort(-tr["de_markov_z"], axis=None)[:20]
    r, c = np.unravel_index(flat, (10, 100))
    tens = draws[cut - 1 : -1, 0] // 10
    nxt_de = draws[cut:, 0]
    n = h = 0
    for rr, cc in zip(r, c, strict=True):
        m = tens == rr
        n += int(m.sum())
        h += int((nxt_de[m] == cc).sum())
    oos["de_markov_top20"] = (h, n, h / n, float(binom_z(h, n, 0.01)))
    out["oos"] = oos
    out["oos_span"] = (str(dates.iloc[cut].date()), str(dates.iloc[-1].date()), Tte)

    # ---------------- Bước 4: ma trận quyết định cho kỳ kế tiếp ----------------
    last = draws[-1]
    hit_y = H[-1].astype(bool)
    Dl = D[-1]
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
        msig = mz[i] if hit_y[i] else -mz[i]
        comps = {
            "bayes": cnull("bayes_post_max", s["bayes_post"][i]),
            "markov": cnull("markov_z_max", msig),
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
        base = np.full_like(P, sm.baseline_rate(mode))
        fb[mode] = {
            "days": len(days),
            "first": days[0],
            "last": days[-1],
            "mae_model": float(np.abs(P - Y).mean()),
            "mae_base": float(np.abs(base - Y).mean()),
            "brier_model": float(((P - Y) ** 2).mean()),
            "brier_base": float(((base - Y) ** 2).mean()),
            "logloss_model": _logloss(P, Y),
            "logloss_base": _logloss(base, Y),
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
        # Chia phần dư cho các khối đầu: chạy ĐÚNG số mô phỏng được yêu cầu.
        # Với 10 000 (chia hết cho 40) các khối và hạt giống y như trước.
        chunks = min(40, args.sims)
        sizes = [args.sims // chunks + (1 if i < args.sims % chunks else 0) for i in range(chunks)]
        seeds = np.random.SeedSequence(20260928).spawn(chunks)
        jobs = [(s, n, T) for s, n in zip(seeds, sizes, strict=True)]
        with Pool(args.workers) as pool:
            null = np.concatenate(pool.map(worker, jobs))
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
