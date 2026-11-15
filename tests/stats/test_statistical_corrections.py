"""Hiệu chỉnh nhiều kiểm định của kho (`stats.statistical_corrections`), bản DUY NHẤT từ 15-11-2026.

BH không để giá trị thiếu làm mất các kiểm định hợp lệ; Holm thay ba bản chép (`digit_sum_rules`,
`board_record`, `multi_hit_benchmark`).
"""
from __future__ import annotations

import numpy as np
import pytest

from stats.statistical_corrections import benjamini_hochberg, holm


def test_missing_p_value_does_not_poison_other_hypotheses() -> None:
    corrected = benjamini_hochberg(np.array([0.01, np.nan, 0.2, np.inf]))
    np.testing.assert_allclose(corrected[[0, 2]], [0.02, 0.2])
    assert np.isnan(corrected[[1, 3]]).all()


@pytest.mark.parametrize("values", [[-0.01, 0.5], [0.2, 1.1], [[0.1, 0.2]]])
def test_invalid_finite_p_values_or_matrix_are_rejected(values) -> None:
    with pytest.raises(ValueError):
        benjamini_hochberg(np.asarray(values))


def test_fdr_finite_values_keep_order_and_known_result() -> None:
    np.testing.assert_allclose(benjamini_hochberg(np.array([0.04, 0.01, 0.03, 0.002])), [0.04, 0.02, 0.04, 0.008])
    assert benjamini_hochberg(np.array([])).shape == (0,)


def test_bh_fdr_is_bounded_monotone_in_rank_and_never_below_the_raw_p() -> None:
    p = np.array([0.20, 0.001, 0.04, 0.01, 0.70], dtype=float)
    q = benjamini_hochberg(p)
    assert np.all((0.0 <= q) & (q <= 1.0))
    assert np.all(np.diff(q[np.argsort(p)]) >= -1e-12)
    assert np.all(q + 1e-12 >= p)


def test_holm_steps_down_stays_monotone_and_keeps_the_input_order() -> None:
    """Giá trị sách giáo khoa, đúng các ca ba bản chép cũ từng ghim."""
    assert holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert holm([0.01, 0.04, 0.03, 0.5]) == pytest.approx([0.04, 0.09, 0.09, 0.5])
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.9, 0.9]) == [1.0, 1.0]
    assert holm([]) == []
    assert holm((0.02, 0.02)) == [0.04, 0.04]   # hoà: cùng mức, không phụ thuộc vị trí


def own_corrections(source: str) -> list[str]:
    """Hàm hiệu chỉnh (tên chứa holm / hochberg / fdr) TỰ cài đặt thay vì gọi bản ở `stats.statistical_corrections`."""
    import ast
    tree = ast.parse(source)
    shared = {alias.asname or alias.name for node in ast.walk(tree)
              if isinstance(node, ast.ImportFrom) and node.module == "stats.statistical_corrections"
              for alias in node.names}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and any(k in node.name.lower() for k in ("holm", "hochberg", "fdr")):
            called = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            if not called & shared:
                found.append(node.name)
    return found


def test_multiple_testing_corrections_live_in_one_module() -> None:
    """15-11-2026: Holm có ba bản chép, BH hai lớp bọc. Bản chép thứ tư sẽ lệch khỏi ba bản kia ở ca hoà."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "src"
    found = {path.relative_to(src).as_posix(): names for path in src.rglob("*.py")
             if path.name != "statistical_corrections.py"
             and (names := own_corrections(path.read_text(encoding="utf-8")))}
    assert found == {}
    assert own_corrections("def holm(p):\n    return sorted(p)\n") == ["holm"]
    assert own_corrections("from stats.statistical_corrections import holm as h\n"
                           "def holm(p):\n    return dict(zip(p, h(list(p.values()))))\n") == []
