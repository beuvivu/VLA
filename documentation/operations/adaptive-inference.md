# Vận hành suy luận xác suất và tự học

## Phạm vi

Nâng cấp tập trung vào tầng Bayes, thống kê có trọng số, học trọng số, hiệu chuẩn, stacking và vòng học online. Giữ crawler, lịch nghỉ quay, lịch vận hành, trang thống kê và hợp đồng artifact hiện có. Không chứng minh một mô hình có thể đoán xổ số gần chính xác tuyệt đối.

| Phần hiện có | Thay đổi | Lý do |
|---|---|---|
| `hierarchical_pooling` | Sửa moment Beta–Binomial hữu hạn, kiểm counts/trials hữu hạn | Trừ nhiễu nhị thức phải tính cả hệ số hữu hạn, tránh co quá mạnh |
| `statistical_signal` | Dùng cùng cỡ mẫu hiệu dụng cho điểm và khoảng hậu nghiệm | Trọng số tương đối không được đổi ý nghĩa chỉ vì nhân cùng một hằng số |
| `learn_ensemble_weights` | Tách lịch sử chọn trọng số khỏi lịch sử hiệu chuẩn | Không dùng nhãn giữ riêng để quyết định một thành phần ở tầng trước |
| `calibration` | Identity khi thiếu mẫu; kiểm nhãn/xác suất/trọng số | Không phát hành phép khớp trong mẫu chưa được thẩm định |
| `meta_predictor` | Schema 3, cổng theo kỳ, trust cố định, chấm chính blend, comparator cùng policy production | Thắng mô hình tham chiếu sai hoặc chọn trust trên holdout đều có thể tạo kỹ năng giả |
| `predict_nextday_2d` | Kiểm thời điểm train và availability theo đúng tier | Model từng thấy ngày đích bị loại; tier 3 không cần 5 thành phần |
| `ml_engine` | Dự báo cache, học tuần tự, Brier reward, ranker calibration theo thời gian | Chấm đúng forecast, tránh double-count và calibration trong mẫu |
| `online_learning` | Journal, EW hai bộ nhớ, Bayes đa cửa sổ và điều kiện trễ, cổng triển khai | Học từ mọi chuyên gia bằng proper score và giữ ký ức dài hạn |
| ML/boosting và feature registry | Giữ mô hình nền và các bộ trích đặc trưng đã có | Chưa có bằng chứng ngoài mẫu để thay bằng Transformer lớn hơn |
| Markov, hazard, conditional, opinion pool, bridge/pattern research | Giữ module; chạy regression và firewall hiện có | Phương pháp nghiên cứu không tự động có quyền tác động production |

## Toán học chính

Beta–Binomial dùng trung bình hậu nghiệm `(s + κ μ)/(n + κ)`. Với cùng n, phương sai tỷ lệ quan sát gồm phương sai giữa đơn vị nhân `(1−1/n)` và nhiễu nhị thức `μ(1−μ)/n`; vì vậy phải chia lại hệ số hữu hạn khi khôi phục phương sai giữa đơn vị. Trường hợp n khác nhau dùng moment có trọng số và hiệu chỉnh theo kích thước thử.

Với dữ liệu suy giảm mũ, `n_eff=(Σw)²/Σw²` và số thành công hiệu dụng là `rate*n_eff`. Đây là xấp xỉ cỡ mẫu hiệu dụng cho quan sát có trọng số; không mô tả nó như hậu nghiệm Bayes đầy đủ tích phân mọi siêu tham số. Tầng Đặc Biệt vẫn có bước chuẩn hóa categorical; ước lượng κ dùng moment thực nghiệm là xấp xỉ, không phải full hierarchical MCMC.

Khoảng hậu nghiệm trong `statistical_signal` mô tả thành phần EWM. Nó không phải khoảng tin cậy đã được kiểm chứng cho hỗn hợp dự báo cuối cùng và không bao gồm toàn bộ bất định khi ước lượng siêu tham số.

Bộ online dùng Brier theo kỳ: Đặc Biệt `Σ(p−y)²/2`; LOTO `mean((p−y)²)`. Mọi chuyên gia đều được chấm sau khi biết kết quả, nên không cần thăm dò kiểu bandit. Trọng số mỗi bộ nhớ tỷ lệ `exp(−4L)`; bộ nhanh cập nhật `L_fast=0.97L_fast+loss`, bộ chậm tích lũy toàn bộ loss. Trộn hai bộ nhớ 50/50 và dành 3% trọng số cho chia sẻ cố định. Nhờ đó chuyên gia yếu tạm thời vẫn có thể phục hồi; thống kê dài hạn không bị reset khi thị trường/trạng thái dữ liệu thay đổi. Không cam kết loại bỏ mọi dạng quên trong mọi mô hình sâu.

