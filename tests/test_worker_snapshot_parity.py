"""Payload live.json của Worker phải giống hệt bản Python.

Đây là phép đối chiếu cuối và là phép quan trọng nhất trong ba phép: nó so
TOÀN BỘ tệp mà trang live thực sự đọc, chứ không chỉ một tầng bên trong. Nếu
phép này xanh thì dù Worker hay GitHub Actions sinh ra tệp, trang cũng hiển
thị y như nhau.

So cả luật chuyển nguồn: hai bên chạy nguyên đường thu thập (Python ``fetch_snapshot``,
JS ``collectSnapshot``) với lượt gọi từng nguồn thay bằng bảng giải cho sẵn, nên nhật ký
``failover`` cũng được so. Chỉ phần đi mạng thật là không đối chiếu được, vì proxy trong môi
trường dựng không vào được các trang nguồn — giới hạn này được nói rõ trong
documentation/operations/live-worker.md.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ingest import live_sync
from ingest.sources import (
    EXPECTED_COUNTS,
    FALLBACK_SOURCE_NAMES,
    PRIMARY_COMPLETE_BY,
    PRIMARY_SOURCE_NAMES,
    PRIZE_ORDER,
    STALE_PAGE_ERROR,
)
from core.time_policy import VIETNAM_TZ

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "worker" / "test" / "run_snapshot.mjs"


def _require_node() -> str:
    """Trả về đường dẫn ``node``; ngoài CI thì bỏ qua, trong CI thì HỎNG.

    Bỏ qua trong CI là chốt chặn giả: bộ kiểm vẫn xanh trong khi phép so hai
    bản mã chưa hề chạy. Ngoài CI thì bỏ qua là hợp lý — không phải máy nào
    cũng cài Node.
    """
    import os

    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError(
                "CI phải có node để chạy phép kiểm đối chiếu Python/JS; "
                "xem bước 'Thiết lập Node' trong .github/workflows/ci.yml"
            )
        pytest.skip("không có node trên máy chạy kiểm")
    return node

#: Đúng danh mục thật: bản JS gọi ``PRIMARY_SOURCES``/``FALLBACK_SOURCES`` của chính nó, còn
#: bản Python được thay nguồn giả mang cùng tên theo cùng thứ tự.
SOURCE_NAMES = [*PRIMARY_SOURCE_NAMES, *FALLBACK_SOURCE_NAMES]
TOTAL_SLOTS = sum(EXPECTED_COUNTS.values())


class _FakeSource:
    def __init__(self, name: str, prize_map: dict[str, list[str]]) -> None:
        self.name = name
        self._prize_map = prize_map

    def fetch_partial(self, _date, _http, *, live: bool = False):
        return self._prize_map


def _token(rng: random.Random, key: str) -> str:
    width = {"special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
             "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2}[key]
    return "".join(rng.choice("0123456789") for _ in range(width))


def _cases(count: int = 160) -> list[dict]:
    """Sinh ca phủ mọi trạng thái VÀ cả hai nhánh của luật chuyển nguồn.

    Nguồn chính có ba dạng: đi cùng các nguồn khác, rỗng (sự cố ngay), hoặc kẹt ở nửa bảng —
    kẹt chỉ là sự cố khi đồng hồ đã quá ``PRIMARY_COMPLETE_BY``. Dự phòng có thể khớp nhau,
    lệch nhau (ô xung đột) hoặc chỉ một bên có dữ liệu.
    """
    rng = random.Random(20261013)
    cases = []
    base = datetime(2026, 9, 13, 0, 0, tzinfo=VIETNAM_TZ)
    halves = PRIZE_ORDER[: len(PRIZE_ORDER) // 2]
    for n in range(count):
        truth = {k: [_token(rng, k) for _ in range(EXPECTED_COUNTS[k])] for k in PRIZE_ORDER}
        # Ép một phần ca vào đúng khung quay số để chạm nhánh "live", một phần ra ngoài để
        # chạm "partial", và một phần quanh 18:40 để chạm cả hai phía của mốc chuyển nguồn.
        moment = base + timedelta(
            hours=rng.choice([10, 17, 18, 18, 18, 18, 20]),
            minutes=rng.randrange(0, 60),
            seconds=rng.randrange(0, 60),
        )
        fill = rng.choice([0.0, 0.3, 0.7, 1.0, 1.0])
        agreement = rng.choice(["all", "all", "split", "single"])
        primary_state = rng.choice(["follows", "follows", "empty", "stuck"])

        partials = []
        for name in SOURCE_NAMES:
            pmap: dict[str, list[str]] = {}
            for key in PRIZE_ORDER:
                vals = []
                for idx in range(EXPECTED_COUNTS[key]):
                    if rng.random() > fill:
                        break
                    if agreement == "split":
                        vals.append(truth[key][idx] if rng.random() < 0.6 else _token(rng, key))
                    else:
                        vals.append(truth[key][idx])
                # "single": chỉ MỘT nguồn (dự phòng đầu) có dữ liệu — với ngưỡng 2 nhóm, kỳ
                # đủ ô mà chưa đủ nhân chứng là complete_provisional.
                if agreement == "single" and name != SOURCE_NAMES[1]:
                    vals = []
                pmap[key] = vals
            if name == SOURCE_NAMES[0] and primary_state == "empty":
                pmap = {key: [] for key in PRIZE_ORDER}
            elif name == SOURCE_NAMES[0] and primary_state == "stuck":
                pmap = {key: list(truth[key]) if key in halves else [] for key in PRIZE_ORDER}
            partials.append((name, pmap))

        # Kỳ đã lưu gần nhất: không có, đúng "sự thật" của ca (nguồn nào chỉ hiện các ô ấy là
        # còn hiện kỳ trước), hoặc một kỳ khác hẳn.
        previous = rng.choice([
            None,
            truth,
            {k: [_token(rng, k) for _ in range(EXPECTED_COUNTS[k])] for k in PRIZE_ORDER},
        ])
        cases.append({
            "now": moment,
            "partials": partials,
            "min_agreement": rng.choice([1, 1, 2]),
            "previous": previous,
            "index": n,
        })
    return cases


def _python_payload(case: dict, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Thay từng nguồn của danh mục bằng nguồn giả CÙNG TÊN, rồi chạy nguyên ``fetch_snapshot``."""
    from ingest import sources as sources_module

    fakes = [_FakeSource(name, pmap) for name, pmap in case["partials"]]
    primary = len(PRIMARY_SOURCE_NAMES)
    monkeypatch.setattr(sources_module, "primary_sources", lambda: fakes[:primary])
    monkeypatch.setattr(sources_module, "fallback_sources", lambda: fakes[primary:])
    monkeypatch.setattr(live_sync.requests, "Session", lambda: object())
    return live_sync.fetch_snapshot(
        now=case["now"], min_agreement=case["min_agreement"], previous=case["previous"]
    )


