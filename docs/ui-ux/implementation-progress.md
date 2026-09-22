# Tiến độ giao diện

## 2026-09-22 — Quay về giao diện cũ, khôi phục từ git history

Chủ dự án nhận xét giao diện "Master Design System" tuy đẹp nhưng thiếu quá
nhiều thứ, và định xoá sạch mã trên GitHub để đẩy một bản backup cục bộ lên.
Không cần làm thế: **mã sinh ra giao diện cũ vẫn còn nguyên trong git
history**, nên phép quay về là một thao tác git, không phải một lần tải lên.

### Vì sao không chỉ tải HTML cũ lên

`docs/*.html` là SẢN PHẨM SINH RA, không phải nguồn. `src/pipeline.py` dựng
lại toàn bộ `docs/` mỗi lần chạy, nên HTML cũ đẩy lên sẽ bị ghi đè ngay ở lần
chạy kế tiếp. Muốn giữ giao diện cũ thì phải có lại mã sinh nó.

### Phép đo trước khi làm

| Đo | Kết quả |
| --- | --- |
| Commit xoá giao diện | `00cf02ea`, 120 tệp, 81 574 dòng |
| Tệp khôi phục được từ `00cf02ea^` | 107 |
| Trình dựng cũ chạy được trên dữ liệu thật | 12/12 |
| Trang dựng lại | 29/29, không thiếu trang nào |
| Bộ kiểm tại `00cf02ea^` (mốc gốc) | 22 đỏ / 2 156 xanh |
| Bộ kiểm ngay sau khi khôi phục | 19 đỏ / 2 164 xanh — **0 lỗi mới** |

Ba phép kiểm đỏ ở mốc gốc tự xanh lại sau khi dựng lại trang trên dữ liệu
hôm nay. Không có phép kiểm nào đỏ thêm vì phép khôi phục.

### Giữ lại, không quay về

- `src/ensemble_utils.weights_provenance` — hàm xuất xứ trọng số, thuộc tầng
  dữ liệu chứ không thuộc tầng trình bày.
- `.github/workflows/static.yml` vẫn bị xoá. Nó xuất bản GỐC KHO và thắng
  cuộc đua deploy với `pages.yml`, làm site 404.
- Dữ liệu và mô hình mới nhất (không tụt về bản cũ).

### Sửa thêm trong lúc khôi phục

**`docs/live.html` — mất bảng hiện số từ 20/09.** Truy theo từng commit:

    4a930ee2   revealQueue=3  workers.dev=1   ← bản lành cuối cùng
    b63a6105   revealQueue=3  workers.dev=0   ← CSP bị bóp lại
    30d9a074   revealQueue=0  workers.dev=0   ← mất luôn bảng
    bf6c6d5a   revealQueue=0  workers.dev=0   ← commit giao diện cuối

Tám phép kiểm đã đỏ từ trước vì việc này. Lấy lại `docs/live.html` ở
`4a930ee2` làm cả tám xanh.

**`a9ebeb29` đã cắt cụt hai trình dựng** (`build_dashboard.py` −215 dòng,
`build_traditional_results.py` −317 dòng, chỉ thêm 5). Chuỗi commit "restore
from known-good" sau đó dựng lại chúng từ một bản ĐÃ MẤT DẤU TIẾNG VIỆT, nên
trang xuất bản đọc là "Bang dieu khien phan tich XSMB", "Thu hai". Đã phục
hồi dấu: 20 chuỗi trong `build_dashboard.py`, và lấy lại nguyên tệp
`build_traditional_results.py` ở `2d1c26cb` (giữ thay đổi `css_links`).

**`_attach_visual_system` không phải điểm bất động.** Luật bóc thẻ `<link>`
trần chạy TRƯỚC luật bóc khối `<noscript>`, nên nó ăn mất chính cái `<link>`
nằm trong `<noscript>`; luật sau không còn gì để khớp và một
`<noscript></noscript>` rỗng ở lại sau mỗi lần ghi. Đã đảo thứ tự, đã thử
bằng đột biến (đảo lại → đỏ).

