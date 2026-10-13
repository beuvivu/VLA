# Vietlott: kiểm chứng xác suất và số khớp H — Mega 6/45, Power 6/55

Giao thức đăng ký ngày 2026-10-13 (`vlm.forecast.hit_benchmark.PROTOCOL`). Walk-forward theo kỳ: mỗi kỳ được dự báo trước khi mô hình thấy kết quả; cấu hình challenger chọn trên dev, bỏ nhóm đặc trưng không ổn định qua các fold dev + validation, hiệu chuẩn trên validation, rồi chốt trước khi chấm test một lần. Δ log-score là log P(mô hình) − log P(công bằng) mỗi kỳ, gồm bộ chính và (Power) số đặc biệt chấm riêng; dương là tốt hơn công bằng.

## Kết luận

**Challenger chưa chứng minh lợi thế.** Không ứng viên nào đạt đủ năm điều kiện đề bạt đã đăng ký; giữ production: xác suất triển khai vẫn là luật công bằng (cổng live của bộ ML chưa mở), vé công bố giữ nguyên quy tắc hiện có.

## Mega 6/45

Dữ liệu #1–#1574 (2016-07-20 → 2026-10-11), `history_sha256` `909d636b858ec671…`, commit `b71aecce8b62`. Bỏ 300 kỳ đầu; dev #301–#937 (637 kỳ), validation #938–#1192 (255), test #1193–#1574 (2024-05-03 → 2026-10-11, 382 kỳ).

### Test (nhìn một lần)

| Nhánh | Δ log-score (nats/kỳ) | p tốt hơn công bằng | Brier − công bằng (×10⁶) | ECE (×10⁴) | H trung bình | H ≥ 3 | H ≥ 4 | H ≥ 5 | H = 6 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Công bằng (vé ngẫu nhiên chốt trước) | 0,000000 | — | 0,00 | 0,00 | 0,827 | 13 | 0 | 0 | 0 |
| Legacy đang chạy | -0,000613 | 0,9942 | 3,10 | 0,00 | 0,691 | 9 | 0 | 0 | 0 |
| Legacy + hiệu chuẩn τ | 0,000000 | 0,9808 | 0,00 | 0,00 | 0,691 | 11 | 0 | 0 | 0 |
| ML đang chạy | -0,000091 | 0,5960 | 0,45 | 0,00 | 0,775 | 9 | 0 | 0 | 0 |
| ML + hiệu chuẩn τ | -0,000261 | 0,6358 | 1,28 | 0,00 | 0,775 | 9 | 0 | 0 | 0 |
| Challenger co về công bằng | 0,000241 | 0,3609 | -1,25 | 0,00 | 0,767 | 8 | 0 | 0 | 0 |
| Challenger đặc trưng nhân quả | 0,000000 | 1,0000 | 0,00 | 0,00 | 0,741 | 7 | 0 | 0 | 0 |
| *Kỳ vọng siêu bội* | 0 | — | 0 | — | 0,800 | 9,10 | 0,53 | 0,011 | 0,0000 |

| Ứng viên | So với | Δ (nats/kỳ) | p một phía (DM HAC) |
|---|---|---:|---:|
| Legacy + hiệu chuẩn τ | Legacy đang chạy | 0,000612 | 0,0058 |
| Legacy + hiệu chuẩn τ | ML đang chạy | 0,000091 | 0,4043 |
| ML + hiệu chuẩn τ | Legacy đang chạy | 0,000352 | 0,3267 |
| ML + hiệu chuẩn τ | ML đang chạy | -0,000170 | 0,6738 |
| Challenger co về công bằng | Legacy đang chạy | 0,000854 | 0,0957 |
| Challenger co về công bằng | ML đang chạy | 0,000333 | 0,3302 |
| Challenger đặc trưng nhân quả | Legacy đang chạy | 0,000613 | 0,0058 |
| Challenger đặc trưng nhân quả | ML đang chạy | 0,000091 | 0,4040 |

### Chọn cấu hình (chỉ dev/validation)

- Co về công bằng: nửa đời 30, độ co 20, τ dev 0,096, τ validation 0,285.
- Đặc trưng nhân quả: λ = 10.0; ablation Δ trung bình theo nhóm: frequency -5,54·10⁻⁴ (bỏ), gap_lag -0,26·10⁻⁴ (bỏ), calendar -1,36·10⁻⁴ (bỏ), cooccurrence -0,74·10⁻⁴ (bỏ). Nhóm giữ lại: không nhóm nào — challenger trùng luật công bằng; τ validation 0,000.
- Hiệu chuẩn nhiệt độ trên validation: legacy τ = 0,0006, ML τ = 1,9994 (τ = 1: giữ nguyên; τ → 0: dữ liệu đòi co hẳn về công bằng).

### Công suất thống kê của H

| Mức | Tỷ lệ ngẫu nhiên | Hệ số tối thiểu phát hiện được (test, 80%, α = 5%) | Trên mọi kỳ đã chấm | Số kỳ cần để phát hiện ×2 | ×1,2 |
|---|---:|---:|---:|---:|---:|
| H ≥ 3 | 2,3834% | ×1,98 | ×1,52 | 355 | 6895 |
| H ≥ 4 | 0,1393% | ×8,01 | ×3,78 | 6502 | 120492 |

