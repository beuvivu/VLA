from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from ingest.sources import PRIMARY_SOURCE_NAMES, SOURCE_PUBLIC_CODE, default_sources

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "worker" / "test" / "run_sources.mjs"
NGAY = date(2026, 9, 5)


def _require_node() -> str:
    import os

    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError(
                "CI phải có node để chạy phép kiểm đối chiếu Python/JS; "
                "xem bước 'Thiết lập Node' trong .github/workflows/ci.yml"
            )
        pytest.skip("không có node trên máy chạy kiểm")
    return node


def _javascript_payload() -> dict:
    node = _require_node()
    proc = subprocess.run(
        [node, str(PROBE), NGAY.isoformat()],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, f"bản JS hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _javascript_sources() -> list[dict[str, object]]:
    return _javascript_payload()["sources"]


def test_source_order_and_urls_match_the_python_catalogue() -> None:
    python = [
        {
            "name": s.name,
            "tier": "primary" if s.name in PRIMARY_SOURCE_NAMES else "fallback",
            "date_urls": list(s.date_urls(NGAY)),
            "live_urls": list(s.live_urls(NGAY)),
        }
        for s in default_sources()
    ]
    javascript = [
        {k: v for k, v in row.items() if k != "has_select_section"}
        for row in _javascript_sources()
    ]
    assert javascript == python


def test_the_public_code_table_matches_entry_for_entry() -> None:
    assert _javascript_payload()["public_codes"] == SOURCE_PUBLIC_CODE


def test_no_source_trims_the_page_before_parsing() -> None:
    assert [row["name"] for row in _javascript_sources() if row["has_select_section"]] == []


def test_ci_sets_up_node_explicitly() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "actions/setup-node" in ci
    assert "node-version:" in ci
