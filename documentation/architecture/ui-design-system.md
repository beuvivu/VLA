# Hệ thiết kế giao diện

Tài liệu này ghi các quy tắc đã được **đo** chứ không phải được cảm nhận, cùng
tên phép kiểm canh giữ từng quy tắc. Mọi con số trong đây đều lặp lại được.

Lý do tài liệu tồn tại: các quy tắc này từng chỉ nằm trong chú thích mã, và một
thay đổi sau đó đã hạ một ngưỡng rồi tạo ra vùng lệch — không phải vì bất đồng
ý kiến, mà vì lý do nằm ở chỗ không ai đọc tới. Sửa một quy tắc ở đây thì sửa
luôn phép kiểm tương ứng, và ghi lại số đo mới.

## 1. Bốn chủ thể tạo kiểu

Kho có **bốn** nơi phát sinh CSS độc lập. Một thay đổi giao diện chỉ chạm một
nơi sẽ không nhìn thấy được ở ba nơi còn lại.

| Chủ thể | Phủ |
|---|---|
| `src/ui_theme.py` → `docs/assets/vla.css` | 28 trang, gồm trang chủ |
| `src/templates/stat_pages.css` (nhúng thẳng) | 14 trang thống kê |
| `src/build_landing_page.py` (`:root` riêng) | `index` / `landing` / `landing_desktop` |
| `src/build_statistics_dashboard.py` (nội tuyến) | `statistics.html` |

Canh: `test_every_style_owner_declares_the_same_page_ground`,
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

Thang **liên tục** (nhạt → đậm) không được đổi sắc giữa chừng: đổi sắc là đọc
sai thứ tự. Trần tương phản của một thang liên tục với ba lựa chọn mực
(`#ffffff` / `#0f172a` / `#000000`) là khoảng **4,5:1** — đó là giới hạn cấu
trúc, không phải lỗi cấu hình.

Thang **phân cấp số nháy** là ngoại lệ có chủ ý, theo quy ước các trang XSMB:

```
1 nháy   #FFFFFF / #161C2D   16,96:1
2 nháy   #DBEAFE / #1D4ED8    5,49:1
3 nháy   #D1FAE5 / #047857    4,84:1
4 nháy   #FFEDD5 / #9A3412    6,38:1
5+ nháy  #5B21B6 / #FFFFFF    8,98:1
```

Xanh dương → xanh lá → cam **không có trật tự tri giác**, nên bảng màu này
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

Phân biệt bằng **ba** dấu hiệu, không riêng màu: nền, vân, độ nổi.

- **Không về** — nền đặc `#E2E8F0` + vân chéo `rgba(100,116,139,.38)`.
- **Có về** — nền sáng + vòng trong + bóng mỏng.
- **Giải ĐẶC BIỆT** — luôn đỏ, ở cả hai chế độ: `#BE123C`/`#FFE4E6` (5,24:1)
  sáng, `#FDA4AF`/`#4C0519` (8,27:1) tối. Giữ `#BE123C` ở nền tối thì chìm còn
  2,49:1.

Trước khi sửa, ô trống và ô có về cùng đứng trên nền trắng — **1,00:1**.

Canh: `test_empty_cell_sinks_with_solid_fill_and_visible_hatch`,
`test_hit_cell_rises_with_fill_ring_and_shadow`,
`test_special_prize_is_red_in_both_themes`.

## 7. Rãnh lưới phải có sàn tường minh

`1fr` trần trụi là `minmax(auto, 1fr)`: một bảng rộng nằm trong rãnh đó sẽ tự
nới rãnh ra và phá vỡ tỉ lệ đã định. Sàn có thể là `0` (cho phép co hết cỡ, kèm
cuộn bên trong) hoặc một số đo cụ thể — miễn là được **nói ra**.

Sàn cụ thể phải lấy từ bề rộng khối **thực sự cần**, không phải bề rộng thoải
mái của nó. Sàn quá tay đẩy ngưỡng lên cao và bỏ trống cả một dải bề rộng; sàn
cụ thể ở nơi không cần thì gây tràn trang (đo được `minmax(420px,…)` cho
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
