# Kiểm chứng trải nghiệm thống kê ngày 17-10-2026

## Kết quả được đo

| Phạm vi | Bằng chứng |
| --- | --- |
| Frontend | `npm test --prefix tests/frontend`: 182 đạt, không bỏ qua |
| Toàn bộ trang | 50 trang × 320/390/768/1440 px × sáng/tối: 400 trạng thái; không lỗi JavaScript, tài nguyên thiếu hoặc tràn toàn trang; trang desktop cố định được miễn kiểm độ rộng theo hợp đồng cũ |
| Hợp đồng tương tác chung | `check_ui_browser.py`: 200 trạng thái, 0 lỗi |
| Ma trận/lịch | `check_stat_tables_browser.py`: 104 trạng thái, đạt |
| Soi cầu/phôi tuần | `check_bridge_workspace_browser.py`: 72 trường hợp, 0 lỗi |
| Dashboard | `check_dashboard_browser.py`: 28 trạng thái bố cục, đạt |
| Lịch năm mới | 320/390/768/1440 px × sáng/tối: 8 trạng thái; chọn tháng, đủ 12 tháng, lọc, xóa lọc, bộ đếm, cột ngày dính và tương phản đạt |
| Gói tài nguyên | `python src/site_assets.py --root docs --check`: đạt; CSS workspace trên các trang xuất bản khớp source |

Lượt Python toàn kho: **3.799 đạt, 1 bỏ qua, 1 guard CSS báo sai** trong
503,70 giây. Sau khi sửa guard, chạy lại toàn bộ `test_ui_design_system.py`:
**53 đạt**, gồm 16 trường hợp guard mới. CI trên commit `ce83f59` xác nhận
**3.808 Python đạt, 9 bỏ qua** trong 573,60 giây; toàn bộ cổng phát hành lõi,
challenger, Excel và nghiên cứu đều đạt.

CI `39007970894` trên bản sửa phép kiểm `fcbaca9` đạt toàn bộ job: 3.808
Python, 182 frontend và các cổng Chromium, gồm 104 trạng thái ma trận cùng
72 trường hợp Soi cầu. CodeQL và pipeline dựng/triển khai tự động cũng đạt.

## Các luồng đã đối chiếu

- Nhấp đơn chọn số/calculator ngay; nhấp đúp mở căn cứ ở trang chủ và các
  biến thể landing; bàn phím/nhấn giữ và thao tác ở trang khác được giữ.
- Cột thanh xác suất cùng kích thước, ba bảng ngày mai cùng hàng/chiều cao;
  màu số theo điều chỉnh của chủ dự án bên dưới.
- Dọc hiển thị thẻ, Ngang giữ ma trận và virtualization. Kiểm tra số lượt ở
  các dải 30/60/90, dải rỗng/ngắn, chọn họ cặp và lịch sử mở theo nhu cầu.
- Demo tách bộ nhớ khỏi dữ liệu thật, vẫn hoạt động khi storage bị chặn.
- Lịch năm giữ số 0 đầu, năm nhuận, ngày thiếu/ngày không tồn tại và bản ghi
  hợp lệ cuối cùng. Điện thoại xem một tháng; người dùng chọn đủ năm được.
- Workspace bảo toàn ID, script, controls; refine hai lần không đổi byte.
  Phạm vi suy từ điều hướng thật cộng các trang thống kê chi tiết.

## Phát hiện trong nghiệm thu

Review độc lập tìm được lỗi Enter từ vùng ma trận chọn hàng ẩn sau khi lọc
họ cặp. Đã sửa fallback chọn ô hiện và thêm kiểm thử Enter/ArrowDown từ vùng
cuộn sau thao tác Bỏ hết → 12–21. Review lại và 15 kiểm thử tần suất đều đạt.

Guard margin cũ nhận nhầm `body .card` là chính `body`; khoảng cách thẻ 24px
bị báo sai. Guard được kiểm lại theo phần tử đích của selector, giữ chặn
margin 24px trên body và cho phép khoảng cách của thành phần con.

