from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from ingest.sources import (
    EXPECTED_COUNTS,
    FALLBACK_SOURCE_NAMES,
    PRIMARY_SOURCE_NAMES,
    PRIZE_ORDER,
    source_consensus_partial,
)

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "worker" / "test" / "run_consensus.mjs"


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

SOURCE_NAMES = [*PRIMARY_SOURCE_NAMES, *FALLBACK_SOURCE_NAMES, "nguon-ngoai-danh-muc.example"]


def _token(rng: random.Random, key: str) -> str:
    width = {"special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
             "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2}[key]
    return "".join(rng.choice("0123456789") for _ in range(width))


def _cases(count: int = 400) -> list[dict[str, object]]:
    rng = random.Random(20260913)
    cases: list[dict[str, object]] = []
    for _ in range(count):
        truth = {k: [_token(rng, k) for _ in range(EXPECTED_COUNTS[k])] for k in PRIZE_ORDER}
        chosen_sources = rng.sample(SOURCE_NAMES, rng.randint(1, len(SOURCE_NAMES)))
        rng.shuffle(chosen_sources)

        partials = []
        for name in chosen_sources:
            pmap: dict[str, list[str]] = {}
            for key in PRIZE_ORDER:
                vals: list[str] = []
                for idx in range(EXPECTED_COUNTS[key]):
                    roll = rng.random()
                    if roll < 0.12:
                        break
                    if roll < 0.22:
                        vals.append(_token(rng, key))
                    elif roll < 0.27:
                        vals.append("x" * 3)
                    elif roll < 0.30:
                        vals.append("")
                    else:
                        vals.append(truth[key][idx])
                pmap[key] = vals
            partials.append([name, pmap])
        cases.append({"partials": partials, "min_agreement": rng.choice([1, 2, 2, 2, 3])})
    return cases


def _javascript_results(cases: list[dict[str, object]], tmp_path: Path) -> list[dict]:
    node = _require_node()
    payload = tmp_path / "cases.json"
    payload.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [node, str(RUNNER), str(payload)],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert proc.returncode == 0, f"bản JS hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_python_and_javascript_consensus_agree_on_every_case(tmp_path: Path) -> None:
    cases = _cases()
    javascript = _javascript_results(cases, tmp_path)
    assert len(javascript) == len(cases)

    lech: list[str] = []
    for n, (case, js) in enumerate(zip(cases, javascript, strict=True)):
        partials = [(name, pmap) for name, pmap in case["partials"]]
        merged, meta = source_consensus_partial(
            partials, min_agreement=case["min_agreement"]
        )
        left = json.dumps({"merged": merged, "meta": meta}, sort_keys=True, ensure_ascii=False)
        right = json.dumps(js, sort_keys=True, ensure_ascii=False)
        if left != right:
            lech.append(f"  ca #{n} (min_agreement={case['min_agreement']})")
            if len(lech) >= 5:
                break

    assert not lech, "hai bản đồng thuận đã trôi lệch nhau:\n" + "\n".join(lech)


def test_the_generated_cases_actually_reach_every_branch() -> None:
    verified = conflicted = tied = empty = 0
    for case in _cases():
        partials = [(name, pmap) for name, pmap in case["partials"]]
        _merged, meta = source_consensus_partial(
            partials, min_agreement=case["min_agreement"]
        )
        if meta["verified_slots"]:
            verified += 1
        if meta["conflicts"]:
            conflicted += 1
        for slot in meta["slot_meta"].values():
            if slot["ambiguous_tie"]:
                tied += 1
            if slot["value"] is None:
                empty += 1

    assert verified > 50, f"chỉ {verified} ca có ô xác minh được"
    assert conflicted > 50, f"chỉ {conflicted} ca có xung đột"
    assert tied > 0, "chưa ca nào chạm thế giằng nhóm bằng nhau"
    assert empty > 0, "chưa ca nào có ô trống"


def test_the_two_independence_tables_are_entry_for_entry_identical() -> None:
    import re

    from ingest.sources import SOURCE_INDEPENDENCE_GROUP

    js = (ROOT / "worker" / "src" / "consensus.js").read_text(encoding="utf-8")
    block = re.search(
        r"const SOURCE_INDEPENDENCE_GROUP = \{(.*?)\};", js, re.S
    )
    assert block is not None, "không tìm thấy bảng nhóm nguồn trong bản JS"
    pairs = re.findall(r'"([^"]+)":\s*"([^"]+)"', block.group(1))
    assert dict(pairs) == SOURCE_INDEPENDENCE_GROUP
