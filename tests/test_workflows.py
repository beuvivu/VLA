from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def _vietnam_minutes(cron: str) -> int:
    """Phút trong ngày theo giờ Việt Nam của một biểu thức cron viết theo UTC."""
    minute, hour = cron.split()[:2]
    return ((int(hour) + 7) % 24) * 60 + int(minute)


def test_live_workflow_uses_utc_schedule_and_subminute_poll_loop() -> None:
    text = _text("live-results.yml")
    crons = re.findall(r'cron: "([^"]+)"', text)
    # Kiểm tính chất thay vì chuỗi cố định: phải có mốc đủ sớm để, kể cả khi
    # GitHub trễ như đã đo (2,5–4,5 giờ), vẫn còn cơ hội rơi vào khung quay.
    assert crons, "workflow live phải có ít nhất một mốc lịch"
    assert min(_vietnam_minutes(c) for c in crons) <= 14 * 60
    assert max(_vietnam_minutes(c) for c in crons) <= 18 * 60 + 15
    assert 'POLL_SECONDS: "15"' in text
    assert 'MAX_SECONDS: "3600"' in text
    assert "refs/heads/live" in text
    assert "complete_verified" in text
    assert "actions: write" in text
    assert "actions/workflows/update-data.yml/dispatches" in text
    assert "cancel-in-progress: false" in text


def test_daily_workflow_has_primary_and_recovery_finalization_times() -> None:
    text = _text("update-data.yml")
    # Kiểm tính chất chứ không kiểm chuỗi cố định: cần đủ nhiều mốc phục hồi
    # trải sau giờ quay, và không mốc nào rơi vào phút :00 hay :30 — hàng đợi
    # lịch của GitHub dồn nặng nhất ở hai mốc đó.
    crons = re.findall(r'cron: "([^"]+)"', text)
    assert len(crons) >= 9
    minutes = [_vietnam_minutes(c) for c in crons]
    assert min(minutes) >= 18 * 60 + 30, "mốc đầu phải sau giờ quay 18:30"
    assert max(minutes) >= 20 * 60, "cần mốc phục hồi muộn"
    assert not [c for c in crons if int(c.split()[0]) in (0, 30)]
    assert "--cutoff 18:35" in text
    assert '"--consensus-min-recent", "2"' in text
    assert "Ghi nhận kết quả chuẩn ngay lập tức" in text
    assert "--fail-on-stale" in text
    assert "--fail-on-missing" in text
    assert "--cutoff-aware" in text
    assert "push:" in text
    assert '"reason": "live_verified"' in _text("live-results.yml")


def test_watchdog_and_post_finalization_use_utc7_cutoff_and_recovery() -> None:
    watchdog = _text("watchdog.yml")
    for cron in ("55 10", "5 11", "15 11", "25 11", "45 11", "5 12", "25 12", "45 12", "5 13"):
        assert f'cron: "{cron} * * *"' in watchdog
    assert '"18:35"' in watchdog
    assert '"reason": "watchdog_recovery"' in watchdog
    assert "--cutoff 18:35" in _text("post-finalization.yml")


def test_dashboard_refresh_checks_vietnamese_contract() -> None:
    text = _text("dashboard-refresh.yml")
    for marker in ("lịch 7 cột", "Độ nâng so với nền", "Kiểm toán và liên kết chi tiết"):
        assert marker in text
    assert "Lift vs baseline" not in text


def test_daily_workflow_scopes_privileged_permissions_to_the_jobs_that_need_them() -> None:
    text = _text("update-data.yml")
    top, jobs = text.split("jobs:\n", 1)
    update, rest = jobs.split("  trigger-post-finalization:\n", 1)
    trigger, deploy = rest.split("  deploy-pages:\n", 1)

    assert "permissions:\n  contents: read" in top
    assert "    permissions:\n      contents: write" in update
    assert "    permissions:\n      actions: write\n      contents: read" in trigger
    assert (
        "    permissions:\n      contents: read\n      id-token: write\n      pages: write"
    ) in deploy


