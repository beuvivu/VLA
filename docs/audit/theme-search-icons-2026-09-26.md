# Hoàn thiện giao diện sáng/tối, tìm kiếm và SVG — 26-09-2026

## Phạm vi

Tiếp tục nhánh `codex/crafto-design-system-20260926` trên `c0033bb`.
Giữ khung Nexlink, nội dung 29 trang và phần landing Crafto đã làm trước đó.
Không đổi dữ liệu, mô hình hoặc thuật toán thống kê.

- Bỏ các khối ghim sáng trên body; nền, chữ, viền, thẻ, bảng, modal và trạng
  thái dữ liệu kế thừa token chung. Runtime đồng bộ `.dark`, lựa chọn đã lưu,
  hệ điều hành và thay đổi từ tab khác trước khi tải CSS.
- SVG Lucide chính thức tự host, giữ giấy phép/provenance; 20px, lưới24,
  stroke2, currentColor; menu và header dùng cùng hệ thống.
- Header mở dialog Ctrl/Cmd+K phủ toàn bộ đích điều hướng. Sidebar chỉ lọc
  nhóm hiện tại. Hai ID, truy vấn và trạng thái độc lập, hỗ trợ tìm không dấu,
  bàn phím, empty state, đóng và trả focus.
- Trạng thái chọn số/cặp dùng màu nhấn và viền rõ, không bị skin ghi đè.

## Kiểm chứng trước PR

- Python: 2.216 đạt, 7 bỏ qua; không có lỗi.
- JavaScript: 41 đạt, gồm ba hồi quy mới cho API media bị chặn.
- Kiểm asset xuất bản và workflow sau sửa: 28 đạt; lint E9/F63/F7/F82 đạt.
- Review độc lập phát hiện API `matchMedia` hoặc đăng ký listener ném lỗi có
  thể dừng khởi tạo. Ba kiểm thử tái hiện thất bại trước sửa; sau sửa đều đạt.
- Reviewer xác nhận shell lũy đẳng, không trùng app-ID, asset khớp nguồn và
  cascade của nút chọn số/cặp đúng. Không còn finding chắc chắn khác.
- So JSON nhúng trên 29 trang: chỉ khác timestamp dựng. Dữ liệu nguồn và
  thuật toán không đổi. Bảng top 10 đường cầu Đặc Biệt trên landing có một
  hàng ở ngưỡng hòa điểm đổi từ 39/L11 sang 06/L9; cả hai cùng điểm 12.8627,
  xác suất 0.01412714 và 27/1980, đều có trong CSV nguồn. Không coi đây là
  bằng chứng mọi số hiển thị giống từng byte với HTML cũ.

## Cổng trình duyệt và phát hành

`scripts/check_ui_browser.py` chạy Chromium trên HTML thật, toàn bộ 29 trang
ở 390px/1440px, light/dark, kiểm overflow, một shell, theme header, dialog,
empty state, hai truy vấn đồng thời và lỗi JavaScript. Lưu report và ảnh
trong artifact `ui-browser-review`. Bản desktop cố định có chủ đích được
loại khỏi phép kiểm overflow ở màn hẹp.

Trình duyệt cloud không truy cập được localhost của workspace; dùng cổng CI
cho bản chưa phát hành, sau merge kiểm trực tiếp trang public. Chỉ merge
sau khi các cổng của commit được thông qua. Trạng thái CI/merge được ghi ở PR.

## Tiếp tục và tích hợp phần còn dở của PR91

- Đối chiếu PR91 phát hiện bản mới còn thiếu cơ chế bóc khung đã chuẩn hóa
  thứ tự thuộc tính và một phần dọn dock cũ. Không đóng PR91 như đã hoàn tất
  trước khi hòa các delta này vào cùng nhánh.
- Đóng menu bằng nền phủ hoặc thu cửa sổ phải đưa focus ra trước khi vùng
  chứa nó trở thành `inert`/`aria-hidden`. Tránh giành focus khi phần tử đang
  dùng vẫn còn thao tác được. Tooltip toàn màn hình đồng bộ cả lúc vào/thoát.
- Dock cũ nghỉ ở nguồn dựng, stylesheet và tài nguyên đã xuất bản. Giữ mẫu
  lịch sử trong fixture để kiểm tra sửa khung lồng mà không tái sinh dock.
- Trang thống kê dùng token sáng/tối cho hero và giữ anchor nội dung; gỡ
  hướng dẫn dành cho người phát triển khỏi phần hiển thị sản phẩm.
- Bộ kiểm Chromium bổ sung xác nhận focus native sau Escape/nền phủ và ảnh
  trang thống kê. Kết quả cuối của bản hợp nhất được ghi trong PR.

Bản trước phần cleanup đạt 2.216 Python, 7 bỏ qua; 116 trạng thái Chromium
ở 390/1440px, sáng/tối không lỗi. Bộ frontend sau sửa focus và fullscreen
đạt 47/47. Các mutation bỏ chuyển focus, chuyển sau `inert`, giành focus vô
điều kiện hoặc bỏ cập nhật tooltip đều làm kiểm thử tương ứng thất bại.

## Chốt bản tiếp tục ngày 26-09-2026

- Bộ Python chạy lại: 2.227 đạt, 7 bỏ qua, 14 cảnh báo hiệu năng pandas;
  các kiểm tra cú pháp/lint và diff whitespace đạt.
- Review cuối phát hiện nhánh không đọc được `matchMedia` có thể để CSS tối
  nhưng nút báo sáng. Kiểm thử mới tái hiện thất bại trước sửa; runtime dùng
  màu sáng dự phòng trong tab khi không đọc được OS, không ghi lựa chọn giả
  vào storage. Lựa chọn đã lưu và chế độ OS bình thường vẫn giữ nguyên.
- Frontend sau sửa: 49/49 đạt. Bộ hồi quy theme/asset/cleanup: 30/30 đạt.
- Review độc lập xác nhận 29 trang bọc lại lũy đẳng, 7 asset khớp nguồn và
  42 SVG khớp SHA trong manifest. Không sửa `data/` hoặc `models/`.
- CI, Chromium trên commit cuối và trạng thái phát hành được ghi ở PR.
