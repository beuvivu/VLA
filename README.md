# Phân tích xổ số Việt Nam — bản vận hành hoàn toàn trên GitHub

Bộ mã nguồn vận hành hoàn toàn trên GitHub để tự động thu thập dữ liệu XSMB, xây dựng thống kê, chạy AI/ML, đánh giá mô hình và xuất bảng điều khiển tĩnh bằng **GitHub Actions + GitHub Pages**. Không cần máy chủ riêng hay dịch vụ nền chạy thường trực.

> Mục đích của hệ thống là phân tích dữ liệu lịch sử và nghiên cứu xác suất. Kết quả AI/ML là tín hiệu thống kê, không bảo đảm kết quả tương lai.

## Ảnh chụp dữ liệu mới nhất

<!-- SNAPSHOT:BEGIN -->
| Xổ số | Lô tô |
| :------------: | :----------: |
| <table><tr><td>Ngày</td><td>02-09-2026</td></tr><tr><td>Giải đặc biệt</td><td>44542</td></tr><tr><td>Giải nhất</td><td>70943</td></tr><tr><td>Giải nhì</td><td>20944, 30062</td></tr><tr><td>Giải ba</td><td>60516, 22853, 65620, 02493, 52067, 04270</td></tr><tr><td>Giải tư</td><td>3422, 1237, 4540, 1955</td></tr><tr><td>Giải năm</td><td>9150, 5572, 7077, 4767, 4522, 2340</td></tr><tr><td>Giải sáu</td><td>261, 232, 249</td></tr><tr><td>Giải bảy</td><td>15, 64, 32, 10</td></tr></table> | <table><tr><td>Đầu</td><td>Đuôi</td></tr><tr><td>0</td><td></td></tr><tr><td>1</td><td>6, 5, 0</td></tr><tr><td>2</td><td>0, 2, 2</td></tr><tr><td>3</td><td>7, 2, 2</td></tr><tr><td>4</td><td>2, 3, 4, 0, 0, 9</td></tr><tr><td>5</td><td>3, 5, 0</td></tr><tr><td>6</td><td>2, 7, 7, 1, 4</td></tr><tr><td>7</td><td>0, 2, 7</td></tr><tr><td>8</td><td></td></tr><tr><td>9</td><td>3</td></tr></table> |
<!-- SNAPSHOT:END -->

<!-- FUN_PREDICTION:BEGIN -->
## 🎲 Dự đoán vui ngày 03-09-2026

> **Ngày neo:** kết quả thực đến **02-09-2026**. **Không phải kết quả thật.** Dự đoán vui/mô phỏng để tham khảo. Mô hình chỉ ước lượng xác suất 2 số cuối; các chữ số tiền tố trong bảng giải đầy đủ là số tổng hợp tất định, không phải xác suất dự đoán giải 3–5 chữ số và không bảo đảm kết quả thực tế.

### Bảng mô phỏng đầy đủ

| Giải | Dự đoán vui |
|---|---|
| Đặc biệt | `03102` |
| Giải nhất | `76384` |
| Giải nhì | `66107` · `02399` |
| Giải ba | `55192` · `64851` · `09021` · `38618` · `49128` · `86678` |
| Giải tư | `7027` · `0542` · `7360` · `0661` |
| Giải năm | `7286` · `5586` · `1564` · `1358` · `7202` · `5717` |
| Giải sáu | `668` · `301` · `812` |
| Giải bảy | `60` · `75` · `18` · `61` |

### Lô tô đứng đầu cho ngày mai

| # | Số | Xác suất mô hình |
|---:|:---:|---:|
| 1 | **95** | **25.10%** |
| 2 | **83** | **25.03%** |
| 3 | **52** | **24.79%** |
| 4 | **50** | **24.69%** |
| 5 | **54** | **24.64%** |
| 6 | **64** | **24.64%** |
| 7 | **61** | **24.63%** |
| 8 | **51** | **24.59%** |
| 9 | **13** | **24.58%** |
| 10 | **06** | **24.55%** |

