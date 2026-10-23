from __future__ import annotations

import csv
import logging
import operator
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Final, Protocol

from bs4 import BeautifulSoup

from core.dtos import Result

logger = logging.getLogger(__name__)

EXPECTED_WIDTHS = {
    "special": 5,
    "prize1": 5,
    "prize2": 5,
    "prize3": 5,
    "prize4": 4,
    "prize5": 4,
    "prize6": 3,
    "prize7": 2,
}
EXPECTED_COUNTS = {
    "special": 1,
    "prize1": 1,
    "prize2": 2,
    "prize3": 6,
    "prize4": 4,
    "prize5": 6,
    "prize6": 3,
    "prize7": 4,
}
PRIZE_ORDER = ["special", "prize1", "prize2", "prize3", "prize4", "prize5", "prize6", "prize7"]


class HttpClient(Protocol):
    def get(self, url: str, timeout: int | float = ...) -> object: ...


class Source(Protocol):
    name: str

    def fetch(self, selected_date: date, http: HttpClient) -> Result | None: ...

    def fetch_partial(self, selected_date: date, http: HttpClient, *, live: bool = False) -> dict[str, list[str]]: ...


def _get_status_code(resp: object) -> int | None:
    return getattr(resp, "status_code", None)


def _get_text(resp: object) -> str:
    return getattr(resp, "text", "")


def _ascii_fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.replace("Đ", "D").replace("đ", "d").lower().strip()


_LABEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("special", re.compile(r"^(?:(?:giai|g)[.\s]*)?(?:db|dac\s+biet)\b")),
    ("prize1", re.compile(r"^(?:(?:giai|g)[.\s]*)?(?:nhat|1)\b")),
    ("prize2", re.compile(r"^(?:(?:giai|g)[.\s]*)?(?:nhi|2)\b")),
    ("prize3", re.compile(r"^(?:(?:giai|g)[.\s]*)?(?:ba|3)\b")),
    ("prize4", re.compile(r"^(?:(?:giai|g)[.\s]*)?(?:tu|4)\b")),
    ("prize5", re.compile(r"^(?:(?:giai|g)[.\s]*)?(?:nam|5)\b")),
    ("prize6", re.compile(r"^(?:(?:giai|g)[.\s]*)?(?:sau|6)\b")),
    ("prize7", re.compile(r"^(?:(?:giai|g)[.\s]*)?(?:bay|7)\b")),
]


def _label_key(line: str) -> str | None:
    folded = _ascii_fold(line)
    for key, pattern in _LABEL_PATTERNS:
        if pattern.search(folded):
            return key
    return None


def _valid_tokens(text: str, key: str) -> list[str]:
    width = EXPECTED_WIDTHS[key]
    # Require token boundaries, not merely digit boundaries.  Otherwise an
    # embedded identifier such as ``ABC12345XYZ`` can masquerade as a prize.
    # ``\w`` is Unicode-aware in Python, so full-width digits/letters cannot
    # flank an ASCII result and bypass the token boundary check.
    return re.findall(rf"(?<!\w)[0-9]{{{width}}}(?!\w)", text)


def _valid_prize_token(value: object, key: str) -> str | None:
    token = str(value).strip()
    width = EXPECTED_WIDTHS[key]
    return token if re.fullmatch(rf"[0-9]{{{width}}}", token) is not None else None


#: Một dòng tách thành các cụm chữ số ASCII và các cụm KHÁC; khoảng trắng, dấu phẩy, chấm
#: phẩy và gạch đứng chỉ là dấu phân cách.
_LINE_TOKEN = re.compile(r"[0-9]+|[^\s0-9,;|]+")


def _value_line_tokens(line: str, key: str) -> list[str] | None:
    """Giá trị của một dòng NẰM SAU nhãn giải, hoặc ``None`` nếu dòng ấy không phải hàng số.

    Hàng số chỉ gồm các số đúng độ rộng của giải và dấu phân cách. Mọi dòng khác — chữ
    ("Loto Miền Bắc", "Normal"), ngày tháng ("12/10", "XSMB 12/10/2026"), chữ số trần của
    ô chọn tháng ("8"), số tiền thưởng, ký hiệu chờ ("…", "-") — kết thúc hàng giải. Ba
    nguồn đều in mỗi giá trị trên một dòng và các ô chưa quay đứng SAU các ô đã quay, nên
    dừng ở dòng đầu tiên không phải hàng số không bỏ sót giá trị nào.

    Vì sao cần: giải 7 là nhãn CUỐI của bảng, nên trước đây khối số của nó kéo tới nhãn
    kế tiếp ở tận bảng lô tô hay ô chọn tháng. Khi giải 7 chưa quay, bộ bóc vớ số hai chữ
    số ở đó: ``xoso.com.vn`` cho ``["10", "11", "12"]`` (tháng), ``xosodaiphat.com`` cho
    ``["12", "10", "14", "10"]`` (ngày) — đo trên trang thật ngày 13-10-2026.
    """
    width = EXPECTED_WIDTHS[key]
    values: list[str] = []
    for token in _LINE_TOKEN.findall(line):
        if not (token.isascii() and token.isdigit()) or len(token) != width:
            return None
        values.append(token)
    return values


