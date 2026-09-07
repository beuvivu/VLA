# Tái thiết kế giao diện: từ sidebar sang dock nổi

> Mọi con số trong tài liệu này đo bằng trình duyệt thật ở 1680×1050, hoặc tính
> từ mã nguồn. Không con số nào ước lượng.

---

## 1. Ba va chạm giữa đặc tả và ràng buộc thật

Đặc tả yêu cầu Tailwind CDN, phông Inter/Plus Jakarta Sans từ Google Fonts, và
WCAG AAA. Kho này phục vụ qua GitHub Pages với chính sách bảo mật:

```
default-src 'self'; font-src 'self'; style-src 'self' 'unsafe-inline';
script-src 'self' 'unsafe-inline'
```

| Yêu cầu | Va chạm | Cách giải quyết |
|---|---|---|
| Tailwind CDN | `default-src 'self'` chặn — trang mất **toàn bộ** style, không báo lỗi | Viết CSS thật trong `ui_theme.py`, giữ đúng token và thang 8pt |
| Google Fonts | `font-src 'self'` chặn | Tự host Inter (SIL OFL cho phép phân phối lại) |
| WCAG AAA | `--vla-ink-soft` thiếu 0.30 | Nâng `#93a4bb` → `#97a8be` (**7.02:1**) |

### Phát hiện phụ: phông chưa bao giờ tải được

Trước thay đổi này kho có **0 quy tắc `@font-face`** và **0 tệp phông**, trong
khi CSS khai báo `--vla-font: Aptos, …`. Với `font-src 'self'` thì không phông
nào tải được từ đâu cả — nên trang chỉ hiển thị bằng Aptos trên máy đã cài sẵn
Microsoft 365; mọi máy khác rơi về `system-ui`.

Aptos còn **không được phép phân phối lại** (giấy phép Microsoft 365), nên
không thể tự host hợp pháp. Inter theo SIL OFL thì được, miễn giữ kèm giấy
phép — `docs/assets/Inter-LICENSE.txt` tồn tại vì lý do đó và một phép kiểm
canh nó.

| | |
|---|---|
| Nguồn | Inter v4.1, bản variable |
| Gốc | 344 KB |
| Sau khi cắt gọn còn Latin + tiếng Việt | **172 KB** |
| Trục | `wght` 100–900, `opsz` 14–32 |
| Ký tự tiếng Việt | **74/74** đã kiểm |
| Kiểm chứng khi chạy | `document.fonts` báo `status: loaded`, dựng được `ữỗẹặ` |

---

## 2. Hiện trạng đo được trước khi sửa

| Vấn đề | Số đo |
|---|---|
| Sidebar chiếm | **292 / 1680 px = 17.4%** chiều ngang |
| Khoảng trắng chết đầu panel tín hiệu | **140 / 355 px = 39%** |
| Cột 2–3 khu căn cứ | bảng hết ở ~795px trong khung 1450px → **~45% rỗng** |
| Cột "Tỷ lệ" trong bảng hẹp | **bị cắt mất** |
| Thẻ chỉ số | 4 |
| Trang không có `<nav>` nào | **6** (4 soi cầu + research-lab + live) |

---

## 3. Thay đổi và kết quả đo

### 3.1 Dock thay sidebar

17 đích là quá nhiều cho một dock kiểu macOS — icon sẽ nhỏ hơn 32px và tooltip
chồng nhau. `SITE_NAV` vốn đã chia 5 nhóm, nên dock hiện **5 icon nhóm**, mỗi
icon mở một popover. Trang landing có thêm nhóm thứ sáu "Trên trang" chứa 12
neo cuộn nội bộ.

Phóng to dùng đúng đường cong đặc tả yêu cầu:

```css
.dock-ic { transition: transform .28s cubic-bezier(.25, 1, .5, 1); }
.dock-btn:hover .dock-ic,
.dock-btn:focus-visible .dock-ic { transform: scale(1.18) translateY(-4px); }
```

Ba điểm không có trong đặc tả nhưng bắt buộc:

* **`:focus-within` bên cạnh `:hover`** — chỉ hover thì người dùng bàn phím
  không bao giờ tới được mục con.
