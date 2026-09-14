"""Hai bản đồng thuận nguồn phải cho kết quả giống hệt nhau.

Cùng lý do với ``test_worker_parser_parity``: Worker chạy JavaScript nên có
bản thứ hai của ``source_consensus_partial``. Nhưng chỗ này còn nguy hơn bản
phân tích, vì nó quyết định ô nào được đánh dấu ĐÃ XÁC MINH — tức quyết định
trang live nói "đã xác minh" hay "đang cập nhật".

Khác bản phân tích, đầu vào ở đây là dữ liệu thuần chứ không phải HTML, nên
không cần mẫu tay: sinh ngẫu nhiên có hạt giống cố định rồi so từng ca. Bộ
sinh cố ý tạo ra đủ các thế khó — đồng thuận sạch, xung đột, hai tên miền
cùng một nhà cung cấp, thế giằng nhóm bằng nhau, ô trống, và token hỏng.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from sources import EXPECTED_COUNTS, PRIZE_ORDER, source_consensus_partial

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "worker" / "test" / "run_consensus.mjs"


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
    "xoso.com.vn",
    "mketqua.net",
    "www.minhngoc.net.vn",
    "xosominhngoc.com",
    "xosodaiphat.com",
    "hainhay.net",
    "xskt.vn",
]


def _token(rng: random.Random, key: str) -> str:
    width = {"special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
             "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2}[key]
    return "".join(rng.choice("0123456789") for _ in range(width))


def _cases(count: int = 400) -> list[dict[str, object]]:
    rng = random.Random(20260913)
    cases: list[dict[str, object]] = []
    for _ in range(count):
        # Một "sự thật" chung để các nguồn có cơ hội đồng thuận; nếu mọi nguồn
        # đều ngẫu nhiên độc lập thì gần như không bao giờ có ô được xác minh
        # và phép so sẽ chỉ chạy qua một nhánh duy nhất.
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
                        break               # nguồn dừng giữa chừng (trang live)
                    if roll < 0.22:
                        vals.append(_token(rng, key))        # sai khác
                    elif roll < 0.27:
                        vals.append("x" * 3)                 # token hỏng
                    elif roll < 0.30:
                        vals.append("")                      # ô rỗng
                    else:
                        vals.append(truth[key][idx])         # khớp sự thật
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
        partials = [(name, pmap) for name, pmap in case["partials"]]  # type: ignore[misc]
        merged, meta = source_consensus_partial(
            partials, min_agreement=case["min_agreement"]  # type: ignore[arg-type]
        )
        left = json.dumps({"merged": merged, "meta": meta}, sort_keys=True, ensure_ascii=False)
        right = json.dumps(js, sort_keys=True, ensure_ascii=False)
        if left != right:
            lech.append(f"  ca #{n} (min_agreement={case['min_agreement']})")
            if len(lech) >= 5:
                break

    assert not lech, "hai bản đồng thuận đã trôi lệch nhau:\n" + "\n".join(lech)


def test_the_generated_cases_actually_reach_every_branch() -> None:
    """Bộ sinh phải chạm cả bốn nhánh, nếu không phép so chỉ kiểm một nhánh.

    Bốn nhánh: có ô xác minh được, có xung đột, có thế giằng nhóm bằng nhau,
    và có ô không nguồn nào cung cấp.
    """
    verified = conflicted = tied = empty = 0
    for case in _cases():
        partials = [(name, pmap) for name, pmap in case["partials"]]  # type: ignore[misc]
        _merged, meta = source_consensus_partial(
            partials, min_agreement=case["min_agreement"]  # type: ignore[arg-type]
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
    """Bảng nhóm nguồn phải khớp từng mục giữa hai bản.

    Đây không phải kiểm thừa: bản JS đầu tiên tôi viết chỉ chép hai bản sao
    minhngoc và để các nguồn còn lại rơi về tên miền đầy đủ. Phép so ngẫu
    nhiên bắt được, nhưng chỉ sau khi một ô tình cờ có đúng một nguồn ủng hộ.
    Chốt trực tiếp này đỏ ngay tức khắc và chỉ đúng dòng sai.
    """
    import re

    from sources import SOURCE_INDEPENDENCE_GROUP

    js = (ROOT / "worker" / "src" / "consensus.js").read_text(encoding="utf-8")
    block = re.search(
        r"const SOURCE_INDEPENDENCE_GROUP = \{(.*?)\};", js, re.S
    )
    assert block is not None, "không tìm thấy bảng nhóm nguồn trong bản JS"
    pairs = re.findall(r'"([^"]+)":\s*"([^"]+)"', block.group(1))
    assert dict(pairs) == SOURCE_INDEPENDENCE_GROUP
