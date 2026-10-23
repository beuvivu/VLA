# Hệ thiết kế giao diện

Tài liệu này ghi các quy tắc đã được **đo** chứ không phải được cảm nhận, cùng
tên phép kiểm canh giữ từng quy tắc. Mọi con số trong đây đều lặp lại được.

Lý do tài liệu tồn tại: các quy tắc này từng chỉ nằm trong chú thích mã, và một
thay đổi sau đó đã hạ một ngưỡng rồi tạo ra vùng lệch — không phải vì bất đồng
ý kiến, mà vì lý do nằm ở chỗ không ai đọc tới. Sửa một quy tắc ở đây thì sửa
luôn phép kiểm tương ứng, và ghi lại số đo mới.

## 1. Một nền dùng chung, các lớp phủ có phạm vi

Kiến trúc hiện tại **không còn là nhiều hệ CSS độc lập**. Mọi trang HTML xuất
bản trong `docs/` phải nạp cùng một nền từ:

```
src/web/ui_theme.py -> docs/assets/ui.css
```

Tại thời điểm chốt 15-09-2026, nền này được nạp trên toàn bộ **29 trang HTML**
đã xuất bản. Số 29 chỉ là ảnh chụp hiện trạng, không phải hằng số cần ghim vào
kiểm thử: thêm trang mới thì trang đó tự động rơi vào phạm vi kiểm tra.

Các trang vẫn được phép có **scoped overlay** cho nhu cầu dữ liệu riêng, nhưng
overlay chỉ được bổ sung lên shared base, không được thay thế nó:

| Lớp | Phủ | Vai trò |
|---|---|---|
| `src/web/ui_theme.py` -> `docs/assets/ui.css` | mọi `docs/*.html` | token, typography, shell, card, table, grid, dark mode |
| `src/pages/build_landing_page.py` | `index` / `landing` / `landing_desktop` | bố cục và trực quan riêng của trang chủ |
| `src/templates/stat_pages.css` | 14 trang thống kê chi tiết | ma trận, bộ lọc và trạng thái ô thống kê |
| `src/pages/build_statistics_dashboard.py` | `statistics.html` | ma trận nhiệt và dashboard thống kê tổng hợp |
| CSS nội tuyến của `live.html` | `live.html` | màu theo token dùng chung; base từ `ui.css`, khung từ `app_shell` |

`live.html` là ngoại lệ duy nhất còn được lưu như trang viết tay; hàm
`ui_theme.refresh_live_page()` chịu trách nhiệm đồng bộ khung điều hướng của
nó từ `SITE_NAV` để trang này không trôi khỏi hệ thống.

Dock chân trang đã nghỉ. Bộ bọc giữ khả năng sửa HTML lịch sử có khung lồng,
thẻ `main` bị chuẩn hóa thành `div` hoặc thứ tự thuộc tính bị đảo. Mỗi lượt
ghi chỉ giữ một khung, một `app-main` và nội dung nghiệp vụ bên trong.

Tên stylesheet chuẩn là **`assets/ui.css`**. `assets/vla.css` là tên cũ và
không được dùng lại.

Canh: `test_every_published_page_loads_the_shared_design_system`,
`test_no_published_page_references_the_retired_stylesheet_name`,
`test_every_published_page_carries_the_shell`,
`test_every_style_owner_declares_the_same_page_ground`,
`test_brand_ramp_is_identical_wherever_it_is_declared`.

## 2. Màu thương hiệu tách khỏi màu dữ liệu

Thương hiệu là `#4F46E5`, sắc **243°**. Không dấu hiệu mã hoá dữ liệu nào được
mang sắc trong phạm vi **40°** quanh nó — nếu không thì "đang chọn" và "giá trị
cao" trông như nhau.

```
blue    #2563eb   lệch  22°   KHÔNG dùng cho dữ liệu
purple  #7c3aed   lệch  19°   KHÔNG dùng cho dữ liệu
slate   #334155   lệch  28°   KHÔNG dùng cho dữ liệu
sky     #0891b2   lệch  52°   dùng được
green   #059669   lệch  82°   dùng được
rose    #e11d48   lệch 103°   dùng được
orange  #ea580c   lệch 137°   dùng được
```

Phải đo trên **trang đã dựng**, không trên bảng màu ở mã nguồn: màu ô sinh ra
bằng cách trộn hex trong Python nên đọc bảng màu không cho biết ô thật ra màu gì.

