# Hoàn thiện và dọn giao diện Nexlink

> Thực hiện trực tiếp theo executing-plans; review độc lập trước khi tích hợp.

**Mục tiêu:** Gỡ điều hướng đã nghỉ, sửa focus bị kẹt khi đóng menu và hoàn thiện skin trang con.
**Kiến trúc:** Giữ `write_page` là điểm xuất bản duy nhất. Bộ dựng không sinh dock; wrapper chỉ nhận diện bản cũ để chuyển đổi an toàn. Bề mặt chung dùng token, giữ nguyên bảng và dữ liệu.
**Công nghệ:** Python, HTML/CSS, JavaScript thuần, pytest, jsdom.
**Đặc tả:** `documentation/architecture/ui-design-system.md` và yêu cầu Nexlink của chủ dự án.

## Ràng buộc
- Dải biểu tượng 80px, panel 240px phủ nội dung, header 80px.
- Gradient dành cho trang chủ. Không đổi dữ liệu hay mô hình.
- Không framework, không ghi DOM bằng chuỗi HTML, không tiết lộ nguồn dữ liệu.
- Xuất HTML bằng `write_page`; kiểm tra trước push/PR/merge đã được ủy quyền.

## Điểm review
- HTML cũ có script nghiệp vụ ngay sau nav: chỉ xóa đúng script dock.
- Ghi lại cùng trang hai lần phải ổn định.
- Menu đóng do scrim, liên kết hoặc resize: không giữ focus trong vùng inert.
- Các nút hero phải đọc được cả sáng/tối sau khi bỏ nền gradient.
- Tài nguyên chạy tay vẫn có người gọi: không xóa nhầm.

## Task 1: Gỡ dock đã nghỉ
Tệp: `src/ui_theme.py`, các builder gọi dock, `src/app_shell.py`, `src/web_security.py`, `scripts/patch_csp_no_inline.py`, tests và assets.
- [x] Viết regression: wrapper bỏ script dock nhưng giữ script khác; cây xuất bản không còn script dock; test tài nguyên không còn ngoại lệ chết.
- [x] Chạy đỏ: `PYTHONPATH=src ../venv/bin/python3 -m pytest tests/test_ui_cleanup.py -q`.
- [x] Bỏ hàm sinh dock và caller; bỏ CSS dock, helper không caller, hai asset không dùng. Wrapper nhận diện đúng phần script dock. Chạy writer cho 29 trang, xác nhận JSON/bảng không đổi.
- [x] Chạy xanh và commit.

## Task 2: Hoàn thiện tương tác và skin
Tệp: `src/assets/app-shell.js`, `src/templates/ui_visual_system.css`, `tests/frontend/navigation.test.mjs`.
- [x] Regression focus: mở menu, focus search, đóng bằng scrim; mong đợi `activeElement.id === 'app-toggle'`.
- [x] Chạy `npm test --prefix tests/frontend`, xác nhận lỗi trước sửa.
- [x] Trả focus về toggle trước khi vùng bị inert; đồng bộ title fullscreen. Neutral hero/section/KPI trang con dùng token, radius10, h1/h2 24px.
- [x] Chạy JS tests; kiểm tra HTML thực trên site sau triển khai.

## Task 3: Tích hợp
- [x] Cập nhật hướng dẫn kiến trúc không còn mô tả dock là điều hướng chính.
- [x] Full pytest, JS tests, diff check; review độc lập và xử lý kết quả.
- [ ] Push, tạo PR, theo dõi CI/CodeQL, merge và kiểm tra Pages.

## Kiểm chứng ngày 25/09/2026

- Đồng bộ dữ liệu từ `main` tại `08ff523e74d21cde35bfdda0292dfb99f09ec24b`.
- Full pytest sau tích hợp: **1.930 đạt, 8 bỏ qua, 14 cảnh báo** (165,18 giây).
- JavaScript: **10/10 đạt**. Sau sửa nhãn thống kê: **17/17 đạt**.
- Ruff E9/F63/F7/F82 và `git diff --check` đạt.
- Cả 29 trang giữ nguyên bảng, JSON nhúng, ID và script nghiệp vụ; một rail/main/toggle mỗi trang; writer ổn định khi ghi lại.
- Review độc lập không có lỗi chặn merge. Đã sửa nhãn UI/UX còn sót, giữ nguyên neo `ui-ux`.
- Trang trực tiếp trước sửa có 11 lớp khung. Regression kiểm tra cả HTML chuẩn hóa thành div và 12 lớp lồng.
- Kết quả CI, merge và kiểm tra site sau triển khai được ghi trong PR.
