# Điều hướng Vietlott trong khung dùng chung

Theo yêu cầu tích hợp và xuất bản ngày 08/10/2026, Vietlott trở thành nhóm thứ hai trên rail, sau Kết quả. Mọi trang dùng cùng SITE_NAV_SECTIONS, renderer Nexlink và token theme hiện hành. Không đưa rail React của bản tham chiếu vào chồng lên shell cũ.

- Giữ rail 80px, panel 240px/220px, header 80px và bo góc 8px. Panel phủ lên nội dung, không làm co bảng.
- Icon tags từ bộ Nexlink hiện có đại diện phân hệ, chỉ thêm viền tím nhạt/gradient theo token khi hover hoặc active. Các menu khác giữ cùng hành vi, typography và khoảng cách.
- Desktop có hover preview 160ms, rời vùng đóng sau 220ms; click giữ mở, click cùng nhóm thu lại. Preview không ghi localStorage, không đổi nhóm khi panel đang giữ focus bàn phím. Touch dùng click/overlay hiện hành.
- Năm nhóm nghiệp vụ và một cụm kết quả sản phẩm chứa 18 liên kết. Mười neo mới nằm trong trang tổng quan Vietlott; bảy trang sản phẩm giữ nguyên địa chỉ.
- Tần suất/cặp/hot-cold được tính trên số chính và cửa sổ kỳ đang công bố của từng sản phẩm. Không trộn số đặc biệt, Max 3D hoặc Bingo18 vào thống kê set.
- Bộ số và đối chiếu lấy từ engine hiện hữu. Bằng chứng e-value và sổ kiểm định tổng hợp thuộc mô hình tự học trực tuyến, được ghi rõ để không nhầm với ML. Mốc học của dự báo lấy từ chính bản dự báo.
- Trạng thái dữ liệu là snapshot tại thời điểm dựng; không giả làm heartbeat crawler realtime. Tham số/danh mục mô hình là chỉ đọc, không tạo nút lưu hoặc huấn luyện giả trên website tĩnh.

Tái dựng toàn bộ shell: `PYTHONPATH=src python scripts/refresh_navigation.py`. Dựng dữ liệu và nội dung Vietlott: `PYTHONPATH=src python src/build_vietlott_results.py` (cần cài engine).

Kiểm chứng: pytest liên quan, bộ JavaScript, kiểm thử Chromium trên 320/390/768/1440px ở hai theme cho index/dashboard/Vietlott (24 trạng thái), thêm hover/click desktop và mọi link phải nhận được thao tác. Kết quả CI/ảnh chụp thực tế đi kèm PR phát hành.
