# Pattern Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans; thực hiện từng tác vụ và kiểm chứng trước khi kết luận.

**Goal:** Bổ sung bốn chuyên gia thống kê nhân quả và phép so ngoài mẫu tái lập.
**Architecture:** Chuyên gia độc lập trả vector xác suất; MLComponent chuyển sang Law và học trọng số sau khi chấm. Cấu hình và checkpoint giữ tương thích.
**Tech Stack:** Python, NumPy, SciPy, Pydantic, pytest.
**Spec:** `../specs/2026-10-24-pattern-learning-design.md`.

## Global Constraints

Không đổi luật vé công bố, dữ liệu kết quả, giao thức benchmark H hoặc chứng nhận live. Không bật production trước bằng chứng cải thiện. Mọi docstring mới tiếng Việt.

## Review Focus

ID thiếu; tuổi gap bị kiểm duyệt; checkpoint cũ; bật chính sách khi đang có vé đã phát; không kế thừa điểm live khi thay mô hình.

### Task 1: Chuyên gia mẫu hình

- [x] Viết test và xác nhận đỏ cho cold start, học bias/chuyển trạng thái/chu kỳ, missing IDs, roundtrip, dữ liệu sai.
- [x] Tạo `src/vlm/forecast/patterns.py`: `PatternExperts(nodes: int, base: float)`, `names`, `predict() -> ndarray[4,nodes]`, `observe(target: ndarray, draw_id: int)`, `to_dict()`, `from_dict(data, *, nodes, base)`; bộ đếm `seen`, `last_id`.
- [x] Chạy test, thử đột biến luật canh.

### Task 2: Tích hợp và chuyển cấu hình

- [x] Test đỏ cấu hình patterns, chấm trước học, checkpoint, nâng cấp giữ nguyên pending và reset live.
- [x] Sửa pipeline/service/settings; thêm bốn expert sau các model gốc và trước multi_agent; serialize trạng thái và kiểm đếm đồng bộ lịch sử.
- [x] Kiểm cấu hình cũ tiếp tục chạy, cấu hình mới học riêng và không nhận bằng chứng cũ.

### Task 3: Đánh giá và bàn giao

- [x] Bổ sung `--patterns` và `--multi-agent` cho evaluate_adaptive và CLI fit; giữ cấu hình mặc định chưa bật.
- [x] Chạy cùng giao thức 600/400 trên 7 sản phẩm, trước/sau dùng multi_agent hiện hành; báo cáo paired CI và kết quả so nền, không sửa tham số sau khi xem holdout.
- [x] Chạy pytest Vietlott và kiểm tích hợp VLA, lint; review độc lập và xử lý lỗi quan trọng.
- [x] Commit/push nhánh và tạo PR có bằng chứng, không tuyên bố đã lên main nếu chưa merge.


## Kết quả thực hiện

- 54 kiểm thử chuyên gia mẫu hình; 11 kiểm thử tích hợp/chuyển chính sách; 4 cấu hình CLI chạy mô hình thật.
- Toàn bộ engine: 873 đạt, 3 bỏ qua (DuckDB CLI và hai backend ML tùy chọn không có trong môi trường).
- Tích hợp VLA: 81 đạt; Ruff toàn engine đạt; diff không có lỗi khoảng trắng.
- 9 đột biến hành vi bị phát hiện (6 chuyên gia, 3 tích hợp); reviewer độc lập xác nhận không còn lỗi quan trọng sau sửa fingerprint và explicit refit.
- Hai nhánh benchmark cùng nguồn/hash dữ liệu, 7 × 200 kỳ ngoài mẫu; chưa chứng minh cải thiện. Giữ `patterns=False`.
- Báo cáo: `../../../reports/vlm/pattern-learning-2026-10-24/README.md`.
