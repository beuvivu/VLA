# Tiến độ thi hành giao diện VLA

Cập nhật: 2026-09-21. Commit gốc: `18b709c4`.

Quy tắc của tệp này: **không mục nào được đánh dấu xong khi chưa có phép đo
kèm theo.** "Đã viết CSS" không phải là xong.

## Trạng thái theo PHASE của spec

| PHASE | Trạng thái | Bằng chứng |
|---|---|---|
| 1 — Discovery | **XONG** | 29 trang khôi phục từ git history; 864 tệp dữ liệu / 473 MB trong 23 thư mục; không có `package.json`, không bước build JS |
| 2 — Design research | **XONG CÓ GIỚI HẠN** | Cả 5 reference + trang production bị chặn 403 CONNECT. Nguồn thay thế: mô tả của chủ dự án trong spec. Xem mục 23.2 |
| 3 — Master Design System | **XONG** | `src/vla_design/tokens.py` + `stylesheet.py`; 27 cặp tương phản × 2 bảng màu đều đạt WCAG AA, biên thấp nhất 1,025x; 13 phép kiểm, 20 đột biến đều chết. Tầng component (thẻ, KPI, bảng, badge, nút, trạng thái rỗng/lỗi/skeleton) hoàn thành cùng PHASE 4 |
| 4 — Global App Shell | **XONG** | `navigation.py` (7 nhóm / 29 trang, đối chiếu khít 29 tệp cũ), `shell.py`, `shell_css.py`, `component_css.py`, `icons.py` (21 hình tự vẽ), `assets/vla-shell.js`; 20 phép kiểm Chromium ở 7 viewport, 12 đột biến đều chết |
| 5 — Page-by-page | CHƯA BẮT ĐẦU | 0/29 trang. Có `docs/_shell-preview.html` là hiện vật QA của khung, KHÔNG phải trang sản phẩm |
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

## PHASE 4 — những gì TRÌNH DUYỆT tìm ra

Chromium mở trang ở 7 viewport và tìm ra **3 lỗi code thật** mà đọc CSS không
thấy:

| Lỗi | Nguyên nhân |
|---|---|
| Nút ba gạch vẫn hiện ở 1440px | `.vla-btn { display: inline-flex }` khai SAU khối `@media` ẩn `.vla-menu-button`. Cùng độ đặc hiệu một lớp thì luật sau thắng → hai đường điều hướng cùng lúc. Sửa: đặt luật ẩn ở CUỐI và dùng hai lớp `.vla-btn.vla-menu-button` |
| Liên kết điều hướng cao **39px** | Chỉ dùng `padding` cho ra 39px — thiếu ĐÚNG một pixel so với ngưỡng vùng chạm 40px của mục X. Sửa: `min-height: 40px` |
| `frame-ancestors` ghi lỗi console | Chỉ thị ấy **bị bỏ qua** khi giao qua `<meta>`; Chromium ghi thẳng cảnh báo. Nó chỉ hoạt động qua HTTP header mà GitHub Pages không cho đặt |

Và **3 lỗi nữa chỉ lộ ra khi xem ẢNH CHỤP THẬT**, không phép đo nào bắt được:

| Lỗi | Sửa |
|---|---|
| Tiêu đề lặp hai lần (topbar + `<h1>`) | Trên màn 375px nó ăn 64px để nhắc lại thứ cách đó 40px. Topbar giờ hiện TÊN NHÓM — không lặp, và trên điện thoại sidebar đóng nên đó là thông tin duy nhất nói đang ở nhánh nào |
| 4 thẻ KPI xếp dọc trên điện thoại | Chiếm ~580px chiều cao để hiện 4 con số. Lưới KPI riêng: 1 cột ở 320px, **2 cột từ 360px**, 4 cột từ 1280px |
| Mốc 380px loại đúng 375px | Mốc đầu tôi chọn là 380 — nó loại chiều rộng "Mobile" trong bảng viewport của chính spec, tức hạng thiết bị phổ biến nhất |

**Và một lỗi thật ở ĐÚNG 1024px**, tìm ra vì tôi đo lại bằng đại lượng đúng:
lưới KPI bật 4 cột từ 1024px nhưng sidebar ăn 264px nên mỗi thẻ còn 159px, và
`2026-09-21` ở 2rem **xuống hai dòng** — chiều cao thẻ nhảy 143→181px, đúng
thứ mục 5.2 cấm. Đã chuyển mốc 4 cột lên 1280px.