### H trên mọi kỳ đã chấm (mô tả; chỉ mô hình KHÔNG được chỉnh ở đây)

| Nhánh | Kỳ | H trung bình | H ≥ 3 (kỳ vọng) | H ≥ 4 (kỳ vọng) | p H ≥ 3 tốt hơn ngẫu nhiên |
|---|---:|---:|---:|---:|---:|
| Legacy đang chạy | 1274 | 0,750 | 30 (30,4) | 0 (1,78) | 0,5518 |
| ML đang chạy | 1274 | 0,794 | 22 (30,4) | 1 (1,78) | 0,9541 |
| Công bằng (vé ngẫu nhiên chốt trước) | 1274 | 0,794 | 38 (30,4) | 1 (1,78) | 0,0980 |

### Danh mục 5 vé của ML (ngân sách cố định 50.000 đ/kỳ)

| Đoạn | Kỳ | Trùng trung bình giữa hai vé | Độ phủ | Ít nhất một vé H ≥ 3 (ngẫu nhiên) | H ≥ 4 (ngẫu nhiên) | p H ≥ 3 (luôn hợp lệ) |
|---|---:|---:|---:|---:|---:|---:|
| test | 382 | 5,00 số | 33,3% | 23 (23,1) | 3 (1,75) | 0,4818 |
| all_scored | 1274 | 5,00 số | 33,3% | 72 (77,1) | 5 (5,83) | 1,0000 |

Mốc ngẫu nhiên tính chính xác trên chính bộ vé của từng kỳ. Danh mục học lại sau mỗi kỳ nên mốc phụ thuộc kết quả trước; p là e-process luôn hợp lệ cho xác suất dự đoán được, không phải Poisson–nhị thức.

Năm vé tốn năm lần tiền vé; xác suất "ít nhất một vé" cao hơn một vé là do mua nhiều vé, không phải dự báo tốt hơn.

## Power 6/55

Dữ liệu #1–#1409 (2017-08-01 → 2026-10-10), `history_sha256` `743b0454e9c6422a…`, commit `b71aecce8b62`. Bỏ 300 kỳ đầu; dev #301–#854 (554 kỳ), validation #855–#1076 (222), test #1077–#1409 (2024-08-22 → 2026-10-10, 333 kỳ).

### Test (nhìn một lần)

| Nhánh | Δ log-score (nats/kỳ) | p tốt hơn công bằng | Brier − công bằng (×10⁶) | ECE (×10⁴) | H trung bình | H ≥ 3 | H ≥ 4 | H ≥ 5 | H = 6 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Công bằng (vé ngẫu nhiên chốt trước) | 0,000000 | — | 0,00 | 0,00 | 0,664 | 6 | 0 | 0 | 0 |
| Legacy đang chạy | 0,000575 | 0,2145 | -1,85 | 0,69 | 0,730 | 5 | 0 | 0 | 0 |
| Legacy + hiệu chuẩn τ | 0,000000 | 0,1595 | 0,00 | 0,00 | 0,733 | 6 | 0 | 0 | 0 |
| ML đang chạy | -0,000514 | 0,8418 | 2,65 | 0,00 | 0,586 | 1 | 0 | 0 | 0 |
| ML + hiệu chuẩn τ | -0,000447 | 0,8352 | 2,34 | 0,00 | 0,586 | 1 | 0 | 0 | 0 |
| Challenger co về công bằng | -0,002005 | 0,9638 | 5,43 | 0,00 | 0,574 | 3 | 0 | 0 | 0 |
| Challenger đặc trưng nhân quả | -0,002433 | 0,9851 | 6,10 | 0,02 | 0,592 | 3 | 0 | 0 | 0 |
| *Kỳ vọng siêu bội* | 0 | — | 0 | — | 0,655 | 4,44 | 0,21 | 0,003 | 0,0000 |

| Ứng viên | So với | Δ (nats/kỳ) | p một phía (DM HAC) |
|---|---|---:|---:|
| Legacy + hiệu chuẩn τ | Legacy đang chạy | -0,000575 | 0,7854 |
| Legacy + hiệu chuẩn τ | ML đang chạy | 0,000514 | 0,1580 |
| ML + hiệu chuẩn τ | Legacy đang chạy | -0,001022 | 0,8809 |
| ML + hiệu chuẩn τ | ML đang chạy | 0,000067 | 0,1130 |
| Challenger co về công bằng | Legacy đang chạy | -0,002580 | 0,9273 |
| Challenger co về công bằng | ML đang chạy | -0,001491 | 0,8956 |
| Challenger đặc trưng nhân quả | Legacy đang chạy | -0,003008 | 0,9713 |
| Challenger đặc trưng nhân quả | ML đang chạy | -0,001919 | 0,9447 |

### Chọn cấu hình (chỉ dev/validation)

