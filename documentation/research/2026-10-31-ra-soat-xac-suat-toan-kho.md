# Rà soát chuyên sâu xác suất và thống kê toàn kho (31-10-2026)

## Yêu cầu

Chủ dự án: "Rà soát chuyên sâu, hiệu chỉnh chuẩn các thuật toán, tăng tính chính xác của toàn bộ code,
tạo bộ code thành bộ code hoàn thiện có độ xác suất và tính chính xác cao nhất."

Kỳ quay đã kiểm là ngẫu nhiên, nên không thuật toán nào đẩy được xác suất trúng vượt mức của kỳ quay
công bằng (`scripts/research/audit_forecast_ceiling.py`). "Chính xác nhất" ở đây vì thế có nghĩa là:

- mọi con số in ra đúng định nghĩa;
- xác suất được hiệu chỉnh;
- p và q hợp lệ khi không có tín hiệu;
- không bảng nào khoe một ô may mắn như thể đó là xác suất kỳ sau.

## Cách kiểm

**Kiểm hiệu chỉnh trên lịch sử công bằng.** Ta dựng lịch sử quay giả lập đúng luật (27 lô đều trên
100 số, `forecast.multi_hit_forecast.mock_raw_history`). Sau đó chạy chính hàm thống kê của kho trên
lịch sử ấy và đòi hai điều:

- p phân phối đều;
- tỉ lệ đo được nằm ở đúng mức nền.

Hàm nào cho p dồn về 0 hay tỉ lệ lệch khỏi nền trên lịch sử không có tín hiệu thì đang in nhiễu
thành phát hiện.

**Đối chiếu hằng số và tổng.**

- Mọi mức nền so với `core.xsmb_domain`.
- Vector Đặc Biệt cộng lại phải bằng 1.
- Vector LOTO cộng lại phải bằng 100·(1 − 0,99²⁷) ≈ 23,77.
- Năm con đã công bố phải đúng là năm con được chấm.

**Bốn kịch bản chốt phát hành** chạy trên `main` trước khi sửa, đều xanh:

- `release_check.sh`
- `domain_challenger_check.sh`
- `number_integrity_check.sh`
- `research_release_check.sh`

## Phần đã đúng (không sửa)

| Hạng mục | Kiểm | Kết quả |
|---|---|---|
| Hằng số mức nền | `LOTO_BASELINE_RATE`, `DE_BASELINE_RATE`, `PAIR_COOCCURRENCE_RATE`, trần 4 950 cặp | đúng |
| Vector công bố | tổng Đặc Biệt = 1, tổng LOTO = 23,77 (`finalize_blend`) | đúng |
| p từng con (`significance_stats`) | 30 lịch sử × 1 500 kỳ, 3 000 p mỗi chế độ | LOTO: P(p < 0,05) = 5,10%, P(p < 0,01) = 0,70%. Đặc Biệt: 3,10% / 0,37% (rời rạc nên thận trọng) |
| FDR từng con | số con q < 0,05 mỗi lịch sử công bằng | TB 0,05 |
| χ² toàn cục | p < 0,05 ở 3,3% lịch sử (Đặc Biệt và mọi giải) | đúng mức, phía thận trọng |
| Đường gan LOTO (`hazard_stats`) | z của 900 ô so với mức nền | TB +0,012, độ lệch chuẩn 0,971, \|z\| > 3 ở 0,11% |
| Xác suất chính xác của sổ phỏng đoán (`prediction_board.base_probability`) | so với đếm thẳng | đúng |
| Năm con công bố = năm con được chấm | sổ phỏng đoán ↔ `vip.json` | khớp (kiểm toán Lô VIP cùng ngày) |

## Phần đã sửa

### 1. Bảng xác suất có điều kiện xếp theo tỉ lệ thô — lỗi chọn lọc

`stats.conditional_matrices` dựng ba bảng 100 × 100 ô:

- Đặc Biệt hôm trước → LOTO hôm sau;
- Đặc Biệt → Đặc Biệt;
- LOTO → LOTO.

Bảng cũ ghi 500 ô có **tỉ lệ thô** cao nhất, không kèm mức nền, không co, không hiệu chỉnh đa kiểm.
Trang chủ, trang Thống kê và `DASHBOARD.md` in phần đầu bảng. Riêng `DASHBOARD.md` còn gắn nhãn "Có mẫu
lịch sử tương đối tốt hơn".

