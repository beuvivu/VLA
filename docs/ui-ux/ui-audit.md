# Kiểm kê giao diện VLA

Cập nhật 2026-09-21. Nguồn: đo trực tiếp trên kho và trên Chromium.

## Lưu ý về phạm vi

Bảng audit mà mục VII của spec mô tả có các cột "Current layout", "Visual
defects", "Responsive defects" — dành cho việc *transform* một giao diện đang
có. Giao diện cũ đã bị xóa theo yêu cầu ngày 2026-09-21 (107 tệp, 82 800
dòng), nên **không có "current" để audit**. Bảng dưới đây vì thế là kiểm kê
trạng thái SAU khi dựng mới, với bằng chứng đo được cho từng trang.

## 29 trang, trạng thái thi hành

Cột "Dữ liệu" ghi hiện vật mà trang thực sự đọc. Không trang nào dùng dữ liệu
minh hoạ.

| # | Trang | Nhóm | Dữ liệu đọc | Trạng thái | QA |
|---|---|---|---|---|---|
| 1 | `index.html` | Tổng quan | `health.json` | xong | 7 viewport × 2 chủ đề |
| 2 | `dashboard.html` | Tổng quan | `predictions_today.json`, `predict_next_de_all_*.csv`, `weights_*.json` | xong | idem |
| 3 | `statistics.html` | Tổng quan | `advanced/freq_99d.json`, `advanced/overdue.json` | xong | idem |
| 4 | `thong-ke-tong-hop.html` | Tổng quan | `advanced/head_20d.json`, `tail_20d`, `total_20d` | xong | idem |
| 5 | `live.html` | Kết quả | `xsmb.csv` | xong, có giới hạn | idem |
| 6 | `so-ket-qua-truyen-thong.html` | Kết quả | `xsmb.csv` | xong | idem |
| 7 | `bang-dac-biet.html` | Đặc Biệt | `xsmb.csv` | xong | idem |
| 8 | `bang-dac-biet-thang.html` | Đặc Biệt | `advanced/special_month_board.json` | xong | idem |
| 9 | `bang-dac-biet-nam.html` | Đặc Biệt | `advanced/special_year_frequency.json` | xong | idem |
| 10 | `cau-giai-dac-biet.html` | Đặc Biệt | `advanced/conditional_special_after_special_top500.json` | xong | idem |
| 11 | `cau-dac-biet-theo-bo-so.html` | Đặc Biệt | `advanced/special_group_frequency_current.json` | xong | idem |
| 12 | `chu-ky-dac-biet.html` | Đặc Biệt | `cycle/cycle_de.csv` | xong | idem |
| 13 | `giai-dac-biet-theo-tong.html` | Đặc Biệt | `advanced/special_total_overdue.json`, `special_cham_overdue.json` | xong | idem |
| 14 | `giai-db-ngay-mai.html` | Đặc Biệt | `predict/predict_next_de_all_*.csv` | xong | idem |
| 15 | `tan-suat-loto.html` | Lô tô | `advanced/freq_99d.json` | xong | idem |
| 16 | `tan-suat-cap-loto.html` | Lô tô | `advanced/reverse_pair_frequency_current.json` | xong | idem |
| 17 | `cap-lon-loto.html` | Lô tô | `pairs/cap_loto_50_stats_loto.csv` | xong | idem |
| 18 | `dau-duoi-loto.html` | Lô tô | `advanced/head_tail_total_loto_current.json` | xong | idem |
| 19 | `lo-gan.html` | Lô tô | `advanced/overdue.json` | xong | idem |
| 20 | `ml_top10_loto.html` | Dự đoán | `predict/predict_next_loto_all_*.csv` | xong | idem |
| 21 | `ml_top10_de.html` | Dự đoán | `predict/predict_next_de_all_*.csv` | xong | idem |
| 22 | `model-quality.html` | Dự đoán | `model_quality/report.json`, `health.json` | xong | idem |
| 23 | `soi-path-loto-stable.html` | Soi path | `path_ui/paths_loto_stable.csv` | xong | idem |
| 24 | `soi-path-loto-active.html` | Soi path | `path_ui/paths_loto_active.csv` | xong | idem |
| 25 | `soi-path-de-stable.html` | Soi path | `path_ui/paths_de_stable.csv` | xong | idem |
| 26 | `soi-path-de-active.html` | Soi path | `path_ui/paths_de_active.csv` | **trạng thái rỗng** | idem |
| 27 | `research-lab.html` | Nghiên cứu | `research/bridge_scan_summary.json` | xong | idem |
| 28 | `landing.html` | (ngoài sidebar) | `health.json` | xong | idem |
| 29 | `landing_desktop.html` | (ngoài sidebar) | `health.json` | xong | idem |

## Hai trang có giới hạn, và giới hạn là THẬT

**`live.html` không phải luồng trực tiếp.** Giao diện cũ có một trang lấy dữ
liệu từ nguồn ngoài. Kho hiện KHÔNG có hợp đồng dữ liệu nào cho kết quả đang
về, nên trang mới hiện kỳ đã chốt gần nhất và nói thẳng điều đó. Dựng một
trang trông như trực tiếp mà không có nguồn là vi phạm mục XVIII.2.

**`soi-path-de-active.html` ở trạng thái rỗng** vì
`data/path_ui/paths_de_active.csv` chỉ có dòng tiêu đề — không có đường path
nào. Đó là sự thật về dữ liệu, không phải lỗi giao diện, và trang nói đúng như
vậy thay vì bịa hàng.

## Lỗi đã sửa trong quá trình dựng

| Lỗi | Tìm ra bằng | Sửa |
|---|---|---|
| Nút ba gạch vẫn hiện ở 1440px | Chromium | Luật ẩn đặt ở cuối, hai lớp `.vla-btn.vla-menu-button` |
| Liên kết điều hướng cao 39px | Chromium | `min-height: 40px` |
| `frame-ancestors` bị bỏ qua trong `<meta>` | Console Chromium | Gỡ khỏi CSP; ghi lại là giới hạn hạ tầng |
| Số KPI xuống hai dòng ở 1024px | Đếm số dòng | Mốc 4 cột chuyển lên 1280px |
| Tên tệp dài làm tràn trang ở 320px | Quét 420 lượt viewport | `overflow-wrap: anywhere` cho `<code>` |
| Tiêu đề lặp ở topbar và `<h1>` | Ảnh chụp | Topbar hiện TÊN NHÓM |
| 4 thẻ KPI xếp dọc chiếm ~580px trên điện thoại | Ảnh chụp | Lưới KPI riêng, 2 cột từ 360px |
| Đường cơ sở làm tròn khác nhau giữa các trang | Đột biến | Chuẩn hoá 3 chữ số thập phân |
| `so-ket-qua-truyen-thong` và `model-quality` thiếu cảnh báo | Đột biến | Thêm cảnh báo đúng bản chất từng trang |
