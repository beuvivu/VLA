"""Hợp đồng API Sổ kết quả: lịch sử chuẩn trước, nguồn dự phòng chỉ bù ngày thiếu.

Từ 08-10-2026 nguồn dự phòng CHỈ được gọi từ cron (``refreshFallbackOverlay``); yêu cầu của khách
chỉ đọc lớp bù đã lưu. Một khoá KV không chặn được khuếch đại giữa các isolate (KV nhất quán sau,
không có đọc-ghi nguyên tử), nên lưu lượng khách phải không còn đường nào chạm tới nguồn ngoài.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "worker" / "test" / "run_traditional_results.mjs"


def _node() -> str:
    executable = shutil.which("node")
    if executable is None:
        if os.environ.get("CI"):
            raise AssertionError("CI phải có Node để kiểm hợp đồng API Sổ kết quả")
        pytest.skip("không có Node trên máy chạy kiểm")
    return executable


def _scenario(name: str) -> dict:
    proc = subprocess.run(
        [_node(), str(RUNNER), name],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_internal_vla_database_is_used_without_calling_xskt() -> None:
    result = _scenario("primary_first")
    assert result["counter"] == {"primary": 1, "xskt": 0}
    assert result["count"] == 1
    assert result["source"] == "canonical"
    assert result["special"] == "58851"
    assert result["leading_zero"] == "01"
    assert result["head_tail_total"] == 27


def test_the_cron_fills_the_missing_date_and_requests_only_read_it() -> None:
    result = _scenario("cron_fills_then_requests_read")
    assert result["refreshed"] is True
    assert result["xskt_on_cron"] == 1
    assert result["statuses"] == [200, 200]
    assert result["counter"] == {"primary": 1, "xskt": 1}, "hai yêu cầu không được gọi thêm nguồn nào"
    assert result["dates"] == ["2026-09-13", "2026-09-12"]
    assert result["sources"] == ["fallback", "canonical"]
    assert result["fallback_requested"] is True
    assert result["fallback_network_fetch"] is False
    assert result["second_cache"] == "hit"
    assert result["xskt_special"] == "83799"


def test_xskt_outage_does_not_hide_available_vla_results() -> None:
    result = _scenario("fallback_outage_keeps_primary")
    assert result["refresh_error"] == "upstream timeout"
    assert result["counter"] == {"primary": 1, "xskt": 1}
    assert result["dates"] == ["2026-09-12"]
    assert result["unresolved"] == ["2026-09-13"]
    assert result["warning"] == "Một số ngày chưa có trong lịch sử chuẩn; lượt cập nhật theo lịch sẽ bù."


def test_api_rejects_unsupported_or_unsafe_ranges() -> None:
    assert _scenario("validation") == {
        "unsupported": 400,
        "invalid_days": 400,
        "missing_to": 400,
        "too_long": 400,
    }


def test_api_cors_preflight_allows_the_static_page() -> None:
    assert _scenario("cors_preflight") == {
        "status": 204,
        "origin": "*",
        "methods": "GET, OPTIONS",
        "max_age": "86400",
    }


def test_xskt_parser_and_vietnam_cutoff_policy() -> None:
    result = _scenario("parser_and_preset")
    assert result["dates"] == ["2026-09-13"]
    assert result["fields"] == 8
    assert result["from"] == "2026-08-14"
    assert result["to"] == "2026-09-12"
    assert result["timezone"] == "Asia/Ho_Chi_Minh"


def test_changing_the_date_range_cannot_amplify_calls_to_the_fallback_source() -> None:
    """Mỗi khoảng ngày là một khoá đệm mới; trước đây 20 khoảng kéo 20 lượt tải trang nguồn."""
    result = _scenario("amplification")
    assert result["statuses"] == [200]
    assert result["counter"] == {"primary": 1, "xskt": 0}


def test_the_cron_refresh_is_spaced_ten_minutes_apart() -> None:
    """Ngày 13-09 vẫn thiếu ở các lượt cron phút 0, 5, 9, 11, 15, 22: chỉ phút 0, 11, 22 tải."""
    assert _scenario("cron_refresh_is_spaced")["xskt_after_each"] == [1, 1, 1, 2, 2, 3]


def test_days_the_source_never_had_are_not_fetched_again() -> None:
    """XSMB nghỉ quay dịp Tết: ngày ấy thiếu mãi trong lịch sử chuẩn. Không ghi nhớ thì lượt cron
    nào cũng thấy "thiếu" và tải lại trọn trang 500 ngày."""
    result = _scenario("days_the_source_never_had_are_remembered")
    assert result["first"] == {"fetched": True, "missing": 2, "filled": 1, "absent": 1}
    assert result["second"] == {"fetched": False, "missing": 0}
    assert result["xskt"] == 1
    assert result["dates"] == ["2026-09-13", "2026-09-12", "2026-09-10"]
    assert result["unresolved"] == []


def test_the_cron_refresh_needs_the_wrangler_switch() -> None:
    assert _scenario("scheduled_refresh_needs_the_switch") == {"on": 1, "off": 0}
    toml = (ROOT / "worker" / "wrangler.toml").read_text(encoding="utf-8")
    assert 'TRADITIONAL_FALLBACK_REFRESH = "on"' in toml, "bản triển khai phải bật lớp bù theo lịch"


def test_a_range_ending_after_the_latest_draw_is_rejected() -> None:
    assert _scenario("future_range") == {"status": 400}


def test_dates_older_than_the_fallback_window_never_trigger_a_fetch() -> None:
    result = _scenario("out_of_window")
    assert result["counter"] == {"primary": 1, "xskt": 0}
    assert result["unresolved"] == ["2020-01-01", "2020-01-02", "2020-01-03"]


def test_the_api_never_names_its_sources() -> None:
    result = _scenario("anonymised")
    assert result["mentions_source"] is False
    assert result["sources"] == ["fallback", "canonical"]
