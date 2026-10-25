# Sửa tra cứu Đặc Biệt hôm sau và làm rõ các trang dự báo

Yêu cầu ngày 25-10-2026: sửa `giai-db-ngay-mai.html` theo lịch sử các lần cùng hai số cuối xuất hiện; thiết kế lại hai trang Top 10 ML và trang soi cầu vị trí để dễ xem và dễ hiểu.

Yêu cầu bổ sung trong cùng phiên: tô ba mức số đường cầu cao nhất ở `soi-cau-loto.html` và `soi-cau-hai-nhay.html`, chỉ xét từng số có hơn 7 đường cầu; đồng hạng cùng màu. Đổi bộ lọc phải tính lại màu.

## Thiết kế

- Giữ khung Nexlink và hệ màu chung; giao diện dữ liệu sáng rõ, tiêu đề gọn, không dải giới thiệu lớn hay thẻ trang trí chiếm chỗ. Màu Đặc Biệt đỏ, LOTO xanh theo token; sáng/tối đồng bộ.
- Đặc Biệt hôm sau: chọn 00–99 (mặc định hai số cuối kỳ mới nhất), toàn bộ lịch sử mặc định, liệt kê các lần cùng đuôi từ mới đến cũ. Cột giải gốc giữ đủ 5 số và nhấn đúng 2 số cuối. Cạnh nó là Đặc Biệt của ngày lịch kế tiếp và ngày tương ứng. Không lấy ngày có dữ liệu kế tiếp để thay cho một ngày bị thiếu; chưa có kết quả giữ trạng thái trống có giải thích. Bảng tần suất chỉ đếm các kết quả kế tiếp đã biết, không biến thành xác suất dự báo.
- Top 10 ML: một tiêu đề ngắn, chuyển Đặc Biệt/LOTO rõ ràng, kỳ dự báo và trạng thái mức tin, bảng xếp hạng có cột số và xác suất dễ đọc. Giữ thứ tự, số 0 đầu, xác suất đầy đủ, bằng chứng từng giá trị và ý nghĩa mức tin. Giải thích kỹ thuật đặt trong phần mở rộng.
- Soi cầu vị trí: luồng đọc "chọn điều kiện → chọn cặp số/cầu → xem từng kỳ"; hướng dẫn ngắn ngay chỗ thao tác. Dải chọn và kết quả nổi bật, bảng vị trí rõ nhãn giải/chữ số; kiểm chứng thống kê và phương pháp đặt sau phần sử dụng, có thể mở rộng. Giữ nguyên luật cầu và hợp đồng query.
- Hai bảng cầu LOTO: xếp ba mức đếm khác nhau từ cao xuống thấp, chỉ trong các số có >7 đường cầu. Nhất vàng, nhì xanh dương, ba xanh lá theo token sáng/tối; giữ màu khi chọn/rê chuột, có chú giải và nhãn truy cập. Không cộng chung số đảo và không thay đổi luật hay điểm kiểm chứng.
- Tất cả không tràn ngang toàn trang ở 390/768/1440px; bảng rộng được cuộn riêng; không tooltip từ chuột, không chuỗi HTML gán vào DOM; không lộ danh tính nguồn trên trang xuất bản.

## Phương án

Chọn chỉnh có phạm vi ở trình dựng/tài nguyên riêng: sửa đúng luồng nghiệp vụ, không ảnh hưởng các trang khác. Thay hệ CSS toàn kho hoặc thêm framework không cần thiết và làm tăng rủi ro hồi quy.

## Thực hiện và kiểm chứng

- [x] TDD cho các lần trùng đuôi, ngày kế tiếp thực, ngày thiếu/chờ, số 0 đầu, thứ tự ngược thời gian và bộ lọc; bỏ phép xếp hạng gan cũ.
- [x] Thiết kế lại ML, giữ bằng chứng, ngày và mức tin; kiểm dữ liệu không đổi và trạng thái rỗng.
- [x] Thiết kế lại soi cầu, giữ thuật toán/query và kiểm Python ↔ JS; kiểm thao tác chọn hai vị trí và đường cầu.
- [x] TDD cho màu >7 đường cầu, đồng hạng, giới hạn ba mức, đổi bộ lọc, giới hạn đúng hai trang và Python ↔ JS.
- [x] Dựng sáu trang, kiểm Chromium thực 390/768/1440px và sáng/tối, kiểm bàn phím/mobile; chụp ảnh trước/sau trong scratch.
- [x] Chạy pytest/Node/Ruff liên quan, kiểm trình duyệt và review độc lập với bằng chứng; bộ Python toàn repo chạy bổ sung.

Baseline: 168 kiểm thử ML/trang thống kê/cầu vị trí đạt trước sửa trên nhánh từ `origin/main` 9daca67.
