# VLA MASTER UI/UX SPEC

Tài liệu chuẩn (normative) cho mọi công việc giao diện trong kho VLA.
Mọi thay đổi frontend phải đọc tệp này trước.

Phần **I–XXII** là yêu cầu do chủ dự án đặt ra, giữ nguyên văn tiếng Anh vì
sửa lời văn là rủi ro đổi nghĩa. Phần **XXIII** là các SỰ THẬT ĐÃ KIỂM CHỨNG
của kho và các quyết định kiến trúc kèm lý do — phần này mới là thứ thi hành
được, và nó ghi rõ chỗ nào trong I–XXII hiện KHÔNG áp dụng được.

---

## ROLE

Principal Product Designer, UI/UX Architect & Frontend Engineering Lead.
Transform VLA into a premium, production-grade data analytics platform —
preserving the integrity of its data, statistical calculations, machine
learning models, prediction services and business logic.

## I. PROJECT CONTEXT

- Repository: `https://github.com/beuvivu/VLA`
- Production website: `https://beuvivu.github.io/VLA/`
- Application: Vietnamese Lottery Analytics — VLA. Primary language: Vietnamese.

Core objective: transform VLA from independently styled analytical pages into
a cohesive, sophisticated, enterprise-grade analytics product that communicates
**Precision · Intelligence · Trust · Clarity · Modernity · Professionalism**.

## II. UI/UX REFERENCE RESEARCH

| # | Reference | URL | Characteristics to study |
|---|---|---|---|
| 01 | Tapotik AI | `https://tapotik-ai.vercel.app/` | Premium SaaS appearance; sophisticated gradients; Bento Grid; contemporary typography; soft glassmorphism; premium dark interface; refined hierarchy; micro-interactions; subtle animation; consistent component geometry |
| 02 | Paces | `https://themes.coderthemes.com/paces/index.html` | Enterprise dashboard architecture; modular components; consistent navigation; scalable tokens; advanced tables; filters; chart presentation; complex layouts; light + dark |
| 03 | NexLink | `https://nexlink.layoutdrop.com/demo/index.html` | Premium light dashboard; balanced cards; KPI presentation; indigo/purple accents; soft backgrounds; professional data viz; high density with appropriate spacing |
| 04 | GXON | `https://gxon.layoutdrop.com/laravel/demo/` | Clean enterprise interface; BI presentation; statistical cards; consistent tables; operational dashboards; status indicators |
| 05 | PreSkool | `https://preskool.dreamstechnologies.com/html/teacher-dashboard.html` | Role-based dashboards; quick actions; information grouping; task-oriented navigation; operational widgets; contextual panels |

**Rule:** if a reference is inaccessible, explicitly document the limitation and
use verifiable sources rather than inventing observations.

## III. DESIGN DIRECTION

Premium Data Analytics UI + Soft Modern Design + Intelligent Bento Grid +
Subtle Glassmorphism. Combine the references' strengths without copying their
layouts or branding. The result must have a distinct VLA identity.

| Component | Reference |
|---|---|
| Overall design architecture | Paces |
| Main analytics dashboard | NexLink |
| Premium visual identity | Tapotik AI |
| Typography and spacing | Tapotik AI + NexLink |
| Advanced tables | Paces + GXON |
| KPI and analytics cards | NexLink |
| Quick actions | PreSkool |
| Light Mode | NexLink |
| Dark Mode | Tapotik AI |
| Component consistency | Paces |
| Animation and micro-interactions | Tapotik AI |

## IV. MASTER DESIGN SYSTEM

Centralized and maintainable. No scattered CSS overrides, no duplicate
declarations, no page-specific inconsistencies.

### 4.1 Color architecture — Light Mode foundation (starting point, not immutable)

```css
:root {
  --vla-primary: #5941C8;
  --vla-primary-hover: #4933AF;
  --vla-primary-soft: #EEEAFE;
  --vla-secondary: #7C3AED;
  --vla-accent: #6366F1;
  --vla-background: #F4F5FF;
  --vla-background-secondary: #EAECFA;
  --vla-surface: #FFFFFF;
  --vla-surface-secondary: #F8F9FE;
  --vla-text-primary: #172033;
  --vla-text-secondary: #64748B;
  --vla-text-muted: #94A3B8;
  --vla-border: #E2E8F0;
  --vla-success: #16A34A;
  --vla-warning: #D97706;
  --vla-danger: #DC2626;
  --vla-info: #0284C7;
  --vla-radius-sm: 8px;
  --vla-radius-md: 12px;
  --vla-radius-lg: 16px;
  --vla-radius-xl: 20px;
}
```

