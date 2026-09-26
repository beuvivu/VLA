# Crafto Application Integration Implementation Plan

> **For agentic workers:** Use parallel focused implementation tasks, followed by an independent whole-branch review.

**Goal:** Hoàn thiện hệ thống thị giác Crafto trên ứng dụng thống kê hiện tại.
**Architecture:** CSS và JS độc lập, gắn tại ranh giới `write_page`; hero được dựng từ dữ liệu thật.
**Tech Stack:** Python, CSS thuần, JavaScript thuần; tài nguyên nội bộ.
**Spec:** `docs/design/crafto-integration-2026-09-26.md`

## Global Constraints

- Giữ rail/header 80px, panel phủ 240px, menu 7 nhóm.
- Tiền tố app-, tiếng Việt có dấu; không đổi dữ liệu, màu thống kê hay mô hình.
- Không framework/CDN, không HTML sink; không giấu nội dung khi thiếu JS.
- Output lũy đẳng, reduced motion và touch được hỗ trợ.

## Review Focus

- Ghi lại HTML đã có shell không được lồng shell hoặc hiệu ứng.
- Storage bị chặn vẫn phải thao tác và tắt chuyển động được.
- Tab ẩn và thiết bị cảm ứng không chạy vòng lặp cursor liên tục.
- Bảng có màu trạng thái giữ nguyên ý nghĩa và độ tương phản.
- Mobile 360px không có hero/header tràn ngang.

### Task 1: Ranh giới xuất bản và hero

Files: `src/page_output.py`, `src/crafto_design.py`, `src/build_landing_page.py`, `tests/test_crafto_design.py`.

- [ ] Kiểm thử xuất bản CSS/JS, lũy đẳng hai lần, giữ JSON và nội dung số.
- [ ] Thêm helper `attach_crafto_design(path: Path, html: str) -> str` sau shell.
- [ ] Gắn script defer trong head để không phá bộ gỡ shell cũ; effects trong app-main.
- [ ] Dựng hero với mô tả rõ ràng, liên kết thật và dữ liệu mới nhất, giữ h1 và các id.
- [ ] Dựng lại các trang từ dữ liệu có sẵn, xác minh thay đổi chỉ ở giao diện.

### Task 2: Hệ thống CSS

Files: `src/templates/app_design.css`.

- [ ] Áp dụng hợp đồng selector trong spec; lớp cuối sau app-shell.
- [ ] Hero gradient/marquee/visual cards, bề mặt trắng, nút viên thuốc, icon nhất quán.
- [ ] Dark mode theo token; trạng thái reduced motion/off/hidden dừng animation.
- [ ] Mobile, focus-visible, print và bề mặt dữ liệu không dịch chuyển.

### Task 3: Runtime chuyển động

Files: `src/assets/app-motion.js`, `tests/frontend/motion.test.mjs`, `tests/frontend/package.json`.

- [ ] Test trước cho toggle/persistence/reduced motion/touch/visibility/idempotent startup.
- [ ] Dùng requestAnimationFrame gộp pointer input, không vòng lặp chạy vô hạn.
- [ ] IntersectionObserver chỉ cho vùng trang trí; storage lỗi không làm hỏng khởi tạo.
- [ ] Chạy npm test gồm điều hướng hiện có và runtime mới.

### Task 4: QA và tích hợp

- [ ] Chạy kiểm thử Python/UI, JS, kiểm tra cú pháp và tài nguyên tham chiếu.
- [ ] Kiểm tra trực quan hero, bảng, menu, theme, chuyển động trên kích thước thực.
- [ ] Review độc lập; sửa lỗi; đồng bộ main và PR91 trước đẩy PR.
- [ ] Đẩy PR; merge khi cổng kiểm thử đạt; báo chính xác trạng thái triển khai.
