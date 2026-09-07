"""Bổ sung lịch sử KQXS theo dải ngày.

Vì sao cần công cụ riêng
------------------------
``Lottery.fetch`` đã lấy được một kỳ bất kỳ trong quá khứ, và 5 trong 6 nguồn
có URL lưu trữ theo ngày. Thứ còn thiếu chỉ là trình điều khiển quét dải ngày
một cách an toàn.

"An toàn" ở đây có nghĩa cụ thể:

* **Có thể chạy lại.** Một lần chạy phủ nhiều năm sẽ gửi hàng nghìn yêu cầu và
  chắc chắn bị đứt giữa chừng. Mỗi kỳ đã có được bỏ qua, nên chạy lại chỉ tốn
  công cho phần còn thiếu.
* **Ghi theo lô.** Đứt ở kỳ thứ 900 mà chưa ghi gì thì mất trắng. Ghi sau mỗi
  ``checkpoint_every`` kỳ giữ lại phần đã làm.
* **Có nhịp chờ.** Nã 2000 yêu cầu liên tiếp vào một trang tin là hành vi lạm
  dụng và sẽ bị chặn IP. Mặc định chờ 1,5-3 giây giữa các kỳ.

Ràng buộc quan trọng: **393 kỳ hiện có là trần cứng của mọi mô hình trong
kho**. Xem ``documentation/architecture/soi-cau-ml-mapping.md``. Đây là thay
đổi duy nhất làm dịch chuyển được kết quả của toàn bộ lớp phân tích.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Iterable, Sequence

logger = logging.getLogger(__name__)

#: Kỳ XSMB sớm nhất mà các nguồn còn lưu trữ đáng tin. Trước mốc này nhiều
#: trang chỉ còn bản tóm tắt thiếu giải, và dữ liệu thiếu giải còn tệ hơn
#: không có dữ liệu vì nó lặng lẽ làm lệch mọi thống kê.
EARLIEST_SUPPORTED = date(2015, 1, 1)


@dataclass
class BackfillReport:
    """Kết quả một lần chạy bổ sung lịch sử.

    Attributes:
        requested: Số kỳ nằm trong dải yêu cầu.
        already_present: Số kỳ đã có sẵn, không cần lấy.
        fetched: Số kỳ lấy được mới.
        failed: Danh sách kỳ không lấy được.
        checkpoints: Số lần ghi ra đĩa.
        elapsed_seconds: Tổng thời gian chạy.
    """

    requested: int = 0
    already_present: int = 0
    fetched: int = 0
    failed: list[date] = field(default_factory=list)
    checkpoints: int = 0
    elapsed_seconds: float = 0.0

    @property
    def attempted(self) -> int:
        """Số kỳ thực sự phải gọi mạng."""
        return self.fetched + len(self.failed)

    @property
    def success_rate(self) -> float:
        """Tỉ lệ lấy được trên số kỳ đã thử; 1.0 khi không phải thử kỳ nào."""
        return 1.0 if self.attempted == 0 else self.fetched / self.attempted

    def summary(self) -> str:
        """Một dòng tóm tắt để in ra nhật ký."""
        return (
            f"yêu cầu {self.requested}, đã có {self.already_present}, "
            f"lấy mới {self.fetched}, hỏng {len(self.failed)}, "
            f"ghi {self.checkpoints} lần, {self.elapsed_seconds:.0f}s"
        )


def date_range(start: date, end: date) -> list[date]:
    """Mọi ngày từ ``start`` tới ``end``, bao gồm hai đầu.

    XSMB quay tất cả các ngày trong tuần nên không cần lọc thứ.

    Args:
        start: Ngày đầu.
        end: Ngày cuối.

    Returns:
        Danh sách ngày tăng dần; rỗng nếu ``start`` sau ``end``.
    """
    if start > end:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def missing_dates(wanted: Iterable[date], have: set[date]) -> list[date]:
    """Các kỳ còn thiếu, sắp xếp từ MỚI tới CŨ.

    Thứ tự này là có chủ đích: kỳ gần đây được nhiều nguồn lưu trữ hơn và có
    giá trị phân tích cao hơn, nên nếu lần chạy bị đứt sớm thì phần thu được
    vẫn là phần đáng giá nhất.

    Args:
        wanted: Dải ngày mong muốn.
        have: Các kỳ đã có trong kho.

    Returns:
        Danh sách kỳ còn thiếu, giảm dần theo ngày.
    """
    return sorted({d for d in wanted if d not in have}, reverse=True)


def backfill(
    lottery,
    start: date,
    end: date,
    *,
    min_agreement: int = 1,
    checkpoint_every: int = 25,
    delay_range: tuple[float, float] = (1.5, 3.0),
    max_failures: int = 40,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> BackfillReport:
    """Lấy các kỳ còn thiếu trong dải ngày và ghi vào kho.

    Args:
        lottery: Đối tượng ``Lottery`` đã ``load()``.
        start: Ngày đầu dải.
        end: Ngày cuối dải.
        min_agreement: Số nguồn độc lập phải khớp. Mặc định 1 cho backfill —
            kỳ quá khứ đã được nhiều nơi đăng lại và đối chiếu, còn đòi 2
            nguồn cho hàng nghìn kỳ thì gấp đôi lưu lượng và làm hỏng cả dải
            khi một nguồn ngừng lưu trữ.
        checkpoint_every: Ghi ra đĩa sau mỗi bấy nhiêu kỳ lấy được.
        delay_range: Khoảng chờ ngẫu nhiên (giây) giữa hai yêu cầu.
        max_failures: Dừng sau bấy nhiêu kỳ hỏng LIÊN TIẾP. Hỏng liên tiếp
            nghĩa là nguồn đã chặn hoặc đổi cấu trúc, chạy tiếp chỉ tốn thời
            gian và làm tình hình tệ hơn.
        sleeper: Hàm chờ; tiêm vào để test không phải chờ thật.
        clock: Hàm lấy mốc thời gian đơn điệu.

    Returns:
        :class:`BackfillReport`.

    Raises:
        ValueError: Nếu dải ngày không hợp lệ hoặc tham số ngoài miền.
    """
    if start > end:
        raise ValueError(f"start ({start}) phải trước hoặc bằng end ({end})")
    if start < EARLIEST_SUPPORTED:
        raise ValueError(
            f"start ({start}) sớm hơn mốc {EARLIEST_SUPPORTED} — "
            "các nguồn không còn lưu trữ đầy đủ trước mốc này"
        )
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every phải >= 1")
    if max_failures < 1:
        raise ValueError("max_failures phải >= 1")
    low, high = delay_range
    if low < 0 or high < low:
        raise ValueError("delay_range phải là (min>=0, max>=min)")

    began = clock()
    wanted = date_range(start, end)
    have = lottery.get_dates()
    todo = missing_dates(wanted, have)

    report = BackfillReport(
        requested=len(wanted),
        already_present=len(wanted) - len(todo),
    )
    logger.info(
        "Dải %s → %s: %d kỳ, đã có %d, cần lấy %d",
        start, end, report.requested, report.already_present, len(todo),
    )

    consecutive_failures = 0
    since_checkpoint = 0

    for index, day in enumerate(todo, start=1):
        try:
            ok = lottery.fetch(day, min_agreement=min_agreement)
        except Exception as exc:  # noqa: BLE001 - một kỳ hỏng không được dừng cả dải
            logger.debug("kỳ %s lỗi: %s", day, exc)
            ok = False

        if ok:
            report.fetched += 1
            since_checkpoint += 1
            consecutive_failures = 0
        else:
            report.failed.append(day)
            consecutive_failures += 1
            if consecutive_failures >= max_failures:
                logger.error(
                    "Dừng sớm: %d kỳ hỏng liên tiếp (tới %s). Nguồn nhiều khả "
                    "năng đã chặn hoặc đổi cấu trúc.",
                    consecutive_failures, day,
                )
                break

        if since_checkpoint >= checkpoint_every:
            lottery.dump()
            report.checkpoints += 1
            since_checkpoint = 0
            logger.info(
                "Đã ghi %d/%d kỳ (%.0f%%)",
                report.fetched, len(todo), 100.0 * index / len(todo),
            )

        if index < len(todo):
            sleeper(random.uniform(low, high))

    if since_checkpoint > 0:
        lottery.dump()
        report.checkpoints += 1

    report.elapsed_seconds = clock() - began
    logger.info("Xong: %s", report.summary())
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Điểm vào dòng lệnh.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        0 nếu lấy được ít nhất một kỳ hoặc không có kỳ nào cần lấy; 1 nếu
        phải thử mà không lấy được kỳ nào.
    """
    parser = argparse.ArgumentParser(description="Bổ sung lịch sử KQXS theo dải ngày.")
    parser.add_argument("--start", required=True, help="Ngày đầu YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="Ngày cuối YYYY-MM-DD (mặc định: hôm qua)")
    parser.add_argument("--min-agreement", type=int, default=1)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--delay-min", type=float, default=1.5)
    parser.add_argument("--delay-max", type=float, default=3.0)
    parser.add_argument("--max-failures", type=int, default=40)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from lottery import Lottery, vietnam_today

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else vietnam_today() - timedelta(days=1)

    lottery = Lottery()
    lottery.load()
    before = len(lottery.get_dates())

    report = backfill(
        lottery,
        start,
        end,
        min_agreement=args.min_agreement,
        checkpoint_every=args.checkpoint_every,
        delay_range=(args.delay_min, args.delay_max),
        max_failures=args.max_failures,
    )

    after = len(lottery.get_dates())
    logger.info("Kho: %d → %d kỳ (+%d)", before, after, after - before)

    if report.attempted and report.fetched == 0:
        logger.error("Không lấy được kỳ nào trong %d lần thử.", report.attempted)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
