# Kiểm chứng nâng cấp xác suất và tự học

Ngày 27-09-2026. Nền khảo sát: `9af298885c234f2e0c2d795163c19ca6035f513b`.

## Phạm vi và môi trường

Thay đổi Bayes, thống kê có trọng số, hiệu chuẩn, stacking, `ml_engine` và tích hợp journal online vào pipeline. Không thay thế toàn bộ kho bằng một mô hình khác. Kiểm thử cục bộ dùng Python 3.12 và các phụ thuộc trong `requirements-dev.txt`; CI dùng Python 3.11.

Các lệnh tái lập:

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=src OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m pytest tests -q -ra
python -m ruff check src tests
git diff --check
```

## Kết quả cuối tại môi trường cục bộ

- Toàn bộ `tests`: **2.421 passed, 7 skipped, 28 warnings**, 320,29 giây; exit code 0.
- Bảy test bị bỏ qua đều cần Playwright/trình duyệt chưa được cài ở môi trường này. Không tính chúng là đã đạt; trạng thái kiểm tra Chromium của GitHub Actions được theo dõi riêng trên PR.
- `ruff check src tests scripts/diagnose_conditional_pooling.py`: đạt.
- `git diff --check`: đạt.
- CLI chẩn đoán hai seed/hai kịch bản chạy được; đầu vào `--seeds 0` bị từ chối. Smoke trên dữ liệu thật cho các tầng Bayes/meta, ML tuần tự và online/retry đều đạt.

Đây là kết quả kiểm chứng mã, không phải tỷ lệ dự đoán đúng. CI và trạng thái hợp nhất xem tại PR chứa bản thay đổi; kết quả cục bộ không thay thế kết quả CI trên Python 3.11.

## Các bất biến đã kiểm

- Bayes: hiệu chỉnh moment hữu hạn; counts/trials/prior hợp lệ; trường hợp không có quan sát; trọng số EWM được nhân cùng hằng số không làm đổi posterior.
- Hiệu chuẩn/stacking: nhãn và thời gian hợp lệ; lát chọn trọng số không thấy nhãn lát hiệu chuẩn; thiếu mẫu trả identity/default; pack cũ hoặc đã thấy ngày đích bị loại; comparator cùng chính sách production; chấm chính blend định phát hành.
- `ml_engine`: forecast được cache và chấm nguyên bản; dự đoán lặp không tiêu thụ RNG thêm; không replay hoặc lùi thời gian; rollback khi tạo forecast lỗi; drift tác động kỳ tiếp theo; Brier reward phân biệt xác suất dù ranking giống nhau.
- Online: forecast trước cutoff; chỉ học một lần khi có kết quả; journal nguyên tử và lock; kiểm schema/checksum/lịch sử; không backfill bằng chứng; giữ đủ vector và chuyên gia; shadow/fallback; vector LOTO thuộc miền khả thi; khôi phục cả CSV đầy đủ và Top-K sau gián đoạn.
- Pipeline: online nằm sau sinh dự báo và trước đánh giá; lỗi journal làm bước vận hành dừng.

Các lượt kiểm đột biến độc lập đã phát hiện 31 thay đổi sai ở Bayes/meta/EWM, 16 ở `ml_engine`, 9 ở online và 4 ở hiệu chuẩn/tích hợp. Đây là các đột biến chọn theo rủi ro, không phải điểm mutation coverage toàn codebase.

Ba đột biến bổ sung của kiểm thử điều kiện mới (bỏ co, luôn κ=60, luôn co hoàn toàn) đều bị phát hiện.

Review độc lập phát hiện ba lỗi đã được sửa và có regression: khôi phục Top-K khi retry sau gián đoạn; vector chuyên gia LOTO có tổng xác suất vượt 27; dữ liệu không hữu hạn ở prefix học trọng số.

Review tích hợp bổ sung tình huống nghỉ quay: record chỉ được chốt `non_draw` khi lịch chuẩn xác nhận, vẫn giữ forecast gốc và được nén, nhưng không tạo nhãn/loss hoặc tăng số kỳ chấm. Ngày thiếu không rõ nguyên nhân vẫn chặn pipeline. Hai regression và hai đột biến bổ sung đều đạt.

## Giới hạn diễn giải

Moment đúng không đồng nghĩa rủi ro dự báo luôn thấp hơn. Bộ kiểm thử có cả dữ liệu ngẫu nhiên và tín hiệu được tiêm; kết quả trên tín hiệu được tiêm không chứng minh xổ số thật có tín hiệu tương tự. Không chọn seed hoặc hạ ngưỡng để che một kết quả bất lợi.

Kiểm thử cũ đòi phép học κ thắng κ=60 trên một seed nhiễu (`11`, 700 ngày khớp, 199 cặp chấm). Sau hiệu chỉnh moment, Brier là 0,18132763 so với 0,18129113: phép học **thua**. Kiểm tra 1.000 seed xác nhận đây là đánh đổi có thật, không chỉ dao động một seed: chênh Brier mới trừ κ=60 là +0,00005026 (SE 0,00000494). Vì không có định lý thống trị rủi ro như test cũ ngầm đòi, test được thay bằng hai hợp đồng đa seed cố định 0–19, vẫn giữ seed 11: co nhiễu phải tốt hơn tần suất thô; tín hiệu điều kiện được tiêm phải được giữ tốt hơn co hoàn toàn/κ=60. Các test moment riêng vẫn chặn việc quay lại công thức sai.

Bảng dưới dùng Brier dư kỳ vọng `mean((p−p_true)²)`; nhỏ hơn tốt hơn. Mỗi mô phỏng có 900 ngày, khớp 699 cặp từ 700 ngày đầu. Tín hiệu tiêm giữ Đặc Biệt IID; sau nguồn 42, chỉ 26 giải thường ngày sau được lấy đều từ 00–19. Không giả định 100 nhãn trong kỳ độc lập.

| Kịch bản và phần chấm | Công thức cũ | Moment mới | κ=60 | Co hoàn toàn |
|---|---:|---:|---:|---:|
| Nhiễu, toàn bảng, 1.000 seed | 0,00046754 | 0,00057943 | 0,00053046 | 0,00025814 |
| Tín hiệu tiêm, toàn bảng, 20 seed | 0,00059389 | 0,00068884 | 0,00124962 | 0,00116193 |
| Tín hiệu tiêm, riêng nguồn 42, 20 seed | 0,01152345 | 0,00947621 | 0,07206630 | 0,08995417 |

Moment mới khôi phục tham số đúng hơn dưới giả định mô hình và giữ tín hiệu mạnh ở nguồn 42 tốt hơn công thức cũ, nhưng trả giá bằng variance ở các nguồn nhiễu; ngay cả toàn bảng có tín hiệu tiêm, công thức cũ vẫn thắng trong mô phỏng này. Không diễn giải bảng thành bằng chứng tăng độ chính xác production. Mô phỏng này là chẩn đoán sau khi thấy lỗi, không phải nghiên cứu đăng ký trước.

[Số đo chi tiết](conditional-pooling-diagnostic-2026-09-27.json) lưu cả kết quả bất lợi và định nghĩa fixture. Tái lập bằng:

```bash
python scripts/diagnose_conditional_pooling.py --seeds 1000 --scenarios null
python scripts/diagnose_conditional_pooling.py --seeds 20 --scenarios null source42_prefers_first20
```

Script chẩn đoán giữ fallback về trung bình scalar cho hàng nguồn vắng của phép so sánh lịch sử, và dùng κ=10⁶ để xấp xỉ co hoàn toàn. Test regression mới dùng baseline riêng từng số cho hàng vắng và co hoàn toàn chính xác. Vì vậy số đo của hai phép kiểm có thể khác rất nhỏ; không dùng lẫn các số này làm ngưỡng test.

Hiện lịch sử đủ năm thành phần chỉ có 28 kỳ LOTO và 26 kỳ Đặc Biệt; lát xác nhận trọng số còn 6 kỳ, dưới sàn 8. Cả hai mode giữ default và identity calibration. Journal online chưa có kỳ dự báo thật đã chốt; chưa có bằng chứng tăng độ chính xác production.

Cổng online là quy tắc vận hành bảo thủ kiểm lại hằng ngày, không phải kiểm định anytime-valid. Khoảng posterior EWM không phải khoảng bất định của toàn ensemble. Kiểm thử kỹ thuật không chứng minh lợi thế xổ số.
