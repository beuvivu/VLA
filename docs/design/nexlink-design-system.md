# Hệ thiết kế NexLink áp cho VLA — số đo, không phải ước

Mọi con số trong tài liệu này là **số đo** lấy từ trang tham chiếu bằng
`scripts/inspect_reference_layout.py` và `scripts/inspect_reference_shell.py`,
chạy trên runner GitHub Actions. Proxy của môi trường phát triển chặn trang
tham chiếu (403 ngay ở tầng CONNECT), nên runner là đường duy nhất đọc được.

Hai script chỉ **đọc** và in số đo. Chúng không tải HTML, CSS hay hình ảnh của
trang tham chiếu về kho. Trang tham chiếu là sản phẩm thương mại; ta đọc ngôn
ngữ thị giác rồi tự viết CSS của mình. Kho này viết CSS tay, không framework,
nên bê tệp của họ về vừa sai về giấy phép vừa không dùng được.

## Vì sao phải đo bằng trình duyệt, không đọc CSS

Bản đọc CSS dạng văn bản chạy trước đó thu về **0 biến chủ đề, 0 quy tắc
`body`, bộ xương rỗng**. Nguyên nhân đo được: trang nạp **mười** biểu định
kiểu, tám cái đầu là thư viện icon và widget (FontAwesome, lucide, flatpickr,
simplebar, bootstrap-select…). Chủ đề dùng lớp tiện ích chứ gần như không khai
biến CSS nào. Với một dashboard, `getComputedStyle` là cách duy nhất đọc đúng.

## Bảng màu

| Vai trò | Sáng | Tối |
| --- | --- | --- |
| Nền trang | `#fdfdff` | `#282828` |
| Bề mặt (thẻ, dải) | `#ffffff` | `#1e1e1e` |
| Nền ô nhập / mục hoạt động | `#f2f2f6` | `#232323` |
| Viền | `#eeeef3` | `rgba(255,255,255,.05)` |
| Chữ thân | `#696981` | `#999999` |
| Chữ tiêu đề | `#0c243c` | `#bcbcbc` |
| Chữ mục nav hoạt động | `#29294b` | `#b9c2da` |
| Nhấn | `#5955d1` | `#9b99e3` |

## Thang chữ

Phông của trang tham chiếu là **Instrument Sans**. Kho này giữ **Inter tự
host**: CSP đặt `font-src 'self'` và proxy không tải được tệp phông về để tự
host. Đây là thiếu sót đã biết, không phải bỏ qua.

| | 1440px | 390px |
| --- | --- | --- |
| h2 | 28px / 600 | 23.14px / 600 |
| h3 | 24.5px / 600 | 21.77px / 600 |
| h4 | 21px / 600 | 20.39px / 600 |
| h5 | 17.5px / 600 | 17.5px / 600 |
| body | 14px / 500 / 22.4px | như 1440 |
| p | 13px / 500 / 20.8px | như 1440 |
| small | 12.25px / 500 | như 1440 |

Trang tham chiếu **không dùng `clamp()`** — thang chữ đổi theo breakpoint.

## Thẻ, bảng, ô nhập, nút

    thẻ         nền bề mặt, bo 10px, viền 1px, bóng rgba(2,2,76,.02) 0 5px 10px
    bảng th     nền rgba(242,242,246,.6), 14px/600, đệm 8px 0 8px 20px
    bảng td     14px/500, đệm 6px 0 6px 20px, viền dưới 1px, chiều cao hàng 45px
    ô nhập      nền #f2f2f6, bo 6px, viền 1px, cao 41px, đệm 8.5px 19.2px
    nút         bo 8px

## Khung ứng dụng

Đo ở 1440 / 1024 / 390, cả hai trạng thái thu và mở:

    dải biểu tượng   80px, x=0, bóng trong rgba(41,41,75,.05) 0 0 10px
    dải chi tiết     240px (220px ở <=1024)
    thanh trên       80px, padding-left 80px, viền dưới 1px
    vùng nội dung    margin-left 80px, đệm 10px 15px 30px
    mục nav          47x46, bo 8px

**Sự thật quan trọng nhất đo được:** khi mở dải chi tiết, `margin-left` của
vùng nội dung **không đổi**. Dải chi tiết **phủ lên** nội dung chứ không đẩy
nó. Với một trang phân tích thì đây là khác biệt lớn: đẩy nội dung nghĩa là
mỗi lần mở menu, cả một bảng số phải dàn lại.

Dưới 1200px, cả hai dải ra ngoài màn (x=−80 và x=−250), thanh trên bỏ
padding-left, vùng nội dung về `margin-left:0`, và menu mở ra dưới dạng phủ.

## Nơi các giá trị này sống trong kho

| Hạng mục | Tệp |
| --- | --- |
| Token màu, bóng, bo góc, phông | `src/ui_theme.py` |
| Lớp skin dùng chung | `src/templates/ui_visual_system.css` |
| Khung ứng dụng (CSS) | `src/templates/app_shell.css` |
| Khung ứng dụng (dựng HTML) | `src/app_shell.py` |
| Khung ứng dụng (hành vi) | `src/assets/app-shell.js` |
| Nơi bọc mọi trang | `src/page_output.py::_attach_shell` |