def _javascript_payloads(cases: list[dict], tmp_path: Path) -> list[dict]:
    node = _require_node()
    payload = [
        {
            "partials": [[name, pmap] for name, pmap in c["partials"]],
            "now_utc": c["now"].astimezone(tz=None).isoformat(),
            "min_agreement": c["min_agreement"],
            "previous": c["previous"],
        }
        for c in cases
    ]
    path = tmp_path / "snapshots.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [node, str(RUNNER), str(path)],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert proc.returncode == 0, f"bản JS hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _normalise_numbers(value):
    """Đưa mọi số về float trước khi so.

    JSON chỉ có MỘT kiểu số: ``100`` và ``100.0`` là cùng một giá trị. Nhưng
    module json của Python giữ phân biệt int/float khi ghi, còn
    ``JSON.stringify`` của JS luôn bỏ phần thập phân bằng 0 — nên
    ``progress_percent`` tròn trăm ra ``100.0`` một bên và ``100`` bên kia.

    Đó là khác biệt về CÁCH GHI, không phải về giá trị, và phép so ban đầu của
    tôi báo lệch chỉ vì nó so chuỗi. Chuẩn hoá ở đây để phép kiểm bắt đúng thứ
    nó định bắt; sai lệch số thật vẫn lộ ra vì float so được với nhau.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return {k: _normalise_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise_numbers(v) for v in value]
    return value


def _comparable(payload: dict) -> str:
    """Bỏ đúng một trường không thể so: độ trễ mạng."""
    trimmed = dict(payload)
    trimmed["source_status"] = [
        {k: v for k, v in row.items() if k != "latency_ms"}
        for row in payload["source_status"]
    ]
    return json.dumps(_normalise_numbers(trimmed), sort_keys=True, ensure_ascii=False)


def test_python_and_javascript_snapshots_are_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = _cases()
    javascript = _javascript_payloads(cases, tmp_path)

    lech: list[str] = []
    for case, js in zip(cases, javascript, strict=True):
        python = _python_payload(case, monkeypatch)
        if _comparable(python) != _comparable(js):
            khac = [
                k for k in set(python) | set(js)
                if json.dumps(_normalise_numbers(python.get(k)), sort_keys=True,
                              ensure_ascii=False)
                != json.dumps(_normalise_numbers(js.get(k)), sort_keys=True,
                              ensure_ascii=False)
            ]
            lech.append(f"  ca #{case['index']} lệch ở: {sorted(khac)}")
            if len(lech) >= 5:
                break

    assert not lech, "payload live.json đã trôi lệch nhau:\n" + "\n".join(lech)


def test_the_generated_cases_reach_every_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phải chạm đủ các trạng thái, nếu không phép so chỉ kiểm một nhánh."""
    seen = set()
    reasons = set()
    stale = 0
    for case in _cases():
        payload = _python_payload(case, monkeypatch)
        seen.add(payload["status"])
        reasons.add(payload["failover"]["reason"].split(" mà ")[0])
        stale += sum(row["error"] == STALE_PAGE_ERROR for row in payload["source_status"])
    assert stale > 0, "bộ sinh chưa chạm nhánh nguồn còn hiện kỳ trước"
    for status in ("waiting", "live", "partial", "complete_verified", "complete_provisional",
                   "complete_conflict"):
        assert status in seen, f"bộ sinh chưa chạm trạng thái {status}; mới có {sorted(seen)}"
    assert reasons == {
        "nguồn chính dùng được",
        "nguồn chính không trả giá trị nào",
        f"đã quá {PRIMARY_COMPLETE_BY:%H:%M}",
        "cần 2 nhóm độc lập xác nhận",
    }, f"bộ sinh chưa chạm đủ bốn nhánh chuyển nguồn: {sorted(reasons)}"
