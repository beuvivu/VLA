# Tự học mẫu hình Vietlott — 24-10-2026

Mục tiêu: bổ sung chuyên gia học thống kê có thể kiểm chứng vào bộ dự báo hiện tại. Không cam kết xác suất trúng cao hơn khi dữ liệu chưa chứng minh.

## Phương án

1. Thêm mạng sâu: trùng vai trò GRU/mạng hiện có, khó kiểm toán và tốn tài nguyên.
2. Chuyên gia thống kê riêng biệt: tần suất Bayes ngắn/dài, chuyển trạng thái xuất hiện, hazard theo nhóm khoảng cách; chọn phương án này vì học trực tuyến, bộ nhớ nhỏ và chấm riêng từng thuật toán được.
3. Thay bộ dự báo: rủi ro mất hợp đồng checkpoint/sổ dự báo; không chọn.

## Hợp đồng

- Giữ đúng thứ tự dự báo → chấm → học; không dùng kỳ đang chấm làm đặc trưng.
- Bốn vector xác suất của `PatternExperts(nodes, base)` phải hữu hạn và có prior co về nền; không giả định số lâu chưa về sẽ đến hạn.
- Tần suất giảm trọng số theo thời gian (half-life 16/128 kỳ); chuyển trạng thái và hazard chỉ học khi hai ID liên tiếp. Mất kỳ thì kiểm duyệt lại tuổi khoảng cách; không bịa kết quả.
- Tích hợp qua `MLConfig.patterns`, mặc định False ở API cấp thấp. Chỉ bật mặc định vận hành nếu phép so ngoài mẫu chứng minh cải thiện; nếu chưa đủ bằng chứng, giữ như challenger bật tường minh qua cấu hình.
- Mỗi chuyên gia được chấm log-likelihood bằng luật tập cố định/categorical hiện có và học trọng số mũ; giữ chuyên gia uniform và cổng xác thực live.
- Checkpoint cấu hình cũ vẫn đọc được. Bật pattern trên checkpoint cũ thì replay lịch sử cho chính sách mới, giữ nguyên law/vé đã phát và không kế thừa điểm live của chính sách cũ.
- Không đổi giao thức H benchmark đã đăng ký. Báo cáo mới là thăm dò, kiểm chứng trên mọi sản phẩm, so với nền và mô hình trước sửa; không gọi đây là kiểm định độc lập sau khi đã xem kết quả.
- Chú thích/docstring mới tiếng Việt; không thay sổ lịch sử hoặc trang UI ngoài phạm vi.

## Kiểm chứng

Kiểm thử tín hiệu tổng hợp (bias, chuyển trạng thái, chu kỳ, đổi chế độ), cold-start, missing IDs, dữ liệu sai, checkpoint/chạy chia đoạn, và tính nhân quả. Chạy bộ Vietlott và phép kiểm tích hợp VLA. Đo 600 kỳ với 400 kỳ khởi tạo, 200 kỳ score-before-learn, tất cả 7 sản phẩm; ghi rõ hạn chế thống kê.
