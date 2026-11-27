from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def unstable_sorts(source: str) -> list[int]:
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
                continue
        found.append(node.lineno)
    return sorted(found)


def test_the_rule_itself_catches_unstable_sorts() -> None:
    sample = "\n".join([
        'a = df.sort_values("count", ascending=False)',
        'b = df.sort_values(by="count")',
        "c = np.argsort(x)",
        "d = x.argsort()[::-1]",
        "e = np.argpartition(score, -3)[-3:]",
        'f = df.sort_values("count", kind="stable")',
        'g = df.sort_values(["count", "x"], ascending=False)',
        'h = np.argsort(-score, kind="stable")',
        "i = df.sort_values(key_name)",
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
