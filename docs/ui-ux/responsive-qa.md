# QA responsive

Công cụ: Chromium 1194 qua Playwright. Không kết luận nào rút ra từ việc đọc
`@media` — mục X cấm.

## Phạm vi đo

30 trang (29 trang sản phẩm + 1 trang QA khung) × 7 viewport × 2 chủ đề =
**420 lượt kiểm**.

| Thiết bị | Viewport | Tràn ngang |
|---|---|---|
| Small Mobile | 320px | 0/60 |
| Mobile | 375px | 0/60 |
| Large Mobile | 430px | 0/60 |
| Tablet | 768px | 0/60 |
| Small Laptop | 1024px | 0/60 |
| Desktop | 1440px | 0/60 |
| Large Desktop | 1920px | 0/60 |

**Tổng: 0/420 ca tràn ngang.**

## Lỗi responsive đã tìm ra và sửa

| Lỗi | Viewport | Nguyên nhân |
|---|---|---|
| Nút ba gạch vẫn hiện | 1024px+ | `.vla-btn { display: inline-flex }` khai SAU khối `@media`; cùng độ đặc hiệu thì luật sau thắng |
| Liên kết điều hướng 39px | mọi viewport | Thiếu đúng một pixel so với ngưỡng vùng chạm 40px |
| Số KPI xuống hai dòng | **đúng 1024px** | 4 cột bật ở 1024px nhưng sidebar ăn 264px → thẻ 159px; chiều cao nhảy 143→181px |
| Trang tràn ngang 353px | **chỉ 320px, chỉ 1 trang** | Tên tệp `conditional_special_after_special_top500.json` rộng 337px, không có chỗ ngắt |
| 4 thẻ KPI xếp dọc ~580px | 320–768px | Lưới một cột áp máy móc cho mọi thứ |
| Mốc 380px loại 375px | 375px | Mốc đầu chọn sai, loại đúng hạng thiết bị phổ biến nhất |

## Hai sai sót trong chính phép đo

**Đo trong lúc transition còn chạy.** Đo ngay sau `click()` và `focus()` trong
khi transition 120–180ms chưa xong, nên báo sai là drawer "không mở" và liên
kết bỏ qua "vẫn ẩn". Đã thêm `waitTransition`.

**Đo sai đại lượng.** Kiểm `scrollWidth` cho ô KPI và thấy "không tràn" nên
tưởng ổn — con số không tràn ngang vì nó *xuống dòng* được. Phải ĐẾM SỐ DÒNG.
Đo sai đại lượng thì kết luận đúng cũng là tình cờ.

## Hành vi mobile đã kiểm bằng tương tác thật

| Kiểm | Kết quả |
|---|---|
| Drawer mở bằng nút ba gạch | đạt |
| Nền mờ hiện, nội dung sau đặt `inert` | đạt |
| Focus chuyển vào drawer khi mở | đạt |
| Vòng focus giữ Tab trong drawer | đạt |
| Esc đóng drawer, nhả `inert` và khoá cuộn | đạt |
| Kéo rộng qua 1024px tự đóng drawer | đạt |
| Mọi nút và liên kết ≥ 40px chiều cao | đạt |
| Sidebar KHÔNG chiếm màn hình khi chưa mở | đạt |
