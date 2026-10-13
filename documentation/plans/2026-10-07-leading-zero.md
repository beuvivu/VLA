# Giữ số 0 đầu — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Thực hiện tuần tự, kiểm thử rồi review toàn nhánh.

**Goal:** Sửa mất số 0 đầu các bảng và CSV, kiểm tra Excel giữ mã dạng text.
**Architecture:** Một bộ định dạng mã theo độ rộng ở biên hiển thị/xuất file. Pipeline chuẩn hóa các cột mã đã biết trước khi dựng trang; không đổi mô hình, số đo và JSON số nguyên.
**Tech Stack:** Python, pandas, CSV, HTML tĩnh, openpyxl.
**Spec:** Yêu cầu chủ dự án ngày 07-10-2026: “Loại bỏ hiện tượng mất số 0 ở đầu các bảng hoặc file”.

## Global Constraints

- Giữ nguyên phép tính, xác suất, lịch sử theo giá trị và hợp đồng mô hình.
- Ô trống không được biến thành `00`; số âm/thập phân/ngoài miền phải báo lỗi.
- Giao diện thực tế phải được kiểm tra; CSV không thể khai kiểu ô cho Excel.

## Review Focus

- Mã 0 hợp lệ khác ô thiếu.
- Số đếm, hạng, đầu/đuôi đơn lẻ không bị đệm.
- Xác suất giữ nguyên từng chữ số qua chuẩn hóa file.
- Giải đầy đủ khác hai số cuối trong bảng điều kiện.
- Lần chạy pipeline sau không tái tạo lỗi.

## Task 1: Định dạng và xuất bản

- [x] Viết test tái hiện ML/Research mất số 0; xem 20 test thất bại trước sửa.
- [x] Thêm `lottery_code(value, width=2)`, `csv_code_widths(path, headers)`, `normalize_csv(path)` trong `src/lottery_codes.py`.
- [x] Áp dụng tại ba trình dựng, Lottery.dump và pipeline.
- [x] Chạy `PYTHONPATH=src python -m pytest tests/test_leading_zero_contract.py -q`: 24 passed.
- [x] Chuẩn hóa file cũ, dựng lại bốn trang, kiểm giá trị CSV không đổi.

## Task 2: Xác minh và tích hợp

- [x] Kiểm Excel roundtrip, trình duyệt, bộ test đầy đủ.
- [x] Review độc lập toàn nhánh; sửa lỗi quan trọng nếu có.
- [ ] Tạo PR, đợi CI, merge theo ủy quyền hiện có và xác minh Pages.

Review phát hiện publisher standalone còn ghi số nguyên: đã tái hiện test đỏ, bổ sung `write_code_csv` cho các trình xuất mã số và kiểm lại 46 test liên quan. Bộ đầy đủ: 3190 passed, 8 skipped. 498 CSV / 58.707 ô chỉ đổi cách viết mã; 228.312 ô Excel và 27 giải ngày mới nhất đã kiểm roundtrip. Trình duyệt: 16 cấu hình trên bốn trang, số đo nguyên vẹn.
