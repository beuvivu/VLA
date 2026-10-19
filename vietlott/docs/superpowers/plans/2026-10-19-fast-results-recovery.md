# Khôi phục đồng bộ Keno/Bingo18

> Thực thi trực tiếp trong phiên hiện tại theo yêu cầu sửa, kiểm thử, áp dụng và chạy lại của chủ dự án.

**Mục tiêu:** Đồng bộ kết quả có xác thực, giữ nguyên dữ liệu đã có khi nguồn lỗi và không báo hoàn tất nếu còn thiếu kỳ.

**Kiến trúc:** Giữ HTTP thông thường và chuỗi nguồn hiện tại. Tách ngân sách archive khỏi nguồn trực tiếp; chuyển đọc/parse lịch sử lớn khỏi event loop; hợp nhất phần kết quả đã xác thực và kiểm tra liên tục trước khi ghi.

**Công nghệ:** Python 3.11+, asyncio, httpx, pytest, GitHub Actions.

**Đặc tả:** Yêu cầu khắc phục run `39207003570` ngày 19/10/2026 trong phiên này.

## Ràng buộc

- Không giải hoặc vượt xác minh Cloudflare; trang challenge không phải dữ liệu.
- Dòng archive đang chờ xác thực chính thức không được nhập tự động cho Keno/Bingo18.
- Không tự sinh kết quả hoặc mã kỳ theo đồng hồ; kỳ không xác nhận chỉ bỏ qua khi có thông báo loại kỳ.
- Không sửa lịch sử chuẩn bằng kết quả mâu thuẫn của nguồn dự phòng.
- Giữ workflow đỏ khi nguồn hoặc tính liên tục chưa được chứng minh; giữ dữ liệu và báo cáo để phục hồi.

## Trọng tâm rà soát

- Retry của archive cần còn thời gian chạy sau một request lỗi.
- Đọc seed Keno lớn không làm nghẽn thời hạn của sản phẩm khác.
- Mã kỳ cao hơn không che khoảng thiếu ở giữa hoặc dòng chưa xác thực.
- Nguồn dự phòng có thể bổ sung khoảng thiếu nhưng không sửa kỳ đã có bằng số mâu thuẫn.
- Hủy lượt đồng bộ không để thread ghi nền tiếp tục sau khi nhả khóa.

## 1. HTTP và ngân sách nguồn

- [x] Viết và chạy đỏ kiểm thử challenge HTTP 200, retry archive qua ngân sách nguồn trực tiếp, heartbeat trong lúc đọc store chậm.
- [x] Sửa `crawler/http.py`, `crawler/product_store.py`, `core/config.py`, truyền cấu hình qua CLI và service.
- [x] Chạy lại kiểm thử, xác nhận timeout bị chặn vẫn có báo cáo rõ nguồn và thời hạn.

## 2. Xác thực và liên tục

- [x] Viết và chạy đỏ kiểm thử pending/invalid/sai sản phẩm, mirror không có xác thực, thiếu kỳ, loại kỳ và mâu thuẫn.
- [x] Thêm gate xác thực live trong `crawler/sources/nhanaz.py`; kiểm tra và hợp nhất liên tục trong `crawler/product_store.py`.
- [x] Truyền chẩn đoán nguồn và liên tục qua `vlm/updates/service.py` và `runner.py` vào checkpoint.
- [x] Chạy kiểm thử hồi quy và đột biến hành vi được canh.

## 3. Kiểm chứng và áp dụng

- [x] Chạy Ruff và toàn bộ pytest của engine; ghi rõ lỗi nền nếu có.
- [x] Cập nhật workflow: ngân sách hữu hạn, kiểm thử trước đồng bộ, lưu chẩn đoán, kích hoạt khi crawler đổi.
- [ ] Rà soát diff, áp dụng commit trên main bằng cập nhật có kiểm tra SHA để giữ thay đổi đồng thời.
- [ ] Chạy lại Actions; đọc log, artifact và journal thực tế. Chỉ xác nhận khôi phục khi dữ liệu xác thực và liên tục; nếu nguồn vẫn chặn/chưa xác thực thì báo rõ phần chưa hoàn tất.
