"""Design system dùng chung cho các trang tĩnh VLA.

Trang sinh ra phải tự chứa: CSP là ``default-src 'self'`` nên không được nạp
Tailwind hay web font từ CDN. Vì vậy module này nhúng sẵn một tập tiện ích
kiểu Tailwind cùng các lớp component ngữ nghĩa (shell, card, table, badge).

Ba nhóm API:

* :data:`TAILWIND_LITE_CSS` / :func:`tailwind_style_tag` — biểu định kiểu.
* :func:`shell_open` / :func:`shell_close` — khung trang căn giữa, cân đối.
* :func:`render_table` / :func:`dataframe_table` — bảng dữ liệu đã canh cột.
"""

from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from typing import Any


# Căn lề theo loại dữ liệu: số/chỉ số canh phải, trạng thái canh giữa.
ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"

_ALIGN_CLASS = {
    ALIGN_LEFT: "vla-al",
    ALIGN_CENTER: "vla-ac",
    ALIGN_RIGHT: "vla-ar",
}


TAILWIND_LITE_CSS = r"""
/* ---- 1. Design token ------------------------------------------------- */
:root{
--vla-bg:#f8fafc;--vla-surface:#fff;--vla-surface-2:#f8fafc;
--vla-border:rgba(226,232,240,.75);--vla-border-strong:#e2e8f0;
--vla-ink:#0f172a;--vla-ink-2:#1e293b;--vla-ink-soft:#475569;--vla-ink-muted:#94a3b8;
--vla-brand:#4f46e5;--vla-brand-ink:#4338ca;--vla-brand-soft:#eef2ff;--vla-brand-border:#c7d2fe;
--vla-ok:#047857;--vla-ok-soft:#ecfdf5;--vla-ok-border:#a7f3d0;
--vla-warn:#b45309;--vla-warn-soft:#fffbeb;--vla-warn-border:#fde68a;
--vla-bad:#be123c;--vla-bad-soft:#fff1f2;--vla-bad-border:#fecdd3;
--vla-r-md:.5rem;--vla-r-lg:.75rem;--vla-r-xl:1rem;
--vla-sh-sm:0 1px 2px rgba(15,23,42,.06);
--vla-sh-md:0 4px 12px rgba(15,23,42,.10);
--vla-sh-lg:0 10px 25px rgba(15,23,42,.14);
--vla-font:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--vla-mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}

/* ---- 2. Nền tảng ----------------------------------------------------- */
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--vla-bg);color:var(--vla-ink-2);
font-family:var(--vla-font);font-size:14px;line-height:1.6;
-webkit-font-smoothing:antialiased}
img{max-width:100%;height:auto}
a{color:var(--vla-brand);text-decoration:none}
a:hover{text-decoration:underline}
code,pre,.mono{font-family:var(--vla-mono)}
h1,h2,h3,h4{color:var(--vla-ink);font-weight:600;line-height:1.25;margin:0 0 .5rem}
h1{font-size:1.5rem;letter-spacing:-.015em}
h2{font-size:1.125rem}
h3{font-size:1rem}
@media (min-width:768px){h1{font-size:1.875rem}h2{font-size:1.25rem}}

/* ---- 3. Khung trang: container căn giữa, không tràn ngang ------------- */
.vla-shell{width:100%;max-width:80rem;margin-inline:auto;padding:1.5rem 1rem 3rem}
@media (min-width:640px){.vla-shell{padding-left:1.5rem;padding-right:1.5rem}}
@media (min-width:1024px){.vla-shell{padding-left:2rem;padding-right:2rem;padding-top:2rem}}
.vla-shell-wide{max-width:90rem}

.vla-header{margin-bottom:1.5rem;padding-bottom:1.25rem;
border-bottom:1px solid var(--vla-border)}
.vla-header h1{margin-bottom:.35rem}
.vla-sub{color:var(--vla-ink-soft);font-size:.875rem;margin:0}
.vla-meta{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem .875rem;
margin-top:.625rem;color:var(--vla-ink-soft);font-size:.8125rem}

/* ---- 4. Lưới 12 cột: các ô luôn kéo đầy, không để khoảng trống lệch --- */
.vla-grid{display:grid;grid-template-columns:repeat(1,minmax(0,1fr));
gap:1.25rem;align-items:stretch}
.vla-grid>*{min-width:0}
@media (min-width:768px){
.vla-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:1.5rem}
.vla-grid-1-md{grid-template-columns:repeat(1,minmax(0,1fr))}
}
@media (min-width:1024px){
.vla-grid{grid-template-columns:repeat(12,minmax(0,1fr))}
.vla-c3{grid-column:span 3/span 3}.vla-c4{grid-column:span 4/span 4}
.vla-c5{grid-column:span 5/span 5}.vla-c6{grid-column:span 6/span 6}
.vla-c7{grid-column:span 7/span 7}.vla-c8{grid-column:span 8/span 8}
.vla-c9{grid-column:span 9/span 9}.vla-c12{grid-column:span 12/span 12}
}
/* Dưới lg mọi ô chiếm trọn hàng thay vì thu nhỏ lệch. */
@media (max-width:1023px){[class*="vla-c"]{grid-column:auto}}

/* ---- 5. Card --------------------------------------------------------- */
.vla-card{display:flex;flex-direction:column;background:var(--vla-surface);
border:1px solid var(--vla-border);border-radius:var(--vla-r-lg);
box-shadow:var(--vla-sh-sm);overflow:hidden;
transition:box-shadow .2s cubic-bezier(.4,0,.2,1),transform .2s cubic-bezier(.4,0,.2,1)}
.vla-card:hover{box-shadow:var(--vla-sh-md)}
.vla-card-lift:hover{transform:translateY(-2px);box-shadow:var(--vla-sh-lg)}
.vla-card-head{display:flex;flex-wrap:wrap;align-items:center;
justify-content:space-between;gap:.75rem;padding:1rem 1.25rem;
border-bottom:1px solid var(--vla-border)}
.vla-card-head h2,.vla-card-head h3{margin:0}
/* Thân card là flex dọc để khối nội dung cuối cùng kéo giãn lấp đầy chiều cao
   hàng lưới, thay vì bỏ lại khoảng trắng dưới đáy card thấp hơn. */
.vla-card-body{flex:1 1 auto;display:flex;flex-direction:column;gap:.75rem;
min-height:0;padding:1.25rem}
.vla-card-body>:first-child{margin-top:0}
.vla-card-body>:last-child{margin-bottom:0}
.vla-card-flush{padding:0}

/* ---- 6. Bảng dữ liệu ------------------------------------------------- */
.vla-table-wrap{width:100%;flex:1 1 auto;min-height:0;
overflow-x:auto;overflow-y:auto;-webkit-overflow-scrolling:touch;
max-height:26rem;overscroll-behavior:contain}
.vla-table-wrap-tall{max-height:min(75vh,46rem)}
.vla-table{width:100%;border-collapse:separate;border-spacing:0;
font-size:.8125rem;font-variant-numeric:tabular-nums}
.vla-table th,.vla-table td{padding:.625rem 1rem;text-align:left;
vertical-align:middle;white-space:nowrap}
.vla-table thead th{position:sticky;top:0;z-index:1;
background:rgba(248,250,252,.92);backdrop-filter:blur(8px);
-webkit-backdrop-filter:blur(8px);
color:var(--vla-ink-soft);font-weight:600;font-size:.6875rem;
letter-spacing:.04em;text-transform:uppercase;
border-bottom:1px solid var(--vla-border-strong)}
.vla-table tbody tr{transition:background-color .15s ease-in-out}
.vla-table tbody tr+tr td{border-top:1px solid rgba(241,245,249,.9)}
.vla-table tbody tr:nth-child(even){background:rgba(248,250,252,.5)}
.vla-table tbody tr:hover{background:rgba(238,242,255,.7)}
.vla-table td{color:var(--vla-ink-2)}
.vla-table .vla-al,.vla-table th.vla-al{text-align:left}
.vla-table .vla-ac,.vla-table th.vla-ac{text-align:center}
.vla-table .vla-ar,.vla-table th.vla-ar{text-align:right;
font-variant-numeric:tabular-nums}
.vla-table .vla-key{font-weight:600;color:var(--vla-ink)}
.vla-table-empty{padding:2rem 1.25rem;text-align:center;color:var(--vla-ink-muted)}
/* Bảng do pandas sinh (không có class trên ô) vẫn được canh nền tảng. */
.vla-table-wrap>table{width:100%;border-collapse:separate;border-spacing:0;
font-size:.8125rem}
.vla-table-wrap>table th,.vla-table-wrap>table td{padding:.625rem 1rem;
text-align:left;border-bottom:1px solid rgba(241,245,249,.9);white-space:nowrap}
.vla-table-wrap>table thead th{position:sticky;top:0;background:rgba(248,250,252,.92);
color:var(--vla-ink-soft);font-weight:600;font-size:.6875rem;
letter-spacing:.04em;text-transform:uppercase}
.vla-table-wrap>table tbody tr:hover{background:rgba(238,242,255,.7)}

/* ---- 7. Badge / pill ------------------------------------------------- */
.vla-badge{display:inline-flex;align-items:center;gap:.3rem;
padding:.15rem .55rem;border-radius:999px;border:1px solid transparent;
font-size:.75rem;font-weight:600;line-height:1.5;white-space:nowrap}
.vla-badge-ok{background:var(--vla-ok-soft);color:var(--vla-ok);
border-color:var(--vla-ok-border)}
.vla-badge-warn{background:var(--vla-warn-soft);color:var(--vla-warn);
border-color:var(--vla-warn-border)}
.vla-badge-bad{background:var(--vla-bad-soft);color:var(--vla-bad);
border-color:var(--vla-bad-border)}
.vla-badge-brand{background:var(--vla-brand-soft);color:var(--vla-brand-ink);
border-color:var(--vla-brand-border)}
.vla-badge-mute{background:var(--vla-surface-2);color:var(--vla-ink-soft);
border-color:var(--vla-border-strong)}

/* ---- 8. Nav / liên kết trang ----------------------------------------- */
.vla-nav{display:flex;flex-wrap:wrap;gap:.5rem;margin:0 0 1.5rem}
.vla-nav a{display:inline-flex;align-items:center;padding:.375rem .75rem;
border-radius:var(--vla-r-md);border:1px solid var(--vla-border);
background:var(--vla-surface);color:var(--vla-ink-soft);
font-size:.8125rem;font-weight:500;transition:all .15s ease-in-out}
.vla-nav a:hover{border-color:var(--vla-brand-border);color:var(--vla-brand-ink);
background:var(--vla-brand-soft);text-decoration:none}
.vla-nav a[aria-current="page"]{background:var(--vla-brand);color:#fff;
border-color:var(--vla-brand)}

/* ---- 9. Khối phụ trợ ------------------------------------------------- */
/* Giới hạn chiều cao: dữ liệu JSON dài không được kéo dài trang vô hạn. */
.vla-pre{margin:0;padding:.875rem 1rem;background:var(--vla-surface-2);
border:1px solid var(--vla-border);border-radius:var(--vla-r-md);
font-family:var(--vla-mono);font-size:.75rem;line-height:1.6;
flex:1 1 auto;min-height:0;max-height:26rem;overflow:auto;white-space:pre;
color:var(--vla-ink-soft);overscroll-behavior:contain}
.vla-muted{color:var(--vla-ink-soft);font-size:.8125rem}
.vla-note{padding:.75rem 1rem;background:var(--vla-brand-soft);
border:1px solid var(--vla-brand-border);border-radius:var(--vla-r-md);
color:var(--vla-brand-ink);font-size:.8125rem}
.vla-stat{display:flex;flex-direction:column;gap:.2rem}
.vla-stat-label{color:var(--vla-ink-soft);font-size:.75rem;font-weight:500;
letter-spacing:.02em;text-transform:uppercase}
.vla-stat-value{color:var(--vla-ink);font-size:1.5rem;font-weight:600;
letter-spacing:-.02em;font-variant-numeric:tabular-nums}

/* ---- 10. Tiện ích kiểu Tailwind (giữ tương thích ngược) -------------- */
.bg-slate-50{background-color:#f8fafc}.bg-slate-50\/50{background-color:rgba(248,250,252,.5)}
.bg-white{background-color:#fff}.bg-indigo-600{background-color:#4f46e5}
.text-slate-900{color:#0f172a}.text-slate-800{color:#1e293b}
.text-slate-600{color:#475569}.text-slate-500{color:#64748b}.text-slate-400{color:#94a3b8}
.text-indigo-600{color:#4f46e5}.text-blue-600{color:#2563eb}.text-white{color:#fff}
.border{border-width:1px;border-style:solid}
.border-slate-200\/60{border-color:rgba(226,232,240,.6)}
.rounded-md{border-radius:.375rem}.rounded-lg{border-radius:.5rem}
.rounded-xl{border-radius:.75rem}.rounded-2xl{border-radius:1rem}
.shadow-sm{box-shadow:var(--vla-sh-sm)}.shadow-md{box-shadow:var(--vla-sh-md)}
.flex{display:flex}.grid{display:grid}.hidden{display:none}
.flex-wrap{flex-wrap:wrap}.flex-col{flex-direction:column}
.items-center{align-items:center}.items-stretch{align-items:stretch}
.justify-between{justify-content:space-between}.justify-center{justify-content:center}
.gap-2{gap:.5rem}.gap-3{gap:.75rem}.gap-4{gap:1rem}.gap-6{gap:1.5rem}
.p-4{padding:1rem}.p-6{padding:1.5rem}
.px-4{padding-left:1rem;padding-right:1rem}.py-3{padding-top:.75rem;padding-bottom:.75rem}
.py-6{padding-top:1.5rem;padding-bottom:1.5rem}
.mb-4{margin-bottom:1rem}.mb-6{margin-bottom:1.5rem}.mt-4{margin-top:1rem}
.mx-auto{margin-left:auto;margin-right:auto}
.max-w-6xl{max-width:72rem}.max-w-7xl{max-width:80rem}.w-full{width:100%}
.text-left{text-align:left}.text-center{text-align:center}.text-right{text-align:right}
.font-medium{font-weight:500}.font-semibold{font-weight:600}.font-bold{font-weight:700}
.italic{font-style:italic}.underline{text-decoration-line:underline}
.overflow-x-auto{overflow-x:auto}.table-auto{table-layout:auto}.table-fixed{table-layout:fixed}
.transition-all{transition-property:all}.duration-200{transition-duration:.2s}
.ease-in-out{transition-timing-function:cubic-bezier(.4,0,.2,1)}
.hover\:shadow-lg:hover{box-shadow:var(--vla-sh-lg)}
.hover\:shadow-md:hover{box-shadow:var(--vla-sh-md)}
.hover\:-translate-y-0\.5:hover{transform:translateY(-.125rem)}
@media (min-width:640px){.sm\:px-6{padding-left:1.5rem;padding-right:1.5rem}}
@media (min-width:768px){
.md\:grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}
.md\:flex-row{flex-direction:row}
}
@media (min-width:1024px){
.lg\:px-8{padding-left:2rem;padding-right:2rem}
.lg\:grid-cols-12{grid-template-columns:repeat(12,minmax(0,1fr))}
.lg\:col-span-4{grid-column:span 4/span 4}
.lg\:col-span-8{grid-column:span 8/span 8}
}

/* ---- 11. In ấn ------------------------------------------------------- */
@media print{
body{background:#fff}
.vla-card{box-shadow:none;break-inside:avoid}
.vla-table-wrap{max-height:none;overflow:visible}
.vla-nav{display:none}
}
""".strip()


