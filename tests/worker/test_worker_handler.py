from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "worker" / "test" / "run_handler.mjs"

def _primary_round_fetches() -> int:
    from datetime import date

    from ingest.sources import primary_sources

    return sum(len(s.live_urls(date(2026, 9, 5))) for s in primary_sources())


SOURCES_PER_COLLECTION = _primary_round_fetches()

PRIMARY_SOURCE_ROWS = 1
ALL_SOURCE_ROWS = 3


def _require_node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError(
                "CI phải có node để chạy phép kiểm handler của Worker; "
                "xem bước 'Thiết lập Node' trong .github/workflows/ci.yml"
            )
        pytest.skip("không có node trên máy chạy kiểm")
    return node


def _scenario(name: str) -> dict:
    proc = subprocess.run(
        [_require_node(), str(RUNNER), name],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert proc.returncode == 0, f"kịch bản {name} hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


@pytest.mark.parametrize("kv_state", ["kv_empty", "kv_put_drops"])
def test_viewer_requests_never_call_the_sources(kv_state: str) -> None:
    out = _scenario("requests_never_collect")
    assert out["outbound_fetches"] == 0, (
        f"lượt yêu cầu đã gọi nguồn {out['outbound_fetches']} lần; chỉ cron được gọi"
    )
    assert out[kv_state]["statuses"] == [503], "KV rỗng phải báo lỗi để trang đọc nguồn kế tiếp"
    assert out[kv_state]["cors"] == ["*"], "thiếu CORS thì trình duyệt chỉ thấy lỗi mạng"
    assert out[kv_state]["body_status"] == "waiting"


def test_the_live_page_treats_a_non_ok_worker_reply_as_a_reason_to_fall_back() -> None:
    page = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    block = page.split("async function fetchSnapshot()")[1].split("throw lastError")[0]
    assert "if (!response.ok) throw" in block


def test_the_scheduled_run_writes_once_and_reads_come_from_storage() -> None:
    out = _scenario("normal")
    assert out["outbound_on_cron"] == SOURCES_PER_COLLECTION
    assert out["outbound_after_read"] == SOURCES_PER_COLLECTION, (
        "lượt đọc sau khi cron đã ghi không được gọi nguồn lần nữa"
    )
    assert out["schema_version"] == 2, "phải khớp lược đồ bản Python"
    assert out["source_count"] == PRIMARY_SOURCE_ROWS, (
        "nguồn chính dùng được thì không được chạm tới nguồn dự phòng"
    )
    assert out["special"] == ["83772"], "dữ liệu phải đi hết đường từ HTML tới payload"
    assert out["cors"] == "*", "trang live ở tên miền khác nên bắt buộc có CORS"
    assert "max-age" in out["cache_control"]
    assert out["health_ok"] and out["health_has_snapshot"]


def test_every_source_failing_still_publishes_a_waiting_snapshot() -> None:
    out = _scenario("all_sources_down")
    assert out["scheduled_threw"] is False, "một lượt cron hỏng không được đổ lượt sau"
    assert out["wrote_snapshot"] is True
    assert out["status"] == "waiting"
    assert out["fallback_activated"] is True, (
        "nguồn chính hỏng thì PHẢI kích hoạt dự phòng"
    )
    assert out["source_rows"] == ALL_SOURCE_ROWS
    assert out["errors"] == ALL_SOURCE_ROWS, "phải ghi lỗi của TỪNG nguồn"


def test_a_primary_stuck_after_the_deadline_hands_over_to_the_fallbacks() -> None:
    out = _scenario("primary_stuck_after_deadline")
    assert out["fallback_activated"] is True
    assert out["source_rows"] == ALL_SOURCE_ROWS
    assert out["status"] == "complete_verified", "hai dự phòng khớp nhau trọn kỳ"
    assert out["prize1"] == ["68785"], "giá trị phải đến từ dự phòng"
    assert out["prize7"] == ["66", "21", "34", "78"]
    assert out["hosts"] == ["mketqua.net", "www.minhngoc.net.vn", "xoso.com.vn"]
    assert out["supporters"] == ["F1", "F2"], "nguồn chính đã hỏng không được cầm phiếu ở ô nào"


def test_a_page_still_showing_yesterday_is_not_todays_result() -> None:
    out = _scenario("stale_page_is_not_today")
    assert out["draw_date"] == "2026-10-13"
    assert out["status"] == "waiting"
    assert out["received_values"] == 0
    assert out["fallback_activated"] is True, "nguồn chính còn hiện kỳ trước là sự cố"
    assert out["failed_rows"] == ALL_SOURCE_ROWS
    assert out["later_statuses"] == ["waiting"] * 3, (
        "lượt cron đầu đã ghi đè ảnh chụp hôm qua; các lượt sau vẫn phải nhận ra trang cũ"
    )


def test_a_cold_start_takes_the_previous_draw_from_canonical_history() -> None:
    out = _scenario("cold_start_seeds_from_canonical_history")
    assert out["statuses"] == ["waiting"] * 3


def test_the_newest_known_draw_wins_when_canonical_history_lags() -> None:
    assert _scenario("canonical_lags_behind_the_kv_snapshot")["status"] == "waiting"


def test_with_nothing_to_compare_a_complete_board_is_not_settled() -> None:
    out = _scenario("cold_start_without_history_does_not_settle")
    assert out["status"] == "complete_provisional"
    assert out["verified_complete"] is False
    assert out["outbound_after_second"] > out["outbound_after_first"], (
        "chưa chốt thì lượt cron sau phải thu thập tiếp"
    )


def test_a_missing_kv_binding_says_exactly_what_to_do() -> None:
    message = _scenario("missing_kv")["message"]
    assert message is not None, "thiếu KV phải nổ, không được lặng lẽ chạy tiếp"
    assert "wrangler kv namespace create LIVE" in message
    assert "live-worker.md" in message


def test_a_settled_draw_stops_the_cron_from_calling_sources_again() -> None:
    out = _scenario("settled_stops_collecting")
    assert out["status"] == "complete_verified"
    assert out["outbound_after_first_cron"] == PRIMARY_SOURCE_ROWS
    assert out["outbound_after_six_crons"] == PRIMARY_SOURCE_ROWS, (
        "năm lượt cron sau khi đã xác minh không được gọi nguồn lần nào nữa"
    )
    assert out["outbound_after_stale_date"] == PRIMARY_SOURCE_ROWS * 2, (
        "ảnh chụp của NGÀY KHÁC phải cho thu thập lại, không được chặn"
    )


def test_routing_and_methods() -> None:
    out = _scenario("routing")
    assert out["unknown_path"] == 404
    assert out["post"] == 405, "chỉ đọc, không nhận ghi"
    assert out["options"] == 204, "preflight CORS phải qua"


def test_a_kv_that_cannot_write_does_not_break_the_cron_or_the_reply() -> None:
    out = _scenario("kv_put_throws")
    assert out["cron_rejected"] is False, "một lượt cron hỏng không được đổ lượt sau"
    assert out["outbound_on_cron"] == SOURCES_PER_COLLECTION
    assert out["statuses"] == [503]
    assert out["cors"] == ["*"]
    assert out["outbound_after_reads"] == SOURCES_PER_COLLECTION


def test_health_survives_a_corrupt_stored_snapshot() -> None:
    assert _scenario("health_corrupt_kv") == {"status": 200, "has_snapshot": False}
