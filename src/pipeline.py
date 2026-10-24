from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time

from core.paths import REPO_ROOT, SRC
from core.time_policy import DEFAULT_DRAW_CUTOFF

ROOT = REPO_ROOT


def _child_env() -> dict[str, str]:
    """Môi trường cho bước con: ``src`` đứng đầu ``PYTHONPATH``.

    Mỗi bước nằm trong một gói con (``src/<gói>/<module>.py``). Chạy bằng đường dẫn
    tệp thì Python chỉ đặt thư mục của CHÍNH tệp ấy lên ``sys.path``, nên import
    ``from core.time_policy import ...`` hỏng nếu thiếu ``src``.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(SRC), env.get("PYTHONPATH", "")) if p)
    return env


def _run(cmd: list[str], *, allow_fail: bool = False, timeout_s: int = 900) -> None:
    logging.info("RUN: %s", " ".join(cmd))
    started = time.perf_counter()
    try:
        # Commands are fixed Python argv lists assembled by this module; no
        # untrusted text is interpreted by a shell.
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

    # Canonical data integrity is a hard precondition, even in non-strict mode.
    # Many historical analytics use row-based rolling windows after this gate;
    # allowing a gap here would silently change the meaning of "day" and "t+1".
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

    # Deterministic number ontology and Excel serialization are hard data
    # contracts. They must be valid before any downstream statistics consume
    # number-family labels or prize workbooks.
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
    ]:
        _run(_py(script), allow_fail=soft_fail)

    # Normalize all pair artifacts after both pair_stats and descriptive_ext
    # have regenerated their raw tables. This preserves legacy filenames while
    # making cặp lộn, bóng/bộ relations and statistical co-occurrence explicit.
    _run(_py("src/stats/normalize_pair_artifacts.py"), allow_fail=soft_fail)

    # ``statistical_matrices.py`` still contains historical row-adjacent
    # conditionals and an undated ML overlay loader. Canonical post-processors
    # overwrite both artifact families before any downstream reader sees them.
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
    # Cầu bóng trên toàn bộ 107 ô chữ số: họ rộng gấp 15,7 lần họ cross-lag,
    # vì nó nối được chữ số nằm bất kỳ đâu bên trong số đầy đủ chứ không chỉ
    # hai chữ số cuối. Quét hết 206 082 giả thuyết mất khoảng 48 giây trên
    # lịch sử 4 207 kỳ (đo 2026-09-16; là 15 giây hồi kho còn 2 401 kỳ).
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
        # Domain challenger is deliberately downstream of the baseline. It may
        # only modify production probabilities after its four chronological OOS
        # gates confirm partner/cặp50/bộ/bóng/chạm/tổng feature skill.
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
        # In strict production runs the persisted gate, model pack and 100-number
        # prediction table must agree. Inactive challengers must be an exact
        # rollback to baseline probabilities.
        _run(
            _py("src/ml/validate_cau_keo_domain.py"),
            allow_fail=soft_fail,
        )
        # Chụp top 10 cầu-kèo theo ngày quay cho trang trực tiếp; phải chạy SAU
        # domain challenger vì nó ghi đè bảng top20.
        _run(_py("src/ml/cau_keo_daily_top.py"), allow_fail=soft_fail)
        # Keep the machine-readable experiment report synchronized with the
        # gate artifacts produced by this same daily run.
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

        # Rebuild matrices after fresh ML artifacts and canonicalize both the
        # next-day conditionals and the target-date-aware statistics AI overlay.
        _run(_py("src/stats/statistical_matrices.py"), allow_fail=soft_fail)
        _run(_py("src/stats/conditional_matrices.py", "--top", "500"), allow_fail=soft_fail)
        _run(_py("src/stats/statistics_ai_overlay.py"), allow_fail=soft_fail)
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

            # Chốt dự báo đầy đủ trước kỳ quay; chỉ học từ dự báo đã lưu. Lỗi sổ
            # phải dừng lượt xuất bản để không đánh mất hoặc chấm lại bằng chứng.
            _run(_py("src/forecast/online_learning.py", "--mode", mode), allow_fail=False)

    for mode in ["loto", "de"]:
        _run(_py("src/evaluation/prob_eval_history.py", "--mode", mode), allow_fail=soft_fail)

    # Log tầm quan trọng đặc trưng chạy SAU khi trọng số và dự đoán đã cập nhật,
    # vì nó đo đóng góp của từng thành phần bằng phép bỏ-một-thành-phần trên
    # chính vector đang có hiệu lực. Module này từng không được gọi ở đâu cả:
    # `data/forecast/feature_attribution/report.json` là ảnh chụp chạy tay một lần, nên
    # nó mô tả một bộ trọng số đã bị thay từ lâu mà không dấu hiệu gì.
    _run(_py("src/forecast/feature_attribution.py"), allow_fail=soft_fail)

    # Mã hiệu là dữ liệu phụ theo kỳ; lỗi nguồn không được chặn kết quả đã xác thực.
    _run(_py("src/web/draw_metadata.py"), allow_fail=True)

    # Chốt độ rộng mã ở biên xuất bản sau khi mọi trình phân tích đã ghi CSV.
    # Cổng cứng: không xuất bản tệp có mã sai miền hoặc mất số 0 đầu.
    _run(_py("src/core/lottery_codes.py"), allow_fail=False)

    # Chẩn đoán và kho tri thức là dữ liệu đầu vào của tác tử, không phải
    # tác dụng phụ của dựng HTML. Kể cả --skip-docs cũng phải truy xuất luật
    # và mức tin của CÙNG lượt chạy, sau chấm dự báo thật và trước snapshot.
    if not args.skip_docs or not args.skip_ml:
        _run(_py("src/evaluation/model_quality.py"), allow_fail=soft_fail)
        _run(_py("src/evaluation/confidence_matrix.py"), allow_fail=soft_fail)
        _run(_py("src/forecast/multi_hit_report.py"), allow_fail=soft_fail)
        _run(_py("src/forecast/knowledge_base.py"), allow_fail=soft_fail)
    if not args.skip_ml:
        # Sổ hỏng phải dừng lượt xuất bản; không đánh mất bằng chứng tiến cứu.
        _run(_py("src/forecast/xsmb_agents/run_xsmb_agents.py"), allow_fail=False)

    if not args.skip_docs:
        _run(
            _py("src/pages/build_docs.py", "--display-days", str(args.display_days)),
            allow_fail=soft_fail,
        )
        _run(_py("src/pages/build_docs_ml.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_dashboard.py"), allow_fail=soft_fail)
        # Chẩn đoán trước, dựng trang sau: trang Chất lượng mô hình đọc thẳng
        # `data/evaluation/model_quality/report.json` nên đảo thứ tự sẽ xuất bản báo cáo
        # của ngày hôm trước mà không có dấu hiệu gì.
        _run(_py("src/pages/build_model_quality.py"), allow_fail=soft_fail)
        # Confidence Score đọc dự báo vừa công bố cho kỳ tới và trạng thái của
        # kỳ vừa quay, nên đứng sau dự báo và sau chẩn đoán. Phân phối null
        # 10 000 lịch sử được lưu sẵn; chỉ tính lại khi số kỳ trôi quá 2%.
        _run(_py("src/pages/build_confidence_page.py"), allow_fail=soft_fail)
        # Lô VIP nhiều nháy: khung thách đấu, không vào tổ hợp. Bộ lọc đo lại
        # mỗi ngày (~25 s); lượt hai là phép kiểm một lần, đóng băng ở
        # SECOND_ROUND_UNTIL, chỉ đo lại khi đoạn lịch sử ấy bị sửa.
        _run(_py("src/pages/build_multi_hit_page.py"), allow_fail=soft_fail)
        # Kho tri thức: luật tự khai phá (chỉ chấm tiến cứu), bộ nhớ ngữ cảnh và lời giải thích
        # top-10. Đọc sổ tự học, báo cáo Confidence và số đo Lô VIP của CÙNG lượt chạy, nên đứng sau
        # cả ba. Khung thách đấu: không đổi tổ hợp xác suất.
        # Soi cầu vị trí đọc kỳ vừa quay; phải có TRƯỚC trang chủ vì ô "cầu đẹp
        # nhất" nằm cạnh bảng LOTO của khung kết quả hằng ngày.
        _run(_py("src/soi_cau/position_bridges.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_position_bridges.py"), allow_fail=soft_fail)
        # Bảy kiểu cầu vị trí và công cụ phôi tuần: cùng dữ liệu vừa chốt.
        _run(_py("src/soi_cau/bridge_rules.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_bridge_pages.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_markdown_dashboard_v3.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_statistics_dashboard.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_landing_page.py"), allow_fail=soft_fail)
        # This is a user-visible, date-bound snapshot.  Swallowing a builder
        # error here leaves yesterday's simulation in place and makes the UI
        # appear frozen, so it is a hard step even in non-strict research runs.
        _run(_py("src/pages/build_fun_prediction.py"), allow_fail=False)
        # Sổ phỏng đoán trong ngày: chụp MỌI danh sách vừa công bố cho kỳ tới để trang Live
        # đặt cạnh kết quả đang về. Đọc bảng mô phỏng, cầu đẹp nhất và bảy trang soi cầu nên
        # đứng sau chúng; khoá 18:10 giờ VN của kỳ đích, sau đó sổ đóng băng.
        _run(_py("src/evaluation/prediction_board.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_research_lab.py"), allow_fail=True)
        # Trang thống kê chi tiết: nhúng lịch sử và tính bằng JS phía
        # trình duyệt, nên phải chạy SAU khi dữ liệu đã chốt.
        _run(_py("src/pages/build_stat_pages.py"), allow_fail=soft_fail)
        _run(_py("src/pages/build_traditional_results.py"), allow_fail=soft_fail)
        _run(_py("src/pages/update_readme.py"), allow_fail=soft_fail)

    _run(
        _py("src/evaluation/cleanup_artifacts.py", "--retention-days", "45"),
        allow_fail=soft_fail,
    )

    if not args.skip_docs:
        # Chốt mọi URL sau trình dựng cuối: không cho xuất bản tham chiếu cũ/thiếu.
        _run(_py("src/web/site_assets.py", "--refresh", "docs", "--check"), allow_fail=False)

    logging.info("DONE")


if __name__ == "__main__":
    main()