Refine based on actual contrast testing. Create equivalent semantic tokens for
Dark Mode — **do not** implement Dark Mode by inverting all colors.

### 4.2 Typography

`Inter`, falling back to `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.

| Element | Font size |
|---|---|
| Main page heading | 24–30px |
| Section heading | 18–22px |
| Card heading | 15–18px |
| Primary KPI | 24–36px |
| Body text | 14–16px |
| Table text | 12–14px |
| Supporting information | 12–13px |

VLA is data-intensive: avoid oversized typography that reduces usable
analytical information. Statistical data uses `font-variant-numeric: tabular-nums`.

### 4.3 Spacing

Multiples of four: 4, 8, 12, 16, 20, 24, 32, 40, 48px. No arbitrary values
without a documented layout requirement.

### 4.4 Cards and surfaces

Consistent radius, subtle shadows, lightweight borders, balanced padding, clear
title/content hierarchy, consistent header/footer alignment, controlled hover.
Avoid excessive nesting and decorative boxes. Apply glassmorphism selectively to
decorative or secondary surfaces — **never** to dense statistical tables.

### 4.5 Icons

One consistent family. Consistent stroke width, sizing, vertical alignment,
icon-to-text spacing, meaningful semantics. Do not mix incompatible libraries.

## V. GLOBAL LAYOUT ARCHITECTURE

- Standard container: max width 1440px, horizontal padding 16 / 24 / 32px.
- Do **not** force large statistical tables or matrices into a narrow viewport;
  specialized analytical pages may use wider containers.
- Consistent 12-column responsive grid where appropriate; cards occupy
  intentional column spans.
- Avoid large empty space beside a single narrow card; avoid inconsistent card
  heights within one visual group.
- Standardize sidebar width, nav group spacing, active/hover/collapsed states,
  mobile sidebar behavior, topbar height, breadcrumbs, theme toggle, search,
  page actions. The selected nav item must be visually identifiable. Nested
  menus must work with mouse **and** keyboard. On mobile, navigation must never
  permanently obscure essential content.

Desktop reference composition:

```
┌──────────────────────────────────────────────────────────┐
│ Page Heading / Breadcrumb / Actions                      │
├────────────┬────────────┬────────────┬───────────────────┤
│ KPI 01     │ KPI 02     │ KPI 03     │ KPI 04            │
├──────────────────────────────┬───────────────────────────┤
│ Primary Analytics            │ Secondary Analytics       │
├──────────────────────────────┴───────────────────────────┤
│ Advanced Data Table                                      │
└──────────────────────────────────────────────────────────┘
```

## VI. SPECIALIZED VLA DATA DESIGN

VLA is not a generic CRM dashboard.

### 6.1 Lottery results layout (desktop)

```
┌───────────────────────────────────────────────────────────┐
│                  RESULTS OVERVIEW                         │
├──────────────────────────┬───────────────┬────────────────┤
│       Main Results       │    Chục       │    Đơn vị      │
└──────────────────────────┴───────────────┴────────────────┘
```

Main results table on the left; Chục and Đơn vị side by side to its right. Do
not stack all three vertically on desktop unless the viewport requires it. On
mobile, reorganize by content priority without losing information.

### 6.2 Prediction simulation layout (desktop)

```
┌────────────────────────────────────────────────────────────┐
│                    SIMULATION RESULTS                      │
├──────────────────────┬──────────────────┬──────────────────┤
│ Simulation Results   │ Đặc Biệt         │ Lô tô            │
│                      │ Prediction       │ Prediction       │
└──────────────────────┴──────────────────┴──────────────────┘
```

Prediction interfaces must **never** imply guaranteed outcomes.

### 6.3 Statistical matrix

Dedicated cell visualization system.

Empty / miss cell, Light Mode: `background: #E2E8F0;` with optional diagonal hatch:

```css
background-image:
  repeating-linear-gradient(
    135deg, transparent, transparent 5px,
    rgba(100, 116, 139, 0.16) 5px, rgba(100, 116, 139, 0.16) 6px
  );
```

