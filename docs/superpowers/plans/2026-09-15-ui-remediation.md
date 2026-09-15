# Nine-page UI Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa và đồng bộ chín trang VLA được chỉ định theo Master Design System, loại bỏ overflow/dock overlap và giảm chiều cao bảng bằng bố cục Bento mà không mất dữ liệu.

**Architecture:** Chỉnh tại nguồn sinh trang: stat-page builder/template cho bốn trang thống kê, Jinja template chung cho bốn trang soi cầu, builder riêng cho dashboard và research lab; live chỉ tinh chỉnh khi audit xác nhận cần. Thêm các contract test dựa trên class/markup ổn định để pipeline hằng ngày tái sinh trang vẫn giữ thiết kế.

**Tech Stack:** Python 3.11, Jinja2, HTML/CSS/vanilla JS, pytest/BeautifulSoup, GitHub Pages.

**Spec:** `documentation/architecture/ui-remediation-20260915.md`

## Global Constraints

- Giữ `assets/ui.css` làm stylesheet nền chuẩn và không tham chiếu `assets/vla.css`.
- Không thay đổi thuật toán/statistical semantics/ML outputs.
- Không cắt dữ liệu; giảm dàn trải bằng Bento, bounded scroll, sticky header và progressive disclosure.
- Dock/footer phải có safe area trên desktop/mobile và không chặn pointer/touch.
- Chỉnh builder/template nguồn thay vì vá trực tiếp HTML sinh ra khi nguồn tương ứng tồn tại.

---

### Task 1: Khóa lỗi bằng UI contract tests

**Files:**
- Create: `tests/test_targeted_ui_remediation.py`

**Interfaces:**
- Consumes: builder/template source and generated `docs/*.html`.
- Produces: regression contracts for stat-page page classes, path dock safe area, dashboard command center and research-lab instrument shell.

- [ ] **Step 1: Write failing tests**

```python
def test_path_template_reserves_dock_safe_area():
    html = Path("src/templates/path_ui_page.html.j2").read_text(encoding="utf-8")
    assert "ui-dock-space" in html
    assert "path-shell" in html


def test_stat_pages_expose_page_slug_for_scoped_layout():
    source = Path("src/build_stat_pages.py").read_text(encoding="utf-8")
    assert 'sp-page sp-page-{page.slug}' in source


def test_dashboard_has_command_center_shell():
    source = Path("src/build_dashboard.py").read_text(encoding="utf-8")
    assert "ai-command-center" in source


def test_research_lab_has_experiment_pipeline():
    source = Path("src/build_research_lab.py").read_text(encoding="utf-8")
    assert "rl-pipeline" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_targeted_ui_remediation.py`
Expected: FAIL on the new class/markup contracts before implementation.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_targeted_ui_remediation.py
git commit -m "test(ui): lock targeted page remediation contracts"
```

---

### Task 2: Rebuild detailed statistics layouts

**Files:**
- Modify: `src/build_stat_pages.py`
- Modify: `src/templates/stat_pages.css`
- Test: `tests/test_targeted_ui_remediation.py`

**Interfaces:**
- Consumes: existing `StatPage.slug`, table IDs and `stat_pages.js` renderers.
- Produces: body class `sp-page sp-page-<slug>` and scoped layouts without changing JS IDs/data.

- [ ] **Step 1: Add a stable page slug class**

Change non-frequency and frequency bodies so each generated page has `sp-page sp-page-{page.slug}` in addition to any existing body class. This provides a safe selector boundary instead of relying on `:has()` or global table rules.

- [ ] **Step 2: Implement scoped CSS**

Add selectors with these contracts:

```css
.sp-page-bang-dac-biet .sp-scroll{width:100%}
.sp-page-bang-dac-biet #sp-grid{width:100%;table-layout:fixed}

.sp-page-lo-gan #sp-grid,
.sp-page-lo-gan #sp-pair-gan{width:100%}
.sp-page-lo-gan .sp-scroll{width:100%;max-height:32rem;overflow:auto}

.sp-page-dau-duoi-loto .sp-recent-grid{
  display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem
}
.sp-page-dau-duoi-loto .sp-recent-grid .sp-scroll{width:100%;max-height:32rem;overflow:auto}

