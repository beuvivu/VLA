# Kế hoạch triển khai ML audit — 09-10-2026

Spec: `documentation/architecture/2026-10-09-adaptive-forecast-design.md`.

## Global Constraints

Giữ luật score-before-learn, ledger bất biến, forecast gate và project boundary. Không sửa dữ liệu/model sản xuất trong kiểm thử; dùng tmp_path. Không mở dependency GPU hay framework mới. Không xóa module không có chứng minh dead code. Repo shared; implementation tuần tự, audit/review có thể đọc song song. Người dùng đã cho phép main push; controller thực hiện commit và push cuối cùng, implementer không commit/push hoặc spawn thêm agent.

Python kiểm thử: `/workspace/scratch/b214352c542d/tmp/vla-push-venv/bin/python`. Root: `PYTHONPATH=src python -m pytest`; engine: `cd vietlott && python -m pytest`. Nền: `46aa9b53`.

## Task 1: Vòng đời model và runtime XSMB

**Phạm vi:** `src/atomic_io.py`, `ml_predict.py`, `ml_train.py`, `meta_predictor.py`, các writer pack cầu-kèo; `online_learning.py`; `src/ml_engine/{models,bandit,main_pipeline}.py` và helper normalize liên quan. Test tương ứng trong `tests/`.

**Yêu cầu:**

1. Test đỏ: train thất bại vẫn giữ pack cũ; joblib dump/write thất bại không tạo pack cụt; corrupt serialization được nhận diện để retrain, không lộ nội dung pack qua log. Dùng atomic helper cùng thư mục, giữ nguyên pack/API.
2. Top LOTO sau online (kể cả shadow) giữ diversified_order tối đa ba số cùng đuôi, probability không đổi; các top4/8/10 là prefix cùng thứ tự.
3. Research TabularBooster fit thất bại giữ model cũ; TemporalSequenceModel linear từ chối nonfinite x/y trước mutation; predict từ chối nonfinite đầu ra trước clipping; Bandit checkpoint từ chối NaN và bộ đếm không hợp lệ; normalize vector lớn vẫn finite và sum=1.
4. Research _refit không xóa fitted arms tốt khi candidate thất bại; báo model_failed=True cho safe-mode và không gắn model tên arm giả khi chỉ có baseline. Step thất bại sau reward phải rollback state/cursor để retry không double count.
5. Bổ sung type hints/docstring phù hợp, catch cụ thể; không sửa thuật toán scoring/trust/false promotion.

**Kiểm chứng:** pytest các module ML/online/meta/atomic và engine research integrity; ruff files sửa. Ghi kết quả đỏ/xanh, phạm vi và concerns vào report task. Controller review patch trước Task 2.

## Task 2: Nhân quả feature và ngữ cảnh Vietlott

**Phạm vi:** `vietlott/src/vietlott_engine/ml_models/{features,gcn}.py`, inference/{predictive,power,report,multiple_testing,changepoint}, API analytics, legacy `forecast/engine.py`; `vietlott/src/vlm/forecast/features.py` và `pipeline.py` chỉ resolver/report/portfolio; `vietlott/src/vietlott_engine/api/routers/catalog.py`; test engine.

**Yêu cầu:**

1. Test đỏ phantom PMI: sau một draw, không có edge unseen-unseen/unseen-seen; đối xứng/finite, planted pair có edge, prefix không thay đổi khi thêm tương lai. Chỉ tính PMI nơi cooc dương.
   Cluster-rate cũng chỉ lấy tối đa ba neighbor có pair-count dương; không tạo hỗ trợ vì argsort các cạnh zero.
