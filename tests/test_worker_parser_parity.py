"""Hai bản phân tích giải phải cho kết quả giống hệt nhau.

Worker chạy trên nền JavaScript nên không dùng lại được ``src/sources.py``.
Hai bản cùng một logic là nợ kỹ thuật thật: chúng sẽ trôi lệch nhau, và lệch ở
đây nghĩa là TRANG LIVE hiển thị một dãy số khác với dãy được ghi vào LỊCH SỬ —
kiểu sai không bao giờ nổ, chỉ âm thầm mâu thuẫn.

Phép kiểm này là chốt chặn duy nhất cho chuyện đó: chạy cả hai bản trên cùng
một bộ mẫu và đòi kết quả trùng khít từng ký tự. Sửa một bản mà quên bản kia
thì nó đỏ ngay.

Bộ mẫu ``tests/fixtures/prize_pages.json`` cố tình gồm cả những trang độc:
chữ số toàn phần, số nhúng trong mã định danh, thẻ script giả mạo nhãn giải,
menu lặp nhãn, hai bảng chồng nhau, và thẻ script không đóng.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sources import extract_partial_prize_map

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "prize_pages.json"
RUNNER = ROOT / "worker" / "test" / "run_parser.mjs"


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
    """Bộ mẫu phải phủ các bẫy đã biết, nếu không phép so chỉ là hình thức."""
    corpus = _load_corpus()
    for required in (
        "chu_so_toan_phan",
        "so_nhung_trong_ma_dinh_danh",
        "script_style_gia_mao",
        "the_long_tach_so",
        "menu_lap_nhan_truoc_bang_that",
        "hai_bang_bang_sau_day_du_hon",
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
        # Bản Python trả dict; so sánh theo JSON đã sắp khoá để không phụ thuộc
        # thứ tự chèn của hai ngôn ngữ.
        left = json.dumps(python_map, sort_keys=True, ensure_ascii=False)
        right = json.dumps(javascript[name], sort_keys=True, ensure_ascii=False)
        if left != right:
            lech.append(f"  {name}\n    python: {left}\n    js    : {right}")

    assert not lech, "hai bản phân tích đã trôi lệch nhau:\n" + "\n".join(lech)


def test_the_shared_corpus_is_not_silently_all_empty() -> None:
    """Một bộ mẫu toàn trang rỗng cũng "trùng khít" — và chẳng chứng minh gì.

    Đòi hỏi bộ mẫu có ít nhất vài trang bóc ra đủ 27 ô, nếu không phép so trên
    kia có thể xanh trong khi cả hai bản đều hỏng như nhau.
    """
    corpus = _load_corpus()
    full = 0
    for html in corpus.values():
        prize_map = extract_partial_prize_map(html)
        if sum(len(v) for v in prize_map.values()) == 27:
            full += 1
    assert full >= 3, f"chỉ {full} trang bóc đủ 27 ô — bộ mẫu quá yếu"
