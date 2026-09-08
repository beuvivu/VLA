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

Ràng buộc quan trọng: **độ dài lịch sử là trần cứng của mọi mô hình trong
kho** (393 kỳ trước lần bổ sung đầu tiên). Xem
``documentation/architecture/soi-cau-ml-mapping.md``. Đây là thay đổi duy nhất
làm dịch chuyển được kết quả của toàn bộ lớp phân tích.

Hệ quả cần nhớ khi kho dài ra: mọi mốc ngẫu nhiên đều co giãn theo số kỳ.
Cực đại do ngẫu nhiên của 4950 cặp lô tô là 39,9 ở 393 kỳ nhưng 161,8 ở 2200
kỳ — xem :func:`xsmb_domain.pair_chance_maximum`. Mốc nào còn đóng cứng theo
393 kỳ sẽ biến mọi cặp thành "bất thường" ngay sau lần bổ sung này.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
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


def _persist(lottery) -> None:
    """Ghi kho ra đĩa, dựng lại bảng trước khi ghi.

    ``Lottery.fetch`` chỉ thêm vào ``_data``; ``Lottery.dump`` lại ghi
    ``_raw_data``, bảng chỉ được dựng bởi ``generate_dataframes``. Thiếu một
    lệnh gọi ở giữa thì hàm ghi đè bảng cũ lên đĩa và **xoá đúng những kỳ vừa
    lấy về**.

    Đây không phải giả thiết: lần chạy thật 34174095945 lấy 2049 kỳ, hỏng 0,
    báo "Kho: 393 → 2442 kỳ", rồi ghi ra một tệp 393 kỳ — mất trọn 1 giờ 35
    phút cào dữ liệu. ``src/sync.py`` của quy trình hàng ngày luôn gọi cặp
    này liền nhau; chỉ backfill bỏ sót.

    Args:
        lottery: Đối tượng ``Lottery`` đang giữ dữ liệu.
    """
    lottery.generate_dataframes()
    lottery.dump()


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
            _persist(lottery)
            report.checkpoints += 1
            since_checkpoint = 0
            logger.info(
                "Đã ghi %d/%d kỳ (%.0f%%)",
                report.fetched, len(todo), 100.0 * index / len(todo),
            )

        if index < len(todo):
            sleeper(random.uniform(low, high))

    if since_checkpoint > 0:
        _persist(lottery)
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
    parser.add_argument(
        "--merge-store",
        default=None,
        metavar="PATH",
        help=(
            "Hợp nhất một bản kho đã lưu vào data/xsmb.json rồi dựng lại các "
            "tệp dẫn xuất, sau đó thoát. Dùng khi nhánh chính đã tiến lên "
            "trong lúc backfill chạy."
        ),
    )
    parser.add_argument(
        "--drop-repeats",
        action="store_true",
        help=(
            "Loại các bản ghi trùng khít ngày liền trước rồi dựng lại kho, "
            "sau đó thoát. Đó là ngày XSMB không quay (Tết, giãn cách 2020) "
            "mà nguồn trả kết quả cũ."
        ),
    )
    parser.add_argument("--start", required=False, help="Ngày đầu YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="Ngày cuối YYYY-MM-DD (mặc định: hôm qua)")
    parser.add_argument("--min-agreement", type=int, default=1)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--delay-min", type=float, default=1.5)
    parser.add_argument("--delay-max", type=float, default=3.0)
    parser.add_argument("--max-failures", type=int, default=40)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from lottery import Lottery, vietnam_today

    if args.merge_store:
        # Hợp nhất theo ngày rồi để Lottery dựng lại csv/json và các bảng
        # dẫn xuất — không tự viết tệp dẫn xuất, vì định dạng của chúng là
        # việc của Lottery.
        root = Path(__file__).resolve().parents[1]
        canonical = root / "data" / "xsmb.json"
        merge_stores(Path(args.merge_store), canonical, canonical)
        merged = Lottery()
        merged.load()
        merged.dump()
        logger.info("Đã hợp nhất và dựng lại: %d kỳ", len(merged.get_dates()))
        return 0

    if args.drop_repeats:
        root = Path(__file__).resolve().parents[1]
        canonical = root / "data" / "xsmb.json"
        records = json.loads(canonical.read_text(encoding="utf-8"))
        drop = set(repeated_draw_dates(records))
        if not drop:
            logger.info("Không có kỳ trùng khít nào.")
            return 0
        kept = [r for r in records if str(r["date"])[:10] not in drop]
        canonical.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        cleaned = Lottery()
        cleaned.load()
        cleaned.generate_dataframes()
        cleaned.dump()
        logger.info(
            "Đã loại %d kỳ không quay (%s → %s); còn %d kỳ",
            len(drop), min(drop), max(drop), len(cleaned.get_dates()),
        )
        return 0

    if not args.start:
        parser.error("--start là bắt buộc khi không dùng --merge-store hoặc --drop-repeats")

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


def repeated_draw_dates(records: Sequence[dict]) -> list[str]:
    """Các ngày có kết quả TRÙNG KHÍT ngày liền trước — không phải kỳ quay.

    XSMB nghỉ quay dịp Tết và trong đợt giãn cách 2020. Vào những ngày đó
    trang nguồn vẫn trả kết quả gần nhất, nên trình cào ghi lại như thể đó là
    kỳ của ngày ấy. Trên kho 2442 kỳ có 8 cụm như vậy: Tết mỗi năm 2020-2026
    (5 ngày mỗi dịp) và 01-22/4/2020 (23 ngày, Chỉ thị 16).

    Một kỳ có 107 chữ số giải, nên xác suất hai kỳ trùng khít do ngẫu nhiên là
    10^-107. Không phải "hiếm" mà là bất khả: trùng khít luôn là hiện vật.

    Bản ghi ĐẦU mỗi cụm được giữ vì đó là kỳ thật cuối cùng trước khi tạm
    ngừng — kiểm chứng được: nội dung cụm khác với ngày liền trước cụm.

    Args:
        records: Bản ghi kho, mỗi phần tử có khoá ``date``.

    Returns:
        Danh sách ngày (``YYYY-MM-DD``) cần loại, theo thứ tự tăng dần.
    """
    def fingerprint(record: dict) -> tuple[str, ...]:
        return tuple(str(v) for k, v in sorted(record.items()) if k != "date")

    ordered = sorted(records, key=lambda r: str(r["date"])[:10])
    drop: list[str] = []
    # So với MỌI kỳ đã gặp, không chỉ kỳ liền trước. Bản chỉ so kề nhau đã
    # thủng trong sản xuất: sau khi dọn cụm Tết 2026, quy trình hàng ngày cào
    # lại các ngày thiếu và 2026-02-17 không còn ngày liền kề nào để so, nên
    # bản bịa lọt lại vào kho.
    seen: dict[tuple[str, ...], str] = {}
    for record in ordered:
        current = fingerprint(record)
        day = str(record["date"])[:10]
        if current in seen:
            drop.append(day)
        else:
            seen[current] = day
    return drop


def merge_stores(mine: Path, theirs: Path, out: Path) -> tuple[int, int, int]:
    """Hợp nhất hai bản kho theo ngày, ưu tiên bản ``theirs``.

    Vì sao cần: một lần backfill chạy 1,5 giờ, trong khi quy trình hàng ngày
    đẩy commit vào nhánh chính vài lần mỗi giờ. Đến lúc ghi thì checkout của
    runner đã cũ và ``git push`` bị từ chối — đã xảy ra thật, mất trọn một lần
    chạy đã lấy xong dữ liệu.

    Rebase không giải được: hai bên thêm dòng ở HAI ĐẦU khác nhau của cùng một
    tệp (backfill thêm kỳ cũ, quy trình hàng ngày thêm kỳ mới), nên git thấy
    xung đột nội dung. Nhưng ở mức dữ liệu thì không có xung đột nào cả: mỗi
    bản ghi khoá theo ngày và hai tập gần như rời nhau.

    ``theirs`` thắng khi trùng ngày, vì kỳ trên nhánh chính đã qua kiểm đồng
    thuận hai nguồn còn backfill chỉ đòi một nguồn.

    Args:
        mine: Bản kho của lần backfill.
        theirs: Bản kho hiện có trên nhánh chính.
        out: Nơi ghi kết quả hợp nhất.

    Returns:
        Bộ ``(số bản ghi của mine, của theirs, của kết quả)``.
    """
    def _load(path: Path) -> dict[str, dict]:
        if not path.exists():
            return {}
        rows = json.loads(path.read_text(encoding="utf-8"))
        return {str(row["date"]): row for row in rows}

    a, b = _load(mine), _load(theirs)
    merged = {**a, **b}
    ordered = [merged[k] for k in sorted(merged)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ordered, ensure_ascii=False), encoding="utf-8")
    logger.info("hợp nhất: %d + %d -> %d bản ghi", len(a), len(b), len(ordered))
    return len(a), len(b), len(ordered)

if __name__ == "__main__":
    sys.exit(main())
