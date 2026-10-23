"""Quyết định CHUYỂN NGUỒN phải giống nhau ở hai bản mã.

Chính sách từ 13-10-2026: một nguồn chính, hai nguồn dự phòng chỉ được gọi khi nguồn chính
gặp sự cố (``sources.primary_has_failed`` / ``primaryHasFailed`` trong Worker). Quyết định
"có gọi dự phòng không" xảy ra TRƯỚC bước dựng bản chụp, nên phép so bản chụp không thấy nó.
Hai bản lệch nhau thì một bên gọi dự phòng ở mọi lượt, hoặc bỏ qua dự phòng đúng lúc nguồn
chính kẹt — không làm sai số, chỉ làm trang live đứng im.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from ingest.sources import EXPECTED_COUNTS, PRIZE_ORDER, SourceObservation, primary_has_failed
from core.time_policy import VIETNAM_TZ

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "worker" / "test" / "run_failover.mjs"

FULL = {
    "special": ["83772"],
    "prize1": ["68785"],
    "prize2": ["50518", "27452"],
    "prize3": ["57053", "92810", "56241", "65128", "33811", "42264"],
    "prize4": ["4753", "1152", "6777", "3507"],
    "prize5": ["9460", "2913", "3232", "2999", "3670", "5129"],
    "prize6": ["939", "751", "594"],
    "prize7": ["66", "21", "34", "78"],
}
EMPTY = {k: [] for k in PRIZE_ORDER}
PARTIAL = {**EMPTY, "prize1": ["68785"], "prize2": ["50518", "27452"]}


def _at(hhmmss: str) -> datetime:
    hour, minute, second = (int(x) for x in hhmmss.split(":"))
    return datetime(2026, 10, 13, hour, minute, second, tzinfo=VIETNAM_TZ)


CASES: list[tuple[str, dict[str, list[str]], str]] = [
    ("trước giờ quay, trang chưa có số", EMPTY, "17:55:00"),
    ("đang quay, mới về vài giải", PARTIAL, "18:20:00"),
    ("đủ giải lúc 18:33", FULL, "18:33:00"),
    ("thiếu ô một giây trước hạn", PARTIAL, "18:39:59"),
    ("thiếu ô đúng hạn 18:40", PARTIAL, "18:40:00"),
    ("thiếu ô lúc 23:00", PARTIAL, "23:00:00"),
    ("nguồn chết giữa lúc quay", EMPTY, "18:25:00"),
    ("đủ giải lúc 23:00", FULL, "23:00:00"),
]


def _require_node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError("CI phải có node để chạy phép đối chiếu chuyển nguồn")
        pytest.skip("không có node trên máy chạy kiểm")
    return node


def _javascript(tmp_path: Path) -> list[dict[str, object]]:
    payload = [
        {"prize_map": prize_map, "now_utc_ms": int(_at(when).timestamp() * 1000)}
        for _, prize_map, when in CASES
    ]
    path = tmp_path / "failover.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [_require_node(), str(RUNNER), str(path)],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert proc.returncode == 0, f"bản JS hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _python(prize_map: dict[str, list[str]], when: str) -> tuple[bool, str]:
    now = _at(when)
    return primary_has_failed(prize_map, target=now.date(), now=now)


def test_the_failover_decision_matches_case_for_case(tmp_path: Path) -> None:
    javascript = _javascript(tmp_path)
    assert len(javascript) == len(CASES)
    mismatched = [
        f"  {label}: python={_python(prize_map, when)} js=({js['failed']}, {js['reason']!r})"
        for (label, prize_map, when), js in zip(CASES, javascript, strict=True)
        if _python(prize_map, when) != (js["failed"], js["reason"])
    ]
    assert not mismatched, "quyết định chuyển nguồn đã trôi lệch:\n" + "\n".join(mismatched)


def test_a_primary_with_nothing_reaches_the_fallbacks() -> None:
    failed, reason = _python(EMPTY, "18:25:00")
    assert failed is True
    assert "không trả giá trị nào" in reason


def test_values_still_arriving_during_the_draw_are_not_a_failure() -> None:
    """Các giải về dần: gọi dự phòng ở mọi lượt thăm dò trong lúc quay là thứ phải tránh."""
    assert _python(PARTIAL, "18:20:00") == (False, "nguồn chính dùng được")
    assert _python(PARTIAL, "18:39:59")[0] is False


def test_a_primary_stuck_after_the_draw_reaches_the_fallbacks() -> None:
    failed, reason = _python(PARTIAL, "18:40:00")
    assert failed is True
    assert "3/27" in reason


def test_a_complete_primary_never_reaches_the_fallbacks() -> None:
    assert _python(FULL, "18:33:00")[0] is False
    assert _python(FULL, "23:00:00")[0] is False


def test_the_deadline_is_counted_on_the_draw_date() -> None:
    """Một lượt chạy sau nửa đêm cho kỳ HÔM QUA: 00:30 vẫn là sau hạn của ngày quay."""
    now = datetime(2026, 10, 14, 0, 30, tzinfo=VIETNAM_TZ)
    failed, _ = primary_has_failed(PARTIAL, target=_at("18:00:00").date(), now=now)
    assert failed is True


def test_a_source_returning_http_200_but_no_prizes_is_not_usable() -> None:
    """Mã trạng thái 200 mà trang đổi bố cục thì vẫn là hỏng."""
    obs = SourceObservation(name="xoso.com.vn", tier="primary", priority=1, prize_map=EMPTY)
    assert obs.usable is False


def test_the_fixtures_really_are_what_their_names_say() -> None:
    """Nếu FULL thiếu ô thì mọi ca ở trên kiểm nhầm thứ khác mà vẫn xanh."""
    for key in PRIZE_ORDER:
        assert len(FULL[key]) == EXPECTED_COUNTS[key], key
    assert sum(len(v) for v in PARTIAL.values()) == 3
