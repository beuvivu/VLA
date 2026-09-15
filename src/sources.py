from __future__ import annotations

import logging
import operator
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from bs4 import BeautifulSoup

from dtos import Result

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


def extract_partial_prize_map(text: str) -> dict[str, list[str]]:
    """Extract the best labelled XSMB prize block from page text.

    The six configured sources use slightly different labels (Đặc Biệt/G1/1, etc.).
    This parser finds candidate prize blocks, enforces exact prize widths and
    returns partial values without zero-filling.  It is therefore safe for live
    pages where some prizes are not available yet.
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
            next_idx = labels[pos + 1][0] if pos + 1 < len(labels) else min(len(lines), line_idx + 10)
            chunk = " ".join(lines[line_idx:next_idx])
            values = _valid_tokens(chunk, key)
            if values:
                prize_map[key] = values[: EXPECTED_COUNTS[key]]
            if key == "prize7":
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


def _request_page(http: HttpClient, url: str, *, timeout: int = 20) -> str:
    try:
        resp = http.get(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.debug("request failed %s: %s", url, exc)
        return ""
    if _get_status_code(resp) != 200:
        return ""
    return _get_text(resp)


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


@dataclass(frozen=True)
class XosoMinhNgocSource(_TextPageSource):
    name: str = "xosominhngoc.com"

    def date_url(self, selected_date: date) -> str:
        return f"https://www.xosominhngoc.com/kqxs/mien-bac/{selected_date:%d-%m-%Y}.html"

    def live_url(self, selected_date: date) -> str:
        return "https://www.xosominhngoc.com/xo-so-truc-tiep/mien-bac.html"


@dataclass(frozen=True)
class XosoDaiPhatSource(_TextPageSource):
    name: str = "xosodaiphat.com"

    def date_url(self, selected_date: date) -> str:
        return f"https://xosodaiphat.com/xsmb-{selected_date:%d-%m-%Y}.html"


@dataclass(frozen=True)
class HainhaySource(_TextPageSource):
    name: str = "hainhay.net"

    def date_url(self, selected_date: date) -> str:
        return "https://www.hainhay.net/so-ket-qua-truyen-thong/300"

    def live_url(self, selected_date: date) -> str:
        return "https://www.hainhay.net/"

    def select_section(self, html: str, selected_date: date) -> str:
        text = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
        date_patterns = [selected_date.strftime("%d/%m/%Y"), selected_date.strftime("%d-%m-%Y")]
        starts: list[int] = []
        for token in date_patterns:
            starts.extend(m.start() for m in re.finditer(re.escape(token), text))
        if not starts:
            return html
        start = min(starts)
        # Keep a bounded section.  Hainhay's page is a rolling ledger and the
        # next XSMB date follows shortly after the current block.
        next_markers = []
        for pattern in (r"XSMB\s*[>\-]", r"Kết Quả Miền Bắc\s*\("):
            m = re.search(pattern, text[start + 80 :], flags=re.IGNORECASE)
            if m:
                next_markers.append(start + 80 + m.start())
        end = min(next_markers) if next_markers else min(len(text), start + 5000)
        return text[start:end]


@dataclass(frozen=True)
class XsktVnSource(_TextPageSource):
    """Nguồn bù lịch sử từ sổ kết quả công khai của xskt.vn.

    Trang xskt.vn là một sổ cái cuộn chứa nhiều kỳ trong cùng một tài liệu.
    Vì vậy phải cắt đúng khối ngày được yêu cầu trước khi đưa qua bộ bóc giải
    dùng chung; nếu không, mọi ngày thiếu đều có nguy cơ nhận kết quả mới nhất.
    """

    name: str = "xskt.vn"

    def date_url(self, selected_date: date) -> str:
        # Dùng sổ cuộn thay vì gửi một lượt HTTP riêng cho từng ngày thiếu.
        # Tên đường dẫn do xskt.vn đặt; nguồn có thể chỉ trả một phần dải ngày,
        # vì vậy ngày không xuất hiện luôn được giữ là thiếu, không đoán bừa.
        return "https://xskt.vn/xsmb-500-ngay/"

    def live_url(self, selected_date: date) -> str:
        return "https://xskt.vn/"

    def select_section(self, html: str, selected_date: date) -> str:
        text = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
        tokens = (
            selected_date.strftime("%d-%m-%Y"),
            f"{selected_date.day}-{selected_date.month}-{selected_date.year}",
            selected_date.strftime("%d/%m/%Y"),
        )
        starts = [text.find(token) for token in tokens if text.find(token) >= 0]
        if not starts:
            return ""
        start = min(starts)
        # Một kỳ XSMB đầy đủ ngắn hơn rất nhiều; 8 000 ký tự đủ rộng để giữ
        # cả markup rời rạc nhưng vẫn dừng trước các bảng thống kê kế tiếp.
        return text[start : min(len(text), start + 8000)]


@dataclass(frozen=True)
class XosoThuDoSource(_TextPageSource):
    """Nguồn ưu tiên số một.

    Mẫu đường dẫn CHƯA kiểm chứng được từ môi trường phát triển: sandbox chặn
    toàn bộ HTTP ra ngoài (đã đo: ``example.com`` cũng trả 000). Vì vậy nguồn
    này khai báo nhiều ứng viên và thử lần lượt, thay vì chốt cứng một phỏng
    đoán rồi hỏng âm thầm.

    Rủi ro được chặn ở tầng dưới chứ không phải ở đây: một nguồn không bóc
    được gì thì đóng góp rỗng, và ``source_consensus_partial`` đòi ít nhất hai
    NHÓM nhà cung cấp độc lập khớp nhau mới đánh dấu đã xác minh. Nguồn hỏng
    làm mất bằng chứng, không làm sai dữ liệu.

    Kiểm chứng bằng ``.github/workflows/inspect-reference-pages.yml`` — runner
    của Actions gọi ra ngoài được. Khi biết mẫu đúng, rút danh sách còn một.
    """

    name: str = "xosothudo.com.vn"

    def date_url(self, selected_date: date) -> str:
        return self.date_urls(selected_date)[0]

    def date_urls(self, selected_date: date) -> tuple[str, ...]:
        return (
            f"https://xosothudo.com.vn/xsmb-{selected_date:%d-%m-%Y}.html",
            f"https://xosothudo.com.vn/ket-qua-xo-so-mien-bac/{selected_date:%d-%m-%Y}.html",
            f"https://xosothudo.com.vn/xsmb/{selected_date:%d-%m-%Y}.html",
        )

    def live_urls(self, selected_date: date) -> tuple[str, ...]:
        return (
            "https://xosothudo.com.vn/tuong-thuat-truc-tiep-xsmb.html",
            "https://xosothudo.com.vn/xsmb-truc-tiep.html",
            *self.date_urls(selected_date),
        )


#: Hai tầng ưu tiên. Thứ tự trong mỗi tuple CHÍNH LÀ thứ tự ưu tiên khi các
#: nguồn bất đồng, và cũng là thứ tự gọi.
PRIMARY_SOURCE_NAMES: tuple[str, ...] = ("xosothudo.com.vn", "xoso.com.vn")
FALLBACK_SOURCE_NAMES: tuple[str, ...] = (
    "xskt.vn",
    "mketqua.net",
    "www.minhngoc.net.vn",
    "xosominhngoc.com",
    "xosodaiphat.com",
    "hainhay.net",
)

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
        "xosothudo.com.vn": XosoThuDoSource(),
        "xoso.com.vn": XosoComVnSource(),
        "xskt.vn": XsktVnSource(),
        "mketqua.net": MketquaSource(),
        "www.minhngoc.net.vn": MinhNgocSource(),
        "xosominhngoc.com": XosoMinhNgocSource(),
        "xosodaiphat.com": XosoDaiPhatSource(),
        "hainhay.net": HainhaySource(),
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
    "xosothudo.com.vn": "xosothudo",
    "xoso.com.vn": "xoso",
    "mketqua.net": "mketqua",
    # These two domains are Minh Ngọc-branded mirrors and therefore count as
    # one independent provider for verification purposes.
    "www.minhngoc.net.vn": "minhngoc",
    "xosominhngoc.com": "minhngoc",
    "xosodaiphat.com": "xosodaiphat",
    "hainhay.net": "hainhay",
    "xskt.vn": "xskt",
}


def source_independence_key(source_name: str) -> str:
    return SOURCE_INDEPENDENCE_GROUP.get(source_name, source_name)


def source_consensus_partial(
    partials: list[tuple[str, dict[str, list[str]]]],
    *,
    min_agreement: int = 2,
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
    """Số NHÓM nhà cung cấp độc lập có dữ liệu dùng được.

    Đếm theo nhóm chứ không theo tên miền: hai trang cùng thương hiệu Minh Ngọc
    không phải hai lời chứng độc lập.
    """
    return len(
        {source_independence_key(o.name) for o in observations if o.usable}
    )


def primary_tier_is_sufficient(
    observations: list[SourceObservation], *, min_agreement: int = 2
) -> tuple[bool, str]:
    """Tầng chính có đủ để KHÔNG cần gọi dự phòng hay không, kèm lý do.

    Hai điều kiện, và điều kiện thứ hai mới là điều dễ bỏ sót:

    1. Đủ ``min_agreement`` nhóm độc lập trả về dữ liệu dùng được. Thiếu nhóm
       thì không thể xác minh, dù trang có trả HTTP 200.
    2. Các nhóm ấy KHÔNG bất đồng ở bất kỳ ô nào. Hai nguồn chính đều chạy tốt
       mà nói hai số khác nhau thì cũng không xác minh được gì — và im lặng
       chấp nhận một trong hai theo thứ tự ưu tiên là cách một số sai lọt vào
       lịch sử. Trường hợp này phải gọi thêm nguồn để phá thế hoà.

    Thiếu giá trị KHÔNG phải bất đồng: lúc đang quay số các nguồn về số lệch
    nhịp nhau là chuyện bình thường, và ``source_consensus_partial`` chỉ tính
    xung đột khi hai nguồn đưa ra hai GIÁ TRỊ khác nhau cho cùng một ô.
    """
    groups = independent_group_count(observations)
    if groups < min_agreement:
        return False, f"chỉ có {groups} nhóm độc lập, cần {min_agreement}"
    _, meta = source_consensus_partial(
        [(o.name, o.prize_map) for o in observations if o.usable],
        min_agreement=min_agreement,
    )
    conflicts = meta["conflicts"]
    if conflicts:
        return False, f"tầng chính bất đồng ở {len(conflicts)} ô"
    return True, "tầng chính đủ"


def fetch_with_failover(
    fetch_one,
    *,
    min_agreement: int = 2,
    run_batch=None,
) -> tuple[list[SourceObservation], dict[str, object]]:
    """Gọi tầng chính trước; chỉ chạm tới dự phòng khi tầng chính không đủ.

    ``fetch_one(source, tier, priority) -> SourceObservation`` do bên gọi cung
    cấp, nên hàm này không tự quyết định cách đi mạng và kiểm thử được bằng
    hàm giả. ``run_batch(jobs)`` cho phép bên gọi chạy song song; mặc định
    chạy tuần tự.

    Trả về mọi quan sát đã thực hiện, theo đúng thứ tự ưu tiên, kèm nhật ký
    nói rõ dự phòng có được kích hoạt hay không và vì sao.
    """
    if run_batch is None:
        def run_batch(jobs):
            return [fetch_one(*job) for job in jobs]

    primary_jobs = [
        (source, "primary", index)
        for index, source in enumerate(primary_sources(), start=1)
    ]
    observations = list(run_batch(primary_jobs))
    sufficient, reason = primary_tier_is_sufficient(
        observations, min_agreement=min_agreement
    )
    log: dict[str, object] = {
        "primary_attempted": len(primary_jobs),
        "primary_usable_groups": independent_group_count(observations),
        "fallback_activated": not sufficient,
        "reason": reason,
        "fallback_attempted": 0,
    }
    if sufficient:
        return observations, log

    offset = len(primary_jobs)
    fallback_jobs = [
        (source, "fallback", offset + index)
        for index, source in enumerate(fallback_sources(), start=1)
    ]
    observations.extend(run_batch(fallback_jobs))
    log["fallback_attempted"] = len(fallback_jobs)
    log["usable_groups"] = independent_group_count(observations)
    return observations, log


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
    """Mọi chuỗi định danh nguồn mà tải trọng công khai KHÔNG được chứa."""
    names = (*PRIMARY_SOURCE_NAMES, *FALLBACK_SOURCE_NAMES)
    groups = tuple(dict.fromkeys(SOURCE_INDEPENDENCE_GROUP[n] for n in names))
    bare = tuple(n.removeprefix("www.").split(".")[0] for n in names)
    return tuple(dict.fromkeys(names + groups + bare))
