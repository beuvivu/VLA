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
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from page_output import write_page, write_stylesheet_text


# Căn lề theo loại dữ liệu: số/chỉ số canh phải, trạng thái canh giữa.
ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"

_ALIGN_CLASS = {
    ALIGN_LEFT: "ui-al",
    ALIGN_CENTER: "ui-ac",
    ALIGN_RIGHT: "ui-ar",
}


TAILWIND_LITE_CSS = r"""
/* ---- 1. Design token ------------------------------------------------- */
:root{
--ui-bg:#F2F4FF;--ui-bg-2:#E6EAFB;--ui-surface:#fff;--ui-surface-2:#F7F8FE;
--ui-border:#E7EAF6;--ui-border-strong:#D8DDF0;
--ui-ink:#161C2D;--ui-ink-2:#28304A;--ui-ink-soft:#5A6480;
/* Lưới sáng periwinkle phủ trên nền dốc. Tách thành token riêng để chế độ
   tối tắt hẳn nó đi thay vì phải viết lại quy tắc body. */
--ui-bg-mesh:radial-gradient(1200px 620px at 10% -8%,rgba(129,140,248,.20),transparent 60%),
radial-gradient(900px 520px at 92% 2%,rgba(99,102,241,.15),transparent 62%);
/* THƯƠNG HIỆU — chỉ dành cho điều hướng và hành động chính. Không một dấu
   hiệu mã hoá dữ liệu nào được lấy màu từ đây; màu phân tích nằm ở khối
   --ui-ok/warn/bad và ở các thang nhiệt của từng trang. */
--ui-brand:#4f46e5;--ui-brand-ink:#4338ca;--ui-brand-soft:#eef2ff;--ui-brand-border:#c7d2fe;
--ui-brand-grad:linear-gradient(135deg,#4F46E5 0%,#4C3BC4 54%,#5B2E9E 100%);
/* Chữ đặt TRÊN nền thương hiệu. Phải lật cùng lúc với --ui-brand: ở chế
độ tối nền thương hiệu sáng lên, và chữ trắng chỉ còn 2,75:1. */
--ui-on-brand:#ffffff;
--ui-ok:#047857;--ui-ok-soft:#ecfdf5;--ui-ok-border:#a7f3d0;
--ui-warn:#a94e08;--ui-warn-soft:#fffbeb;--ui-warn-border:#fde68a;
--ui-bad:#be123c;--ui-bad-soft:#fff1f2;--ui-bad-border:#fecdd3;
/* 18-24px cho bề mặt nổi; .75rem giữ lại cho chi tiết nhỏ bên trong, vì bo
   18px lên một ô 32px thì góc ăn hết cạnh. */
--ui-r-md:.75rem;--ui-r-lg:1.125rem;--ui-r-xl:1.5rem;
/* Bóng hai lớp, ám lạnh theo màu mực: một lớp sát để tách khỏi nền, một lớp
   toả rộng rất nhạt để bề mặt trông nổi lên chứ không bị viền đen. */
--ui-sh-sm:0 1px 2px rgba(22,28,45,.04),0 8px 26px rgba(22,28,45,.06);
--ui-sh-md:0 2px 4px rgba(22,28,45,.05),0 14px 38px rgba(22,28,45,.09);
--ui-sh-lg:0 4px 8px rgba(22,28,45,.06),0 22px 60px rgba(22,28,45,.13);
--ui-sh-brand:0 10px 30px rgba(79,70,229,.26);
/* Inter tự host. Bản trước khai báo Aptos theo tên, nhưng CSP đặt font-src
'self' và kho KHÔNG có tệp font nào — nên trang chưa bao giờ hiển thị bằng
Aptos trừ máy đã cài sẵn Microsoft 365; mọi máy khác rơi về font hệ thống.
Aptos cũng không được phép phân phối lại nên không thể tự host hợp pháp.
Inter theo giấy phép SIL OFL thì được, và bản variable cho đủ 9 độ đậm trong
một tệp 172 KB đã cắt gọn còn Latin + tiếng Việt. */
--ui-font:"Inter var",Inter,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--ui-font-display:var(--ui-font);
--ui-mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;

/* Thang 8pt. Mọi padding/margin/gap chỉ được lấy từ đây — một giá trị nằm
ngoài thang là một quyết định chưa được cân nhắc. */
--s1:8px;--s2:16px;--s3:24px;--s4:32px;--s5:40px;--s6:48px;--s8:64px;

/* Bo góc và viền hạt mịn */
--r-card:16px;--r-inner:12px;--r-pill:999px;
--hairline:rgba(15,23,42,.06);

/* Thang chữ — số dùng tabular-nums để cột số không nhảy khi giá trị đổi */
--fs-display:clamp(28px,2.4vw,40px);
--fs-title:20px;--fs-metric:clamp(32px,2.2vw,44px);
--fs-body:15px;--fs-label:12px;

--ui-dock-h:54px;
color-scheme:light;
}

/* ---- 1a. Phông tự host ------------------------------------------------
Một khai báo cho cả dải 100–900 nhờ trục variable, nên không cần 9 tệp riêng.
font-display:swap để chữ hiện ngay bằng font hệ thống rồi mới hoán đổi — 172 KB
vẫn là 172 KB, nhưng người đọc không phải nhìn trang trắng trong lúc chờ. */
@font-face{
font-family:"Inter var";
font-style:normal;
font-weight:100 900;
font-display:swap;
src:url("InterVariable.woff2") format("woff2-variations");
}

/* ---- 1b. Chế độ tối ---------------------------------------------------
Chỉ định nghĩa lại token, không lặp lại selector thành phần nào: mọi thành
phần đã lấy màu qua token nên đổi ở đây là đủ. Ba trạng thái được phủ — chọn
tay sáng, chọn tay tối, và mặc định "theo hệ điều hành" vốn không gắn thuộc
tính nào lên thẻ gốc. */
@media (prefers-color-scheme:dark){
:root:not([data-ui-theme="light"]){
--ui-bg:#0b1220;--ui-bg-2:#0b1220;--ui-bg-mesh:none;
--ui-surface:#131c2e;--ui-surface-2:#0f1727;--hairline:rgba(255,255,255,.08);
--ui-border:rgba(35,50,72,.9);--ui-border-strong:#233248;
--ui-ink:#e8eef6;--ui-ink-2:#cbd7e6;--ui-ink-soft:#97a8be;
--ui-brand:#8b93f8;--ui-brand-ink:#a5abfa;--ui-brand-soft:#1b1f3d;--ui-brand-border:#343b6b;
--ui-on-brand:#0f172a;
--ui-ok:#4ade80;--ui-ok-soft:#0f2018;--ui-ok-border:#1f4034;
--ui-warn:#fbbf24;--ui-warn-soft:#231a08;--ui-warn-border:#4a3714;
--ui-bad:#fb7185;--ui-bad-soft:#2a1119;--ui-bad-border:#4d2030;
--ui-sh-sm:0 1px 2px rgba(0,0,0,.4);
--ui-sh-md:0 4px 12px rgba(0,0,0,.45);
--ui-sh-lg:0 10px 25px rgba(0,0,0,.5);
--ui-sh-brand:0 10px 30px rgba(0,0,0,.5);
color-scheme:dark;
}
}
:root[data-ui-theme="dark"]{
--ui-bg:#0b1220;--ui-bg-2:#0b1220;--ui-bg-mesh:none;
--ui-surface:#131c2e;--ui-surface-2:#0f1727;--hairline:rgba(255,255,255,.08);
--ui-border:rgba(35,50,72,.9);--ui-border-strong:#233248;
--ui-ink:#e8eef6;--ui-ink-2:#cbd7e6;--ui-ink-soft:#97a8be;
--ui-brand:#8b93f8;--ui-brand-ink:#a5abfa;--ui-brand-soft:#1b1f3d;--ui-brand-border:#343b6b;
--ui-on-brand:#0f172a;
--ui-ok:#4ade80;--ui-ok-soft:#0f2018;--ui-ok-border:#1f4034;
--ui-warn:#fbbf24;--ui-warn-soft:#231a08;--ui-warn-border:#4a3714;
--ui-bad:#fb7185;--ui-bad-soft:#2a1119;--ui-bad-border:#4d2030;
--ui-sh-sm:0 1px 2px rgba(0,0,0,.4);
--ui-sh-md:0 4px 12px rgba(0,0,0,.45);
--ui-sh-lg:0 10px 25px rgba(0,0,0,.5);
--ui-sh-brand:0 10px 30px rgba(0,0,0,.5);
color-scheme:dark;
}

/* ---- 2. Nền tảng ----------------------------------------------------- */
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
/* Nền ba lớp: hai vầng periwinkle rồi mới tới dốc nền. background-attachment
   ghim cố định để vầng sáng không trôi theo khi cuộn — trang dài 1,7 MB mà
   để nó trôi thì phần dưới rơi hẳn vào mảng tối nhất của dốc. */
body{margin:0;color:var(--ui-ink-2);
background:var(--ui-bg-mesh),linear-gradient(162deg,var(--ui-bg) 0%,var(--ui-bg-2) 100%);
background-attachment:fixed;background-color:var(--ui-bg);
font-family:var(--ui-font);font-size:14px;line-height:1.6;
-webkit-font-smoothing:antialiased}
img{max-width:100%;height:auto}
a{color:var(--ui-brand);text-decoration:none}
a:hover{text-decoration:underline}
code,pre,.mono{font-family:var(--ui-mono)}
/* Chỉ áp màu chữ tiêu đề bên trong khung của chính hệ thống này. Đặt màu ở
   cấp h1..h4 toàn cục sẽ đè lên các trang có hero/nền tối riêng và làm tiêu
   đề của họ trùng màu nền. */
h1,h2,h3,h4{font-weight:600;line-height:1.25;margin:0 0 .5rem}
.ui-shell h1,.ui-shell h2,.ui-shell h3,.ui-shell h4,
.ui-card h2,.ui-card h3,.ui-header h1{color:var(--ui-ink)}
h1{font-size:1.5rem;letter-spacing:-.015em}
h2{font-size:1.125rem}
h3{font-size:1rem}
@media (min-width:768px){h1{font-size:1.875rem}h2{font-size:1.25rem}}

/* ---- 3. Khung trang: container căn giữa, không tràn ngang ------------- */
.ui-shell{width:100%;max-width:80rem;margin-inline:auto;padding:1.5rem 1rem 3rem}
@media (min-width:640px){.ui-shell{padding-left:1.5rem;padding-right:1.5rem}}
@media (min-width:1024px){.ui-shell{padding-left:2rem;padding-right:2rem;padding-top:2rem}}
.ui-shell-wide{max-width:90rem}

.ui-header{margin-bottom:1.5rem;padding-bottom:1.25rem;
border-bottom:1px solid var(--ui-border)}
.ui-header h1{margin-bottom:.35rem}
.ui-sub{color:var(--ui-ink-soft);font-size:.875rem;margin:0}
.ui-meta{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem .875rem;
margin-top:.625rem;color:var(--ui-ink-soft);font-size:.8125rem}

/* ---- 4. Lưới 12 cột: các ô luôn kéo đầy, không để khoảng trống lệch --- */
.ui-grid{display:grid;grid-template-columns:repeat(1,minmax(0,1fr));
gap:1.25rem;align-items:stretch}
.ui-grid>*{min-width:0}
@media (min-width:768px){
.ui-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:1.5rem}
.ui-grid-1-md{grid-template-columns:repeat(1,minmax(0,1fr))}
}
@media (min-width:1024px){
.ui-grid{grid-template-columns:repeat(12,minmax(0,1fr))}
.ui-c3{grid-column:span 3/span 3}.ui-c4{grid-column:span 4/span 4}
.ui-c5{grid-column:span 5/span 5}.ui-c6{grid-column:span 6/span 6}
.ui-c7{grid-column:span 7/span 7}.ui-c8{grid-column:span 8/span 8}
.ui-c9{grid-column:span 9/span 9}.ui-c12{grid-column:span 12/span 12}
}
/* Dưới lg mọi ô chiếm trọn hàng thay vì thu nhỏ lệch. */
@media (max-width:1023px){[class*="ui-c"]{grid-column:auto}}

/* ---- 5. Card --------------------------------------------------------- */
.ui-card{display:flex;flex-direction:column;background:var(--ui-surface);
border:1px solid var(--ui-border);border-radius:var(--ui-r-lg);
box-shadow:var(--ui-sh-sm);overflow:hidden;
transition:box-shadow .2s cubic-bezier(.4,0,.2,1),transform .2s cubic-bezier(.4,0,.2,1)}
.ui-card:hover{box-shadow:var(--ui-sh-md)}
.ui-card-lift:hover{transform:translateY(-2px);box-shadow:var(--ui-sh-lg)}
.ui-card-head{display:flex;flex-wrap:wrap;align-items:center;
justify-content:space-between;gap:.75rem;padding:1rem 1.25rem;
border-bottom:1px solid var(--ui-border)}
.ui-card-head h2,.ui-card-head h3{margin:0}
/* Thân card là flex dọc để khối nội dung cuối cùng kéo giãn lấp đầy chiều cao
   hàng lưới, thay vì bỏ lại khoảng trắng dưới đáy card thấp hơn. */
.ui-card-body{flex:1 1 auto;display:flex;flex-direction:column;gap:.75rem;
min-height:0;padding:1.25rem}
.ui-card-body>:first-child{margin-top:0}
.ui-card-body>:last-child{margin-bottom:0}
.ui-card-flush{padding:0}

/* ---- 6. Bảng dữ liệu ------------------------------------------------- */
/* Bóng mờ hai mép chỉ hiện khi bảng thực sự cuộn được, để nội dung bị che
   đọc ra là "còn cuộn tiếp" chứ không phải bị cắt mất. */
.ui-table-wrap{width:100%;flex:1 1 auto;min-height:0;
overflow-x:auto;overflow-y:auto;-webkit-overflow-scrolling:touch;
max-height:26rem;overscroll-behavior:contain;
background:
linear-gradient(to right,var(--ui-surface) 30%,rgba(255,255,255,0)) left center/2.5rem 100% no-repeat local,
linear-gradient(to left,var(--ui-surface) 30%,rgba(255,255,255,0)) right center/2.5rem 100% no-repeat local,
radial-gradient(farthest-side at 0 50%,rgba(15,23,42,.14),rgba(15,23,42,0)) left center/.875rem 100% no-repeat scroll,
radial-gradient(farthest-side at 100% 50%,rgba(15,23,42,.14),rgba(15,23,42,0)) right center/.875rem 100% no-repeat scroll}
.ui-table-wrap-tall{max-height:min(75vh,46rem)}
.ui-table{width:100%;border-collapse:separate;border-spacing:0;
font-size:.8125rem;font-variant-numeric:tabular-nums}
.ui-table th,.ui-table td{padding:.625rem 1rem;text-align:left;
vertical-align:middle;white-space:normal;overflow-wrap:anywhere}
.ui-table thead th{position:sticky;top:0;z-index:1;
background:rgba(248,250,252,.92);backdrop-filter:blur(8px);
-webkit-backdrop-filter:blur(8px);
color:var(--ui-ink-soft);font-weight:600;font-size:.6875rem;
letter-spacing:.04em;text-transform:uppercase;
border-bottom:1px solid var(--ui-border-strong)}
.ui-table tbody tr{transition:background-color .15s ease-in-out}
.ui-table tbody tr+tr td{border-top:1px solid rgba(241,245,249,.9)}
.ui-table tbody tr:nth-child(even){background:rgba(248,250,252,.5)}
.ui-table tbody tr:hover{background:rgba(238,242,255,.7)}
.ui-table td{color:var(--ui-ink-2)}
.ui-table .ui-al,.ui-table th.ui-al{text-align:left}
.ui-table .ui-ac,.ui-table th.ui-ac{text-align:center;white-space:nowrap}
.ui-table .ui-ar,.ui-table th.ui-ar{text-align:right;white-space:nowrap;
font-variant-numeric:tabular-nums}
.ui-table .ui-key{font-weight:600;color:var(--ui-ink)}
.ui-table-empty{padding:var(--s4) var(--s3);text-align:center;color:var(--ui-ink-soft)}
/* Bảng do pandas sinh (không có class trên ô) vẫn được canh nền tảng. */
.ui-table-wrap>table{width:100%;border-collapse:separate;border-spacing:0;
font-size:.8125rem}
.ui-table-wrap>table th,.ui-table-wrap>table td{padding:.625rem 1rem;
text-align:left;border-bottom:1px solid rgba(241,245,249,.9);white-space:nowrap}
.ui-table-wrap>table thead th{position:sticky;top:0;background:rgba(248,250,252,.92);
color:var(--ui-ink-soft);font-weight:600;font-size:.6875rem;
letter-spacing:.04em;text-transform:uppercase}
.ui-table-wrap>table tbody tr:hover{background:rgba(238,242,255,.7)}

/* ---- 7. Badge / pill ------------------------------------------------- */
.ui-badge{display:inline-flex;align-items:center;gap:.3rem;
padding:.15rem .55rem;border-radius:999px;border:1px solid transparent;
font-size:.75rem;font-weight:600;line-height:1.5;white-space:nowrap}
.ui-badge-ok{background:var(--ui-ok-soft);color:var(--ui-ok);
border-color:var(--ui-ok-border)}
.ui-badge-warn{background:var(--ui-warn-soft);color:var(--ui-warn);
border-color:var(--ui-warn-border)}
.ui-badge-bad{background:var(--ui-bad-soft);color:var(--ui-bad);
border-color:var(--ui-bad-border)}
.ui-badge-brand{background:var(--ui-brand-soft);color:var(--ui-brand-ink);
border-color:var(--ui-brand-border)}
.ui-badge-mute{background:var(--ui-surface-2);color:var(--ui-ink-soft);
border-color:var(--ui-border-strong)}

/* ---- 8. Nav / liên kết trang ----------------------------------------- */
.ui-nav{display:flex;flex-wrap:wrap;gap:.5rem;margin:0 0 1.5rem}
.ui-nav a{display:inline-flex;align-items:center;padding:.375rem .75rem;
border-radius:var(--ui-r-md);border:1px solid var(--ui-border);
background:var(--ui-surface);color:var(--ui-ink-soft);
font-size:.8125rem;font-weight:500;transition:all .15s ease-in-out}
.ui-nav a:hover{border-color:var(--ui-brand-border);color:var(--ui-brand-ink);
background:var(--ui-brand-soft);text-decoration:none}
.ui-nav a[aria-current="page"]{background:var(--ui-brand);color:var(--ui-on-brand);
border-color:var(--ui-brand)}

/* ---- 8b. Tab: giữ nguyên hook .tabbtn/.panel cho script sẵn có -------- */
.ui-tabs{display:flex;flex-wrap:wrap;gap:.5rem;margin:0 0 1.25rem}
.ui-tabs .tabbtn{padding:.5rem .9rem;border:1px solid var(--ui-border);
border-radius:var(--ui-r-md);background:var(--ui-surface);
color:var(--ui-ink-soft);font-family:inherit;font-size:.8125rem;
font-weight:600;cursor:pointer;transition:all .15s ease-in-out}
.ui-tabs .tabbtn:hover{border-color:var(--ui-brand-border);
color:var(--ui-brand-ink);background:var(--ui-brand-soft)}
.ui-tabs .tabbtn.active{background:var(--ui-brand);color:var(--ui-on-brand);
border-color:var(--ui-brand)}
.panel{display:none}.panel.active{display:block}

/* ---- 9. Khối phụ trợ ------------------------------------------------- */
/* Giới hạn chiều cao: dữ liệu JSON dài không được kéo dài trang vô hạn. */
.ui-pre{margin:0;padding:.875rem 1rem;background:var(--ui-surface-2);
border:1px solid var(--ui-border);border-radius:var(--ui-r-md);
font-family:var(--ui-mono);font-size:.75rem;line-height:1.6;
flex:1 1 auto;min-height:0;max-height:26rem;overflow:auto;white-space:pre;
color:var(--ui-ink-soft);overscroll-behavior:contain}
.ui-muted{color:var(--ui-ink-soft);font-size:.8125rem}
.ui-note{padding:.75rem 1rem;background:var(--ui-brand-soft);
border:1px solid var(--ui-brand-border);border-radius:var(--ui-r-md);
color:var(--ui-brand-ink);font-size:.8125rem}
.ui-stat{display:flex;flex-direction:column;gap:.2rem}
.ui-stat-label{color:var(--ui-ink-soft);font-size:.75rem;font-weight:500;
letter-spacing:.02em;text-transform:uppercase}
.ui-stat-value{color:var(--ui-ink);font-size:1.5rem;font-weight:600;
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
.shadow-sm{box-shadow:var(--ui-sh-sm)}.shadow-md{box-shadow:var(--ui-sh-md)}
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
.hover\:shadow-lg:hover{box-shadow:var(--ui-sh-lg)}
.hover\:shadow-md:hover{box-shadow:var(--ui-sh-md)}
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

/* ---- 12. Khung ứng dụng full-width -----------------------------------
Không còn cột sidebar. Sidebar cũ chiếm 292px trên màn 1680px — 17,4% chiều
ngang dành cho 17 liên kết mà phần lớn thời gian không ai bấm. Điều hướng
chuyển sang dock nổi ở mục 15, và toàn bộ phần đó trả về cho nội dung. */
.ui-app{min-height:100vh}

/* .ui-sr-only vẫn cần: dock dùng biểu tượng, và một vài nút chỉ có icon sẽ
được trình đọc màn hình đọc thành nút trống nếu thiếu nhãn ẩn này. */
.ui-raw{margin-top:var(--s2)}
.ui-raw summary{cursor:pointer;font-size:.8125rem;color:var(--ui-ink-soft);
padding:.375rem 0;user-select:none}
.ui-raw summary:hover{color:var(--ui-brand-ink)}
.ui-raw[open] summary{margin-bottom:var(--s1)}
.ui-sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}

/* Điều hướng dự phòng trong footer: dock là một <nav> đầy đủ nên trình thu
thập vẫn thấy mọi liên kết, nhưng để nguyên một bản phẳng ở cuối trang là rẻ
và loại bỏ hoàn toàn rủi ro nếu CSS không tải được. */
.ui-nav-fallback{margin-top:var(--s6);padding-top:var(--s3);
border-top:1px solid var(--ui-border);font-size:13px;
display:grid;gap:var(--s3) var(--s4);
grid-template-columns:repeat(auto-fit,minmax(min(180px,100%),1fr))}
.ui-nav-fallback>section{min-width:0}
.ui-nav-fallback h2{font-size:var(--fs-label);letter-spacing:.06em;
text-transform:uppercase;color:var(--ui-ink-soft);margin:0 0 var(--s1)}
/* Mỗi nhóm là một cột xếp dọc. Bản cũ dùng flex-wrap + space-between trên
từng <ul>: với 2-4 mục thì space-between kéo giãn chúng ngang cả container,
chữ dính hai mép còn giữa trống hoác. Lưới cột phân bố đều theo nghĩa footer
thật sự — mỗi nhóm chiếm một phần bằng nhau của chiều ngang. */
.ui-nav-fallback ul{list-style:none;padding:0;margin:0;
display:flex;flex-direction:column;gap:var(--s1)}

/* ---- 13. Lưới nội dung tự co giãn -----------------------------------
Ba lớp cho ba nhu cầu bố cục cụ thể, tất cả đều align-items:stretch nên các ô
cùng hàng luôn bằng chiều cao và không sinh khoảng trống thò thụt. */
.ui-row{display:grid;gap:1.25rem;align-items:stretch;
grid-template-columns:repeat(auto-fit,minmax(min(22rem,100%),1fr))}
.ui-row>*{min-width:0}
.ui-duo{display:grid;gap:1.25rem;align-items:stretch;grid-template-columns:minmax(0,1fr)}
@media (min-width:768px){.ui-duo{grid-template-columns:repeat(2,minmax(0,1fr))}}
.ui-trio{display:grid;gap:1.25rem;align-items:stretch;grid-template-columns:minmax(0,1fr)}
@media (min-width:768px){.ui-trio{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:1200px){.ui-trio{grid-template-columns:repeat(3,minmax(0,1fr))}}
.ui-duo>*,.ui-trio>*{min-width:0;display:flex;flex-direction:column}
.ui-duo>*>.ui-card-body,.ui-trio>*>.ui-card-body{flex:1 1 auto}

/* ---- 14. Trạng thái rỗng và đang tải ---------------------------------
Một trang trống không kèm lời giải thích không phân biệt được với một trang
hỏng. Khối này luôn nói RÕ vì sao trống và chỉ ra lối đi tiếp. */
.ui-empty{display:flex;flex-direction:column;align-items:center;text-align:center;
gap:.625rem;padding:2.5rem 1.5rem;color:var(--ui-ink-soft)}
.ui-empty-icon{font-size:1.75rem;line-height:1;opacity:.55}
.ui-empty h3{margin:0;font-size:1rem;color:var(--ui-ink)}
.ui-empty p{margin:0;max-width:46ch;font-size:.875rem}
.ui-empty-why{background:var(--ui-surface-2);border:1px solid var(--ui-border);
border-radius:var(--ui-r-md);padding:.75rem 1rem;font-size:.8125rem;
text-align:left;max-width:52ch;margin-top:.25rem}
.ui-skeleton{background:linear-gradient(90deg,var(--ui-surface-2) 25%,
var(--ui-border-strong) 37%,var(--ui-surface-2) 63%);
background-size:400% 100%;animation:ui-shimmer 1.4s ease infinite;
border-radius:var(--ui-r-md);height:1rem;margin:.5rem 0}
@keyframes ui-shimmer{0%{background-position:100% 50%}100%{background-position:0 50%}}
@media (prefers-reduced-motion:reduce){
.ui-skeleton{animation:none}
.ui-app{transition:none}
}

/* ---- 11. In ấn ------------------------------------------------------- */
@media print{
body{background:#fff}
.ui-card{box-shadow:none;break-inside:avoid}
.ui-table-wrap{max-height:none;overflow:visible}
.ui-nav{display:none}
}

/* ---- 15. Dock điều hướng nổi ------------------------------------------
Thay sidebar dọc. Sidebar chiếm 292px trên màn 1680px — 17,4% chiều ngang chỉ
để hiển thị 17 liên kết mà phần lớn thời gian không ai bấm. Dock trả lại toàn
bộ phần đó cho nội dung.

17 đích là quá nhiều cho một dock kiểu macOS: icon sẽ nhỏ hơn 32px và tooltip
chồng lên nhau. SITE_NAV vốn đã chia 5 nhóm, nên dock hiện 5 icon nhóm và mở
popover khi hover hoặc focus. */
.ui-dock{position:fixed;left:50%;bottom:var(--s3);transform:translateX(-50%);
z-index:60;max-width:calc(100vw - var(--s4))}
/* Nhãn nằm dưới icon đẩy dock lên 108px. Đưa nhãn thành tooltip nổi phía
trên (xem .ui-dock-name) thì thanh chỉ còn icon: 40 + 6*2 viền = 54px, đúng
khoảng 48-56px của bản thiết kế. Nền hạ từ 84% xuống 30% để thấy rõ nội dung
trôi phía sau — đó mới là hiệu ứng kính. */
.ui-dock-inner{position:relative;display:flex;align-items:center;gap:4px;
padding:6px 10px;border-radius:var(--r-pill);
background:color-mix(in srgb,var(--ui-surface) 30%,transparent);
border:1px solid var(--hairline);
box-shadow:0 8px 32px rgba(15,23,42,.22),inset 0 1px 0 rgba(255,255,255,.06);
backdrop-filter:blur(12px) saturate(1.8);-webkit-backdrop-filter:blur(12px) saturate(1.8)}
/* Trình duyệt không có backdrop-filter sẽ thấy nền đặc thay vì trong suốt —
vẫn đọc được, chỉ mất hiệu ứng kính. */
@supports not (backdrop-filter:blur(1px)){
.ui-dock-inner{background:var(--ui-surface)}
}
.ui-dock-group{position:relative}
.ui-dock-btn{position:relative;display:grid;place-items:center;padding:0;
background:none;border:0;color:var(--ui-ink-2);cursor:pointer;border-radius:var(--r-inner)}
.ui-dock-ic{display:grid;place-items:center;width:40px;height:40px;font-size:18px;
border-radius:var(--r-inner);background:var(--ui-surface-2);
border:1px solid var(--hairline);
transition:transform .24s ease-in-out,background .2s ease-in-out}
/* Nhãn thành tooltip: ra khỏi luồng nên không cộng vào chiều cao thanh. */
.ui-dock-name{position:absolute;bottom:calc(100% + 8px);left:50%;
transform:translateX(-50%) translateY(4px);
padding:3px 8px;border-radius:var(--r-inner);
background:var(--ui-ink);color:var(--ui-surface);
font-size:11px;font-weight:600;letter-spacing:.02em;white-space:nowrap;
opacity:0;visibility:hidden;pointer-events:none;
transition:opacity .16s ease-in-out,transform .16s ease-in-out,visibility .16s}
.ui-dock-btn:hover .ui-dock-name,.ui-dock-btn:focus-visible .ui-dock-name{
opacity:1;visibility:visible;transform:translateX(-50%) translateY(0)}
/* Nhóm nào có popover thì popover đã nói rõ tên nhóm — hiện thêm tooltip là
thừa và hai lớp nổi chồng lên nhau. */
.ui-dock-group:hover .ui-dock-name{opacity:0;visibility:hidden}
.ui-dock-btn:hover .ui-dock-ic,.ui-dock-btn:focus-visible .ui-dock-ic{
transform:scale(1.18);background:var(--ui-brand-soft)}
.ui-dock-btn[aria-current="true"] .ui-dock-ic{
background:var(--ui-brand);color:var(--ui-on-brand);border-color:transparent}
.ui-dock-btn:focus-visible{outline:2px solid var(--ui-brand);outline-offset:2px}

/* Popover: mặc định ẩn khỏi CÂY TRỢ NĂNG lẫn thị giác. Dùng visibility chứ
không dùng display:none để còn chuyển động được, và hidden-until-found sẽ làm
trình đọc màn hình bỏ qua khi đóng. */
.ui-dock-pop{position:absolute;bottom:calc(100% + var(--s2));left:50%;
transform:translateX(-50%) translateY(6px);min-width:220px;padding:var(--s1);
background:var(--ui-surface);border:1px solid var(--ui-border);
border-radius:var(--r-card);box-shadow:var(--ui-sh-lg);
opacity:0;visibility:hidden;pointer-events:none;
/* Độ trễ BẤT ĐỐI XỨNG. Mở gần như tức thì, nhưng đóng chậm .40s: con trỏ đi
từ nút lên popover phải băng qua khe hở var(--s2), và nếu đóng ngay khi rời
nút thì menu biến mất giữa đường. Đây là nửa sau của "hover intent"; nửa đầu
là cầu nối ::after ngay bên dưới. */
transition:opacity .18s ease-in-out .22s,transform .18s ease-in-out .22s,
visibility 0s linear .40s}
/* Cầu nối phủ kín khe hở giữa đáy popover và đỉnh nút, nên :hover của nhóm
không bao giờ đứt khi con trỏ băng qua. */
.ui-dock-pop::after{content:"";position:absolute;left:0;right:0;top:100%;
height:18px}
/* Vùng đệm quanh cả nhóm: tha thứ cho đường chuột đi chéo ra ngoài mép nút. */
.ui-dock-group::after{content:"";position:absolute;left:-6px;right:-6px;
top:-18px;bottom:-6px;z-index:-1}
.ui-dock-group:hover .ui-dock-pop,
.ui-dock-group:focus-within .ui-dock-pop,
.ui-dock-group.ui-open .ui-dock-pop{
opacity:1;visibility:visible;pointer-events:auto;transform:translateX(-50%) translateY(0);
transition-delay:0s,0s,0s}
.ui-dock-pop a{display:flex;align-items:center;gap:var(--s1);
padding:var(--s1) var(--s2);border-radius:var(--r-inner);
color:var(--ui-ink-2);font-size:13px;white-space:nowrap}
.ui-dock-pop a:hover{background:var(--ui-surface-2);text-decoration:none}
.ui-dock-pop a[aria-current="page"]{background:var(--ui-brand-soft);
color:var(--ui-brand-ink);font-weight:600}

/* MÀN HẸP: dock không được cuộn ngang, và menu con neo vào CẢ DẢI DOCK.
   ========================================================================
   Hai lỗi chồng lên nhau khiến dock chết hẳn trên điện thoại.

   Lỗi 1 — menu lòi ra ngoài viền. Menu rộng cố định 220px canh giữa theo nút
   của nó. Máy bàn thì dock nằm giữa màn rộng nên không sao; điện thoại thì
   dock chiếm gần trọn bề ngang, nên các nhóm ở HAI ĐẦU đẩy menu ra ngoài:

       390px   3/7 nhóm hỏng   #0 lòi trái 63px · #1 lòi trái 19px · #6 lòi phải 31px
       360px   4/7 nhóm hỏng   thêm #5 lòi phải 17px, #6 thành 61px

   Lỗi 2 — KHÔNG ô nào chạm tới được, kể cả ô nằm gọn trong màn. Đo được 0/9
   liên kết nhận cú chạm trên điện thoại trong khi máy bàn 9/9. Nguyên nhân
   là `.ui-dock-inner` cũ mang `overflow-x:auto`: hộp cuộn CẮT mọi hậu duệ
   nằm ngoài nó, mà inner chỉ cao 54px còn menu bung lên phía trên. Menu bị
   xén sạch — `elementFromPoint` giữa menu trả về nội dung trang chứ không
   phải liên kết, dù computed style vẫn báo `visibility:visible`.

   `position:fixed` KHÔNG thoát ra được: `.ui-dock-inner` có `backdrop-filter`,
   mà backdrop-filter biến phần tử thành khối chứa cho cả hậu duệ `fixed`. Đo
   để chắc: tắt riêng `backdrop-filter` → chạm được; tắt riêng `overflow-x` →
   cũng chạm được; để cả hai → không. Phải gỡ đúng một trong hai, và gỡ hộp
   cuộn mới là gỡ đúng gốc.

   Nên bỏ hẳn cuộn ngang: cho mỗi nhóm `flex:1 1 0` để N nhóm luôn vừa khít
   bề ngang. Không còn ngữ cảnh cắt thì menu chỉ cần `absolute` lấy
   `.ui-dock-inner` làm gốc toạ độ rồi căng `left:0;right:0` — hết cả hai lỗi
   bằng cùng một thay đổi. Cuộn ngang với thanh cuộn ẩn vốn cũng là cách điều
   hướng tồi trên màn cảm ứng: không có gì báo rằng còn nhóm phía sau. */
@media (max-width:640px){
.ui-dock{left:var(--s2);right:var(--s2);transform:none;max-width:none}
.ui-dock-inner{justify-content:space-between;gap:2px;padding:6px;
border-radius:var(--r-card)}
.ui-dock-group{position:static;flex:1 1 0;min-width:0}
.ui-dock-btn{width:100%}
.ui-dock-ic{width:100%;max-width:40px;margin-left:auto;margin-right:auto}
/* Màn cảm ứng không có trạng thái hover để hiện tooltip, mà tên nhóm đã nằm
sẵn trong menu con. */
.ui-dock-name{display:none}
.ui-dock-pop{position:absolute;left:0;right:0;min-width:0;
transform:translateY(6px);max-height:min(60vh,420px);overflow-y:auto}
/* Trên màn cảm ứng, MỘT CÚ CHẠM phải mở và cú chạm thứ hai phải đóng. Nhưng
chạm vào nút cũng làm nút nhận focus, nên `:focus-within` sẽ giữ menu mở mãi
và cú chạm thứ hai không đóng được gì. Ở màn hẹp, chỉ `.ui-open` (do kịch bản
đặt) mới là công tắc. Có `.ui-js` đứng đầu để khi không có JavaScript thì
`:focus-within` của quy tắc gốc vẫn còn tác dụng. */
.ui-js .ui-dock-group:hover .ui-dock-pop,
.ui-js .ui-dock-group:focus-within .ui-dock-pop{
opacity:0;visibility:hidden;pointer-events:none;transform:translateY(6px)}
.ui-js .ui-dock-group.ui-open .ui-dock-pop,
.ui-dock-group.ui-open .ui-dock-pop{
opacity:1;visibility:visible;pointer-events:auto;transform:translateY(0)}
/* Cầu nối và vùng đệm là để chuột đi chéo không làm đứt `:hover`. Màn cảm
ứng không có hover, còn `z-index:-1` của vùng đệm lại đẩy nó xuống dưới dải
dock nên nó nuốt mất cú chạm ở rìa nút. */
.ui-dock-pop::after{content:none}
.ui-dock-group::after{content:none}
}

/* Dock che mất phần cuối trang nếu không chừa chỗ. */
.ui-dock-space{padding-bottom:calc(var(--ui-dock-h) + var(--s4))}

@media (prefers-reduced-motion:reduce){
.ui-dock-ic,.ui-dock-pop,.ui-dock-name{transition:none}
.ui-dock-btn:hover .ui-dock-ic,.ui-dock-btn:focus-visible .ui-dock-ic{transform:none}
}

/* ---- 16. Lưới KPI -----------------------------------------------------
auto-fit + minmax cho 6 thẻ tự xuống 3 rồi 2 rồi 1 mà không cần media query
nào cho từng mốc. */
.ui-kpi-grid{display:grid;gap:var(--s2);
grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.ui-kpi{display:flex;flex-direction:column;gap:var(--s1);
padding:var(--s3);border-radius:var(--r-card);
background:var(--ui-surface);border:1px solid var(--ui-border);
box-shadow:var(--ui-sh-sm)}
.ui-kpi-label{font-size:var(--fs-label);font-weight:600;letter-spacing:.06em;
text-transform:uppercase;color:var(--ui-ink-soft)}
.ui-kpi-value{font-size:var(--fs-metric);font-weight:700;line-height:1;
color:var(--ui-ink);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.ui-kpi-sub{font-size:13px;color:var(--ui-ink-soft)}
.ui-kpi-spark{margin-top:auto;padding-top:var(--s1);display:block;
width:100%;height:32px;overflow:visible}
.ui-kpi-spark polyline{fill:none;stroke:var(--ui-brand);stroke-width:1.75;
stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.ui-kpi-delta{font-size:12px;font-weight:650;font-variant-numeric:tabular-nums}
.ui-kpi-delta[data-dir="up"]{color:var(--ui-ok)}
.ui-kpi-delta[data-dir="down"]{color:var(--ui-bad)}
.ui-kpi-delta[data-dir="flat"]{color:var(--ui-ink-soft)}

/* ---- 17. Lưới ma trận dữ liệu hai tầng --------------------------------
minmax(0,…) là BẮT BUỘC, không phải tuỳ chọn: 1fr mặc định là minmax(auto,1fr)
và một bảng rộng sẽ đẩy cột phình ra, phá vỡ tỉ lệ 58/42 đã chọn. */
.ui-matrix-top{display:grid;gap:var(--s3);align-items:stretch;
grid-template-columns:minmax(0,58fr) minmax(0,42fr)}
.ui-matrix-top>*{min-width:0}
.ui-matrix-full{width:100%}
@media (max-width:1100px){.ui-matrix-top{grid-template-columns:minmax(0,1fr)}}

/* ---- 18. Ba bảng dự đoán ngày mai, một hàng --------------------------- */
.ui-next-day{display:grid;gap:var(--s3);align-items:stretch;
grid-template-columns:repeat(3,minmax(0,1fr))}
.ui-next-day>*{min-width:0;display:flex;flex-direction:column}
.ui-next-day>*>.ui-card-body{flex:1 1 auto}
@media (max-width:1240px){.ui-next-day{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:760px){.ui-next-day{grid-template-columns:minmax(0,1fr)}}

/* ---- 19. Khu căn cứ: trái độc lập, phải hợp nhất ---------------------- */
.ui-basis{display:grid;gap:var(--s3);align-items:start;
grid-template-columns:minmax(0,34fr) minmax(0,66fr)}
.ui-basis>*{min-width:0}
.ui-basis-merged{border:1px solid var(--ui-border);border-radius:var(--r-card);
background:var(--ui-surface);overflow:hidden;box-shadow:var(--ui-sh-sm)}
.ui-basis-merged>section{padding:var(--s3)}
/* Đường phân cách chỉ nằm GIỮA hai phần, không nằm trên phần đầu. */
.ui-basis-merged>section+section{border-top:1px solid var(--ui-border)}
@media (max-width:1100px){.ui-basis{grid-template-columns:minmax(0,1fr)}}

""".strip()