### Đặc biệt đứng đầu cho ngày mai

| # | Số | Xác suất mô hình |
|---:|:---:|---:|
| 1 | **83** | **1.284%** |
| 2 | **68** | **1.181%** |
| 3 | **39** | **1.165%** |
| 4 | **21** | **1.163%** |
| 5 | **54** | **1.162%** |
| 6 | **44** | **1.151%** |
| 7 | **38** | **1.150%** |
| 8 | **23** | **1.141%** |
| 9 | **42** | **1.117%** |
| 10 | **37** | **1.114%** |

> Xác suất ở bảng lô tô là xác suất mô hình cho số 00–99 xuất hiện trong kỳ; xác suất ĐB là phân phối riêng cho 2 số cuối giải đặc biệt. Các chữ số tiền tố trong bảng mô phỏng đầy đủ được sinh tất định để tạo bảng vui, không phải dự báo xác suất cho toàn bộ số 3–5 chữ số.
<!-- FUN_PREDICTION:END -->

## Kiến trúc vận hành

### Nguồn dữ liệu theo thứ tự ưu tiên

1. `xoso.com.vn`
2. `mketqua.net`
3. `www.minhngoc.net.vn`
4. `xosominhngoc.com`
5. `xosodaiphat.com`
6. `hainhay.net`

Kết quả mới không được ghi thẳng vào lịch sử chỉ vì một trang web đã hiển thị. Với kỳ quay gần nhất, hệ thống chuẩn hóa đúng độ dài từng giải, đối chiếu toàn bộ 27 giá trị và yêu cầu **ít nhất 2 nhóm nhà cung cấp độc lập** đồng thuận. Hai tên miền Minh Ngọc được coi là cùng một nhóm nhà cung cấp để tránh đếm trang phản chiếu như hai xác nhận độc lập.

Dữ liệu trực tiếp là tạm thời và được giữ tách biệt khỏi lịch sử chuẩn cho tới khi đủ đồng thuận.

## Chức năng chính

- Thu thập đa nguồn, thử lại, kiểm toán nguồn và cổng sức khỏe dữ liệu.
- XSMB gần thời gian thực bằng GitHub Actions: 6 nguồn được tải song song, hợp nhất từng ô giải và cập nhật JSON trực tiếp khi dữ liệu thay đổi.
- Bộ phân tích cú pháp nghiêm ngặt: không chèn số 0 vào chỗ trống hoặc số đang quay chưa đủ độ dài.
- Thống kê tần suất, gan, chu kỳ, nháy, đầu/đuôi/tổng, chạm, cặp lộn, lô rơi, ma trận ngày/tuần/tháng/năm.
- Kiểm định thống kê với co Bayes, khoảng tin cậy, kiểm soát nhiều phép thử/FDR và chẩn đoán entropy/dịch chuyển.
- Tín hiệu Bayes thực nghiệm độc lập: suy giảm hàm mũ, hậu nghiệm theo thứ, ổn định đa cửa sổ và co về nền khi tín hiệu không ổn định.
- Bộ máy đường cầu theo vị trí chữ số, chuỗi đang chạy/ổn định, kiểm định cuốn chiếu và bằng chứng vị trí có thể giải thích.
- ML nền với đặc trưng thời gian: thứ của ngày mục tiêu, EWM 14/45, cửa sổ 7/30/90/365, xu hướng, gan/chuỗi, động lực số đảo và mức hỗ trợ đường cầu được vector hóa.
- Chọn mô hình theo thời gian qua 4 tầng: huấn luyện → hiệu chỉnh theo tỷ lệ tự nhiên → chọn mô hình → kiểm định chưa chạm.
- `HistGradientBoostingClassifier` + hiệu chỉnh Platt + trọng số gần đây; mô hình yếu được co về nền lịch sử thay vì phát xác suất quá tự tin.
- Cầu-kèo ML + bằng chứng vị trí.
- Mô hình tổ hợp 5 thành phần: ML nền + cầu-kèo ML + Bayes thống kê + cầu đang chạy + cầu ổn định; trọng số học bằng LogLoss cuốn chiếu có điều chuẩn.
- Mức bất đồng/bất định của mô hình, LogLoss/Brier cuốn chiếu và lịch sử dự báo gọn.
- Bảng điều khiển thích ứng trong `docs/`, triển khai trực tiếp bằng GitHub Pages Actions.
- Tệp xuất an toàn cho Excel, giữ số 0 ở đầu.