**`test_every_published_page_receives_same_skin` đếm sai.** Nó đòi đúng MỘT
thẻ `link[data-ui-visual-system]`, trong khi trang đúng có hai: thẻ tải và
bản dự phòng trong `<noscript>`. Phép kiểm đỏ với trang hoàn toàn đúng, và
đồng thời không thấy trường hợp hỏng thật (một thẻ tải nhân đôi vẫn cho tổng
bằng 2). Đã tách hai phép đếm. Đột biến: nhân đôi thẻ tải → đỏ.

**`ensure_critical_css_file` chưa từng được gọi ở đâu.** `docs/assets/
critical.css` là hiện vật chép tay đứng im — còn mang chú thích
`/* critical shell ... */` mà nguồn không có, và trôi khỏi `CRITICAL_CSS` mà
không dấu hiệu gì. Đã nối vào đường ghi trang, cùng chỗ với
`ui-visual-system.css`.

### Xoá bốn workflow vá một lần

`optimize_dom.yml`, `patch_css_links.yml`, `patch_csp.yml`,
`hotfix_ui_csp.yml` đều có `contents: write`, tự sửa mã nguồn hoặc `docs/`
rồi tự đẩy lên. Chúng kích hoạt theo `paths:` trỏ vào chính những tệp mà
phép khôi phục này chạm tới, nên một lần đẩy sẽ khởi động bốn con bot cùng
ghi vào `main`. Đây đúng loại lỗi đã gây ra sự cố `static.yml`. Việc chúng
cần làm đã nằm sẵn trong mã và trong `docs/`; và `optimize_dom.yml` chạy
script cần `numpy`/`pandas`/`scipy` mà không cài — nó sẽ vỡ ngay
(`test_every_workflow_installs_what_its_python_scripts_import` bắt được).

### Tách mã xuất xứ khỏi câu chữ

`test_the_card_states_the_provenance_the_stored_record_actually_supports` có
docstring nói rõ "không ghim mặt CHỮ của câu xuất xứ", rồi dò
`"mac dinh" in card["nguon"]` — tức ghim đúng mặt chữ. Chỉ thêm lại dấu tiếng
Việt vào nhãn là nó đỏ, trong khi hành vi không đổi một ly nào.
`_effective_weights` nay trả thêm `xuat_xu` là MÃ (`da_hoc`, `bi_tu_choi`,
`mac_dinh_dat_tay`, `da_hoc_chua_co_cong`); phép kiểm đọc mã. Đột biến:
`bi_tu_choi` → `da_hoc` → đỏ.

## Kết quả cuối

| Phép đo | Trước (mốc `00cf02ea^`) | Sau |
| --- | --- | --- |
| `pytest tests` | 22 đỏ / 2 156 xanh | **0 đỏ / 2 175 xanh** |
| `release_check.sh` | đỏ | xanh |
| `domain_challenger_check.sh` | — | xanh |
| `number_integrity_check.sh` | — | xanh |
| `research_release_check.sh` | — | xanh |
| Trang dựng được | 29 | 29 |

Bản khôi phục **xanh hơn chính bản gốc mà nó khôi phục**: 22 phép kiểm đã đỏ
ở mốc gốc nay xanh hết.

## Việc chưa làm

- `docs/ui-ux/VLA_MASTER_UIUX_SPEC.md` giữ lại để tham chiếu. Chưa có hiệu
  lực; chờ chủ dự án quyết định bắt đầu lại phần thiết kế.
- `build_fun_prediction.py` làm hai việc: lấy mẫu (dữ liệu) và chèn bảng vào
  ba trang HTML (trình bày). Vì thế `--skip-docs` bỏ luôn phép lấy mẫu. Tách
  đôi là việc riêng.
- `build_dashboard._effective_weights` lặp lại logic của
  `ensemble_utils.weights_provenance`, nhưng phân biệt thêm một trường hợp
  thứ tư (vector đã học từ trước khi có cổng đề bạt) mà hàm chung gộp vào
  `khong_co_ho_so`. Gộp hai bên là đổi hành vi, không phải dọn dẹp.
- 14 trang thống kê do `build_stat_pages.py` sinh ra dùng `.innerHTML`.

## 2026-09-22 (2) — Áp ngôn ngữ thị giác của trang tham chiếu lên cả 29 trang

Chủ dự án đưa một trang mẫu và yêu cầu dùng nền, hiệu ứng và toàn bộ UI/UX của
nó cho `index` / `landing_desktop` và các trang còn lại.

