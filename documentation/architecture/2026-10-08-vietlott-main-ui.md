# Vietlott: giao diện theo trang chính

Phân hệ Vietlott dùng cùng font và chế độ ngày/đêm với trang chính. Nội dung
dùng Inter var tự host, khung điều hướng giữ Instrument Sans. Các trang không
khai báo bảng màu riêng hoặc lưu một lựa chọn theme khác `app-theme`.

## Bố cục

- Tổng quan: hero hai cột, phần giới thiệu và hành động bên trái; thẻ Jackpot
  Power 6/55 bên phải, chuyển sang Mega 6/45 khi Power chưa có kỳ xác thực.
  Hub giữ đủ bảy sản phẩm và tất cả mục thống kê, dự báo, đối chiếu, trạng thái.
- Sản phẩm: hero, điều hướng sản phẩm, bộ số nháp cho Mega/Power, kỳ mới nhất,
  dự báo/phân tích, đối chiếu, lịch sử và cơ cấu giải.
- Hero 24px, card 16px, nút pill 50px, control tối thiểu 44px. Grid luôn có
  `minmax(0,1fr)` và chuyển thành một cột trên điện thoại.
- Thẻ Jackpot chỉ đọc `latest.prizes` của đúng sản phẩm; Power giữ cả hai
  pool. Tiền chưa công bố hiện `—`, không lấy kỳ cũ làm giá trị hiện tại.

## Nguồn dựng

`src/build_vietlott_results.py` đọc CSS native từ
`src/templates/vietlott_main.css`, xuất đủ tám trang qua `write_page`, và
chép `src/assets/vietlott-picks.js` sang `docs/assets`. Workflow Vietlott
kích hoạt khi các tệp nguồn này thay đổi và lưu cả asset được dựng.
Shell, font, theme, evidence và motion vẫn do đường xuất trang chung gắn vào.

## Bộ số nháp

Bộ chọn chỉ có trên Mega 6/45 và Power 6/55, chạy hoàn toàn trong trình duyệt.
Mỗi bộ gồm đúng sáu số riêng biệt trong miền của sản phẩm. Chọn nhanh xáo
trộn toàn miền rồi lấy sáu số; đây là thao tác ngẫu nhiên. Xóa trả lại trạng
thái trống. Một nút số ở trong luồng Tab; mũi tên và Home/End di chuyển,
Enter/Space chọn hoặc bỏ chọn. Nút xem trước mở khi chọn đủ sáu số.

Dialog hiển thị bộ số đã sắp tăng dần. Escape hoặc Chỉnh sửa đóng dialog,
trả focus về nút xem trước. Tải bộ số tạo TXT trên thiết bị, ghi rõ bộ số
nháp chưa phải vé đã mua. Không có giao dịch, API đặt vé, ghi sổ dự báo,
lưu server hoặc mô hình AI trong bộ chọn. Khi JavaScript tắt, trang kết quả
vẫn đọc được và bộ chọn có thông báo yêu cầu bật JavaScript.

Màu nền, chữ, border, focus và trạng thái chọn dùng token chung. Các con số
dùng Inter var với `tabular-nums`; reduced motion tắt transition riêng.
In giấy ẩn bộ chọn và hành động, giữ nội dung kết quả.
