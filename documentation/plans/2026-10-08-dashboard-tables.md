# Bố cục bảng Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Triển khai trực tiếp và review độc lập trước merge.

**Goal:** Thiết kế lại toàn bộ bảng Dashboard, sửa cột giá trị bị đẩy ngoài khung.
**Architecture:** Bốn nhóm nội dung, mỗi nhóm đối chiếu hai kênh. Trình bày riêng xác suất, danh sách mã, trọng số và hiệu chỉnh; CSS chỉ có hiệu lực trong Dashboard. JSON gốc giữ nguyên trong khối mở rộng.
**Tech Stack:** Python, HTML và CSS viết tay; không thêm framework hay JavaScript.
**Spec:** Yêu cầu chủ dự án: thực hiện sau khi bản sửa số 0 được merge/phát hành. PR #143 đã merge, Pages và bốn trang live đã xác minh trước khi bắt đầu nhánh này.

## Global Constraints

- Giữ xác suất, thứ tự dự báo, các mã số đủ hai chữ số và JSON gốc.
- Giữ phong cách phòng nghiên cứu, giao diện sáng/tối và cơ chế bằng chứng.
- Không tràn ngang bảng trên điện thoại, kể cả khi mở hồ sơ có chuỗi dài.

## Review Focus

- Top 10 phải hiện đủ mười mã, không bị cắt còn sáu như bảng liệt kê cũ.
- Thiếu dữ liệu khác trạng thái không hoạt động và số 0.
- Nội dung JSON gốc phải còn nguyên để kiểm chứng.
- Số xác suất và tham số phải mở đúng nhóm bằng chứng.
- Mở thẻ kiểm chứng không kéo cột hoặc ép chiều cao thẻ bên cạnh.

## Task 1: Trình bày và bố cục

- [x] Đo lỗi hiện hữu: bảng gợi ý rộng 1.181 px trong khung 586 px; trên điện thoại 1.165/324 px.
- [x] Viết hai kiểm thử dữ liệu và trạng thái rỗng; quan sát cả hai thất bại trước sửa.
- [x] Thêm `dashboard_tables.py`, CSS có phạm vi, gọi từ `build_dashboard.py`.
- [x] Dựng trang thật; 33 kiểm thử trọng tâm đạt.
- [x] Kiểm trình duyệt: 24 trạng thái ở 320–1.440 px, sáng/tối và hồ sơ đóng/mở; không tràn ngang. 48 ngăn bằng chứng và 12 lượt điều hướng bàn phím đạt.
- [x] Đối chiếu: sáu JSON gốc và từng ô của hai bảng xác suất giữ nguyên. Bộ kiểm giao diện chung: 592 đạt, 7 bỏ qua.

## Task 2: Tích hợp

- [x] Review độc lập: sửa tên thành phần `w_cau` thành “Cầu-kèo AI/ML”, kiểm thử hồi quy đã thất bại trước sửa và đạt sau sửa. Không có finding Important/Critical khác.
- [x] Kiểm thử toàn dự án sau sửa: 3.193 đạt, 8 bỏ qua; lint và kiểm tra khoảng trắng đạt.
- [ ] Tạo PR, đợi CI, merge và xác minh Pages.
