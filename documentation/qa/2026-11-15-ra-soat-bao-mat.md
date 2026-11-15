# Rà soát bảo mật toàn kho — 15-11-2026

Phạm vi: mã Python của VLA (`src/`, `scripts/`), engine Vietlott (`vietlott/src`), Worker (`worker/src`), 29
workflow GitHub Actions, và 50 trang đã xuất bản trong `docs/`. Ghi chép nói rõ đã kiểm gì, tìm thấy gì, sửa gì, và
còn gì là rủi ro được chấp nhận.

## Đã kiểm

| Lớp lỗ hổng | Cách kiểm | Kết quả |
| --- | --- | --- |
| Luật bảo mật tĩnh | ruff `S` (bandit) trên ba cây mã | không `shell=True`, `eval`, `pickle.loads`, `yaml.load`; chi tiết dưới |
| Tiêm SQL | 9 câu SQL ghép chuỗi | tên bảng theo danh sách cho phép, giá trị qua tham số; một đường dẫn chưa thoát nháy (đã sửa) |
| Tiêm lệnh trong workflow | dò `${{ github.event.* }}` do người ngoài điều khiển trong `run:` | chỉ `head.ref`, truyền qua `env` (an toàn) |
| Quyền token workflow | khối `permissions` | 29/29 tệp khai ở cấp cao nhất; mọi workflow chạy theo PR chỉ đọc |
| `workflow_run` có quyền ghi | ba workflow | chặn đúng kho và nhánh mặc định, hoặc chỉ checkout `main`; không tải artifact lạ |
| Chuỗi cung ứng action | mọi `uses:` | chỉ `actions/*`, `github/*` |
| Bí mật trong kho | mẫu token GitHub/AWS/Slack/khoá riêng, tệp `.env`/`.pem` | không có |
| Token lọt vào log | kịch bản đụng token, `set -x`, `echo` bí mật | không có |
| Thư viện có lỗ hổng đã công bố | `pip-audit` trên 6 bộ yêu cầu (VLA, live, dev, engine, engine-dev, ml-engine) | không có |
| Giải nén lưu trữ, XML (XXE) | dò `extractall`, `etree` | không giải nén, không phân tích XML |
| Yêu cầu mạng thiếu thời hạn | mọi lời gọi `requests`/`urlopen`, kể cả viết nhiều dòng | đều có thời hạn |
| Nạp dữ liệu tuần tự hoá | `joblib.load` | chỉ nạp pack mô hình trong chính kho |
| Path traversal ở API engine | tham số đường dẫn | đều qua enum `GameSpec`/`ProductCode` trước khi thành tên tệp |
| Đầu vào API Worker | thử ngày không tồn tại, sai định dạng, ký tự lạ | bị từ chối đúng |
| Thoát JSON nhúng trong `<script>` | mọi `json.dumps` đặt trong thẻ script | đều thoát `<`, `>`, `&` (hai bản chép đã gom về `json_for_html_script`) |
| Liên kết mở tab mới | `target="_blank"` thiếu `rel="noopener"` | không có |
| `assert` trong mã chạy thật | S101 | chỉ là bất biến thu hẹp kiểu; không nơi nào chạy `-O` |

## Đã sửa

