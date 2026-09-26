"""Phân giải token màu nguồn cho phép kiểm CSS, không duy trì bảng màu thứ hai."""
import re

from ui_theme import TAILWIND_LITE_CSS


def theme_tokens(dark: bool = False) -> dict[str, str]:
    selector = ':root[data-ui-theme="dark"]' if dark else ':root'
    match = re.search(re.escape(selector) + r'\s*\{([^{}]*)\}', TAILWIND_LITE_CSS)
    assert match, selector
    values = dict(re.findall(r'(--[\w-]+)\s*:\s*([^;{}]+)', match.group(1)))
    assert '--ui-surface' in values and '--ui-ink' in values
    return values


def resolve_theme_colors(css: str, dark: bool = False) -> str:
    values = theme_tokens(dark)
    return re.sub(r'var\((--ui-[\w-]+)\)', lambda m: values.get(m.group(1), m.group(0)), css)
