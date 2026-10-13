# Hoàn tất PR và công việc VLA — kế hoạch thực hiện

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Sửa các lỗi đã tái hiện, tích hợp sáu PR đang mở và xác minh main cùng bản triển khai.

**Architecture:** Giữ cấu trúc HTML/Python hiện có. Sửa nhánh PR trước khi merge; các thay đổi kiểm thử/vận hành bổ sung được commit riêng. Giữ dữ liệu mới nhất từ main khi tích hợp.

**Tech Stack:** Python 3.11/3.12, pytest, JavaScript, Playwright, GitHub Actions.

**Spec:** Yêu cầu rà soát, commit/push main của chủ dự án; `documentation/qa/2026-10-08-deep-code-audit.md`; `CLAUDE.md`; `SECURITY.md`.

## Global Constraints

- Không đổi thống kê, chính sách mô hình hay lịch sử sổ dự báo.
- Giữ Python 3.11 của pipeline và các bản sửa Vietlott đã triển khai.
- Không in danh tính nguồn vào phản hồi API/giao diện; chỉ HTTP thông thường cho collector.
- Không force-push main; cập nhật ref có kiểm tra SHA, giữ commit tự động.
- Chủ dự án đã yêu cầu commit, push và tích hợp lên main; thực hiện liên tục trong phạm vi đó.

## Review Focus

- Cache từ phiên bản trước không được trả danh tính nguồn.
- Bảng có ngày nhưng thiếu giải phải tiếp tục được thử lại, không thành ngày nghỉ.
- API dưới tiền tố mount/root_path vẫn chặn mọi GET ghi trạng thái khi thiếu token.
- Dependency resolver phải thành công trên cả Python 3.11 và 3.12.
- Kiểm menu dài phải dùng thao tác cuộn thật; khóa cuộn phải làm kiểm thử đỏ.

### Task 1: Khép các lỗi trong PR #149

**Files:** `worker/src/traditional_results.js`, `worker/test/run_traditional_results.mjs`, `tests/test_traditional_results_api.py`, `vietlott/src/vietlott_engine/api/main.py`, `vietlott/tests/test_api_security.py`, tài liệu audit của PR.

**Interfaces:** Giữ `handleTraditionalResults`, `refreshFallbackOverlay`, `create_app`; đổi namespace cache phản hồi theo schema 2; không đổi payload kết quả quay.

- [x] Viết ca kiểm cache v1 có provider và primary JSON sai; đòi schema 2 và phản hồi không chứa danh tính nguồn.
- [x] Viết ca cron gặp bảng thiếu G7 rồi nguồn sửa; đòi ngày vẫn unresolved trước khi sửa và kết quả được nạp ở lần thử sau.
- [x] Viết ca GET forecast/evidence/ML khi mount/root_path; không token phải 401, token hợp lệ phải dùng được, không có checkpoint do yêu cầu bị chặn.
- [x] Chạy kiểm mới: xác nhận thất bại đúng hành vi; sửa tối thiểu; chạy toàn bộ Worker/API liên quan.
- [x] Cập nhật nhánh PR bằng commit đã kiểm chứng, kiểm SHA rồi merge vào main.

### Task 2: Tương thích năm PR dependency

**Files:** `requirements.txt`, `requirements-live.txt`, `requirements-ml-engine.txt` trên các nhánh PR #114–118.

**Interfaces:** Optuna 5, Matplotlib 3.11.2, tzdata 2026.4; SHAP 0.51/0.52 và NetworkX 3.6.1/3.7 theo mốc Python 3.12.

- [x] Kiểm metadata PyPI và resolver Python 3.11/3.12; giữ bằng chứng hai PR nguyên trạng lỗi trên 3.11.
- [x] Sửa marker của #115/#117; xác minh API dùng thật bằng các kiểm thử attribution/challenger/đồ thị/biểu đồ/lịch.
- [x] Merge từng PR với head SHA đã kiểm, không ghi đè các dependency khác.

### Task 3: Kiểm thử và vận hành còn thiếu

**Files:** `tests/test_app_shell.py`, `.github/workflows/ci.yml`, `.github/workflows/vlm-results.yml`, `vietlott/docker-compose.yml`, `documentation/qa/2026-10-08-pending-work.md`.

**Interfaces:** Playwright mặc định hoặc `UI_CHROMIUM_EXECUTABLE`/`UI_CHROMIUM_ARGS_FILE`; browser job bắt buộc chạy riêng ca menu điện thoại (các cổng giao diện khác đã có); backend collector `httpx`.

- [x] Tái hiện ca menu hiện tại báo 7/59 mục không chạm được; sửa kiểm thử cuộn và bỏ đường dẫn Chromium ghim.
- [x] Xác minh khóa cuộn làm phép kiểm đỏ; thêm ca này vào browser CI để không còn bị bỏ qua trên runner.
- [x] Đồng bộ cấu hình collector với SECURITY.md; xem báo cáo lỗi nguồn và thử lại có kiểm soát, giữ dữ liệu hợp lệ khi nguồn chưa sẵn sàng.
- [x] Chạy full Python VLA, full engine, Node, các cổng phát hành và kiểm giao diện liên quan; ghi kết quả và phạm vi tồn đọng thực tế vào tài liệu.
- [x] Review tổng thể, commit/push main, xác nhận CI và Pages; kiểm lại PR còn mở và workspace sạch.
