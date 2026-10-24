# XSMB Multi-Agent Implementation Plan

Kế hoạch đặt trong `documentation/plans/` theo hợp đồng bố cục của kho;
`docs/` chỉ chứa site xuất bản.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Áp dụng đặc tả ba tác tử vào pipeline XSMB, có sổ tiến cứu và XAI thật.

**Architecture:** Điều phối trên lõi online và knowledge hiện hữu; thêm profile
Hedge để không sửa sổ cũ. Tác tử mới được chấm shadow, báo cáo vào trang Độ tin cậy.

**Tech Stack:** Python 3.11, NumPy, pandas, scikit-learn, pytest.

**Spec:** documentation/architecture/2026-10-17-xsmb-multi-agent.md

## Global Constraints

- Không sửa sổ lịch sử hay hợp đồng xác suất sản xuất.
- Đặc Biệt tổng 1; LOTO giữ biên xác suất, tổng không vượt 27.
- Không học từ tương lai; không cộng hồi cứu vào kết quả tiến cứu.
- Ghi sổ nguyên tử, khóa, checksum; chốt trước 18:00 ICT.
- Mọi trang qua page_output, dùng design system, không tooltip chuột.

## Review Focus

- Profile cũ và nén archive phải đọc lại được sau khi thêm profile mới.
- Chạy lại cùng ngày không đổi dự báo hoặc chấm trùng kết quả.
- Lịch nghỉ không được giả làm chuyển trạng thái ngày kế tiếp.
- MLP thiếu một lớp nhãn phải lui về mức nền có lý do.
- Báo cáo thiếu/cũ không được in ra như dự báo kỳ mới.

### Task 1: Lõi học dùng chung

**Files:** src/forecast/online_learning.py; tests/forecast/test_xsmb_agents.py.
**Interfaces:** new_state(mode, profile='legacy'); advance(..., expert_predictions=None).

- [ ] Viết test profile cũ/mới, settlement một lần, trọng số thay đổi sau nhãn thật.
- [ ] Chạy test để thấy profile chưa được hỗ trợ.
- [ ] Thêm profile và tuner replay dùng chung core; giữ mặc định legacy.
- [ ] Chạy tests/forecast/test_online_learning.py và test profile mới.

### Task 2: Bộ nhớ, ba tác tử và điều phối

**Files:** src/forecast/xsmb_agents/{__init__,knowledge,algorithms,engine}.py; src/forecast/xsmb_agents/run_xsmb_agents.py.
**Interfaces:** KnowledgeBaseManager(frame); AlgorithmEnsemble.predict(mode, incumbent);
MetaLearner.advance(...); PredictiveEngine.run(data_dir, now).

- [ ] Viết test tiền tố, xác suất, truy xuất ngữ cảnh, MLP và sổ đóng băng.
- [ ] Chạy test để thấy API chưa có.
- [ ] Triển khai các lớp, loss và giải thích đóng góp, báo cáo có 100 số/mục tiêu.
- [ ] Chạy test; kiểm chẩn đoán trên dữ liệu thật và tín hiệu giả lập.

### Task 3: Pipeline và public

**Files:** src/pipeline.py; src/pages/build_confidence_page.py; tests/forecast/test_xsmb_agents.py.
**Interfaces:** báo cáo data/forecast/agents/report.json; card ở do-tin-cay.html#app-agents.

- [ ] Viết test thứ tự chạy thực, hiển thị xác suất/ứng viên và loại báo cáo cũ.
- [ ] Chạy test đỏ; tích hợp sau online và chẩn đoán/kho tri thức, trước dựng trang.
- [ ] Dựng trang thật; chạy lint, suite và kiểm giao diện.
- [ ] Review độc lập; commit, push main trong phạm vi đã được ủy quyền, xác minh Pages.