### Đọc trang mẫu: proxy chặn, đi qua runner Actions

Trang mẫu trả **403 ngay ở tầng CONNECT** với cả `curl` lẫn trình lấy trang —
giống năm trang tham chiếu trước. Runner của Actions không bị chặn, nên thêm
`scripts/inspect_reference_design.py` và
`.github/workflows/inspect-reference-design.yml`: chúng in SỐ ĐO thị giác (mã
màu theo tần suất, gradient, `box-shadow`, `border-radius`, `font-family`,
`@keyframes`, `transition`, `filter`) chứ không lưu HTML/CSS/hình của họ vào
kho. Trang mẫu là sản phẩm thương mại có bản quyền, và kho này viết CSS tay
không framework, nên bê tệp của họ về vừa sai vừa không dùng được.

Ba lần chạy mới ra đủ dữ liệu, và hai lần đầu hỏng vì lỗi của công cụ:

1. Lần 1 không in `--primary-font`/`--alt-font` — trang mẫu khai **508 biến
   CSS**, gần hết là `--bs-*` của Bootstrap, nên khung in 60 dòng chỉ toàn
   framework.
2. Lần 2 in ra nhưng không đọc được: log của Actions chỉ lấy về được phần
   cuối (tải trọn tệp log cũng bị proxy chặn 403), mà ba mục cần thì nằm giữa.
   Phải đưa chúng xuống cuối.

### Số đo thu được

| Hạng mục | Trang tham chiếu |
| --- | --- |
| Phông | `--primary-font: 'Inter'`, `--alt-font: 'Plus Jakarta Sans'` |
| Nhấn | `--base-color #2946f3`, `--majorelle-blue #724ade` |
| Nền | `--solitude-blue #f0f4fd`, `--selago #eaedff` |
| Bóng | luôn đen 8%: `0 0 10px`, `0 0 25px`, `0 20px 60px` |
| Bo góc | 16px (thẻ) ×9, 50px (viên thuốc) ×8 |
| Nhịp | `.3s` ×107; `cubic-bezier(.12,0,.39,0)`, `(.37,0,.63,1)` |
| Quầng | `filter: blur(20px)` / `blur(30px)` |
| `clamp()` | **0** — họ dùng breakpoint, không dùng thang co giãn |

Phông: giữ **Inter tự host**. Không thêm Plus Jakarta Sans vì CSP đặt
`font-src 'self'` và proxy không tải được tệp phông về để tự host. Đây là
thiếu sót đã biết, không phải bỏ qua.

### Chỗ KHÔNG lấy nguyên

Màu chữ mờ của họ, `--medium-gray #717580`, chỉ đạt **3,96:1** trên nền
`#eaedff` — trượt AA. `--green #2ebb79` đạt 2,24, `--golden-yellow #fd961e`
đạt 1,99, `--red #dc3131` đạt 4,21: đó là màu TÔ, không phải màu CHỮ. Lấy sắc
độ, đo lại độ đậm: chữ mờ `#5c6270` (5,25 trên nền tối nhất), trạng thái
`#12744a` / `#8f5608` / `#c62828`.

### Bốn bản sao của màu nền

Màu nền trang hoá ra có **bốn** bản: `ui_theme.py`, `critical_css_generated`,
bản dự phòng trong `css_links.py`, và một chuỗi ghim cứng trong
`scripts/extract_critical_css.py`. Bản thứ tư không ai canh, nên sau khi đổi
bảng màu thì **khung vẽ đầu tiên vẫn là nền cũ**. Nay cả hai chỗ sinh CSS tới
hạn đều đọc `var(--ui-bg)`, và hai phép kiểm canh việc đó.

### Phép kiểm tương phản: tự nó từng không thể đỏ

`test_text_on_brand_background_flips_with_the_theme` ghim hằng `"#4f46e5"` và
`"#8b93f8"` — nó kiểm hai con số do chính nó viết ra, nên đổi `--ui-brand`
sang màu KHÔNG đạt chuẩn thì vẫn xanh. Nay nó đọc token thật. Trong lúc viết
lại, đột biến còn lộ hai lỗi trong chính phép kiểm mới:

