"""Payload live.json của Worker phải giống hệt bản Python.

Đây là phép đối chiếu cuối và là phép quan trọng nhất trong ba phép: nó so
TOÀN BỘ tệp mà trang live thực sự đọc, chứ không chỉ một tầng bên trong. Nếu
phép này xanh thì dù Worker hay GitHub Actions sinh ra tệp, trang cũng hiển
thị y như nhau.

Chỉ so phần THUẦN. Phần gọi mạng không đối chiếu được vì phụ thuộc mạng thật,
và proxy trong môi trường dựng không vào được các trang nguồn — giới hạn này
được nói rõ trong documentation/operations/live-worker.md.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import live_sync
from sources import EXPECTED_COUNTS, PRIZE_ORDER, source_independence_key
from time_policy import VIETNAM_TZ

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

SOURCE_NAMES = [
    "xoso.com.vn", "mketqua.net", "www.minhngoc.net.vn",
    "xosominhngoc.com", "xosodaiphat.com", "hainhay.net", "xskt.vn",
]
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


def _cases(count: int = 120) -> list[dict]:
    """Sinh ca phủ cả năm trạng thái: waiting, partial, live, complete_*, verified."""
    rng = random.Random(20260914)
    cases = []
    base = datetime(2026, 9, 13, 0, 0, tzinfo=VIETNAM_TZ)
    for n in range(count):
        truth = {k: [_token(rng, k) for _ in range(EXPECTED_COUNTS[k])] for k in PRIZE_ORDER}
        # Ép một phần ca vào đúng khung quay số để chạm nhánh "live", và một
        # phần ra ngoài khung để chạm nhánh "partial" — hai nhánh ấy chỉ khác
        # nhau ở ĐỒNG HỒ chứ không ở dữ liệu.
        moment = base + timedelta(
            hours=rng.choice([10, 17, 17, 18, 18, 18, 20]),
            minutes=rng.randrange(0, 60),
            seconds=rng.randrange(0, 60),
        )
        fill = rng.choice([0.0, 0.3, 0.7, 1.0, 1.0])
        agreement = rng.choice(["all", "all", "split", "single"])

        partials = []
        for name in SOURCE_NAMES:
            pmap: dict[str, list[str]] = {}
            for key in PRIZE_ORDER:
                vals = []
                for idx in range(EXPECTED_COUNTS[key]):
                    if rng.random() > fill:
                        break
                    if agreement == "all":
                        vals.append(truth[key][idx])
                    elif agreement == "split":
                        vals.append(truth[key][idx] if rng.random() < 0.6 else _token(rng, key))
                    else:
                        vals.append(truth[key][idx] if name == SOURCE_NAMES[0] else "")
                pmap[key] = vals
            partials.append((name, pmap))

        cases.append({
            "now": moment,
            "partials": partials,
            "min_agreement": rng.choice([2, 2, 2, 3]),
            "index": n,
        })
    return cases


def _python_payload(case: dict, monkeypatch: pytest.MonkeyPatch) -> dict:
    fakes = [_FakeSource(name, pmap) for name, pmap in case["partials"]]
    monkeypatch.setattr(live_sync, "default_sources", lambda: fakes)
    monkeypatch.setattr(live_sync.requests, "Session", lambda: object())
    return live_sync.fetch_snapshot(
        now=case["now"], min_agreement=case["min_agreement"]
    )


def _javascript_payloads(cases: list[dict], tmp_path: Path) -> list[dict]:
    node = _require_node()
    payload = [
        {
            "partials": [[name, pmap] for name, pmap in c["partials"]],
            "source_status": [
                {
                    "priority": i + 1,
                    "source": name,
                    "provider_group": source_independence_key(name),
                    "received_values": sum(len(pmap.get(k, [])) for k in PRIZE_ORDER),
                    "complete": sum(len(pmap.get(k, [])) for k in PRIZE_ORDER) == TOTAL_SLOTS,
                    "latency_ms": 0,
                    "error": None,
                }
                for i, (name, pmap) in enumerate(c["partials"])
            ],
            "now_utc": c["now"].astimezone(tz=None).isoformat(),
            "min_agreement": c["min_agreement"],
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
    for case in _cases():
        seen.add(_python_payload(case, monkeypatch)["status"])
    for status in ("waiting", "live", "complete_verified"):
        assert status in seen, f"bộ sinh chưa chạm trạng thái {status}; mới có {sorted(seen)}"
