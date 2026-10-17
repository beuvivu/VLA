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
**53 đạt**, gồm 16 trường hợp guard mới. CI chạy lại toàn bộ trên commit xuất
bản; lượt local ban đầu không được ghi nhận là toàn bộ xanh.

## Các luồng đã đối chiếu

- Nhấp đơn chọn số/calculator ngay; nhấp đúp mở căn cứ ở trang chủ và các
  biến thể landing; bàn phím/nhấn giữ và thao tác ở trang khác được giữ.
- Cột thanh xác suất cùng kích thước, ba bảng ngày mai cùng hàng/chiều cao;
  số chính emerald/amber, không dùng màu điều hướng làm thang dữ liệu mới.
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

## Dựng và vận hành

Dựng landing, statistics, các trang thống kê chi tiết; chèn mô phỏng bằng
payload và ledger hiện có qua `inject_into_html`, không ghi lại ledger. Sau
đó chạy `scripts/ops/refresh_navigation.py` để đồng bộ toàn site và chốt dấu
phiên bản tài nguyên. Không thay lịch sử kết quả, mô hình, trọng số hoặc sổ
dự báo trong đợt giao diện này. Các thay đổi nằm trong source nên được giữ
qua các lần cập nhật dữ liệu tự động.
