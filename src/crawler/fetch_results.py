"""Thăm dò thông minh: chờ đủ 27 ô kết quả XSMB rồi thoát ngay lập tức.

Vì sao có mô-đun này
--------------------
Kiến trúc cũ phụ thuộc vào việc bộ lập lịch của GitHub nổ ĐÚNG 9-10 lần mỗi
ngày, mỗi lần chụp một ảnh. Đo trên kho này trong 7 ngày: chỉ 10 trên khoảng
63 mốc thực sự nổ, và mốc sớm nhất trong ngày trễ tới 6 giờ 21 phút. Một lịch
bị rơi mốc thì không có ảnh nào được chụp cả.

Mô-đun này đảo ngược quan hệ đó: MỘT lần chạy tự thăm dò trong vòng lặp cho
tới khi đủ số hoặc hết hạn. Nó chỉ cần bộ lập lịch đúng MỘT lần thay vì mười
lần, nên chịu được việc GitHub rơi mốc — và khi được gọi bằng
``repository_dispatch`` từ bộ hẹn giờ bên ngoài thì không phụ thuộc vào bộ
lập lịch của GitHub chút nào.

Mô-đun tái dùng nguyên bộ nguồn và phép đồng thuận trong :mod:`sources`. Viết
lại parser sẽ vứt đi phần đã chạy đúng và đã có test; thứ thực sự thiếu chỉ
là vòng lặp chờ, User-Agent và hạn thời gian chặt hơn.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

import requests

from sources import (
    EXPECTED_COUNTS,
    PRIZE_ORDER,
    Source,
    default_sources,
    source_consensus_partial,
)

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

#: Tổng số ô giải của một kỳ XSMB. Bất biến của bài toán, không phải tham số.
TOTAL_SLOTS = sum(EXPECTED_COUNTS.values())

#: Hạn cho MỖI yêu cầu HTTP. Đặt chặt là có chủ đích: trong khung 18:15-18:30
#: các trang kết quả quá tải, và một nguồn treo 20 giây sẽ nuốt trọn một chu
#: kỳ thăm dò. Sáu nguồn chạy song song nên mất một nguồn không sao; chờ nó
#: mới là mất.
DEFAULT_REQUEST_TIMEOUT = 8.0

#: Xoay vòng User-Agent. Bản cũ để mặc định ``python-requests/2.x`` — thứ mà
#: lớp chống bot của Cloudflare chặn thẳng tay. Đây không phải để giả dạng
#: người dùng mà để không bị lọc bởi một luật quá thô.
USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
)


def now_ict() -> datetime:
    """Thời điểm hiện tại theo giờ Việt Nam.

    Returns:
        ``datetime`` có múi giờ ``Asia/Ho_Chi_Minh``.
    """
    return datetime.now(TZ)


def stamp(moment: datetime | None = None) -> str:
    """Dấu thời gian ghi CẢ giờ Việt Nam lẫn UTC.

    Nhật ký chỉ ghi một múi giờ là nguồn gốc của mọi tranh cãi "chạy lúc mấy
    giờ": người đọc ở Việt Nam đọc giờ ICT, còn GitHub báo cáo mọi thứ theo
    UTC. Ghi cả hai thì không còn gì để suy diễn.

    Args:
        moment: Thời điểm cần in; mặc định là bây giờ.

    Returns:
        Chuỗi dạng ``18:15:03 ICT (11:15:03 UTC)``.
    """
    moment = (moment or now_ict()).astimezone(TZ)
    return (
        f"{moment:%H:%M:%S} ICT "
        f"({moment.astimezone(ZoneInfo('UTC')):%H:%M:%S} UTC)"
    )


def build_session(user_agent: str | None = None) -> requests.Session:
    """Phiên HTTP có User-Agent trình duyệt và các đầu mục đi kèm.

    Chỉ đặt mỗi ``User-Agent`` vẫn dễ bị nhận diện: một trình duyệt thật luôn
    gửi kèm ``Accept-Language`` và ``Accept``. Thiếu chúng là dấu hiệu rõ ràng
    của script.

    Args:
        user_agent: Chuỗi UA cụ thể; mặc định chọn ngẫu nhiên từ
            :data:`USER_AGENTS`.

    Returns:
        Phiên ``requests`` đã gắn sẵn đầu mục.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent or random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    return session


