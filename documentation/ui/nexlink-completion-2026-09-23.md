# Hoàn thiện khung Nexlink — 23/09/2026

## Phạm vi

Bản sửa bắt đầu từ `239fc4e7`, đầu nhánh Claude của PR #87, đã gồm `main` tại `e563febc`. Giữ bộ biểu tượng SVG và các sửa khoảng trống của Claude. Nguồn đối chiếu: `https://nexlink.layoutdrop.com/demo/index.html`.

Dải icon 80 px, panel 240 px và header 80 px tiếp tục dùng hình học chung. Logo trở về đúng vị trí trên dải icon; header có tìm kiếm, chế độ màu, liên kết sổ kết quả, chất lượng mô hình và toàn màn hình khi trình duyệt hỗ trợ. Các điều khiển đều gắn vào chức năng có thật của ứng dụng.

Card dùng bo 10 px, viền mảnh và bóng nhẹ; bỏ chuyển động nâng bảng khi hover. KPI dùng hàng 6/3/2 cột phù hợp bề rộng, tránh hàng cuối chỉ còn một thẻ. Nền chuyển sắc riêng của trang chủ được giữ; các trang dữ liệu dùng nền trung tính. Màu ô dữ liệu và cấu trúc bảng không thay đổi.

## Lỗi đã sửa

- Bộ xuất chỉ nhận `.ui-dock`, bỏ sót `.dock` và thứ tự thuộc tính khác: dock cũ vẫn hiện cùng khung mới.
- Breadcrumb lấy nhãn của neo cuối cùng trỏ đến `index.html`, khiến trang chủ hiện “Kiểm định AI/ML”.
- Tất cả neo trong trang chủ cùng nhận `aria-current=page`; hai địa chỉ landing lại không có mục đang chọn.
- Menu đang đóng vẫn cho bàn phím đi vào; menu điện thoại không khóa vùng nội dung bên dưới.
- Tìm kiếm có dấu mới khớp; đổi nhóm sau khi tìm giữ lại các mục bị ẩn.
- Sau điều hướng đến neo, kết quả tìm ở nhóm khác biến mất dù ô nhập không đổi.
- Bỏ dock làm mất 12 liên kết nhảy nhanh: chuyển chúng vào “Trên trang này” trong panel.
- Mốc `main` lồng nhau: giữ một mốc, bảo toàn id/lớp/nội dung; vùng thống kê dùng lớp `.statistics-content` thay selector thẻ.
- CodeQL phát hiện thao tác xóa thẻ bằng regex trong hàm `asPair` dùng chung của 14 trang. Các nơi gọi đều truyền dữ liệu số thuần; bỏ thao tác xóa thẻ, giữ kiểm tra định dạng số nghiêm ngặt và thêm kiểm thử từ chối markup.

## Kiểm chứng

- So sánh 29 trang trước/sau: toàn bộ bảng, JSON nhúng và id phân tích giữ nguyên.
- Bộ xuất chạy lại không làm thay đổi trang lần nữa.
- Bảy kiểm tra Python mới đã thất bại trước khi sửa và đạt sau khi sửa.
- Bảy kiểm tra JavaScript đầu tiên đều thất bại với script gốc; bản sửa đạt, cộng thêm kiểm tra neo sau rà soát độc lập.
- Kiểm thử JavaScript dùng DOM thực từ trang xuất bản: `npm ci --prefix tests/frontend && npm test --prefix tests/frontend`. Đã bổ sung vào CI.
- Bộ kiểm tra Python: `PYTHONPATH=src python -m pytest tests -q`.
- Bản trước sửa `asPair`: toàn bộ Python đạt 1.927, bỏ qua 8 theo môi trường. Sau sửa: 166 kiểm tra thống kê/bảo mật/tài nguyên đạt; JavaScript đạt 9/9. CI chạy lại trên commit cuối.

## Giới hạn xác minh trực quan

Đã quan sát trang Nexlink và VLA đang chạy bằng trình duyệt. Trình duyệt phiên này không cho mở localhost hoặc tệp nội bộ nên chưa xác minh trực quan bản sửa ở desktop/mobile. Các phép kiểm Chromium hiện có cũng bỏ qua khi không có Chromium tại đường dẫn đã ghim. Kiểm tra DOM không được tính là kiểm tra bố cục hay cảm ứng thật.

Một số trang dữ liệu vốn chỉ hỗ trợ nội dung sáng, còn khung hỗ trợ ba trạng thái màu. Bản sửa này không đổi hợp đồng màu dữ liệu của những trang đó. Không coi việc đổi màu header là bằng chứng toàn bộ bảng đã hỗ trợ chế độ tối.