1. **Worker: cạn hạn mức ghi KV từ yêu cầu của khách (tính sẵn sàng).** API Sổ kết quả đệm mỗi cặp `from:to` mà khách
   gửi thành một khoá KV. Gói KV Free có 1 000 lượt ghi/ngày cho cả tài khoản, dùng chung với cron ghi kết quả trang
   Live (`RESULTS_CACHE` chưa khai nên rơi về namespace `LIVE`). Số cặp ngày hợp lệ lên tới hàng triệu, nên ~900 yêu
   cầu khác khoảng ngày là cạn hạn mức, và `kv.put` của cron hỏng đúng giờ quay: trang Live đứng hình. Thêm nữa, bản
   last-good 36 giờ bị ghi lại mỗi 5 phút có khách dù nội dung không đổi (tối đa ~576 lượt/ngày).
   - Bỏ đệm phản hồi trong KV; biên Cloudflare vẫn đệm theo `Cache-Control`.
   - Phần tốn CPU (phân tích ~1,2 MB lịch sử chuẩn ~17 ms, kiểm token và tính đầu–đuôi ~40% thời gian dựng; quá trần
     10 ms của gói Free) nay nằm trong bộ nhớ isolate, có trần và không tốn lượt ghi: lịch sử đã phân tích (giữ
     nguyên đối tượng khi bản tươi không đổi), từng kỳ dựng sẵn một lần, và tối đa 64 khoảng ngày đã tuần tự hoá
     trong 60 giây (theo góp ý review: khoảng 500 ngày không còn ~14 ms mỗi lần gọi lại). Đo: khoảng 500 ngày lần
     đầu ~4 ms, gọi lại gần 0 ms (trước: ~33 ms mỗi lần trượt đệm KV).
   - Bản tươi sống 5 phút trong khung 18:00–24:00 giờ VN, ngoài khung tới 18:00 (tối đa 1 giờ); bản last-good chỉ ghi
     khi nội dung đổi và không hết hạn (dịp Tết không có kỳ mới vẫn còn nó).
   - Lượng ghi KV của API nay ≤ ~90 lượt/ngày, không phụ thuộc lưu lượng. Năm phép kiểm mới trong
     `tests/worker/test_traditional_results_api.py`; chín đột biến (khôi phục đệm KV, luôn ghi last-good, đổi thời hạn, tắt
     bộ nhớ isolate, bỏ đệm phản hồi trong bộ nhớ, bỏ trần đệm, luôn phân tích lại, không giữ kỳ dựng sẵn) đều làm
     chúng đỏ.
2. **Engine Vietlott: đường dẫn ghép thẳng vào câu SQL của DuckDB CLI** (`crawler/sources/vqe130.py`) không thoát dấu
   nháy đơn; thư mục tên `it's here` cắt câu lệnh. Nay thoát như `storage.export_parquet`, có phép kiểm (đỏ với bản cũ).
3. **Worker trả nguyên lỗi bất ngờ cho khách** (CodeQL `js/stack-trace-exposure` trên PR): hai nhánh lỗi của API
   trả `String(error?.message || error)`, nên lỗi KV hay `TypeError` lọt chi tiết nội bộ ra ngoài. Nay chỉ thông báo tự
   soạn (`PublicError`: kiểm truy vấn, lịch sử chuẩn hỏng) được trả; lỗi khác chỉ còn một câu cố định. Phép kiểm mới;
   ba đột biến đỏ.
4. **Hai bản chép của quy tắc thoát JSON-trong-script** trong `evidence_catalog` nay dùng chung
   `web_security.json_for_html_script` (bản này thoát thêm U+2028/U+2029); hai phép kiểm sẵn có vẫn canh.

## Rủi ro được chấp nhận, kiến nghị

- **CSP còn `script-src 'unsafe-inline'`.** Các trang có 30 script nội tuyến khác nhau (một bản 735 KB) và 2 214 thuộc
  tính `on*`; CSP theo hash không phủ được thuộc tính `on*` khi không có `unsafe-hashes`, nên bỏ `unsafe-inline` nghĩa
  là viết lại cách gắn sự kiện của gần như mọi trình dựng trang. Hai lớp chặn hiện có giữ rủi ro ở mức thấp: luật cấm
  mọi cống HTML trên toàn kho (`test_nothing_published_to_the_browser_uses_an_untrusted_html_dom_sink`) và thoát JSON khi
  nhúng. Kiến nghị: làm theo từng trang — chuyển script nội tuyến ra tệp, gắn sự kiện bằng `addEventListener` — rồi
  bỏ `unsafe-inline` khi trang cuối cùng xong.
- **Action ghim theo nhãn phiên bản (`@v7`), không theo SHA.** Chỉ dùng action của GitHub; ghim SHA là bước cứng hoá
  thêm, không phải lỗ hổng hiện hữu.
- **CORS `*` của Worker** chấp nhận được: dữ liệu công khai, chỉ GET, không cookie hay thông tin đăng nhập.