* **`prefers-reduced-motion`** — tắt phóng to cho người đặt giảm chuyển động.
* **Điều hướng dự phòng cuối trang** — popover ẩn bằng `visibility:hidden`;
  nếu CSS không tải được thì trạng thái hiển thị rơi về mặc định trình duyệt.
  Một danh sách phẳng tốn vài trăm byte và giữ nguyên khả năng dò của trình
  thu thập, vốn là lý do sidebar tồn tại.

**Kết quả:** chiều rộng nội dung **1292 → 1584 px (+22.6%)**.

### 3.2 Bảng chỉ số: 4 → 6 thẻ

Hai thẻ mới dùng dữ liệu đã có: `Chuỗi ngày` (392 kỳ liên tục trong
`data/xsmb.csv`) và `Chất lượng mô hình` (hạng A/B/C từ
`data/research/model_scores.json`).

Thẻ chất lượng cố ý **không** hiện phần trăm: kỹ năng đo được nằm ở mức một
phần vạn, nên in "0,07%" sẽ gợi ý một độ chính xác mà phép đo không có.

```css
.metric-row { grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }
```

`auto-fit` cho 6 → 3 → 2 → 1 cột mà không cần media query cho từng mốc.

Panel tín hiệu: `align-content: end` → `center`, khoảng trắng **140/0 → 76/76**.

### 3.3 Ma trận dữ liệu hai tầng

```
Tầng 1  ┌── #ket-qua (58%) ──┬── #chuc-don-vi (42%) ──┐  align-items: stretch
Tầng 2  └───────── #ma-tran-ngay (100%) ──────────────┘
```

```css
.matrix-top { grid-template-columns: minmax(0, 58fr) minmax(0, 42fr); }
```

`minmax(0, …)` là **bắt buộc**, không phải tuỳ chọn: `1fr` mặc định là
`minmax(auto, 1fr)`, nên bảng kết quả rộng sẽ đẩy cột phình ra và phá vỡ tỉ lệ.

Đo được: 905 + 655 px, cân bằng chiều cao; ma trận ngày từ 637 → **1584 px**.

### 3.4 Ba bảng dự đoán trên một hàng

Thứ tự trái → phải: mô phỏng, Đặc Biệt, Lô Tô.

Trước đây `#mo-phong` là section riêng phía trên còn ĐB/Lô tô nằm trong section
khác, nên ba thứ cùng nói về ngày mai bị tách làm hai vùng cuộn.

**Một cạm bẫy của bố cục mới:** `#mo-phong` được `build_fun_prediction.py` chèn
vào *sau* khi trang dựng xong. Nếu bước đó không chạy, một section rỗng vẫn
chiếm trọn một phần ba chiều ngang — trước đây nó là section full-width nên tự
xẹp và không ai thấy.

```css
.next-day > section:empty { display: none; }
.next-day:has(> section:empty) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
```

### 3.5 Khu căn cứ: gộp hai bảng

Khung chọn số giữ nguyên bên trái (34%); hai bảng đường cầu gộp thành một khối
bên phải (66%), ĐB trên — đường phân cách — Lô tô dưới.

```css
.basis-merged > section + section { border-top: 1px solid var(--line); }
```

Dùng bộ chọn anh em liền kề chứ không phải `border-top` cho mọi con: cách sau
vẽ thừa một đường trên phần đầu.

**Sửa được hai lỗi cùng lúc:** mỗi bảng từ 445 → ~1090 px nên cột "Tỷ lệ" hết
bị cắt, và ~45% khoảng trắng thừa biến mất vì hai bảng chia nhau chiều cao.

---

## 4. Kiểm chứng

### Đáp ứng — 0 tràn ngang ở mọi bề rộng

| Bề rộng | Tràn ngang | Tầng 1 | Ngày mai |
|---:|---:|---|---|
| 1680 | 0 | 905+655 cạnh nhau | 1 hàng |
| 1440 | 0 | 771+558 cạnh nhau | 1 hàng |
| 1240 | 0 | 662+479 cạnh nhau | 2 hàng |
| 1024 | 0 | xếp dọc | 2 hàng |
| 768 | 0 | xếp dọc | 2 hàng |
| 390 | 0 | xếp dọc | 3 hàng |

### Tương phản — trước/sau trên toàn bộ 14 trang

