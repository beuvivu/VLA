# Kiểm chứng sáu trang thống kê, 25-10-2026

Phạm vi theo [kế hoạch](../plans/2026-10-25-readable-stat-pages.md): sửa lịch sử Đặc Biệt hôm sau, làm rõ hai bảng Top 10 ML và cầu vị trí, thêm màu xếp hạng số đường cầu trên hai trang LOTO.

## Hành vi đã đối chiếu

- Đặc Biệt hôm sau mặc định số cuối kỳ mới nhất, liệt kê các lần trùng hai số cuối từ mới đến cũ, giữ đủ năm chữ số. Kết quả bên cạnh thuộc đúng ngày lịch kế tiếp; ngày thiếu không được thay bằng kỳ có dữ liệu sau đó. Chỉ kết quả kế tiếp đã biết được đưa vào mẫu số tần suất. Dữ liệu thật: 26/09/2026 có 18132, ngày 27/09/2026 có 55473; 24/10/2026 có 45932 và kết quả hôm sau đang chờ.
- Hai trang ML giữ nguyên mười số, thứ tự, số 0 đầu, toàn bộ xác suất và bằng chứng JSON so với `origin/main` tại 9daca67; chỉ bố cục thay đổi. Ngày dự báo, mức tin và chuyển loại luôn nhìn thấy. Mỗi bằng chứng vẫn mở bằng bàn phím và đóng bằng Escape.
- Cầu vị trí giữ luật, 107 vị trí chữ số và tham số URL. Luồng ba bước cho phép lọc cặp số, chọn cầu rồi xem từng kỳ; nhãn vị trí ghi rõ giải/chữ số. Liên kết cầu đang chọn hiện rõ cả khi URL chưa có hash.
- Màu LOTO dùng số đường cầu của từng số, độc lập với cặp đảo. Ví dụ đếm 20,20,12,9,8,7 cho các số khác nhau tạo hạng 1,1,2,3,không màu,không màu. Mức 7 không đủ điều kiện, mức 8 có thể vào hạng; chỉ ba mức đếm cao nhất được tô. Đổi bộ lọc tính lại màu. Các kiểu cầu khác không nhận màu hay chú giải mới.
- Màu là số đường cầu, không phải xác suất dự báo. Bộ lọc hai nháy mặc định hiện chưa có số nào trên 7 cầu, nên bảng không ép tạo màu. Đổi độ dài tối thiểu còn một kỳ tạo đủ mẫu để kiểm ba màu thực tế.

## Kiểm tra trên trình duyệt

Chromium 153 chạy bản HTML dựng từ nguồn cuối, không sửa tay tệp xuất bản.

| Kiểm tra | Kết quả |
| --- | --- |
| Sáu trang × 390/768/1440 px × sáng/tối | 36 trạng thái, không lỗi JavaScript, không tràn ngang toàn trang |
| Tương tác bốn trang thiết kế lại × 390/1440 px | 8 trường hợp đạt |
| Hai trang màu × 390/1440 px × sáng/tối | 8 trường hợp đạt |
| Tương phản ba màu ở hai chế độ | Tất cả đạt ít nhất 4,5:1 |
| Rê chuột, focus và chọn số có hạng | Giữ nền hạng, thêm viền chọn |

Đã xem ảnh desktop/mobile, sáng/tối; ma trận rộng cuộn trong khung riêng. Kiểm tương tác chọn số Đặc Biệt, trở về số mới nhất, dải 30/toàn bộ; mở bằng chứng ML; lọc/chọn đường cầu, chế độ Đặc Biệt; đổi số kỳ để tạo/xóa màu cầu.

## Kiểm thử tự động

- 405 kiểm thử Python liên quan đạt trên nguồn cuối, gồm trình dựng trang, lịch sử Đặc Biệt, trình bày ML, hai loại cầu và danh mục bằng chứng.
- Toàn bộ 238 kiểm thử frontend Node đạt.
- Ruff trên tất cả tệp Python thay đổi và `git diff --check` đạt.
- Các kiểm thử mới đã thất bại trước khi sửa. Đột biến lấy kỳ có dữ liệu kế tiếp thay vì ngày lịch kế tiếp, đảo thứ tự lịch sử, sai ngưỡng 7/8, phá đồng hạng, bỏ cập nhật màu theo bộ lọc và mở màu sang trang khác đều bị kiểm thử bắt.
- Review độc lập đối chiếu dữ liệu ML, thuật toán ngày kế tiếp, hợp đồng URL cầu và phạm vi màu.

Baseline: 168 kiểm thử liên quan đạt trước thay đổi. Tài nguyên khung trang dùng chung, trang chủ, dữ liệu quay và mô hình ML được giữ nguyên.