Mỗi hàng của bảng Đặc Biệt chỉ có khoảng 42 kỳ, nên đầu bảng là ô may mắn nhất trong 10 000 ô:

| Bảng (dữ liệu đến 30-10-2026) | Ô đầu bảng cũ | Tỉ lệ thô | Mức nền | Sau co | q (FDR) |
|---|---|---|---|---|---|
| Đặc Biệt → LOTO | 42 → 96 | 21/40 = 52,5% | 24,0% | 24,0% | 0,94 |
| Đặc Biệt → Đặc Biệt | 88 → 93 | 5/48 = 10,4% | 0,94% | 1,02% | 0,92 |
| LOTO → LOTO | 94 → 10 | 300/1 035 = 29,0% | 24,7% | 24,7% | 0,97 |

Trên lịch sử quay công bằng giả lập (20 lịch sử × 4 250 kỳ), ô đầu bảng theo tỉ lệ thô đạt TB **53,4%**,
đúng như ô 52,5% của dữ liệu thật. Không ô nào của ba bảng thật khác mức nền sau hiệu chỉnh đa kiểm.

**Sửa.** Mỗi ô có thêm năm cột:

- `baseline_rate`: tỉ lệ số đích về ở kỳ sau trên mọi cặp kỳ liền nhau;
- `posterior_rate`: co về mức nền bằng Bayes thực nghiệm;
- `lift`: tỉ số `posterior_rate` / `baseline_rate`;
- `p_value`: một phía, nhị thức so với mức nền;
- `q_value_fdr`: Benjamini–Hochberg trên **mọi** ô đã kiểm, kể cả ô đếm 0 và ô không được ghi ra.

Bảng xếp theo p tăng dần. Các trang in tỉ lệ thô cạnh mức nền, ước lượng sau co và q, kèm một câu đọc
bảng suy từ q (`stats.conditional_reading.reading_note`), không viết cứng. Phần trang cần (cột in, ngưỡng, câu đọc) nằm ở mô-đun nhẹ ấy để trình dựng trang không kéo theo `ingest` và scipy.

**Vì sao một κ chung cho cả bảng, không κ riêng từng hàng.** Đo trên cùng 20 lịch sử công bằng:

| Cách co | Ô cao nhất sau co (nền 23,8%) | Tín hiệu cài sẵn "42 → 96 nửa số lần" (thật ≈ 62%) |
|---|---|---|
| Không co (bảng cũ) | 53,4% | 60,1% |
| κ riêng từng hàng (`fit_shrinkage_to_prior_rows`) | 30,6% | 32,2% |
| κ riêng từng hàng, chỉ khi hàng qua χ² | 26,3% | 25,5% |
| **κ chung cả bảng** (`fit_shrinkage_to_prior`) | **nền + 0,08 điểm %** | 24,2% |

Phương pháp mô men cho κ hữu hạn ở khoảng nửa số hàng ngay cả khi không có tín hiệu (docstring của
`fit_shrinkage_to_prior_rows` đã ghi điều này). Vì thế κ theo hàng vẫn khoe ô 30,6% trên lịch sử không có
gì.

κ chung co mạnh cả một ô có tín hiệu thật. Khi ấy **q là công cụ phát hiện**:

- tín hiệu "nửa số lần" bị q < 0,05 bắt ở 65% số lịch sử;
- tín hiệu "luôn luôn" bị bắt ở 100%.

`posterior_rate` là ước lượng thận trọng, không phải phép kiểm.

**Bản trùng.** `statistical_matrices._conditional_tables` từng tự đếm theo HÀNG kề nhau, tức nối cả hai
kỳ hai bên một ngày nghỉ, rồi xếp theo tỉ lệ thô. Pipeline ghi đè đầu ra ấy bằng `conditional_matrices`
ngay sau đó. Nhưng bước ghi đè được phép lỗi mềm, và khi nó lỗi thì bảng sai được xuất bản. Nay hàm ấy
gọi lại `build_conditional_tables`.

### 2. Kỳ vọng của bảng xếp hạng tần suất LOTO