Canh: `test_landing_data_marks_never_borrow_the_brand_hue` (quét 417 dấu hiệu).

## 3. Một phép đo, một sắc

Bốn ma trận tần suất lô tô ngày/tuần/tháng/năm là **cùng một phép đo qua bốn cửa
sổ thời gian**. Cho chúng bốn sắc khác nhau là nói rằng đó là bốn loại dữ liệu.

```
tần suất lô tô   4 ma trận + 3 thẻ đầu/đuôi/tổng   green
tần suất ĐB      2 ma trận                         orange
```

Canh: `test_one_measure_uses_one_hue_across_its_time_windows`.

## 4. Thang liên tục và thang phân cấp

Thang **liên tục** (nhạt -> đậm) không được đổi sắc giữa chừng: đổi sắc là đọc
sai thứ tự. Trần tương phản của một thang liên tục với ba lựa chọn mực
(`#ffffff` / `#0f172a` / `#000000`) là khoảng **4,5:1** — đó là giới hạn cấu
trúc, không phải lỗi cấu hình.

Thang **phân cấp số nháy** là ngoại lệ có chủ ý, theo quy ước các trang XSMB:

| Cấp | Nền sáng / chữ | Nền tối / chữ | Tương phản sáng / tối |
|---|---|---|---|
| 1 nháy | `#FFF3CC` / `#714D0C` | `#3B311B` / `#F8D982` | 6,84 / 9,29 |
| 2 nháy | `#E0F2FE` / `#075985` | `#183647` / `#9DD9F3` | 6,59 / 8,24 |
| 3 nháy | `#DCFCE7` / `#166534` | `#173E30` / `#A0E3BC` | 6,49 / 8,04 |
| 4 nháy | `#F3E8FF` / `#6B21A8` | `#362647` / `#D9B6F4` | 7,39 / 7,83 |
| 5+ nháy | `#FFE4E6` / `#9F1239` | `#48212E` / `#F6B4C5` | 6,68 / 8,00 |

Bảng này cập nhật ngày 26-09-2026 từ token thực tế. Các tỷ số tính bằng
`ui_theme.contrast_ratio`, không phải nhận xét cảm quan.

Các sắc theo từng cấp **không có trật tự tri giác**, nên bảng màu này
BẮT BUỘC đi kèm chú giải; thiếu chú giải thì nó chỉ là màu, không phải thông tin.

Canh: `test_every_nhay_tier_has_a_distinct_pair_that_passes_aa`,
`test_nhay_legend_exists_because_the_ramp_has_no_perceptual_order`.

## 5. Dữ liệu thắng điều hướng

Sọc ngựa vằn và nền hover cùng vẽ `background` lên đúng ô mà cấp nháy dùng để
mang dữ liệu, và chúng cụ thể hơn nên chúng thắng — đo được ô "4 nháy" ở hàng
chẵn mất sạch nền cam, tức **một nửa số hàng bị xoá thông tin**.

Trợ giúp điều hướng trên bảng có mã màu phải dùng kênh khác nền: viền, vòng
trong, hoặc ô nhãn.

Canh: `test_zebra_and_hover_never_repaint_a_data_coloured_cell`,
`test_crosshair_covers_the_row_as_well_as_the_column`.

## 6. Ba trạng thái ô ma trận

Phân biệt bằng **hai** dấu hiệu, không riêng màu: độ sáng và độ nổi.

- **Không về** — nền phẳng, sẫm: `#0B1220` ở chế độ tối, `#E2E8F0` ở chế độ
  sáng. Không vân, không bóng.
- **Có về** — nền sáng hơn + vòng viền trong + bóng mỏng.
- **Giải ĐẶC BIỆT** — luôn đỏ, ở cả hai chế độ: `#BE123C`/`#FFE4E6` (5,24:1)
  sáng, `#FDA4AF`/`#4C0519` (8,27:1) tối. Giữ `#BE123C` ở nền tối thì chìm còn
  2,49:1.

Trước khi sửa, ô trống và ô có về cùng đứng trên nền trắng — **1,00:1**.

