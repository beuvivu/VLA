# Số đo bảng màu sáng/tối — 26-09-2026

Yêu cầu mới thay hợp đồng chỉ sáng: các trang kế thừa token trên `html`,
`.dark` và `data-ui-theme="dark"` dùng cùng bảng màu; media hệ điều hành là
phương án khi JavaScript tắt. Các owner của trang chỉ alias token, không đặt
lại `--ui-surface`, `--ui-ink` hoặc các trạng thái trên `body`.

Đo bằng `ui_theme.contrast_ratio`, đọc trực tiếp các giá trị trong
`TAILWIND_LITE_CSS`; không dùng bảng màu chép lại trong phép kiểm.

| Cặp nền/chữ | Sáng | Tối |
|---|---:|---:|
| Không về | 6,15:1 | 8,46:1 |
| Giải Đặc Biệt | 5,24:1 | 8,27:1 |
| Đánh dấu | 7,28:1 | 8,15:1 |
| Chưa quay | 5,20:1 | 8,73:1 |
| Một nháy | 6,84:1 | 9,29:1 |
| Hai nháy | 6,59:1 | 8,24:1 |
| Ba nháy | 6,49:1 | 8,04:1 |
| Bốn nháy | 7,39:1 | 7,83:1 |
| Năm nháy | 6,68:1 | 8,00:1 |
| Cam của bảng tần suất | 6,38:1 | 8,85:1 |
| Nhãn coral | 5,88:1 | 8,36:1 |

Chữ chung (`ink`, `ink-2`, `ink-soft`, `brand-ink`, `ok`, `warn`, `bad`)
trên bốn bề mặt (`bg`, `bg-2`, `surface`, `surface-2`) đạt thấp nhất
**4,83:1 ở sáng**, **5,84:1 ở tối**. Icon điều hướng sáng dùng Indigo
`#4F46E5`; tối dùng `#a5abfa`.

Cấp nháy giữ sắc và thứ tự hiện hành. Nền cấp nháy sáng vẫn pastel;
nền tối dùng cùng sắc với thành phần RGB lớn nhất dưới 100, chữ sáng cùng
sắc đạt AA. Ô không về giữ mặt phẳng, ô có về có vòng viền trong. Chú giải
và ô thật đọc cùng token. Bento giữ một nháy ở bề mặt thường và năm nháy
ở sắc cam như trước. Đường dóng dùng viền với nền trong suốt, không phủ
lên màu mã hoá dữ liệu. Không sửa số liệu, phân cấp, chuỗi JSON hay màu
nhiệt do Python sinh sẵn.

Bản in đặt lại toàn bộ cặp chữ/bề mặt và trạng thái về sáng ngay cả khi
`html.dark` đang có hiệu lực. Các tiện ích trung tính cũ (`bg-white`,
`text-slate-*`) cũng tham chiếu token.

Hợp đồng kiểm thử chuyển từ tìm hex trong từng selector sang phân giải
token của từng chủ đề. Kiểm tra AA và độ phân biệt vẫn giữ nguyên, bổ sung
kiểm dark không chói, media/explicit cùng bảng màu, không pinlight trên body,
đường dóng không che ô và in từ màn tối. Phép kiểm nguồn bổ sung nằm ở
`tests/test_theme_palette.py`; helper chỉ đọc token thật ở
`tests/theme_palette_helpers.py`. Kiểm tra render cuối thuộc bước tích hợp.