`renderLotoFrequency` (`src/web/templates/stat_pages.js`) so **số nháy** của từng con với
`(1 − 0,99²⁷)·số kỳ`. Mức ấy là tỉ lệ có mặt ít nhất một lần, một phép đếm khác. Hệ quả là cột "So kỳ vọng"
bị thổi lên 27/23,77 ≈ 1,14 lần.

Trang `tan-suat-loto.html` vẫn in đúng 27/100·số kỳ, vì `frequency_bento.js` ghi đè ô sau mỗi lần dựng. Lỗi
này vì thế tiềm ẩn, nhưng có hai nguồn cho một con số.

Nay bộ máy dùng một hằng số `NHAY_PER_DRAW = 27 / 100`, chung với trang Tổng hợp, và đoạn vá đã gỡ.

### 3. Thứ tự dòng hoà điểm phụ thuộc CPU

`build_landing_page._sort_top` và `build_statistics_dashboard._table` dùng `sort_values` mặc định. Đó là
quicksort của numpy, không ổn định. Thứ tự các dòng hoà điểm phụ thuộc lệnh vector của CPU, nên cùng dữ
liệu mà runner CI và máy khác in hai dòng cầu cùng điểm theo thứ tự ngược nhau.

Nay cả hai dùng `kind="stable"`: dòng hoà giữ thứ tự của tệp.

### 4. Hằng số viết tay

`evaluation.confidence_matrix.BASE` là `1 − 0,99**27` viết tay. Nay nó đọc `LOTO_BASELINE_RATE`. Giá trị
trùng từng bit, nên phân vị null đã lưu vẫn hợp lệ và không cần tăng `STAT_VERSION`.

## Phép kiểm và đột biến

`tests/stats/test_conditional_matrices.py`:

- `test_a_fair_history_puts_no_cell_above_its_baseline`
- `test_a_planted_dependence_ranks_first_and_passes_fdr`
- `test_rows_are_ordered_by_evidence_not_by_raw_rate`
- `test_p_value_is_the_one_sided_binomial_tail_against_the_baseline`
- `test_fdr_counts_every_tested_cell_not_only_the_written_rows` (BH viết lại độc lập)
- `test_baseline_is_the_next_day_rate_over_exact_pairs_only`
- `test_the_reading_note_is_derived_from_the_table`
- `test_statistical_matrices_builds_the_same_calendar_safe_tables`

Phép kiểm trang:

- `tests/pages/test_markdown_dashboard.py::test_the_conditional_table_puts_the_raw_rate_beside_its_baseline_in_evidence_order`
- `tests/pages/test_landing_page.py::test_the_conditional_tables_print_the_baseline_and_fdr_beside_the_raw_rate`
- `tests/pages/test_landing_page.py::test_tied_rows_keep_their_file_order_on_every_machine`
- `tests/pages/test_statistics_dashboard_ui.py::test_highlighted_tables_keep_tied_rows_in_file_order`

Phép kiểm trình duyệt: `tests/frontend/frequency-overview.test.mjs`, «bảng xếp hạng LOTO so số nháy với
27/100 nháy mỗi kỳ…».

Đột biến: **15/15** làm phép kiểm tương ứng đỏ.

| Nhóm | Số đột biến | Đột biến |
|---|---|---|
| Bảng có điều kiện | 8 | bỏ co; κ nhỏ cố định; xếp theo tỉ lệ thô; p lệch một; BH bỏ ô đếm 0; mức nền trên mọi ngày; câu đọc bảng viết cứng; `statistical_matrices` cắt bảng riêng |
| Trang | 4 | markdown xếp theo tỉ lệ thô; ý nghĩa viết cứng; bỏ cột mức nền; mất nhãn |
| JS | 1 | kỳ vọng 1 − 0,99²⁷ |
| Sắp xếp | 2 | bỏ `kind="stable"` ở hai trình dựng |

## Còn mở — chủ dự án quyết

- `research.conditional_nextday` vẫn co bằng κ riêng từng hàng. Đầu ra của nó là bảng nghiên cứu có
  q đi kèm, không in lên trang chính. Muốn thống nhất thì đổi sang κ chung như trên.
- χ² "mọi giải" trên 30 lịch sử công bằng cho p < 0,05 ở 3,3%. KS đều có p = 0,028, lệch về phía thận
  trọng, nên chưa sửa.
