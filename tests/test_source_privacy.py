"""Không thứ gì ra tới trình duyệt được phép mang danh tính nguồn.

Đây là phép kiểm dạng QUÉT chứ không dạng liệt kê: nó tìm mọi chuỗi định danh
nguồn ở BẤT KỲ đâu trong tải trọng, kể cả những khoá sẽ được thêm về sau.

Lý do phải quét: tên nguồn nằm rải ở bốn chỗ khác nhau trong cùng một bản chụp
— ``source_status``, ``source_priority``, và bên trong ``slot_meta`` là
``support``, ``support_groups`` cùng các KHOÁ của ``observations``. Một phép
kiểm liệt kê từng khoá sẽ xanh trong khi khoá thứ năm ai đó vừa thêm thì lộ.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

import live_sync
import sources as sources_module
from sources import (
    PRIZE_ORDER,
    anonymise_snapshot,
    known_source_domains,
    public_group_code,
    public_source_code,
)

ROOT = Path(__file__).resolve().parents[1]

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


class _FakeSource:
    def __init__(self, name: str, pmap: dict[str, list[str]]):
        self.name = name
        self.pmap = pmap

    def fetch_partial(self, selected_date, http, *, live=False):
        return self.pmap


def _leaks(payload: object) -> list[str]:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    return [needle for needle in known_source_domains() if needle.lower() in blob]


def _raw_snapshot(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Bản chụp CHƯA ẩn danh, dựng từ những nguồn thật sự bất đồng.

    Bất đồng là quan trọng: chỉ khi có xung đột thì ``slot_meta.observations``
    mới mang nhiều hơn một giá trị, và mới lộ ra đủ tên nguồn để kiểm.
    """
    other = {k: list(v) for k, v in FULL.items()}
    other["special"] = ["11111"]
    fakes = [
        _FakeSource("xosothudo.com.vn", FULL),
        _FakeSource("xoso.com.vn", other),
        _FakeSource("xskt.vn", FULL),
        _FakeSource("mketqua.net", {k: [] for k in PRIZE_ORDER}),
        _FakeSource("www.minhngoc.net.vn", FULL),
        _FakeSource("xosominhngoc.com", FULL),
        _FakeSource("xosodaiphat.com", other),
        _FakeSource("hainhay.net", FULL),
    ]
    monkeypatch.setattr(sources_module, "primary_sources", lambda: fakes[:2])
    monkeypatch.setattr(sources_module, "fallback_sources", lambda: fakes[2:])
    monkeypatch.setattr(live_sync.requests, "Session", lambda: object())
    return live_sync.fetch_snapshot(now=datetime(2026, 8, 30, 11, 30, tzinfo=UTC))


def test_the_unredacted_snapshot_really_does_contain_names(monkeypatch) -> None:
    """Chốt chặn cho chính phép kiểm dưới.

    Nếu bản chưa ẩn danh KHÔNG chứa tên nào thì phép kiểm rò rỉ ở dưới xanh mà
    chẳng chứng minh điều gì — nó chỉ đang kiểm một tải trọng rỗng.
    """
    raw = _raw_snapshot(monkeypatch)
    assert len(_leaks(raw)) >= 5
    assert raw["slot_meta"]["special[0]"]["observations"]


def test_no_source_identity_survives_anonymisation(monkeypatch) -> None:
    public = anonymise_snapshot(_raw_snapshot(monkeypatch))
    assert _leaks(public) == []


def test_anonymisation_keeps_every_number_intact(monkeypatch) -> None:
    """Ẩn danh không được làm mất bằng chứng, chỉ làm mất danh tính."""
    raw = _raw_snapshot(monkeypatch)
    public = anonymise_snapshot(raw)
    for key in (
        "status", "complete", "verified_complete", "received_values",
        "expected_values", "verified_values", "progress_percent",
        "verification_percent", "prizes", "conflicts", "draw_date",
    ):
        assert public[key] == raw[key], key
    for slot, meta in raw["slot_meta"].items():
        assert public["slot_meta"][slot]["value"] == meta["value"]
        assert public["slot_meta"][slot]["verified"] == meta["verified"]
        assert len(public["slot_meta"][slot]["support"]) == len(meta["support"])


def test_error_messages_are_dropped_not_truncated() -> None:
    """Thông điệp lỗi của thư viện HTTP hầu như luôn kèm tên miền hoặc IP.

    Cắt ngắn không đủ: tên miền thường nằm ngay đầu chuỗi.
    """
    public = anonymise_snapshot({
        "source_status": [{
            "priority": 1, "source": "xoso.com.vn", "provider_group": "xoso",
            "error": "ConnectTimeout: HTTPSConnectionPool(host='xoso.com.vn', port=443)",
        }],
    })
    row = public["source_status"][0]
    assert "error" not in row
    assert row["failed"] is True
    assert row["source_code"] == "P2"
    assert _leaks(public) == []


def test_an_unknown_source_name_is_not_echoed_back() -> None:
    """Tên lạ phải thành "?", không được trả về chính nó.

    Trả về chính tên là cách một nguồn mới thêm vào mà quên đăng ký mã sẽ lộ
    ra ngoài — và lộ đúng lúc không ai để ý vì mọi thứ vẫn chạy.
    """
    assert public_source_code("bi-mat.example.com") == "?"
    assert public_group_code("bi-mat.example.com") == "?"