.sp-page-giai-dac-biet-theo-tong .sp-scroll{width:100%;overflow:auto}
```

At responsive breakpoints, collapse three recent panels to one column and preserve horizontal scroll inside each panel.

- [ ] **Step 3: Adjust only structural markup**

Wrap the three recent Head/Tail/Sum tables in `dau-duoi-loto` inside `.sp-recent-grid`. Add Bento card wrappers/section labels to `lo-gan` and `giai-dac-biet-theo-tong` while preserving all existing element IDs.

- [ ] **Step 4: Build and verify**

Run:
`python src/build_stat_pages.py --docs-dir /tmp/vla-stat-pages`
then `pytest -q tests/test_targeted_ui_remediation.py tests/test_ui_design_system.py`.
Expected: generated pages keep all data hooks and satisfy targeted layout contracts.

- [ ] **Step 5: Commit**

```bash
git add src/build_stat_pages.py src/templates/stat_pages.css tests/test_targeted_ui_remediation.py
git commit -m "fix(ui): rebalance detailed statistics pages"
```

---

### Task 3: Redesign path pages and eliminate dock/footer overflow

**Files:**
- Modify: `src/templates/path_ui_page.html.j2`
- Test: `tests/test_targeted_ui_remediation.py`

**Interfaces:**
- Consumes: `dock_html`, `nav_fallback_html`, `rows`, `picks`, `days`, `empty_reason` from `build_docs.py`.
- Produces: a shared `path-shell` for `soi-path-loto-*` and `soi-path-de-*` with dock-safe bottom spacing and bounded table regions.

- [ ] **Step 1: Add dock-safe app shell**

Use `<body class="ui-app ui-dock-space path-page">` and a `.path-shell` container with `padding-bottom: calc(var(--ui-dock-h, 64px) + env(safe-area-inset-bottom) + 2rem)`.

- [ ] **Step 2: Convert top content to Bento hierarchy**

Create a compact hero/status band, a two-column prediction/quick-pick grid and a full-width route matrix card. Keep all existing Jinja loops and visible explanatory text.

- [ ] **Step 3: Bound the route matrix**

Use `.path-table-scroll{max-height:min(66vh,52rem);overflow:auto}` with sticky headers. Footer/nav fallback must be outside the bounded table and above the dock safe area.

- [ ] **Step 4: Build and test**

Run: `python src/build_docs.py --display-days 10`
Then: `pytest -q tests/test_targeted_ui_remediation.py tests/test_dock_on_mobile.py`.
Expected: both active pages and stable siblings share the same fixed template contract; no fixed dock can overlap the footer/content area.

- [ ] **Step 5: Commit**

```bash
git add src/templates/path_ui_page.html.j2 tests/test_targeted_ui_remediation.py
git commit -m "fix(ui): rebuild path pages with dock-safe bento layout"
```

---

### Task 4: Upgrade AI/ML dashboard

**Files:**
- Modify: `src/build_dashboard.py`
- Test: `tests/test_targeted_ui_remediation.py`

**Interfaces:**
- Consumes: existing predictions, picks, weights and calibration payloads.
- Produces: `ai-command-center`, hero/status strip, two signal panels and model-health panels; model-quality builder output remains semantically unchanged.

- [ ] **Step 1: Introduce scoped dashboard CSS and hero**

Add an `ai-command-center` wrapper, an eyebrow/status row, latest-data badge, and subdued glass/Bento surfaces using shared tokens.

- [ ] **Step 2: Reorganize existing content**

Keep both top-20 tables and all JSON-derived definitions. Place LOTO and Đặc Biệt next-day signals as the primary visual pair; place picks/weights/calibration below in balanced panels.

- [ ] **Step 3: Verify output**

Run: `python src/build_dashboard.py --docs-dir /tmp/vla-dashboard`
Then: `pytest -q tests/test_targeted_ui_remediation.py tests/test_ui_design_system.py`.

- [ ] **Step 4: Commit**

```bash
git add src/build_dashboard.py tests/test_targeted_ui_remediation.py
git commit -m "feat(ui): turn ml dashboard into command center"
```

---

### Task 5: Turn Research Lab into an experiment workspace and audit Live

**Files:**
- Modify: `src/build_research_lab.py`
- Modify only if needed: `docs/live.html` and the source path responsible for preserving its custom markup
- Test: `tests/test_targeted_ui_remediation.py`

**Interfaces:**
- Consumes: existing diagnostic/firewall/strategy/cross-lag/conditional datasets.
- Produces: `rl-pipeline`, research-firewall status area, instrument-style panels and explicit experiment stages; live retains realtime semantics.

- [ ] **Step 1: Add the research pipeline**

Render five stages: `Giả thuyết → Huấn luyện → Kiểm định → Tập giữ lại → Cổng vận hành`, with the production gate visually separated from exploratory results.

- [ ] **Step 2: Group laboratory instruments**

Use Bento sections for `Research Firewall`, diagnostics, strategy chambers, cross-lag/bóng bridge experiments and legacy observations. Keep all existing tables and cautionary copy.

- [ ] **Step 3: Audit Live**

Confirm live has shared stylesheet, adequate dock-safe bottom spacing, no full-width overflow and consistent card radii/spacing. Only make a scoped visual refinement if a concrete mismatch remains; do not disturb polling/reveal logic.

- [ ] **Step 4: Build and verify**

Run:
`python src/build_research_lab.py --data-dir data --docs-dir /tmp/vla-research`
then targeted tests and dock tests.

- [ ] **Step 5: Commit**

```bash
git add src/build_research_lab.py tests/test_targeted_ui_remediation.py
git commit -m "feat(ui): rebuild research lab as experiment workspace"
```

---

### Task 6: Full verification, generated artifacts, PR and merge gate

**Files:**
- Generated as appropriate: `docs/*.html`, `docs/assets/ui.css`
- No algorithm files should change.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: a merge-ready UI-only change set.

- [ ] **Step 1: Regenerate all docs using the production builders/pipeline with sync/ML skipped where safe**

Run the same doc builders used by `src/pipeline.py`; verify that generated targets include all nine pages.

- [ ] **Step 2: Run regression tests**

Run:
`pytest -q tests/test_targeted_ui_remediation.py tests/test_published_ui_contract.py tests/test_dock_on_mobile.py tests/test_ui_design_system.py`.
Expected: all pass.

- [ ] **Step 3: Inspect diff scope**

Confirm no statistical formulas, model artifacts or unrelated dependencies changed.

- [ ] **Step 4: Create PR and inspect CI status**

Do not report skipped checks as green. Resolve actual failures before merge.

- [ ] **Step 5: Squash merge after verification**

Merge only when source contracts and generated output are consistent; report exact PR, merge SHA and any live-site verification limitation.
