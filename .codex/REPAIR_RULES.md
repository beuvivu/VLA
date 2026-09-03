# Repair rules

Last verified: 2026-09-03

1. Reproduce a defect with a focused test before or with the patch.
2. Treat any feature change after future-result mutation as P0 temporal leakage.
3. Require raw and derived histories to share the same unique ordered date axis.
4. Keep all candidate rows from one draw in one temporal partition and one bootstrap cluster.
5. Compare champion and challenger on identical rows, labels, dates, hyperparameters and seeds.
6. Interpret Brier and LogLoss as losses; positive improvement is baseline minus challenger.
7. Promotion fails closed on non-finite state, insufficient OOS dates, non-positive skill, or an improvement CI crossing zero.
8. Pass production model inputs through an explicit feature allowlist.
9. Keep failed/rejected experiments out of production and record the reason.
10. Preserve deterministic domain definitions in `number_reference.py` rather than copying them into feature code.
11. Khi tăng phiên bản schema của model, phải tái tạo mọi model/gate/manifest được theo dõi và chạy validator tương thích trước khi phát hành.
12. Không đặt tên biến cục bộ trùng module đã import khi closure dùng module đó; kiểm thử phải thực thi builder chứ không chỉ đọc artifact cũ.
13. Chuẩn hóa token kết quả theo chữ số ASCII, độ rộng, tính nguyên/hữu hạn và miền giải trước khi đưa vào đồng thuận hay lịch sử chuẩn.
14. Khi nhúng JSON vào HTML, escape theo ngữ cảnh script và chỉ dựng nội dung không tin cậy bằng DOM `textContent`; mọi trang sinh phải có CSP và `no-referrer`.
15. Metadata model sau giải tuần tự không phải dữ liệu tin cậy: kiểm tra schema, mode, feature allowlist, shape và miền xác suất trước suy luận.
16. Không gọi model challenger khi cổng chất lượng từ chối; trạng thái thiếu, NaN hoặc không hợp lệ phải giữ baseline.
17. Workflow chỉ cấp quyền ghi tại job cần ghi và chỉ dùng tệp tạm tên ngẫu nhiên trong thư mục tạm của runner.
