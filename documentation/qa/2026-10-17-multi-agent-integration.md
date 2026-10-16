# Kiểm chứng tích hợp đa thuật toán — 17-10-2026

## Thay đổi đã kiểm

`vlm.multi_agent` được nối vào luật tập số thật của `MLComponent`, bật mặc định
qua Settings sản xuất. Ba chuyên gia và phân phối nền có trọng số theo ngữ cảnh;
loss dùng phân phối tập đúng số phần tử, không nhân các xác suất biên của mixture.
Power giữ luật joint số chính/số phụ. Các mô hình chữ số giữ mô hình riêng.

Checkpoint version 4 đọc được version 3. Nâng cấp chấm law đã issue trước khi
học lại; pending chưa có kết quả vẫn giữ nguyên. Hai ledger đang có giữ nguyên
từng byte trong lần tích hợp này. Cấu hình nghiên cứu mặc định không bật nhóm
mới, không đổi giao thức benchmark H đã đăng ký.

## Dữ liệu và trang

| Sản phẩm | Kỳ dữ liệu cuối | Ngày | Kỳ đã học trong checkpoint |
| --- | --- | --- | ---: |
| Mega 6/45 | 1576 | 16-10-2026 | 1007 |
| Power 6/55 | 1411 | 15-10-2026 | 1000 |
| Lotto 5/35 | 950 | 16-10-2026 | 950 |

Đã chạy `vlm.forecast.cli next` trên seed và nhật ký kết quả đã commit, trong
thư mục runtime riêng. Tám trang dựng bằng `src/build_vietlott_results.py` qua
`page_output.write_page`. Phần mới hiển thị cutoff, trọng số nội bộ, bộ nhớ và
trạng thái live từ `multi-agent-summary.json`; workflow lấy lại bản HEAD sau
cache để cache cũ không đè tóm tắt đã commit.

## Kết quả kiểm thử

- Engine đầy đủ: 706 pass, 3 skip; 43 subtest pass.
- Bộ VLA: xác nhận 3672 test, 11 skip, qua lượt toàn bộ và chạy lại hai test
  cần metadata Git bị thiếu trong bản sao cách ly (hai test chạy lại đều pass).
- Core, adapter và migration: 56 test pass trong lượt kiểm tra riêng cuối.
- Frontend JavaScript: 161 pass.
- Trang Vietlott và phần mới: 50 pass sau khi dựng HTML thật.
- Hợp đồng giao diện, bảo mật và trang đã xuất bản: 448 pass sau khi dựng.
- 11 đột biến về luật nhóm, loss, checkpoint, rollback, nâng cấp và summary đều
  bị các test mới bắt; 4 test giao diện/workflow cũng bắt được đột biến tương ứng.
- Ruff và `git diff --check` không báo lỗi.
- Các kịch bản domain challenger, number integrity và research release đã qua.

## Giới hạn diễn giải

Cả ba sản phẩm có 0 kỳ live được chấm theo chính sách mới tại cutoff này.
Trạng thái là `insufficient_live_evidence`; không công bố một phần trăm độ tin
cậy giả. Chẩn đoán hồi cứu không mở cổng live. Trạng thái trọng số hiện tại
không thay bộ số hoặc phân phối của dự báo đã khóa trước khi tích hợp.
