# Đặc tả rà soát giao diện VLA — 2026-09-15

## Mục tiêu

Đưa chín trang được rà soát về cùng Master Design System của VLA: Soft Modern UI, Bento có thứ bậc rõ, mật độ dữ liệu cao nhưng không dàn trải, bảng không phá container, dock/footer không che nội dung và responsive ổn định trên desktop/mobile.

## Phạm vi

1. `live.html`: giữ ưu tiên realtime và trạng thái nguồn; chỉ tinh chỉnh nếu khác nhịp thiết kế chung hoặc dock/footer thiếu khoảng an toàn.
2. `bang-dac-biet.html`: bảng tuần phải giãn đều hết chiều rộng card/box trên desktop, nhưng vẫn cuộn an toàn ở màn hình nhỏ.
3. `lo-gan.html`: thiết kế lại bố cục; không xếp liên tiếp các bảng dài. Dữ liệu chi tiết phải nằm trong các panel Bento có chiều cao hữu hạn, header sticky và cuộn nội bộ.
4. `dau-duoi-loto.html`: thiết kế lại thành dashboard phân bố; hai bảng Đầu/Đuôi cân bằng, ba bảng 20 kỳ gần nhất nằm trong lưới responsive thay vì xếp dọc kéo dài trang.
5. `giai-dac-biet-theo-tong.html`: khắc phục vỡ layout/overflow; các khối chuyển tổng và chẵn-lẻ phải nằm trong container có giới hạn và co giãn đúng.
6. `soi-path-loto-active.html`: đồng bộ giao diện với thiết kế chính; bảng đường cầu phải có vùng cuộn riêng và dock không chồng nội dung.
7. `soi-path-de-active.html`: sửa triệt để lỗi menu/dock footer tràn hoặc che nội dung; dùng cùng template với các trang soi cầu để không tạo nhánh CSS riêng.
8. `dashboard.html`: nâng thành AI/ML command center dạng Bento, làm nổi bật tín hiệu kỳ kế tiếp, dữ liệu mới nhất, khối mô hình và calibration; không làm mất dữ liệu gốc.
9. `research-lab.html`: tạo cảm giác Research Lab thực sự bằng pipeline nghiên cứu, research firewall, trạng thái thí nghiệm/kiểm định và các instrument panel; giữ nguyên tính thận trọng khoa học.

## Ràng buộc hệ thống

- `assets/ui.css` vẫn là stylesheet nền chuẩn; không khôi phục `assets/vla.css`.
- Không sửa trực tiếp HTML sinh ra nếu có builder/template nguồn tương ứng.
- Không cắt bỏ dữ liệu để làm trang ngắn hơn; dùng phân cấp thông tin, lưới Bento, scroll nội bộ, sticky header và progressive disclosure.
- Dock dùng chung phải còn hoạt động với touch/keyboard và không chặn footer/nội dung.
- Không thay đổi thuật toán thống kê, xác suất, ML hoặc ngữ nghĩa dữ liệu trong đợt UI này.
- Các trang phải hoạt động ở light/dark theo quy ước hiện tại; riêng live/path có thể giữ palette tối chuyên dụng nếu vẫn ánh xạ đúng token dùng chung.
- Các thay đổi phải được khóa bằng test cấu trúc để pipeline build lại hằng ngày không làm mất thiết kế.

## Nguyên nhân đã xác minh từ mã nguồn

- Bốn trang thống kê cùng sinh từ `src/build_stat_pages.py`; `src/templates/stat_pages.css` đang dùng `.sp-scroll { width: fit-content; }` và `.sp-table { width: auto; }`, phù hợp bảng xếp hạng hẹp nhưng không phù hợp mọi bảng lịch/ma trận.
- `lo-gan.html` hiện render toàn bộ bảng 100 số, hai bảng gan cực đại 50+50 và bảng 50 cặp theo chiều dọc, tạo chiều cao trang quá lớn.
- `dau-duoi-loto.html` xếp ba bảng 20 kỳ gần nhất nối tiếp theo chiều dọc.
- Template `src/templates/path_ui_page.html.j2` gắn dock dùng chung nhưng `<body>`/wrapper chưa dùng vùng đệm dock chuẩn; đây là nguyên nhân cấu trúc của lỗi dock/footer che nội dung ở `soi-path-de-active.html`.
- `dashboard.html` và `research-lab.html` có builder riêng, vì vậy phải chỉnh tại builder để pipeline tái sinh đúng giao diện.