def test_pages_use_official_actions_deployment_flow() -> None:
    page = _text("pages.yml")
    daily = _text("update-data.yml")
    for text in (page, daily):
        assert "actions/configure-pages@v6" in text
        assert "actions/upload-pages-artifact@v5" in text
        assert "actions/deploy-pages@v5" in text


def test_production_refreshes_do_not_restore_package_caches() -> None:
    # Live/daily jobs must not restore an old runner cache while repairing a
    # stale data snapshot.  CI may retain its dependency cache for speed.
    for name in ("ci.yml", "live-results.yml", "update-data.yml", "dashboard-refresh.yml"):
        text = _text(name)
        assert "cache:" not in text
        assert "--no-cache-dir" in text


def test_cache_purge_is_explicit_and_not_scheduled() -> None:
    text = _text("cache-purge.yml")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "actions: write" in text
    assert "scripts/purge_github_caches.py --confirm" in text


# --- Thu thập đúng giờ ------------------------------------------------------


def test_daily_update_prefers_dispatch_over_schedule() -> None:
    """Lịch của GitHub trễ 2-6 giờ và rơi mốc trên kho này; đường đúng giờ
    phải là repository_dispatch, cron chỉ là lưới an toàn."""
    text = _text("daily_update.yml")
    assert "repository_dispatch:" in text
    assert "types: [daily-collect]" in text
    crons = re.findall(r'cron: "([^"]+)"', text)
    assert len(crons) <= 8, "quá nhiều mốc chỉ tăng số lần chạy thừa"


def test_cron_slots_sit_early_enough_for_the_measured_scheduler_delay() -> None:
    """Mốc cron phải đặt theo ĐỘ TRỄ ĐO ĐƯỢC, không theo giờ mong muốn.

    Đo trên 62 lần chạy theo lịch của kho này: trễ tối thiểu 49 phút, trung vị
    144, tối đa 305. Lịch cũ đặt mốc sớm nhất ở 11:08 UTC (18:08 giờ VN) —
    cộng 49 phút thì không đời nào chạy trước 18:57, tức lịch tự đặt trần cho
    chính nó. Kỳ về sớm nhất quan sát được là 19:38, khớp đúng.

    Mốc chính phải sớm hơn khung quay 11:15 UTC ít nhất bằng độ trễ TRUNG VỊ,
    để ở ngày trung bình nó rơi đúng khung.
    """
    text = _text("daily_update.yml")
    crons = re.findall(r'cron: "([^"]+)"', text)
    minutes = sorted(int(c.split()[1]) * 60 + int(c.split()[0]) for c in crons)

    window = 11 * 60 + 15          # 18:15 giờ VN
    median_delay = 144             # phút, đo được

    assert minutes[0] <= window - median_delay, (
        f"mốc sớm nhất {minutes[0] // 60:02d}:{minutes[0] % 60:02d} UTC quá muộn; "
        f"phải <= {(window - median_delay) // 60:02d}:{(window - median_delay) % 60:02d} "
        "để ở độ trễ trung vị còn rơi đúng khung"
    )


def test_early_arrivals_exit_instead_of_idling_the_runner() -> None:
    """Bộ thăm dò chờ tới khung quay KHÔNG giới hạn, nên một job nổ lúc 15:39
    sẽ nằm im 2h36m rồi chết vì timeout — đúng những gì lịch cũ vẫn làm. Phải
    có trần chờ, và timeout phải đủ chứa trần đó cộng cả khung thăm dò."""
    text = _text("daily_update.yml")
    found = re.search(r'MAX_WAIT_MINUTES:\s*"(\d+)"', text)
    assert found is not None, "thiếu trần chờ MAX_WAIT_MINUTES cho job đến quá sớm"

    cap = int(found.group(1))
    timeout = int(re.search(r"timeout-minutes:\s*(\d+)", text).group(1))
    poll_window = 75  # 18:15 -> 19:30

    assert timeout >= cap + poll_window, (
        f"timeout {timeout} phút không đủ cho trần chờ {cap} cộng khung thăm dò "
        f"{poll_window}; job sẽ bị giết giữa chừng"
    )