class _TimeoutCappedSession:
    """Bọc phiên HTTP: ép hạn thời gian, thử lại có lùi mũ, và ghi nhận lỗi.

    ``sources._request_page`` truyền sẵn ``timeout=15`` hoặc ``20``. Trong
    khung cao điểm hai mức đó đều quá dài, nhưng sửa thẳng vào ``sources`` sẽ
    đổi hành vi của cả đường lấy dữ liệu lịch sử — nơi chờ lâu là hợp lý vì
    không ai đứng đợi. Bọc lại cho phép lớp thăm dò siết hạn mà không đụng tới
    ngữ nghĩa của phần còn lại.

    Attributes:
        inner: Phiên thật bên dưới.
        cap: Trần thời gian tính bằng giây.
    """

    #: Mã trạng thái đáng thử lại. 429 là "quá nhiều yêu cầu" và 5xx là lỗi
    #: phía máy chủ — cả hai đều THOÁNG QUA, đúng kiểu hay gặp lúc 18:15-18:40
    #: khi cả nước cùng vào xem. 403 và 404 thì không: thử lại chỉ tốn thời
    #: gian vì câu trả lời sẽ y hệt.
    RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

    def __init__(
        self,
        inner: requests.Session,
        cap: float,
        *,
        max_attempts: int = 3,
        backoff_base: float = 0.5,
        backoff_cap: float = 4.0,
        sleeper=time.sleep,
    ) -> None:
        self.inner = inner
        self.cap = cap
        self.max_attempts = max(1, max_attempts)
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.sleeper = sleeper
        self.last_error: str | None = None
        self.last_status: int | None = None
        self.attempts = 0

    def _backoff_delay(self, attempt: int, response: object | None) -> float:
        """Thời gian chờ trước lần thử kế tiếp.

        Lũy thừa cơ số 2 kèm nhiễu ngẫu nhiên. Nhiễu là phần bắt buộc chứ
        không phải trang trí: sáu nguồn chạy song song, nếu cùng thất bại rồi
        cùng chờ đúng một khoảng thì lần thử sau lại dội vào cùng một thời
        điểm — đúng lúc máy chủ đang quá tải.

        Tôn trọng ``Retry-After`` khi máy chủ có nói, nhưng vẫn kẹp theo trần:
        một số nơi trả về hàng trăm giây, chờ chừng đó thì hết cả kỳ quay.

        Args:
            attempt: Lần thử vừa hỏng, đếm từ 1.
            response: Phản hồi nếu có, để đọc ``Retry-After``.

        Returns:
            Số giây cần chờ.
        """
        delay = min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_cap)
        headers = getattr(response, "headers", None) or {}
        raw = headers.get("Retry-After") if hasattr(headers, "get") else None
        if raw:
            try:
                delay = max(delay, float(raw))
            except (TypeError, ValueError):
                pass
        delay = min(delay, self.backoff_cap)
        return delay * random.uniform(0.5, 1.0)

    def get(self, url: str, timeout: int | float = 0, **kwargs: object) -> object:
        """Gọi GET với hạn thời gian không bao giờ vượt quá ``cap``.

        Cũng GHI LẠI kết quả thật của lần gọi. ``sources._request_page`` bắt
        mọi ngoại lệ mạng rồi trả về chuỗi rỗng, nên nếu chỉ nhìn giá trị trả
        về thì "DNS hỏng", "bị Cloudflare chặn 403" và "trang có thật nhưng
        chưa đăng số" trông giống hệt nhau — cả ba đều ra 0 ô. Với một lớp mà
        việc chính là chẩn đoán vì sao số chưa về, phân biệt được ba trường
        hợp đó là điều kiện cần.

        Args:
            url: Địa chỉ cần lấy.
            timeout: Hạn do nơi gọi đề nghị; bị kẹp xuống ``cap``.
            **kwargs: Chuyển tiếp nguyên vẹn cho ``requests``.

        Returns:
            Đối tượng phản hồi của ``requests``.

        Raises:
            Exception: Ném lại nguyên vẹn cho nơi gọi sau khi đã ghi nhận.
        """
        effective = self.cap if not timeout else min(float(timeout), self.cap)
        last_exc: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            self.attempts = attempt
            try:
                response = self.inner.get(url, timeout=effective, **kwargs)
            except Exception as exc:  # noqa: BLE001 - lỗi mạng là chuyện thường
                last_exc = exc
                self.last_error = f"{type(exc).__name__}: {str(exc)[:120]}"
                self.last_status = None
                if attempt < self.max_attempts:
                    self.sleeper(self._backoff_delay(attempt, None))
                    continue
                raise

            status = getattr(response, "status_code", None)
            self.last_status = status
            self.last_error = None if status == 200 else f"HTTP {status}"
            if status in self.RETRY_STATUS and attempt < self.max_attempts:
                self.sleeper(self._backoff_delay(attempt, response))
                continue
            return response

        # Chỉ tới đây khi lần thử cuối ném ngoại lệ mà vòng lặp không raise.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("không thực hiện được lần thử nào")


