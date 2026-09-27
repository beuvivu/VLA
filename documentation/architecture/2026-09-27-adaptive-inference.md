# Kiến trúc nâng cấp xác suất và tự học VLA

Ngày: 27-09-2026. Mốc khảo sát: `9af298885c234f2e0c2d795163c19ca6035f513b`.

## Mục tiêu và tiêu chí

Nâng độ đúng của suy luận, tính toàn vẹn thời gian và khả năng tự cập nhật. Không đặt mục tiêu gần chính xác tuyệt đối cho một quá trình xổ số ngẫu nhiên. Thành công kỹ thuật được chứng minh bằng tests; cải thiện dự báo chỉ được khẳng định trên dự báo thật chưa thấy nhãn. Giữ hợp đồng 100 số, Đặc Biệt categorical, LOTO marginal, lịch Asia/Ho_Chi_Minh và pipeline hiện có.

## Quyết định kiến trúc

1. Giữ boosting, Bayes phân cấp, feature registry và research firewall đã có. Sửa moment beta-binomial hữu hạn và từ chối số không hữu hạn trước suy luận.
2. Tách các lát thời gian: khớp trọng số → xác nhận trọng số → khớp hiệu chuẩn → chọn hiệu chuẩn. Khi không đủ dữ liệu, dùng identity, không khớp rồi mặc nhiên phát hành.
3. Stacking phải xác minh availability thật, thời điểm huấn luyện, comparator và độ bất định theo kỳ. Pack cũ chưa có bằng chứng mới phải tự tái huấn luyện.
4. Bộ online production lưu dự báo bất biến trước kỳ quay. Có nhãn mới thì chấm dự báo đã lưu một lần, cập nhật tất cả chuyên gia bằng proper loss, theo dõi bộ nhớ dài/ngắn và cổng triển khai. Xác suất nền tham gia mọi so sánh.
5. Gia đình đặc trưng Bayes theo cửa sổ/điều kiện là không gian ứng viên hữu hạn, được lựa chọn bằng bằng chứng. Không tự sinh mã hoặc tìm vô hạn để chọn may mắn.
6. Hệ online khởi đầu ở shadow. Ít nhất 60 kỳ đã công bố và cổng cải thiện logloss/Brier so với cả incumbent và constant mới cho phép thay đầu ra. Đây là cổng vận hành thận trọng, không phải kiểm định anytime-valid.
7. Module nghiên cứu ml_engine cũng phải dự đoán trước rồi học, chặn replay/lùi thời gian, dùng Brier reward, hiệu chuẩn chronological và ghi đúng chế độ trước cập nhật.

## Phương án cân nhắc

| Tầng | Hạn chế tìm thấy | Nâng cấp và lý do toán học |
|---|---|---|
| Bayes/weighted statistics | Moment chưa hiệu chỉnh đầy đủ nhiễu hữu hạn; điểm và khoảng EWM dùng cỡ mẫu khác nhau | Empirical Bayes Beta–Binomial hiệu chỉnh `1−1/n`; thống nhất `n_eff=(Σw)²/Σw²`. Sửa ý nghĩa thống kê, không bảo đảm rủi ro luôn giảm. |
| Calibration/ensemble | Có đường khớp khi thiếu holdout; nguy cơ dùng chung nhãn giữa tầng chọn trọng số và calibration | Bốn lát thời gian tuần tự, proper scores và identity/default khi thiếu mẫu; giảm selection leakage. |
| Meta stacking | Comparator, availability và thời điểm model có thể không khớp forecast thực tế | Gate theo kỳ/khối trên chính blend với trust cố định trước holdout; phải thắng constant và production linear. |
| ML research | Top-K reward bỏ qua chất lượng xác suất; dự đoán lại/replay có thể sai provenance | Reward `1−Brier`, cache forecast, cập nhật tuần tự, calibration theo thời gian, chặn resume thiếu trạng thái. |
| Học liên tục/chọn chiến lược | Thiếu journal production gắn với dự báo thật đã công bố | Exponential weights với bộ nhớ tích lũy và bộ nhớ giảm trọng số, fixed share, bảy chuyên gia Bayes/lag; học đủ mọi chuyên gia vì đều quan sát được loss. |

- **Chọn:** sửa nền tảng hiện hữu + bộ online nhỏ có journal. Tương thích pipeline, kiểm được và có đường lui.
- Viết lại toàn bộ bằng neural network/Transformer: tăng tham số, chi phí và rủi ro quá khớp khi chưa có tín hiệu ngoài mẫu.
- Chỉ sửa module nghiên cứu: không tác động luồng dự báo công bố nên không đáp ứng vận hành.

## Kiểm chứng

Regression tests chống rò rỉ tương lai, replay, NaN/Inf, ngày/nhãn sai, posterior hữu hạn, phân biệt ranking và probability calibration; chạy lại các tests hiện có liên quan và toàn bộ suite khi dữ liệu/asset có sẵn. Kiểm đột biến các bất biến mới. Báo cáo rõ phần chưa chạy được, số mẫu và giới hạn của cổng.

## Nguồn phương pháp

- https://scikit-learn.org/stable/modules/calibration.html
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- https://www2.cs.uh.edu/~ceick/7362/T5-2.pdf
- https://arxiv.org/html/1707.02038v3

Hedge dùng full-information feedback khi mọi chuyên gia đều chấm được. Brier và logloss là proper scores, không phải bảo đảm tự động cải thiện calibration hoặc tạo lợi thế xổ số.