def _column_align_rules(columns: int = 10) -> str:
    """Sinh class căn lề theo vị trí cột.

    Dùng cho bảng được ghép chuỗi ``<tr><td>`` thủ công, nơi không tiện gắn
    class lên từng ô: chỉ cần thêm ``ui-r3`` (cột 3 canh phải) hoặc
    ``ui-m2`` (cột 2 canh giữa) lên chính thẻ ``<table>``.
    """

    parts = []
    for index in range(1, columns + 1):
        for suffix, value in (("r", "right"), ("m", "center")):
            parts.append(
                f".ui-table.ui-{suffix}{index} td:nth-child({index}),"
                f".ui-table.ui-{suffix}{index} th:nth-child({index})"
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
#: Nhãn ở đây là VĂN BẢN THUẦN, không phải HTML đã escape sẵn.
#:
#: Bản trước lưu "Gan &amp; nhịp" đã escape. Nơi dựng nào cũng gọi
#: ``html.escape()`` một lần nữa nên thành "&amp;amp;" và hiện ra màn hình
#: đúng chuỗi "Gan &amp; nhịp". Nơi nào quên escape thì lại hiện đúng — nên lỗi
#: chỉ xuất hiện ở một số trang, càng khó truy. Escape thuộc về ranh giới dựng
#: HTML, không thuộc về dữ liệu.
SITE_NAV: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "Trực tiếp",
        (
            ("live.html", "Kết quả trực tiếp", "◉"),
            ("index.html", "Kết quả hôm nay", "▤"),
            ("so-ket-qua-truyen-thong.html", "Sổ kết quả", "▥"),
        ),
    ),
    (
        "Thống kê",
        (
            ("statistics.html", "Ma trận thống kê", "▦"),
            ("index.html#tan-suat-loto", "Tần suất LOTO", "◧"),
            ("index.html#gan-nhip", "Gan & nhịp", "◷"),
            ("index.html#cap-lon", "Cặp lộn & bóng", "⇅"),
        ),
    ),
    (
        "Cầu kèo",
        (
            ("soi-path-loto-active.html", "Cầu LOTO đang chạy", "⟋"),
            ("soi-path-loto-stable.html", "Cầu LOTO ổn định", "⟊"),
            ("soi-path-de-active.html", "Cầu Đặc Biệt đang chạy", "⟍"),
            ("soi-path-de-stable.html", "Cầu Đặc Biệt ổn định", "⟌"),
            ("index.html#duong-cau", "Căn cứ vị trí cầu", "⌗"),
        ),
    ),
    (
        "Phỏng đoán",
        (
            ("dashboard.html", "Bảng điều khiển AI/ML", "◈"),
            ("ml_top10_loto.html", "10 số LOTO", "①"),
            ("ml_top10_de.html", "10 số Đặc Biệt", "②"),
            ("model-quality.html", "Chất lượng mô hình", "✓"),
        ),
    ),
    (
        "Bảng Đặc Biệt",
        (
            ("bang-dac-biet.html", "Theo ngày", "▦"),
            ("bang-dac-biet-thang.html", "Theo tháng", "▩"),
            ("bang-dac-biet-nam.html", "Theo năm", "▨"),
            ("chu-ky-dac-biet.html", "Chu kỳ Đặc Biệt", "◷"),
            ("cau-dac-biet-theo-bo-so.html", "Cầu Đặc Biệt theo bộ số", "⌗"),
            ("giai-db-ngay-mai.html", "Giải Đặc Biệt ngày mai", "◐"),
        ),
    ),
    (
        "LOTO chi tiết",
        (
            ("tan-suat-loto.html", "Tần suất LOTO", "◧"),
            ("tan-suat-cap-loto.html", "Tần suất cặp LOTO", "⇅"),
            ("cap-lon-loto.html", "Cặp lộn LOTO", "🔁"),
            ("cau-giai-dac-biet.html", "Cầu giải Đặc Biệt", "🎯"),
            ("giai-dac-biet-theo-tong.html", "Đặc Biệt theo tổng", "Σ"),
            ("dau-duoi-loto.html", "Đầu đuôi LOTO", "⊞"),
            ("lo-gan.html", "Lô gan", "⏳"),
            ("thong-ke-tong-hop.html", "Thống kê tổng hợp", "◫"),
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


STYLESHEET_NAME = "assets/ui.css"

def write_stylesheet(docs_dir: Path) -> Path:
    """Ghi biểu định kiểu dùng chung ra ``docs/assets/ui.css``.

    Trước đây toàn bộ CSS nội tuyến trong từng trang: khoảng 250 KB lặp lại
    trên 14 trang, không trang nào dùng lại được cache của trang nào. Một tệp
    cùng nguồn hợp lệ với CSP hiện tại (``style-src 'self'``) nên không phải
    nới chính sách bảo mật.
    """
    target = Path(docs_dir) / STYLESHEET_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    write_stylesheet_text(target, TAILWIND_LITE_CSS)
    # Phông đi cùng biểu định kiểu: @font-face trong CSS trỏ tới tệp cạnh nó,
    # nên ghi CSS mà quên phông sẽ tạo ra một tham chiếu chết.
    write_font_assets(docs_dir)
    return target


#: Thư mục chứa tài nguyên tĩnh đi kèm mã nguồn (phông chữ và giấy phép).
ASSET_SOURCE_DIR: Final[Path] = Path(__file__).resolve().parent / "assets"

#: Các tệp phải sao chép sang ``docs/assets/`` mỗi lần dựng trang.
FONT_ASSETS: Final[tuple[str, ...]] = ("InterVariable.woff2", "Inter-LICENSE.txt")


def write_font_assets(docs_dir: Path) -> list[Path]:
    """Sao chép phông tự host và giấy phép sang ``docs/assets/``.

    Phải sao chép chứ không thể trỏ tới ``src/``: GitHub Pages chỉ phục vụ thư
    mục ``docs/``. Và phải kèm giấy phép — SIL OFL cho phép phân phối lại nhưng
    yêu cầu giữ nguyên văn bản giấy phép đi cùng tệp phông.

    Args:
        docs_dir: Thư mục gốc của trang tĩnh.

    Returns:
        Danh sách tệp đã ghi.

    Raises:
        FileNotFoundError: Khi thiếu tệp nguồn — im lặng bỏ qua sẽ khiến trang
            xuất bản mà không có phông, và lỗi chỉ lộ ra ở trình duyệt người
            dùng dưới dạng chữ rơi về phông hệ thống.
    """
    target_dir = Path(docs_dir) / "assets"
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in FONT_ASSETS:
        source = ASSET_SOURCE_DIR / name
        if not source.exists():
            raise FileNotFoundError(f"thiếu tài nguyên phông: {source}")
        target = target_dir / name
        target.write_bytes(source.read_bytes())
        written.append(target)
    return written


def stylesheet_link() -> str:
    """Thẻ liên kết tới biểu định kiểu dùng chung."""

    return f'<link rel="stylesheet" href="{STYLESHEET_NAME}" />'


def dock_script(prefix: str = "ui-dock") -> str:
    """Kịch bản điều khiển dock, nhúng thẳng vào trang.

    Dock vốn chỉ mở bằng ``:hover``/``:focus-within``. Màn cảm ứng KHÔNG CÓ
    hover, còn ``:focus-within`` thì mở được nhưng không đóng được: chạm lần
    hai vào nút chẳng thay đổi gì vì nút vẫn đang giữ focus. Vậy nên cần một
    công tắc tường minh — lớp ``ui-open`` — dùng chung cho chạm và bàn phím.

    Kịch bản cũng gắn ``ui-js`` lên ``<html>``. Biểu định kiểu dựa vào lớp đó
    để chỉ tắt ``:focus-within`` KHI có JavaScript; không có JavaScript thì
    hành vi cũ vẫn còn, tốt hơn là chẳng còn gì.

    Kèm theo là ``aria-expanded``: nút mang ``aria-haspopup`` mà không báo
    trạng thái đóng/mở thì trình đọc màn hình không biết menu đang ra sao.

    Args:
        prefix: Tiền tố lớp của dock — ``ui-dock`` cho khung dùng chung,
            ``dock`` cho dock riêng của trang chủ.

    Returns:
        Thẻ ``<script>`` đã đóng gói.
    """
    root, group, btn = f".{prefix}", f".{prefix}-group", f".{prefix}-btn"
    return (
        "<script>(function(){"
        f'var d=document.querySelector("{root}");if(!d)return;'
        'document.documentElement.classList.add("ui-js");'
        f'var gs=Array.prototype.slice.call(d.querySelectorAll("{group}"));'
        'function set(g,o){g.classList.toggle("ui-open",o);'
        f'var b=g.querySelector("{btn}");'
        'if(b)b.setAttribute("aria-expanded",o?"true":"false")}'
        "function shut(k){for(var i=0;i<gs.length;i++)if(gs[i]!==k)set(gs[i],false)}"
        'd.addEventListener("click",function(e){'
        f'var b=e.target.closest&&e.target.closest("{btn}");if(!b)return;'
        f'var g=b.closest("{group}");if(!g)return;'
        'var o=!g.classList.contains("ui-open");shut(g);set(g,o)});'
        'document.addEventListener("click",function(e){'
        f'if(!(e.target.closest&&e.target.closest("{root}")))shut(null)}});'
        'document.addEventListener("keydown",function(e){'
        'if(e.key!=="Escape")return;'
        f'var g=d.querySelector("{group}.ui-open");if(!g)return;'
        f'var b=g.querySelector("{btn}");shut(null);if(b)b.focus()}});'
        'd.addEventListener("focusout",function(e){'
        "if(!e.relatedTarget||!d.contains(e.relatedTarget))shut(null)})"
        "})();</script>"
    )


def dock(current: str = "") -> str:
    """Dựng dock điều hướng nổi ở giữa chân trang.

    Thay cho sidebar dọc. Sidebar chiếm 292px trên màn 1680px — 17,4% chiều
    ngang — chỉ để hiện 17 liên kết mà phần lớn thời gian không ai bấm.

    17 đích là quá nhiều cho một dock kiểu macOS: icon sẽ nhỏ hơn 32px và
    tooltip chồng nhau. :data:`SITE_NAV` vốn đã chia 5 nhóm, nên dock hiện 5
    icon nhóm, mỗi icon mở một popover chứa các mục con.

    Popover mở bằng ``:hover`` **và** ``:focus-within`` — chỉ hover thôi thì
    người dùng bàn phím không bao giờ tới được các mục con.

    Args:
        current: Tên tệp trang hiện tại, để đánh dấu mục đang xem.

    Returns:
        Chuỗi HTML của dock.
    """
    parts = ['<nav class="ui-dock" aria-label="Điều hướng chính">', '<div class="ui-dock-inner">']
    for group, items in SITE_NAV:
        hrefs = {href.split("#", 1)[0] for href, _, _ in items}
        active = " aria-current=\"true\"" if current and current in hrefs else ""
        icon = items[0][2] if items else "•"
        group_id = "dock-" + re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-")
        parts.append('<div class="ui-dock-group">')
        parts.append(
            f'<button class="ui-dock-btn" type="button"{active}'
            f' aria-haspopup="true" aria-expanded="false"'
            f' aria-controls="{group_id}">'
            f'<span class="ui-dock-ic" aria-hidden="true">{icon}</span>'
            f'<span class="ui-dock-name">{html.escape(group)}</span>'
            "</button>"
        )
        parts.append(f'<div class="ui-dock-pop" id="{group_id}" role="menu">')
        for href, label, item_icon in items:
            mark = ' aria-current="page"' if href == current else ""
            parts.append(
                f'<a href="{href}" role="menuitem"{mark}>'
                f'<span aria-hidden="true">{item_icon}</span>'
                f"<span>{html.escape(label)}</span></a>"
            )
        parts.append("</div></div>")
    parts.append("</div></nav>")
    parts.append(dock_script())
    return "".join(parts)


def app_shell_open(current: str = "", *, wide: bool = False) -> str:
    """Mở khung ứng dụng: nội dung chiếm trọn chiều ngang, dock ở chân trang.

    Args:
        current: Tên tệp trang hiện tại.
        wide: Bỏ giới hạn chiều rộng tối đa của khung nội dung.

    Returns:
        Phần HTML mở khung; đóng bằng :func:`app_shell_close`.
    """
    extra = " ui-shell-wide" if wide else ""
    return (
        f'<div class="ui-app ui-dock-space" id="ui-app">'
        f'<main class="ui-shell{extra}">'
    )


def nav_fallback(class_name: str = "ui-nav-fallback") -> str:
    """Điều hướng phẳng đặt cuối trang, phòng khi CSS không tải được.

    Dock là một ``<nav>`` đầy đủ nên trình thu thập vẫn thấy mọi liên kết dù
    popover đang ẩn. Nhưng popover ẩn bằng ``visibility:hidden``, nên nếu CSS
    không tải được vì bất kỳ lý do gì thì trạng thái hiển thị sẽ là mặc định
    của trình duyệt — và không nên phụ thuộc vào điều đó cho việc điều hướng.
    Một danh sách phẳng ở cuối trang tốn vài trăm byte và loại bỏ hẳn rủi ro.

    Args:
        class_name: Lớp của thẻ ``<nav>``. Trang trực tiếp có bảng màu riêng
            và định kiểu khối này bằng lớp ``ui-live-nav`` của chính nó.

    Returns:
        Chuỗi HTML của khối điều hướng dự phòng.
    """
    parts = [f'<nav class="{class_name}" aria-label="Điều hướng đầy đủ">']
    for group, items in SITE_NAV:
        parts.append(f"<section><h2>{html.escape(group)}</h2><ul>")
        for href, label, _ in items:
            parts.append(f'<li><a href="{href}">{html.escape(label)}</a></li>')
        parts.append("</ul></section>")
    parts.append("</nav>")
    return "".join(parts)


#: Vá riêng cho trang trực tiếp, chèn vào cuối thẻ ``<style>`` của chính nó.
#:
#: Trang này có bảng màu tối riêng và trước đây không dùng biểu định kiểu dùng
#: chung. Gắn dock thì phải nạp biểu định kiểu ấy, và nó mang theo quy tắc
#: ``body{font-size:14px;line-height:1.6}`` cùng ``a{text-decoration:none}`` —
#: hai thứ trang không tự khai báo nên chúng lọt xuống toàn bộ nội dung: đo
#: được trang cao thêm 235px và liên kết ở đầu trang mất gạch chân.
#:
#: Ghim lại theo ``.wrap`` chứ không theo ``body``: ``.wrap`` bọc đúng phần
#: nội dung của trang, còn dải dock và khối điều hướng cuối trang nằm NGOÀI
#: nó nên vẫn giữ nguyên định kiểu dùng chung.
_LIVE_PATCH = (
    ".wrap{font-size:16px;line-height:normal}"
    ".wrap a{text-decoration:underline}"
    ".ui-live-nav{padding-bottom:calc(var(--ui-dock-h,54px) + 40px)}"
)

#: Khối điều hướng phẳng viết tay của trang trực tiếp.
_LIVE_NAV = re.compile(r'<nav class="ui-live-nav".*?</nav>', re.S)

#: Dock đã gắn ở lượt dựng trước, để lượt sau thay chứ không chồng thêm.
_LIVE_DOCK = re.compile(r'<nav class="ui-dock".*?</nav>\s*(?:<script>.*?</script>)?', re.S)


def refresh_live_page(docs_dir: Path) -> Path | None:
    """Gắn dock và làm mới điều hướng cho ``live.html``.

    ``live.html`` là trang DUY NHẤT không do builder nào sinh ra: nó được viết
    tay và commit thẳng. Cái giá của việc đó đã hiện rõ — khối điều hướng
    trong tệp là bản chép tay của một :data:`SITE_NAV` cũ, nên nó vừa thiếu
    hai nhóm mới, vừa còn nguyên cách gọi "lô tô" và "ĐB" mà cả dự án đã
    chuẩn hoá thành "LOTO" và "Đặc Biệt". Chép tay lần nữa là lặp lại đúng
    lỗi ấy, nên ở đây sinh lại từ nguồn.

    Hàm chạy được nhiều lần cho cùng một kết quả: dock cũ bị thay chứ không
    bị chồng thêm.

    Args:
        docs_dir: Thư mục gốc của trang tĩnh.

    Returns:
        Đường dẫn tệp đã ghi, hoặc ``None`` nếu tệp không tồn tại.
    """
    path = Path(docs_dir) / "live.html"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if STYLESHEET_NAME not in text:
        text = text.replace("<style>", f"{stylesheet_link()}\n  <style>", 1)
    text = _LIVE_DOCK.sub("", text)
    text = _LIVE_NAV.sub(lambda _: nav_fallback("ui-live-nav"), text)
    if _LIVE_PATCH not in text:
        # Phải chèn vào đúng thẻ `<style>` của trang, và chèn CUỐI: quy tắc
        # `.ui-live-nav` của trang dùng lối viết gộp `padding` nên nó đè mất
        # mọi `padding-bottom` đến từ nơi khác.
        text = text.replace("</style>", f"{_LIVE_PATCH}\n  </style>", 1)
    text = text.replace("</body>", f'{dock("live.html")}\n</body>', 1)
    write_page(path, text)
    return path


def app_shell_close(current: str = "") -> str:
    """Đóng khung mở bởi :func:`app_shell_open` và gắn dock.

    Dock đặt ở CUỐI phần thân chứ không phải đầu: thứ tự trong DOM là thứ tự
    trình đọc màn hình đi qua, và nội dung nên đến trước điều hướng phụ.

    Args:
        current: Tên tệp trang hiện tại, chuyển tiếp cho :func:`dock`.

    Returns:
        Phần HTML đóng khung kèm dock.
    """
    return f"{nav_fallback()}</main>{dock(current)}</div>"


def tailwind_style_tag() -> str:
    """Trả về thẻ style CSP-safe; không gọi CDN bên ngoài."""

    return f'<style id="ui-tailwind-lite">{TAILWIND_LITE_CSS}</style>'


def shell_open(*, wide: bool = False) -> str:
    """Mở container căn giữa dùng chung cho mọi trang."""

    extra = " ui-shell-wide" if wide else ""
    return f'<div class="ui-shell{extra}">'


def shell_close() -> str:
    """Đóng container mở bởi :func:`shell_open`."""

    return "</div>"


def page_header(title: str, subtitle: str = "", meta: Iterable[str] = ()) -> str:
    """Dựng khối tiêu đề trang thống nhất (đã escape)."""

    parts = [
        '<header class="ui-header">',
        f"<h1>{html.escape(title)}</h1>",
    ]
    if subtitle:
        parts.append(f'<p class="ui-sub">{html.escape(subtitle)}</p>')
    items = [html.escape(str(m)) for m in meta if str(m).strip()]
    if items:
        cells = "".join(f"<span>{item}</span>" for item in items)
        parts.append(f'<div class="ui-meta">{cells}</div>')
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
    return f'<nav class="ui-nav">{"".join(items)}</nav>'


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

    classes = ["ui-card"]
    if lift:
        classes.append("ui-card-lift")
    if span:
        classes.append(f"ui-c{max(1, min(12, int(span)))}")
    head = ""
    if title or aside:
        head = f'<div class="ui-card-head"><h2>{html.escape(title)}</h2>{aside}</div>'
    body_class = "ui-card-body ui-card-flush" if flush else "ui-card-body"
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
        return '<p class="ui-table-empty">Chưa có dữ liệu.</p>'

    body = "".join(
        f'<tr><td class="ui-al ui-key">{html.escape(label)}</td>'
        f'<td class="ui-ar">{html.escape(value)}</td></tr>'
        for label, value in rows
    )
    return (
        '<div class="ui-table-wrap"><table class="ui-table">'
        '<thead><tr><th class="ui-al" scope="col">Mục</th>'
        '<th class="ui-ar" scope="col">Giá trị</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def raw_details(payload: Any, *, summary: str = "Xem dữ liệu gốc (JSON)") -> str:
    """Khối gập lại chứa JSON gốc, dành cho người muốn kiểm chứng số liệu."""

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f'<details class="ui-raw"><summary>{html.escape(summary)}</summary>'
        f'<pre class="ui-pre">{html.escape(text)}</pre></details>'
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
        return f'<p class="ui-table-empty">{html.escape(empty)}</p>'

    width = len(headers)
    if align is None:
        first = body_rows[0]
        align = [
            ALIGN_RIGHT if index < len(first) and _is_numeric(first[index]) else ALIGN_LEFT
            for index in range(width)
        ]
    classes = [
        _ALIGN_CLASS.get(align[i] if i < len(align) else ALIGN_LEFT, "ui-al") for i in range(width)
    ]

    head = "".join(
        f'<th scope="col" class="{classes[i]}">{html.escape(str(h))}</th>'
        for i, h in enumerate(headers)
    )
    out = [
        '<div class="ui-table-wrap"><table class="ui-table">',
        f"<thead><tr>{head}</tr></thead><tbody>",
    ]
    for row in body_rows:
        cells = []
        for index in range(width):
            value = row[index] if index < len(row) else ""
            cell_class = classes[index]
            if index == key_column:
                cell_class += " ui-key"
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
        return f'<p class="ui-table-empty">{html.escape(empty)}</p>'
    headers = [str(c) for c in frame.columns]
    rows = frame.astype(object).where(frame.notna(), "").values.tolist()
    return render_table(headers, rows, align=align, empty=empty, key_column=key_column)


def table_wrap(inner_html: str) -> str:
    """Bọc bảng HTML có sẵn (ví dụ ``DataFrame.to_html``) vào vùng cuộn chuẩn."""

    return f'<div class="ui-table-wrap">{inner_html}</div>'
