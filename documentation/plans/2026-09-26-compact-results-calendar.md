# Bảng kết quả gọn và lịch vạn niên

> **For agentic workers:** Thực hiện theo superpowers:executing-plans, từng phần có kiểm chứng.

**Goal:** Dùng kiểu bảng giải của Sổ kết quả trên các trang kết quả và thay hai bảng lịch trang chủ bằng lịch vạn niên có giải Đặc Biệt từng ngày.

**Architecture:** Một stylesheet bảng giải dùng chung cho trang chủ, bảng mô phỏng và trực tiếp. Lịch là thành phần tĩnh, nhúng dữ liệu đã xác thực; thuật toán lịch Việt Nam UTC+7 tách khỏi mã tương tác DOM.

**Tech Stack:** Python, HTML/CSS, JavaScript thuần, pytest và node:test/jsdom.

**Spec:** Yêu cầu và hai ảnh của chủ dự án ngày 26-09-2026; mẫu trực quan `docs/so-ket-qua-truyen-thong.html`.

## Ràng buộc

- Giữ khung Nexlink và tất cả mô hình, thống kê, dữ liệu đã lưu.
- Thẻ kết quả thống nhất, ô số kẻ đường mảnh, không ba thẻ cao rời nhau.
- Giữ đủ 27 số giải, số 0 đầu, đầu–đuôi và thao tác xem căn cứ.
- Lịch có ngày dương/âm, tháng nhuận, can chi, tiết khí, ngày lễ, giờ hoàng đạo; Đặc Biệt đủ 5 số, không dùng số mô phỏng.
- DOM dựng bằng createElement/textContent; dùng token giao diện và class app- cho thành phần mới.

## Trọng tâm kiểm tra

- Ngày gần nửa đêm phải theo Việt Nam, không theo múi giờ máy.
- Tháng nhuận không lặp sai ngày lễ âm lịch.
- Dữ liệu thiếu/sai phải được phân biệt với kết quả 00000 hợp lệ.
- Tháng ngắn/năm nhuận/chuyển năm và bàn phím không làm mất ngày đang chọn.
- Màn 360px và theme tối vẫn đọc được số, không tràn toàn trang.

## 1. Bảng kết quả chung

- [x] Kiểm tra cấu trúc 27 số và dữ liệu đầu–đuôi; bỏ bố cục ba thẻ trang chủ.
- [x] Thêm `src/templates/compact_results.css`, nạp vào `src/ui_theme.py`.
- [x] Sửa trình bày ở `src/build_landing_page.py`, `src/build_fun_prediction.py`, `docs/live.html`.
- [x] Dùng bảng giải viền ô cùng kiểu Sổ kết quả, giữ nhãn phân biệt mô phỏng/kết quả thật.

## 2. Lịch vạn niên

- [x] Thêm kiểm thử `tests/test_calendar_widget.py` cho dữ liệu Đặc Biệt và `tests/frontend/calendar.test.mjs` cho ngày âm và tương tác.
- [x] Chạy đỏ trước khi tạo thành phần.
- [x] `src/calendar_widget.py`: `load_special_results(repo_root) -> dict[str, str]`, `render_calendar(repo_root) -> str`.
- [x] `src/templates/vietnamese_calendar.js`: `AppVietnameseCalendar.getDay(iso)` và `todayISO(date)`; phạm vi 1900–2099.
- [x] `src/templates/calendar_widget.js` và `.css`: tháng 7 cột, chọn tháng/năm/hôm nay, thông tin ngày, điều khiển bằng bàn phím.
- [x] Thay phần `db-tuan-thang`, giữ neo cũ, cập nhật tên trong menu.
- [x] Kiểm tra Tết 1985/2024/2025/2026, tháng nhuận 2004/2025, số 00001, ngày chưa có dữ liệu và ngày tương lai.

## 3. Kiểm chứng và phát hành

- [x] Dựng landing rồi fun prediction; làm mới khung trang trực tiếp.
- [x] Chạy pytest và frontend tests; đảo một điều kiện để kiểm tra test lịch phát hiện sai.
- [ ] Kiểm tra desktop/mobile, sáng/tối, nút lịch và đủ 27 số trên trang thật.
- [ ] Rà soát diff, cập nhật main, đẩy nhánh và PR; chỉ hợp nhất khi các cổng bắt buộc đạt.
- [ ] Kiểm tra Pages và trang public, báo đúng trạng thái AI Scan nếu lỗi dịch vụ vẫn xuất hiện.