Bảy chuyên gia: dự báo hiện hành, xác suất hằng số, Bayes 30 kỳ, Bayes 180 kỳ, Bayes toàn lịch sử, điều kiện theo Đặc Biệt kỳ trước, điều kiện trạng thái xuất hiện kỳ trước. Đây là tìm kiếm chiến lược trong một danh mục cố định, không phải hệ tự phát minh thuật toán vô hạn.

LOTO giữ 100 xác suất biên, không chuẩn hóa tổng 1. Vector phải có tổng không vượt 27; ứng viên điều kiện quá lớn được chiếu về miền khả thi. Đặc Biệt có tổng 1.

## Chạy

Môi trường chuẩn CI là Python 3.11; phụ thuộc nằm trong requirements-dev.txt. Cài thư viện rồi chạy:

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=src python src/pipeline.py --strict
```

Pipeline gọi bộ online cho cả `loto` và `de` ngay sau `predict_nextday_2d`, trước đánh giá và dựng giao diện. Nếu chỉ muốn chạy bước online trên artifact đã có:

```bash
PYTHONPATH=src python src/online_learning.py --mode loto --data-dir data --out-dir data/predict
PYTHONPATH=src python src/online_learning.py --mode de --data-dir data --out-dir data/predict
```

Lịch sử phải được xác thực và chứa đủ 27 giải mỗi kỳ. Bước online không tải kết quả từ nguồn bên ngoài. Không chạy lệnh này để biến dự báo hồi cứu thành bằng chứng thật.

## Chu kỳ một ngày

1. Pipeline nhận kết quả mới và tạo dự báo ngày kế tiếp bằng các mô hình hiện có.
2. Đọc journal; xác minh checksum, schema, prefix dữ liệu và thứ tự thời gian.
3. Chỉ các dự báo đã lưu trước **18:00 Asia/Ho_Chi_Minh** mới đủ điều kiện. Mốc **18:35** dùng để xác định kết quả đã hoàn tất, không phải hạn cuối cho forecast.
4. Với mỗi kỳ chưa chốt đã có kết quả thật: chấm các vector đóng băng, cập nhật bộ nhớ đúng một lần.
5. Đánh giá cổng trên các kỳ đã chốt trước ngày đang dự báo; tiếp tục chấm cả shadow khi đang fallback.
6. Ghi forecast đầy đủ 100 số, từng chuyên gia, weights, vector mixture/blend/final, thời điểm và fingerprint. Ghi nguyên tử bằng thay tệp và giữ lock trong toàn giao dịch.
7. Khôi phục CSV đầy đủ, top 4/8/10 và picks từ chính vector đã lưu. Retry cùng ngày không thay forecast và không học thêm.

Nếu ngày dự báo là ngày nghỉ quay được khai báo trong `data/non_draw_days.json`, khi lịch sử tiến qua ngày đó journal ghi `status=non_draw`, giữ vector và chứng cứ lịch. Record này được lưu trữ nhưng không có nhãn/loss và không tăng số kỳ học hoặc bằng chứng cho cổng. Ngày vắng không thuộc lịch nghỉ làm bước online dừng; không tự gán kết quả bằng 0.

## Cổng triển khai và drift

Khởi động với **shadow**, cần ít nhất 60 kỳ dự báo thật đã chốt. Cả mixture và blend 50% phải cải thiện logloss so với **cả incumbent và constant**, đạt sàn 0,2%, cận dưới bảo thủ dương và Brier không xấu đi; 20 kỳ gần nhất cũng phải có tiến bộ. Sai số dùng mức lớn hơn giữa theo kỳ và khối 7 kỳ, nhân hệ số 4. Cổng này là quy tắc vận hành bảo thủ, **không phải kiểm định anytime-valid** khi kiểm lại mỗi ngày và không bảo đảm tỷ lệ báo động giả toàn vòng đời.

Khi không đạt, đầu ra giữ incumbent; journal vẫn lưu và chấm các ứng viên. Suy giảm ở cửa sổ gần hạ cổng cho kỳ kế tiếp, không sửa lại dự báo đã công bố. Ngay sau cài đặt chưa thể có 60 kỳ bằng chứng, nên không được tuyên bố đã tăng tỷ lệ trúng.

## Tệp trạng thái và xử lý lỗi

- `data/online/loto.json`, `data/online/de.json`: sổ bằng chứng và hai bộ nhớ. Giữ lâu dài, không đưa vào cleanup 45 ngày của dự báo.
- `data/research/online_<mode>_report.json`: trạng thái shadow/active, số kỳ, weights, các so sánh và provenance.
- `data/predict/predict_next_<mode>_all_<date>.csv`: xác suất cuối cùng; top và picks được đồng bộ.
- Sau 365 record đầy đủ, các khối 64 kỳ đã chốt được nén không mất dữ liệu. Bộ nhớ và mọi bằng chứng vẫn được giữ.

Sổ hỏng, schema lạ, lịch sử bị sửa hoặc đồng hồ lùi đều làm bước online dừng; không tự xóa sổ để khởi tạo lại vì điều đó xóa các lần thua. Khôi phục bản journal đã xác minh từ Git và chạy lại. Checksum phát hiện lỗi tệp, không phải chữ ký chống giả mạo.

Lượt đầu chưa có forecast trong journal mà đã quá 18:00 ngày đích cũng bị từ chối. Cần đưa lịch sử lên kỳ đã xác minh mới nhất rồi tạo forecast kỳ kế tiếp đúng hạn; không đổi đồng hồ hoặc timestamp để vượt cutoff. Trên Linux, khóa dùng `fcntl`; môi trường CI/vận hành của kho đáp ứng điều kiện này.

`generated_at` chứng minh thời điểm tạo theo đồng hồ tiến trình, không phải xác nhận độc lập của máy chủ về thời điểm người xem nhận được forecast. Khi đối soát kỹ năng đã công bố, cần giữ cả commit/artifact triển khai và xác nhận chúng xuất hiện đúng hạn. Chạy CLI nghiên cứu cục bộ chưa tự tạo bằng chứng công bố công khai.

**Backfill hoặc hiệu chỉnh lịch sử cũ:** fingerprint sẽ thay đổi và chặn pipeline. Chưa có migration tự động cho trường hợp này. Giữ bản sổ cũ và các artifact đã công bố, xác minh nguồn sửa, xây migration/replay từ forecast nguyên gốc hoặc khởi tạo một phiên nghiên cứu mới được ghi nhận rõ. Không xóa sổ rồi backfill dự báo như thể đã công bố trước kỳ quay. Việc khởi tạo phiên mới phải chờ lại đủ bằng chứng.

Module nghiên cứu `ml_engine` từ chối resume từ tệp chỉ chứa bandit; nó không chứa đủ mô hình/RNG/cursor để tiếp tục một chuỗi đánh giá đúng. Dùng journal production cho vận hành bền vững, hoặc chạy nghiên cứu mới từ trạng thái sạch.

## Kiểm tra

```bash
PYTHONPATH=src OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m pytest tests -q
python -m ruff check src tests
```

Các tests mới kiểm rò rỉ tương lai, nhãn hỏng, lặp kỳ, restart, cutoff, posterior, vector LOTO khả thi, mô hình cùng thứ hạng nhưng calibration khác, cổng trên dữ liệu ngẫu nhiên/tín hiệu tiêm và khôi phục sau gián đoạn. Tín hiệu tiêm chỉ kiểm thuật toán hoạt động, không chứng minh tín hiệu tồn tại trong xổ số thật.


## Bằng chứng hiện tại

Trên snapshot `9af298885c234f2e0c2d795163c19ca6035f513b`, lịch sử ensemble có 28 kỳ LOTO và 26 kỳ Đặc Biệt đầy đủ năm thành phần (đến 26-09-2026). Lát kiểm trọng số chỉ còn 6 kỳ sau khi tách dữ liệu, dưới mức 8; cả hai mode từ chối promote và trả identity calibration. Journal online bắt đầu 0 kỳ, không nhập lịch sử hồi cứu vào bằng chứng.

Kiểm thử trên dữ liệu thật chứng minh chương trình chạy, giữ hợp đồng và fail-closed đúng; chưa chứng minh mô hình mới tăng độ chính xác ngoài mẫu. Đánh giá lợi ích chỉ nên dùng logloss/Brier theo kỳ và forecast thật được lưu trước quay; không dùng tỷ lệ trúng mẫu huấn luyện.
