"""Lớp thu thập kết quả XSMB đúng giờ.

Tách khỏi :mod:`live_sync` vì hai mục đích khác nhau: ``live_sync`` chụp MỘT
ảnh và ghi ra nhánh live để trang web hiển thị số nhỏ giọt, còn lớp này CHỜ
cho tới khi đủ 27 ô được xác minh rồi thoát ngay — nó là cổng "xong hay chưa"
cho quy trình hoàn tất.
"""

from crawler.fetch_results import (
    DEFAULT_REQUEST_TIMEOUT,
    USER_AGENTS,
    PollConfig,
    PollOutcome,
    build_session,
    poll_until_complete,
)

__all__ = [
    "DEFAULT_REQUEST_TIMEOUT",
    "USER_AGENTS",
    "PollConfig",
    "PollOutcome",
    "build_session",
    "poll_until_complete",
]
