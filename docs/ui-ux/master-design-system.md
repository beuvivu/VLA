# VLA Master Design System

Nguồn sự thật: `src/vla_design/tokens.py`. CSS được SINH RA từ đó
(`stylesheet.py`), không có bản viết tay song song. Một phép kiểm so hai bên
nên chúng không thể trôi khỏi nhau.

## Màu — đã đo, không đặt tay

Bảng màu chủ dự án cung cấp có **6 trong 15 cặp không đạt WCAG AA**:

| Cặp | Tỉ lệ | Cần |
|---|---|---|
| `text-muted #94A3B8` / surface | 2,56:1 | 4,5:1 |
| `text-muted` / surface-secondary | 2,44:1 | 4,5:1 |
| `accent #6366F1` / surface | 4,47:1 | 4,5:1 |
| `success #16A34A` / surface | 3,30:1 | 4,5:1 |
| `warning #D97706` / surface | 3,19:1 | 4,5:1 |
| `info #0284C7` / surface | 4,10:1 | 4,5:1 |

Ba nhóm sửa, ba lý do khác nhau:

1. **`text-muted`** làm đậm tới `#5C708B`, giữ hue/saturation bằng phép giảm
   độ sáng trong HLS.
2. **Bốn màu ngữ nghĩa** không đạt khi làm CHỮ nhưng hợp lệ khi làm NỀN. Mỗi
   màu tách ba token: `-fill` (nền), `-ink` (chữ, đạt 4,5:1), `-soft` (nền
   badge). Làm đậm một giá trị rồi mất luôn màu nền là câu trả lời sai.
3. **`border #E2E8F0`** ở 1,23:1 — nhưng ngưỡng 3:1 áp lúc đầu SAI cho trường
   hợp này. WCAG 1.4.11 đòi 3:1 cho viền nhận dạng *thành phần điều khiển*,
   không cho đường kẻ trang trí. Thêm `border-strong #8794A8` (3,07:1).

Hai phát hiện chỉ lộ ra khi siết phép kiểm:

- Dùng `info` hoặc `accent` NGUYÊN BẢN làm nền thì **không màu chữ nào đạt**
  (trắng 4,10 / 4,47; đậm 3,97 / 3,64). Badge hai màu ấy buộc theo mẫu nền
  nhạt + chữ ink.
- **`text-secondary #64748B` trên nền trang `#F4F5FF` = 4,39:1 — KHÔNG đạt.**
  Kết luận ban đầu "đạt, giữ nguyên" là SAI vì hợp đồng chưa canh cặp này.
  Chữ phụ trên nền trang là cặp xuất hiện nhiều nhất của cả sản phẩm.

**Kết quả: 27 cặp × 2 bảng màu = 54 phép đo, 0 không đạt**, biên thấp nhất
1,025×.

## Dark mode — thiết kế riêng, không đảo ngược

Nền navy sâu `#0A0D18`, các mặt nổi dần. Chiều tương phản **ĐẢO** và đây là
chỗ dễ sai nhất: chữ trên mảng màu nhấn phải là màu NỀN TỐI, không phải trắng.
Đo được: chữ trắng trên `primary` dark chỉ đạt 3,06:1; chữ `#0A0D18` đạt
6,34:1.

## Chuyển đổi chủ đề — ba tầng, đúng thứ tự

1. `:root` — Light Mode, mặc định.
2. `@media (prefers-color-scheme: dark)` bọc trong `:root:not([data-theme="light"])`.
3. `:root[data-theme="dark"]` — lựa chọn tường minh, thắng cả hệ điều hành.

Thiếu `:not()` ở tầng 2 thì người đọc chọn sáng trong lúc máy đặt tối sẽ vẫn
thấy trang tối — cái nút vô hiệu, và người dùng không tự chẩn đoán được.

Trạng thái "theo hệ thống" **KHÔNG đặt `data-theme`**: đặt nó là ghi đè
`prefers-color-scheme`, tức mất luôn khả năng theo hệ điều hành.

## Chữ, khoảng cách, bán kính, chuyển động

- Thang chữ ở cận DƯỚI khoảng spec cho, vì mỗi pixel chiều cao dòng là một
  hàng số bị đẩy khỏi màn hình.
- Số thống kê dùng `font-variant-numeric: tabular-nums` — cột số lệch nhau làm
  hỏng chính việc so sánh bằng mắt.
- Khoảng cách: bội số của bốn, 4→48px. Không giá trị tuỳ ý.
- Chuyển động: không mục nào quá 240ms. Mọi thứ bị `prefers-reduced-motion`
  tắt được.

## Ràng buộc kiến trúc — đã đo, không phải gợi ý

| Ràng buộc | Vì sao |
|---|---|
| CSS viết tay, không Tailwind | Kho không có `package.json`; CDN đụng CSP `'self'` mà bộ kiểm đang đòi |
| Cấm mọi cách ghi DOM nhận chuỗi rồi phân tích thành thẻ | `test_nothing_that_emits_markup_uses_an_untrusted_dom_sink` tự dò |
| Mọi trang khai CSP `default-src 'none'` | `test_every_published_page_declares_a_content_security_policy` |
| Icon tự vẽ, không thư viện | Mục XVIII.8 + CSP |
| `frame-ancestors` KHÔNG có | Bị bỏ qua khi giao qua `<meta>`; cần HTTP header mà GitHub Pages không cho đặt |
