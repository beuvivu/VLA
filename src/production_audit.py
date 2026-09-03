from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(".")
TZ = ZoneInfo("Asia/Ho_Chi_Minh")

REQUIRED_PATHS = [
    "data/xsmb.csv",
    "data/xsmb.json",
    "data/source_audit.json",
    "data/health.json",
    "data/predict/fun_draw_next.json",
    "data/predict/fun_draw_next.csv",
    "data/history/pred_loto.csv",
    "data/history/pred_de.csv",
    "data/statistical_signal/predict_next_loto_stat_all.csv",
    "data/statistical_signal/predict_next_de_stat_all.csv",
    "data/number_dynamics/current_dynamics_loto.csv",
    "data/number_dynamics/current_dynamics_de.csv",
    "data/number_dynamics/diagnostics_loto.json",
    "data/number_dynamics/diagnostics_de.json",
    "data/advanced/conditional_matrices_diagnostics.json",
    "data/advanced/ai_ml_signal_diagnostics.json",
    "data/advanced/ai_ml_signal_loto.csv",
    "data/advanced/ai_ml_signal_de.csv",
    "data/ai_ml/cau_keo_manifest_loto.json",
    "data/ai_ml/cau_keo_manifest_de.json",
    "models/ml_loto.joblib",
    "models/ml_de.joblib",
    "models/cau_keo_loto.joblib",
    "models/cau_keo_de.joblib",
    "models/meta_loto.joblib",
    "models/meta_de.joblib",
    "docs/index.html",
    "docs/live.html",
    "docs/statistics.html",
    "docs/dashboard.html",
    "docs/model-quality.html",
    "DASHBOARD.md",
    "README.md",
]


def _parse_cutoff(value: str) -> time:
    hh, mm = value.split(":", 1)
    return time(int(hh), int(mm))


def expected_latest_draw(now: datetime, cutoff: time) -> date:
    return (
        now.date()
        if now.time().replace(tzinfo=None) >= cutoff
        else now.date() - timedelta(days=1)
    )


def _dates_from_csv(path: Path) -> list[date]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = csv.DictReader(fh)
        return [
            date.fromisoformat(str(row["date"])[:10])
            for row in rows
            if row.get("date")
        ]


def _prediction_target(path: Path) -> str | None:
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        row = next(csv.DictReader(fh), None)
    if row:
        for key in ("predict_for_date", "target_date", "date"):
            if row.get(key):
                return str(row[key])[:10]
    suffix = path.stem[-10:]
    try:
        return date.fromisoformat(suffix).isoformat()
    except ValueError:
        return None