- Co về công bằng: nửa đời 500, độ co 20, τ dev -0,174, τ validation 0,429.
- Đặc trưng nhân quả: λ = 10.0; ablation Δ trung bình theo nhóm: frequency -2,08·10⁻⁴ (bỏ), gap_lag -10,78·10⁻⁴ (bỏ), calendar -4,77·10⁻⁴ (bỏ), cooccurrence 0,31·10⁻⁴ (giữ). Nhóm giữ lại: cooccurrence; τ validation 2,000.
- Hiệu chuẩn nhiệt độ trên validation: legacy τ = 0,0006, ML τ = 0,8950 (τ = 1: giữ nguyên; τ → 0: dữ liệu đòi co hẳn về công bằng).

### Công suất thống kê của H

| Mức | Tỷ lệ ngẫu nhiên | Hệ số tối thiểu phát hiện được (test, 80%, α = 5%) | Trên mọi kỳ đã chấm | Số kỳ cần để phát hiện ×2 | ×1,2 |
|---|---:|---:|---:|---:|---:|
| H ≥ 3 | 1,3329% | ×2,55 | ×1,74 | 637 | 12462 |
| H ≥ 4 | 0,0619% | ×14,49 | ×6,23 | 14647 | 271401 |

### H trên mọi kỳ đã chấm (mô tả; chỉ mô hình KHÔNG được chỉnh ở đây)

| Nhánh | Kỳ | H trung bình | H ≥ 3 (kỳ vọng) | H ≥ 4 (kỳ vọng) | p H ≥ 3 tốt hơn ngẫu nhiên |
|---|---:|---:|---:|---:|---:|
| Legacy đang chạy | 1109 | 0,645 | 13 (14,8) | 0 (0,69) | 0,7156 |
| ML đang chạy | 1109 | 0,629 | 13 (14,8) | 0 (0,69) | 0,7156 |
| Công bằng (vé ngẫu nhiên chốt trước) | 1109 | 0,644 | 18 (14,8) | 0 (0,69) | 0,2317 |

### Danh mục 5 vé của ML (ngân sách cố định 50.000 đ/kỳ)

| Đoạn | Kỳ | Trùng trung bình giữa hai vé | Độ phủ | Ít nhất một vé H ≥ 3 (ngẫu nhiên) | H ≥ 4 (ngẫu nhiên) | p H ≥ 3 (luôn hợp lệ) |
|---|---:|---:|---:|---:|---:|---:|
| test | 333 | 4,80 số | 26,7% | 3 (9,8) | 1 (0,61) | 1,0000 |
| all_scored | 1109 | 4,80 số | 26,7% | 32 (32,7) | 2 (2,04) | 0,3116 |

Mốc ngẫu nhiên tính chính xác trên chính bộ vé của từng kỳ. Danh mục học lại sau mỗi kỳ nên mốc phụ thuộc kết quả trước; p là e-process luôn hợp lệ cho xác suất dự đoán được, không phải Poisson–nhị thức.

Năm vé tốn năm lần tiền vé; xác suất "ít nhất một vé" cao hơn một vé là do mua nhiều vé, không phải dự báo tốt hơn.

## Điều kiện đề bạt (đã đăng ký)

- beats_fair_holm: Δ log-score so với công bằng trên test > 0, DM HAC một phía, Holm trên mọi ứng viên × sản phẩm, p < α
- beats_incumbents: Δ so với TỪNG mô hình đang chạy (legacy, ML) trên test > 0, DM một phía p < α
- validation_positive: Δ so với công bằng trên validation > 0
- stable_thirds: Δ so với công bằng > 0 ở ít nhất 2 trong 3 đoạn liền của test
- brier_not_worse: Brier biên trên test ≤ Brier công bằng
- then: Đạt cả năm: đủ điều kiện CHẠY THỬ TIẾN CỨU; xác suất triển khai chỉ đổi khi qua cổng live hiện có

| Ứng viên | Thắng công bằng (Holm) | Thắng legacy và ML | Validation dương | Ổn định 2/3 đoạn | Brier không kém | Đủ điều kiện |
|---|---|---|---|---|---|---|
| Mega 6/45 · Legacy + hiệu chuẩn τ | không (p Holm 1,0000) | không | không | không | không | **không** |
| Mega 6/45 · ML + hiệu chuẩn τ | không (p Holm 1,0000) | không | đạt | không | không | **không** |
| Mega 6/45 · Challenger co về công bằng | không (p Holm 1,0000) | không | đạt | không | đạt | **không** |
| Mega 6/45 · Challenger đặc trưng nhân quả | không (p Holm 1,0000) | không | không | không | đạt | **không** |
| Power 6/55 · Legacy + hiệu chuẩn τ | không (p Holm 1,0000) | không | không | đạt | đạt | **không** |
| Power 6/55 · ML + hiệu chuẩn τ | không (p Holm 1,0000) | không | đạt | không | không | **không** |
| Power 6/55 · Challenger co về công bằng | không (p Holm 1,0000) | không | đạt | không | không | **không** |
| Power 6/55 · Challenger đặc trưng nhân quả | không (p Holm 1,0000) | không | đạt | không | không | **không** |