@dataclass(frozen=True)
class PollConfig:
    """Tham số của một phiên thăm dò.

    Attributes:
        target: Ngày quay cần lấy.
        window_start: Giờ bắt đầu thăm dò (giờ Việt Nam).
        deadline: Giờ bỏ cuộc (giờ Việt Nam).
        interval_seconds: Khoảng cách giữa hai vòng, dạng ``(min, max)``; mỗi
            vòng bốc ngẫu nhiên trong khoảng để nhiều bản chạy không dội cùng
            lúc vào nguồn.
        request_timeout: Hạn cho mỗi yêu cầu HTTP.
        min_agreement: Số nhóm nguồn ĐỘC LẬP phải khớp thì một ô mới được coi
            là đã xác minh.
        max_rounds: Trần số vòng, chốt chặn cuối nếu đồng hồ có vấn đề.
        max_attempts: Số lần thử mỗi yêu cầu HTTP trước khi bỏ nguồn đó cho
            vòng này. Ngân sách xấu nhất là
            ``max_attempts * request_timeout + backoff``, phải nhỏ hơn
            ``interval_seconds`` để vòng sau không bị trượt.
    """

    target: date
    window_start: dtime = dtime(18, 15)
    deadline: dtime = dtime(19, 30)
    interval_seconds: tuple[float, float] = (60.0, 90.0)
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    min_agreement: int = 2
    max_rounds: int = 90
    max_attempts: int = 3

    def __post_init__(self) -> None:
        low, high = self.interval_seconds
        if low <= 0 or high < low:
            raise ValueError("interval_seconds phải là (min>0, max>=min)")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout phải > 0")
        if self.min_agreement < 1:
            raise ValueError("min_agreement phải >= 1")
        if self.max_rounds < 1:
            raise ValueError("max_rounds phải >= 1")
        if self.max_attempts < 1:
            raise ValueError("max_attempts phải >= 1")
        # Ngân sách thử lại phải nằm gọn trong một chu kỳ thăm dò; nếu không,
        # một nguồn chậm sẽ nuốt trọn vòng và vòng kế tiếp bị trượt.
        worst_case = self.max_attempts * self.request_timeout
        if worst_case > self.interval_seconds[0]:
            raise ValueError(
                f"ngân sách thử lại {worst_case:.0f}s vượt chu kỳ thăm dò "
                f"{self.interval_seconds[0]:.0f}s"
            )

    def deadline_at(self) -> datetime:
        """Mốc bỏ cuộc dưới dạng ``datetime`` có múi giờ.

        Returns:
            Thời điểm hết hạn trong ngày ``target``.
        """
        return datetime.combine(self.target, self.deadline, tzinfo=TZ)

    def window_start_at(self) -> datetime:
        """Mốc bắt đầu thăm dò dưới dạng ``datetime`` có múi giờ.

        Returns:
            Thời điểm mở khung quay trong ngày ``target``.
        """
        return datetime.combine(self.target, self.window_start, tzinfo=TZ)


