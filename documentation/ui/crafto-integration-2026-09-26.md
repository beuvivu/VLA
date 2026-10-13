# Crafto Application × giao diện thống kê

## Mục tiêu và phạm vi

Theo yêu cầu ngày 26/09/2026: kết hợp ngôn ngữ giao diện Crafto vào toàn bộ
ứng dụng hiện tại, dùng nền và chuyển động Application làm nhận diện trang chủ.
Giữ điều hướng Nexlink hai tầng, chức năng thống kê, dữ liệu, bộ lọc và miền số.
Quyền chủ động thiết kế/triển khai đã được chủ dự án cấp ở các phiên liên quan.

## Tham chiếu đã kiểm tra

- https://craftohtml.themezaa.com/ — danh mục thành phần và hiệu ứng.
- https://craftohtml.themezaa.com/demo-application.html — kiểm tra trực tiếp DOM,
  hình render, thẻ tính năng và chuyển động chuột/cuộn ngày 25/09 UTC.
- Application: nền trắng với mảng coral/hồng/tím, 12 hạt màu trôi sang phải,
  không phản ứng hover/click; chữ nền 250px chạy ngang; vào trang theo lớp;
  lớp trang trí parallax; nút viên thuốc; bóng thẻ 0 20px 60px đen 8%.
- Màu nguồn: coral #fd6f63, ink #2c2e3c; cursor nguồn rgba(44,46,60,.15); bản tích hợp dùng sắc coral đồng bộ hero.
  Inter tự lưu trong dự án tiếp tục dùng để hiển thị tiếng Việt ổn định.

## Thiết kế

1. Một lớp CSS cuối cùng `app-design.css` thống nhất bề mặt, viền, bo góc,
   nút, nhãn, icon và tiêu đề. Giữ hình học rail/header 80px, panel 240px.
   Giữ nguyên màu mang nghĩa của số liệu, ma trận và biểu đồ.
2. `app-effects` là lớp trang trí độc lập, không chặn chuột. Nền toàn ứng dụng
   nhẹ; hero landing có gradient rực hơn, quỹ đạo và thẻ kết quả từ dữ liệu thật.
3. Trang chủ có tiêu đề thống kê, liên kết đến chức năng thật, marquee
   “Vietnam Lottery Analysis”, dữ liệu ngày gần nhất. Không tạo số minh họa giả.
4. `app-motion.js` phụ trách cursor, parallax nhẹ, xuất hiện khi cuộn,
   tạm dừng hiệu ứng và ghi nhớ lựa chọn. Không thêm framework.
5. Nút tắt chuyển động luôn dùng được bằng bàn phím; giảm chuyển động theo OS;
   không chạy cursor trên thiết bị cảm ứng, không giấu con trỏ gốc.
   Dừng animation khi tab ẩn; nội dung vẫn đầy đủ khi JavaScript không chạy.

## Hợp đồng kết nối

- Body: `data-app-design="crafto"`; runtime đặt `data-app-motion="on|off"`.
- `.app-ambience` chứa `.app-orb` và `.app-particle`, aria-hidden, không focus.
- `.app-cursor` đọc CSS `--app-pointer-x/y`; không đè tương tác.
- `#app-motion-toggle`: aria-pressed=true nghĩa là hiệu ứng đang bật.
- `[data-app-reveal]`: runtime thêm `.app-is-revealed`, không giấu nội dung mặc định.
- `[data-app-parallax]`: transform theo `--app-parallax-x/y` trên wrapper trang trí.
- `.app-marquee-track`: hai bản sao aria-hidden, thương hiệu vẫn có trong header.
- `.app-feature-link`, `.app-hero-copy`, `.app-hero-visual` thuộc hero landing.
- Tất cả tài nguyên từ assets nội bộ; output qua `write_page`, lũy đẳng.

## Kiểm chứng

Kiểm tra bảo toàn payload và móc tương tác; xuất bản tài nguyên; chạy lại output
không lồng shell; JS tắt/bật/reduced-motion/storage bị chặn; kiểm tra menu,
bộ lọc và số; render desktop và mobile; không tràn ngang hay che nội dung.
PR91 đang được xử lý trong phiên khác: tái đồng bộ main trước tích hợp,
không ghi đè các cải tiến điều hướng và phân tích mới.

Yêu cầu bổ sung cùng ngày chuyển toàn bộ bề mặt sang theme tokens, chuẩn hóa
SVG Lucide và tách hai tìm kiếm; xem đặc tả
`../superpowers/specs/2026-09-26-theme-search-icons-design.md`.