def test_gate_skips_when_todays_draw_is_already_stored() -> None:
    """Mốc sau không được thăm dò lại kỳ mà mốc trước đã lấy xong: vừa tốn yêu
    cầu vào nguồn tin, vừa giữ runner suốt cả khung."""
    text = _text("daily_update.yml")
    assert "data/xsmb.csv" in text
    assert "run=false" in text
    assert "steps.gate.outputs.run == 'true'" in text


def test_last_backstop_guard_matches_the_actual_last_cron() -> None:
    """Chốt chặn silent fail so chuỗi cron đã kích hoạt với một hằng số chép
    tay. Đổi lịch mà quên sửa hằng số thì chốt im lặng ngừng hoạt động — đúng
    kiểu hỏng mà không ai phát hiện."""
    text = _text("daily_update.yml")
    crons = re.findall(r'cron: "([^"]+)"', text)
    guard = re.search(r'LAST_CRON:\s*"([^"]+)"', text)
    assert guard, "thiếu hằng số LAST_CRON"
    assert guard.group(1) == crons[-1], (
        f"LAST_CRON={guard.group(1)!r} không khớp mốc cuối {crons[-1]!r}"
    )


def test_missing_data_at_the_last_backstop_fails_the_job() -> None:
    """Job xanh trong khi không lấy được số nào chính là silent fail: không ai
    biết dữ liệu hỏng cho tới khi tự mở trang ra xem."""
    text = _text("daily_update.yml")
    assert "::error::" in text
    assert re.search(r'FIRED_CRON.*=.*LAST_CRON|"\$FIRED_CRON"\s*=\s*"\$LAST_CRON"', text)
    assert "exit 1" in text


def test_daily_update_sets_the_timezone_at_job_level() -> None:
    """Đặt lẻ ở từng bước là cách sinh ra lỗi lệch 7 tiếng mà nhật ký không
    bao giờ chỉ ra được."""
    text = _text("daily_update.yml")
    assert "TZ: Asia/Ho_Chi_Minh" in text


def test_daily_update_bounds_the_runner() -> None:
    text = _text("daily_update.yml")
    assert re.search(r"timeout-minutes:\s*\d+", text)


def test_every_dock_page_builder_runs_in_the_release_chain() -> None:
    """Trang mang dock mà không có trình dựng nào chạy lại sẽ thành hiện vật
    chết: đổi SITE_NAV một lần là nó lệch khỏi phần còn lại và không ai dựng
    lại được ngoài việc gọi tay.

    Bốn trang soi-path đã ở tình trạng đó — build_docs.py không nằm trong
    chuỗi phát hành, nên thêm một mục điều hướng là test dock đỏ mà không có
    cách sửa nào ngoài chạy tay đúng trình dựng.
    """
    chain = (
        Path(__file__).resolve().parents[1] / "scripts" / "release_check.sh"
    ).read_text(encoding="utf-8")

    builders = [
        "build_docs.py",
        "build_docs_ml.py",
        "build_dashboard.py",
        "build_statistics_dashboard.py",
        "build_landing_page.py",
        "build_fun_prediction.py",
    ]
    # So theo DÒNG, không theo chuỗi con: "#python src/x.py" vẫn chứa
    # "python src/x.py", nên phép kiểm chuỗi con sẽ xanh cả khi dòng bị chú
    # thích ra — tức là chốt chặn im lặng ngừng hoạt động.
    lines = {line.strip() for line in chain.splitlines()}
    for name in builders:
        assert f"python src/{name}" in lines, f"{name} không nằm trong chuỗi phát hành"

    # Thứ tự quan trọng: build_docs và build_docs_ml cùng ghi docs/index.html,
    # và bản của build_landing_page mới là bản đúng.
    assert chain.index("python src/build_docs.py") < chain.index(
        "python src/build_landing_page.py"
    ), "build_docs phải chạy trước build_landing_page, nếu không index.html bị ghi đè sai"
