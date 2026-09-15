from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from hierarchical_pooling import fit_shrinkage_to_prior_rows
from lottery import Lottery
from path_models import build_daily_targets
from research_diagnostics import bh_fdr


#: ``None`` nghĩa là HỌC độ co ngót theo từng con đề, thay cho hằng số 60.
#:
#: Đo trên chính bảng này (khớp 1 792 cặp đầu, chấm điểm 598 cặp đuôi mà phép
#: khớp chưa từng thấy):
#:
#:     κ = 60 (đặt tay)    Brier 0,18208903   log-loss 0,550738
#:     co ngót hoàn toàn   Brier 0,18162217   log-loss 0,549427   t = -6,02
#:     HỌC κ               Brier 0,18166797   log-loss 0,549560   t = -6,15
#:
#: Bảng này là bằng chứng mô tả, không vào bộ hợp thành, nên không có Brier
#: của bộ hợp thành để gác — phải chấm điểm chính ``p_eb`` trên phần đuôi.
#:
#: Trung vị κ học được là 1 000 000, tức co ngót HOÀN TOÀN. Nói thẳng điều đó
#: nghĩa là gì: với dữ liệu hiện có, "đề về s hôm nay" KHÔNG phân biệt được
#: phân phối LOTO ngày mai so với phân phối chung. Cả bảng 10 000 dòng là
#: nhiễu, và hằng số 60 đã khiến nó trông như có nội dung. Giữ nguyên phép
#: học chứ không chốt cứng co ngót hoàn toàn, để nếu về sau có tín hiệu thật
#: thì nó tự nổi lên.
LEARN_CONDITIONAL_PRIOR: float | None = None