## Cài đặt mới hoàn toàn trên GitHub

### 1. Tạo kho mã nguồn

Tạo kho mã nguồn GitHub mới và tải **toàn bộ nội dung gói vào thư mục gốc của kho**.

Khuyến nghị để kho ở chế độ riêng tư trong giai đoạn thử nghiệm; chỉ đổi quyền hiển thị khi Pages và truy cập công khai đã đúng.

### 2. Cho phép GitHub Actions ghi dữ liệu

Vào:

`Settings → Actions → General → Workflow permissions`

Chọn:

`Read and write permissions` (quyền đọc và ghi)

rồi bấm Lưu.

### 3. Bật GitHub Pages bằng GitHub Actions

Vào:

`Settings → Pages → Build and deployment`

Chọn:

`Source: GitHub Actions` (nguồn: GitHub Actions)

Không chọn `Deploy from a branch`; gói đã có quy trình Pages chính thức trong `.github/workflows/pages.yml`.

### 4. Chạy hoàn tất dữ liệu lần đầu

Vào:

`Actions → Hoàn tất XSMB, thống kê và AI/ML → Run workflow`

Lần chạy đầu sẽ:

1. Nạp lịch sử đã ghi nhận.
2. Đồng bộ ngày thiếu từ 6 nguồn.
3. Chỉ đưa kết quả mới vào dữ liệu chuẩn khi vượt cổng kiểm định/đồng thuận.
4. Chạy thống kê và kiểm định.
5. Khớp lại đường cầu.
6. Huấn luyện lại ML nền nếu có kỳ quay mới hoặc lược đồ đặc trưng thay đổi.
7. Chạy cầu-kèo ML và tín hiệu Bayes thực nghiệm.
8. Ghi lịch sử dự báo và cập nhật nhãn.
9. Học trọng số/hiệu chỉnh mô hình tổ hợp khi lịch sử đủ trưởng thành.
10. Dựng bảng điều khiển.
11. Ghi nhận `data/`, `models/`, `images/`, `docs/`, `README.md`.
12. Triển khai trực tiếp `docs/` lên GitHub Pages.

Không cần bí mật GitHub trong cấu hình mặc định.

## XSMB gần thời gian thực

Workflow:

`Kết quả XSMB gần thời gian thực`

được lập lịch lúc **18:04 Asia/Ho_Chi_Minh**. Một tiến trình chạy trong cửa sổ quay và thăm dò khoảng **25 giây/lần**. Mỗi ảnh chụp tải 6 nguồn song song; chỉ dữ liệu thay đổi mới được buộc xuất bản thành `live/live.json` trên nhánh `live`.

`docs/live.html` đọc JSON gốc từ nhánh `live`, vì vậy không phải dựng lại toàn bộ GitHub Pages mỗi lần có thêm một giải.

Các trạng thái trực tiếp:

- `waiting`: đang chờ, chưa có giá trị.
- `live`: đang có kết quả từng phần.
- `complete_provisional`: đủ 27 giá trị nhưng chưa đủ đồng thuận độc lập.
- `complete_conflict`: đã đủ nhưng các nguồn còn xung đột.
- `complete_verified`: toàn bộ 27 ô đã được xác minh; tác vụ trực tiếp có thể dừng.

Nếu kho dùng bảo vệ nhánh, **không áp dụng quy tắc cấm đẩy cưỡng bức cho nhánh `live`**, hoặc loại nhánh này khỏi quy tắc. `main` không bị đẩy cưỡng bức.