2. Resolver target ID/date/time thống nhất cho report/portfolio/feature support. Nếu pending hợp lệ giữ law đầu tiên; nếu không, dùng target_draw_time cho weekly/Lotto. Report cùng history trước và sau issue phải cùng model law/marginals/portfolio. Không xác nhận live cho FAST/date-only. Không sửa score-before-learn.
3. Catalogue empty store bắt InsufficientDataError, không báo zero draws khi PermissionError/corrupt store. Test cả hai trường hợp.
4. Legacy Forecaster phải nhận diện tiền tố lịch sử đã sửa và refit sạch, thay vì âm thầm giữ model cũ; giữ bất biến ledger xuất bản. GCN từ chối khoảng train rỗng/đảo hoặc thiếu train/validation; analytics không công bố skill của network chưa train khi chỉ có 25 draw. Power-equivalence không trả NaN với marginal 0/1 từ 20 draw giống nhau; kiểm biên hợp lệ và diễn giải regularization nếu cần.
5. Calibration inference dùng đơn vị kỳ quay cho ma trận (draw, number), có covariance/HAC thay vì flatten number-labels độc lập; giữ reliability mô tả và hợp đồng 1D. Diebold-Mariano reject sample rỗng/quá ngắn rõ ràng. inference_report(alpha) truyền alpha nhất quán vào per-number và changepoint; alpha mặc định giữ 0.05. Test p-value/calibration variance bằng luật one-of-four dựng sẵn và khoảng train không rỗng.

**Kiểm chứng:** pytest forecast/features/models/integration/ml/API modules, ruff files sửa. Không sửa training core vì Task 3 quản lý. Controller review patch trước Task 3.

## Task 3: Phục hồi bounded và thống kê thích nghi Vietlott

**Phạm vi:** `vlm/forecast/{models,pipeline,recovery,adaptation}.py`, tests mới; config backward-compatible.

**Yêu cầu:** Test đỏ rồi triển khai finite validation và transactional learn/fit; prediction fallback riêng expert, learning skip/rate backoff, bounded MemoryError retries với replay nhỏ hơn; telemetry bounded/checkpoint validated. Draw transaction rollback bất kỳ unexpected failure, bao gồm pending/live score. Running feature mean/std và drift chỉ cập nhật sau score; adaptive normalized logistic bật bằng MLConfig adaptive=False mặc định, serialize deterministic và không promote. Reject checkpoint có evidence counters không thể có (ví dụ learned=2 nhưng live_scored=100); đối chiếu first-issued ledger trong service trước khi chấp nhận certification được restore. Giữ checkpoint version 2 nếu có thể đọc pack cũ bằng default an toàn; nếu cần version mới phải có migration rõ ràng. Không làm mới/fabricate published evidence.

**Kiểm chứng:** các regression nonfinite/shape/optimizer/fit failures, rollback/retry, causal normalizer/drift/planted signal, roundtrip và chunk invariance. Existing gradient finite-difference và toàn suite engine phải xanh.

## Task 4: Dọn dependency và helper thống kê

**Phạm vi:** requirements.txt, helper BH-FDR mới + significance_stats/research_diagnostics wrappers; hai closure ruff đã phát hiện.

**Yêu cầu:** NaN không làm mất p-value hợp lệ; BH finite giữ output cũ; input invalid định nghĩa rõ. Loại dependency seaborn không caller; giữ các API/research/export có caller. Fix B023 bằng bind đúng scope. Không gom Wilson với các hợp đồng khác nhau.

**Kiểm chứng:** statistical helpers và site navigation tests, root/engine ruff; full root suite.

## Task 5: Đánh giá, báo cáo và tích hợp

**Phạm vi:** benchmark walk-forward dùng seed và báo cáo audit trong documentation/qa, CLI đánh giá trong vietlott/scripts nếu cần.

**Yêu cầu:** lưu provenance/hash/config/ID split; chạy incumbent và challenger trên cùng held-out chronology, score trước update. Báo Brier/log gain/top-k và fair baseline; không sửa ledger live hay tự promote. Kiểm đầy đủ cú pháp/import/lint/test, review từng task và toàn nhánh. Báo tree, lỗi đã sửa, dependencies dọn, phần không có bằng chứng. Commit/push main sau checks; kiểm CI/Pages nếu trigger, link commit/PR/site đúng phần xem được.
