# Vietlott: đánh giá chuyên gia mẫu hình ngày 24-10-2026

Chưa có bằng chứng rằng nhóm mẫu hình cải thiện dự báo trên dữ liệu thật. Giữ `patterns=False` mặc định; nhóm mới là challenger bật tường minh. Không sản phẩm nào có cải thiện so với mô hình hiện hành hoặc luật công bằng đạt ý nghĩa thống kê trong lần chạy này.

## Phương pháp và nguồn dữ liệu

Hai cấu hình chạy trên cùng bản mã, cùng dữ liệu seed trong kho: 600 kỳ cuối mỗi sản phẩm, 400 kỳ khởi tạo và 200 kỳ chấm ngoài mẫu theo thời gian. Mỗi kỳ được dự báo và chấm trước khi học nhãn; chuyên gia uniform và quy tắc chấm vé hiện hành được giữ nguyên. Cả hai bật `multi_agent=True`, `adaptive=False`; chỉ cấu hình challenger bật thêm `patterns=True`. Không chọn lại tham số sau khi xem kết quả.

Đây là đánh giá hồi cứu thăm dò. Dữ liệu seed chỉ đến 30-09–02-10-2026 tùy sản phẩm; lượt chạy không đọc journal kết quả mới hơn, SQLite lưu trữ, checkpoint hoặc sổ live và không gọi collector. Ngày kỳ đích được coi là điều kiện biết trước. Keno/Bingo18 có ID thiếu và chưa có giờ từng kỳ được xác minh; không suy diễn chứng nhận live từ kết quả này.

| Sản phẩm | ID 200 kỳ được chấm | Từ ngày | Đến ngày |
|---|---:|---|---|
| Mega 6/45 | 1370–1569 | 2025-06-22 | 2026-09-30 |
| Power 6/55 | 1206–1405 | 2025-06-21 | 2026-10-01 |
| Lotto 5/35 | 721–920 | 2026-06-24 | 2026-10-01 |
| Keno | 297308–297782 | 2026-09-28 | 2026-10-02 |
| Bingo18 | 188600–189249 | 2026-09-28 | 2026-10-02 |
| Max 3D / 3D+ | 940–1139 | 2025-06-20 | 2026-09-30 |
| Max 3D Pro | 587–786 | 2025-06-21 | 2026-10-01 |

Mỗi nhánh có cùng hash lịch sử của từng sản phẩm và cùng manifest SHA-256 toàn bộ mã nguồn Python cùng runner:

`d321b2c43e55abed4c036fd87e4dd3a00421fe4ec1b9fc6825429bbd1e5f6a07`

## Kết quả

Điểm là trung bình log P(mô hình) − log P(công bằng), đơn vị nats/kỳ; dương tốt hơn. Chênh lệch ghép cặp là challenger trừ mô hình hiện hành. CI 95% dùng sai số chuẩn HAC theo kỳ. p một phía được tính bằng Diebold–Mariano; cột q hiệu chỉnh BH trên 14 so sánh thăm dò (7 sản phẩm × hai mốc so sánh). CI là CI từng phép so, chưa hiệu chỉnh đồng thời.

| Sản phẩm | Hiện hành so công bằng | Mẫu hình so công bằng | Mẫu hình − hiện hành | CI 95% của chênh lệch | q so hiện hành | q so công bằng |
|---|---:|---:|---:|---|---:|---:|
| Mega 6/45 | -0.000184 | -0.000839 | -0.000655 | [-0.005004; +0.003693] | 0.9937 | 0.9937 |
| Power 6/55 | -0.000295 | -0.000440 | -0.000145 | [-0.000563; +0.000272] | 0.9937 | 0.9937 |
| Lotto 5/35 | -0.000400 | -0.001107 | -0.000707 | [-0.002032; +0.000617] | 0.9937 | 0.9937 |
| Keno | -0.000580 | -0.000536 | +0.000044 | [-0.000292; +0.000379] | 0.9937 | 0.9937 |
| Bingo18 | -0.000322 | +0.000077 | +0.000399 | [-0.001987; +0.002785] | 0.9937 | 0.9937 |
| Max 3D / 3D+ | -0.001874 | +0.002890 | +0.004763 | [-0.019302; +0.028829] | 0.9937 | 0.9937 |
| Max 3D Pro | -0.003324 | -0.003287 | +0.000037 | [-0.004913; +0.004987] | 0.9937 | 0.9937 |