> Quy trình GitHub theo lịch có thể bị nền tảng trì hoãn. Vì vậy kiến trúc chỉ dùng GitHub không thể cam kết thời gian thực tuyệt đối như máy chủ luôn chạy. Thiết kế này giảm rủi ro bằng cách mở tác vụ trực tiếp trước giờ quay, thăm dò trong tác vụ và có nhiều mốc hoàn tất/phục hồi sau quay.

## Lịch hoàn tất dữ liệu hằng ngày

Timezone: `Asia/Ho_Chi_Minh`.

- `18:38` — hoàn tất chính.
- `18:53` — phục hồi 1.
- `19:13` — phục hồi 2.

Bộ gác kiểm tra ngày dữ liệu chuẩn trước khi chạy; nếu kỳ hôm nay đã được ghi thành công, các lượt phục hồi không làm gì thêm. Có thể bấm `Run workflow` để chạy thủ công bất kỳ lúc nào.

<!-- AUTOMATION:BEGIN -->
## ⚙️ Tự động hóa không cần can thiệp

Hệ thống vận hành tự động bằng GitHub Actions; không cần chạy cron/VPS bên ngoài trong cấu hình mặc định.

| Lớp tự động | Giờ Việt Nam | Hành vi |
|---|---|---|
| Gần thời gian thực chính | **18:04** | Mở cửa sổ trực tiếp, thăm dò khoảng 25 giây/lần và kiểm chứng nhiều nguồn. |
| Bộ giám sát trực tiếp | **18:10, 18:20** | Nếu dữ liệu trực tiếp chưa có nhịp báo của ngày hiện tại, tự gọi lại quy trình trực tiếp. |
| Hoàn tất hằng ngày | **18:18, 18:28, 18:38, 18:48, 18:58, 19:13, 19:28** | Thăm dò/tải, yêu cầu ≥2 nhóm nhà cung cấp độc lập, ghi dữ liệu chuẩn trước rồi mới chạy thống kê + AI/ML + dự báo + README + Pages. |
| Phục hồi dữ liệu chuẩn | **19:35, 20:05** | Nếu dữ liệu chuẩn còn cũ hoặc kiểm toán artifact không đạt, tự gọi lại quy trình hoàn tất hằng ngày. |
| Phục hồi Pages | **20:20** | Thử lại việc triển khai Pages độc lập khi dữ liệu chuẩn đã ổn. |
| Lưới an toàn qua đêm | **07:15** | Kiểm tra lại dữ liệu chuẩn, dự báo, README, artifact mô hình, bảng điều khiển và đối soát dữ liệu trực tiếp. |
| Hậu kiểm hoàn tất | Sau mỗi lượt hằng ngày thành công | Kiểm toán vận hành đầy đủ và đồng bộ nhánh `live` về đúng dữ liệu chuẩn `complete_verified`. |

Các quy trình phục hồi kiểm tra trạng thái trước khi gọi để tránh tạo tác vụ trùng khi quy trình mục tiêu đang `queued/in_progress`. Việc ghi dữ liệu chuẩn hằng ngày vẫn độc lập với Pages/bộ giám sát, nên lỗi bảng điều khiển hoặc hậu kiểm không giữ lại kết quả hằng ngày đã xác minh.

> Quy trình GitHub theo lịch hoạt động theo khả năng tốt nhất và nguồn dữ liệu bên thứ ba có thể thay đổi/gián đoạn. Bộ giám sát cùng nhiều mốc phục hồi giúp hệ thống tự phục hồi tối đa trong giới hạn kiến trúc chỉ dùng GitHub, nhưng không thể tạo SLA tuyệt đối như bộ lập lịch/máy chủ chuyên dụng.
<!-- AUTOMATION:END -->

## Bảng điều khiển

- `docs/index.html` — trang tổng hợp/bảng điều khiển chính.
- `docs/live.html` — kết quả gần thời gian thực và xác minh nguồn.
- `docs/statistics.html` — thống kê/ma trận nâng cao.
- `docs/dashboard.html` — bảng điều khiển mô hình tổ hợp AI/ML.
- `docs/model-quality.html` — LogLoss/Brier cuốn chiếu.
- `docs/ml_top10_loto.html`, `docs/ml_top10_de.html`.
- `docs/soi-path-loto-active.html`, `docs/soi-path-loto-stable.html`.
- `docs/soi-path-de-active.html`, `docs/soi-path-de-stable.html`.

