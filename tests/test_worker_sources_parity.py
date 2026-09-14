"""Danh mục nguồn của Worker phải khớp bản Python.

Ba thứ phải khớp và mỗi thứ hỏng một kiểu:

* **Thứ tự** là thứ tự ƯU TIÊN khi các nguồn bất đồng. Đảo thứ tự thì lúc chưa
  đủ đồng thuận, trang live hiện giá trị của nguồn này còn lịch sử lấy của
  nguồn kia — hai mặt cùng một kỳ nói khác nhau.
* **Địa chỉ theo ngày** sai thì Worker lấy nhầm kỳ. Đây là kiểu sai tệ nhất:
  số vẫn hợp lệ, vẫn đủ 27 ô, chỉ là của hôm khác.
* **Địa chỉ trực tiếp** sai thì Worker đọc trang tổng hợp thay vì trang tường
  thuật, và sẽ không bao giờ thấy số về dần.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from sources import SOURCE_PUBLIC_CODE, default_sources

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "worker" / "test" / "run_sources.mjs"
NGAY = date(2026, 9, 5)


def _require_node() -> str:
    """Trả về đường dẫn ``node``; ngoài CI thì bỏ qua, trong CI thì HỎNG.

    Bỏ qua trong CI là chốt chặn giả: bộ kiểm vẫn xanh trong khi phép so hai
    bản mã chưa hề chạy. Ngoài CI thì bỏ qua là hợp lý — không phải máy nào
    cũng cài Node.
    """
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
            "tier": "primary" if i < 2 else "fallback",
            "date_urls": list(s.date_urls(NGAY)),
            "live_urls": list(s.live_urls(NGAY)),
        }
        for i, s in enumerate(default_sources())
    ]
    javascript = [
        {k: v for k, v in row.items() if k != "has_select_section"}
        for row in _javascript_sources()
    ]
    assert javascript == python


def test_the_public_code_table_matches_entry_for_entry() -> None:
    """Mã ẩn danh phải khớp hai bên.

    Lệch mã thì trang live hiện "P1" cho nguồn này còn nhật ký ghi "P1" cho
    nguồn kia — và cả hai vẫn trông hợp lệ, nên không gì báo.
    """
    assert _javascript_payload()["public_codes"] == SOURCE_PUBLIC_CODE


def test_only_rolling_ledgers_trim_the_page_before_parsing() -> None:
    """Hai sổ cái cuộn phải cắt; các nguồn theo ngày thì không.

    Cắt nhầm một nguồn không cần cắt sẽ âm thầm bỏ mất phần đầu bảng giải.
    """
    javascript = _javascript_sources()
    co_cat = {row["name"] for row in javascript if row["has_select_section"]}
    assert co_cat == {"hainhay.net", "xskt.vn"}


def test_ci_sets_up_node_explicitly() -> None:
    """Bốn phép kiểm đối chiếu vô dụng nếu CI không có node.

    Chúng tự bỏ qua khi thiếu `node`, nên nếu CI mất Node thì bộ kiểm vẫn xanh
    trong khi phép so hai bản mã chưa hề chạy. `_require_node` đã biến việc
    thiếu node TRONG CI thành lỗi; phép kiểm này khoá nốt nửa còn lại — bước
    dựng Node phải nằm trong quy trình.
    """
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "actions/setup-node" in ci
    assert "node-version:" in ci
