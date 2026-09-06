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
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final


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
/* Chữ đặt TRÊN nền thương hiệu. Phải lật cùng lúc với --vla-brand: ở chế
độ tối nền thương hiệu sáng lên, và chữ trắng chỉ còn 2,75:1. */
--vla-on-brand:#ffffff;
--vla-ok:#047857;--vla-ok-soft:#ecfdf5;--vla-ok-border:#a7f3d0;
--vla-warn:#b45309;--vla-warn-soft:#fffbeb;--vla-warn-border:#fde68a;
--vla-bad:#be123c;--vla-bad-soft:#fff1f2;--vla-bad-border:#fecdd3;
--vla-r-md:.5rem;--vla-r-lg:.75rem;--vla-r-xl:1rem;
--vla-sh-sm:0 1px 2px rgba(15,23,42,.06);
--vla-sh-md:0 4px 12px rgba(15,23,42,.10);
--vla-sh-lg:0 10px 25px rgba(15,23,42,.14);
/* Aptos là font của Microsoft, phát hành kèm Microsoft 365. Giấy phép KHÔNG
cho phép phân phối lại tệp font, và CSP của kho đặt font-src 'self' nên cũng
không tải được từ host ngoài. Khai báo theo tên là cách đúng: máy có Microsoft
365 hiển thị Aptos thật, máy khác lùi về font hệ thống mà không hỏng bố cục. */
--vla-font:Aptos,"Aptos Display","Segoe UI Variable Text",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--vla-font-display:"Aptos Display",Aptos,var(--vla-font);
--vla-mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
--vla-sidebar-w:15rem;--vla-sidebar-w-collapsed:3.75rem;
color-scheme:light;
}

