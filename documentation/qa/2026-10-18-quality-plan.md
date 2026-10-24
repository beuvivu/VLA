# Kế hoạch kiểm toán và hoàn thiện VLA — 18/10/2026

**Mốc mã:** kiểm kê từ `696a7c78a5d8f0db8c42847d1e586ab38226061c`; bản vá đặt trên `4f9ad9526ed6b16db30c8b6c7caa55b813bf5a8b` để giữ cập nhật dữ liệu tự động mới hơn.

**Mục tiêu:** rà soát mã đang vận hành, sửa lỗi có thể tái hiện và bàn giao bằng chứng kiểm thử cùng mã thay thế hoàn chỉnh.

**Kiến trúc:** giữ ranh giới giữa pipeline XSMB, engine Vietlott, Worker và site tĩnh. Sửa tại nơi sở hữu hành vi, giữ hợp đồng dữ liệu và giao diện. Không bổ sung mô hình mới khi chưa có bằng chứng ngoài mẫu.

**Công nghệ:** Python, NumPy/pandas/scikit-learn, FastAPI, JavaScript thuần, CSS dùng token, pytest, Node test/jsdom, Chromium.

## Ràng buộc chung

- Tuân thủ `CLAUDE.md` và `documentation/architecture/ui-design-system.md`.
- Không sửa lịch sử kết quả, ledger, mô hình đã lưu, tham số giả thuyết hay giao thức kiểm định đã đăng ký.
- Mỗi lỗi hành vi có kiểm thử đỏ trước sửa, xanh sau sửa và phép đảo thay đổi để chứng minh kiểm thử bắt được lỗi.
- Giữ cutoff, khôi phục dự báo đã ghi, API route và ý nghĩa xác suất hiện có.
- Không thêm framework giao diện hoặc phụ thuộc sản phẩm.
- Bản vá được kiểm tra trên nhánh riêng trước khi tích hợp.

## Các gói công việc

### 1. Kiểm tra baseline và lập bản đồ

- [x] Chốt SHA trên GitHub và tạo worktree riêng.
- [x] Kiểm kê mã nguồn, trang xuất bản và workflow.
- [x] Chạy kiểm tra nhất quán production và frontend hiện có.
- [x] Hoàn tất hai bộ kiểm thử Python và lint.

### 2. Tính nhân quả và hiệu năng XSMB

**Tệp:** `src/forecast/online_learning.py`, `src/xsmb_agents/engine.py`, các phép kiểm tự học/tác tử.

- [x] Tái hiện đồng hồ đọc trước khóa cho phép ghi dự báo mới sau cutoff.
- [x] Đọc giờ sau khóa và kiểm sát trước ghi; giữ khả năng khôi phục bản ghi cũ.
- [x] Chạy ca khóa chậm, tính toán chậm, ghi chậm, đồng hồ được tiêm và khôi phục sau cutoff.
- [x] Gom tính hiệu chuẩn theo bucket trong một lượt; kiểm kết quả bằng bản tham chiếu và đo trước/sau.

### 3. Benchmark và tính toàn vẹn Vietlott

**Tệp:** `vietlott/src/vlm/forecast/hit_benchmark.py`, crawler và phép kiểm tương ứng.

- [x] Tái hiện benchmark giữ component cũ sau cập nhật mô hình.
- [x] Đọc component hiện hành trong từng kỳ; so với vòng lặp prequential tham chiếu ở cả hai chế độ agent.
- [x] Tái hiện nguồn chính bỏ sót kỳ giữa, xác nhận cách cursor ảnh hưởng nguồn dự phòng.
- [x] Sửa việc lấp khoảng hở mà vẫn ưu tiên giá trị nguồn chính khi trùng kỳ.
- [x] Kiểm tra độ bền journal khi append lỗi; chọn cách khôi phục dựa trên bằng chứng cụ thể.

### 4. Tương tác giao diện

**Tệp:** `src/assets/app-evidence.js`, `src/templates/frequency_bento.js`, phép kiểm frontend.