Active / hit cells use semantic colors based on actual data, differentiating
where applicable: normal hit, multiple occurrences, two-nháy, special-number
occurrence, selected, hovered, highlighted pattern.

**Preserve the original statistical definitions and data mappings.** Do not
assign new colors or meanings that contradict existing business logic. Provide
an accessible legend. **Color must not be the only way to communicate state.**

### 6.4 Advanced data tables

Sticky headers, column alignment, horizontal scrolling, zebra rows, hover,
selected rows, sorting, filtering, pagination, loading/empty/error states,
tooltips, numeric formatting. Do not sacrifice information density for
spaciousness — statistical tables prioritize accurate comparison and fast scanning.

## VII. COMPLETE UI COMPONENT AUDIT

Inventory every user-facing page and component, discovered from the repository.
Audit fields: Page · Current layout · Visual defects · Functional defects ·
Responsive defects · Design System compliance · Required changes ·
Implementation status · QA status.

## VIII. FUNCTIONAL QA

Every control must work: buttons (handlers, disabled, loading, navigation,
modals, refresh); filters (date, ranges, number, region, period, reset,
combinations); checkboxes/toggles (state, data interaction, styling,
persistence, keyboard); dropdowns (open/close, selection, placement, no
clipping, no z-index faults); tables (data, sorting, filtering, pagination,
scrolling, alignment); Quick Selection (data source, initialization, rendering,
handlers).

**Do not mask a data-loading bug with a fabricated placeholder.** Where no data
genuinely exists, render a meaningful Vietnamese empty state. Where loading
fails, expose a recoverable error state.

## IX. VIETNAMESE LOCALIZATION

Professional Vietnamese with correct diacritics, consistent terminology.

**Terminology rule:** replace user-facing “Đề” with “Đặc Biệt” where it refers
to the lottery category (`Thống kê đề` → `Thống kê Đặc Biệt`, `Dự đoán đề` →
`Dự đoán Đặc Biệt`, `Bảng đề` → `Bảng Đặc Biệt`).

**Do not** blindly replace substrings in JavaScript identifiers, API routes,
database columns or variable names. Preserve technical identifiers.

## X. RESPONSIVE REQUIREMENTS

| Device | Viewport |
|---|---|
| Small Mobile | 320px |
| Mobile | 375px |
| Large Mobile | 430px |
| Tablet | 768px |
| Small Laptop | 1024px |
| Desktop | 1440px |
| Large Desktop | 1920px |

Intentional horizontal scrolling **within a table container** is acceptable.
Unintended page-level horizontal overflow is not. Mobile: no overlapping
elements, clipped buttons, invisible dropdowns, broken cards, oversized blank
space, inaccessible navigation, unreadable text, or layout shift during loading.
Design mobile intentionally; do not apply the desktop layout mechanically.

## XI. ANIMATION & MICRO-INTERACTIONS

Motion communicates feedback and hierarchy, never decoration. Respect
`@media (prefers-reduced-motion: reduce)`. Avoid animation-induced layout
shifts. Do not animate large statistical matrices unnecessarily.

## XII. ACCESSIBILITY

Target WCAG 2.2 AA where applicable: text and control contrast, keyboard
navigation, focus indicators, accessible labels, table semantics, dialog
semantics, form errors, screen-reader announcements, color-dependent indicators.
Semantic HTML — no clickable generic `<div>` where a button or link belongs.
Essential information must not be hover-only.

## XIII. PERFORMANCE & FRONTEND ARCHITECTURE

Investigate the existing implementation before adding dependencies. Prefer
incremental modernization compatible with the existing build and deployment
architecture. Optimize CSS duplication, unused styles, JS size, layout shifts,
DOM updates, chart rendering, large tables, matrix rendering, listeners, memory,
assets. Virtualize only where measured rendering performance warrants it.
Preserve GitHub Pages compatibility.

## XIV. PRESERVE EXISTING APPLICATION LOGIC

Strict. Preserve lottery result data, historical records, frequency
calculations, number domains, statistical definitions, prediction outputs, ML
features, simulation logic, API contracts, database structures.

Correct discovered integration bugs, but do not change business rules without
validating their definitions. Distinguish a visual pair-labeling issue from a
genuine number-mapping defect: if the interface shows `77-77` where verified
domain logic requires `22-77`, investigate the underlying transformation rather
than hard-coding a display patch. Corrections must be generalizable and
regression-tested.