/* ---- 1b. Chế độ tối ---------------------------------------------------
Chỉ định nghĩa lại token, không lặp lại selector thành phần nào: mọi thành
phần đã lấy màu qua token nên đổi ở đây là đủ. Ba trạng thái được phủ — chọn
tay sáng, chọn tay tối, và mặc định "theo hệ điều hành" vốn không gắn thuộc
tính nào lên thẻ gốc. */
@media (prefers-color-scheme:dark){
:root:not([data-vla-theme="light"]){
--vla-bg:#0b1220;--vla-surface:#131c2e;--vla-surface-2:#0f1727;
--vla-border:rgba(35,50,72,.9);--vla-border-strong:#233248;
--vla-ink:#e8eef6;--vla-ink-2:#cbd7e6;--vla-ink-soft:#93a4bb;--vla-ink-muted:#64748b;
--vla-brand:#8b93f8;--vla-brand-ink:#a5abfa;--vla-brand-soft:#1b1f3d;--vla-brand-border:#343b6b;
--vla-on-brand:#0f172a;
--vla-ok:#4ade80;--vla-ok-soft:#0f2018;--vla-ok-border:#1f4034;
--vla-warn:#fbbf24;--vla-warn-soft:#231a08;--vla-warn-border:#4a3714;
--vla-bad:#fb7185;--vla-bad-soft:#2a1119;--vla-bad-border:#4d2030;
--vla-sh-sm:0 1px 2px rgba(0,0,0,.4);
--vla-sh-md:0 4px 12px rgba(0,0,0,.45);
--vla-sh-lg:0 10px 25px rgba(0,0,0,.5);
color-scheme:dark;
}
}
:root[data-vla-theme="dark"]{
--vla-bg:#0b1220;--vla-surface:#131c2e;--vla-surface-2:#0f1727;
--vla-border:rgba(35,50,72,.9);--vla-border-strong:#233248;
--vla-ink:#e8eef6;--vla-ink-2:#cbd7e6;--vla-ink-soft:#93a4bb;--vla-ink-muted:#64748b;
--vla-brand:#8b93f8;--vla-brand-ink:#a5abfa;--vla-brand-soft:#1b1f3d;--vla-brand-border:#343b6b;
--vla-on-brand:#0f172a;
--vla-ok:#4ade80;--vla-ok-soft:#0f2018;--vla-ok-border:#1f4034;
--vla-warn:#fbbf24;--vla-warn-soft:#231a08;--vla-warn-border:#4a3714;
--vla-bad:#fb7185;--vla-bad-soft:#2a1119;--vla-bad-border:#4d2030;
--vla-sh-sm:0 1px 2px rgba(0,0,0,.4);
--vla-sh-md:0 4px 12px rgba(0,0,0,.45);
--vla-sh-lg:0 10px 25px rgba(0,0,0,.5);
color-scheme:dark;
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
/* Chỉ áp màu chữ tiêu đề bên trong khung của chính hệ thống này. Đặt màu ở
   cấp h1..h4 toàn cục sẽ đè lên các trang có hero/nền tối riêng và làm tiêu
   đề của họ trùng màu nền. */
h1,h2,h3,h4{font-weight:600;line-height:1.25;margin:0 0 .5rem}
.vla-shell h1,.vla-shell h2,.vla-shell h3,.vla-shell h4,
.vla-card h2,.vla-card h3,.vla-header h1{color:var(--vla-ink)}
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
/* Bóng mờ hai mép chỉ hiện khi bảng thực sự cuộn được, để nội dung bị che
   đọc ra là "còn cuộn tiếp" chứ không phải bị cắt mất. */
.vla-table-wrap{width:100%;flex:1 1 auto;min-height:0;
overflow-x:auto;overflow-y:auto;-webkit-overflow-scrolling:touch;
max-height:26rem;overscroll-behavior:contain;
background:
linear-gradient(to right,var(--vla-surface) 30%,rgba(255,255,255,0)) left center/2.5rem 100% no-repeat local,
linear-gradient(to left,var(--vla-surface) 30%,rgba(255,255,255,0)) right center/2.5rem 100% no-repeat local,
radial-gradient(farthest-side at 0 50%,rgba(15,23,42,.14),rgba(15,23,42,0)) left center/.875rem 100% no-repeat scroll,
radial-gradient(farthest-side at 100% 50%,rgba(15,23,42,.14),rgba(15,23,42,0)) right center/.875rem 100% no-repeat scroll}
.vla-table-wrap-tall{max-height:min(75vh,46rem)}
.vla-table{width:100%;border-collapse:separate;border-spacing:0;
font-size:.8125rem;font-variant-numeric:tabular-nums}
.vla-table th,.vla-table td{padding:.625rem 1rem;text-align:left;
vertical-align:middle;white-space:normal;overflow-wrap:anywhere}
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
.vla-table .vla-ac,.vla-table th.vla-ac{text-align:center;white-space:nowrap}
.vla-table .vla-ar,.vla-table th.vla-ar{text-align:right;white-space:nowrap;
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
.vla-nav a[aria-current="page"]{background:var(--vla-brand);color:var(--vla-on-brand);
border-color:var(--vla-brand)}

/* ---- 8b. Tab: giữ nguyên hook .tabbtn/.panel cho script sẵn có -------- */
.vla-tabs{display:flex;flex-wrap:wrap;gap:.5rem;margin:0 0 1.25rem}
.vla-tabs .tabbtn{padding:.5rem .9rem;border:1px solid var(--vla-border);
border-radius:var(--vla-r-md);background:var(--vla-surface);
color:var(--vla-ink-soft);font-family:inherit;font-size:.8125rem;
font-weight:600;cursor:pointer;transition:all .15s ease-in-out}
.vla-tabs .tabbtn:hover{border-color:var(--vla-brand-border);
color:var(--vla-brand-ink);background:var(--vla-brand-soft)}
.vla-tabs .tabbtn.active{background:var(--vla-brand);color:var(--vla-on-brand);
border-color:var(--vla-brand)}
.panel{display:none}.panel.active{display:block}

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

/* ---- 12. Khung ứng dụng có sidebar thu gọn ---------------------------
Dùng grid-template-columns thay vì tính chiều rộng bằng JavaScript: chuyển
trạng thái chỉ là một phép đổi giá trị token, nên không có bước đo lại bố cục
và không giật khung. */
.vla-app{display:grid;grid-template-columns:var(--vla-sidebar-w) minmax(0,1fr);
min-height:100vh;transition:grid-template-columns .22s ease}
.vla-app[data-collapsed="true"]{grid-template-columns:var(--vla-sidebar-w-collapsed) minmax(0,1fr)}
.vla-app>*{min-width:0}

.vla-side{position:sticky;top:0;align-self:start;max-height:100vh;overflow-y:auto;
background:var(--vla-surface);border-right:1px solid var(--vla-border);
padding:.75rem 0 1.5rem;display:flex;flex-direction:column;gap:.125rem}
.vla-side-top{display:flex;align-items:center;gap:.5rem;padding:.25rem .75rem .75rem;
border-bottom:1px solid var(--vla-border);margin-bottom:.5rem}
.vla-side-toggle{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;
width:2rem;height:2rem;border-radius:var(--vla-r-md);border:1px solid var(--vla-border);
background:var(--vla-surface);color:var(--vla-ink-soft);cursor:pointer;
font:inherit;font-size:1rem;line-height:1;transition:all .15s ease-in-out}
.vla-side-toggle:hover{border-color:var(--vla-brand-border);color:var(--vla-brand-ink);
background:var(--vla-brand-soft)}
.vla-side-toggle:focus-visible{outline:2px solid var(--vla-brand);outline-offset:2px}
.vla-side-brand{font-family:var(--vla-font-display);font-weight:700;font-size:.9375rem;
color:var(--vla-ink);white-space:nowrap;overflow:hidden}

/* ink-muted (#94a3b8) chỉ đạt 2,56:1 trên nền trắng — dưới ngưỡng WCAG AA cho
chữ nhỏ. ink-soft đạt 7,5:1 và vẫn giữ được thứ bậc thị giác so với nhãn liên kết. */
.vla-side-group{font-size:.6875rem;letter-spacing:.08em;text-transform:uppercase;
color:var(--vla-ink-soft);font-weight:600;padding:.875rem .875rem .25rem;white-space:nowrap}
.vla-side a{display:flex;align-items:center;gap:.625rem;padding:.4375rem .875rem;
color:var(--vla-ink-2);font-size:.8125rem;white-space:nowrap;overflow:hidden;
border-left:3px solid transparent;transition:background .15s ease-in-out}
.vla-side a:hover{background:var(--vla-surface-2);text-decoration:none}
.vla-side a[aria-current="page"]{background:var(--vla-brand-soft);color:var(--vla-brand-ink);
font-weight:600;border-left-color:var(--vla-brand)}
.vla-side-ic{flex:0 0 1.25rem;text-align:center;font-size:.875rem}
.vla-side-label{overflow:hidden;text-overflow:ellipsis}
/* Nhãn chỉ dành cho trình đọc màn hình: nút thu gọn chỉ có biểu tượng, nên
nếu không có nhãn này thì người dùng trình đọc màn hình nghe thấy một nút trống. */
.vla-raw{margin-top:.75rem}
.vla-raw summary{cursor:pointer;font-size:.8125rem;color:var(--vla-ink-soft);
padding:.375rem 0;user-select:none}
.vla-raw summary:hover{color:var(--vla-brand-ink)}
.vla-raw[open] summary{margin-bottom:.5rem}
.vla-sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}

/* Khi thu gọn, nhãn biến mất nhưng biểu tượng giữ nguyên vị trí. */
.vla-app[data-collapsed="true"] .vla-side-group{height:0;padding:0;opacity:0;overflow:hidden}
.vla-app[data-collapsed="true"] .vla-side-label,
.vla-app[data-collapsed="true"] .vla-side-brand{width:0;opacity:0;overflow:hidden}

/* Trên mobile sidebar mặc định là dải biểu tượng; không có trạng thái nào ẩn
hoàn toàn điều hướng, vì trang tĩnh không có nút quay lại nào khác. */
@media (max-width:767px){
.vla-app{grid-template-columns:var(--vla-sidebar-w-collapsed) minmax(0,1fr)}
.vla-side-group{height:0;padding:0;opacity:0;overflow:hidden}
.vla-side-label,.vla-side-brand{width:0;opacity:0;overflow:hidden}
.vla-side-top{justify-content:center;padding-inline:.25rem}
}

/* ---- 13. Lưới nội dung tự co giãn -----------------------------------
Ba lớp cho ba nhu cầu bố cục cụ thể, tất cả đều align-items:stretch nên các ô
cùng hàng luôn bằng chiều cao và không sinh khoảng trống thò thụt. */
.vla-row{display:grid;gap:1.25rem;align-items:stretch;
grid-template-columns:repeat(auto-fit,minmax(min(22rem,100%),1fr))}
.vla-row>*{min-width:0}
.vla-duo{display:grid;gap:1.25rem;align-items:stretch;grid-template-columns:minmax(0,1fr)}
@media (min-width:768px){.vla-duo{grid-template-columns:repeat(2,minmax(0,1fr))}}
.vla-trio{display:grid;gap:1.25rem;align-items:stretch;grid-template-columns:minmax(0,1fr)}
@media (min-width:768px){.vla-trio{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:1200px){.vla-trio{grid-template-columns:repeat(3,minmax(0,1fr))}}
.vla-duo>*,.vla-trio>*{min-width:0;display:flex;flex-direction:column}
.vla-duo>*>.vla-card-body,.vla-trio>*>.vla-card-body{flex:1 1 auto}

/* ---- 14. Trạng thái rỗng và đang tải ---------------------------------
Một trang trống không kèm lời giải thích không phân biệt được với một trang
hỏng. Khối này luôn nói RÕ vì sao trống và chỉ ra lối đi tiếp. */
.vla-empty{display:flex;flex-direction:column;align-items:center;text-align:center;
gap:.625rem;padding:2.5rem 1.5rem;color:var(--vla-ink-soft)}
.vla-empty-icon{font-size:1.75rem;line-height:1;opacity:.55}
.vla-empty h3{margin:0;font-size:1rem;color:var(--vla-ink)}
.vla-empty p{margin:0;max-width:46ch;font-size:.875rem}
.vla-empty-why{background:var(--vla-surface-2);border:1px solid var(--vla-border);
border-radius:var(--vla-r-md);padding:.75rem 1rem;font-size:.8125rem;
text-align:left;max-width:52ch;margin-top:.25rem}
.vla-skeleton{background:linear-gradient(90deg,var(--vla-surface-2) 25%,
var(--vla-border-strong) 37%,var(--vla-surface-2) 63%);
background-size:400% 100%;animation:vla-shimmer 1.4s ease infinite;
border-radius:var(--vla-r-md);height:1rem;margin:.5rem 0}
@keyframes vla-shimmer{0%{background-position:100% 50%}100%{background-position:0 50%}}
@media (prefers-reduced-motion:reduce){
.vla-skeleton{animation:none}
.vla-app{transition:none}
}

/* ---- 11. In ấn ------------------------------------------------------- */
@media print{
body{background:#fff}
.vla-card{box-shadow:none;break-inside:avoid}
.vla-table-wrap{max-height:none;overflow:visible}
.vla-nav{display:none}
}
""".strip()


def _column_align_rules(columns: int = 10) -> str:
    """Sinh class căn lề theo vị trí cột.

    Dùng cho bảng được ghép chuỗi ``<tr><td>`` thủ công, nơi không tiện gắn
    class lên từng ô: chỉ cần thêm ``vla-r3`` (cột 3 canh phải) hoặc
    ``vla-m2`` (cột 2 canh giữa) lên chính thẻ ``<table>``.
    """

    parts = []
    for index in range(1, columns + 1):
        for suffix, value in (("r", "right"), ("m", "center")):
            parts.append(
                f".vla-table.vla-{suffix}{index} td:nth-child({index}),"
                f".vla-table.vla-{suffix}{index} th:nth-child({index})"
                f"{{text-align:{value};white-space:nowrap}}"
            )
    return "\n".join(parts)


TAILWIND_LITE_CSS = f"{TAILWIND_LITE_CSS}\n{_column_align_rules()}"


#: Điều hướng dùng chung cho MỌI trang, chia năm nhóm.
#:
#: Trước đây có ba bảng điều hướng ở ba tệp builder khác nhau, liệt kê những
#: trang khác nhau và không bảng nào phủ hết 14 trang; hai trang soi cầu ổn định
#: không được liên kết từ bất kỳ đâu. Một nguồn duy nhất khiến tình trạng đó
#: không tái diễn được: thêm trang mà quên thêm vào menu sẽ bị test bắt.
SITE_NAV: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "Trực tiếp",
        (
            ("live.html", "Kết quả trực tiếp", "◉"),
            ("index.html", "Kết quả hôm nay", "▤"),
        ),
    ),
    (
        "Thống kê",
        (
            ("statistics.html", "Ma trận thống kê", "▦"),
            ("index.html#tan-suat-loto", "Tần suất lô tô", "◧"),
            ("index.html#gan-nhip", "Gan &amp; nhịp", "◷"),
            ("index.html#cap-lon", "Cặp lộn &amp; bóng", "⇅"),
        ),
    ),
    (
        "Cầu kèo",
        (
            ("soi-path-loto-active.html", "Cầu lô tô đang chạy", "⟋"),
            ("soi-path-loto-stable.html", "Cầu lô tô ổn định", "⟊"),
            ("soi-path-de-active.html", "Cầu ĐB đang chạy", "⟍"),
            ("soi-path-de-stable.html", "Cầu ĐB ổn định", "⟌"),
            ("index.html#duong-cau", "Căn cứ vị trí cầu", "⌗"),
        ),
    ),
    (
        "Phỏng đoán",
        (
            ("dashboard.html", "Bảng điều khiển AI/ML", "◈"),
            ("ml_top10_loto.html", "10 số lô tô", "①"),
            ("ml_top10_de.html", "10 số Đặc Biệt", "②"),
            ("model-quality.html", "Chất lượng mô hình", "✓"),
        ),
    ),
    (
        "Tool nâng cao",
        (
            ("research-lab.html", "Phòng nghiên cứu", "⚗"),
            ("index.html#backtest", "Kiểm định AI/ML", "⟳"),
        ),
    ),
)


#: Mọi trang HTML mà điều hướng phải phủ. Test đối chiếu với docs/*.html.
def nav_targets() -> set[str]:
    """Tập tệp .html mà :data:`SITE_NAV` trỏ tới, đã bỏ phần neo."""

    return {
        href.split("#", 1)[0]
        for _, items in SITE_NAV
        for href, _, _ in items
        if href.split("#", 1)[0]
    }


STYLESHEET_NAME = "assets/vla.css"

#: Script điều khiển sidebar. Nội tuyến vì CSP cho phép 'unsafe-inline' cho
#: script, và vì một tệp rời cho 30 dòng sẽ thêm một lượt tải cho mỗi trang.
SIDEBAR_SCRIPT = """
(function(){
  var KEY='vla-sidebar-collapsed';
  var app=document.getElementById('vla-app');
  var btn=document.getElementById('vla-side-toggle');
  if(!app||!btn){return;}
  function read(){try{return window.localStorage.getItem(KEY)==='true';}catch(e){return false;}}
  function write(v){try{window.localStorage.setItem(KEY,v?'true':'false');}catch(e){}}
  function apply(c){
    app.setAttribute('data-collapsed',c?'true':'false');
    btn.setAttribute('aria-expanded',c?'false':'true');
    btn.setAttribute('title',c?'Mở rộng menu':'Thu gọn menu');
  }
  apply(read());
  btn.addEventListener('click',function(){
    var next=app.getAttribute('data-collapsed')!=='true';
    write(next);apply(next);
  });
})();
""".strip()


def write_stylesheet(docs_dir: Path) -> Path:
    """Ghi biểu định kiểu dùng chung ra ``docs/assets/vla.css``.

    Trước đây toàn bộ CSS nội tuyến trong từng trang: khoảng 250 KB lặp lại
    trên 14 trang, không trang nào dùng lại được cache của trang nào. Một tệp
    cùng nguồn hợp lệ với CSP hiện tại (``style-src 'self'``) nên không phải
    nới chính sách bảo mật.
    """
    target = Path(docs_dir) / STYLESHEET_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TAILWIND_LITE_CSS, encoding="utf-8")
    return target


def stylesheet_link() -> str:
    """Thẻ liên kết tới biểu định kiểu dùng chung."""

    return f'<link rel="stylesheet" href="{STYLESHEET_NAME}" />'


def sidebar(current: str = "", *, brand: str = "Thống kê XSMB") -> str:
    """Dựng menu trái thu gọn được, trạng thái lưu trong ``localStorage``."""

    parts = [
        '<aside class="vla-side" id="vla-side">',
        '<div class="vla-side-top">',
        '<button class="vla-side-toggle" id="vla-side-toggle" type="button"'
        ' aria-expanded="true" aria-controls="vla-side" title="Thu gọn menu">'
        '<span aria-hidden="true">☰</span>'
        '<span class="vla-sr-only">Thu gọn menu</span></button>',
        f'<span class="vla-side-brand">{html.escape(brand)}</span>',
        "</div>",
    ]
    for group, items in SITE_NAV:
        parts.append(f'<p class="vla-side-group">{group}</p>')
        for href, label, icon in items:
            mark = ' aria-current="page"' if href == current else ""
            parts.append(
                f'<a href="{href}"{mark}>'
                f'<span class="vla-side-ic" aria-hidden="true">{icon}</span>'
                f'<span class="vla-side-label">{label}</span></a>'
            )
    parts.append("</aside>")
    return "".join(parts)


def app_shell_open(current: str = "", *, wide: bool = False) -> str:
    """Mở khung ứng dụng: sidebar bên trái, nội dung căn giữa bên phải."""

    extra = " vla-shell-wide" if wide else ""
    return (
        f'<div class="vla-app" id="vla-app" data-collapsed="false">'
        f"{sidebar(current)}"
        f'<main class="vla-shell{extra}">'
    )


def app_shell_close() -> str:
    """Đóng khung mở bởi :func:`app_shell_open` và gắn script sidebar."""

    return f"</main></div><script>{SIDEBAR_SCRIPT}</script>"


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
        items.append(f'<a href="{html.escape(href)}"{mark}>{html.escape(label)}</a>')
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
        head = f'<div class="vla-card-head"><h2>{html.escape(title)}</h2>{aside}</div>'
    body_class = "vla-card-body vla-card-flush" if flush else "vla-card-body"
    return (
        f'<section class="{" ".join(classes)}">'
        f'{head}<div class="{body_class}">{body}</div>'
        "</section>"
    )


#: Hai màu chữ dùng cho ô tô nền. Chọn giữa chúng theo tỉ lệ tương phản THỰC
#: TẾ, không theo ngưỡng độ sáng: một ngưỡng cố định luôn để lọt một dải nền
#: tầm trung mà cả hai màu đều không đạt chuẩn.
_INK_LIGHT: Final[str] = "#ffffff"
_INK_DARK: Final[str] = "#0f172a"
_INK_DARKEST: Final[str] = "#000000"

WCAG_AA_NORMAL: Final[float] = 4.5
WCAG_AA_LARGE: Final[float] = 3.0


def _srgb_luminance(hex_color: str) -> float:
    """Độ sáng tương đối theo WCAG của một màu ``#rrggbb``."""
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """Tỉ lệ tương phản WCAG giữa hai màu ``#rrggbb`` (1.0 tới 21.0)."""
    a, b = _srgb_luminance(foreground), _srgb_luminance(background)
    lo, hi = min(a, b), max(a, b)
    return (hi + 0.05) / (lo + 0.05)


def readable_ink(background: str, *, minimum: float = WCAG_AA_NORMAL) -> str:
    """Màu chữ đọc được trên ``background``, đảm bảo đạt ``minimum``.

    Cách cũ dùng ngưỡng độ sáng cố định (``luminance < 0.42 → trắng``). Ngưỡng
    kiểu đó bỏ sót cả một dải nền tầm trung: đo trên trang thật, chữ trắng nằm
    trên nền xanh ``#8aacf5`` chỉ đạt 2,26:1 và trên nền cam ``#ea580c`` đạt
    3,56:1 — đều dưới chuẩn AA cho chữ thường.

    Chọn theo tỉ lệ thật thì luôn có lời giải: dải nền mà chữ trắng không đạt
    và dải mà ``#0f172a`` không đạt chồng lấn nhau, nên thêm màu đen tuyền là
    phủ kín mọi nền.
    """
    candidates = (_INK_LIGHT, _INK_DARK, _INK_DARKEST)
    best = max(candidates, key=lambda ink: contrast_ratio(ink, background))
    if contrast_ratio(best, background) >= minimum:
        # Ưu tiên #0f172a hơn đen tuyền khi cả hai cùng đạt: mềm mắt hơn.
        if best is _INK_DARKEST and contrast_ratio(_INK_DARK, background) >= minimum:
            return _INK_DARK
        return best
    return best


def _format_scalar(value: Any) -> str:
    """Định dạng một giá trị đơn cho bảng, giữ nguyên độ chính xác có nghĩa."""

    if isinstance(value, bool):
        return "Có" if value else "Không"
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def definition_table(
    payload: Mapping[str, Any],
    *,
    labels: Mapping[str, str] | None = None,
    label_of: Any = None,
    max_list: int = 6,
) -> str:
    """Dựng bảng nhãn–giá trị từ một ánh xạ lồng nhau.

    Thay cho việc đổ JSON thô ra thẻ ``<pre>``. Khối JSON thô đọc được với người
    viết ra nó và gần như vô nghĩa với người dùng trang, lại còn lộ ra tên khóa
    chưa dịch nằm cạnh nhãn đã dịch.

    Dict lồng nhau được làm phẳng thành nhãn hai cấp thay vì lồng bảng trong
    bảng: bảng lồng nhau trên màn hình hẹp là nguồn tràn ngang kinh điển.
    """
    resolve = label_of or (lambda key: key)
    overrides = dict(labels or {})

    def name(key: str, prefix: str = "") -> str:
        label = overrides.get(key) or resolve(key)
        return f"{prefix}{label}" if not prefix else f"{prefix} · {label}"

    rows: list[tuple[str, str]] = []

    def walk(mapping: Mapping[str, Any], prefix: str = "") -> None:
        for key, value in mapping.items():
            label = name(str(key), prefix)
            if isinstance(value, Mapping):
                walk(value, label)
            elif isinstance(value, (list, tuple)):
                items = [_format_scalar(v) for v in value]
                shown = ", ".join(items[:max_list])
                if len(items) > max_list:
                    shown += f" … (tổng {len(items)})"
                rows.append((label, shown or "—"))
            else:
                rows.append((label, _format_scalar(value)))

    walk(payload)
    if not rows:
        return '<p class="vla-table-empty">Chưa có dữ liệu.</p>'

    body = "".join(
        f'<tr><td class="vla-al vla-key">{html.escape(label)}</td>'
        f'<td class="vla-ar">{html.escape(value)}</td></tr>'
        for label, value in rows
    )
    return (
        '<div class="vla-table-wrap"><table class="vla-table">'
        '<thead><tr><th class="vla-al" scope="col">Mục</th>'
        '<th class="vla-ar" scope="col">Giá trị</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def raw_details(payload: Any, *, summary: str = "Xem dữ liệu gốc (JSON)") -> str:
    """Khối gập lại chứa JSON gốc, dành cho người muốn kiểm chứng số liệu."""

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f'<details class="vla-raw"><summary>{html.escape(summary)}</summary>'
        f'<pre class="vla-pre">{html.escape(text)}</pre></details>'
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
            ALIGN_RIGHT if index < len(first) and _is_numeric(first[index]) else ALIGN_LEFT
            for index in range(width)
        ]
    classes = [
        _ALIGN_CLASS.get(align[i] if i < len(align) else ALIGN_LEFT, "vla-al") for i in range(width)
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
    return render_table(headers, rows, align=align, empty=empty, key_column=key_column)


def table_wrap(inner_html: str) -> str:
    """Bọc bảng HTML có sẵn (ví dụ ``DataFrame.to_html``) vào vùng cuộn chuẩn."""

    return f'<div class="vla-table-wrap">{inner_html}</div>'
