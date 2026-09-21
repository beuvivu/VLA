from __future__ import annotations

"""Sinh CSS nền tảng TỪ token, không viết tay song song.

Vì sao sinh ra thay vì viết một tệp ``.css`` tĩnh: trước đây mỗi trang tự khai
màu, nên cùng một khái niệm mang ba giá trị khác nhau và không ai biết giá trị
nào đúng. Ở đây ``tokens.py`` là nguồn duy nhất; CSS chỉ là một cách xuất của
nó, và một phép kiểm so hai bên để chúng không thể trôi khỏi nhau.

Cách khai Dark Mode có ba tầng, cố ý:

1. ``:root`` mang Light Mode — mặc định khi không biết gì.
2. ``@media (prefers-color-scheme: dark)`` bọc trong
   ``:root:not([data-theme="light"])`` — theo hệ điều hành, NHƯNG nhường cho
   lựa chọn tường minh của người đọc.
3. ``:root[data-theme="dark"]`` — người đọc bấm chọn, thắng cả hệ điều hành.

Thiếu tầng 2 thì máy đặt dark mà trang vẫn sáng. Thiếu ``:not()`` ở tầng 2 thì
người đọc chọn sáng mà máy đặt tối sẽ ra trang tối — tức cái nút không hoạt
động, đúng loại lỗi khó hiểu nhất với người dùng.
"""

from vla_design.component_css import component_css
from vla_design.shell_css import shell_css
from vla_design.tokens import (
    DARK,
    LIGHT,
    MOTION,
    RADII,
    SHADOWS,
    SPACING,
    TYPE_SCALE,
)


def _color_block(palette: dict[str, str]) -> str:
    return "\n".join(f"  --vla-{name}: {value};" for name, value in palette.items())


def _shadow_block(mode: str) -> str:
    return "\n".join(f"  --vla-shadow-{k}: {v};" for k, v in SHADOWS[mode].items())


def _static_block() -> str:
    lines: list[str] = []
    for step in SPACING:
        lines.append(f"  --vla-space-{step}: {step}px;")
    for name, value in RADII.items():
        lines.append(f"  --vla-radius-{name}: {value};")
    for name, value in MOTION.items():
        lines.append(f"  --vla-motion-{name}: {value};")
    for name, (size, line_height, weight) in TYPE_SCALE.items():
        lines.append(f"  --vla-font-{name}-size: {size};")
        lines.append(f"  --vla-font-{name}-line: {line_height};")
        lines.append(f"  --vla-font-{name}-weight: {weight};")
    return "\n".join(lines)


def foundation_css() -> str:
    """Tầng nền: biến, reset, kiểu chữ, và các lớp utility của VLA."""
    return f""":root {{
  color-scheme: light;
{_color_block(LIGHT)}
{_shadow_block("light")}
{_static_block()}
  --vla-font-sans: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  --vla-page-max: 1440px;
  --vla-page-max-wide: 1920px;
  --vla-page-gutter: 16px;
  --vla-sidebar-w: 264px;
  --vla-sidebar-w-collapsed: 72px;
  --vla-topbar-h: 64px;
}}

@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
{_color_block(DARK)}
{_shadow_block("dark")}
  }}
}}

:root[data-theme="dark"] {{
  color-scheme: dark;
{_color_block(DARK)}
{_shadow_block("dark")}
}}

@media (min-width: 640px) {{
  :root {{ --vla-page-gutter: 24px; }}
}}

@media (min-width: 1024px) {{
  :root {{ --vla-page-gutter: 32px; }}
}}

*,
*::before,
*::after {{ box-sizing: border-box; }}

html {{
  -webkit-text-size-adjust: 100%;
  scroll-behavior: smooth;
}}

body {{
  margin: 0;
  font-family: var(--vla-font-sans);
  font-size: var(--vla-font-body-size);
  line-height: var(--vla-font-body-line);
  color: var(--vla-text-primary);
  background: var(--vla-background);
  -webkit-font-smoothing: antialiased;
}}

/* Số thống kê phải thẳng cột. Chữ số tỉ lệ làm hai hàng cạnh nhau lệch nhau,
   và so sánh bằng mắt là việc chính trên mọi trang của VLA. */
.vla-num,
td.vla-num,
th.vla-num,
.vla-table td,
.vla-kpi-value {{ font-variant-numeric: tabular-nums; }}

a {{ color: var(--vla-primary); text-decoration-thickness: 1px; text-underline-offset: 2px; }}
a:hover {{ color: var(--vla-primary-hover); }}

/* Focus PHẢI thấy được, và thấy được trên cả hai nền. Dùng `:focus-visible`
   nên chuột không kéo theo vòng sáng, còn bàn phím thì luôn có. */
:where(a, button, input, select, textarea, summary, [tabindex]):focus-visible {{
  outline: 2px solid var(--vla-focus-ring);
  outline-offset: 2px;
  border-radius: var(--vla-radius-sm);
}}

.vla-visually-hidden {{
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}}

/* Bỏ qua điều hướng: bắt buộc khi sidebar có hàng chục liên kết, nếu không
   người dùng bàn phím phải Tab qua hết mới tới nội dung. */
.vla-skip-link {{
  position: absolute;
  left: var(--vla-space-16);
  top: calc(-1 * var(--vla-space-48));
  z-index: 100;
  padding: var(--vla-space-8) var(--vla-space-16);
  background: var(--vla-surface);
  color: var(--vla-text-primary);
  border: 1px solid var(--vla-border-strong);
  border-radius: var(--vla-radius-sm);
  box-shadow: var(--vla-shadow-md);
  transition: top var(--vla-motion-fast) var(--vla-motion-ease);
}}
.vla-skip-link:focus {{ top: var(--vla-space-16); }}

@media (prefers-reduced-motion: reduce) {{
  html {{ scroll-behavior: auto; }}
  *,
  *::before,
  *::after {{
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }}
}}
"""


def full_css() -> str:
    """Toàn bộ CSS của VLA: nền tảng rồi khung ứng dụng.

    Thứ tự quan trọng: nền tảng khai biến, khung dùng biến. Đảo lại thì mọi
    ``var(--vla-*)`` trong khung rơi về rỗng và trang mất màu — mà trình duyệt
    KHÔNG báo lỗi cho biến CSS không xác định, nên nó là lỗi im lặng.
    """
    return foundation_css() + shell_css() + component_css()