def _json(path: str) -> dict:
    obj = json.loads((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return obj


def _single_csv_value(path: str, column: str) -> str | None:
    values: set[str] = set()
    with (ROOT / path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            value = str(row.get(column, "")).strip()
            if value:
                values.add(value[:10] if "date" in column else value)
    return next(iter(values)) if len(values) == 1 else None


def audit(
    *,
    now: datetime | None = None,
    cutoff: str = "18:15",
    check_freshness: bool = True,
    check_docs: bool = True,
) -> dict:
    now = now or datetime.now(TZ)
    cutoff_t = _parse_cutoff(cutoff)
    critical: list[str] = []
    warnings: list[str] = []

    missing = [
        p
        for p in REQUIRED_PATHS
        if not (ROOT / p).is_file() or (ROOT / p).stat().st_size == 0
    ]
    if missing:
        critical.append("missing_or_empty=" + ",".join(missing))

    latest: date | None = None
    dates: list[date] = []
    raw_path = ROOT / "data/xsmb.csv"
    if raw_path.exists():
        try:
            dates = sorted(_dates_from_csv(raw_path))
            latest = dates[-1] if dates else None
        except Exception as exc:  # noqa: BLE001
            critical.append(f"xsmb_csv_invalid={exc}")

    expected = expected_latest_draw(now, cutoff_t)
    if latest is None:
        critical.append("latest_canonical_missing")
    elif check_freshness and latest < expected:
        critical.append(f"canonical_stale latest={latest} expected={expected}")
    elif check_freshness and latest > expected:
        warnings.append(f"canonical_ahead latest={latest} expected={expected}")

    if dates:
        if len(dates) != len(set(dates)):
            critical.append("duplicate_canonical_dates")
        missing_days: list[str] = []
        for prev, cur in zip(dates[:-1], dates[1:], strict=True):
            gap = (cur - prev).days
            if gap > 1:
                missing_days.extend(
                    (prev + timedelta(days=i)).isoformat()
                    for i in range(1, gap)
                )
        if missing_days:
            critical.append("canonical_gaps=" + ",".join(missing_days[-10:]))

    if latest:
        try:
            source_audit = _json("data/source_audit.json")
            item = source_audit.get(latest.isoformat(), {})
            if not item.get("accepted"):
                critical.append(f"source_audit_not_accepted={latest}")
            if int(item.get("agreement", 0)) < 2:
                critical.append(f"source_consensus_lt2={latest}")
        except Exception as exc:  # noqa: BLE001
            critical.append(f"source_audit_invalid={exc}")

        target = latest + timedelta(days=1)
        target_str = target.isoformat()

        try:
            fun = _json("data/predict/fun_draw_next.json")
            if fun.get("anchor_date") != latest.isoformat():
                critical.append(
                    f"fun_anchor_mismatch={fun.get('anchor_date')} expected={latest}"
                )
            if fun.get("target_date") != target_str:
                critical.append(
                    f"fun_target_mismatch={fun.get('target_date')} expected={target}"
                )
            if len(fun.get("rows", [])) != 27:
                critical.append("fun_rows_not_27")
            if len(fun.get("top_loto", [])) < 10 or len(fun.get("top_de", [])) < 10:
                critical.append("fun_top10_incomplete")
        except Exception as exc:  # noqa: BLE001
            critical.append(f"fun_prediction_invalid={exc}")

        for mode in ("loto", "de"):
            candidates = sorted(
                (ROOT / "data/predict").glob(f"predict_next_{mode}_all_*.csv")
            )
            if not candidates:
                critical.append(f"predict_{mode}_missing")
                continue
            latest_file = max(candidates, key=lambda p: p.name)
            pred_target = _prediction_target(latest_file)
            if pred_target != target_str:
                critical.append(
                    f"predict_{mode}_target={pred_target} expected={target}"
                )

            stat_target = _prediction_target(
                ROOT / f"data/statistical_signal/predict_next_{mode}_stat_all.csv"
            )
            if stat_target != target_str:
                critical.append(
                    f"stat_signal_{mode}_target={stat_target} expected={target}"
                )

            try:
                cau = _json(f"data/ai_ml/cau_keo_manifest_{mode}.json")
                if str(cau.get("predict_for_date"))[:10] != target_str:
                    critical.append(
                        f"cau_keo_{mode}_target={cau.get('predict_for_date')} expected={target}"
                    )
                contract = str(cau.get("calendar_contract", ""))
                if contract != "daily-contiguous raw and two-digit histories":
                    critical.append(f"cau_keo_{mode}_calendar_contract_missing")
            except Exception as exc:  # noqa: BLE001
                critical.append(f"cau_keo_{mode}_manifest_invalid={exc}")

            overlay_target = _single_csv_value(
                f"data/advanced/ai_ml_signal_{mode}.csv", "target_date"
            )
            if overlay_target != target_str:
                critical.append(
                    f"ai_overlay_{mode}_target={overlay_target} expected={target}"
                )

        try:
            cond = _json("data/advanced/conditional_matrices_diagnostics.json")
            if int(cond.get("calendar_rows", -1)) != len(dates):
                critical.append(
                    f"conditional_calendar_rows={cond.get('calendar_rows')} expected={len(dates)}"
                )
            if int(cond.get("exact_next_day_pairs", -1)) != max(0, len(dates) - 1):
                critical.append(
                    "conditional_next_pairs="
                    f"{cond.get('exact_next_day_pairs')} expected={max(0, len(dates)-1)}"
                )
            if int(cond.get("skipped_nonconsecutive_boundaries", -1)) != 0:
                critical.append(
                    "conditional_nonconsecutive_boundaries="
                    f"{cond.get('skipped_nonconsecutive_boundaries')}"
                )
            if str(cond.get("calendar_end", ""))[:10] != latest.isoformat():
                critical.append(
                    f"conditional_calendar_end={cond.get('calendar_end')} expected={latest}"
                )
        except Exception as exc:  # noqa: BLE001
            critical.append(f"conditional_diagnostics_invalid={exc}")

        try:
            overlay = _json("data/advanced/ai_ml_signal_diagnostics.json")
            if str(overlay.get("anchor_date", ""))[:10] != latest.isoformat():
                critical.append(
                    f"ai_overlay_anchor={overlay.get('anchor_date')} expected={latest}"
                )
            if str(overlay.get("target_date", ""))[:10] != target_str:
                critical.append(
                    f"ai_overlay_target={overlay.get('target_date')} expected={target}"
                )
            modes = overlay.get("modes", {})
            for mode in ("loto", "de"):
                ml = (modes.get(mode) or {}).get("ml") or {}
                attempts = ml.get("attempts") or []
                if ml.get("available"):
                    if ml.get("source") not in {
                        "cau_keo",
                        "base_ml",
                        "ensemble_exact",
                    }:
                        critical.append(
                            f"ai_overlay_{mode}_unknown_source={ml.get('source')}"
                        )
                    if not attempts or attempts[-1].get("status") != "ok":
                        critical.append(f"ai_overlay_{mode}_accepted_without_ok")
        except Exception as exc:  # noqa: BLE001
            critical.append(f"ai_overlay_diagnostics_invalid={exc}")

        for mode in ("loto", "de"):
            try:
                dyn = _json(f"data/number_dynamics/diagnostics_{mode}.json")
                if dyn.get("calendar_contiguous") is not True:
                    critical.append(f"dynamics_{mode}_calendar_not_verified")
                if str(dyn.get("anchor_date", ""))[:10] != latest.isoformat():
                    critical.append(
                        f"dynamics_{mode}_anchor={dyn.get('anchor_date')} expected={latest}"
                    )
            except Exception as exc:  # noqa: BLE001
                critical.append(f"dynamics_{mode}_diagnostics_invalid={exc}")

        try:
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            if (
                readme.count("<!-- FUN_PREDICTION:BEGIN -->") != 1
                or readme.count("<!-- FUN_PREDICTION:END -->") != 1
            ):
                critical.append("readme_fun_prediction_markers_invalid")
            target_display = target.strftime("%d-%m-%Y")
            if f"Dự đoán vui ngày {target_display}" not in readme:
                critical.append(
                    f"readme_prediction_target_missing={target_display}"
                )
        except Exception as exc:  # noqa: BLE001
            critical.append(f"readme_invalid={exc}")

        if check_docs:
            for page in (
                "docs/index.html",
                "docs/landing.html",
                "docs/landing_desktop.html",
            ):
                p = ROOT / page
                if not p.exists() or p.stat().st_size == 0:
                    critical.append(f"landing_page_missing={page}")
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
                if text.count('id="du-doan-vui"') != 1:
                    critical.append(f"fun_board_marker_invalid={page}")

    try:
        health = _json("data/health.json")
        if health.get("ok") is False:
            critical.append("health_json_not_ok")
    except Exception as exc:  # noqa: BLE001
        critical.append(f"health_json_invalid={exc}")

    return {
        "schema_version": 2,
        "checked_at_local": now.isoformat(),
        "cutoff": cutoff,
        "freshness_checked": check_freshness,
        "docs_checked": check_docs,
        "expected_latest_draw": expected.isoformat(),
        "latest_canonical": latest.isoformat() if latest else None,
        "ok": not critical,
        "critical": critical,
        "warnings": warnings,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="18:15")
    ap.add_argument("--json-out", default="data/production_audit.json")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--consistency-only", action="store_true")
    ap.add_argument("--skip-docs", action="store_true")
    args = ap.parse_args()

    result = audit(
        cutoff=args.cutoff,
        check_freshness=not args.consistency_only,
        check_docs=not args.skip_docs,
    )
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
