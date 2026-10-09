# Thiết kế rà soát và phục hồi ML — 09-10-2026

## Phạm vi và căn cứ

Yêu cầu: rà soát VLA, sửa lỗi, dọn phụ thuộc có bằng chứng, tách logic phục hồi/học thích nghi, kiểm thử và đánh giá dự báo Vietlott. Người dùng đã yêu cầu commit/push phần đạt kiểm chứng lên main. Nền thực hiện: `46aa9b53312c457bae21e5a6ee065facc712d4f2`.

VLA là hệ thống xổ số XSMB và engine Vietlott độc lập, không phải Vision–Language Model. Sản xuất dùng thống kê, mô hình tabular, online mixture và GRU NumPy; `src/ml_engine` là nhánh nghiên cứu, GRU torch tùy chọn chạy CPU. Không thêm encoder ảnh, LLM, FSDP, CUDA hoặc dependency GPU không có caller. Không thể chứng minh phần mềm tuyệt đối không lỗi hay tăng tỷ lệ trúng xổ số chỉ bằng refactor.

## Các hợp đồng bắt buộc

- Tách `src/` XSMB và `vietlott/src/`; giữ CLI, artifact schema và API hiện có.
- Không sửa lịch sử, ledger đã công bố, luật giả thuyết hot-tail hoặc số đo kiểm định tiến cứu.
- Dự báo/chấm điểm trước khi học kết quả. Giữ nguyên law đã issue đầu tiên, target và hash tiền tố.
- Uniform là baseline; mô hình không có bằng chứng live tiếp tục dùng xác suất triển khai fair. Challenger thích nghi mặc định tắt và không tự promote từ backtest.
- Dữ liệu sai shape/label là lỗi đầu vào rõ ràng; không đoán layout hay tự sửa nhãn. Numeric failure/OOM chỉ phục hồi có giới hạn, có trạng thái, giữ bản model tốt trước đó.
- Viết checkpoint/model theo staging cùng thư mục, fsync rồi replace; lỗi ghi/fit không phá bản cũ. Không bắt mọi Exception để báo thành công.
- Type hints và docstring mới bằng tiếng Việt, trình bày Args/Returns/Raises khi có ích; test pytest thực hành vi và lỗi đã tái hiện.

## Thiết kế lựa chọn

### Vòng đời model XSMB

Dùng chung `model_io.atomic_joblib_dump` cho pack ML, meta và cầu-kèo. Loader không unlink bản cũ trước huấn luyện, nhận diện lỗi pickle/joblib cụ thể. Giữ diversified_order cho top LOTO ngay cả shadow online. Research learners fit theo candidate, từ chối nonfinite trước clip; normalize xác suất bằng scale trước sum để tránh overflow. Research step rollback nếu bước downstream thất bại, không đếm reward/draw hai lần.

### Ngữ cảnh dự báo Vietlott

Một resolver dùng pending hợp lệ hoặc lịch quay đã xác định để lấy target ID/date/time. Report, portfolio và feature diagnostics dùng cùng ngữ cảnh. Keno/Bingo date-only không được tạo slot verified giả. PMI chỉ được tính cho cặp có co-occurrence dương; node chưa quan sát chỉ có self-loop.

### Phục hồi và học thích nghi Vietlott

Tách `vlm.forecast.recovery` (lỗi số học rõ ràng, retry giới hạn, telemetry) và `vlm.forecast.adaptation` (running mean/std, biến động phân phối, chuẩn hóa nhân quả). Logistic/GRU/tree staging cập nhật trước khi commit; loss, gradients, optimizer và prediction đều được kiểm tra finite. Gradient clipping dùng norm có scale để không tự overflow.

Khi prediction hỏng: thay riêng expert đó bằng law fair trước khi có kết quả, ghi recovery. Khi update hỏng số học: giữ trọng số/optimizer cũ, giảm rate scale có chặn dưới và bỏ update đó. Tree OOM có thể thử lại trên nửa replay buffer với số lần hữu hạn; không thay đổi effective gradient accumulation vốn không tồn tại trong NumPy engine. Lỗi lập trình/đầu vào không thuộc nhóm phục hồi tiếp tục nổi lên.

Một draw update phải nguyên tử ở cấp forecaster: lỗi ngoài nhóm phục hồi giữ cursor, mixture, metrics và pending trước draw; retry chỉ chấm một lần. Running statistics chỉ nhận feature của draw sau khi score, replay tối đa theo config, lịch sử telemetry có giới hạn. Challenger `adaptive=True` thêm logistic sử dụng chuẩn hóa từ thống kê quá khứ; mặc định False để không đổi chính sách đang phát hành khi chưa có kiểm định. AdaGrad, posterior mixture và rate backoff cung cấp learning rate/weight thích nghi có kiểm chứng, không thêm loss đa tác vụ cho bài toán không có nhiều tác vụ.

### Dọn code và xác suất thống kê

Bỏ seaborn sau khi quét caller; giữ API nghiên cứu, archive, dữ liệu seed, wrapper CLI có caller. Gom BH-FDR thành helper finite-aware qua wrapper tương thích; giữ NaN ở vị trí thiếu. Wilson chưa thay đổi vì các caller có hợp đồng zero-trial/z khác nhau. Thu hẹp catch catalogue về InsufficientDataError. Sửa hai closure bị ruff B023. Các refactor export Excel/provenance lớn sẽ phải có fixture riêng; không xóa code đang chạy để đạt số dòng giảm.

## Kiểm chứng và phát hành

Baseline toàn bộ hai suite độc lập; test lỗi đỏ trước sửa. Review riêng từng mảng và toàn nhánh. Benchmark walk-forward trên dữ liệu seed thật: forecast trước update, so fair và incumbent, Brier/log-likelihood/top-k; ghi hash, ID/date, config và thời gian. Benchmark hồi cứu không thay thế ledger live và không được quảng bá cải thiện nếu challenger không thắng ngoài mẫu. Mọi cảnh báo/test lỗi hoặc giới hạn môi trường được báo rõ. Sau gate xanh, commit và đẩy phần hoàn chỉnh lên main theo ủy quyền hiện có.