def tailwind_style_tag() -> str:
    """Trả về thẻ style CSP-safe; không gọi CDN bên ngoài."""

    return f'<style id="vla-tailwind-lite">{TAILWIND_LITE_CSS}</style>'


def shell_open(*, wide: bool = False) -> str:
    """Mở container căn giữa dùng chung cho mọi trang."""

    extra = " vla-shell-wide" if wide else ""
    return f'<div class="vla-shell{extra}">'


def shell_close() -> str:
    """Đóng container mở bởi :func:`shell_open`."""

    return "</div>"


def page_header(title: str, subtitle: str = "", meta: Iterable[str] = ()) -> str:
    """Dựng khối tiêu đề trang thống nhất (đã escape)."""

    parts = [
        '<header class="vla-header">',
        f"<h1>{html.escape(title)}</h1>",
    ]
    if subtitle:
        parts.append(f'<p class="vla-sub">{html.escape(subtitle)}</p>')
    items = [html.escape(str(m)) for m in meta if str(m).strip()]
    if items:
        cells = "".join(f"<span>{item}</span>" for item in items)
        parts.append(f'<div class="vla-meta">{cells}</div>')
    parts.append("</header>")
    return "".join(parts)


def nav_links(links: Sequence[tuple[str, str]], current: str = "") -> str:
    """Dựng thanh liên kết giữa các trang tĩnh."""

    if not links:
        return ""
    items = []
    for href, label in links:
        mark = ' aria-current="page"' if href == current else ""
        items.append(
            f'<a href="{html.escape(href)}"{mark}>{html.escape(label)}</a>'
        )
    return f'<nav class="vla-nav">{"".join(items)}</nav>'