## XV. DESIGN SYSTEM IMPLEMENTATION

Conceptual architecture (not a mandatory file structure):

- **Foundations** — Colors, Typography, Spacing, Shadows, Borders, Motion
- **Layout** — App Shell, Sidebar, Topbar, Page Header, Content Container, Responsive Grid
- **Components** — Card, KPI Card, Button, Badge, Dropdown, Checkbox, Select, Date Picker, Filter Panel, Modal, Tooltip, Tabs, Pagination, Data Table
- **Analytics** — Statistical Matrix, Number Cell, Frequency Chart, Lottery Result Table, Prediction Panel, Simulation Panel
- **Feedback** — Loading, Skeleton, Empty State, Error State, Toast

## XVI. AUTOMATED VISUAL QA

Use the repository's existing tooling; Playwright where compatible. Screenshot
comparison (desktop light/dark, mobile light/dark); layout validation
(horizontal overflow, unexpected gaps, overlap, inconsistent card dimensions,
broken grid spans, misaligned columns, clipped content, z-index, layout shift,
invisible controls); interaction validation; console validation; network
validation; data validation against the verified source; regression testing.

**A screenshot alone is not proof that a page works.**

## XVII. IMPLEMENTATION WORKFLOW

1. **Discovery** — architecture, pages/routes, CSS frameworks, component patterns, templates, JS deps, data bindings, build config, deployment config, tests. Produce a complete interface inventory.
2. **Design research** — analyze the references; document what to adopt and what not to.
3. **Master Design System** — centralized foundations.
4. **Global application shell** — sidebar, topbar, header, breadcrumbs, containers, responsive layout, theme switching.
5. **Page-by-page transformation** — every discovered page. CSS changes alone do not make a page complete.
6. **Specialized analytics** — matrices, frequency, historical results, prediction simulation, tables, quick selection, charts, legends.
7. **Regression & QA** — lint, type, unit, integration, browser, visual regression, build. Document pre-existing failures separately.
8. **Final verification** — against the full page inventory.

## XVIII. STRICT ENGINEERING RULES

1. No superficial redesign.
2. No fabricated functionality — never fake data to conceal broken components.
3. No destructive changes — do not remove features, data, models or working modules to simplify the UI.
4. No uncontrolled rewrites.
5. No inconsistent components.
6. No generic mobile fallback.
7. No unverified completion claims.
8. No uncontrolled dependency growth.
9. No exposed credentials.
10. No blind merge — no force-push, no overwriting unrelated changes, no merging unverified code.

## XIX. DEFINITION OF DONE

Design System · Visual Identity · Layout · Responsive · Functionality · Tables ·
Statistical Matrix · Vietnamese · Light Mode · Dark Mode · Accessibility ·
Performance · Build · Tests · Deployment · Documentation — each verified.

Do not claim 100% bug-free operation without adequate evidence. Document
remaining limitations explicitly.

## XX. DELIVERABLES

```
docs/ui-ux/
├── ui-audit.md
├── design-reference-analysis.md
├── master-design-system.md
├── component-inventory.md
├── responsive-qa.md
├── functional-qa.md
└── final-implementation-report.md
```

The final report must list: pages discovered, pages modified, shared components,
UI/functional/responsive defects corrected, test commands executed, test results,
visual evidence, remaining known issues, files changed, branch and commit info,
PR link if created, deployment verification status. **Only report actions that
actually occurred.**

## XXI. EXECUTION MODE

Autonomous senior engineering team. Implement directly in the repository. Cycle:
DISCOVER → AUDIT → DESIGN → IMPLEMENT → BUILD → TEST → VISUALLY INSPECT → FIX →
REGRESSION TEST → DOCUMENT. If the session ends before completion, leave the
repository recoverable and record the precise remaining work. Do not claim
unfinished work is complete.

## XXII. FINAL PRODUCT VISION

A sophisticated analytical SaaS application for demanding professional users,
combining Tapotik AI's visual identity, Paces' systematic architecture,
NexLink's analytics presentation, GXON's operational clarity and PreSkool's
task-oriented usability — unmistakably VLA.

---

# XXIII. SỰ THẬT ĐÃ KIỂM CHỨNG & QUYẾT ĐỊNH KIẾN TRÚC