Phép đo ĐẦU của tôi ở chỗ này **sai đại lượng**: tôi kiểm `scrollWidth` và
thấy "không tràn" nên tưởng ổn. Con số không tràn ngang vì nó *xuống dòng*
được. Phải đếm số dòng. Đo sai đại lượng thì kết luận đúng cũng là tình cờ.

### Một tệp kiểm RỖNG đã ẩn trong màu xanh

Sau lần xóa giao diện, bộ kiểm báo **1 127 xanh / 0 đỏ** — đúng, nhưng trong
đó `tests/test_dock_on_mobile.py` (7 phép kiểm) xanh CHỈ VÌ nó parametrize
qua 0 trang. Nó thức dậy ngay khi trang đầu tiên xuất hiện và đòi thành phần
`.ui-dock` đã bị xóa cùng UI cũ.

Đã xóa tệp ấy, và thêm chốt chặn cho cả LỚP lỗi này:
`test_the_published_tree_holds_at_least_one_page` — `docs/` trống là nó đỏ,
nói ra sự rỗng thay vì để nó ẩn. Đã xác minh bằng đột biến: bỏ trang đi thì
nó đỏ ngay.

**Giới hạn còn lại từ lỗi `frame-ancestors`:** VLA **không được bảo vệ khỏi bị nhúng
iframe**. Muốn có `frame-ancestors` phải đưa trang qua một CDN cho phép đặt
header (ví dụ Cloudflare) — đó là quyết định hạ tầng, không phải của tầng
giao diện.

Và **2 lỗi trong phép kiểm của tôi**, không phải trong trang: tôi đo ngay sau
`click()` và sau `focus()` trong khi transition 120–180ms còn đang chạy, nên
nó báo drawer "không mở" và liên kết bỏ qua "vẫn ẩn" — cả hai đều sai.

Thêm **một chú thích của tôi bị phép đo phủ nhận**: tôi viết rằng
`min-width: 0` ở các tổ tiên là chỗ giữ cuộn ngang nằm trong bảng. Đột biến
cho thấy không phải — bỏ nó ở cả bốn chỗ, hay bỏ cả `overflow-x` của khung
bảng, đều không làm trang tràn ngang, vì `<table>` khai `inline-size: 100%`
nên hộp của nó không vượt khung chứa. Đã sửa chú thích thành "phòng ngự", và
đã xác minh phép kiểm tràn ngang **có** bắt được tràn thật (chèn phần tử rộng
3000px → cả 7 viewport đỏ).

Nửa "bảng cuộn" của phép kiểm cũng quá lỏng: `scrollWidth > clientWidth` vẫn
đúng khi `overflow: visible`, tức nội dung rộng hơn mà **không cuộn được**.
Đã siết thành đặt `scrollLeft` rồi đọc lại.

### Đã dựng

| Thành phần | Chi tiết |
|---|---|
| Điều hướng | 7 nhóm, 27 trang trong sidebar + 2 biến thể trang chủ ngoài sidebar = 29, đối chiếu khít danh sách tệp cũ |
| Sidebar | `position: fixed` (không phải cột lưới — cột lưới cuộn mất khỏi màn hình trên trang dài); drawer có nền mờ dưới 1024px |
| Nhóm điều hướng | `<details>`/`<summary>` — mở bằng bàn phím sẵn, trình đọc màn hình hiểu sẵn, chạy được khi JS lỗi |
| Mục đang mở | **Bốn kênh độc lập**: nền nhạt, dải bên trái, chữ đậm, `aria-current="page"` — mục XII cấm dùng màu làm kênh duy nhất |
| Chủ đề | Xoay 3 trạng thái (hệ thống / sáng / tối); trạng thái "hệ thống" KHÔNG đặt `data-theme` vì đặt nó là ghi đè `prefers-color-scheme`; vùng `aria-live` thông báo |
| Drawer | Vòng focus, `inert` cho nội dung phía sau, Esc đóng, khoá cuộn body, nhả tất cả khi đóng hoặc khi kéo rộng qua 1024px |
| Icon | 21 hình SVG tự vẽ, một khung nhìn 24×24, nét 1,75, `currentColor` — không thư viện ngoài |
| CSP | `default-src 'none'` rồi mở từng thứ; đây là lý do mọi CSS/JS là tệp riêng, không nội tuyến |

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