- [x] Tái hiện Chromium: chọn cặp bằng Space làm mất focus; mũi tên chọn ô thuộc hàng đã ẩn.
- [x] Cập nhật trạng thái picker mà không thay phần tử đang focus; loại số không hiển thị khỏi điều hướng căn cứ.
- [x] Chạy kiểm thử hành vi, dựng lại trang bằng generator và xem thật trên desktop/mobile, sáng/tối.

### 5. Ranh giới bảo mật API

**Tệp:** `vietlott/src/vietlott_engine/api/main.py`, `vietlott/tests/test_api_security.py`.

- [x] Tái hiện hai GET GCN có thể huấn luyện khi thiếu token mặc dù đã cấu hình token API.
- [x] Áp dụng cổng xác thực/Origin hiện có cho hai thao tác huấn luyện, giữ route và response.
- [x] Kiểm 401 khi thiếu bearer, thành công khi đúng token và 403 cho trình duyệt cross-site ở chế độ không token.
- [x] Ghi rõ phạm vi kiểm tra thủ công: hosted Codex Security scan không khả dụng vì thiếu preflight/reference/scripts.

### 6. Lint và tài liệu vận hành

**Tệp:** `src/pages/build_statistics_dashboard.py`, `src/pages/update_readme.py`, `src/templates/README.j2`, `README.md`, phép kiểm README.

- [x] Sửa B905 tại phép ghép hai Series cùng hàng bằng `strict=True`.
- [x] Đồng bộ mô tả nguồn và template automation với chính sách một nguồn chính/hai dự phòng/ngưỡng một nhóm đang chạy.
- [x] Xác nhận generator không tái sinh chính sách cũ và vẫn lũy đẳng.

### 7. Khung nghiên cứu ML

**Tệp:** `src/ml_engine/{main_pipeline,metrics,validation}.py`, `tests/research/test_ml_engine_economics.py`.

- [x] Tái hiện temporal bị bỏ khi thiếu Torch dù đã có đường lui tuyến tính; bật theo cấu hình và kiểm fit/predict thật.
- [x] Truyền counts thật vào tracker, trả doanh thu theo số nháy; giữ chỉ số xác suất dùng nhãn nhị phân.
- [x] Sửa đối chứng kinh tế và giải thích kiến trúc; không công bố lại ROI lịch sử thiếu counts.
- [x] Kiểm hồi quy và đảo từng sửa đổi để xác nhận kiểm thử bắt lỗi.

### 8. Hoàn thiện và bàn giao

- [x] Rà soát độc lập bản vá, xử lý phát hiện trước tích hợp.
- [x] Chạy đầy đủ pytest XSMB/Vietlott, frontend, Worker, lint và kiểm gói trang.
- [x] Bàn giao báo cáo: lỗi, nguyên nhân, mã đã sửa, số đo, giới hạn kiểm tra và checklist duy trì.

## Điểm cần soi khi review

1. Bản ghi đã có phải còn khôi phục được sau giờ chốt; bản ghi mới phải bị từ chối.
2. Hiệu chuẩn phải giữ đúng trọng số theo kỳ và khoảng sai số hiện hành.
3. Benchmark phải dùng trạng thái trước kỳ, cập nhật sau kỳ, không mở lại tập kiểm đóng băng.
4. Nội dung bị lọc/ẩn phải không nhận điều hướng số; picker phải giữ focus sau Space.
5. Mọi endpoint kích hoạt huấn luyện phải đi qua cùng cổng xác thực với forecast hiện có.

## Kết quả chốt

Phủ đủ 3.877 ca root bằng bốn nhóm và kiểm lại tệp UI sau khi sửa guard cũ; engine 759 đạt/3 bỏ qua, frontend 209 đạt. Bốn cổng phát hành đạt, với pytest chạy riêng. Chi tiết số đo và giới hạn ở [báo cáo kiểm toán](2026-10-18-repository-audit.md).
