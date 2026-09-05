# So sánh các nguồn công khai

Xác minh lần cuối: 2026-09-03, chỉ sử dụng các trang công khai. Không truy cập
xác thực, CAPTCHA, API riêng tư hay mã nguồn độc quyền. Nhãn và điều khiển trên
trang cho biết dịch vụ cung cấp gì, nhưng không bộc lộ toàn bộ quy tắc xếp hạng.
Mọi phần tái dựng trong VLA dưới đây đều là **bản triển khai độc lập dựa trên
hành vi quan sát được công khai**.

## Quan sát theo nguồn

| Nguồn | Chức năng quan sát được công khai | Hành vi có thể suy ra | Điểm mơ hồ / độ tin cậy |
| --- | --- | --- | --- |
| [mketqua.net](https://mketqua.net/) | Tần suất, tần suất cặp, chu kỳ, gan, đầu/đuôi, bảng điều kiện, lô rơi, cầu lô tô/đặc biệt/bạch thủ/hai nháy | Điều khiển ngày/cửa sổ; bảng số lần xuất hiện; cấu hình biên cầu chạy/độ dài chuỗi; hiển thị vị trí nguồn và số ngày liên tiếp | Số đếm mô tả: cao. Cách liệt kê/xếp hạng mẫu chính xác: trung bình/thấp. |
| [hainhay.net](https://hainhay.net/) | Chu kỳ, tần suất, tần suất cặp, gan, đầu/đuôi, thống kê điều kiện, cầu lô tô/hai nháy/bạch thủ/đặc biệt | Trang chu kỳ hiển thị khoảng lớn nhất, ngày lịch sử và khoảng cách kỳ hiện tại; điều hướng tách riêng từng họ mục tiêu | Diễn giải chu kỳ: cao. Cách chọn cầu độc quyền: thấp. |
| [rongbachkim.net](https://rongbachkim.net/thongke.html) | Lưới lịch sử 00..99, số lần xuất hiện theo ngày, dấu giải đặc biệt, xem sâu chu kỳ/gan | Chú giải tách rõ không về, về một, hai, ba và bốn lần; cửa sổ ngày có thể cấu hình | Ngữ nghĩa số lần xuất hiện: cao. Sắp xếp/chấm điểm nội bộ: thấp. |
| [xosodaiphat.com](https://xosodaiphat.com/) | Gan, cặp cùng kỳ, kép, đầu/đuôi, đặc biệt, tần suất, tần suất cặp, lần xuất hiện và chu kỳ | Công cụ cùng kỳ nhận số/khoảng thời gian được chọn và trả về ngày thỏa điều kiện; trang tần suất cặp công bố bố cục 50 cặp | Quan hệ mô tả: cao. Diễn giải dự báo: không có bằng chứng. |
| [minhngoc.net.vn](https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html) | Tra cứu lô tô, gan cực đại, tần suất theo miền/tỉnh và loại mục tiêu | Biểu mẫu công khai nhận truy vấn 2–4 chữ số, số kỳ/ngày, chế độ lô tô/đầu-đuôi/đặc biệt; hiển thị khoảng số kỳ vắng mặt lớn nhất | Hành vi truy vấn: cao. Cách tổng hợp lịch quay nhiều tỉnh: trung bình. |
| [Trang Cầu Lô 100 Pascal](https://caulo100.com/soi-cau-pascal-cau-lo-100) | Tam giác chữ số mang nhãn Pascal và dàn số | Mỗi hàng tiếp theo được mô tả công khai là tổng hai số kề nhau rồi lấy hàng đơn vị | Quy tắc truy hồi: trung bình/cao. Cách chọn hạt giống và trích dàn: thấp. Độ tin cậy hiển thị không phải bằng chứng đã hiệu chỉnh. |

## Ma trận so sánh phương pháp

| Phương pháp | Tên gọi khác | Triển khai trong VLA | Cơ sở toán học | Tham số chính | Giá trị mô tả | Rủi ro rò rỉ | Trạng thái dự báo |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lô gan | gan, lô khan | `gap_cycle_stats.compute_gap_stats` | Số kỳ hoàn tất từ lần về gần nhất, luôn trước ngày mục tiêu | ngày chốt, cửa sổ | Độ gần/kiểm duyệt phải | Trung bình | Chỉ mô tả; bác bỏ diễn giải “đến hạn” |
| Tần suất | số lần về | `frequency_stats.compute_frequency_stats` | Tổng số lần xuất hiện và tổng số ngày có mặt | cửa sổ lịch/số kỳ | Cao | Trung bình | Chưa kiểm định |
| Tần suất cặp | cặp cùng về, lịch sử lô xiên | `pair_stats`, `build_cooccurrence_matrix` | Số đếm/mức hỗ trợ/độ nâng cùng kỳ | cửa sổ, hỗ trợ | Cao | Trung bình | Chưa kiểm định |
| Chu kỳ | nhịp | `gap_cycle_stats` | Khoảng kỳ/ngày giữa hai lần về | cửa sổ, khoảng gần đây | Cao | Thấp | Chưa kiểm định |
| Đầu/đuôi | hàng chục/hàng đơn vị | `number_reference`, `frequency_stats` | Nhóm chữ số hàng chục/hàng đơn vị | nhóm/cửa sổ | Cao | Thấp | Chưa kiểm định |
| Tổng | tổng đề | `digit_sum`, `digit_sum_mod10` | `a+b` hoặc `(a+b) mod 10`, ghi rõ tên | tổng thô/modulo 10 | Cao | Thấp | Chưa kiểm định |
| Chạm | chạm đầu/đuôi | `dan_cham`, thống kê nhóm | `a=d hoặc b=d` | chữ số/cửa sổ | Cao | Thấp | Chưa kiểm định |
| Lộn | đảo | `number_reference.reverse` | `AB↔BA` | không có | Cao | Không | Chỉ là phép biến đổi tất định |
| Cặp 50 | cặp lô tô, kép-bóng | `number_reference.cap_loto_50` | 45 cặp đảo + 5 cặp kép-bóng | không có | Cao | Không | Chỉ là quan hệ thử nghiệm |
| Bộ/bóng | bộ, hệ, bóng dương/âm | `number_reference` | Ánh xạ chữ số đã định nghĩa và quỹ đạo sinh | quy ước | Trung bình/cao | Trung bình nếu được chọn | Chỉ là quan hệ thử nghiệm |
| Cầu vị trí động | cầu chạy, ghép vị trí | `dynamic_cau.find_running_patterns` | Chữ số ngữ nghĩa trễ một ngày + phép biến đổi tất định + chuỗi liên tiếp | vị trí, chuỗi, hỗ trợ, mục tiêu | Khai phá mẫu | Cao | Chỉ nghiên cứu, chưa kiểm định |
| Cầu lộn | cầu cặp đảo | phép `reverse_pair` trong `dynamic_cau` | Tập ứng viên `{AB,BA}` | vị trí/chuỗi | Khai phá mẫu | Cao | Chỉ nghiên cứu, chưa kiểm định |
| Cầu 2 nháy | hai nháy | mục tiêu `loto_2_nhay` trong `dynamic_cau` | Một số được dự báo riêng xuất hiện ít nhất hai lần | vị trí/chuỗi/hỗ trợ | Nhận biết số lần xuất hiện | Cao | Chỉ nghiên cứu, chưa kiểm định |
| Cầu giải đặc biệt | cầu đề, cầu ĐB | mục tiêu `special` trong `dynamic_cau` | Ứng viên chứa hai số cuối ĐB kế tiếp | vị trí/chuỗi | Khai phá mẫu | Cao | Chỉ nghiên cứu, chưa kiểm định |
| Ma trận điều kiện | lô tô theo lô tô/ĐB | `conditional_matrices`, `conditional_nextday` | Số đếm nguồn–đích theo ngày lịch chính xác và tỷ lệ có làm trơn | alpha, ngày chốt | Cao | Cao | Chưa kết luận/chỉ nghiên cứu |
| Luật kết hợp | A→B | `association_rules.mine_association_rules` | mức hỗ trợ, độ tin cậy, độ nâng, cận dưới Wilson | ngưỡng, độ trễ | Cao | Cao | Chưa kiểm định |
| Markov | mô hình chuyển tiếp | `markov_stats.build_markov_chain` | Chuyển tiếp bậc một có làm trơn cộng | alpha, trạng thái | Trung bình | Cao | Chưa kết luận/chỉ nghiên cứu |
| Điểm ứng viên | chỉ số nổ, điểm | `candidate_scoring.rank_candidates` | Các thành phần chuẩn hóa có trọng số rõ ràng | trọng số, EMA, cửa sổ | Giải thích/xếp hạng | Trung bình | Chưa kiểm định; không gọi là xác suất |
| Pascal | tam giác Pascal | Chưa triển khai | Truy hồi tổng kề nhau modulo 10 công khai; ánh xạ chưa đủ rõ | hạt giống/độ sâu/cách trích | Chỉ là phép biến đổi | Cao | Bác bỏ cho tới khi có ánh xạ tái lập được |
| Fibonacci | cầu Fibonacci | Chưa triển khai | Truy hồi Fibonacci; không tìm thấy ánh xạ xổ số | chưa xác định | Chưa có | Cao | Bác bỏ vì thiếu đặc tả |
| Đồ thị | mạng số | Chưa có; đã có nền ma trận | Tóm tắt đồ thị có trọng số | cạnh/ngưỡng | Có thể hữu ích mô tả | Cao | Chỉ dự kiến nghiên cứu |

## Ranh giới bằng chứng

- Các nguồn đều cung cấp thống kê lịch sử và công cụ tìm mẫu. Điều đó xác lập
  thuật ngữ và phép biến đổi quan sát được, không chứng minh kỹ năng dự báo.
- Không thể khôi phục cách liệt kê, cắt tỉa, xếp hạng hay công thức “độ tin cậy”
  độc quyền từ đầu ra công khai; VLA không bịa đặt các phần đó.
- Bố cục cặp 50 chuẩn của VLA khớp bảng 50 cặp công khai quan sát được tại Xổ
  Số Đại Phát, gồm cả năm cặp kép-bóng.
- Các trang Pascal công khai có mô tả tương tự nhau, nhưng sự giống nhau không
  chứng minh tính độc lập hay khả năng dự báo. VLA chỉ ghi quy tắc truy hồi thấy được.
- Không có ánh xạ Fibonacci→xổ số công khai nào đủ chính xác vượt ngưỡng tài
  liệu, vì vậy không thêm triển khai.
