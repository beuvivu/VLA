# Rà các bước tự hiệu chỉnh của chuỗi dự báo — 15-11-2026

Yêu cầu: «đảm bảo việc hiệu chỉnh các bước thống kê đạt tối ưu và tự động điều chỉnh hợp lý nhằm đạt
kết quả cao nhất». Bản này ghi từng bước tự học của chuỗi dự báo XSMB: nó tối ưu thước đo nào, nó tự
điều chỉnh ra sao khi có kỳ mới, trạng thái ngày 15-11-2026, và khi nào nó tự bật thêm.

## «Kết quả cao nhất» ở đây là gì

Thước đo là log-loss / Brier NGOÀI MẪU của chính vector xác suất đã công bố, so với dự báo hằng số
(LOTO 1 − 0,99²⁷ ≈ 23,77%, Đặc Biệt 1%). Kỳ quay đã kiểm là ngẫu nhiên, nên mốc tốt nhất đạt được về
kỳ vọng là KHÔNG THUA hằng số. Một dự báo «nhọn» hơn mà không có tín hiệu thật thì log-loss tệ hơn
(ngày 25-09-2026 tổ hợp làm nhọn a = 4,89 và thua cả hằng số). Vì thế mọi bước dưới đây đều co về
nền khi không có bằng chứng, và chỉ rời nền khi thắng hằng số trên lát chưa chạm.

Số đo ngày 14-11-2026 (`data/evaluation/model_quality/report.json`, 78 kỳ đã công bố):

| | Kỹ năng log-loss trung bình | Khoảng 95% | Độ nhọn (khoảng quanh nền) |
|---|---|---|---|
| LOTO | −4,2·10⁻⁵ | −1,8·10⁻⁴ … +9,8·10⁻⁵ | ±0,17% |
| Đặc Biệt | +6,1·10⁻⁵ | −1,1·10⁻³ … +1,2·10⁻³ | ±1,2% |

Kỹ năng không phân biệt được với 0 ở cả hai, `skill_monitor` ở `vung_0` (z = 3, 60 kỳ). Dự báo đã
công bố đang ở mức tối ưu đạt được: bằng hằng số trong sai số đo.

## Từng bước

| Bước | Tối ưu gì, đo ở đâu | Tự điều chỉnh khi có kỳ mới | Trạng thái 15-11 | Tự bật thêm khi |
|---|---|---|---|---|
| Trọng số tổ hợp (`learn_ensemble_weights`) | log-loss ngoài mẫu; đề bạt chỉ khi thắng vector MẶC ĐỊNH ≥ 0,20% trên lát thẩm định | học lại mỗi lượt trên 180 ngày, bán rã 45 ngày | 41 ngày đủ năm thành phần; ứng viên thắng 0,0000% (LOTO), 0,0365% (Đặc Biệt) → giữ mặc định | luôn chạy; đề bạt ngay khi một thành phần thật sự có kỹ năng |
| Hiệu chỉnh xác suất (`calibration`) | Brier trên khối giữ riêng, có ứng viên `identity` | chọn lại mỗi lượt trên lát SAU lát trọng số | 17 ngày < 60 → giữ phép đồng nhất | lát hiệu chỉnh là 40% số ngày: đủ 60 khi có ≈ 150 ngày đủ năm thành phần (≈ đầu tháng 3-2027) |
| Xếp chồng (`meta_predictor`) | phải thắng CẢ tổ hợp tuyến tính LẪN hằng số | học lại mỗi lượt, chọn tầng thành phần đủ 100 ngày | LOTO chưa tầng nào đủ 100 ngày; Đặc Biệt học tầng ba thành phần, thua hằng số → trust 0 | tầng năm thành phần đủ 100 ngày ≈ đầu tháng 1-2027 |
| Học trực tuyến Hedge (`online_learning`) | log-loss, hai trí nhớ (nhanh/chậm), chia cố định 3% | cập nhật mỗi kỳ | 48 kỳ đã chấm; tổn thất các chuyên gia gần bằng nhau | cổng đề bạt cần 60 kỳ: ≈ 27-11-2026 (sổ ba tác tử: 26 kỳ, ≈ giữa tháng 12) |
| Độ tin thành phần (`model_trust`) | `trust = clip(20·s, 0, 1)`, s là kỹ năng thẩm định so với nền | học lại cùng mô hình | ML trust 0; Cầu Kèo theo gói | tự tăng khi kỹ năng thẩm định dương |
| Neo mức LOTO (`finalize_blend`) | Σp = 23,77 (kỳ vọng số con khác nhau mỗi kỳ) | không có tham số học | luôn áp | — |
| Kho tri thức (`knowledge_base`) | e-process, ngưỡng lô α·6/(π²k²) | khai phá mỗi 30 kỳ, chấm mỗi kỳ | chưa luật nào đạt ngưỡng | tự đăng ký lô mới |

Mỗi cổng có phép kiểm cài tín hiệu cho CẢ HAI chiều: nhiễu thuần không được đề bạt, tín hiệu thật được
đề bạt và thắng trên ngày chưa thấy (`test_ensemble_weight_holdout_gate`, `test_meta_holdout_gate`,
`test_online_learning::test_gate_rejects_null_and_promotes_frozen_stable_signal`).

## Đã thêm: canh việc tự điều chỉnh không dừng lặng lẽ

Bộ học hỏng thì lượt `--strict` đỏ. Nhưng bộ học thoát mã 0 mà bỏ qua kỳ mới (sổ trạng thái không ghi,
đầu vào cũ) thì không gì thấy. `production_audit.stale_learners` (chạy ở `post-finalization` và
`watchdog`) đòi Hedge hai chế độ, sổ ba tác tử, báo cáo ba tác tử, kho tri thức và mô hình xếp chồng
đang ở trạng thái đã học phải ghi đúng ngày kỳ mới nhất. Trên 33 commit chốt từ 06-10-2026, không bộ nào
trễ một kỳ, nên phép canh không báo nhầm. Trọng số tổ hợp không nằm trong danh sách: nó CỐ Ý đứng yên khi
sổ đủ năm thành phần chưa đủ ngày (đổi `COMPONENT_POLICY` thì sổ bắt đầu lại).

## Những gì KHÔNG làm, và vì sao

- Không nới cổng (0,20%, z = 3, 60 / 100 ngày) và không chỉnh tay siêu tham số (bán rã, η của Hedge, hệ
  số 20 của trust) trên cùng dữ liệu đang chấm: chọn tham số theo kết quả rồi chấm lại trên chính dữ liệu
  ấy là rò rỉ, và với kỳ quay ngẫu nhiên nó chỉ làm dự báo nhọn hơn mà kém hơn. Muốn đổi thì đăng ký phép
  đo tiến cứu mới (`scripts/research/benchmark_probability_models.py --power-check`).
- Không ép bước hiệu chỉnh bật sớm bằng lát nhỏ hơn 60 ngày: dưới ngưỡng ấy khác biệt Brier giữa các
  ứng viên nhỏ hơn sai số đo.
