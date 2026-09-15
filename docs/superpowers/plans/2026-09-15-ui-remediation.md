# VLA Master Bento UI Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuẩn hóa toàn bộ màn hình VLA được chỉ định theo Soft Modern UI + Bento Grid, sửa overflow/dock overlap, giảm dàn trải dọc và tạo Research Lab mang bản sắc High-Tech Data Lab mà không thay đổi logic dữ liệu.

**Architecture:** Giữ các builder chịu trách nhiệm dữ liệu/semantic HTML. Áp dụng một lớp presentation idempotent tại output boundary: `page_output.write_page()` gọi `ui_page_refinements.refine_page(path, html)` trước khi strip comment và ghi vào `docs/`. Cách này bảo đảm mọi lần daily build đều tái áp dụng Master Design System và tránh nhân bản CSS/markup trong nhiều builder.

**Tech Stack:** Python 3.11, HTML/CSS/vanilla JS, Jinja2, pytest, GitHub Actions, GitHub Pages.

**Spec:** `documentation/architecture/ui-remediation-20260915.md`

## Global Constraints

- Giữ `assets/ui.css` làm stylesheet nền chuẩn; không khôi phục `assets/vla.css`.
- Không thay đổi thuật toán, xác suất, model, prediction artifact hoặc statistical semantics.
- Giữ nguyên element ID và JavaScript data hook hiện có.
- Không cắt dữ liệu; giảm chiều dài bằng Bento grid, bounded scroll và responsive hierarchy.
- Dùng nền `#F4F5FF → #EAEBFF → #E8ECFF`, glass cards và Indigo accent cho Light Mode.
- Dock/footer phải có `safe-area-inset-bottom` và không chặn touch/pointer.
- Refinement phải idempotent.

---

### Task 1: Establish an output-boundary visual compositor

**Files:**
- Create: `src/ui_page_refinements.py`
- Modify: `src/page_output.py`
- Test: `tests/test_targeted_ui_remediation.py`

**Interfaces:**
- Consumes: final semantic HTML plus destination filename.
- Produces: `refine_page(path: Path | str, page: str) -> str`.

- [x] **Step 1:** Add failing structural contracts for target screens.
- [x] **Step 2:** Implement `refine_page` as filename-scoped, idempotent presentation composition.
- [x] **Step 3:** Route `write_page()` through the compositor before `strip_comments()`.
- [x] **Step 4:** Verify unrelated pages remain byte-for-byte unchanged by the compositor.

---

### Task 2: Rebuild detailed statistics screens

**Files:**
- Modify through compositor: `src/ui_page_refinements.py`
- Test: `tests/test_targeted_ui_remediation.py`

**Targets:** `bang-dac-biet.html`, `lo-gan.html`, `dau-duoi-loto.html`, `giai-dac-biet-theo-tong.html`, `cau-dac-biet-theo-bo-so.html`, `giai-db-ngay-mai.html`, `cap-lon-loto.html`.

- [x] **Step 1:** Make weekly special table full-width with fixed table layout and mobile overflow.
- [x] **Step 2:** Bound Lô gan table regions to internal scroll and retain two-column desktop Bento hierarchy.
- [x] **Step 3:** Transform the three recent Head/Tail/Sum tables into a responsive 3-card grid.
- [x] **Step 4:** Bound Special-by-sum transition/parity tables to prevent viewport breakage.
- [x] **Step 5:** Apply the same glass/Bento/scroll contract to the three additional requested statistic pages.

---

### Task 3: Normalize all path-analysis screens

**Files:**
- Modify through compositor: `src/ui_page_refinements.py`
- Existing source retained: `src/templates/path_ui_page.html.j2`, `src/build_docs.py`
- Test: `tests/test_targeted_ui_remediation.py`

**Targets:** `soi-path-loto-active.html`, `soi-path-de-active.html` and their stable siblings.

- [x] **Step 1:** Add `path-shell`, `path-hero`, `path-overview` and dock-safe body contract.
- [x] **Step 2:** Convert the formerly dark page to the shared light Soft Modern palette.
- [x] **Step 3:** Add bounded route-table scroll with sticky header.
- [x] **Step 4:** Apply miss-cell hatch and Đặc Biệt palette without changing cell logic.
- [x] **Step 5:** Preserve the shared template contract across LOTO/Đặc Biệt active/stable pages.

---

### Task 4: Upgrade realtime and AI/ML command surfaces

**Files:**
- Modify through compositor: `src/ui_page_refinements.py`
- Existing builders/logic retained: `docs/live.html`, `src/build_dashboard.py`
- Test: `tests/test_targeted_ui_remediation.py`

- [x] **Step 1:** Convert `live.html` to 12-column Realtime Bento while preserving polling, reveal and consensus logic.
- [x] **Step 2:** Keep Special red/pastel, empty hatch, verification badge and source-health hierarchy readable in Light Mode.
- [x] **Step 3:** Convert `dashboard.html` to an AI/ML glass Command Center with status widgets and Indigo emphasis.
- [x] **Step 4:** Keep all prediction/pick/weight/calibration content semantically unchanged.

---

### Task 5: Build the Research Lab identity

**Files:**
- Modify through compositor: `src/ui_page_refinements.py`
- Existing data builder retained: `src/build_research_lab.py`
- Test: `tests/test_targeted_ui_remediation.py`

- [x] **Step 1:** Keep the global page light but use a dark cyber-lab hero.
- [x] **Step 2:** Add `LIVE AI PROCESSING`, subtle LED accents and monospace instrumentation labels.
- [x] **Step 3:** Add the five-stage research pipeline: Giả thuyết → Huấn luyện → Kiểm định → Tập giữ lại → Cổng vận hành.
- [x] **Step 4:** Add AI Parameters, Backtest Runner, Number × Bóng Matrix and Confidence Gate experiment modules.
- [x] **Step 5:** Add a reduced-motion-safe scanning effect and explicitly state that the gauge is not hit probability.
- [x] **Step 6:** Lock valid sibling hierarchy between hero, pipeline and experiment console.

---

### Task 6: Verification, PR and merge gate

**Files:**
- `tests/test_targeted_ui_remediation.py`
- `documentation/architecture/ui-remediation-20260915.md`
- this plan

- [x] **Step 1:** Inspect diff scope and confirm algorithm/model/data source files are untouched.
- [x] **Step 2:** Add idempotence and no-op regression contracts.
- [ ] **Step 3:** Run the latest branch CI to completion; older runs cancelled by newer commits do not count.
- [ ] **Step 4:** Confirm PR is mergeable against current `main` and inspect final diff.
- [ ] **Step 5:** Squash merge only after fresh CI success.
- [ ] **Step 6:** Verify the resulting `main` commit and Pages/pipeline deployment state; do not claim pixel verification unless directly observed.
