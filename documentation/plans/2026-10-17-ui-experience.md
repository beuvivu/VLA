# Nâng cấp trải nghiệm thống kê ngày 17-10-2026

## Phạm vi đã được yêu cầu

Triển khai trực tiếp thiết kế của chủ dự án: số chính lớn, rõ, emerald/amber;
phân cấp số và chỉ báo; thẻ dữ liệu gọn, sáng/tối đồng bộ; dùng tốt trên điện
thoại. Giữ khung điều hướng, phép tính, dữ liệu lịch sử và các sổ dự báo.

## Hợp đồng thiết kế

- Trang chủ dùng nhấp đúp để mở căn cứ số. Nhấp chọn số, bàn phím và nhấn giữ
  vẫn hoạt động. Các bảng dự báo dùng cùng tỉ lệ cột xác suất.
- Ma trận có chế độ Ngang/Dọc; điện thoại ưu tiên hàng/thẻ từng số. Mỗi số
  00–99 có số lượt và biểu đồ nhỏ tính từ chính khoảng kỳ đang chọn.
- Demo có các bước đọc dữ liệu rõ ràng; trạng thái demo tách khỏi dữ liệu thật.
- Các trang phân tích có ngữ cảnh, lối đọc theo mục, bộ lọc và thẻ nhất quán;
  giữ toàn bộ ID và các điểm nối JavaScript.
- Thống kê Đặc Biệt bổ sung chế độ theo năm từ lịch sử thực, phân biệt ngày
  thiếu dữ liệu và ngày không tồn tại, xử lý năm nhuận.
- Mọi thay đổi nằm trong source dựng trang, được giữ khi chạy cập nhật ngày.

## Thứ tự thực hiện

1. Rà soát nguồn, hợp đồng màu, shell, thao tác và dữ liệu.
2. Thực hiện song song bốn nhóm độc lập: trang chủ; ma trận/demo; Đặc Biệt
   theo năm; workspace phân tích và thống kê tổng hợp.
3. Dựng lại trang từ dữ liệu hiện tại; đồng bộ stylesheet, shell và dấu phiên
   bản tài nguyên qua luồng xuất chuẩn.
4. Kiểm thử hành vi mới, hồi quy Python/JavaScript và render Chromium ở các
   kích thước điện thoại/máy tính, hai chế độ màu.
5. Rà soát diff, cập nhật main/public theo ủy quyền và kiểm tra CI/Pages.

## Tiêu chí nghiệm thu

Không tràn toàn trang ở 320/390/768/1440 px (ngoại trừ trang cố định desktop);
không lỗi JavaScript hoặc tài nguyên thiếu; số đếm đổi đúng theo range; bộ
lọc năm đúng lịch; căn cứ mở đúng thao tác; chọn số còn hoạt động; mỗi trang
chỉ có một shell. Không sửa mô hình, trọng số, lịch sử, nhật ký dự báo.

Kết quả kiểm chứng thực tế được ghi sau khi tích hợp, không suy từ thiết kế.
