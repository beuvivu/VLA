"""Mọi phép sắp xếp trong ``src`` phải ổn định: hoà điểm có MỘT thứ tự, trên mọi máy.

Sắp xếp mặc định của numpy/pandas (quicksort, ``argpartition``) xếp phần tử hoà theo lệnh vector của
CPU. Ngày 05-11-2026 hai lượt pipeline trên CÙNG dữ liệu, chạy trên hai runner, giữ hai tập top cầu
soi đường lệch 13 cầu, in «68-97» rồi «68-76» ở bảng cặp trang chủ và đảo hàng trong DASHBOARD.md.
Luật: ``sort_values`` một khoá (hoặc khoá không phải danh sách hằng) và ``argsort`` phải khai ``kind``;
``argpartition`` bị cấm (chọn phần tử hoà ở ranh giới không xác định) — sắp đủ rồi cắt.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def unstable_sorts(source: str) -> list[int]:
    """Số dòng của các phép sắp xếp không ổn định trong ``source``."""
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name = node.func.attr
        if name == "argpartition":
            found.append(node.lineno)
            continue
        if name not in ("sort_values", "argsort"):
            continue
        if any(keyword.arg in ("kind", None) for keyword in node.keywords):
            continue
        if name == "sort_values":
            by = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "by"), None)
            if isinstance(by, (ast.List, ast.Tuple)) and len(by.elts) > 1:
                continue  # nhiều khoá: pandas dùng lexsort, vốn ổn định
        found.append(node.lineno)
    return sorted(found)


def test_the_rule_itself_catches_unstable_sorts() -> None:
    sample = "\n".join([
        'a = df.sort_values("count", ascending=False)',      # 1: một khoá, không kind
        'b = df.sort_values(by="count")',                    # 2
        "c = np.argsort(x)",                                 # 3
        "d = x.argsort()[::-1]",                             # 4
        "e = np.argpartition(score, -3)[-3:]",               # 5: luôn cấm
        'f = df.sort_values("count", kind="stable")',        # 6: được
        'g = df.sort_values(["count", "x"], ascending=False)',  # 7: nhiều khoá, được
        'h = np.argsort(-score, kind="stable")',             # 8: được
        "i = df.sort_values(key_name)",                      # 9: khoá là biến, phải khai kind
    ])
    assert unstable_sorts(sample) == [1, 2, 3, 4, 5, 9]


def test_every_sort_in_src_declares_a_stable_kind() -> None:
    files = sorted((ROOT / "src").rglob("*.py"))
    assert len(files) > 100, "tập quét rỗng thì phép kiểm không thể đỏ"
    offenders = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in files
        for line in unstable_sorts(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "Sắp xếp không ổn định (thêm kind=\"stable\"):\n" + "\n".join(offenders)
