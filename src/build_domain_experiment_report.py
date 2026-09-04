from __future__ import annotations

"""Tổng hợp artifact ablation miền số thành báo cáo thí nghiệm máy đọc được."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def _read_gate(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Artifact cổng không hợp lệ: {path}")
    return payload


def _rejection_reasons(
    *, brier_skill: float, logloss_skill: float, confirmed_stage: bool
) -> list[str]:
    reasons: list[str] = []
    if brier_skill <= 0.0:
        reasons.append("negative_brier_skill")
    if logloss_skill <= 0.0:
        reasons.append("negative_logloss_skill")
    if confirmed_stage:
        reasons.insert(0, "unstable_across_folds")
    if not reasons:
        reasons.append("insufficient_support")
    return reasons


def _records_for_mode(
    mode: str, ablation: pd.DataFrame, gate: dict[str, object]
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    groups = list(dict(gate.get("feature_groups", {})).keys())
    screened = set(gate.get("screened_groups", []))
    generated_day = str(gate.get("generated_at", ""))[:10].replace("-", "")
    promoted_groups = set(gate.get("production_selected_groups", []))

    for group in groups:
        confirmed_stage = group in screened
        if confirmed_stage:
            rows = ablation[
                (ablation["stage"] == "confirm")
                & (ablation["candidate"] == group)
            ]
        else:
            rows = ablation[
                (ablation["stage"] == "screen")
                & (ablation["candidate"] == group)
            ]
        if rows.empty:
            raise ValueError(f"Thiếu kết quả {mode}/{group} trong ablation")

        baseline_brier = float(rows["baseline_brier"].mean())
        challenger_brier = float(rows["candidate_brier"].mean())
        baseline_logloss = float(rows["baseline_logloss"].mean())
        challenger_logloss = float(rows["candidate_logloss"].mean())
        brier_improvement = baseline_brier - challenger_brier
        logloss_improvement = baseline_logloss - challenger_logloss
        brier_skill = brier_improvement / baseline_brier
        logloss_skill = logloss_improvement / baseline_logloss
        val_ends = rows["val_end_exclusive"].dropna().astype(str)
        evaluation_end = val_ends.max() if not val_ends.empty else None

        promoted = group in promoted_groups
        records.append(
            {
                "experiment_id": (
                    f"EXP-{mode.upper()}-{group.upper().replace('_', '-')}-"
                    f"{generated_day}"
                ),
                "algorithm_group": group,
                "mode": mode,
                "parameters": {
                    "baseline_features": int(gate["baseline_feature_count"]),
                    "challenger_features": int(rows["feature_count"].iloc[0]),
                    "positive_skill_threshold": float(
                        gate["positive_skill_threshold"]
                    ),
                },
                "evaluation_period": {
                    "start": str(rows["val_start"].min()),
                    "end_exclusive": evaluation_end,
                },
                "folds": [int(value) for value in rows["fold"].tolist()],
                "oos_dates": int(rows["oos_dates"].sum()),
                "oos_rows": int(rows["oos_rows"].sum()),
                "baseline_brier": baseline_brier,
                "challenger_brier": challenger_brier,
                "brier_improvement": brier_improvement,
                "brier_skill": brier_skill,
                "brier_ci": None,
                "baseline_logloss": baseline_logloss,
                "challenger_logloss": challenger_logloss,
                "logloss_improvement": logloss_improvement,
                "logloss_skill": logloss_skill,
                "logloss_ci": None,
                "promoted": promoted,
                "rejection_reason": []
                if promoted
                else _rejection_reasons(
                    brier_skill=brier_skill,
                    logloss_skill=logloss_skill,
                    confirmed_stage=confirmed_stage,
                ),
                "ci_status": (
                    "passed_final_gate"
                    if promoted
                    else "not_computed_candidate_failed_before_final_gate"
                ),
            }
        )
    return records


def build_report(*, data_dir: Path, output: Path) -> dict[str, object]:
    experiments: list[dict[str, object]] = []
    gates: dict[str, dict[str, object]] = {}
    for mode in ("loto", "de"):
        gate = _read_gate(data_dir / f"cau_keo_domain_gate_{mode}.json")
        ablation = pd.read_csv(data_dir / f"cau_keo_domain_ablation_{mode}.csv")
        experiments.extend(_records_for_mode(mode, ablation, gate))
        gates[mode] = gate

    payload: dict[str, object] = {
        "schema_version": 2,
        "generated_at": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "baseline": "HistGradientBoosting cầu-kèo với 39 đặc trưng production",
        "common_parameters": {
            "screening_folds": [1, 2],
            "confirmation_fold": 3,
            "untouched_final_fold": 4,
            "bootstrap_replicates_if_final_gate_reached": 1_000,
            "bootstrap_seed": 20260902,
        },
        "result_summary": {
            "promoted_groups": {
                mode: list(gate.get("production_selected_groups", []))
                for mode, gate in gates.items()
            },
            "production_changed": any(
                bool(gate.get("domain_active")) for gate in gates.values()
            ),
            "note": (
                "Production chỉ dùng nhóm có trong cổng cuối; nhóm không đạt "
                "vẫn là research-only."
            ),
        },
        "experiments": experiments,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tạo báo cáo thí nghiệm challenger miền số."
    )
    parser.add_argument("--data-dir", default="data/ai_ml")
    parser.add_argument(
        "--output", default="docs/research/experiment_results.json"
    )
    args = parser.parse_args()
    payload = build_report(data_dir=Path(args.data_dir), output=Path(args.output))
    print(
        f"[OK] {args.output}: {len(payload['experiments'])} thí nghiệm, "
        f"production_changed={payload['result_summary']['production_changed']}"
    )


if __name__ == "__main__":
    main()
