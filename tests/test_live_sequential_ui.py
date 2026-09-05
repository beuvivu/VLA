"""Kiểm thử trang kết quả trực tiếp và lịch chạy workflow live.

Trang phải dựng sẵn đủ 27 ô (không xê dịch bố cục), hiện số lần lượt qua hàng
đợi, và tuân thủ ràng buộc bảo mật: không dùng innerHTML, giữ nguyên CSP.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LIVE_PAGE = ROOT / "docs/live.html"
LIVE_WORKFLOW = ROOT / ".github/workflows/live-results.yml"


def _page() -> str:
    return LIVE_PAGE.read_text(encoding="utf-8")


def test_live_page_keeps_security_contract() -> None:
    page = _page()
    assert ".innerHTML" not in page
    assert "insertAdjacentHTML" not in page
    assert "connect-src 'self' https://raw.githubusercontent.com" in page
    # Không nạp tài nguyên ngoài ngoài đúng một nguồn dữ liệu đã khai báo.
    external = set(re.findall(r"https://[a-z0-9.\-]+", page))
    assert external == {"https://raw.githubusercontent.com"}


def test_live_page_declares_all_twenty_seven_prize_slots() -> None:
    """Khung dựng sẵn đủ ô nên chiều cao trang không đổi khi số về."""
    page = _page()
    counts = [int(m) for m in re.findall(r"count:\s*(\d+)", page)]
    assert sum(counts) == 27, counts
    # Khớp EXPECTED_COUNTS phía Python.
    assert counts == [1, 1, 2, 6, 4, 6, 3, 4]
    digits = [int(m) for m in re.findall(r"digits:\s*(\d+)", page)]
    assert digits == [5, 5, 5, 5, 4, 4, 3, 2]


def test_live_page_reveals_new_numbers_through_a_stagger_queue() -> None:
    """Số mới phải đi qua hàng đợi để hiện lần lượt, không đổ cùng lúc."""
    page = _page()
    assert "revealQueue" in page
    assert "REVEAL_STAGGER_MS" in page
    assert "queueReveal" in page
    # Ô đã hiển thị không được đưa lại vào hàng đợi (tránh nhấp nháy).
    assert "if (value === entry.value) continue;" in page


def test_live_page_polls_faster_while_the_draw_is_in_progress() -> None:
    """Nhịp thăm dò do trạng thái dữ liệu quyết định, đồng hồ chỉ là phụ."""
    page = _page()
    assert "if (status === 'partial') return 5000;" in page
    assert "if (status === 'complete_verified') return 300000;" in page
    assert "visibilitychange" in page


def test_live_page_respects_reduced_motion() -> None:
    page = _page()
    assert "prefers-reduced-motion" in page


def test_live_workflow_timeout_outlasts_its_polling_budget() -> None:
    """Job bị giết trước khi vòng lặp kết thúc thì bước bàn giao daily không chạy."""
    workflow = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["live"]
    timeout_seconds = int(job["timeout-minutes"]) * 60
    max_seconds = int(job["env"]["MAX_SECONDS"])
    assert timeout_seconds > max_seconds, (
        f"timeout {timeout_seconds}s phải lớn hơn ngân sách thăm dò {max_seconds}s"
    )
    # Còn đủ biên cho checkout + cài đặt thư viện.
    assert timeout_seconds - max_seconds >= 300


def test_watchdog_live_window_covers_the_whole_live_run() -> None:
    """Khung cứu hộ phải phủ hết thời gian job live có thể còn chạy."""
    watchdog = (ROOT / ".github/workflows/watchdog.yml").read_text(encoding="utf-8")
    match = re.search(
        r"live_window = 17 \* 60 \+ 55 <= local_hm <= (\d+) \* 60 \+ (\d+)", watchdog
    )
    assert match, "không tìm thấy định nghĩa live_window"
    end_minutes = int(match.group(1)) * 60 + int(match.group(2))
    live_job = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["live"]
    # Live bắt đầu 18:00 giờ VN; khung phải phủ tới lúc job kết thúc.
    live_end = 18 * 60 + int(live_job["env"]["MAX_SECONDS"]) // 60
    assert end_minutes >= live_end