@dataclass
class PollOutcome:
    """Kết quả của một phiên thăm dò.

    Attributes:
        verified: Đã đủ 27 ô được xác minh hay chưa.
        verified_slots: Số ô đã xác minh.
        total_slots: Tổng số ô cần có.
        rounds: Số vòng đã chạy.
        prize_map: Bản đồ giải đã hợp nhất.
        started_at: Lúc bắt đầu vòng đầu tiên.
        finished_at: Lúc kết thúc.
        source_stats: Thống kê theo từng nguồn, dùng để chẩn đoán.
    """

    verified: bool
    verified_slots: int
    total_slots: int
    rounds: int
    prize_map: dict[str, list[str]]
    started_at: datetime
    finished_at: datetime
    source_stats: list[dict[str, object]] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        """Tổng thời gian đã thăm dò, tính bằng giây."""
        return (self.finished_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, object]:
        """Chuyển thành ``dict`` thuần để ghi JSON.

        Returns:
            Từ điển chỉ chứa kiểu cơ bản.
        """
        return {
            "verified": self.verified,
            "verified_slots": self.verified_slots,
            "total_slots": self.total_slots,
            "rounds": self.rounds,
            "started_at_ict": self.started_at.isoformat(),
            "finished_at_ict": self.finished_at.isoformat(),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "prize_map": self.prize_map,
            "source_stats": self.source_stats,
        }


def _fetch_one(
    source: Source,
    target: date,
    timeout: float,
    max_attempts: int = 3,
) -> tuple[str, dict[str, list[str]], str | None, int, int]:
    """Lấy một nguồn duy nhất, không bao giờ ném ngoại lệ ra ngoài.

    Một nguồn hỏng không được phép làm sập cả vòng: bản chất của thiết kế
    nhiều nguồn là chịu được mất mát từng phần.

    Args:
        source: Nguồn cần lấy.
        target: Ngày quay.
        timeout: Hạn cho mỗi yêu cầu.
        max_attempts: Số lần thử mỗi yêu cầu.

    Returns:
        Bộ ``(tên nguồn, bản đồ giải, lỗi hoặc None, độ trễ ms, số lần thử)``.
    """
    started = time.perf_counter()
    error: str | None = None
    prize_map: dict[str, list[str]] = {k: [] for k in PRIZE_ORDER}
    # Mỗi nguồn một phiên riêng: UA khác nhau, và tránh chia sẻ trạng thái
    # giữa các luồng.
    http = _TimeoutCappedSession(build_session(), timeout, max_attempts=max_attempts)
    try:
        prize_map = source.fetch_partial(target, http, live=True)
    except Exception as exc:  # noqa: BLE001 - phải nuốt mọi lỗi mạng
        error = f"{type(exc).__name__}: {str(exc)[:120]}"
    # Lỗi mà nguồn đã tự nuốt vẫn phải nổi lên nhật ký.
    error = error or http.last_error
    latency_ms = int(round((time.perf_counter() - started) * 1000.0))
    return source.name, prize_map, error, latency_ms, http.attempts


