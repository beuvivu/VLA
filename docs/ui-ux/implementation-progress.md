# Tiến độ thi hành giao diện VLA

Cập nhật: 2026-09-21. Commit gốc: `18b709c4`.

Quy tắc của tệp này: **không mục nào được đánh dấu xong khi chưa có phép đo
kèm theo.** "Đã viết CSS" không phải là xong.

## Trạng thái theo PHASE của spec

| PHASE | Trạng thái | Bằng chứng |
|---|---|---|
| 1 — Discovery | **XONG** | 29 trang khôi phục từ git history; 864 tệp dữ liệu / 473 MB trong 23 thư mục; không có `package.json`, không bước build JS |
| 2 — Design research | **XONG CÓ GIỚI HẠN** | Cả 5 reference + trang production bị chặn 403 CONNECT. Nguồn thay thế: mô tả của chủ dự án trong spec. Xem mục 23.2 |
| 3 — Master Design System | **NỀN TẢNG XONG** | `src/vla_design/tokens.py` + `stylesheet.py`; 27 cặp tương phản × 2 bảng màu đều đạt WCAG AA, biên thấp nhất 1,025x; 13 phép kiểm, 20 đột biến đều chết |
| 4 — Global App Shell | CHƯA BẮT ĐẦU | |
| 5 — Page-by-page | CHƯA BẮT ĐẦU | 0/29 trang |
| 6 — Specialized analytics | CHƯA BẮT ĐẦU | |
| 7 — Regression & QA | CHƯA BẮT ĐẦU | Mốc nền: 1127 xanh / 0 đỏ tại `18b709c4` |
| 8 — Final verification | CHƯA BẮT ĐẦU | |

## PHASE 3 — những gì phép đo tìm ra

Bảng màu chủ dự án cung cấp có **6 trong 15 cặp không đạt WCAG AA** khi đo
thật:

| Cặp | Tỉ lệ | Cần |
|---|---|---|
| `text-muted #94A3B8` / surface | 2,56:1 | 4,5:1 |
| `text-muted` / surface-secondary | 2,44:1 | 4,5:1 |
| `accent #6366F1` / surface | 4,47:1 | 4,5:1 |
| `success #16A34A` / surface | 3,30:1 | 4,5:1 |
| `warning #D97706` / surface | 3,19:1 | 4,5:1 |
| `info #0284C7` / surface | 4,10:1 | 4,5:1 |

Ba nhóm sửa, lý do khác nhau:

1. **`text-muted`** làm đậm tới `#5C708B`, giữ hue/saturation bằng phép giảm
   độ sáng trong HLS.
2. **`accent`/`success`/`warning`/`info`** không đạt khi làm CHỮ nhưng hợp lệ
   khi làm NỀN, nên mỗi màu tách ba token: `-fill` (nền), `-ink` (chữ, đạt
   4,5:1), `-soft` (nền badge). Làm đậm một giá trị rồi mất luôn màu nền là
   câu trả lời sai.
3. **`border #E2E8F0`** ở 1,23:1 — nhưng NGƯỠNG 3:1 tôi áp lúc đầu SAI cho
   trường hợp này. WCAG 1.4.11 đòi 3:1 cho viền nhận dạng *thành phần điều
   khiển*, không cho đường kẻ trang trí. Nên `border` giữ nguyên, thêm
   `border-strong #8794A8` (3,07:1) cho viền điều khiển.

Thêm hai phát hiện chỉ lộ ra khi siết phép kiểm:

- Dùng `info` hoặc `accent` NGUYÊN BẢN làm nền thì **không màu chữ nào đạt**
  (trắng 4,10 / 4,47; đậm 3,97 / 3,64). Badge hai màu ấy buộc phải theo mẫu
  nền nhạt + chữ ink.
- **`text-secondary #64748B` trên nền trang `#F4F5FF` = 4,39:1, KHÔNG đạt.**
  Tôi đã kết luận sai là "đạt, giữ nguyên" khi hợp đồng còn chưa canh cặp
  này. Đây là một trong những cặp xuất hiện nhiều nhất của cả sản phẩm và nó
  suýt lọt. Đã làm đậm thành `#5C6A80`.

