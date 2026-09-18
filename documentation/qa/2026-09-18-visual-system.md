# Đồng bộ giao diện toàn bộ trang

Mục tiêu: áp dụng thiết kế Soft Modern UI đã được yêu cầu lên 29 trang công khai,
giữ nguyên dữ liệu, ID, class, bộ lọc và JavaScript.

## Kế hoạch thực hiện

- Kiểm kê toàn bộ `docs/*.html` và các bộ dựng tương ứng.
- Thêm stylesheet cuối cùng tại `page_output.write_page`, dùng tài nguyên cùng nguồn.
  Chỉ trang HTML hoàn chỉnh nhận stylesheet; ghi lại nhiều lần không nhân bản liên kết.
- Tạo `src/templates/ui_visual_system.css`: khung 1280px, khoảng cách 8px,
  bề mặt kính mờ, bảng cuộn nội bộ, trạng thái focus và giảm chuyển động.
- Sửa màu dữ liệu ở stylesheet thống kê nguồn; ô dữ liệu và chú giải dùng cùng màu.
- Dựng lại trang, kiểm tra hợp đồng HTML/JS, chạy kiểm thử hồi quy và kiểm tra trình duyệt.
- Push, tạo PR và merge sau khi kiểm tra đạt theo ủy quyền hiện có.

## Phát hiện ban đầu

| Vấn đề | Bằng chứng | Cách xử lý |
| --- | --- | --- |
| Chiều rộng không thống nhất | Landing 1600px, tần suất 1440px, trang chi tiết 1280px | Một token 1280px cho các khung chính |
| Nền trang không đồng nhất | Statistics có gradient xanh/cam đậm, trang khác nền tím nhẹ | Gradient ba chặng tím nhạt dùng chung |
| Bảng tuần khó phân biệt ô trống | Ô trống trắng, ô có dữ liệu cũng trắng | Nền trống xám, viền ô có dữ liệu; giữ căn giữa cả bảy cột |
| Màu nháy chói | `stat_pages.css` còn `#FFFF00` | Palette pastel có chữ tương phản, đồng bộ chú giải |
| Chữ nhỏ tần suất nhạt | Nhãn và trạng thái dùng màu xám tím nhạt | Tăng tương phản nhãn và trạng thái |
| Nhiều kiểu thẻ | Radius, viền, bóng riêng theo bộ dựng | Thẻ 20px, viền mảnh và bóng nhiều lớp |

## Kiểm chứng

- Đối chiếu với `main` tại `834aafe2bdc16f57ea95fad987a6ced4c29c679f`:
  toàn bộ 29 trang giữ nguyên ID, class và JavaScript; mỗi trang chỉ có một
  liên kết tới stylesheet chung.
- Toàn bộ kiểm thử: **2.122 passed, 1 skipped**, 279,12 giây. Kiểm thử trình
  duyệt bị bỏ qua vì không có Chromium; 28 cảnh báo đến từ thư viện và hiệu năng
  DataFrame, không phải lỗi kiểm thử.
- Sau sửa cuối: **223 kiểm thử UI đạt**; **24 kiểm thử** cho feature attribution,
  model quality và stationary rate đạt. `ruff check src tests`, `compileall`
  và `git diff --check` đều đạt.
- Rà soát độc lập phát hiện CSS mặc định đè màu tiêu đề cột đang được rê chuột.
  Đã loại `.col-hint` khỏi selector mặc định và đồng bộ asset đã xuất bản;
  rà soát lại xác nhận trạng thái đánh dấu được giữ nguyên.
- Sửa 7 lỗi lint sẵn có trong phần mã mới từ main. Giữ nguyên bước tiêu thụ
  RNG để không đổi kết quả bootstrap đã cố định seed; thêm `strict=True` cho
  các phép zip có độ dài bằng nhau và bỏ import không dùng.
- Giới hạn: chưa thực hiện kiểm tra ảnh chụp/responsive bằng trình duyệt trong
  lượt này. Môi trường thiếu Chromium và tải bản cài đặt bị timeout. Kết quả
  kiểm thử cấu trúc không thay thế việc kiểm tra trực quan này.
