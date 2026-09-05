"""Kiểm thử trang kết quả trực tiếp và lịch chạy workflow live.

Trang phải dựng sẵn đủ 27 ô (không xê dịch bố cục), hiện số lần lượt qua hàng
đợi, và tuân thủ ràng buộc bảo mật: không dùng innerHTML, giữ nguyên CSP.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def _live_job_budget() -> tuple[int, int]:
    """Trả về (giới hạn job, ngân sách thăm dò) tính bằng giây.

    Đọc bằng regex thay vì PyYAML: dự án không khai báo PyYAML là phụ thuộc
    nên thêm import chỉ để phục vụ một test sẽ làm hỏng CI.
    """
    workflow = LIVE_WORKFLOW.read_text(encoding="utf-8")
    timeout = re.search(r"^\s*timeout-minutes:\s*(\d+)", workflow, re.MULTILINE)
    budget = re.search(r"^\s*MAX_SECONDS:\s*\"?(\d+)\"?", workflow, re.MULTILINE)
    assert timeout and budget, "không đọc được timeout-minutes / MAX_SECONDS"
    return int(timeout.group(1)) * 60, int(budget.group(1))


def test_live_workflow_timeout_outlasts_its_polling_budget() -> None:
    """Job bị giết trước khi vòng lặp kết thúc thì bước bàn giao daily không chạy."""
    timeout_seconds, max_seconds = _live_job_budget()
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
    # Live bắt đầu 18:00 giờ VN; khung phải phủ tới lúc job kết thúc.
    live_end = 18 * 60 + _live_job_budget()[1] // 60
    assert end_minutes >= live_end