Dark Mode được thiết kế riêng, không đảo ngược: nền navy sâu `#0A0D18`, và
chiều tương phản ĐẢO — chữ trên mảng màu nhấn là màu nền tối, không phải
trắng (chữ trắng trên `primary` Dark Mode chỉ đạt 3,06:1; chữ `#0A0D18` đạt
6,34:1).

## Giới hạn đã biết

1. **Năm reference không truy cập được** (403 CONNECT qua agent proxy, đo
   2026-09-21T13:23Z). Không có nhận xét nào về hình thức thật của chúng được
   phát biểu. Nếu về sau có truy cập, phải đối chiếu lại thiết kế.
2. **Trang production không truy cập được**, nên không kiểm chứng được deploy
   từ phiên này. Phải do chủ dự án xác nhận.
3. **Không có "before" để so screenshot** — giao diện cũ đã bị xóa theo yêu
   cầu. Chỉ có ảnh "after".

## 29 trang cần dựng

Khôi phục từ `git show 00cf02ea --stat`. Đây là DANH SÁCH CẦN DỰNG, không phải
danh sách đã có.

| # | Trang | Trạng thái |
|---|---|---|
| 1 | `index.html` | chưa dựng |
| 2 | `landing.html` | chưa dựng |
| 3 | `landing_desktop.html` | chưa dựng |
| 4 | `dashboard.html` | chưa dựng |
| 5 | `statistics.html` | chưa dựng |
| 6 | `thong-ke-tong-hop.html` | chưa dựng |
| 7 | `model-quality.html` | chưa dựng |
| 8 | `live.html` | chưa dựng |
| 9 | `so-ket-qua-truyen-thong.html` | chưa dựng |
| 10 | `bang-dac-biet.html` | chưa dựng |
| 11 | `bang-dac-biet-thang.html` | chưa dựng |
| 12 | `bang-dac-biet-nam.html` | chưa dựng |
| 13 | `cau-giai-dac-biet.html` | chưa dựng |
| 14 | `cau-dac-biet-theo-bo-so.html` | chưa dựng |
| 15 | `chu-ky-dac-biet.html` | chưa dựng |
| 16 | `giai-dac-biet-theo-tong.html` | chưa dựng |
| 17 | `giai-db-ngay-mai.html` | chưa dựng |
| 18 | `tan-suat-loto.html` | chưa dựng |
| 19 | `tan-suat-cap-loto.html` | chưa dựng |
| 20 | `cap-lon-loto.html` | chưa dựng |
| 21 | `dau-duoi-loto.html` | chưa dựng |
| 22 | `lo-gan.html` | chưa dựng |
| 23 | `ml_top10_loto.html` | chưa dựng |
| 24 | `ml_top10_de.html` | chưa dựng |
| 25 | `soi-path-loto-stable.html` | chưa dựng |
| 26 | `soi-path-loto-active.html` | chưa dựng |
| 27 | `soi-path-de-stable.html` | chưa dựng |
| 28 | `soi-path-de-active.html` | chưa dựng |
| 29 | `research-lab.html` | chưa dựng |

## Việc còn lại, theo thứ tự

1. PHASE 3 — Design System: token màu light/dark, thang chữ, thang khoảng
   cách, shadow, radius, motion. Kèm phép kiểm tương phản WCAG thật.
2. PHASE 4 — App Shell: sidebar, topbar, breadcrumb, container, theme toggle,
   hành vi mobile.
3. PHASE 5 — dựng 29 trang, mỗi trang đọc dữ liệu thật.
4. PHASE 6 — ma trận thống kê, bảng dữ liệu nâng cao, quick selection.
5. PHASE 7 — Playwright ở 7 viewport, light + dark; kiểm console, network,
   overflow, overlap.
6. Dựng lại 3 safeguard ở mục 23.5 của spec.
