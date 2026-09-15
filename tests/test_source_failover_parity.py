"""Quyết định CHUYỂN NGUỒN phải giống nhau ở hai bản mã.

Vì sao đây là phép đối chiếu riêng, không gộp vào phép so bản chụp: phép so
kia nhận sẵn một tập quan sát rồi kiểm cách DỰNG bản chụp. Quyết định "có gọi
tới tầng dự phòng không" xảy ra TRƯỚC đó, và nếu hai bản lệch nhau thì Worker
sẽ gọi sáu nguồn dự phòng trong khi bản Python chỉ gọi hai — hoặc ngược lại,
bản Python bỏ qua dự phòng ở đúng kỳ cần nó nhất.

Hỏng kiểu ấy KHÔNG làm sai số: cả hai bên vẫn trả kết quả hợp lệ. Nó chỉ làm
một bên không xác minh được, và im lặng.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from sources import (
    EXPECTED_COUNTS,
    PRIZE_ORDER,
    SourceObservation,
    independent_group_count,
    primary_tier_is_sufficient,
)

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


def _differs(field: str, index: int, value: str) -> dict[str, list[str]]:
    out = {k: list(v) for k, v in FULL.items()}
    out[field] = list(out[field])
    out[field][index] = value
    return out


def _obs(name: str, prize_map: dict[str, list[str]]) -> SourceObservation:
    return SourceObservation(name=name, tier="primary", priority=1, prize_map=prize_map)


CASES: list[tuple[str, list[tuple[str, dict[str, list[str]]]], int]] = [
    ("hai nguồn khớp nhau", [("xosothudo.com.vn", FULL), ("xoso.com.vn", FULL)], 2),
    ("một nguồn chết", [("xosothudo.com.vn", FULL), ("xoso.com.vn", EMPTY)], 2),
    ("cả hai chết", [("xosothudo.com.vn", EMPTY), ("xoso.com.vn", EMPTY)], 2),
    (
        "hai nguồn BẤT ĐỒNG ở giải Đặc Biệt",
        [("xosothudo.com.vn", FULL), ("xoso.com.vn", _differs("special", 0, "11111"))],
        2,
    ),
    (
        "bất đồng ở một ô giải bảy",
        [("xosothudo.com.vn", FULL), ("xoso.com.vn", _differs("prize7", 2, "99"))],
        2,
    ),
    (
        "hai tên miền cùng thương hiệu không phải hai lời chứng",
        [("www.minhngoc.net.vn", FULL), ("xosominhngoc.com", FULL)],
        2,
    ),
    ("đòi ba nhóm mà chỉ có hai", [("xosothudo.com.vn", FULL), ("xoso.com.vn", FULL)], 3),
    (
        "về số lệch nhịp: thiếu giá trị KHÔNG phải bất đồng",
        [("xosothudo.com.vn", FULL), ("xoso.com.vn", {**EMPTY, "special": ["83772"]})],
        2,
    ),
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
        {"observations": [[n, m] for n, m in obs], "min_agreement": agreement}
        for _, obs, agreement in CASES
    ]
    path = tmp_path / "failover.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [_require_node(), str(RUNNER), str(path)],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert proc.returncode == 0, f"bản JS hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_the_failover_decision_matches_case_for_case(tmp_path: Path) -> None:
    javascript = _javascript(tmp_path)
    assert len(javascript) == len(CASES)
    mismatched: list[str] = []
    for (label, obs, agreement), js in zip(CASES, javascript, strict=True):
        observations = [_obs(n, m) for n, m in obs]
        sufficient, reason = primary_tier_is_sufficient(
            observations, min_agreement=agreement
        )
        groups = independent_group_count(observations)
        if (sufficient, reason, groups) != (
            js["sufficient"], js["reason"], js["groups"]
        ):
            mismatched.append(
                f"  {label}: python=({sufficient}, {reason!r}, {groups}) "
                f"js=({js['sufficient']}, {js['reason']!r}, {js['groups']})"
            )
    assert not mismatched, "quyết định chuyển nguồn đã trôi lệch:\n" + "\n".join(mismatched)


def test_two_agreeing_primaries_do_not_reach_the_fallback_tier() -> None:
    sufficient, _ = primary_tier_is_sufficient(
        [_obs("xosothudo.com.vn", FULL), _obs("xoso.com.vn", FULL)]
    )
    assert sufficient is True


def test_a_dead_primary_reaches_the_fallback_tier() -> None:
    sufficient, reason = primary_tier_is_sufficient(
        [_obs("xosothudo.com.vn", FULL), _obs("xoso.com.vn", EMPTY)]
    )
    assert sufficient is False
    assert "nhóm độc lập" in reason


def test_two_live_but_disagreeing_primaries_also_reach_the_fallback_tier() -> None:
    """Đây là trường hợp dễ bỏ sót nhất, và là lý do chọn ngưỡng này.

    Cả hai nguồn chính đều trả HTTP 200 và đều đủ 27 giá trị — theo nghĩa
    "lỗi mạng/timeout" thì không có sự cố nào. Nhưng chúng nói hai số khác
    nhau, nên không xác minh được gì, và im lặng lấy nguồn ưu tiên cao hơn là
    cách một số sai lọt vào lịch sử. Phải gọi thêm nguồn để phá thế hoà.
    """
    sufficient, reason = primary_tier_is_sufficient(
        [
            _obs("xosothudo.com.vn", FULL),
            _obs("xoso.com.vn", _differs("special", 0, "11111")),
        ]
    )
    assert sufficient is False
    assert "bất đồng" in reason


def test_lagging_values_are_not_treated_as_disagreement() -> None:
    """Lúc đang quay số các nguồn về số lệch nhịp nhau — đó là bình thường.

    Nếu coi "thiếu giá trị" là bất đồng thì suốt cả kỳ quay, mọi lượt thăm dò
    đều kích hoạt sáu nguồn dự phòng: mỗi 5 giây một lần, vào đúng lúc các
    trang nguồn tải nặng nhất trong ngày.
    """
    sufficient, _ = primary_tier_is_sufficient(
        [
            _obs("xosothudo.com.vn", FULL),
            _obs("xoso.com.vn", {**EMPTY, "special": ["83772"]}),
        ]
    )
    assert sufficient is True


def test_sibling_domains_never_count_as_two_witnesses() -> None:
    sufficient, reason = primary_tier_is_sufficient(
        [_obs("www.minhngoc.net.vn", FULL), _obs("xosominhngoc.com", FULL)]
    )
    assert sufficient is False
    assert "1 nhóm độc lập" in reason


def test_a_source_returning_http_200_but_no_prizes_is_not_usable() -> None:
    """Mã trạng thái 200 mà trang đổi bố cục thì vẫn là hỏng."""
    assert _obs("xoso.com.vn", EMPTY).usable is False
    assert _obs("xoso.com.vn", {**EMPTY, "prize7": ["66"]}).usable is True


def test_the_full_fixture_really_is_a_complete_draw() -> None:
    """Nếu FULL thiếu ô thì mọi ca ở trên kiểm nhầm thứ khác mà vẫn xanh."""
    for key in PRIZE_ORDER:
        assert len(FULL[key]) == EXPECTED_COUNTS[key], key