def compute_loto_nextday_given_special(
    df_2d: pd.DataFrame,
    *,
    prior_strength: float | None = LEARN_CONDITIONAL_PRIOR,
) -> pd.DataFrame:
    """Estimate P(Loto=x at t+1 | De_2d at t=s) for all observed s,x.

    Improvements over the legacy implementation:
    - only exact next-calendar-day pairs are eligible;
    - probabilities are reported both raw and empirical-Bayes shrunk toward the
      unconditional next-day number prevalence;
    - effect/lift and one-sided p-values are measured against that marginal
      baseline, with BH-FDR across the full conditional matrix.

    The table is research/descriptive evidence and is not consumed by the
    production ensemble.
    """
    df_2d = df_2d.sort_values("date").reset_index(drop=True).copy()
    dates, loto_targets, de_targets = build_daily_targets(df_2d)
    n = len(dates)
    columns = [
        "special",
        "special_str",
        "number",
        "number_str",
        "trials",
        "hits",
        "p",
        "p_raw",
        "p_eb",
        "baseline",
        "effect_raw",
        "lift_raw",
        "prior_strength",
        "p_value",
        "q_value_fdr",
        "fdr_05",
    ]
    if n < 2:
        return pd.DataFrame(columns=columns)

    dates_pd = pd.DatetimeIndex(pd.to_datetime(dates))
    consecutive = np.asarray((dates_pd[1:] - dates_pd[:-1]).days == 1, dtype=bool)

    trials = np.zeros(100, dtype=np.int32)
    hits = np.zeros((100, 100), dtype=np.int32)
    global_hits = np.zeros(100, dtype=np.int32)
    eligible_pairs = 0

    for t in range(n - 1):
        if not consecutive[t]:
            continue
        s = int(de_targets[t])
        trials[s] += 1
        eligible_pairs += 1
        next_set = loto_targets[t + 1]
        if next_set:
            idx = np.fromiter((int(x) for x in next_set), dtype=np.int16, count=len(next_set))
            hits[s, idx] += 1
            global_hits[idx] += 1

    if eligible_pairs == 0:
        return pd.DataFrame(columns=columns)

    baseline = global_hits.astype(float) / float(eligible_pairs)
    if prior_strength is None:
        # Mỗi con đề là một câu hỏi riêng — "đề về s thì kéo theo gì" — nên
        # nó phải có độ co ngót riêng. Gộp cả 10 000 ô vào một κ sẽ dìm chết
        # một quan hệ thật nếu chỉ vài hàng có tín hiệu.
        row_prior = fit_shrinkage_to_prior_rows(
            hits.astype(float), np.maximum(trials, 1).astype(float), baseline
        )
    else:
        row_prior = np.full(100, float(prior_strength))
    rows: list[dict[str, object]] = []
    p_values: list[float] = []
    for s in range(100):
        tr = int(trials[s])
        if tr == 0:
            continue
        for x in range(100):
            h = int(hits[s, x])
            p_raw = h / tr
            base = float(baseline[x])
            k = float(row_prior[s])
            p_eb = (h + k * base) / (tr + k)
            if 0.0 < base < 1.0:
                p_value = float(stats.binom.sf(h - 1, tr, base))
            elif base <= 0.0:
                p_value = 0.0 if h > 0 else 1.0
            else:
                p_value = 1.0
            p_values.append(p_value)
            rows.append(
                {
                    "special": s,
                    "special_str": f"{s:02d}",
                    "number": x,
                    "number_str": f"{x:02d}",
                    "trials": tr,
                    "hits": h,
                    # Backward-compatible alias: legacy consumers used `p`.
                    "p": p_raw,
                    "p_raw": p_raw,
                    "p_eb": float(p_eb),
                    "baseline": base,
                    "effect_raw": float(p_raw - base),
                    "lift_raw": float(p_raw / base) if base > 0 else None,
                    "prior_strength": k,
                    "p_value": p_value,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=columns)
    out["q_value_fdr"] = bh_fdr(np.asarray(p_values, dtype=float))
    out["fdr_05"] = out["q_value_fdr"] <= 0.05
    return out[columns]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20, help="Top numbers per special to export")
    ap.add_argument(
        "--prior-strength",
        type=float,
        default=None,
        help="Ép độ co ngót; bỏ trống thì học từ dữ liệu",
    )
    ap.add_argument("--out-dir", type=str, default="data/conditional")
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    df_2d = lot.get_2_digits_data()
    if df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    forced_prior = (
        None if args.prior_strength is None else max(0.0, float(args.prior_strength))
    )
    long_df = compute_loto_nextday_given_special(df_2d, prior_strength=forced_prior)
    long_path = out_dir / "loto_nextday_given_special_long.csv"
    long_df.to_csv(long_path, index=False)

    top_df = (
        long_df.sort_values(
            ["special", "p_eb", "q_value_fdr", "hits"],
            ascending=[True, False, True, False],
        )
        .groupby("special", sort=True)
        .head(max(1, int(args.top)))
        .reset_index(drop=True)
    )
    top_path = out_dir / f"loto_nextday_given_special_top{max(1, int(args.top))}.csv"
    top_df.to_csv(top_path, index=False)

    latest = pd.to_datetime(df_2d["date"]).max().date().isoformat()
    current_special = int(df_2d.sort_values("date").iloc[-1]["special"]) % 100
    current = long_df[long_df["special"] == current_special].sort_values(
        ["p_eb", "q_value_fdr", "hits"], ascending=[False, True, False]
    )
    current_path = out_dir / "current_special_next_loto.csv"
    current.head(max(1, int(args.top))).to_csv(current_path, index=False)

    manifest = {
        "schema_version": 2,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "anchor_date": latest,
        "current_special_2d": f"{current_special:02d}",
        "research_only": True,
        "rows": int(len(long_df)),
        "observed_special_states": int(long_df["special"].nunique()) if not long_df.empty else 0,
        "fdr_05_count": int(long_df["fdr_05"].sum()) if not long_df.empty else 0,
        "prior_strength_learned": forced_prior is None,
        "prior_strength_median": (
            float(long_df["prior_strength"].median()) if not long_df.empty else None
        ),
        "note": "Conditional historical matrix only; it does not alter production prediction weights.",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Saved {long_path}")
    print(f"Saved {top_path}")
    print(f"Saved {current_path}")


if __name__ == "__main__":
    main()