def _prize_row_values(lines: list[str], label_idx: int, stop_idx: int, key: str) -> list[str]:
    """Giá trị của một hàng giải: trên chính dòng nhãn, rồi các dòng hàng số ngay sau nó."""
    values = _valid_tokens(lines[label_idx], key)
    for idx in range(label_idx + 1, stop_idx):
        row = _value_line_tokens(lines[idx], key)
        if row is None:
            break
        values.extend(row)
    return values[: EXPECTED_COUNTS[key]]


def extract_partial_prize_map(text: str) -> dict[str, list[str]]:
    """Extract the best labelled XSMB prize block from page text.

    The configured sources use slightly different labels (Đặc Biệt/G1/1, etc.).
    This parser finds candidate prize blocks, enforces exact prize widths and
    returns partial values without zero-filling.  It is therefore safe for live
    pages where some prizes are not available yet: a prize's values are read from
    its label line and the pure number lines right after it, never from whatever
    text follows an empty row (``_value_line_tokens``).
    """
    soup = BeautifulSoup(text or "", "lxml")
    lines = [re.sub(r"\s+", " ", line).strip() for line in soup.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return {k: [] for k in PRIZE_ORDER}

    labels: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        key = _label_key(line)
        if key is not None:
            labels.append((idx, key))

    if not labels:
        return {k: [] for k in PRIZE_ORDER}

    # Pages may repeat prize labels in navigation/statistics.  Score every block
    # beginning at a special-prize label and keep the most complete, internally
    # ordered result block.
    candidates: list[dict[str, list[str]]] = []
    special_positions = [n for n, (_, key) in enumerate(labels) if key == "special"]
    if not special_positions:
        special_positions = [0]

    for label_pos in special_positions:
        prize_map: dict[str, list[str]] = {k: [] for k in PRIZE_ORDER}
        seen_order = -1
        for pos in range(label_pos, len(labels)):
            line_idx, key = labels[pos]
            key_order = PRIZE_ORDER.index(key)
            if pos > label_pos and key == "special":
                break
            if key_order < seen_order:
                # A new unrelated table has started.
                break
            seen_order = max(seen_order, key_order)
            next_idx = labels[pos + 1][0] if pos + 1 < len(labels) else len(lines)
            values = _prize_row_values(lines, line_idx, next_idx, key)
            if values:
                prize_map[key] = values
            # Giải 7 kết thúc bảng. Hai nhãn giải 7 liền nhau ("Giải bảy" rồi "G7") là
            # một hàng hai cột nhãn: nhãn đầu chưa cho số thì đọc tiếp nhãn sau.
            next_key = labels[pos + 1][1] if pos + 1 < len(labels) else None
            if key == "prize7" and (prize_map["prize7"] or next_key != "prize7"):
                break
        candidates.append(prize_map)

    def score(candidate: dict[str, list[str]]) -> tuple[int, int]:
        received = sum(len(candidate[k]) for k in PRIZE_ORDER)
        complete_fields = sum(len(candidate[k]) == EXPECTED_COUNTS[k] for k in PRIZE_ORDER)
        return received, complete_fields

    return max(candidates, key=score) if candidates else {k: [] for k in PRIZE_ORDER}


def _parse_result_from_prize_map(selected_date: date, *, prize_map: dict[str, list[str]]) -> Result | None:
    def full(key: str) -> list[int] | None:
        vals: list[str] = []
        for raw_value in prize_map.get(key, []):
            token = _valid_prize_token(raw_value, key)
            # External data is never "repaired" by stripping unexpected
            # characters.  Accept only ASCII decimal digits of the exact prize
            # width; anything else is rejected at the ingestion boundary.
            if token is not None:
                vals.append(token)
        if len(vals) < EXPECTED_COUNTS[key]:
            return None
        return [int(v) for v in vals[: EXPECTED_COUNTS[key]]]

    p = {key: full(key) for key in PRIZE_ORDER}
    if any(p[key] is None for key in PRIZE_ORDER):
        return None

    special = p["special"]
    prize1 = p["prize1"]
    prize2 = p["prize2"]
    prize3 = p["prize3"]
    prize4 = p["prize4"]
    prize5 = p["prize5"]
    prize6 = p["prize6"]
    prize7 = p["prize7"]
    if not all((special, prize1, prize2, prize3, prize4, prize5, prize6, prize7)):
        raise RuntimeError("validated prize map unexpectedly contains an empty prize")

    return Result(
        date=selected_date,
        special=special[0],
        prize1=prize1[0],
        prize2_1=prize2[0], prize2_2=prize2[1],
        prize3_1=prize3[0], prize3_2=prize3[1], prize3_3=prize3[2],
        prize3_4=prize3[3], prize3_5=prize3[4], prize3_6=prize3[5],
        prize4_1=prize4[0], prize4_2=prize4[1], prize4_3=prize4[2], prize4_4=prize4[3],
        prize5_1=prize5[0], prize5_2=prize5[1], prize5_3=prize5[2],
        prize5_4=prize5[3], prize5_5=prize5[4], prize5_6=prize5[5],
        prize6_1=prize6[0], prize6_2=prize6[1], prize6_3=prize6[2],
        prize7_1=prize7[0], prize7_2=prize7[1], prize7_3=prize7[2], prize7_4=prize7[3],
    )


#: Trần kích thước một trang nguồn, tính bằng byte.
#:
#: Trang kết quả thật nặng vài trăm KB, nên 8 MiB đã rộng gấp hơn hai chục lần
#: mà vẫn chặn được trường hợp một nguồn bị chiếm hoặc hỏng trả về thân phản
#: hồi vô hạn. Hạn thời gian KHÔNG thay được trần này: trong 20 giây một máy
#: chủ vẫn kịp đẩy hàng gigabyte, và runner nuốt trọn vào bộ nhớ.
MAX_PAGE_BYTES: Final[int] = 8 * 1024 * 1024


def _declared_length(resp: object) -> int | None:
    """Số byte mà máy chủ TỰ KHAI trong ``Content-Length``, nếu có."""
    headers = getattr(resp, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    try:
        return int(headers.get("Content-Length"))
    except (TypeError, ValueError):
        return None


def _request_page(http: HttpClient, url: str, *, timeout: int = 20) -> str:
    """Lấy một trang nguồn, có trần kích thước.

    Nguồn là bên NGOÀI và không đáng tin theo mặc định: dự án có sẵn cả một
    chính sách nguồn nhiều tầng vì đúng lý do ấy. Nhưng thân phản hồi thì trước
    nay đọc thẳng vào bộ nhớ, không giới hạn.

    Trần chặn chắc phần PHÂN TÍCH trong mọi trường hợp, và chặn cả phần CẤP
    PHÁT khi máy chủ khai đúng ``Content-Length``. Chặn cấp phát trong mọi
    trường hợp thì phải chuyển cả lớp khách sang đọc theo luồng — đắt hơn
    nhiều, và không tương xứng với mối đe doạ ở đây khi mọi nguồn đều qua TLS
    còn token của CI chỉ có quyền đọc. Ghi rõ giới hạn này thay vì để người
    đọc tưởng nó kín.
    """
    try:
        resp = http.get(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.debug("request failed %s: %s", url, exc)
        return ""
    if _get_status_code(resp) != 200:
        return ""

    declared = _declared_length(resp)
    if declared is not None and declared > MAX_PAGE_BYTES:
        logger.warning("bỏ qua trang quá lớn: khai %d byte, trần %d", declared, MAX_PAGE_BYTES)
        return ""

    text = _get_text(resp)
    # Một byte UTF-8 không bao giờ nhỏ hơn một ký tự, nên so theo số ký tự là
    # cách kiểm rẻ và luôn thiên về phía an toàn.
    if len(text) > MAX_PAGE_BYTES:
        logger.warning("bỏ qua trang quá lớn: %d ký tự, trần %d", len(text), MAX_PAGE_BYTES)
        return ""
    return text


class _TextPageSource:
    name = "source"

    def date_url(self, selected_date: date) -> str:
        raise NotImplementedError

    def live_url(self, selected_date: date) -> str:
        return self.date_url(selected_date)

    def date_urls(self, selected_date: date) -> tuple[str, ...]:
        """Các đường dẫn ứng viên cho một kỳ, thử theo thứ tự.

        Hầu hết nguồn chỉ có một mẫu đã kiểm chứng nên trả về đúng một phần
        tử. Nhiều phần tử dành cho nguồn mà mẫu đường dẫn CHƯA kiểm chứng
        được từ môi trường này: thử lần lượt cho tới khi có khối giải bóc
        được, thay vì chốt cứng một phỏng đoán rồi hỏng âm thầm.
        """
        return (self.date_url(selected_date),)

    def live_urls(self, selected_date: date) -> tuple[str, ...]:
        return (self.live_url(selected_date),)

    def select_section(self, html: str, selected_date: date) -> str:
        return html

    def fetch_partial(self, selected_date: date, http: HttpClient, *, live: bool = False) -> dict[str, list[str]]:
        urls = self.live_urls(selected_date) if live else self.date_urls(selected_date)
        empty = {k: [] for k in PRIZE_ORDER}
        best = empty
        best_score = 0
        for url in urls:
            html = _request_page(http, url, timeout=15 if live else 20)
            if not html:
                continue
            prize_map = extract_partial_prize_map(self.select_section(html, selected_date))
            score = sum(len(prize_map[k]) for k in PRIZE_ORDER)
            if score > best_score:
                best, best_score = prize_map, score
            if best_score == sum(EXPECTED_COUNTS.values()):
                break
        return best

    def fetch(self, selected_date: date, http: HttpClient) -> Result | None:
        prize_map = self.fetch_partial(selected_date, http, live=False)
        return _parse_result_from_prize_map(selected_date, prize_map=prize_map)


@dataclass(frozen=True)
class XosoComVnSource(_TextPageSource):
    name: str = "xoso.com.vn"

    def date_url(self, selected_date: date) -> str:
        return f"https://xoso.com.vn/xsmb-{selected_date:%d-%m-%Y}.html"

    def live_url(self, selected_date: date) -> str:
        return "https://xoso.com.vn/tuong-thuat-mien-bac/xsmb-tructiep.html"


@dataclass(frozen=True)
class MketquaSource(_TextPageSource):
    name: str = "mketqua.net"

    def date_url(self, selected_date: date) -> str:
        # Date-specific page is more deterministic than the rolling ledger.
        return (
            "https://mketqua.net/x%E1%BB%95-s%E1%BB%91-Truy%E1%BB%81n-Th%E1%BB%91ng/"
            f"{selected_date:%d-%m-%Y}.html"
        )

    def live_url(self, selected_date: date) -> str:
        return "https://mketqua.net/xo-so-truyen-thong.php"


@dataclass(frozen=True)
class MinhNgocSource(_TextPageSource):
    name: str = "www.minhngoc.net.vn"

    def date_url(self, selected_date: date) -> str:
        return f"https://www.minhngoc.net.vn/ket-qua-xo-so/mien-bac/{selected_date:%d-%m-%Y}.html"

    def live_url(self, selected_date: date) -> str:
        return "https://www.minhngoc.net.vn/xo-so-truc-tiep/mien-bac.html"


#: Chính sách nguồn từ 13-10-2026: MỘT nguồn chính, hai nguồn dự phòng chỉ được gọi khi
#: nguồn chính gặp sự cố (``primary_has_failed``). Thứ tự trong mỗi tuple là thứ tự gọi và
#: thứ tự ưu tiên hiển thị.
#:
#: Năm nguồn đã nghỉ, đo trên runner ngày 12/13-10-2026: ``xosothudo.com.vn`` (mẫu đường
#: dẫn chưa từng đúng, cả năm ứng viên đều hỏng) và ``xskt.vn`` (chặn runner) không trả gì
#: ở bất kỳ lượt nào; ``xosodaiphat.com`` bóc ngày tháng thành giải 7 khi kỳ chưa quay;
#: ``hainhay.net`` mất trọn giải 7 vì hai nhãn liền nhau; ``xosominhngoc.com`` chỉ là bản
#: sao của Minh Ngọc. Vì nguồn số một luôn hỏng, tầng chính chưa bao giờ đủ hai nhóm và cả
#: sáu nguồn dự phòng bị gọi ở MỌI lượt thăm dò.
PRIMARY_SOURCE_NAMES: tuple[str, ...] = ("xoso.com.vn",)
FALLBACK_SOURCE_NAMES: tuple[str, ...] = ("mketqua.net", "www.minhngoc.net.vn")

#: Tên của các nguồn đã nghỉ. Không còn được gọi, nhưng tải trọng công khai vẫn không được
#: nhắc tới chúng (``known_source_domains``).
RETIRED_SOURCE_NAMES: tuple[str, ...] = (
    "xosothudo.com.vn",
    "xskt.vn",
    "xosominhngoc.com",
    "xosodaiphat.com",
    "hainhay.net",
)

#: Giờ Việt Nam mà kỳ quay chắc chắn đã xong (đặc biệt về lúc 18:30–18:35). Sau mốc này,
#: nguồn chính còn thiếu ô là sự cố, không phải "đang quay".
PRIMARY_COMPLETE_BY: Final[dtime] = dtime(18, 40)

#: Nguồn của lớp dữ liệu Miền Trung/Miền Nam (``regional_lottery``). KHÔNG thuộc
#: chuỗi nguồn XSMB: không đồng thuận, không dự phòng cho kỳ Miền Bắc. Vietlott
#: không còn dùng nguồn này từ 07-10-2026: dữ liệu đến từ engine ``vietlott/``.
REGIONAL_SOURCE_NAMES: tuple[str, ...] = ("xskt.com.vn",)

#: Nguồn của lớp bù trong API Sổ kết quả của Worker (``worker/src/traditional_results.js``).
#: Chỉ cron gọi, chỉ khi lịch sử chuẩn còn thiếu ngày; KHÔNG thuộc chuỗi nguồn live hay chốt
#: kết quả XSMB ở trên.
HISTORY_API_SOURCE_NAMES: tuple[str, ...] = ("xskt.vn",)

#: Mã công khai thay cho tên miền. Mọi thứ ra tới trình duyệt phải dùng mã này.
#:
#: Không phải để làm đẹp: yêu cầu là KHÔNG để lộ tên miền nguồn trên giao diện
#: hay trong network request của client. Mã phải ỔN ĐỊNH để còn đối chiếu được
#: giữa các kỳ, nên nó bám theo tầng và vị trí chứ không băm ngẫu nhiên.
SOURCE_PUBLIC_CODE: dict[str, str] = {
    **{name: f"P{i}" for i, name in enumerate(PRIMARY_SOURCE_NAMES, start=1)},
    **{name: f"F{i}" for i, name in enumerate(FALLBACK_SOURCE_NAMES, start=1)},
}


def public_source_code(source_name: str) -> str:
    """Mã ẩn danh của một nguồn. Tên lạ trả "?" chứ không trả chính tên."""
    return SOURCE_PUBLIC_CODE.get(source_name, "?")


def _source_registry() -> dict[str, Source]:
    return {
        "xoso.com.vn": XosoComVnSource(),
        "mketqua.net": MketquaSource(),
        "www.minhngoc.net.vn": MinhNgocSource(),
    }


def primary_sources() -> list[Source]:
    registry = _source_registry()
    return [registry[name] for name in PRIMARY_SOURCE_NAMES]


def fallback_sources() -> list[Source]:
    registry = _source_registry()
    return [registry[name] for name in FALLBACK_SOURCE_NAMES]


def default_sources() -> list[Source]:
    """Toàn bộ nguồn, đúng thứ tự ưu tiên: tầng chính trước, dự phòng sau."""
    return primary_sources() + fallback_sources()


SOURCE_INDEPENDENCE_GROUP = {
    "xoso.com.vn": "xoso",
    "mketqua.net": "mketqua",
    "www.minhngoc.net.vn": "minhngoc",
}


def source_independence_key(source_name: str) -> str:
    return SOURCE_INDEPENDENCE_GROUP.get(source_name, source_name)


def source_consensus_partial(
    partials: list[tuple[str, dict[str, list[str]]]],
    *,
    min_agreement: int = 1,
) -> tuple[dict[str, list[str]], dict[str, object]]:
    """Merge partial live results slot-by-slot using source priority + consensus.

    A value is verified only when it has >= ``min_agreement`` independent source
    groups and no different value has the same independent support.  Otherwise
    the highest-priority observation may be shown provisionally but is never
    marked verified or promoted into canonical history by this helper.
    """
    if isinstance(min_agreement, bool):
        raise ValueError("min_agreement must be an integer >= 1")
    try:
        min_agreement = operator.index(min_agreement)
    except TypeError as exc:
        raise ValueError("min_agreement must be an integer >= 1") from exc
    if min_agreement < 1:
        raise ValueError("min_agreement must be an integer >= 1")
    merged = {k: [] for k in PRIZE_ORDER}
    slot_meta: dict[str, dict[str, object]] = {}
    conflicts: list[str] = []
    verified_slots = 0
    total_slots = sum(EXPECTED_COUNTS.values())

    for key in PRIZE_ORDER:
        for idx in range(EXPECTED_COUNTS[key]):
            values: list[tuple[str, str]] = []
            for source_name, pmap in partials:
                vals = pmap.get(key, [])
                if idx < len(vals):
                    token = _valid_prize_token(vals[idx], key)
                    if token is not None:
                        values.append((source_name, token))
            counts: dict[str, list[str]] = defaultdict(list)
            for source_name, value in values:
                counts[value].append(source_name)

            chosen = ""
            support: list[str] = []
            support_groups: list[str] = []
            ambiguous_tie = False
            if counts:
                observed_values = tuple(values)

                def consensus_score(
                    item: tuple[str, list[str]],
                    observations: tuple[tuple[str, str], ...] = observed_values,
                ) -> tuple[int, int, int]:
                    names = item[1]
                    groups = {source_independence_key(name) for name in names}
                    first_priority = min(
                        i
                        for i, (name, _) in enumerate(observations)
                        if name in names
                    )
                    return len(groups), len(names), -first_priority

                ranked = sorted(counts.items(), key=consensus_score, reverse=True)
                best_value, best_sources = ranked[0]
                best_groups = list(
                    dict.fromkeys(source_independence_key(name) for name in best_sources)
                )
                runner_up_groups = 0
                if len(ranked) > 1:
                    runner_up_groups = len(
                        {source_independence_key(name) for name in ranked[1][1]}
                    )
                    ambiguous_tie = (
                        len(best_groups) >= min_agreement
                        and runner_up_groups == len(best_groups)
                    )

                if len(best_groups) >= min_agreement and not ambiguous_tie:
                    chosen = best_value
                    support = best_sources
                    support_groups = best_groups
                    verified_slots += 1
                else:
                    # Priority fallback is display-only. In particular, an
                    # equal-support 2-vs-2 split is never marked verified.
                    chosen = values[0][1]
                    support = [values[0][0]]
                    support_groups = [source_independence_key(values[0][0])]
                if len(counts) > 1:
                    conflicts.append(f"{key}[{idx}]")

            if chosen:
                merged[key].append(chosen)
            slot_meta[f"{key}[{idx}]"] = {
                "value": chosen or None,
                "verified": len(support_groups) >= min_agreement and not ambiguous_tie,
                "ambiguous_tie": ambiguous_tie,
                "support": support,
                "support_groups": support_groups,
                "observations": {value: names for value, names in counts.items()},
            }

    received = sum(len(v) for v in merged.values())
    return merged, {
        "received_slots": received,
        "total_slots": total_slots,
        "verified_slots": verified_slots,
        "conflicts": conflicts,
        "slot_meta": slot_meta,
    }


# --- Cơ chế chuyển nguồn -----------------------------------------------------


@dataclass(frozen=True)
class SourceObservation:
    """Một lượt gọi tới một nguồn, kèm đủ dữ kiện để giải thích vì sao."""

    name: str
    tier: str
    priority: int
    prize_map: dict[str, list[str]]
    error: str | None = None
    latency_ms: int = 0

    @property
    def usable(self) -> bool:
        """Có bóc được ít nhất một giá trị giải hay không.

        Trạng thái HTTP 200 mà trang đổi bố cục thì vẫn là hỏng. Đếm theo giá
        trị bóc được, không đếm theo mã trạng thái.
        """
        return any(self.prize_map.get(key) for key in PRIZE_ORDER)


def independent_group_count(observations: list[SourceObservation]) -> int:
    """Số NHÓM nhà cung cấp độc lập có dữ liệu dùng được."""
    return len(
        {source_independence_key(o.name) for o in observations if o.usable}
    )


#: Lỗi ghi cho một nguồn còn hiện kỳ TRƯỚC; Python và Worker dùng đúng chuỗi này.
STALE_PAGE_ERROR: Final[str] = "StalePage: nguồn còn hiện kỳ trước"


def shows_previous_draw(
    prize_map: dict[str, list[str]], previous: dict[str, list[str]] | None
) -> bool:
    """Nguồn còn hiện kỳ TRƯỚC: có giá trị, và MỌI giá trị trùng đúng ô của kỳ đã lưu gần nhất.

    Đo trên runner lúc 00:37 ngày 13-10-2026: trang live của cả ba nguồn, và trang theo ngày
    13-10 của mketqua/minhngoc, đều hiện trọn kỳ 12-10. Sổ chuẩn có chốt "trùng khít kỳ đã
    lưu" (``Lottery``), bản chụp live thì chưa: lượt thăm dò gặp trang chưa xoá bảng sẽ báo kỳ
    hôm nay "đã xác minh" bằng số của hôm qua rồi dừng thăm dò. Kỳ mới về dần từ giải nhất
    (năm chữ số), nên một trang đang quay trùng kỳ trước ở mọi ô đã về gần như không thể.
    """
    if not previous:
        return False
    received = 0
    for key in PRIZE_ORDER:
        before = previous.get(key, [])
        for index, value in enumerate(prize_map.get(key, [])):
            if index >= len(before) or value != before[index]:
                return False
            received += 1
    return received > 0


def load_previous_draw(path: Path, *, before: date) -> dict[str, list[str]] | None:
    """Bảng giải của kỳ đã lưu gần nhất TRƯỚC ``before`` trong sổ chuẩn, hoặc ``None``."""
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = [r for r in csv.DictReader(handle) if str(r.get("date", ""))[:10] < before.isoformat()]
    except OSError:
        return None
    if not rows:
        return None
    row = max(rows, key=lambda r: str(r["date"])[:10])

    def column(key: str, index: int) -> str:
        name = key if EXPECTED_COUNTS[key] == 1 else f"{key}_{index}"
        value = str(row.get(name, "") or "").strip()
        return value.zfill(EXPECTED_WIDTHS[key]) if value.isdigit() else value

    return {
        key: [column(key, i) for i in range(1, EXPECTED_COUNTS[key] + 1)] for key in PRIZE_ORDER
    }


def primary_has_failed(
    prize_map: dict[str, list[str]], *, target: date, now: datetime
) -> tuple[bool, str]:
    """Nguồn chính có gặp sự cố hay không, kèm lý do. Chỉ khi có sự cố mới gọi dự phòng.

    Hai dạng sự cố:

    1. Không bóc được giá trị nào: lỗi mạng, HTTP khác 200, hay trang đổi bố cục. Trước giờ
       quay, mọi nguồn đều rỗng, nên gọi dự phòng lúc ấy chỉ tốn thêm yêu cầu — vô hại.
    2. Đã qua ``PRIMARY_COMPLETE_BY`` của ngày quay mà nguồn chính vẫn thiếu ô: trang kẹt,
       không còn là "đang quay".

    Thiếu ô TRONG lúc quay là bình thường — các giải về dần — nên không phải sự cố.
    """
    received = sum(len(prize_map.get(k, [])) for k in PRIZE_ORDER)
    if received == 0:
        return True, "nguồn chính không trả giá trị nào"
    deadline = datetime.combine(target, PRIMARY_COMPLETE_BY, tzinfo=now.tzinfo)
    total = sum(EXPECTED_COUNTS.values())
    if received < total and now >= deadline:
        return True, f"đã quá {PRIMARY_COMPLETE_BY:%H:%M} mà nguồn chính mới có {received}/{total}"
    return False, "nguồn chính dùng được"


def fetch_with_failover(
    fetch_one,
    *,
    target: date,
    now: datetime,
    run_batch=None,
    min_agreement: int = 1,
) -> tuple[list[SourceObservation], dict[str, object]]:
    """Gọi nguồn chính; chỉ gọi dự phòng khi nguồn chính gặp sự cố (``primary_has_failed``).

    ``fetch_one(source, tier, priority) -> SourceObservation`` do bên gọi cung cấp, nên hàm
    này không tự đi mạng và kiểm thử được bằng hàm giả. ``run_batch(jobs)`` cho phép chạy
    song song hai nguồn dự phòng; mặc định chạy tuần tự.

    Nguồn chính là MỘT nhóm, nên ngưỡng ``min_agreement > 1`` (vẫn cấu hình được) cần thêm
    nhân chứng: khi ấy dự phòng luôn được gọi. Nếu không, một nguồn chính đủ 27 ô "dùng được"
    mà không bao giờ đạt ngưỡng, và vòng thăm dò chạy tới hạn chót.

    Bên gọi chỉ loại quan sát của nguồn chính khỏi phép hợp nhất khi ``primary_failed``: nó đã
    hỏng, và bản rỗng hay kẹt của nó không được che giá trị của dự phòng.
    """
    if run_batch is None:
        def run_batch(jobs):
            return [fetch_one(*job) for job in jobs]

    primary_jobs = [
        (source, "primary", index)
        for index, source in enumerate(primary_sources(), start=1)
    ]
    primary = list(run_batch(primary_jobs))
    failed, reason = primary_has_failed(primary[0].prize_map, target=target, now=now)
    witnesses = min_agreement > 1
    if witnesses and not failed:
        reason = f"cần {min_agreement} nhóm độc lập xác nhận"
    log: dict[str, object] = {
        "primary_attempted": len(primary_jobs),
        "primary_failed": failed,
        "fallback_activated": failed or witnesses,
        "reason": reason,
        "fallback_attempted": 0,
    }
    if not log["fallback_activated"]:
        return primary, log

    offset = len(primary_jobs)
    fallback_jobs = [
        (source, "fallback", offset + index)
        for index, source in enumerate(fallback_sources(), start=1)
    ]
    observations = list(run_batch(fallback_jobs))
    log["fallback_attempted"] = len(fallback_jobs)
    log["usable_groups"] = independent_group_count(observations)
    return primary + observations, log


# --- Ẩn nguồn khỏi mọi thứ ra tới trình duyệt --------------------------------
#
# Vì sao phải có một tầng riêng thay vì "nhớ đừng in tên ra": tên nguồn nằm rải
# ở bốn chỗ khác nhau trong cùng một bản chụp — ``source_status``,
# ``source_priority``, và bên trong ``slot_meta`` là ``support``,
# ``support_groups`` cùng các khoá của ``observations``. Bỏ sót một chỗ là lộ
# hết, nên phép ẩn danh phải là MỘT hàm duy nhất có thể kiểm được, và có một
# phép kiểm quét toàn bộ tải trọng tìm tên miền.

#: Mã nhóm nhà cung cấp, ẩn danh và ổn định.
SOURCE_PUBLIC_GROUP_CODE: dict[str, str] = {
    key: f"G{index}"
    for index, key in enumerate(
        dict.fromkeys(
            SOURCE_INDEPENDENCE_GROUP[name]
            for name in (*PRIMARY_SOURCE_NAMES, *FALLBACK_SOURCE_NAMES)
        ),
        start=1,
    )
}


def public_group_code(source_name_or_group: str) -> str:
    """Mã nhóm ẩn danh. Nhận cả tên nguồn lẫn khoá nhóm."""
    key = SOURCE_INDEPENDENCE_GROUP.get(source_name_or_group, source_name_or_group)
    return SOURCE_PUBLIC_GROUP_CODE.get(key, "?")


def anonymise_slot_meta(slot_meta: dict[str, object]) -> dict[str, object]:
    """Thay mọi tên nguồn trong siêu dữ liệu từng ô bằng mã ẩn danh."""
    out: dict[str, object] = {}
    for slot, raw in slot_meta.items():
        meta = dict(raw) if isinstance(raw, dict) else {}
        meta["support"] = [public_source_code(n) for n in meta.get("support", [])]
        meta["support_groups"] = [
            public_group_code(g) for g in meta.get("support_groups", [])
        ]
        observations = meta.get("observations", {})
        meta["observations"] = {
            value: [public_source_code(n) for n in names]
            for value, names in (
                observations.items() if isinstance(observations, dict) else []
            )
        }
        out[slot] = meta
    return out


def anonymise_source_status(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Bỏ tên miền khỏi bảng trạng thái nguồn, giữ mọi thứ còn lại.

    ``error`` bị bỏ hẳn chứ không cắt ngắn: thông điệp lỗi của thư viện HTTP
    hầu như luôn kèm tên miền hoặc địa chỉ IP. Lý do hỏng vẫn giữ được ở dạng
    cờ ``failed``, đủ để người xem biết có nguồn trục trặc.
    """
    out: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        name = str(row.pop("source", ""))
        row.pop("provider_group", None)
        error = row.pop("error", None)
        row["source_code"] = public_source_code(name)
        row["provider_code"] = public_group_code(name)
        row["failed"] = error is not None
        out.append(row)
    return out


def anonymise_snapshot(payload: dict[str, object]) -> dict[str, object]:
    """Bản chụp công khai: giữ nguyên mọi con số, bỏ sạch danh tính nguồn."""
    public = dict(payload)
    status = public.get("source_status")
    if isinstance(status, list):
        public["source_status"] = anonymise_source_status(status)
    if "source_priority" in public:
        public["source_priority"] = [
            public_source_code(name)
            for name in (*PRIMARY_SOURCE_NAMES, *FALLBACK_SOURCE_NAMES)
        ]
    slot_meta = public.get("slot_meta")
    if isinstance(slot_meta, dict):
        public["slot_meta"] = anonymise_slot_meta(slot_meta)
    return public


def known_source_domains() -> tuple[str, ...]:
    """Mọi chuỗi định danh nguồn mà tải trọng công khai KHÔNG được chứa.

    Gồm cả nguồn đã nghỉ: nghỉ không làm tên của chúng thành được phép in ra.
    """
    names = (*PRIMARY_SOURCE_NAMES, *FALLBACK_SOURCE_NAMES, *RETIRED_SOURCE_NAMES)
    groups = tuple(dict.fromkeys(SOURCE_INDEPENDENCE_GROUP.get(n, n) for n in names))
    bare = tuple(n.removeprefix("www.").split(".")[0] for n in names)
    return tuple(dict.fromkeys(names + groups + bare))