def test_the_public_audit_log_carries_no_domain_names() -> None:
    audit = json.loads((ROOT / "data" / "source_audit.json").read_text(encoding="utf-8"))
    assert audit, "tệp nhật ký rỗng thì phép kiểm này không chứng minh gì"
    assert _leaks(audit) == []


def test_the_reconciled_public_payload_carries_no_domain_names(tmp_path) -> None:
    out = tmp_path / "live.json"
    subprocess.run(
        [sys.executable, str(ROOT / "src" / "reconcile_live_canonical.py"),
         "--canonical", str(ROOT / "data" / "xsmb.csv"),
         "--audit", str(ROOT / "data" / "source_audit.json"),
         "--out", str(out)],
        cwd=ROOT, check=True, capture_output=True,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert _leaks(json.loads(out.read_text(encoding="utf-8"))) == []


def test_the_live_page_never_renders_a_source_field() -> None:
    """Lớp chặn thứ hai, ở phía trình duyệt.

    Dữ liệu tới đây đã ẩn danh từ máy chủ. Nhưng nếu về sau một trường tên
    miền lọt vào tải trọng, trang vẫn không được vẽ nó ra.
    """
    page = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    # Phải so KHỚP TRỌN thuộc tính: "source.source_code" chứa "source.source"
    # như một chuỗi con, nên phép so chuỗi con báo động giả — bản đầu của
    # phép kiểm này đã đỏ đúng vì thế.
    assert re.search(r"\bsource\.source\b(?!_)", page) is None
    assert "source.source_code" in page
    assert not [d for d in known_source_domains() if d in page]


def _complete_result(day):
    from dtos import Result

    return Result(
        date=day, special=83772, prize1=68785,
        prize2_1=50518, prize2_2=27452,
        prize3_1=57053, prize3_2=92810, prize3_3=56241,
        prize3_4=65128, prize3_5=33811, prize3_6=42264,
        prize4_1=4753, prize4_2=1152, prize4_3=6777, prize4_4=3507,
        prize5_1=9460, prize5_2=2913, prize5_3=3232,
        prize5_4=2999, prize5_5=3670, prize5_6=5129,
        prize6_1=939, prize6_2=751, prize6_3=594,
        prize7_1=66, prize7_2=21, prize7_3=34, prize7_4=78,
    )


class _WholeSource:
    def __init__(self, name: str):
        self.name = name

    def fetch(self, selected_date, http):
        return _complete_result(selected_date)

    def fetch_partial(self, selected_date, http, *, live=False):
        return FULL


@pytest.mark.parametrize("min_agreement", [1, 2])
def test_the_audit_writer_records_codes_not_domain_names(min_agreement: int) -> None:
    """Kiểm chính BỘ GHI, không chỉ tệp đã có trong kho.

    Tệp trong kho đã được chuyển đổi một lần. Nếu chỉ kiểm tệp thì bộ ghi vẫn
    có thể đang ghi tên miền, và nó sẽ lộ ra ở kỳ tiếp theo — một phép kiểm
    xanh suốt cho tới đúng lúc nó cần đỏ.

    Hai ngưỡng đồng thuận đi qua HAI nhánh ghi khác nhau trong ``fetch``.
    """
    from datetime import date

    from lottery import Lottery

    lot = Lottery(
        http=object(),
        sources=[_WholeSource("xosothudo.com.vn"), _WholeSource("xoso.com.vn")],
    )
    assert lot.fetch(date(2026, 9, 5), min_agreement=min_agreement) is True
    entry = lot._fetch_audit["2026-09-05"]
    assert _leaks(entry) == [], f"bộ ghi nhật ký để lộ tên nguồn: {entry}"
    assert set(entry["sources"]) <= {"P1", "P2"}
    if "independent_groups" in entry:
        assert set(entry["independent_groups"]) <= {"G1", "G2"}


def _node() -> str:
    import os
    import shutil

    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError("CI phải có node để chạy phép đối chiếu ẩn danh")
        pytest.skip("không có node trên máy chạy kiểm")
    return node


def _javascript_anonymised(payload: dict, tmp_path: Path) -> dict:
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [_node(), str(ROOT / "worker" / "test" / "run_anonymise.mjs"), str(path)],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert proc.returncode == 0, f"bản JS hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_the_worker_anonymiser_matches_the_python_one(monkeypatch, tmp_path) -> None:
    """Hai bản ẩn danh phải cho cùng một kết quả.

    Worker mới là thứ phục vụ trang live trong khung quay số; bản Python chỉ
    ghi tệp dự phòng. Nếu chỉ kiểm bản Python thì phần mã thật sự đứng ở ranh
    giới công khai lại là phần KHÔNG được kiểm.
    """
    raw = _raw_snapshot(monkeypatch)
    raw["source_priority"] = [
        "xosothudo.com.vn", "xoso.com.vn", "xskt.vn", "mketqua.net",
        "www.minhngoc.net.vn", "xosominhngoc.com", "xosodaiphat.com", "hainhay.net",
    ]
    python = anonymise_snapshot(raw)
    javascript = _javascript_anonymised(raw, tmp_path)
    assert _leaks(javascript) == [], "bản JS để lộ tên nguồn"
    for key in ("source_status", "source_priority", "slot_meta"):
        assert javascript[key] == python[key], key