Phần này do Claude ghi, mỗi khẳng định đều đo được. Nó ghi rõ chỗ nào trong
I–XXII hiện KHÔNG áp dụng được, vì thi hành một yêu cầu không còn đối tượng là
cách nhanh nhất để báo cáo sai.

## 23.1 Kho HIỆN KHÔNG CÓ giao diện nào

Đo lúc 2026-09-21, commit `18b709c4`:

| | |
|---|---|
| Tệp trong `docs/` | **1** (`.nojekyll`, 0 byte) |
| Module trình bày trong `src/` | **0** |
| Tệp trong `src/templates/` | 2 (`README.j2`, `__init__.py`) — cả hai cho `analyze.py`, không phải trang |

Ngày 2026-09-21, theo yêu cầu tường minh của chủ dự án ("Reset và xóa triệt để
hết giao diện hiện có"), toàn bộ tầng trình bày đã bị xóa: 107 tệp, 82 800
dòng — `docs/` (44 tệp, 29 trang, 17 MB), 17 module trình bày, 10 tệp template,
8 script, 6 workflow, 25 tệp kiểm, `DASHBOARD.md`. Xem `00cf02ea` và `e40968b5`.

**Hệ quả:** các mục sau của spec hiện KHÔNG có đối tượng và không được báo cáo
là "đã làm":

- **VII** — cột "Current layout", "Visual defects", "Functional defects",
  "Responsive defects", "Design System compliance" của bảng audit. Không có
  trang nào để audit. Thay thế: `docs/ui-ux/ui-audit.md` liệt kê 29 trang CẦN
  DỰNG, khôi phục từ git history, kèm hợp đồng dữ liệu của từng trang.
- **XVI.1** — "screenshots before and after". Không có "before". Chỉ chụp
  "after", và nói rõ là ảnh của trang mới chứ không phải ảnh so sánh.
- **XVII.5** — "Page-by-page transformation" là DỰNG MỚI, không phải refactor.
- **XVIII.3** — "No destructive changes" không áp dụng hồi tố cho lần xóa đã
  được yêu cầu tường minh; nó áp dụng từ đây trở đi.

## 23.2 Cả 5 reference và trang production đều BỊ CHẶN

Đo bằng `curl` qua agent proxy, 2026-09-21T13:23Z. Sáu địa chỉ, sáu lần
`connect_rejected`, gateway trả **403 cho CONNECT** (policy denial):

| URL | Kết quả |
|---|---|
| `https://tapotik-ai.vercel.app/` | 403 CONNECT — chặn |
| `https://themes.coderthemes.com/paces/index.html` | 403 CONNECT — chặn |
| `https://nexlink.layoutdrop.com/demo/index.html` | 403 CONNECT — chặn |
| `https://gxon.layoutdrop.com/laravel/demo/` | 403 CONNECT — chặn |
| `https://preskool.dreamstechnologies.com/html/teacher-dashboard.html` | 403 CONNECT — chặn |
| `https://beuvivu.github.io/VLA/` | 403 CONNECT — chặn |

Không phải lỗi tạm thời: `curl -sS "$HTTPS_PROXY/__agentproxy/status"` liệt kê
đủ sáu lần từ chối trong `recentRelayFailures`.

**Theo đúng quy tắc của mục II** ("If a reference is inaccessible, explicitly
document the limitation and use verifiable screenshots or existing project
references rather than inventing observations"), nguồn cho PHASE 2 là:

1. Danh sách đặc điểm mà chính chủ dự án đã liệt kê cho từng reference (mục II
   của tệp này) — đây là quan sát của người có truy cập, không phải của Claude.
2. Các token màu, thang chữ, thang khoảng cách, sơ đồ layout mà chủ dự án cung
   cấp ở mục 4.1–4.3, V, VI.
3. Lịch sử git của giao diện cũ, cho các hợp đồng dữ liệu và cấu trúc trang.

Claude **không** phát biểu bất kỳ nhận xét nào về hình thức thật của năm trang
đó. Nếu về sau có truy cập, mục này phải được cập nhật và thiết kế được đối
chiếu lại.

## 23.3 Kiến trúc: builder Python sinh HTML tĩnh, KHÔNG thêm framework

Đo được: kho không có `package.json`, không có bước build JS, không có
Tailwind; `pyproject.toml` + `requirements.txt` là toàn bộ quản lý phụ thuộc;
`node v22.22.2` có sẵn trong môi trường nhưng KHÔNG phải phụ thuộc của kho.
GitHub Pages phục vụ tệp tĩnh từ `docs/` trên nhánh `main`.

Spec có vài đoạn viết bằng class Tailwind (`mx-auto w-full max-w-[1440px]
px-4 sm:px-6 lg:px-8`). Mục XV nói rõ đó là "conceptual architecture, not a
mandatory file structure". Quyết định: **viết CSS tay với một tầng utility nhỏ
do VLA định nghĩa**, không đưa Tailwind vào. Lý do, theo thứ tự quan trọng:

1. **Mục XVIII.8** cấm tăng phụ thuộc không kiểm soát. Tailwind kéo theo
   `package.json`, `node_modules`, một bước build, và một chuỗi cung ứng mới
   cho một kho hiện chỉ có Python.
2. **Mục XIII** đòi giữ tương thích GitHub Pages. Tailwind qua CDN cần
   `unsafe-inline`/`unsafe-eval` trong CSP.
3. **Bộ kiểm hiện tại ĐÒI CSP**: `test_every_published_page_declares_a_content_security_policy`
   làm đỏ mọi trang HTML thiếu `Content-Security-Policy`. Dùng CDN là tự làm
   đỏ chính bất biến bảo mật của kho.
4. **Mục XVIII.4** cấm rewrite kiến trúc không có lý do kỹ thuật.

## 23.4 Hai bất biến bảo mật TỰ ĐỘNG áp cho giao diện mới

Hai phép kiểm này tự dò mọi tệp phát sinh thẻ HTML trong `docs/` và `src/`,
nên trang mới bị soi ngay khi xuất hiện, không cần ai thêm vào danh sách:

| Phép kiểm | Đòi gì |
|---|---|
| `test_nothing_that_emits_markup_uses_an_untrusted_dom_sink` | Không dùng `.innerHTML`, `insertAdjacentHTML`, `outerHTML`, `document.write` |
| `test_no_published_page_renders_a_source_field` | Không vẽ danh tính nguồn dữ liệu ra trình duyệt |
| `test_every_published_page_declares_a_content_security_policy` | Mọi trang HTML phải khai `Content-Security-Policy` |

Vì `.innerHTML` bị cấm, mọi thao tác DOM động phải dùng
`document.createElement` + `textContent`. Đây là ràng buộc kiến trúc, không
phải gợi ý.

## 23.5 Ba safeguard đã mất cùng giao diện cũ — giao diện mới PHẢI dựng lại

| Safeguard | Vì sao cần | Lấy lại từ |
|---|---|---|
| Phát hiện báo cáo cũ hơn dữ liệu | Trang chất lượng từng tự báo khi `covers_through` lùi sau dữ liệu mới nhất | `git show 00cf02ea~1:src/build_model_quality.py` |
| Cột **độ nâng ngoài mẫu** cho cầu bóng | Chỉ hiện cột huấn luyện là cách trang soi cầu đánh lừa người đọc. Đo được: cầu mạnh nhất trong 206 082 luật đạt 1,235 khi huấn luyện rồi rơi về **0,913** trên tập giữ lại | `git show 00cf02ea~1:src/build_research_lab.py` |
| Cảnh báo "Không phải kết quả thật" | Bảng mô phỏng vui phải mang cảnh báo trên TRANG, không chỉ trong JSON. Liên quan mục 6.2 | `git show 00cf02ea~1:src/build_fun_prediction.py` |

## 23.6 Xuất xứ trọng số đã có sẵn ở tầng dữ liệu

`ensemble_utils.weights_provenance(data_dir, mode)` trả `xuat_xu`
(`da_hoc` / `bi_tu_choi` / `khong_co_ho_so`), `ly_do`, và `tham_dinh` với
LogLoss ngoài mẫu của cả ba ứng viên. Giao diện mới chỉ cần gọi và hiện —
không được tự suy xuất xứ bằng cách so trọng số với mặc định, vì phép suy ấy
báo "tệp thiếu hoặc sai lược đồ" cho một tệp hoàn toàn lành.

## 23.7 Tiến độ

Trạng thái thi hành luôn nằm ở `docs/ui-ux/implementation-progress.md`. Không
mục nào ở đó được đánh dấu xong khi chưa có phép đo kèm theo.
