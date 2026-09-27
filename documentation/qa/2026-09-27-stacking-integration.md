# Khép lỗi tích hợp stacking khi chưa đủ lịch sử

Nền sửa: PR #100, commit `1379b1379e16e255871765da03dbc33919514d2b`.

## Nguyên nhân

CI đã qua 2.421 kiểm thử nhưng dừng trong `release_check.sh`: bộ chọn stacking chỉ công nhận 28 kỳ có đủ thành phần hợp lệ, trong khi huấn luyện cần ít nhất 100 kỳ. Script phát hành vẫn coi mọi lần chạy là đã tạo một estimator cùng metric thẩm định.

## Hợp đồng sau sửa

- Chỉ ngoại lệ `InsufficientMetaHistory` được chuyển thành trạng thái `insufficient_history`. Lỗi đọc dữ liệu, thiếu cột lõi, ngày sai, lỗi estimator và lỗi ghi tệp vẫn được báo lỗi.
- Khi thiếu mẫu, ghi pack hiện hành với `model=None`, `quality_pass=False`, `meta_trust=0`; ghi đè pack cũ để không tái sử dụng challenger đang bật. Báo cáo JSON/CSV lưu số kỳ hợp lệ từng tầng và ngưỡng tối thiểu, không tạo metric hay ngày huấn luyện giả.
- Luồng dự báo trả nguyên vector tuyến tính và lý do thiếu lịch sử. Pack vẫn tồn tại để giữ hợp đồng audit hiện có.
- Khi đủ mẫu, nhánh `trained` giữ phép học, bốn lát thời gian và cổng logloss/Brier hiện hành. Sàn 100 kỳ không bị hạ.
- Release check kiểm riêng trạng thái vô hiệu hóa và trạng thái đã học. Model đã học vẫn phải có estimator thật, metric hữu hạn, đủ validation và vượt đúng cổng nếu được bật.

## Kiểm chứng

Chín kiểm thử mới chạy vòng đời thiếu mẫu/ghi đè model cũ, dự báo dự phòng, CLI nghiêm ngặt, lỗi bộ chọn/estimator và chính khối Python trong shell phát hành. Hai mode đều có phép huấn luyện thật trên fixture 100 ngày trong thư mục tạm; dữ liệu mô phỏng không trở thành bằng chứng production.

Vòng kiểm đầu trước sửa: 7 thất bại, 1 đạt. Kiểm lỗi bộ chọn được bổ sung trong lượt đột biến. Nhóm liên quan sau sửa: **60 đạt** trong 8,64 giây. Ruff cho `src`/`tests`, `bash -n scripts/release_check.sh` và `git diff --check` đạt. Cả **5 đột biến** canh ghi đè pack, phạm vi bắt ngoại lệ, model luôn bị tắt, lý do fallback và cổng phát hành đều bị phát hiện.

Lệnh kiểm nhóm liên quan:

```bash
PYTHONPATH=src OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m pytest tests/test_meta_training_lifecycle.py tests/test_meta_predictor.py tests/test_meta_inference_contracts.py tests/test_meta_holdout_gate.py tests/test_ensemble_component_availability.py tests/test_production_automation.py -q
```

Kết quả đầy đủ của bốn script phát hành, Chromium và CodeQL được đối chiếu trên GitHub Actions của commit mới trong PR #100 trước khi hợp nhất. Lượt quét AI do GitHub quản lý là một kiểm tra riêng; lỗi dịch vụ “model không được hỗ trợ” không được ghi thành kết quả quét đạt.
