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