def card(
    body: str,
    *,
    title: str = "",
    aside: str = "",
    span: int = 0,
    flush: bool = False,
    lift: bool = False,
) -> str:
    """Bọc nội dung trong một card thống nhất.

    ``span`` là số cột (1..12) trên breakpoint ``lg``; ``flush`` bỏ padding thân
    card để bảng chạm sát viền; ``lift`` bật hiệu ứng nâng khi rê chuột.
    """

    classes = ["vla-card"]
    if lift:
        classes.append("vla-card-lift")
    if span:
        classes.append(f"vla-c{max(1, min(12, int(span)))}")
    head = ""
    if title or aside:
        head = (
            '<div class="vla-card-head">'
            f"<h2>{html.escape(title)}</h2>{aside}"
            "</div>"
        )
    body_class = "vla-card-body vla-card-flush" if flush else "vla-card-body"
    return (
        f'<section class="{" ".join(classes)}">'
        f'{head}<div class="{body_class}">{body}</div>'
        "</section>"
    )


def _is_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def render_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    align: Sequence[str] | None = None,
    empty: str = "Chưa có dữ liệu.",
    key_column: int = -1,
) -> str:
    """Dựng bảng đã canh cột, có header dính và vùng cuộn ngang riêng.

    ``align`` nhận danh sách ``left``/``center``/``right`` theo từng cột. Khi bỏ
    trống, cột được suy ra từ dữ liệu: giá trị số canh phải, còn lại canh trái.
    """

    body_rows = [list(r) for r in rows]
    if not body_rows:
        return f'<p class="vla-table-empty">{html.escape(empty)}</p>'

    width = len(headers)
    if align is None:
        first = body_rows[0]
        align = [
            ALIGN_RIGHT
            if index < len(first) and _is_numeric(first[index])
            else ALIGN_LEFT
            for index in range(width)
        ]
    classes = [
        _ALIGN_CLASS.get(align[i] if i < len(align) else ALIGN_LEFT, "vla-al")
        for i in range(width)
    ]

    head = "".join(
        f'<th scope="col" class="{classes[i]}">{html.escape(str(h))}</th>'
        for i, h in enumerate(headers)
    )
    out = [
        '<div class="vla-table-wrap"><table class="vla-table">',
        f"<thead><tr>{head}</tr></thead><tbody>",
    ]
    for row in body_rows:
        cells = []
        for index in range(width):
            value = row[index] if index < len(row) else ""
            cell_class = classes[index]
            if index == key_column:
                cell_class += " vla-key"
            cells.append(f'<td class="{cell_class}">{html.escape(str(value))}</td>')
        out.append(f"<tr>{''.join(cells)}</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def dataframe_table(
    frame: Any,
    *,
    align: Sequence[str] | None = None,
    empty: str = "Chưa có dữ liệu.",
    key_column: int = -1,
) -> str:
    """Bọc :func:`render_table` cho ``pandas.DataFrame`` đã định dạng sẵn."""

    if frame is None or getattr(frame, "empty", True):
        return f'<p class="vla-table-empty">{html.escape(empty)}</p>'
    headers = [str(c) for c in frame.columns]
    rows = frame.astype(object).where(frame.notna(), "").values.tolist()
    return render_table(
        headers, rows, align=align, empty=empty, key_column=key_column
    )


def table_wrap(inner_html: str) -> str:
    """Bọc bảng HTML có sẵn (ví dụ ``DataFrame.to_html``) vào vùng cuộn chuẩn."""

    return f'<div class="vla-table-wrap">{inner_html}</div>'