Runner CI phát hiện thêm race trong phép kiểm lịch sử trên thẻ: thao tác mở
`details` đổi `open` trước khi sự kiện `toggle` dựng lịch sử. Đọc số hàng ngay
lập tức có thể thấy 0, sau sự kiện thấy đúng 60. Đã đổi phép kiểm sang chờ
đúng thẻ mở và đúng số hàng bằng Playwright `expect`, giữ các kiểm tra đánh
dấu. Trì hoãn có kiểm soát 250 ms xác nhận điều kiện chờ; tắt renderer vẫn
làm phép kiểm thất bại. Ứng dụng và dữ liệu không đổi trong bản sửa phép kiểm.

Lượt bot Vietlott tiếp theo cho thấy manifest trong git chưa được cập nhật
cùng hai trang nó vừa dựng; gói public vẫn đúng vì được chốt trước upload.
Đã bổ sung chốt trước commit và stage đủ HTML/tài nguyên; giữ chốt sau
rebase trước upload. Kiểm thử chạy shell thật trong kho tạm xác nhận nội
dung đã commit nhất quán, kể cả URL của trang dùng tài nguyên chung. Hai
biến thể bỏ chốt hoặc stage hẹp đều bị kiểm thử bắt lỗi; 14 kiểm thử liên
quan đạt. Pull/push được giả lập nên phép kiểm này không mô phỏng race remote.

Khi bot Vietlott và pipeline XSMB chạy cùng lúc, lượt `39009031543` dựng và
kiểm dữ liệu thành công nhưng xung đột rebase ở riêng `release.json`. Hai bot
đã sinh manifest từ hai ảnh chụp khác nhau. Luồng ghi website được chuyển
sang helper dùng chung: chỉ tái tạo manifest khi đó là tệp xung đột duy nhất,
chốt lại cây mã hợp nhất rồi đẩy fast-forward. Xung đột nội dung khác vẫn
dừng và không ghi đè remote. Các fixture ghi trang dùng bare remote thật để
kiểm cả nội dung đã đẩy, thay cho việc giả lập pull/push.

Review độc lập xác nhận helper; bộ kiểm liên quan gồm ghi trang, tài nguyên,
workflow, cache và thời điểm chốt đạt 126 kiểm thử. Các mutation bỏ chốt sau
gộp sạch, giải xung đột ngoài manifest hoặc nới giới hạn thử lại đều bị bắt.
Bao phủ cả shallow clone và commit sửa manifest trở thành rỗng sau push race.

## Điều chỉnh màu và viền theo chủ dự án

Khôi phục tông xanh dương cũ cho các số và điểm nhấn đã đổi sang xanh ngọc;
bỏ viền và vòng sáng trang trí quanh số. Chọn số dùng nền nhạt, giữ focus
bàn phím. Số vẫn lớn và toàn bộ bố cục/tương tác nâng cấp được giữ.
Kiểm lại 116 Python và 182 frontend: đạt. Chromium 390/1440 px × sáng/tối
trên sáu trang đại diện: 24 trạng thái đạt; nút số có border 0px, không
box-shadow, dùng màu cũ #4F46E5 ở theme sáng, tương phản AA đạt cả hai theme.

Theo yêu cầu tiếp theo, gỡ điểm nhấn nâu mới ở trang chủ và các workspace;
số giải đặc biệt dùng lại đỏ, các chỉ số khác dùng xanh hoặc màu chữ cũ.
Giữ số lớn, chọn nền nhạt, không thêm viền. Kiểm lại 116 Python và 182
frontend đều đạt. Chromium kiểm tám trang × 390/1440 px × sáng/tối: 32
trạng thái đạt, tương phản AA, không tràn trang hoặc lỗi JavaScript; chọn
số không viền, nhấp đúp và hai chiều tần suất hoạt động. Lượt đo hình học
dùng giảm chuyển động để đọc vị trí ổn định sau khi mở ngăn căn cứ.

## Dựng và vận hành

Dựng landing, statistics, các trang thống kê chi tiết; chèn mô phỏng bằng
payload và ledger hiện có qua `inject_into_html`, không ghi lại ledger. Sau
đó chạy `scripts/ops/refresh_navigation.py` để đồng bộ toàn site và chốt dấu
phiên bản tài nguyên. Không thay lịch sử kết quả, mô hình, trọng số hoặc sổ
dự báo trong đợt giao diện này. Các thay đổi nằm trong source nên được giữ
qua các lần cập nhật dữ liệu tự động.