Màu ô lấy từ `--ui-empty-*`, `--ui-n1..n5-*`, `--ui-special-*`.
Các ô nháy tối dùng nền có kênh RGB lớn nhất dưới 100; chữ tương phản ít nhất
7,83:1. Phân cấp giữ sắc pastel nhưng giảm diện tích nền sáng rực khi đọc
ma trận dài. Không dùng vân chéo và không cho hover/zebra thay nền ô dữ liệu.

Canh: `test_empty_cell_sinks_by_tone_and_elevation_not_by_hatching`,
`test_hit_cell_rises_with_fill_ring_and_shadow`,
`test_special_prize_is_red_in_both_themes`.

## 7. Rãnh lưới phải có sàn tường minh

`1fr` trần trụi là `minmax(auto, 1fr)`: một bảng rộng nằm trong rãnh đó sẽ tự
nới rãnh ra và phá vỡ tỉ lệ đã định. Sàn có thể là `0` (cho phép co hết cỡ, kèm
cuộn bên trong) hoặc một số đo cụ thể — miễn là được **nói ra**.

Sàn cụ thể phải lấy từ bề rộng khối **thực sự cần**, không phải bề rộng thoải
mái của nó. Sàn quá tay đẩy ngưỡng lên cao và bỏ trống cả một dải bề rộng; sàn
cụ thể ở nơi không cần thì gây tràn trang (đo được `minmax(420px,...)` cho
`.matrix-top` làm tràn **+46px** ở khung 900px).

Canh: `test_top_row_columns_cannot_be_pushed_open_by_wide_tables`,
`test_matrix_columns_always_have_a_ceiling_of_one_fr`,
`test_shared_grids_never_let_a_child_force_the_page_wider`.

## 8. Ngưỡng tính theo KHUNG NỘI DUNG, không theo cửa sổ

Cửa sổ 1280px chỉ cho khung CSS khoảng **1265px** sau thanh cuộn. Một ngưỡng
`max-width: 1279px` vì thế bỏ sót đúng cỡ laptop phổ biến nhất.

Các ngưỡng liên quan phải **khớp nhau**. Khu bảng đường cầu từng có ngưỡng xếp
cạnh nhau ở 1024px trong khi ngưỡng thu hẹp cột ở 1280px, khiến cả dải
1024–1279px rơi vào trạng thái xấu nhất:

```
1440   628px/bảng   che 10%
1280   553px/bảng   che 21%
1265   546px/bảng   che 32%   <- lệch ngưỡng bắt đầu cắn
1024   445px/bảng   che 44%
```

Canh: `test_evidence_columns_are_balanced_by_a_sticky_panel`.

## 9. Chế độ máy tính đi theo lớp nền

`landing_desktop.html` chỉ khác `index.html` **đúng một lớp** trên thẻ `body`
(chênh 21 byte). Lớp `body.desktop-view` đặt `min-width: 1320px`, tức luôn rộng
hơn mọi ngưỡng của lớp nền, nên lớp nền tự cho ra bố cục đúng.

Dựng lại bố cục bằng `!important` ở lớp này là cách hai trang trôi khỏi nhau mà
mọi phép kiểm vẫn xanh — đã xảy ra một lần: `.inspector` giữ bố cục hai cột cũ
trên trang máy tính trong khi trang thường đã đổi sang xếp theo tầng.

Canh: `test_desktop_view_never_overrides_a_layout_the_base_sheet_defines`,
`test_desktop_page_differs_from_the_default_one_only_by_its_body_class`.

## 10. Thang 8pt ở cấp bố cục

Padding, gap và margin của các khối lấy từ `4 / 8 / 16 / 24 / 32 / 40 / 48`.
Padding **trong ô bảng** cố ý nằm ngoài thang: ép 8pt vào đó là hy sinh mật độ
dữ liệu, thứ mà các trang này tồn tại để cung cấp.

## 11. Theme và trạng thái điều hướng dùng chung

`app-theme.js` chạy trước CSS, đặt `.dark` theo màu thực tế. `data-ui-theme`
chỉ thể hiện lựa chọn light/dark; mặc định theo hệ điều hành. Không được
ghim lại token sáng trên body của một họ trang. CSS riêng chỉ alias token
chung; bản critical có đủ light/dark và media fallback.

Header Search mở dialog riêng bằng Ctrl/Cmd+K, phủ mọi đích SITE_NAV và các
phần trang chủ. Mở tìm kiếm không thay trạng thái menu. Chọn một đích là
điều hướng thật, giải phóng lớp phủ trên điện thoại.

