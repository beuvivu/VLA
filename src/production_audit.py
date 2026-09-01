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
    "models/ml_loto.joblib",
    "models/ml_de.joblib",
    "models/meta_loto.joblib",
    "models/meta_de.joblib",
    "docs/index.html",
    "docs/live.html",
    "docs/statistics.html",
    "docs/dashboard.html",
    "docs/model-quality.html",
    "README.md",
]


def _parse_cutoff(value: str) -> time:
    hh, mm = value.split(":", 1)
    return time(int(hh), int(mm))


def expected_latest_draw(now: datetime, cutoff: time) -> date:
    return now.date() if now.time().replace(tzinfo=None) >= cutoff else now.date() - timedelta(days=1)


def _dates_from_csv(path: Path) -> list[date]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = csv.DictReader(fh)
        return [date.fromisoformat(str(row["date"])[:10]) for row in rows if row.get("date")]


def _prediction_target(path: Path) -> str | None:
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        row = next(csv.DictReader(fh), None)
    if not row:
        return None
    for key in ("predict_for_date", "target_date", "date"):
        if row.get(key):
            return str(row[key])[:10]
    return None


def audit(*, now: datetime | None = None, cutoff: str = "18:15", check_freshness: bool = True) -> dict:
    now = now or datetime.now(TZ)
    cutoff_t = _parse_cutoff(cutoff)
    critical: list[str] = []
    warnings: list[str] = []

    missing = [p for p in REQUIRED_PATHS if not (ROOT / p).is_file() or (ROOT / p).stat().st_size == 0]
    if missing:
        critical.append("missing_or_empty=" + ",".join(missing))

    latest: date | None = None
    dates: list[date] = []
    raw_path = ROOT / "data/xsmb.csv"
    if raw_path.exists():
        try:
            dates = sorted(_dates_from_csv(raw_path))
            latest = dates[-1] if dates else None
        except Exception as exc:
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
        for prev, cur in zip(dates, dates[1:]):
            gap = (cur - prev).days
            if gap > 1:
                missing_days.extend((prev + timedelta(days=i)).isoformat() for i in range(1, gap))
        if missing_days:
            critical.append("canonical_gaps=" + ",".join(missing_days[-10:]))

    if latest:
        try:
            source_audit = json.loads((ROOT / "data/source_audit.json").read_text(encoding="utf-8"))
            item = source_audit.get(latest.isoformat(), {})
            if not item.get("accepted"):
                critical.append(f"source_audit_not_accepted={latest}")
            if int(item.get("agreement", 0)) < 2:
                critical.append(f"source_consensus_lt2={latest}")
        except Exception as exc:
            critical.append(f"source_audit_invalid={exc}")

        target = latest + timedelta(days=1)
        try:
            fun = json.loads((ROOT / "data/predict/fun_draw_next.json").read_text(encoding="utf-8"))
            if fun.get("anchor_date") != latest.isoformat():
                critical.append(f"fun_anchor_mismatch={fun.get('anchor_date')} expected={latest}")
            if fun.get("target_date") != target.isoformat():
                critical.append(f"fun_target_mismatch={fun.get('target_date')} expected={target}")
            if len(fun.get("rows", [])) != 27:
                critical.append("fun_rows_not_27")
            if len(fun.get("top_loto", [])) < 10 or len(fun.get("top_de", [])) < 10:
                critical.append("fun_top10_incomplete")
        except Exception as exc:
            critical.append(f"fun_prediction_invalid={exc}")

        for mode in ("loto", "de"):
            candidates = sorted((ROOT / "data/predict").glob(f"predict_next_{mode}_all_*.csv"))
            if not candidates:
                critical.append(f"predict_{mode}_missing")
                continue
            latest_file = max(candidates, key=lambda p: p.name)
            pred_target = _prediction_target(latest_file)
            if pred_target and pred_target != target.isoformat():
                critical.append(f"predict_{mode}_target={pred_target} expected={target}")

        try:
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            if readme.count("<!-- FUN_PREDICTION:BEGIN -->") != 1 or readme.count("<!-- FUN_PREDICTION:END -->") != 1:
                critical.append("readme_fun_prediction_markers_invalid")
            target_display = target.strftime("%d-%m-%Y")
            if f"Dự đoán vui ngày {target_display}" not in readme:
                critical.append(f"readme_prediction_target_missing={target_display}")
        except Exception as exc:
            critical.append(f"readme_invalid={exc}")

        for page in ("docs/index.html", "docs/landing.html", "docs/landing_desktop.html"):
            p = ROOT / page
            if p.exists():
                text = p.read_text(encoding="utf-8", errors="replace")
                if text.count('id="du-doan-vui"') != 1:
                    critical.append(f"fun_board_marker_invalid={page}")

    try:
        health = json.loads((ROOT / "data/health.json").read_text(encoding="utf-8"))
        if health.get("ok") is False:
            critical.append("health_json_not_ok")
    except Exception as exc:
        critical.append(f"health_json_invalid={exc}")

    return {
        "schema_version": 1,
        "checked_at_local": now.isoformat(),
        "cutoff": cutoff,
        "freshness_checked": check_freshness,
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
    args = ap.parse_args()

    result = audit(cutoff=args.cutoff, check_freshness=not args.consistency_only)
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
