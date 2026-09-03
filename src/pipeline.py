from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, allow_fail: bool = False, timeout_s: int = 900) -> None:
    logging.info("RUN: %s", " ".join(cmd))
    started = time.perf_counter()
    try:
        # Commands are fixed Python argv lists assembled by this module; no
        # untrusted text is interpreted by a shell.
        proc = subprocess.run(  # noqa: S603
            cmd, cwd=ROOT, check=False, timeout=timeout_s
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        message = f"Command timed out after {elapsed:.1f}s: {' '.join(cmd)}"
        if allow_fail:
            logging.warning("%s (non-critical)", message)
            return
        logging.error("%s", message)
        raise SystemExit(124) from exc
    elapsed = time.perf_counter() - started
    if proc.returncode == 0:
        logging.info("OK %.2fs: %s", elapsed, " ".join(cmd))
        return
    if allow_fail:
        logging.warning(
            "Command failed (non-critical): %s (code=%s, %.2fs)",
            " ".join(cmd),
            proc.returncode,
            elapsed,
        )
        return
    raise SystemExit(proc.returncode)


def _py(script: str, *args: str) -> list[str]:
    return [sys.executable, script, *args]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "GitHub pipeline: sync -> validate canonical data -> reference/Excel integrity -> "
            "statistics -> research falsification -> paths -> base ML -> stacked ML -> "
            "calibrated predictions -> dashboards."
        )
    )
    ap.add_argument(
        "--cutoff", default="18:35", help="Daily cutoff HH:MM in Asia/Ho_Chi_Minh."
    )
    ap.add_argument(
        "--window-days", type=int, default=2000, help="History window for ML/path features."
    )
    ap.add_argument(
        "--display-days", type=int, default=10, help="Recent days rendered in dashboard pages."
    )
    ap.add_argument("--lag-max", type=int, default=30)
    ap.add_argument("--top-numbers", type=int, default=30)
    ap.add_argument("--top-paths", type=int, default=200)
    ap.add_argument("--fill-missing-days-back", type=int, default=365)

    ap.add_argument(
        "--skip-sync",
        action="store_true",
        help="Use committed data only; useful for CI/offline checks.",
    )
    ap.add_argument("--skip-path", action="store_true")
    ap.add_argument("--skip-ml", action="store_true")
    ap.add_argument("--skip-docs", action="store_true")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail on core statistics/AI/ML build errors instead of continuing with partial outputs.",
    )

    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    soft_fail = not args.strict

    if not args.skip_sync:
        _run(
            _py(
                "src/sync.py",
                "--cutoff",
                args.cutoff,
                "--fill-missing-days-back",
                str(args.fill_missing_days_back),
            )
        )

    # Canonical data integrity is a hard precondition, even in non-strict mode.
    # Many historical analytics use row-based rolling windows after this gate;
    # allowing a gap here would silently change the meaning of "day" and "t+1".
    _run(
        _py(
            "src/validate_data.py",
            "--lookback-days",
            "90",
            "--out",
            "data/health.json",
        ),
        allow_fail=False,
    )
    _run(
        _py(
            "src/monitor_health.py",
            "--health",
            "data/health.json",
            "--max-staleness-days",
            "2",
        ),
        allow_fail=True,
    )

    # Deterministic number ontology and Excel serialization are hard data
    # contracts. They must be valid before any downstream statistics consume
    # number-family labels or prize workbooks.
    _run(_py("src/export_number_reference.py"), allow_fail=False)
    _run(_py("src/validate_excel_integrity.py"), allow_fail=False)

    for script in [
        "src/analyze.py",
        "src/advanced_stats.py",
        "src/statistical_matrices.py",
        "src/pair_stats.py",
        "src/cycle_stats.py",
        "src/hazard_stats.py",
        "src/markov_stats.py",
        "src/significance_stats.py",
        "src/statistical_signal.py",
        "src/descriptive_extensions.py",
    ]:
        _run(_py(script), allow_fail=soft_fail)

    # Normalize all pair artifacts after both pair_stats and descriptive_ext
    # have regenerated their raw tables. This preserves legacy filenames while
    # making cặp lộn, bóng/bộ relations and statistical co-occurrence explicit.
    _run(_py("src/normalize_pair_artifacts.py"), allow_fail=soft_fail)

    # ``statistical_matrices.py`` still contains historical row-adjacent
    # conditionals and an undated ML overlay loader. Canonical post-processors
    # overwrite both artifact families before any downstream reader sees them.
    _run(_py("src/conditional_matrices.py", "--top", "500"), allow_fail=soft_fail)
    _run(_py("src/statistics_ai_overlay.py"), allow_fail=soft_fail)

    _run(
        _py("src/research_diagnostics.py", "--permutations", "127", "--max-lag", "14"),
        allow_fail=True,
    )
    _run(_py("src/research_legacy_extensions.py"), allow_fail=True)
    _run(
        _py("src/legacy_advanced_diagnostics.py", "--max-lag", "15"),
        allow_fail=True,
    )
    _run(
        _py("src/conditional_nextday.py", "--top", "20", "--prior-strength", "60"),
        allow_fail=True,
    )
    _run(
        _py("src/research_firewall.py", "--mode", "both", "--permutations", "63"),
        allow_fail=True,
        timeout_s=600,
    )
    _run(
        _py("src/strategy_lab.py", "--mode", "both", "--warmup", "180"),
        allow_fail=True,
        timeout_s=600,
    )
    _run(
        _py(
            "src/crosslag_positional_lab.py",
            "--lag-pairs",
            "1-1,1-2",
            "--operators",
            "concat,lon,bo,cham,tong",
            "--warmup",
            "180",
        ),
        allow_fail=True,
        timeout_s=600,
    )

    if not args.skip_path:
        for mode in ["loto", "de"]:
            _run(
                _py(
                    "src/run_path_ui.py",
                    "--mode",
                    mode,
                    "--so-ngay",
                    str(args.display_days),
                    "--lag-max",
                    str(args.lag_max),
                    "--window-days",
                    str(args.window_days),
                    "--top-numbers",
                    str(args.top_numbers),
                    "--top-paths",
                    str(args.top_paths),
                ),
                allow_fail=soft_fail,
            )

    if not args.skip_ml:
        for mode in ["loto", "de"]:
            _run(
                _py(
                    "src/ml_train.py",
                    "--mode",
                    mode,
                    "--window-days",
                    str(args.window_days),
                ),
                allow_fail=soft_fail,
            )

        _run(
            _py(
                "src/ml_predict.py",
                "--cutoff",
                args.cutoff,
                "--window-days",
                str(args.window_days),
            ),
            allow_fail=soft_fail,
        )
        _run(
            _py(
                "src/cau_keo_ml.py",
                "--mode",
                "both",
                "--window-days",
                str(args.window_days),
                "--top",
                "20",
            ),
            allow_fail=soft_fail,
        )
        # Domain challenger is deliberately downstream of the baseline. It may
        # only modify production probabilities after its four chronological OOS
        # gates confirm partner/cặp50/bộ/bóng/chạm/tổng feature skill.
        _run(
            _py(
                "src/cau_keo_domain_challenger.py",
                "--mode",
                "both",
                "--window-days",
                str(args.window_days),
                "--top",
                "20",
            ),
            allow_fail=soft_fail,
            timeout_s=900,
        )
        # In strict production runs the persisted gate, model pack and 100-number
        # prediction table must agree. Inactive challengers must be an exact
        # rollback to baseline probabilities.
        _run(
            _py("src/validate_cau_keo_domain.py"),
            allow_fail=soft_fail,
        )
        _run(
            _py(
                "src/cau_position_evidence.py",
                "--mode",
                "both",
                "--window-days",
                str(args.window_days),
                "--lag-max",
                str(args.lag_max),
                "--top-positions-per-number",
                "8",
            ),
            allow_fail=soft_fail,
        )
        _run(_py("src/path_timeline_evidence.py", "--recent", "20"), allow_fail=True)

        # Rebuild matrices after fresh ML artifacts and canonicalize both the
        # next-day conditionals and the target-date-aware statistics AI overlay.
        _run(_py("src/statistical_matrices.py"), allow_fail=soft_fail)
        _run(_py("src/conditional_matrices.py", "--top", "500"), allow_fail=soft_fail)
        _run(_py("src/statistics_ai_overlay.py"), allow_fail=soft_fail)
        _run(_py("src/record_pred_history.py"), allow_fail=soft_fail)
        _run(_py("src/update_pred_labels.py"), allow_fail=soft_fail)

        for mode in ["loto", "de"]:
            _run(
                _py(
                    "src/learn_ensemble_weights.py",
                    "--mode",
                    mode,
                    "--window-days",
                    "180",
                    "--min-days",
                    "20",
                    "--half-life-days",
                    "45",
                ),
                allow_fail=soft_fail,
            )
            _run(
                _py(
                    "src/meta_predictor.py",
                    "--mode",
                    mode,
                    "--window-days",
                    "240",
                    "--min-days",
                    "100",
                    "--half-life-days",
                    "90",
                ),
                allow_fail=soft_fail,
            )
            _run(
                _py(
                    "src/predict_nextday_2d.py",
                    "--mode",
                    mode,
                    "--top",
                    "10",
                ),
                allow_fail=soft_fail,
            )

    for mode in ["loto", "de"]:
        _run(_py("src/prob_eval_history.py", "--mode", mode), allow_fail=soft_fail)

    if not args.skip_docs:
        _run(
            _py("src/build_docs.py", "--display-days", str(args.display_days)),
            allow_fail=soft_fail,
        )
        _run(_py("src/build_docs_ml.py"), allow_fail=soft_fail)
        _run(_py("src/build_dashboard.py"), allow_fail=soft_fail)
        _run(_py("src/build_markdown_dashboard_v3.py"), allow_fail=soft_fail)
        _run(_py("src/build_statistics_dashboard.py"), allow_fail=soft_fail)
        _run(_py("src/build_landing_page.py"), allow_fail=soft_fail)
        _run(_py("src/build_fun_prediction.py"), allow_fail=soft_fail)
        _run(_py("src/build_research_lab.py"), allow_fail=True)
        _run(_py("src/update_readme.py"), allow_fail=soft_fail)

    _run(
        _py("src/cleanup_artifacts.py", "--retention-days", "45"),
        allow_fail=soft_fail,
    )

    logging.info("DONE")


if __name__ == "__main__":
    main()
