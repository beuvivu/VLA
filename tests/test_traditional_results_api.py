"""Hợp đồng API Sổ kết quả: CSDL VLA trước, xskt.vn chỉ bù ngày thiếu."""

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
    assert result["source"] == "vla_db"
    assert result["special"] == "58851"
    assert result["leading_zero"] == "01"
    assert result["head_tail_total"] == 27


def test_xskt_fills_only_the_missing_date_and_response_is_cached() -> None:
    result = _scenario("fallback_and_response_cache")
    assert result["statuses"] == [200, 200]
    assert result["counter"] == {"primary": 1, "xskt": 1}
    assert result["dates"] == ["2026-09-13", "2026-09-12"]
    assert result["sources"] == ["xskt_fallback", "vla_db"]
    assert result["fallback_requested"] is True
    assert result["fallback_network_fetch"] is True
    assert result["second_cache"] == "hit"
    assert result["xskt_special"] == "83799"


def test_xskt_outage_does_not_hide_available_vla_results() -> None:
    result = _scenario("fallback_outage_keeps_primary")
    assert result["counter"] == {"primary": 1, "xskt": 1}
    assert result["dates"] == ["2026-09-12"]
    assert result["unresolved"] == ["2026-09-13"]
    assert result["warning"] == "Không đọc được xskt.vn: upstream timeout"


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
