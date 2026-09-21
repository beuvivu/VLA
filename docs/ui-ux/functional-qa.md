# QA chức năng

Mục XVI của spec: *"A screenshot alone is not proof that a page works."* Nên
mỗi mục dưới đây là một phép ĐO hoặc một TƯƠNG TÁC thật, không phải ảnh chụp.

## Điều khiển

| Điều khiển | Cách kiểm | Kết quả |
|---|---|---|
| Nút đổi chủ đề | Bấm 3 lần, đọc `data-theme-state` VÀ `getComputedStyle(body).backgroundColor` | Xoay đúng `system → light → dark → system`; màu nền THẬT SỰ đổi |
| Trạng thái "theo hệ thống" | Mở với `color_scheme` light và dark | Màu khác nhau — tầng `prefers-color-scheme` hoạt động |
| Nút mở điều hướng | Bấm, đo vị trí sidebar sau transition | Mở đúng dưới 1024px, ẩn từ 1024px |
| Đóng bằng Esc | Gửi `keydown` Escape | Đóng, `aria-expanded=false`, nhả `inert` và khoá cuộn |
| Nhóm điều hướng | `<details>`/`<summary>` | Mở/đóng bằng bàn phím sẵn, không cần JS |
| Liên kết bỏ qua điều hướng | `focus()` rồi đo vị trí | Là phần tử bấm được ĐẦU TIÊN; hiện ra khi focus; đích tồn tại |
| Cuộn ngang trong bảng | Đặt `scrollLeft` rồi đọc lại | Cuộn thật, không phải chỉ "nội dung rộng hơn" |

## Dữ liệu

| Kiểm | Kết quả |
|---|---|
| Console JavaScript | 0 lỗi trên 29/29 trang |
| Tài nguyên tải lỗi | 0 trên 29/29 trang |
| Trang đọc dữ liệu thật | 29/29; không trang nào dùng dữ liệu minh hoạ |
| Mỗi trang ghi nguồn dữ liệu | 29/29 |
| Bảng xác suất có cột đường cơ sở | 8/8 trang, giá trị kiểm bằng SỐ |
| Trạng thái rỗng khi dữ liệu thật sự rỗng | `soi-path-de-active.html` — đúng |

## Đối chiếu số liệu với nguồn

Kiểm tay trang `so-ket-qua-truyen-thong.html`, kỳ 2026-09-21:

- Giải Đặc Biệt hiển thị `40432`; `data/xsmb.csv` ghi `40432`. Khớp.
- Bảng Chục, hàng `3` hiển thị `0 1 2 2 2 2`. Sáu ô giải có hàng chục là 3:
  32 (Đặc Biệt), 31, 30, 32, 32, 32 → đơn vị `{2,1,0,2,2,2}` sắp lại là
  `0 1 2 2 2 2`. Khớp.
- Bảng Đơn vị, hàng `7` hiển thị `—`. Không ô giải nào của kỳ này kết thúc
  bằng 7. Khớp — và dấu gạch là trạng thái rỗng thật, không phải số 0 bịa.

## Bất biến nội dung — thứ dễ mất nhất

| Bất biến | Vì sao |
|---|---|
| Mọi trang phân tích mang khối cảnh báo | Kho đã quét 824 328 giả thuyết, 0 sống sót sau FDR. Câu cảnh báo là kết luận ấy nói thành lời |
| Bảng xác suất LUÔN có cột đường cơ sở | Lô tô cơ sở 23,766%; một con "top 10" ở 23,887% hơn đúng 0,12 điểm. Bỏ cột đi thì con số trông như phát hiện |
| Đường cơ sở đủ 3 chữ số thập phân | Ở Đặc Biệt, 1,00% so với 1,01% không phân biệt được ở 2 chữ số — cột mất công dụng |
| Mục đang mở trỏ ĐÚNG trang đang xem | Đếm số mục là chưa đủ: khai nhầm `nav_key` vẫn đánh dấu đúng một mục, chỉ là của trang khác |
