# Kiểm chứng Cặp lộn và các bảng Đặc Biệt, 18-10-2026

## Phạm vi thay đổi

- Cặp lộn: bảng 45 cặp và 10 số kép song song từ 1024px, khung hẹp xếp dọc;
  cặp số / số kép lớn hơn hạng và các tham số. Giữ đủ 45 cặp đảo thật và 10 số kép.
- Bảng Đặc Biệt tuần: khóa dấu ô theo tuần/ngày, giữ đúng kỳ khi lọc.
- Cầu giải Đặc Biệt: số ma trận / cặp lộn giữ 24px khi chọn, hiện đủ mười
  hàng và 100 số, không cuộn dọc trong ma trận. Nhãn Đầu và số lượt nhỏ hơn.
- Theo tổng: gan và chẵn/lẻ song song trên máy tính, bảng chuyển tổng bên
  dưới; chia lại cột, dùng cùng tông xanh và ưu tiên chữ số tổng.

Các phép tính, dữ liệu quay, mô hình và sổ cái được giữ nguyên. Đã tiếp nhận
hai lượt cập nhật tự động trên main, gồm analytics và Vietlott, trước khi
chốt lại gói giao diện. Mười bốn trang dùng chung mã đánh dấu được dựng qua
`page_output.write_page`; không sửa tay bản HTML riêng lẻ.

## Lỗi đã tái hiện và sửa

1. Chọn riêng một ô rồi chọn cả cặp từ ô khác để lại hai dấu chồng nhau;
   bỏ chọn từ ô đầu bị kẹt. Dấu riêng được hợp nhất khi chọn cả cặp.
2. Dấu ô mất khi lọc tuần hoặc đổi thứ hạng. Ba trang liên quan dùng khóa
   theo tuần/ngày hoặc số/cột; hậu tố identity-v3 không đọc lại tọa độ cũ.
   Kho dấu cặp toàn site v1 vẫn được giữ.
3. Dấu cặp chỉ cập nhật ở tab đang thao tác. Sự kiện storage nay cập nhật
   các tab đang mở, kể cả khi xóa dấu; không ghi vòng lặp ngược vào storage.
4. Số Cầu giải Đặc Biệt giảm từ 24px xuống 13px khi chọn vì CSS cỡ chữ chỉ
   áp dụng cho ô chưa chọn. Cỡ chữ nay độc lập với trạng thái. Scope dùng
   thuộc tính workspace thật vì trang này không mang lớp sp-page cũ.
5. Workspace giới hạn chiều cao ma trận còn 638px trong khi cần 822px,
   tạo thanh cuộn dọc. Ma trận nay co theo đủ mười hàng, nhãn gọn hơn.

## Bằng chứng kiểm thử

| Kiểm tra | Kết quả |
| --- | --- |
| Frontend: `npm test --prefix tests/frontend` | 197 đạt |
| Python cho thống kê, đánh dấu, workspace, source và gói xuất bản | 287 đạt |
| `scripts/browser/check_stat_tables_browser.py` | 124 trạng thái đạt |
| Chromium năm độ rộng 320/390/768/1024/1440px, sáng/tối | 92 trạng thái đạt |
| Kiểm lại ba trang chi tiết trên source cuối, 390/1440px, sáng/tối | 12 trạng thái đạt |
| Ruff E9/F63/F7/F82, diff, dấu phiên bản tài nguyên | Đạt |

Đối chiếu trực tiếp số lượt của 45 cặp / 10 số kép, tỉ lệ và gan; chuyển
tổng chỉ nối kỳ liền ngày. Kiểm chọn/bỏ chọn, số 00, dải rỗng, storage bị
chặn, tải lại và hai tab cùng origin. Ma trận kiểm đủ 10 hàng / 110 ô gồm
nhãn; cỡ chữ được đo trước/sau chọn. Bảng Theo tổng đo đúng từng tỷ lệ
cột và dóng hàng trên máy tính; cả bốn trang không tràn toàn trang.

Kiểm tra Chromium mới được giữ trong runner dùng chung. Đột biến ép số
đang chọn về 13px làm guard thất bại đúng ở giá trị 24px; đổi hàm tổng
thành hằng 0 bị kiểm thử số liệu bắt. Bản đánh dấu cũ làm các kiểm hồi quy
thất bại, tắt bộ xử lý chọn làm hai kiểm storage bị chặn thất bại.

Đã xem ảnh render trên điện thoại / máy tính, sáng / tối. Hai bảng đầu của
trang Theo tổng vừa khung điện thoại; ma trận 100 số và bảng chuyển tổng
vẫn cuộn ngang khi cần. Không còn cuộn dọc nội bộ trong ma trận Đầu–Đuôi.