def poll_once(
    sources: Sequence[Source],
    target: date,
    *,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    min_agreement: int = 2,
    max_attempts: int = 3,
) -> tuple[dict[str, list[str]], int, list[dict[str, object]]]:
    """Một vòng: hỏi song song mọi nguồn rồi hợp nhất bằng đồng thuận.

    Song song chứ không phải dự phòng nối tiếp. Nối tiếp thì tổng thời gian là
    TỔNG của các nguồn chậm; song song thì là nguồn chậm NHẤT. Quan trọng hơn:
    phép đồng thuận cần nhiều nguồn cùng lúc để đối chiếu, chứ không phải chỉ
    lấy nguồn đầu tiên trả lời.

    Args:
        sources: Danh sách nguồn.
        target: Ngày quay.
        timeout: Hạn mỗi yêu cầu.
        min_agreement: Số nhóm nguồn độc lập tối thiểu.

    Returns:
        Bộ ``(bản đồ giải đã hợp nhất, số ô đã xác minh, thống kê nguồn)``.
    """
    partials: list[tuple[int, str, dict[str, list[str]]]] = []
    stats: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        futures = {
            pool.submit(_fetch_one, source, target, timeout, max_attempts): priority
            for priority, source in enumerate(sources, start=1)
        }
        for future in as_completed(futures):
            priority = futures[future]
            name, prize_map, error, latency_ms, attempts = future.result()
            received = sum(len(prize_map.get(k, [])) for k in PRIZE_ORDER)
            partials.append((priority, name, prize_map))
            stats.append(
                {
                    "priority": priority,
                    "source": name,
                    "received_values": received,
                    "complete": received == TOTAL_SLOTS,
                    "latency_ms": latency_ms,
                    "attempts": attempts,
                    "error": error,
                }
            )

    # Sắp lại theo thứ tự ưu tiên nghiệp vụ. as_completed trả về theo thứ tự
    # nguồn nào xong trước, mà phép đồng thuận dùng thứ tự này để phá hoà.
    partials.sort(key=lambda item: item[0])
    stats.sort(key=lambda item: item["priority"])

    merged, meta = source_consensus_partial(
        [(name, pmap) for _, name, pmap in partials],
        min_agreement=min_agreement,
    )
    verified_slots = int(meta.get("verified_slots", 0))
    return merged, verified_slots, stats


def poll_until_complete(
    config: PollConfig,
    *,
    sources: Sequence[Source] | None = None,
    sleeper=time.sleep,
    clock=now_ict,
) -> PollOutcome:
    """Thăm dò tới khi đủ 27 ô được xác minh, hoặc hết hạn.

    Thoát NGAY khi đủ số — đây là điểm mấu chốt về chi phí: một kỳ quay xong
    lúc 18:32 thì job kết thúc lúc 18:32, không giữ runner tới hết khung.

    Args:
        config: Tham số phiên thăm dò.
        sources: Danh sách nguồn; mặc định là bộ chuẩn của kho.
        sleeper: Hàm ngủ; tiêm vào để test không phải chờ thật.
        clock: Hàm lấy giờ hiện tại; tiêm vào để test điều khiển thời gian.

    Returns:
        :class:`PollOutcome` mô tả kết quả.
    """
    sources = list(sources if sources is not None else default_sources())
    started = clock()
    deadline_at = config.deadline_at()
    window_at = config.window_start_at()

    # Chạy sớm hơn khung quay thì chờ — thăm dò trước 18:15 chỉ tốn yêu cầu
    # cho một trang chắc chắn chưa có số.
    if started < window_at:
        wait = (window_at - started).total_seconds()
        logger.info(
            "Còn %.0f phút mới tới khung quay %s; chờ. Bây giờ %s",
            wait / 60.0,
            config.window_start.strftime("%H:%M"),
            stamp(started),
        )
        sleeper(wait)

    merged: dict[str, list[str]] = {k: [] for k in PRIZE_ORDER}
    stats: list[dict[str, object]] = []
    verified_slots = 0
    rounds = 0
    best_slots = -1

    while rounds < config.max_rounds:
        now = clock()
        if now >= deadline_at:
            logger.warning(
                "Hết hạn %s mà mới có %d/%d ô.",
                config.deadline.strftime("%H:%M"),
                verified_slots,
                TOTAL_SLOTS,
            )
            break

        rounds += 1
        merged, verified_slots, stats = poll_once(
            sources,
            config.target,
            timeout=config.request_timeout,
            min_agreement=config.min_agreement,
            max_attempts=config.max_attempts,
        )

        if verified_slots != best_slots:
            # Chỉ ghi khi CÓ thay đổi. Vòng lặp 60 giây suốt một giờ sẽ đẻ ra
            # 60 dòng giống hệt nhau và chôn vùi dòng thực sự đáng đọc.
            live = sum(1 for s in stats if not s["error"])
            logger.info(
                "Vòng %d lúc %s: %d/%d ô đã xác minh, %d/%d nguồn trả lời.",
                rounds,
                stamp(clock()),
                verified_slots,
                TOTAL_SLOTS,
                live,
                len(sources),
            )
            best_slots = verified_slots

        if verified_slots >= TOTAL_SLOTS:
            logger.info(
                "Đủ %d ô sau %d vòng lúc %s — thoát ngay.",
                TOTAL_SLOTS,
                rounds,
                stamp(clock()),
            )
            break

        # Ngủ trong khoảng ngẫu nhiên, nhưng không bao giờ ngủ quá hạn chót.
        nap = random.uniform(*config.interval_seconds)
        remaining = (deadline_at - clock()).total_seconds()
        if remaining <= 0:
            break
        sleeper(min(nap, remaining))

    finished = clock()
    return PollOutcome(
        verified=verified_slots >= TOTAL_SLOTS,
        verified_slots=verified_slots,
        total_slots=TOTAL_SLOTS,
        rounds=rounds,
        prize_map=merged,
        started_at=started,
        finished_at=finished,
        source_stats=stats,
    )


