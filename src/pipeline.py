from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time

from core.paths import REPO_ROOT, SRC
from core.atomic_io import (
    keep_committed_tables_when_only_noise_changed,
    keep_committed_when_only_stamps_changed,
)
from core.time_policy import DEFAULT_DRAW_CUTOFF
from web.page_output import keep_committed_pages_when_only_stamps_changed

ROOT = REPO_ROOT


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(SRC), env.get("PYTHONPATH", "")) if p)
    return env


def _keep_committed_when_unchanged() -> None:
    try:
        restored = (keep_committed_when_only_stamps_changed(ROOT) + keep_committed_tables_when_only_noise_changed(ROOT)
                    + keep_committed_pages_when_only_stamps_changed(ROOT))
    except Exception as exc:  # noqa: BLE001 - giữ sạch commit là việc phụ, không phải cổng
        logging.warning("Không so được dấu giờ và nhiễu số thực với bản đã commit: %s", exc)
        return
    if restored:
        logging.info("Giữ bản đã commit của %d tệp chỉ đổi dấu giờ hay nhiễu số thực: %s",
                     len(restored), ", ".join(restored))


def _run(cmd: list[str], *, allow_fail: bool = False, timeout_s: int = 900) -> None:
    logging.info("RUN: %s", " ".join(cmd))
    started = time.perf_counter()
    try:
        proc = subprocess.run(  # noqa: S603
            cmd, cwd=ROOT, env=_child_env(), check=False, timeout=timeout_s
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
        _keep_committed_when_unchanged()
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
        "--cutoff",
        default=DEFAULT_DRAW_CUTOFF.strftime("%H:%M"),
        help="Giờ Việt Nam hoàn tất kỳ quay (HH:MM; mặc định UTC+7).",
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
                "src/ingest/sync.py",
                "--cutoff",
                args.cutoff,
                "--fill-missing-days-back",
                str(args.fill_missing_days_back),
            )
        )

    _run(
        _py(
            "src/ingest/validate_data.py",
            "--lookback-days",
            "90",
            "--out",
            "data/health.json",
        ),
        allow_fail=False,
    )
    _run(
        _py(
            "src/evaluation/monitor_health.py",
            "--health",
            "data/health.json",
            "--max-staleness-days",
            "2",
        ),
        allow_fail=True,
    )

    _run(_py("src/stats/export_number_reference.py"), allow_fail=False)
    _run(_py("src/ingest/validate_excel_integrity.py"), allow_fail=False)

    for script in [
        "src/stats/analyze.py",
        "src/stats/advanced_stats.py",
        "src/stats/statistical_matrices.py",
        "src/stats/pair_stats.py",
        "src/stats/cycle_stats.py",
        "src/stats/hazard_stats.py",
        "src/stats/markov_stats.py",
        "src/stats/significance_stats.py",
        "src/stats/statistical_signal.py",
        "src/stats/descriptive_extensions.py",
        "src/stats/xsmb_venue_effects.py",
        "src/forecast/cage_bayes.py",
    ]:
        _run(_py(script), allow_fail=soft_fail)

    _run(_py("src/stats/normalize_pair_artifacts.py"), allow_fail=soft_fail)

    _run(_py("src/stats/conditional_matrices.py", "--top", "500"), allow_fail=soft_fail)
    _run(_py("src/stats/statistics_ai_overlay.py"), allow_fail=soft_fail)

    _run(
        _py("src/research/research_diagnostics.py", "--permutations", "127", "--max-lag", "14"),
        allow_fail=True,
    )
    _run(_py("src/research/research_legacy_extensions.py"), allow_fail=True)
    _run(
        _py("src/research/legacy_advanced_diagnostics.py", "--max-lag", "15"),
        allow_fail=True,
    )
    _run(
        _py("src/research/conditional_nextday.py", "--top", "20", "--prior-strength", "60"),
        allow_fail=True,
    )
    _run(
        _py("src/research/research_firewall.py", "--mode", "both", "--permutations", "63"),
        allow_fail=True,
        timeout_s=600,
    )
    _run(
        _py("src/research/strategy_lab.py", "--mode", "both", "--warmup", "180"),
        allow_fail=True,
        timeout_s=600,
    )
    _run(
        _py(
            "src/research/crosslag_positional_lab.py",
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
    _run(
        _py("src/research/bong_bridge_lab.py", "--permutations", "60", "--top", "50"),
        allow_fail=True,
        timeout_s=600,
    )

    if not args.skip_path:
        for mode in ["loto", "de"]:
            _run(
                _py(
                    "src/soi_cau/run_path_ui.py",
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
                    "src/ml/ml_train.py",
                    "--mode",
                    mode,
                    "--window-days",
                    str(args.window_days),
                ),
                allow_fail=soft_fail,
            )

        _run(
            _py(
                "src/ml/ml_predict.py",
                "--cutoff",
                args.cutoff,
                "--window-days",
                str(args.window_days),
            ),
            allow_fail=soft_fail,
        )
        _run(
            _py(
                "src/ml/cau_keo_ml.py",
                "--mode",
                "both",
                "--window-days",
                str(args.window_days),
                "--top",
                "20",
            ),
            allow_fail=soft_fail,
        )
        _run(
            _py(
                "src/ml/cau_keo_domain_challenger.py",
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
        _run(
            _py("src/ml/validate_cau_keo_domain.py"),
            allow_fail=soft_fail,
        )
        _run(_py("src/ml/cau_keo_daily_top.py"), allow_fail=soft_fail)
        _run(
            _py("src/pages/build_domain_experiment_report.py"),
            allow_fail=soft_fail,
        )
        _run(
            _py(
                "src/soi_cau/cau_position_evidence.py",
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
        _run(_py("src/soi_cau/path_timeline_evidence.py", "--recent", "20"), allow_fail=True)

        _run(_py("src/stats/statistical_matrices.py"), allow_fail=soft_fail)
        _run(_py("src/stats/conditional_matrices.py", "--top", "500"), allow_fail=soft_fail)
        _run(_py("src/stats/statistics_ai_overlay.py"), allow_fail=soft_fail)
        _run(_py("src/stats/cap_loto_50_stats.py"), allow_fail=soft_fail)
        _run(_py("src/evaluation/record_pred_history.py"), allow_fail=soft_fail)
        _run(_py("src/evaluation/update_pred_labels.py"), allow_fail=soft_fail)

        for mode in ["loto", "de"]:
            _run(
                _py(
                    "src/ensemble/learn_ensemble_weights.py",
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
                    "src/forecast/meta_predictor.py",
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
                    "src/forecast/predict_nextday_2d.py",
                    "--mode",
                    mode,
                    "--top",
                    "10",
                ),
                allow_fail=soft_fail,
            )

            _run(_py("src/forecast/online_learning.py", "--mode", mode), allow_fail=False)

    for mode in ["loto", "de"]:
        _run(_py("src/evaluation/prob_eval_history.py", "--mode", mode), allow_fail=soft_fail)

    _run(_py("src/forecast/feature_attribution.py"), allow_fail=soft_fail)

    _run(_py("src/web/draw_metadata.py"), allow_fail=True)

    _run(_py("src/core/lottery_codes.py"), allow_fail=False)

    _run(
        _py("src/evaluation/cleanup_artifacts.py", "--retention-days", "45"),
        allow_fail=soft_fail,
    )

    if not args.skip_docs or not args.skip_ml:
        _run(_py("src/evaluation/model_quality.py"), allow_fail=soft_fail)
        _run(_py("src/evaluation/confidence_matrix.py"), allow_fail=soft_fail)
        _run(_py("src/forecast/multi_hit_report.py"), allow_fail=soft_fail)
        _run(_py("src/forecast/knowledge_base.py"), allow_fail=soft_fail)
    if not args.skip_ml:
        _run(_py("src/forecast/xsmb_agents/run_xsmb_agents.py"), allow_fail=False)
        _run(
            _py("src/evaluation/model_registry.py", *(["--strict"] if args.strict else [])),
            allow_fail=soft_fail,
        )

    if not args.skip_docs:
        _run(
            _py("src/pages/build_docs.py", "--display-days", str(args.display_days)),
            allow_fail=soft_fail,
        )
        _run(_py("src/pages/build_docs_ml.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_dashboard.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_model_quality.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_confidence_page.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_multi_hit_page.py"), allow_fail=soft_fail)
        _run(_py("src/soi_cau/position_bridges.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_position_bridges.py"), allow_fail=soft_fail)
        _run(_py("src/soi_cau/bridge_rules.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_bridge_pages.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_statistics_dashboard.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_landing_page.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_fun_prediction.py"), allow_fail=False)
        _run(_py("src/pages/build_markdown_dashboard_v3.py"), allow_fail=soft_fail)
        _run(_py("src/evaluation/prediction_board.py"), allow_fail=soft_fail)
        _run(_py("src/evaluation/board_record.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_research_lab.py"), allow_fail=True)
        _run(_py("src/pages/build_stat_pages.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_traditional_results.py"), allow_fail=soft_fail)
        _run(_py("src/pages/update_readme.py"), allow_fail=soft_fail)

    if not args.skip_docs:
        _run(_py("src/web/site_assets.py", "--refresh", "docs", "--check"), allow_fail=False)

    logging.info("DONE")


if __name__ == "__main__":
    main()
