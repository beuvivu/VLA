"""Hai lớp CSS riêng không được ghi đè chủ đề hoặc màu ô dữ liệu."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _rule(css: str, selector: str) -> dict[str, str]:
    match = re.search(r"^\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", css, re.M)
    assert match, selector
    return dict(
        (key.strip(), value.strip())
        for key, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", match[1])
    )


def test_detail_hover_keeps_the_row_transparent_and_marks_its_edge() -> None:
    """Ghim lại nền hover sáng phải đỏ; viền không xoá màu ô nháy hoặc ô chọn."""
    css = (ROOT / "src/templates/stat_detail_pages.css").read_text()
    hover = _rule(css, ".sp-page .sp-table tbody tr:hover")
    assert hover["background"] == "transparent"
    assert "var(--ui-brand-border)" in hover["outline"]
    for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if ":hover" in selector and re.search(r"\btd\b", selector):
            assert not re.search(r"\bbackground(?:-color)?\s*:", declarations)


def test_traditional_special_tail_inherits_the_shared_semantic_pair() -> None:
    """Auto-dark và explicit-dark cùng dùng một cặp màu thay vì nhánh riêng."""
    css = (ROOT / "src/templates/traditional_results.css").read_text()
    tail = _rule(css, ".tr-special-tail")
    assert tail["background"] == "var(--ui-special-bg)"
    assert tail["color"] == "var(--ui-special-ink)"
    assert "var(--ui-special-border)" in tail["box-shadow"]
    assert not re.search(r':root\[data-ui-theme="dark"\]\s+\.tr-special-tail', css)


def test_traditional_marking_inherits_the_shared_semantic_pair() -> None:
    """Khôi phục palette sáng cục bộ phải bị phát hiện dù theme cha đã tối."""
    css = (ROOT / "src/templates/traditional_results.css").read_text()
    matches = re.findall(r"(?<![\w-])\.tr-results\s*\{([^{}]*)\}", css)
    assert matches
    declarations = ";".join(matches)
    for local, shared in (("bg", "bg"), ("ink", "ink"), ("line", "border")):
        values = re.findall(r"--tr-mark-" + local + r"\s*:\s*([^;}]*)", declarations)
        assert values == [f"var(--ui-mark-{shared})"]
    marked = _rule(css, ".tr-number[data-marked],.tr-mini[data-marked]")
    assert marked["background"] == "var(--tr-mark-bg)"
    assert marked["color"] == "var(--tr-mark-ink)"