def _parse_hhmm(value: str) -> dtime:
    """Đọc chuỗi ``HH:MM`` thành ``time``.

    Args:
        value: Chuỗi giờ phút.

    Returns:
        Đối tượng ``datetime.time``.

    Raises:
        argparse.ArgumentTypeError: Nếu chuỗi sai định dạng.
    """
    try:
        hh, mm = value.split(":")
        return dtime(int(hh), int(mm))
    except Exception as exc:  # noqa: BLE001
        raise argparse.ArgumentTypeError(f"giờ không hợp lệ: {value!r}") from exc


def _write_github_output(outcome: PollOutcome) -> None:
    """Ghi kết quả ra ``$GITHUB_OUTPUT`` nếu đang chạy trong Actions.

    Args:
        outcome: Kết quả phiên thăm dò.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"verified={'true' if outcome.verified else 'false'}\n")
        handle.write(f"verified_slots={outcome.verified_slots}\n")
        handle.write(f"rounds={outcome.rounds}\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Điểm vào dòng lệnh.

    Args:
        argv: Tham số dòng lệnh; mặc định lấy từ ``sys.argv``.

    Returns:
        0 nếu đã xác minh đủ 27 ô, 1 nếu không.
    """
    parser = argparse.ArgumentParser(
        description="Thăm dò tới khi đủ 27 ô kết quả XSMB được xác minh."
    )
    parser.add_argument("--date", default=None, help="Ngày quay YYYY-MM-DD (mặc định: hôm nay theo giờ VN)")
    parser.add_argument("--window-start", type=_parse_hhmm, default=dtime(18, 15))
    parser.add_argument("--deadline", type=_parse_hhmm, default=dtime(19, 30))
    parser.add_argument("--interval-min", type=float, default=60.0)
    parser.add_argument("--interval-max", type=float, default=90.0)
    parser.add_argument("--timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT)
    parser.add_argument("--min-agreement", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=3,
                        help="Số lần thử mỗi yêu cầu (lùi mũ giữa các lần)")
    parser.add_argument("--json-out", default=None, help="Ghi tóm tắt JSON ra tệp")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    target = date.fromisoformat(args.date) if args.date else now_ict().date()
    config = PollConfig(
        target=target,
        window_start=args.window_start,
        deadline=args.deadline,
        interval_seconds=(args.interval_min, args.interval_max),
        request_timeout=args.timeout,
        min_agreement=args.min_agreement,
        max_attempts=args.max_attempts,
    )

    logger.info(
        "Bắt đầu thăm dò kỳ %s, khung %s-%s giờ VN, hạn mỗi yêu cầu %.1fs. Bây giờ %s",
        target.isoformat(),
        config.window_start.strftime("%H:%M"),
        config.deadline.strftime("%H:%M"),
        config.request_timeout,
        stamp(),
    )

    outcome = poll_until_complete(config)

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    _write_github_output(outcome)

    logger.info(
        "Kết thúc: %s — %d/%d ô sau %d vòng, %.0f giây.",
        "ĐỦ" if outcome.verified else "THIẾU",
        outcome.verified_slots,
        outcome.total_slots,
        outcome.rounds,
        outcome.elapsed_seconds,
    )
    return 0 if outcome.verified else 1


if __name__ == "__main__":
    sys.exit(main())
