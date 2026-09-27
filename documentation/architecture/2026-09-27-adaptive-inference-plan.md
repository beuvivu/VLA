# Kế hoạch triển khai nâng cấp xác suất

**Goal:** sửa suy luận và đưa cơ chế học online có kiểm định vào pipeline.
**Architecture:** nâng cấp độc lập Bayes/meta, ml_engine, hiệu chuẩn và journal online; tích hợp tuần tự ở cuối sinh dự báo.
**Tech Stack:** Python, NumPy, pandas, SciPy, scikit-learn, pytest.
**Spec:** 2026-09-27-adaptive-inference.md.

## Ràng buộc chung

Tiếng Việt trong chú thích; giữ hợp đồng dữ liệu, constant baseline, không coi 100 số cùng kỳ là 100 kỳ độc lập; không phát hành trọng số chưa qua gate.

## Review Focus

Ngày dự báo lùi; journal hỏng/sửa lịch sử; xác suất NaN; lỗi arm; hiệu chuẩn thiếu mẫu. Mỗi phần có regression test cho đầu vào sai và kiểm đường chạy hợp lệ.

## Công việc

- [x] Bayes/meta: tests đỏ → sửa công thức, provenance, availability, uncertainty gate → chạy tests và đột biến.
- [x] ml_engine: tests đỏ → config/chronology/cache/proper reward/calibration/schema → tests và đột biến.
- [x] Hiệu chuẩn: tests tách mẫu → helper chronological stack và identity khi thiếu mẫu → regression.
- [x] Online: tests journal/exactly-once/leakage/gate → full-information mixture + CLI → kiểm restart và dữ liệu ngẫu nhiên.
- [x] Tích hợp pipeline, hướng dẫn vận hành, kiểm tra độc lập, lint/full suite và chuẩn bị source bàn giao qua PR.

Kết quả: 2.421 tests đạt, 7 test trình duyệt bỏ qua do thiếu Playwright; Ruff đạt. Xem báo cáo `../qa/2026-09-27-adaptive-inference.md` để biết phạm vi, kết quả mô phỏng bất lợi và giới hạn.
