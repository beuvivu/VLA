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

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "worker" / "test" / "run_snapshot.mjs"


def _require_node() -> str:
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
    rng = random.Random(20261013)
    cases = []
    base = datetime(2026, 9, 13, 0, 0, tzinfo=VIETNAM_TZ)
    halves = PRIZE_ORDER[: len(PRIZE_ORDER) // 2]
    for n in range(count):
        truth = {k: [_token(rng, k) for _ in range(EXPECTED_COUNTS[k])] for k in PRIZE_ORDER}
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
                if agreement == "single" and name != SOURCE_NAMES[1]:
                    vals = []
                pmap[key] = vals
            if name == SOURCE_NAMES[0] and primary_state == "empty":
                pmap = {key: [] for key in PRIZE_ORDER}
            elif name == SOURCE_NAMES[0] and primary_state == "stuck":
                pmap = {key: list(truth[key]) if key in halves else [] for key in PRIZE_ORDER}
            partials.append((name, pmap))

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
