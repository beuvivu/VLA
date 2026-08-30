from __future__ import annotations

import logging
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


def _only_digits(s: str) -> str:
    return re.sub(r"\D+", "", s)


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
    return [token for token in re.findall(r"\b\d+\b", text) if len(token) == width]


def extract_partial_prize_map(text: str) -> dict[str, list[str]]:
    """Extract the best labelled XSMB prize block from page text.

    The six configured sources use slightly different labels (ĐB/G1/1, etc.).
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
        vals = [_only_digits(v) for v in prize_map.get(key, [])]
        vals = [v for v in vals if len(v) == EXPECTED_WIDTHS[key]]
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
    assert special and prize1 and prize2 and prize3 and prize4 and prize5 and prize6 and prize7

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

    def select_section(self, html: str, selected_date: date) -> str:
        return html

    def fetch_partial(self, selected_date: date, http: HttpClient, *, live: bool = False) -> dict[str, list[str]]:
        url = self.live_url(selected_date) if live else self.date_url(selected_date)
        html = _request_page(http, url, timeout=15 if live else 20)
        if not html:
            return {k: [] for k in PRIZE_ORDER}
        section = self.select_section(html, selected_date)
        return extract_partial_prize_map(section)

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


def default_sources() -> list[Source]:
    """Canonical source policy, in the exact business-priority order."""
    return [
        XosoComVnSource(),
        MketquaSource(),
        MinhNgocSource(),
        XosoMinhNgocSource(),
        XosoDaiPhatSource(),
        HainhaySource(),
    ]


SOURCE_INDEPENDENCE_GROUP = {
    "xoso.com.vn": "xoso",
    "mketqua.net": "mketqua",
    # These two domains are Minh Ngọc-branded mirrors and therefore count as
    # one independent provider for verification purposes.
    "www.minhngoc.net.vn": "minhngoc",
    "xosominhngoc.com": "minhngoc",
    "xosodaiphat.com": "xosodaiphat",
    "hainhay.net": "hainhay",
}


def source_independence_key(source_name: str) -> str:
    return SOURCE_INDEPENDENCE_GROUP.get(source_name, source_name)


def source_consensus_partial(
    partials: list[tuple[str, dict[str, list[str]]]],
    *,
    min_agreement: int = 2,
) -> tuple[dict[str, list[str]], dict[str, object]]:
    """Merge partial live results slot-by-slot using source priority + consensus.

    A value with >= ``min_agreement`` matching sources is verified.  If a live
    slot exists from only one source we expose the highest-priority value as
    provisional, but it is never promoted into canonical history by this helper.
    """
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
                    values.append((source_name, vals[idx]))
            counts: dict[str, list[str]] = defaultdict(list)
            for source_name, value in values:
                counts[value].append(source_name)

            chosen = ""
            support: list[str] = []
            support_groups: list[str] = []
            if counts:
                def consensus_score(item: tuple[str, list[str]]) -> tuple[int, int, int]:
                    names = item[1]
                    groups = {source_independence_key(name) for name in names}
                    first_priority = min(
                        i for i, (name, _) in enumerate(values) if name in names
                    )
                    return len(groups), len(names), -first_priority

                best_value, best_sources = max(counts.items(), key=consensus_score)
                best_groups = list(
                    dict.fromkeys(source_independence_key(name) for name in best_sources)
                )
                if len(best_groups) >= min_agreement:
                    chosen = best_value
                    support = best_sources
                    support_groups = best_groups
                    verified_slots += 1
                else:
                    # Priority fallback for display only.
                    chosen = values[0][1]
                    support = [values[0][0]]
                    support_groups = [source_independence_key(values[0][0])]
                if len(counts) > 1:
                    conflicts.append(f"{key}[{idx}]")

            if chosen:
                merged[key].append(chosen)
            slot_meta[f"{key}[{idx}]"] = {
                "value": chosen or None,
                "verified": len(support_groups) >= min_agreement,
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
