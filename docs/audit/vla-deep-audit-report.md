# VLA — Báo cáo soát sâu và gia cố sản xuất

Bản ghi đang mở. Mỗi mục dưới đây là thứ ĐÃ ĐO, không phải thứ suy ra từ đọc
mã. Mục nào chưa đo thì ghi rõ là chưa đo.

Nguyên tắc áp cho cả báo cáo: **một phát hiện chỉ được ghi là lỗi sau khi tái
hiện được**, và **một bản vá chỉ được ghi là xong sau khi đo lại**.

## 1. Trạng thái kho lúc bắt đầu

| | |
| --- | --- |
| Nhánh làm việc | `claude/statistical-audit-2026-09-lwfyt2` (PR #85) |
| Nhánh song song | `claude/dom-sinks-2026-09` (PR #86) |
| Mô-đun Python trong `src/` | 151 |
| Tệp JS (src + docs) | 11 |
| Tệp CSS (src + docs) | 13 |
| Trang xuất bản | 29 |
| Tệp phép kiểm | 135 |
| Workflow | 16 |
| Kịch bản | 21 |
| Kích thước `docs/` | 18 MB (`docs/assets/` 296 KB) |

Việc đang chạy khi chỉ thị soát tới, đã hoàn tất trước khi soát (§0):

- PR #86 — thay 15 cống HTML bằng `createElement` + `textContent`. Bộ kiểm
  2 187 xanh.
- PR #85 — khung ứng dụng hai cấp; gỡ 45 xung đột với `main`; vá lỗi khung
  đôi. Bộ kiểm 1 903 xanh.

## 2. Phạm vi đã soi

Đã chạy phép đo thật trên: 29 trang xuất bản (7 bề ngang, từ 1920 xuống 320),
`src/templates/stat_pages.js`, `src/templates/frequency_bento.js`,
`src/app_shell.py`, `src/build_landing_page.py`, `src/build_stat_pages.py`,
`src/ui_theme.py`, `docs/assets/*.js`, và bốn kịch bản chốt phát hành.

## 3. Phát hiện

### A-01 · P1 · Khung ứng dụng bọc hai lần trên `docs/live.html`

**Thành phần.** `src/app_shell.py::wrap_page`, `docs/live.html`.

**Tái hiện.** Mở `docs/live.html`, đếm `class="app-rail"` → 2. Đo bằng
`elementFromPoint` tại tâm nút tab đầu của dải: trả về
`<span aria-hidden="true">V</span>` của khung NGOÀI, và `nut.contains(span)`
là `false`. Tức mục điều hướng đầu tiên bấm không ăn.

**Gốc rễ.** `live.html` là trang duy nhất viết tay và commit thẳng, nên mỗi
lượt dựng đọc lại chính bản đã có khung rồi bọc tiếp. Chốt chặn cũ
`if "app-rail" in html: return html` ngăn được lần bọc thứ hai nhưng không
sửa được tệp đã hỏng.

**Bản vá.** Thay bằng `_go_khung`: bóc mọi lớp khung rồi mới bọc lại. Luỹ
đẳng và tự chữa.

Hai lỗi con chỉ lộ ra khi đo, không lộ ra khi đọc mã:

1. Regex đuôi khung khớp nguyên văn `<script src="…" defer>`. Trang đã xuất
   bản đi qua một lượt chuẩn hoá HTML **sắp lại thuộc tính theo thứ tự chữ
   cái**, nên thẻ ấy quay lại thành `<script defer="" src="…">`. Bản đầu
   trượt và làm index, landing, landing_desktop, live thành khung đôi — tệ
   hơn trước khi sửa.
2. Khung phía trong của `live.html` **không có thẻ kịch bản**: lượt chuẩn hoá
   gộp hai thẻ `src` trùng nhau lại làm một.

**Kiểm chứng.** 29/29 trang đúng một khung, bất biến qua hai lượt dựng liên
tiếp. Nút thu/mở bị che: 0 (trước là 1).

**Phép kiểm.** `test_no_published_page_carries_the_shell_twice` (đỏ trên
chính bản `live.html` hỏng lấy từ git) và
`test_wrapping_a_page_twice_gives_the_same_page` (ghim luật trên mẫu dựng
sẵn, nên vẫn đỏ được khi `docs/` đã sạch). Cả hai đã thử bằng đột biến.

**Trạng thái.** ĐÃ SỬA, ĐÃ KIỂM CHỨNG.

### A-02 · P2 · 1 309 trình nghe click gắn từng phần tử trên trang chủ

**Thành phần.** `src/build_landing_page.py` → `docs/index.html`,
`docs/landing.html`, `docs/landing_desktop.html`.

**Tái hiện.** Bọc `EventTarget.prototype.addEventListener` bằng một bộ đếm
trước khi trang chạy. Đếm được **1 339** lần gọi, trong đó **1 309** đến từ
một vòng `forEach` duy nhất: 1 000 `.matrix-cell`, 100 `.tiny-matrix-cell`,
88 `.num-link`, 44 `.bar-row`, 27 `.prize-number`, 27 `.fun-prize-number`,
20 `.fun-prob-row`.

**Gốc rễ.** `document.querySelectorAll('[data-number]').forEach(el =>
el.addEventListener(...))` — gắn từng phần tử thay vì uỷ quyền.

**Bản vá.** Một trình nghe ở `document` cộng `closest('[data-number]')`.

**Kiểm chứng.** Trình nghe **1 339 → 31**. Hành vi giữ nguyên: bấm lần lượt
bốn loại phần tử (`matrix-cell`, `tiny-matrix-cell`, `num-link`, `bar-row`)
đều đặt đúng con số vào `#inspect-num` và `#inspect-title`.

**Về tốc độ tải:** DOMContentLoaded trung vị 189,6 ms → 182,8 ms trên 7 lượt
mỗi bên. Khoảng dao động hai bên chồng nhau (cũ 164,9–235,1; mới
161,1–209,1), nên ở cỡ mẫu này **chênh lệch nằm trong nhiễu** và không được
tính là cải thiện tốc độ. Thứ đo được chắc chắn là số trình nghe và 1 308
closure không còn bị giữ lại.

**Phép kiểm.** `test_the_landing_page_delegates_clicks_instead_of_binding_every_cell`
và `test_every_number_element_on_the_landing_page_can_still_be_opened`. Đã
thử bằng đột biến.

**Trạng thái.** ĐÃ SỬA, ĐÃ KIỂM CHỨNG.

## 4. Những thứ KHÔNG phải lỗi, đã kiểm và loại trừ

Ghi lại để lần sau không ai mất công đi lại.

| Nghi vấn | Kết luận đo được |
| --- | --- |
| Quick Select "không hiện nội dung" (§8.3A) | KHÔNG phải lỗi. Nó nằm trong `<details class="bf-selection">` **đóng sẵn** — 104 nút, 1170×212 khi mở. "Bỏ hết" làm rỗng ma trận, "Tất cả" khôi phục **đúng bằng** số ô ban đầu. |
| Cặp số sai kiểu `77-77` thay vì `22-77` (§8.3C) | KHÔNG tái hiện được. `CAP50` có **50 cặp, không cặp tự lặp nào**; kép-bóng đúng `00-55, 11-66, 22-77, 33-88, 44-99`, trùng khít `test_domain_glossary`. Các chuỗi `NN-NN` trên trang là **nhãn ngày** dd-mm. |
| "Đổi chiều và sắp xếp không ăn" | LỖI CỦA PHÉP THỬ, không phải của trang. Bước trước đã bấm "Bỏ hết" làm ma trận rỗng nên hai bước sau không còn gì để đổi. Cô lập mỗi phép thử trên một lượt tải sạch thì cả ba đều OK. |
| Rò rỉ bộ nhớ (§5.3) | KHÔNG có. Sau 8 vòng dựng lại dữ liệu + mở/đóng dải + đổi chế độ màu, mức tăng của trình nghe / `setInterval` / `setTimeout` / `requestAnimationFrame` / `MutationObserver` / `ResizeObserver` / `IntersectionObserver` đều bằng **0** trên cả 7 trang đo. |
| Nút DOM phình ra (32 252 nút) | DỮ LIỆU, không phải rò rỉ. 2, 8 và 16 vòng thao tác đều dừng đúng ở 32 252. Rò rỉ thì phải tăng theo số vòng. Vẫn là gánh nặng hiệu năng, xếp P2. |
| `landing_desktop.html` tràn ngang ở ≤1200px | CỐ Ý, và có sẵn trên `main`. `body.desktop-view` đặt `min-width:1320px` — đây là trang "xem như máy tính" mà người dùng điện thoại tự chọn, nên cuộn ngang là mục đích của nó. |
| Lỗi console `InterVariable.woff2` | HIỆN VẬT của `file://`. Tệp phông có thật (176 KB) và CSP là `font-src 'self'`, nên trên HTTPS nạp bình thường. |
| CodeQL báo 14 cảnh báo cao trên PR #86 | KHÔNG do PR sinh ra. Trên cùng 14 trang, `innerHTML` đi từ **174 xuống 0** và không hạng mục rủi ro nào tăng. Số cảnh báo bám theo **số trang được ghi lại** (PR #85 dựng lại 29 trang → 28 cảnh báo; PR #86 dựng lại 14 → 14), đúng như ghi chú của chính CodeQL. |
| `github-advanced-security` đỏ | KHÔNG do PR sinh ra. Tác nhân chết ở bước gọi mô hình trước khi đọc tệp nào: `CAPIError: 400 The requested model is not supported`. Lặp lại y hệt trên ba head của PR #86 và trên PR #85 (diff hoàn toàn khác). Lỗi nằm trong dịch vụ của GitHub, không có bản vá nào trong kho sửa được. |

### A-03 · P3 · 12 KB CSS không trang nào nạp

**Thành phần.** `docs/assets/ui-part1.css`, `ui-part2.css`, `ui-part3.css`.

**Tái hiện.** Quét mọi `href`/`src` nội bộ của 29 trang: **0 trang** trỏ tới
ba tệp này. Kiểm đủ năm đường mà §X đòi:

| Đường tham chiếu | Kết quả |
| --- | --- |
| Trang xuất bản | 0/29 |
| `@import` trong CSS | không có |
| Phép kiểm | không nhắc |
| `scripts/extract_critical_css.py` | chỉ đọc `ui.css` |
| Trình dựng | không sinh ra — là tệp tĩnh commit thẳng |

Thứ duy nhất nhắc tên chúng là một chuỗi selector trong `css-async.js`, và
selector ấy chỉ khớp **nếu** có trang nạp chúng.

**Bản vá.** Gỡ ba tệp; gỡ luôn mệnh đề `ui-part` khỏi selector trong
`css-async.js`.

**Trạng thái.** ĐÃ GỠ.

### A-04 · P3 · Bốn tệp JS xuất bản không trang nào nạp — KHÔNG gỡ

Ghi lại thay vì gỡ, vì **đo cho thấy chúng không chết theo nghĩa thường**.

| Tệp | Kích thước | Ai phát ra |
| --- | --- | --- |
| `matrix-virt.js` | 6,5 KB | `scripts/optimize_index_dom.py` |
| `apply-data-styles.js` | 1,2 KB | `scripts/patch_csp_no_inline.py` |
| `ui-dock.js` | 2,0 KB | `src/web_security.py::security_script_tags` |
| `live-board.js` | 9,6 KB | không mã nào phát ra |

Hai sự thật đo được làm chúng thành ứng viên gỡ ở lần sau, chứ không phải
lần này: `security_script_tags` **không ai gọi**, và hai kịch bản kia
**không workflow nào chạy** — chúng là công cụ chạy tay. Gỡ tệp mà để lại
mã phát ra nó là để lại một cái bẫy; gỡ cả đường mã là một thay đổi rộng hơn
phạm vi lần soát này.

Ghi vào `NGOAI_LE` của `tests/test_published_assets.py` kèm lý do, nên chúng
không thể lặng lẽ trôi đi.

**Trạng thái.** ĐÃ GHI NHẬN, CHƯA GỠ.

### A-05 · Không có tham chiếu gãy

Quét 35 đường dẫn nội bộ trên 29 trang: **0** trang trỏ tới tệp không tồn
tại. Nay có `test_no_published_page_points_at_a_file_that_is_not_there` khoá
lại, cùng `test_every_published_asset_is_reachable_from_some_page` canh chiều
ngược. Cả ba phép kiểm của tệp ấy đã thử bằng đột biến, **kể cả đột biến làm
hỏng chính phép quét** — tập rỗng không lọt qua được.

## 5. Kết quả phép kiểm

| | |
| --- | --- |
| Nhánh #86 | 2 187 xanh |
| Nhánh #85 | 1 903 xanh |
| `number_integrity_check` | XANH |
| `domain_challenger_check` | XANH |
| `research_release_check` | XANH |
| `release_check` | XANH (nhánh #86); đang chạy trên #85 |

## 6. Còn lại, chưa làm

Ghi thẳng để không ai đọc nhầm báo cáo này thành "đã soát hết".

- **CSS** (§IV): chưa kiểm kê selector trùng, `!important` thừa, media query
  xung đột. 13 tệp CSS chưa được đo độ phủ.
- **Animation** (§VI): chưa đo CPU/GPU, chưa kiểm `prefers-reduced-motion`
  trên từng hiệu ứng.
- **Mã chết và tài nguyên thừa** (§X): chưa dựng bản đồ phụ thuộc đầy đủ.
- **Mạng và nạp dữ liệu** (§IX): chưa đo trùng lặp yêu cầu trên `live.html`.
- **Lighthouse / Core Web Vitals** (§13.1): chưa chạy. Môi trường phát triển
  mở trang qua `file://` nên LCP/INP/CLS đo được ở đây **không** đại diện cho
  bản chạy trên HTTPS; cần chạy trên runner Actions như đã làm với các phép
  đo trang tham chiếu.
- **Nền Crafto thu hẹp về riêng index/landing** (§4.2): chưa làm; hiện nền
  dùng toàn cục.