Cập nhật 05/10/2026: nhóm chính đi theo luồng sử dụng dưới đây. Mỗi mục khai
một lần ở `SITE_NAV_SECTIONS`; `SITE_NAV` được suy ra để giữ hợp đồng của các
trình dựng và tìm kiếm. Menu con có cụm mang tiêu đề, không thêm tầng bấm.

| Thứ tự | Menu chính | Các cụm menu con |
|---|---|---|
| 1 | Kết quả | Kết quả ngày; tra cứu lịch sử |
| 2 | Thống kê | Tổng quan dữ liệu |
| 3 | Thống kê LOTO | Tần suất & phân bố; cặp số & chu kỳ |
| 4 | Thống kê Đặc Biệt | Bảng kết quả; tần suất & chu kỳ |
| 5 | Soi cầu | Vị trí & căn cứ; cầu LOTO; cầu Đặc Biệt |
| 6 | Dự báo | Mô hình AI/ML; tham khảo theo lịch sử; đánh giá dự báo |
| 7 | Nghiên cứu & công cụ | Kiểm định & nghiên cứu; tiện ích |

Rail hiện nhãn ngắn dưới biểu tượng và đánh dấu nhóm chọn bằng màu lẫn vạch.
Bảy nút nhóm nằm trong tablist theo đúng thứ tự trên; tìm kiếm và đóng nằm
riêng ở cuối. Chỉ nhóm đang chọn có `tabindex=0`; mũi tên và Home/End đổi
nhóm. Khung giữ số đo 80/240/80px và hành vi phủ lên nội dung.

Cập nhật 26/09/2026: rail/header dùng SVG Nexlink gốc (24px, opacity và nét
nguyên bản), sidebar dùng Flaticon Rounded từ đúng font của Nexlink chuyển
sang SVG. Nguồn và SHA-256: `src/assets/nexlink/provenance.json`. Header dùng
Instrument Sans, theme pill 74×40, ba icon inbox/bell/calendar và menu profile.

Icon nội dung/global search dùng Lucide canonical tự host: viewBox24, kích thước20px, stroke2,
currentColor. Hover/active dùng Indigo `#4F46E5` ở light và màu chữ nhấn sáng
đủ tương phản ở dark. Giữ giấy phép và provenance ở `src/assets/icons`.

Canh: `test_theme_script_is_local_synchronous_and_precedes_styles`,
`test_data_state_pairs_are_readable_in_each_theme`,
`test_renderer_keeps_uniform_geometry_and_accessibility`; các bộ kiểm
JavaScript tại `tests/frontend/theme.test.mjs` và `tests/frontend/search.test.mjs`.

## 12. Trải nghiệm thống kê, cập nhật 17/10/2026

Trang chủ và hai biến thể landing mở căn cứ số bằng **nhấp đúp**; nhấp đơn
vẫn chọn số ngay, bàn phím và nhấn giữ vẫn hoạt động. Các trang khác giữ
thao tác căn cứ riêng của chúng. Các hàng xác suất trang chủ chia cùng ba
rãnh 56px / phần còn lại / 72px. Hàng ba bảng ưu tiên bảng kết quả mô phỏng
theo tỷ lệ 2:1:1: bảng kết quả có sàn 400px, hai bảng dự báo có sàn 280px.
Khung hẹp cuộn bên trong, không đẩy rộng toàn trang.

Tần suất LOTO/cặp dùng cùng một ma trận với hai trục hoán đổi: Ngang đặt số
hoặc họ cặp theo hàng, ngày theo cột; Dọc đặt ngày theo hàng, số hoặc họ cặp
theo cột, mặc định trên điện thoại. Mỗi số có tổng lượt và đường diễn biến
ở nhãn hàng hoặc đầu cột, lấy đúng dải lọc và cùng trần lượt/kỳ. Đây là số
đo lịch sử, không phải xác suất dự đoán. Dấu chọn bám theo số/họ cặp và ngày,
không bám vị trí ô; lịch sử dài dựng theo vùng ngày đang xem. Demo và dữ
liệu thật có trạng thái lưu riêng. Bộ chọn chiều cũ vẫn làm cầu nối nội bộ,
không là giao diện chính.

