# Kế hoạch rà soát toàn kho và sửa lỗi xác nhận

**Mục tiêu:** hợp nhất PR #191 vào `main` sau khi các cổng CI thực chạy đều xanh; rà soát toàn kho, ghi bằng chứng tái hiện và sửa lỗi được xác nhận.

**Cách thực hiện:** giữ nguyên HEAD `0335aab` của PR #191 trong lúc CI chạy. Việc sửa sau rà soát ở nhánh `codex/full-repo-audit-fixes`, worktree riêng. Không đổi giao diện hay thuật toán dự báo theo suy đoán; không nới các cổng kiểm định.

**Công nghệ:** Python/pytest/Ruff, JavaScript/Node/jsdom/Chromium, GitHub Actions. Quy tắc nguồn: `CLAUDE.md`, hệ thiết kế trong `documentation/architecture/ui-design-system.md`.

## Phạm vi kiểm tra

- [x] Xác nhận PR, đúng HEAD, base `main`, CI Python/AI/ML, Chromium và CodeQL; merge bằng expected HEAD rồi kiểm lại kết quả hợp nhất.
- [x] Chạy toàn bộ Python của VLA, frontend Node và Python của engine Vietlott; phân biệt bỏ qua theo môi trường với kiểm đã chạy.
- [x] Rà độc lập core/ingest/forecast/evaluation/research, workflow/pipeline, UI và Vietlott. Quét 50 HTML ở desktop/mobile và hai chủ đề.
- [x] Kiểm dữ liệu thật: ngày và số giải của raw/two/sparse/JSON, nhãn sổ dự báo, số đã công bố.

## Các sửa chữa có thể kiểm riêng

Mỗi mục: viết ca tái hiện và xác nhận đỏ, sửa tối thiểu, chạy lại kiểm liên quan, đảo hành vi để chứng minh phép kiểm bắt hồi quy. Không ghi lại sổ lịch sử hay nâng xác suất dự báo.

1. `model_quality.calibration`: xác suất đồng nhất vẫn có một nhóm với đủ count/hits/Wilson; Murphy phải khớp Brier trực tiếp, kể cả xác suất 0/1.
2. `skill_monitor`: vector hỏng, tổng Đặc Biệt bằng 0 hay điểm NaN không được thành trạng thái bình thường hoặc ghi vào sổ.
3. `daily_update.yml`: chỉ job gọi workflow dispatch có `actions: write`; kiểm cả quyền kế thừa và quyền job ghi đè.
4. `daily_prediction.yml` và CLI: mã riêng cho tình huống chưa đến kỳ/chưa có dữ liệu; lỗi thật phải truyền ra ở lần đầu lẫn lần thử lại.
5. Trang Live: huỷ hàng đợi hiện số khi đổi ngày/trở về trạng thái chờ; không rò số kỳ trước vào kỳ mới.
6. Thống kê: hàng chờ tuân theo ngữ cảnh dải ngày và lịch sử toàn bộ; gan cực đại đếm kỳ không về ở giữa hai lần xuất hiện, phân biệt 0 đã biết với thiếu dữ liệu.
7. Coverage Power: jackpot2 phải xét 5 số chính và số đặc biệt từ cùng lồng; so với `spec.classify` và xác suất tổ hợp chính xác.
8. Max 3D Pro: kết quả đối chiếu số đơn không được gán hạng giải dành cho vé cặp; giữ thống kê trùng số minh bạch.

## Điểm cần review

- Mô hình hằng sai mức, vector toàn 0, NaN trong artifact hoặc sổ: không báo hiệu chỉnh hoàn hảo/giám sát bình thường.
- Snapshot Live đổi ngày trong khi còn timer: bảng phải sạch và không được hiện kết quả cũ sau đó.
- Dải ngày cũ, ngày hiện tại đã đủ kết quả, khoảng gan bằng 0: dữ liệu và nhãn phải nhất quán.
- Workflow lỗi ở cả lần đầu và retry: job phải đỏ; expected skip vẫn xanh có lý do.
- Jackpot2 Power và Max 3D Pro: so đúng loại vé/sự kiện, không ghép hai mô hình sản phẩm khác nhau.

## Chốt kiểm chứng

- [x] Review độc lập thay đổi và ca biên; sửa các phát hiện quan trọng trước phát hành.
- [x] Dựng lại đúng trang/tài nguyên bị ảnh hưởng từ source; soi browser thật và chạy kiểm trang đã xuất bản.
- [x] Chạy đầy đủ pytest/Node/Vietlott, Ruff, kiểm liên kết tài liệu, diff-check. Lưu kết quả và hạn chế trong báo cáo QA cùng ngày.
- [x] Công bố bản sửa qua PR; chỉ kết luận đã hợp nhất/triển khai sau khi đọc bằng chứng tương ứng.

Ngày nghỉ quay được ghi riêng trong báo cáo nếu sửa xuyên tuyến đòi thay hợp đồng sổ đã công bố; không sửa sổ cũ hoặc đổi chính sách học trực tuyến trong một bản vá nhãn ngày.