Mọi CI ghép cặp đều chứa 0. Điểm mẫu hình thấp hơn hiện hành ở Mega/Power/Lotto; cao hơn ở Keno/Bingo18/Max 3D/Max 3D Pro nhưng chưa đủ bằng chứng để kết luận cải thiện. Max 3D có mức tăng điểm lớn nhất (+0,004763 nats/kỳ), song CI [−0,019302; +0,028829] và p = 0,3487; so công bằng p = 0,4093. Brier của challenger tốt hơn công bằng chỉ ở Max 3D trong cửa sổ này; sáu sản phẩm còn lại kém hơn.

Brier là tổng lỗi bình phương biên trung bình của từng component, với nhãn chữ số chuẩn hóa theo số kết quả trong kỳ. Không diễn giải log-score/Brier thành phần trăm trúng, lợi nhuận hoặc cam kết thắng. Kết quả chưa đủ để bật mặc định; cổng live vẫn quyết định xác suất triển khai.

## Tái lập và artifact

Môi trường và phiên bản thư viện được lưu trong hai JSON. Thời gian thực tế mỗi nhánh: hiện hành 160,71 giây, challenger 167,31 giây; hai tiến trình chạy song song, toàn khoảng đo khoảng 195,71 giây. Đây là số đo của lần chạy, không phải SLA.

Chạy từ thư mục `vietlott/`, trên cùng mã nguồn và seed không thay đổi:

```bash
PYTHONPATH=src python scripts/evaluate_adaptive.py --seed-dir data/seed --output reports/vlm/pattern-learning-2026-10-24/baseline.json.gz --label current-multi-agent --multi-agent --draws 600 --initial-draws 400
PYTHONPATH=src python scripts/evaluate_adaptive.py --seed-dir data/seed --output reports/vlm/pattern-learning-2026-10-24/patterns.json.gz --label pattern-challenger --multi-agent --patterns --draws 600 --initial-draws 400 --compare-with reports/vlm/pattern-learning-2026-10-24/baseline.json.gz
```

Lần đo gốc chạy hai tiến trình độc lập, rồi dùng `vlm.forecast.evaluation.compare_runs` trên các JSON đã hoàn tất để ghép cặp. Mốc công bằng được dựng trên cùng ID/ngày/hash với `gain_nats=0`; BH trên 14 p-value được tính bằng `vietlott_engine.analytics.stats.benjamini_hochberg`. Kết quả ghép cặp nằm trong tệp riêng bên dưới. Lệnh tái lập tuần tự thêm `--compare-with` cũng ghi kết quả ghép cặp vào báo cáo challenger.

- [Nhánh hiện hành và điểm từng kỳ](baseline.json.gz).
- [Nhánh mẫu hình và điểm từng kỳ](patterns.json.gz).
- [So sánh ghép cặp, so công bằng, Brier, timing và hash dữ liệu](comparison.json).


## Kiểm chứng triển khai

- `python -m pytest -q -ra`: 873 kiểm thử đạt, 3 bỏ qua vì thiếu DuckDB CLI và hai backend tùy chọn XGBoost/LightGBM.
- 81 kiểm thử tích hợp VLA đạt, bao gồm trang Vietlott, summary và luồng làm mới trang.
- `ruff check --select F,B023 src scripts tests`: đạt; `git diff --check`: đạt.
- 9 đột biến hành vi bị phát hiện: 6 cho chuyên gia và 3 cho tích hợp. Reviewer độc lập đã kiểm đường nâng cấp/fit, checkpoint, kỳ thiếu và luật chấm trước học.
- Mã sau kiểm thử vẫn có cùng manifest với hai lượt benchmark; không sửa nguồn hoặc chọn lại tham số sau khi xem kết quả.
