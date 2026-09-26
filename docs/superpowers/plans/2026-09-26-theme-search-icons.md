# Hoàn thiện theme, search và icons — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans; các phần không trùng file được giao song song, chủ nhiệm tích hợp và kiểm tra cuối.

**Goal:** Sáng/tối toàn hệ thống, SVG chuẩn và tìm kiếm độc lập, có bằng chứng trước khi xuất bản.
**Architecture:** Theme bootstrap duy nhất tại page_output. Shell sinh markup tìm kiếm từ SITE_NAV; CSS page owners dùng token chung. Icon_svg giữ API, thay nội dung bằng Lucide canonical.
**Tech Stack:** Python generators, vanilla CSS/JS, local SVG, pytest, Node/JSDOM.
**Spec:** docs/superpowers/specs/2026-09-26-theme-search-icons-design.md

## Global Constraints

- Giữ dữ liệu thống kê và nội dung JSON; không CDN, framework hoặc HTML string sinks.
- Comments/docstrings tiếng Việt; classes app-; shell idempotent.
- Rail/header80px, panel240px overlay, radius8px.
- `.dark` phản ánh theme resolved; storage auto/light/dark tương thích.
- Chữ thông thường đạt 4.5:1 trên bề mặt sử dụng.

## Review Focus

- Storage/matchMedia thiếu hoặc ném lỗi: trang vẫn đọc và chuyển màu được (Task1).
- Hai truy vấn đồng thời, tiếng Việt không dấu, không kết quả: không chạm trạng thái nhau (Task2).
- Keyboard/mobile overlay: Escape/focus/inert đúng khi mở và đóng dialog (Task2).
- Ghi lại live.html đã bọc shell: không nhân markup hoặc script (Task4).
- Màu ô dữ liệu ở hàng chẵn/hover/dark: không bị màu điều hướng đè (Task3).

### Task1 — Theme runtime (root)
Files: src/assets/app-theme.js, src/page_output.py, tests/frontend/theme.test.mjs, tests/test_theme_bootstrap.py.
- [ ] Viết test RED cho explicit/auto, .dark, OS change, storage sync/errors, click chuyển màu thực tế và init trước CSS.
- [ ] Implement runtime + publish/inject script idempotent, chạy đồng bộ sau meta trước CSS.
- [ ] Chạy test GREEN, xác minh đột biến và idempotence.

### Task2 — Shell/search (crafto_motion), icons (crafto_inventory)
Files search: src/app_shell.py, src/assets/app-shell.js, src/templates/app_shell.css, tests/frontend/navigation.test.mjs, tests search.
Files icon: src/app_icons.py, src/assets/icons/*, license, tests/test_app_icons.py.
Interfaces: icon_svg(key, class) giữ nguyên; keys menu/close/sun/moon thêm. Theme runtime giữ #app-theme. Global dialog đặt trước app-main.
- [ ] Search tests RED: global đủhref, filter chỉ nhóm hiện tại, độc lập query, keyboard/focus/close.
- [ ] Implement generated dialog + safeDOM JS + theme-aware CSS; gỡ theme JS trùng; icon20/24 stroke2.
- [ ] Xác minh mapping canonical license, test hình học/coverage, test runtime GREEN và đột biến.

### Task3 — CSS toàn trang (crafto_css + vla_source_audit)
Shared owner: ui_theme.py CSS, ui_visual_system.css, app_design.css, stat_pages.css, frequency_bento.css.
Legacy owner: các builder/page-specific CSS và live inline CSS.
- [ ] Inventory hardcoded surfaces và test RED chứng minh không còn lightpin/hardcode mâu thuẫn.
- [ ] Gỡ pin, chuyển source tokens; đảm bảo explicit light thắng OS dark và dark pastel không lóa.
- [ ] Chạy contrast/source contract; cập nhật hợp đồng cũ bị yêu cầu mới thay thế có lý do và số đo.

### Task4 — Tích hợp, kiểm thử và phát hành (root + reviewer)
- [ ] Dựng lại29 trang, so dữ liệu và markup số, kiểm tra HTML/id trùng/link.
- [ ] Chạy full Python/frontend/lint, độc lập review thay đổi và sửa finding.
- [ ] Commit/PR, chờ CI, merge đúng head sau CI xanh.
- [ ] Kiểm tra public rendered light/dark, search, matrix và ghi bằng chứng/giới hạn thực tế.
