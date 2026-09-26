# Lịch vạn niên và bảng kết quả gọn

Yêu cầu ngày 26-09-2026: dùng kiểu ô giải của Sổ kết quả ở trang chủ, các bản landing, trang trực tiếp và bảng mô phỏng; thay hai bảng Đặc Biệt tuần/tháng trên trang chủ bằng lịch âm dương.

## Hợp đồng dữ liệu và tương tác

- `calendar_widget.load_special_results` chỉ đọc `data/xsmb.csv`, kiểm tra ngày Gregorian thật và chuỗi 1–5 chữ số, bổ sung số 0 đầu. Không dùng dữ liệu mô phỏng hoặc tự điền số cho ngày thiếu.
- Mỗi ô lịch hiện Đặc Biệt đủ 5 chữ số. Hai số cuối được nhấn màu; `00000` là kết quả hợp lệ, khác ngày chưa có dữ liệu.
- Mở ở kỳ gần nhất; nút Hôm nay theo `Asia/Ho_Chi_Minh`. Điều khiển tháng/năm, mũi tên, Home/End, PageUp/PageDown, Shift+PageUp/PageDown giữ ngày đang chọn hoặc chặn về ngày cuối tháng.
- Ngày dương, âm, tháng nhuận, can chi, tiết khí, các ngày lễ chính và sáu giờ hoàng đạo nằm trong bảng chi tiết. Ngày mùng một/rằm có dấu trên lịch, kể cả tháng nhuận; lễ âm lịch chỉ áp dụng tháng thường.
- Phạm vi 1900–2099 dùng UTC+7 thống nhất. Không tái dựng các thay đổi múi giờ/lịch chính thức trong lịch sử trước 1968. Các ngày lễ là ngày kỷ niệm, không phải lịch nghỉ làm bù.

## Tính lịch

Quy tắc đánh số tháng, tháng chứa Đông chí và tháng nhuận theo bài viết của Hồ Ngọc Đức:

- <https://honguyenviet.com/amlich/calrules.html>
- <https://honguyenviet.com/amlich/calrules_en.html>

Không dùng `Intl` với lịch Trung Quốc vì quy đổi theo UTC+8 có thể khác lịch Việt Nam. `Intl` chỉ dùng lấy ngày dương hiện tại tại Việt Nam.

Điểm sóc dùng công thức Meeus, *Astronomical Algorithms*, chương 49, đủ các số hạng chính và 14 hiệu chỉnh hành tinh. Phần này chuyển thể từ `astronomia` (Sonia Keys / Commenthol, MIT); giấy phép đầy đủ được giữ trong đầu tệp JavaScript và trong trang được dựng:

- <https://github.com/commenthol/astronomia/blob/master/src/moonphase.js>
- <https://github.com/commenthol/astronomia/blob/master/LICENSE>

Chuyển TT sang UT bằng đa thức ΔT của Espenak–Meeus:

- <https://eclipse.gsfc.nasa.gov/SEcat5/deltatpoly.html>

Ngày sóc được tìm ở cả hai phía của ước lượng chu kỳ: không giả định chu kỳ trung bình luôn nằm trước ngày cần đổi. Điều này tránh ngày âm bằng 0 khi sóc sát nửa đêm. Kinh độ Mặt trời dùng công thức Meeus độ chính xác thấp; tiết khí là tiết đã vào trong ngày dân sự Việt Nam, không công bố giờ chuyển tiết.

Đối chiếu độc lập với bảng lịch của Hồ Ngọc Đức cho 1968–2099 khớp ngoại trừ tháng âm chứa sóc 07-05-2054, nằm sát 00:00 Việt Nam. Bảng cũ dùng tháng bắt đầu ngày 07-05, công thức Meeus đầy đủ cùng ΔT hiện dùng cho ngày 08-05. Giữ kết quả thiên văn tính được, không chèn ngoại lệ để ép khớp bảng cũ. ΔT tương lai và các phép xấp xỉ thiên văn có sai số; đây không phải lịch công bố chính thức cho các năm xa.

Can chi theo chu kỳ Julian day và năm/tháng âm lịch. Giờ hoàng đạo theo quy ước dân gian; giờ Tý bắt đầu 23:00 hôm trước. Không tạo đánh giá việc nên/không nên làm hoặc diễn giải vận may từ kết quả xổ số.

## Giao diện và kiểm thử

`compact_results.css` nạp vào stylesheet chuẩn. Bảng thật có một thẻ chứa bảng giải và bảng LOTO đầu–đuôi; nhãn/neo cũ còn hoạt động. Trên điện thoại, các giải sáu số chia hai hàng để giữ cỡ chữ đọc được. Trang trực tiếp dùng cùng ô giải, giữ trạng thái đang quay và hiệu ứng cập nhật. Mô phỏng giữ nguyên nhãn cảnh báo và xác suất.

`tests/test_calendar_widget.py` kiểm dữ liệu, số 0 đầu và đủ 27 số. `tests/frontend/calendar.test.mjs` kiểm Tết/Trung thu/tháng nhuận, can chi, UTC+7, sóc gần nửa đêm, tháng ngắn, bàn phím, giới hạn năm, dữ liệu rỗng và dữ liệu không hợp lệ.