| Trang | Lỗi AA trước | Lỗi AA sau |
|---|---:|---:|
| index / landing / landing_desktop | 31 / 31 / 29 | **0 / 0 / 0** |
| dashboard, model-quality, research-lab | 0 | 0 |
| 4 trang soi cầu | 0 | 0 |
| live | 0 | 0 |
| statistics | 289 | 328 |
| **Tổng** | **380** | **328** |

`statistics.html` là vấn đề **có sẵn** và nằm ngoài phạm vi lần này: chữ tối
trên nền bảng nhiệt bão hoà, màu do Python tính chứ không đi qua token. Tệp
`build_statistics_dashboard.py` không bị sửa và trang đó dùng **0** token đã
đổi; chênh lệch ±39 là biến thiên dữ liệu giữa hai lần dựng.

### Ba lỗi tôi gây ra và đã sửa

| Lỗi | Đo được | Sau khi sửa |
|---|---|---|
| Nhãn "Tool nâng cao" tràn khỏi viên thuốc dock | tràn 12px | 0px (nút co theo nhãn) |
| `--vla-on-brand` không lật cùng `--vla-brand` ở mẫu trang soi cầu | 1.80:1 | **10.38:1** |
| Điều hướng tôi thêm vào `live.html` dùng màu chế độ sáng trên nền tối | 3.66:1 | **10.49:1** |

Lỗi thứ hai đáng nói: mẫu `path_ui_page.html.j2` ánh xạ lại `--vla-brand` sang
xanh nhạt cho bảng màu tối nhưng để nguyên `--vla-on-brand: #ffffff`. Lỗi nằm
im cho tới khi dock trở thành thành phần đầu tiên dùng tới token đó.

### Một lỗi trong chính phép đo

Phép dò tương phản đầu tiên báo **5 564** lỗi AA. Nó sai ở ba chỗ mà trang này
dùng đúng cả ba:

1. **Nền gradient** — `backgroundColor` là trong suốt nên phải leo ngược cây và
   thường tìm nhầm.
2. **Cú pháp `color(srgb 1 1 1 / 0.84)`** — biểu thức chính quy tách số đọc
   thành 0–255 thay vì 0–1, biến nền dock trắng thành gần đen.
3. **`position: fixed`** — Chromium vẽ dock **một lần** lên ảnh chụp toàn
   trang, đè lên nội dung phía dưới nếp gấp và tạo lỗi giả ở những ô bình thường.

Phép dò cuối lấy **nền từ điểm ảnh** (miễn nhiễm gradient và trong suốt), **màu
chữ từ CSS đã tính** (đúng cả với nét mảnh), bỏ qua phần tử `fixed`, và chọn
nền là màu phổ biến nhất **khác** màu chữ — vì với tiêu đề đậm 58px, nét chữ
chiếm nhiều điểm ảnh hơn nền và thuật toán ngây thơ chọn phải chính màu chữ,
cho ra 1.00:1.

Con số thật sau khi sửa phép đo: **380 → 328**.

---

## 5. Điều hướng: 6 trang thôi là ngõ cụt

Trước thay đổi, bốn trang soi cầu, `research-lab.html` và `live.html` không có
phần tử `<nav>` nào — người đọc tới đó rồi không đi tiếp được đâu ngoài nút
back. Nay mọi trang đều có, và một phép kiểm canh điều đó:

```python
def test_no_page_is_a_navigation_dead_end() -> None:
    for page in PAGES:
        assert _soup(page).select("nav a"), f"{page.name} không có liên kết điều hướng nào"
```

`live.html` là tệp tĩnh viết tay, có `<style>` riêng và không dùng
`assets/vla.css`, nên dock không áp dụng được — nó nhận một danh sách phẳng
thay thế.

---

## 6. Còn tồn

* **`statistics.html`** — 328 lỗi AA có sẵn, chữ tối trên bảng nhiệt bão hoà.
  Cần đổi hàm tính màu trong Python, không sửa được bằng token.
* **Nhiều builder cùng ghi `docs/index.html`** — `build_docs.py`,
  `build_docs_ml.py` và `build_landing_page.py` đều ghi tệp đó, và
  `build_fun_prediction.py` chèn vào kết quả cuối. Chỉ thứ tự trong
  `pipeline.py` giữ cho nó không hỏng; chạy sai thứ tự thì `#mo-phong` rỗng.
  CSS ở §3.4 làm hậu quả bớt tệ nhưng không sửa được nguyên nhân.
