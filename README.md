# Phân tích xổ số Việt Nam — bản vận hành hoàn toàn trên GitHub

Bộ mã nguồn vận hành hoàn toàn trên GitHub để tự động thu thập dữ liệu XSMB, xây dựng thống kê, chạy AI/ML, đánh giá mô hình và xuất bảng điều khiển tĩnh bằng **GitHub Actions + GitHub Pages**. Không cần máy chủ riêng hay dịch vụ nền chạy thường trực.

> Mục đích của hệ thống là phân tích dữ liệu lịch sử và nghiên cứu xác suất. Kết quả AI/ML là tín hiệu thống kê, không bảo đảm kết quả tương lai.

## Ảnh chụp dữ liệu mới nhất

<!-- SNAPSHOT:BEGIN -->
| Xổ số | LOTO |
| :------------: | :----------: |
| <table><tr><td>Ngày</td><td>21-09-2026</td></tr><tr><td>Giải Đặc Biệt</td><td>40432</td></tr><tr><td>Giải nhất</td><td>24099</td></tr><tr><td>Giải nhì</td><td>55531, 71590</td></tr><tr><td>Giải ba</td><td>34708, 71314, 17048, 80130, 32086, 88432</td></tr><tr><td>Giải tư</td><td>4429, 0668, 3096, 7372</td></tr><tr><td>Giải năm</td><td>7959, 7383, 0254, 3316, 9446, 3893</td></tr><tr><td>Giải sáu</td><td>613, 300, 732</td></tr><tr><td>Giải bảy</td><td>56, 78, 32, 75</td></tr></table> | <table><tr><td>Đầu</td><td>Đuôi</td></tr><tr><td>0</td><td>8, 0</td></tr><tr><td>1</td><td>4, 6, 3</td></tr><tr><td>2</td><td>9</td></tr><tr><td>3</td><td>2, 1, 0, 2, 2, 2</td></tr><tr><td>4</td><td>8, 6</td></tr><tr><td>5</td><td>9, 4, 6</td></tr><tr><td>6</td><td>8</td></tr><tr><td>7</td><td>2, 8, 5</td></tr><tr><td>8</td><td>6, 3</td></tr><tr><td>9</td><td>9, 0, 6, 3</td></tr></table> |
<!-- SNAPSHOT:END -->

<!-- FUN_PREDICTION:BEGIN -->
## 🎲 Dự đoán vui ngày 22-09-2026

> **Ngày neo:** kết quả thực đến **21-09-2026**. **Không phải kết quả thật.** Dự đoán vui/mô phỏng để tham khảo. Mô hình chỉ ước lượng xác suất 2 số cuối; các chữ số tiền tố trong bảng giải đầy đủ là số tổng hợp tất định, không phải xác suất dự đoán giải 3–5 chữ số và không bảo đảm kết quả thực tế.

### Bảng mô phỏng đầy đủ

| Giải | Dự đoán vui |
|---|---|
| Đặc Biệt | `26953` |
| Giải nhất | `44729` |
| Giải nhì | `56409` · `57138` |
| Giải ba | `92813` · `95827` · `92619` · `57696` · `07911` · `72903` |
| Giải tư | `2893` · `4371` · `2344` · `7411` |
| Giải năm | `0455` · `7613` · `8358` · `6713` · `7537` · `0139` |
| Giải sáu | `656` · `729` · `133` |
| Giải bảy | `21` · `37` · `93` · `63` |

### LOTO đứng đầu cho ngày mai

| # | Số | Xác suất mô hình |
|---:|:---:|---:|
| 1 | **86** | **23.57%** |
| 2 | **06** | **23.55%** |
| 3 | **96** | **23.55%** |
| 4 | **26** | **23.54%** |
| 5 | **78** | **23.54%** |
| 6 | **90** | **23.54%** |
| 7 | **00** | **23.54%** |
| 8 | **98** | **23.54%** |
| 9 | **66** | **23.54%** |
| 10 | **72** | **23.53%** |

### Đặc Biệt đứng đầu cho ngày mai

| # | Số | Xác suất mô hình |
|---:|:---:|---:|
| 1 | **85** | **1.006%** |
| 2 | **65** | **1.005%** |
| 3 | **24** | **1.005%** |
| 4 | **89** | **1.004%** |
| 5 | **97** | **1.004%** |
| 6 | **76** | **1.003%** |
| 7 | **62** | **1.003%** |
| 8 | **30** | **1.003%** |
| 9 | **08** | **1.003%** |
| 10 | **31** | **1.003%** |

> Xác suất ở bảng LOTO là xác suất mô hình cho số 00–99 xuất hiện trong kỳ; xác suất Đặc Biệt là phân phối riêng cho 2 số cuối giải Đặc Biệt. Các chữ số tiền tố trong bảng mô phỏng đầy đủ được sinh tất định để tạo bảng vui, không phải dự báo xác suất cho toàn bộ số 3–5 chữ số.
<!-- FUN_PREDICTION:END -->

## Kiến trúc vận hành

<!-- AUTOMATION:BEGIN -->
## ⚙️ Tự động hóa không cần can thiệp

Hệ thống vận hành tự động bằng GitHub Actions; không cần chạy cron/VPS bên ngoài trong cấu hình mặc định.

| Lớp tự động | Giờ Việt Nam | Hành vi |
|---|---|---|
| Gần thời gian thực chính | **18:00** | Mở cửa sổ trực tiếp trước giờ quay, thăm dò khoảng 15 giây/lần và kiểm chứng nhiều nguồn. |
| Bộ giám sát trực tiếp | **17:55, 18:05, 18:15, 18:25, 18:45** | Nếu dữ liệu trực tiếp chưa có nhịp báo của ngày hiện tại, tự gọi lại quy trình trực tiếp. |
| Hoàn tất hằng ngày | **18:30, 18:40, 18:50, 19:00, 19:10, 19:20, 19:30, 19:45, 20:00** | Thăm dò/tải, yêu cầu ≥2 nhóm nhà cung cấp độc lập, ghi dữ liệu chuẩn trước rồi mới chạy thống kê + AI/ML + dự báo + README + Pages. |
| Phục hồi dữ liệu chuẩn | **19:05, 19:25, 19:45, 20:05** | Nếu dữ liệu chuẩn còn cũ hoặc kiểm toán artifact không đạt, tự gọi lại quy trình hoàn tất hằng ngày. |
| Phục hồi Pages | **20:10–20:35** | Thử lại việc triển khai Pages độc lập khi dữ liệu chuẩn đã ổn. |
| Lưới an toàn qua đêm | **07:15** | Kiểm tra lại dữ liệu chuẩn, dự báo, README, artifact mô hình, bảng điều khiển và đối soát dữ liệu trực tiếp. |
| Hậu kiểm hoàn tất | Sau mỗi lượt hằng ngày thành công | Kiểm toán vận hành đầy đủ và đồng bộ nhánh `live` về đúng dữ liệu chuẩn `complete_verified`. |



## Thống kê 1 năm hiện tại

- Tần suất lớn nhất: **121.0**
- Tần suất nhỏ nhất: **81.0**
- Trung bình: **97.47**
- Độ lệch chuẩn: **9.51**

![Ma trận nhiệt tần suất](images/heatmap.jpg)

![10 số đứng đầu](images/top-10.jpg)

![Phân phối](images/distribution.jpg)

