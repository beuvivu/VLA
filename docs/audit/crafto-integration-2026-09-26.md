# Kiểm chứng tích hợp Crafto Application

## Phạm vi

- Nguồn nền: `main` c0033bb0099b974a13a6b160c468be19067c085f.
- Khảo sát trang Crafto tổng, Application và danh mục thành phần; đọc HTML,
  stylesheet Application, mã chuyển động công khai; quan sát trực tiếp hero,
  thẻ tính năng và con trỏ trong trình duyệt.
- 29 trang được gắn lớp trình bày chung. Ba biến thể landing dùng cùng hero.
- Khung Nexlink, điều hướng, dữ liệu, thuật toán và mô hình không đổi.

## Ánh xạ mẫu sang sản phẩm

| Mẫu tham chiếu | Áp dụng |
|---|---|
| Nền Application coral/hồng/tím trên trắng | Gradient CSS hero, quầng nhẹ toàn ứng dụng |
| 12 hạt màu trôi nhẹ | Phần tử trang trí CSS, không bắt sự kiện số liệu |
| Chữ nền lớn chạy ngang | Vietnam Lottery Analysis, hai bản sao ẩn với trình đọc màn hình |
| Cursor 25px và phản hồi hover | Lớp điểm mờ, giữ con trỏ hệ thống, chỉ thiết bị con trỏ chính xác |
| Lớp chuyển động/Atropos | Parallax giới hạn 6px trên cụm trình bày hero |
| Thẻ trắng, bóng mềm, icon, CTA | Hệ thẻ 16px, hero 24px, nút viên thuốc và SVG hiện có |
| Nội dung xuất hiện theo lớp | IntersectionObserver, fallback nội dung luôn nhìn thấy |

Không đưa các chức năng thương mại không liên quan (giỏ hàng, newsletter,
testimonial tự chạy) vào công cụ phân tích. Định dạng số và màu thống kê giữ
nguyên ý nghĩa thay vì dùng màu thương hiệu cho dữ liệu.

## Kiểm chứng mã và dữ liệu

- Kiểm thử mới đã đỏ trước khi triển khai ranh giới xuất bản và hero.
- 11 kiểm thử runtime: storage lỗi, persistence, giảm chuyển động trực tiếp,
  coarse/touch, gộp RAF, hủy trạng thái cũ, tab ẩn, khởi tạo lặp và reveal.
- Toàn bộ JavaScript: 20/20 đạt, gồm 9 bài điều hướng hiện có.
- Bộ Python trước xuất bản: 2107 đạt, 8 bỏ qua; sau đó thêm regression phạm vi
  pause cho live updates và chạy lại bộ kiểm trên các trang đã xuất bản.
- Đối chiếu 26 trang chi tiết trước/sau: tất cả HTML bảng, JSON nhúng và
  số lượng/móc data-number được bảo toàn. Landing dựng từ dữ liệu có sẵn;
  payload mô phỏng lấy nguyên tệp hiện có, không chạy tính lại.
- Review độc lập tìm thấy pause toàn body có thể giữ số live mới ở opacity 0.
  Đã viết regression đỏ→xanh và giới hạn pause vào lớp trang trí.
- Nút hiệu ứng đặt lớp 30, dưới scrim 34/panel 38; không phủ menu mobile.
- Lint Python và kiểm tra khoảng trắng đạt.

## Giới hạn kiểm chứng trực quan

Phiên trình duyệt không cho mở URL tệp cục bộ. Không dùng đường vòng để vượt
giới hạn đó. Kiểm tra hình ảnh trên URL triển khai công khai được thực hiện
sau khi các cổng kiểm thử mã đạt. Chưa xem kết quả mobile trực tiếp thì không
coi kiểm tra responsive bằng mã là nghiệm thu trực quan mobile.

## Tích hợp đồng thời

PR91 đang mở ở thời điểm khảo sát. Bản này dùng các tài nguyên riêng và một
điểm gắn cuối `write_page`; cần giữ chúng khi tái dựng trang hoặc giải xung đột
với phần dọn dock/điều hướng của PR91. Không khôi phục snapshot nguồn cũ.