1. Phép đếm ngoặc bắt đầu từ *bên trong* khối nên không đóng đúng chỗ, ăn sang
   các khối sau, và vì `dict` lấy giá trị cuối cho khoá trùng, `_tokens(":root{")`
   trả về bảng màu chế độ **TỐI**.
2. Chú thích trong khối nhắc tên token bằng đúng cú pháp khai báo
   (`... cùng lúc với --ui-brand: ở chế độ tối`), nên phép dò bắt luôn đoạn văn
   đó làm giá trị và `--ui-on-brand` biến mất khỏi bảng.

Thêm `test_both_dark_blocks_declare_the_same_tokens`: khối `@media
prefers-color-scheme` và khối `[data-ui-theme="dark"]` phải trùng nhau — đột
biến chứng minh lỗ này bằng cách đổi `--ui-on-brand` chỉ ở một khối mà bộ kiểm
vẫn xanh.

### Đo trên trang đã render, không suy từ CSS

Soi 14 trang × 3 khổ × 2 chế độ = 84 trường hợp bằng Chromium thật. Hai lần
đầu thước đo sai:

1. Đầu dò leo cây DOM tìm `backgroundColor` — sai ở mọi nền gradient, vì màu
   nằm ở `background-image`. Nó báo chữ trắng trên dải xanh là **1,00:1**.
2. Đầu dò lấy màu nền từ pixel 3px phía trên hộp chữ — đụng viền, cạnh bóng và
   thẻ bên cạnh, nên **báo quá**.

Cách dùng đúng một thước đo nhiễu là đo **so sánh** trên cùng thước, hai cây
mã. Kết quả:

| Phép đo | Trước | Sau |
| --- | --- | --- |
| Trường hợp có vấn đề | 71 | 65 |
| Tổng lượt chữ trượt AA | 235 | **180** |
| Tràn ngang | 4 | 4 |
| Trường hợp xấu đi | — | **0** |

### Hồi quy do chính thay đổi này, đã tìm và sửa

- Khối "chỉ-sáng" trong skin ghim nền/mực/thương hiệu nhưng **bỏ sót màu trạng
  thái**, nên ở chế độ tối `--ui-ok`/`--ui-bad` vẫn lật sang bản dành cho nền
  tối trong khi bề mặt đã bị ghim trắng: `#4ade80` trên `#f7f7f7` = 1,63:1,
  `#fb7185` trên `#ffffff` = 2,69:1.
- Chữ nhạt trên dải hero được chọn cho màu chàm cũ nhạt hơn. Với `#2946f3` nó
  tụt còn 3,49–4,40:1. Nâng lên `#F8F9FF` (4,55:1 trên điểm hero bất lợi nhất
  đo từ pixel).
- Nền mới (`#eaedff`) sâu hơn nền cũ (`#f4f5ff`), nên 30 tông xám vốn đã sát
  ngưỡng bị đẩy xuống dưới. Đậm lại theo phép đo, giữ sắc độ, chỉ ở những khai
  báo `color:` — cùng một mã màu còn làm nền và viền ở nơi khác.

Bốn trang thiếu trong hợp đồng "chỉ-sáng" (`dashboard`, `model-quality`,
`ml_top10_*`, `bang-dac-biet`) khiến chữ `#e8eef6` nằm trên nền `#ffffff` =
**1,17:1**, vô hình hoàn toàn ở chế độ tối. Đã thêm vào danh sách. Lối sửa
đúng về lâu dài là cho CSS riêng của chúng đọc token.

## Còn lại, chưa sửa — đều có TRƯỚC thay đổi này

Đã kiểm chứng bằng cách chạy cùng phép đo trên cây mã trước khi sửa:

- **180 lượt chữ trượt AA** theo đầu dò pixel. Thước này báo quá (xem trên),
  nên con số thật thấp hơn; nhưng nó giảm 23% và không có trường hợp nào xấu đi.
- **4 trường hợp tràn ngang**, y hệt trước.
- **Dock nổi che chữ ở khổ 390px**: `index` che 2 mục, `landing_desktop` 2,
  `statistics` 1. Đo trước/sau giống hệt từng con số — `padding-bottom` của
  `body` là `0px` nên không chỗ nào dành sẵn cho dock.
- Phông tiêu đề `Plus Jakarta Sans` chưa có (CSP `font-src 'self'`, proxy
  không tải được tệp về).