Trang Đầu đuôi dùng màu xanh liên tục nhạt → đậm theo số lượt, với chữ đạt
AA trên từng màu nền ở cả sáng/tối. Đầu và Đuôi dùng chung trần màu; bảng
tổng và các kỳ gần đây có chú giải riêng, cập nhật theo bộ lọc. Dấu chọn
ưu tiên hơn màu tần suất. Hai bảng tổng giữ cột chữ số / số lần / tỉ lệ /
biểu đồ theo đúng 20% / 20% / 20% / 40%; tiêu đề xuống dòng trên điện thoại.

Cặp lộn đặt bảng 45 cặp và bảng 10 số kép song song từ 1024px, tỷ lệ 2,4:1;
khung hẹp xếp dọc và cuộn bên trong bảng. Cặp số / số kép lớn hơn hạng và
số lượt; giữ tông xanh cũ, không thêm vòng viền quanh số.

Cầu giải Đặc Biệt giữ số ma trận và cặp lộn ở 24px khi chọn / bỏ chọn;
nhãn Đầu và số lượt nhỏ hơn. Ma trận hiện đủ mười hàng, không giới hạn
chiều cao gây cuộn dọc nội bộ. Phạm vi CSS dùng `data-app-workspace-page`
vì trang này không có lớp `sp-page` cũ.

Trang Theo tổng đặt gan và chẵn/lẻ cùng hàng trên máy tính, bảng chuyển
tổng dùng trọn chiều ngang ở dưới. Cột gan chia 20/32/24/24%; chẵn/lẻ
20/20/30/30%; chuyển tổng 18/18/14/18/16/16%. Chữ số tổng dùng xanh cũ,
lớn hơn số kỳ, tỷ lệ và độ lệch; dấu chọn giữ nguyên cỡ chữ. Điện thoại
xếp thẻ dọc, hai bảng đầu co theo khung; bảng chuyển tổng cuộn ngang.

Dấu cặp dùng đúng định danh hai chữ số hoặc họ cặp, không đọc từ số nháy /
thứ hạng. Khi chọn cả cặp, dấu riêng của chính cặp ấy được hợp nhất để bỏ
chọn không bị kẹt. Dấu cặp đồng bộ qua sự kiện storage giữa các tab. Bảng
tuần bám tuần/ngày; các danh sách cặp lộn và số kép bám số/cột, giữ dấu khi
lọc hoặc đổi hạng. Ba trang thay khóa ô dùng phiên bản v3 để tránh nạp nhầm
tọa độ cũ; kho dấu cặp v1 toàn site được giữ nguyên.

`analysis_workspace.refine_workspace` đọc phạm vi từ điều hướng Soi cầu,
Dự báo, Nghiên cứu & công cụ, cộng các trang thống kê chi tiết được chỉ định.
Nó bổ sung phân cấp, hướng dẫn, bộ lọc và thẻ tại ranh giới `write_page`, giữ
nguyên ID, script và dữ liệu. CSS nguồn riêng được nhúng lại với một ID cố
định, nên cập nhật hằng ngày và làm mới trang đã bọc đều giữ đúng thiết kế.

`statistics.html#bang-db` có lịch Đặc Biệt theo năm, giữ đủ số gốc. Trên điện
thoại, mặc định xem tháng có kết quả mới nhất; luôn chuyển được về 12 tháng.
Năm/tháng và tìm số phối hợp cùng bộ đếm; ngày thiếu kết quả khác ngày không
tồn tại trong lịch. Màu đuôi và màu kết quả khớp bộ lọc dùng token semantic.

Điều chỉnh theo chủ dự án ngày 17/10: các số và điểm nhấn trang dùng lại
tông xanh dương cũ (`--ui-brand-ink`/`--ui-brand-soft`); biểu đồ dùng
`--ui-chart-1`. Bỏ viền và vòng sáng trang trí mới quanh số, kể cả khi chọn.
Trạng thái chọn dùng nền nhạt; chỉ tiêu điểm bàn phím giữ viền focus riêng.
Các điểm nhấn nâu mới cũng được gỡ: số giải đặc biệt trở lại đỏ
`--ui-special-ink`, nội dung phân tích dùng xanh cũ hoặc màu chữ vốn có.
Màu có ý nghĩa của ô nháy, cảnh báo và trạng thái dữ liệu vẫn theo chú giải.
