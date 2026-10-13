# Hoàn tất PR và khắc phục khoảng trống CI

> **For agentic workers:** Dùng quy trình executing-plans; kiểm tra từng bước trước khi xác nhận hoàn tất.

**Goal:** Kiểm thử và hoàn tất các PR còn mở, khắc phục việc CI bỏ qua PR nội bộ ngoài danh sách nhánh push.

**Architecture:** Giữ danh sách push hiện tại để tránh chạy bộ kiểm nặng trên nhánh dữ liệu live. Hai job chỉ bỏ qua PR nội bộ nếu nhánh nguồn thực sự đã được push phủ. Hợp nhất bảy cập nhật Dependabot vào một nhánh tích hợp, giữ nguyên commit gốc để GitHub ghi nhận các PR đã được hợp nhất.

**Tech Stack:** GitHub Actions, Python 3.11 trên CI, pytest, Node 22, Chromium.

**Spec:** Yêu cầu ngày 27-09-2026: kiểm tra và hoàn thiện PR/CI còn dang dở, bỏ qua check AI của GitHub.

## Ràng buộc

- Không thay đổi mô hình, dữ liệu lịch sử hoặc ngưỡng chất lượng.
- Không bỏ qua CodeQL, kiểm thử, cổng phát hành hoặc kiểm tra trình duyệt.
- Check AI do GitHub quản lý được loại khỏi điều kiện hoàn tất theo yêu cầu; không đánh dấu giả là thành công.
- Không sửa những bản làm việc cũ có thay đổi chưa commit.
- Không đẩy trực tiếp vào main; chỉ hợp nhất sau khi CI trên commit tích hợp đạt.

## Các tình huống phải kiểm tra

- PR Dependabot và nhánh nội bộ tùy ý không bị bỏ qua.
- Nhánh codex/claude/main/master không chạy trùng push và PR.
- PR từ fork luôn được kiểm thử, kể cả tên nhánh giống nhánh nội bộ.
- workflow_dispatch tiếp tục chạy cả hai job.
- Cập nhật dependency phù hợp với các model lưu sẵn và đường River tùy chọn.

## Thực hiện

- [x] Xác minh PR #100 đã merge, CI và CodeQL đạt; nhận diện bảy PR dependency còn mở.
- [x] Hợp nhất các commit của #79–#84 và #101 vào nhánh tích hợp.
- [x] Thêm phép kiểm ma trận sự kiện đọc điều kiện thật trong `.github/workflows/ci.yml`; xác nhận đỏ với cấu hình cũ.
- [x] Sửa điều kiện cả hai job; xác nhận ma trận xanh và đột biến làm đỏ.
- [ ] Kiểm tra dependency mới, Ruff, kiểm thử đầy đủ và bốn cổng phát hành qua CI.
- [ ] Review độc lập thay đổi cuối; tạo PR tích hợp, xác minh đúng SHA trước merge.
- [ ] Xác minh PR gốc đóng sau merge và CI trên main.

## Quyết định khi thực hiện

- Dùng job chọn sự kiện nhỏ với thời hạn hai phút: biểu thức chuỗi GitHub không phân biệt hoa thường, trong khi bộ lọc nhánh push có phân biệt. Script Python đọc metadata qua biến môi trường và so khớp chính xác; lỗi chọn sự kiện làm workflow đỏ. Các phép kiểm thực thi nguyên script và bắt đột biến chuyển so sánh thành chữ thường.
- Giữ cả PyYAML mới và Ruff mới khi giải quyết xung đột hai dòng kề nhau trong `requirements-dev.txt`.
- Sửa ba vi phạm Ruff có sẵn trong kịch bản Chromium: độ dài vector màu và biến callback trong vòng lặp. Callback route nhận đủ hai đối số Playwright trước tham số giữ fixture.
- Kiểm tra model lưu sẵn trên scikit-learn 1.9.1: năm estimator trả xác suất hữu hạn, pack LOTO còn lại giữ trạng thái `insufficient_history` hợp lệ từ PR #100.

Bằng chứng CI cuối và trạng thái merge được ghi tại PR tích hợp để luôn trỏ đúng SHA đã chạy.