## Dữ liệu đầu ra

| Bộ dữ liệu | CSV | JSON | XLSX an toàn cho Excel |
|---|---|---|---|
| Kết quả gốc | `data/xsmb.csv` | `data/xsmb.json` | `data/excel/xsmb.xlsx` |
| Hai chữ số | `data/xsmb-2-digits.csv` | `data/xsmb-2-digits.json` | `data/excel/xsmb-2-digits.xlsx` |
| Thưa 00–99 | `data/xsmb-sparse.csv` | `data/xsmb-sparse.json` | `data/excel/xsmb-sparse.xlsx` |

Dữ liệu dẫn xuất:

- `data/source_audit.json` — nguồn gốc/đồng thuận gần đây.
- `data/advanced/` — thống kê nâng cao.
- `data/significance/` — kiểm định/FDR/chẩn đoán.
- `data/statistical_signal/` — thành phần Bayes thực nghiệm.
- `data/path_ui/` — đầu ra đường cầu đang chạy/ổn định.
- `data/ai_ml/` — cầu-kèo ML/evidence.
- `data/ml/` — xác suất ML nền đã hiệu chỉnh.
- `data/ensemble/` — trọng số/hiệu chỉnh mô hình tổ hợp đã học.
- `data/predict/` — xác suất và danh sách chọn cuối của mô hình tổ hợp.
- `data/history/` — lịch sử thành phần cuốn chiếu gọn.
- `data/prob_eval/` — chỉ số chất lượng mô hình cuốn chiếu.
- `models/` — artifact mô hình đã huấn luyện + báo cáo huấn luyện.

## Thống kê 1 năm hiện tại

- Tần suất lớn nhất: **123.0**
- Tần suất nhỏ nhất: **82.0**
- Trung bình: **98.55**
- Độ lệch chuẩn: **10.41**

![Ma trận nhiệt tần suất](images/heatmap.jpg)

![10 số đứng đầu](images/top-10.jpg)

![Phân phối](images/distribution.jpg)

## Kiểm tra chất lượng code

CI chạy khi đẩy mã hoặc mở yêu cầu hợp nhất. Có thể nghiệm thu tương đương trên máy phát triển:

```bash
python -m pip install -r requirements-dev.txt
bash scripts/release_check.sh
```

Kiểm tra phát hành xác minh cú pháp/phân tích tĩnh, kiểm thử đơn vị, chính sách nguồn, thử nhanh huấn luyện/dự báo, thống kê Bayes, tính toàn vẹn dữ liệu và các đầu ra bắt buộc từ dữ liệu đã ghi nhận.

## Cấu trúc repository

```text
.github/workflows/      CI, trực tiếp, hoàn tất hằng ngày, triển khai Pages
src/                    nguồn, kiểm định, thống kê, AI/ML, bộ dựng trang
src/templates/          mẫu để tạo README và trang
tests/                  kiểm thử hồi quy + dữ liệu/nguồn/ML
data/                   dữ liệu chuẩn + đầu ra phân tích
models/                 artifact mô hình đã huấn luyện
images/                 hình trực quan đã tạo
docs/                   trang web tĩnh GitHub Pages
scripts/release_check.sh
requirements*.txt
README.md
```

## Ghi chú về xác suất

Xổ số là quá trình ngẫu nhiên; thêm nhiều thuật toán không biến dữ liệu lịch sử thành bảo đảm dự đoán. Hệ thống ưu tiên hiệu chỉnh, kiểm định ngoài mẫu, co ước lượng và bất đồng mô hình để **giảm khớp quá mức và tự tin quá mức**, thay vì phóng đại tín hiệu yếu.

## Giấy phép

Xem `LICENSE` trong kho mã nguồn.