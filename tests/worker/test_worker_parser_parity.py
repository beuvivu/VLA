from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ingest.sources import extract_partial_prize_map

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "prize_pages.json"
RUNNER = ROOT / "worker" / "test" / "run_parser.mjs"


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


def _load_corpus() -> dict[str, str]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _javascript_results() -> dict[str, dict[str, list[str]]]:
    node = _require_node()
    proc = subprocess.run(
        [node, str(RUNNER), str(CORPUS)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, f"bản JS hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_the_corpus_actually_exercises_the_hard_cases() -> None:
    corpus = _load_corpus()
    for required in (
        "chu_so_toan_phan",
        "so_nhung_trong_ma_dinh_danh",
        "script_style_gia_mao",
        "the_long_tach_so",
        "menu_lap_nhan_truoc_bang_that",
        "hai_bang_bang_sau_day_du_hon",
        "chu_thich_dong_bang_cham_than",
    ):
        assert required in corpus, required
    assert len(corpus) >= 20


def test_python_and_javascript_parsers_agree_on_every_page() -> None:
    corpus = _load_corpus()
    javascript = _javascript_results()

    assert set(javascript) == set(corpus), "hai bản không chạy cùng bộ mẫu"

    lech: list[str] = []
    for name, html in corpus.items():
        python_map = extract_partial_prize_map(html)
        left = json.dumps(python_map, sort_keys=True, ensure_ascii=False)
        right = json.dumps(javascript[name], sort_keys=True, ensure_ascii=False)
        if left != right:
            lech.append(f"  {name}\n    python: {left}\n    js    : {right}")

    assert not lech, "hai bản phân tích đã trôi lệch nhau:\n" + "\n".join(lech)


def test_the_shared_corpus_is_not_silently_all_empty() -> None:
    corpus = _load_corpus()
    full = 0
    for html in corpus.values():
        prize_map = extract_partial_prize_map(html)
        if sum(len(v) for v in prize_map.values()) == 27:
            full += 1
    assert full >= 3, f"chỉ {full} trang bóc đủ 27 ô — bộ mẫu quá yếu"


def test_comment_removal_leaves_no_comment_text_behind() -> None:
    node = _require_node()
    module = (ROOT / "worker" / "src" / "prize_map.js").as_uri()
    script = (f"import {{htmlToLines}} from '{module}';"
              "process.stdout.write(JSON.stringify(htmlToLines('<!-<!-- x -->- a > ĐB 83772 --><div>G7 66</div>')));")
    proc = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == ["G7 66"]
