# Nền Crafto cho index / landing — trạng thái thật

> Ghi chú lịch sử. Yêu cầu mới ngày 26/09/2026 mở rộng Crafto sang hệ thống
> trình bày chung, đồng thời chọn Application làm tham chiếu nền/chuyển động.
> Xem [thiết kế hiện hành](crafto-integration-2026-09-26.md). Các mục “CHƯA làm”
> dưới đây mô tả thời điểm cũ, không phải trạng thái của bản tích hợp mới.

## Đã làm

Ngôn ngữ thị giác của trang tham chiếu Crafto đã được đọc bằng
`scripts/inspect_reference_design.py` chạy trên runner Actions (proxy chặn
trang, 403 ở tầng CONNECT) và áp vào token dùng chung:

    nền           --solitude-blue #f0f4fd -> --selago #eaedff
    nhấn          --base-color #2946f3, --majorelle-blue #724ade
    bóng          luôn đen 8%: 0 0 10px / 0 0 25px / 0 20px 60px
    bo góc        16px thẻ, 24px dải tiêu đề
    nhịp          .3s, cubic-bezier(.12,0,.39,0) và (.37,0,.63,1)
    quầng sáng    radial-gradient thay cho phần tử có filter:blur(20-30px)

Chi tiết số đo và các chỗ **không** lấy nguyên (màu chữ mờ `#717580` của họ
chỉ đạt 3,96:1 trên nền `#eaedff` — trượt AA) ghi ở
`docs/ui-ux/implementation-progress.md`.

## CHƯA làm — hai việc

### 1. Thu hẹp nền Crafto về riêng index / landing

Chỉ thị yêu cầu nền Crafto **chỉ** áp cho `index.html`, `landing.html`,
`landing_desktop.html`, còn phần còn lại của ứng dụng theo NexLink.

Hiện tại bảng màu Crafto đang dùng **toàn cục**: nó nằm trong
`src/ui_theme.py` (token dùng chung) và `src/templates/ui_visual_system.css`.
Việc tách đôi là:

* giữ nền + quầng sáng Crafto trong một lớp CSS có phạm vi riêng, chỉ gắn vào
  ba trang trên;
* chuyển nền của mọi trang còn lại sang `#fdfdff` (nền NexLink đã đo);
* giữ bảng màu trạng thái và tương phản đã đo — bốn phép kiểm tương phản
  trong `tests/test_contrast_and_scheduling.py` sẽ đỏ nếu làm hỏng.

### 2. Chuyển động chữ "Vietnam Lottery Analysis"

**Chuỗi này không tồn tại trong kho.** Đã tìm trên toàn bộ mã nguồn, mẫu và
trang xuất bản: không có kết quả nào. Cũng không có marquee hay ticker nào cho
tên thương hiệu — thứ duy nhất chạy vòng lặp là hiệu ứng quét của thẻ console
ở trang Phòng nghiên cứu.

Chỉ thị viết "The VLA index and landing_page **currently contain** the brand
text" và "preserve that behavior". Tiền đề ấy không đúng với kho này: không có
gì để giữ. Tiêu đề hiện tại của trang index là "Trung tâm thống kê xổ số".

Nên việc phải làm là **dựng mới**, không phải giữ nguyên:

* thêm chuỗi "Vietnam Lottery Analysis" vào hero của ba trang landing;
* chuyển động vào nhẹ (opacity + translateY, easing đã đo), đọc được ngay cả
  khi JavaScript không chạy;
* tôn trọng `prefers-reduced-motion: reduce`;
* nếu làm dạng chạy ngang thì phải lặp liền mạch, không tràn ngang, và bản sao
  trang trí phải ẩn với trình đọc màn hình.
