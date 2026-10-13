# Lô nhiều nháy (≥ 2 nháy một kỳ) — bộ lọc VIP và phép đo trên 4 228 kỳ

Ngày 08-10-2026. Mã: `src/multi_hit_vip.py`. Phép kiểm: `tests/test_multi_hit_vip.py`.

## Kết luận

Trên 4 228 kỳ XSMB thật, chọn top-5 của bộ lọc (bốn lớp đặc trưng, trọng số tự tối ưu) trúng
"nhiều nháy" **2,91%** số lượt chọn (606 lượt), KTC95 2,68–3,15%. Chọn bừa trên chính các kỳ ấy
kỳ vọng **2,91%** (607,2 lượt). Top-3: 2,87% so với 2,91%. Bộ lọc không hơn chọn bừa (z = −0,05,
p = 0,52). Phép đo đủ nhạy để thấy một lợi thế chỉ ×1,13, nên mức
15–25% (gấp 4–6 lần nền) mà đặc tả ban đầu đặt ra bị bác chắc chắn.

Bộ lọc không mù: trên lịch sử giả định có cài tín hiệu, nó đưa đúng ba con được cài lên top-3
và trúng 19,5%, so với 3,65% của chọn bừa trên cùng lịch sử (×5,3, z = +12,2). Vì vậy kết luận "không có tín hiệu" là của dữ liệu, không phải
của công cụ đo.

Bộ lọc không vào tổ hợp xác suất. Theo luật đề bạt của kho, một mô hình chỉ được đưa vào khi
thắng cả dự báo hằng số, và bộ lọc này không thắng. Từ 13-10-2026 nó có trang riêng
`docs/lo-vip-nhieu-nhay.html`, in TỪ phép đo (mục cuối).

## Mức nền

Một kỳ có 27 lô, gần như đều trên 00–99. Số nháy của một con định trước là X ~ Binomial(27, 1/100):

    P(X ≥ 2) = 1 − 0,99²⁷ − 27 · 0,01 · 0,99²⁶ = 2,975 %

| Khẳng định trong đặc tả | Đo trên 4 228 kỳ |
|---|---|
| P(một con ≥ 2 nháy) ≈ 3,8–4,5% | 2,916% (lý thuyết 2,975%) |
| Mỗi kỳ có 21–23 số khác nhau | 23,83 (lý thuyết 100 · (1 − 0,99²⁷) = 23,77) |
| Lô gan > 10 kỳ thì nổ ≥ 2 nháy < 1,2% | 2,94%, KTC95 2,75–3,15% (n = 27 856) |
| Vừa ra 2 nháy trong 5 kỳ thì nên cộng điểm | 2,99%, KTC95 2,85–3,13% (n = 57 619) |

Gan và "vừa nổ" đều cho đúng mức nền. Không lớp nào trong bộ lọc được đặt luật cứng dựa trên hai
khẳng định ấy.

## Bộ lọc

Đặc trưng của kỳ t chỉ đọc các kỳ 0..t−1. Có phép kiểm canh luật này (xem mục Kiểm thử).

1. **Tần suất & điểm rơi.** Gồm tần suất trong 30 kỳ, đà về (EWMA 5 kỳ − EWMA 30 kỳ), độ dài
   chuỗi trúng và độ gan.
2. **Dị thường Poisson.** Lấy số kỳ ≥ 2 nháy trong cửa sổ, đổi ra điểm z so với kỳ vọng nhị
   thức. Kèm chỉ số phân tán var/mean − 1, bằng 0 với Poisson.
3. **Đồng xuất hiện.** Ước lượng P(i ≥ 2 nháy ở t | j về ở t−1), làm trơn Beta về mức nền, rồi
   lấy log-lift trung bình theo số nháy của các con đã về kỳ trước.
4. **Cầu nhịp.** Con số đã về 3–5 lần liên tiếp cùng khoảng cách, và kỳ t đúng là kỳ tiếp theo
   của nhịp ấy.

Cách chấm và chọn:

- **VIP Score.** VIP_Score = Σ wₖ · thành phầnₖ. Mỗi thành phần được chuẩn hoá chéo 100 số
  (z-score, hoặc min-max qua tùy chọn).
- **Chọn trọng số.** Trọng số chọn trên lưới đơn hình bước 0,1 (286 vector), bằng 30 kỳ ngay
  trước kỳ dự báo: ưu tiên số lần trúng top-k, hoà thì xét AUC.
- **Đánh giá.** Walk-forward lồng nhau: kỳ t được chấm bằng trọng số chọn trên [t − 30, t). Vì
  vậy tỉ lệ trúng báo ra không mang thiên lệch của phép chọn.
- **Xác suất hiển thị.** Hiệu chỉnh Platt trên các cặp (điểm, kết quả) ngoài mẫu. Không có tín
  hiệu thì xác suất về mức nền; kỳ tới (sau 07-10-2026), top-5 nhận 2,86–2,89%.
- **Confidence (High/Medium/Low).** Suy từ phép so một phía của số lượt trúng ngoài mẫu với chọn
  bừa trên CHÍNH các kỳ ấy: mỗi kỳ, chọn bừa k trong 100 con theo phân phối siêu bội, cộng qua các
  kỳ ra điểm z (cùng hàm `random_pick_null` với lượt thử thứ hai). High: p < 0,01; Medium:
  p < 0,05; cả hai đều đòi lift > 1. Một con chỉ tin được tới mức bộ
  lọc đã chứng minh.

## Kết quả

Walk-forward ngoài mẫu qua 4 168 kỳ (kỳ thứ 61 tới kỳ cuối):

| | Lượt chọn | Trúng | Tỉ lệ | Chọn bừa | Lift | p một phía |
|---|---|---|---|---|---|---|
| Top-5, trọng số tự tối ưu | 20 840 | 606 | 2,91% | 2,91% | ×1,00 | 0,52 |
| Top-3, trọng số tự tối ưu | 12 504 | 359 | 2,87% | 2,91% | ×0,99 | 0,61 |
| Top-5, trọng số cố định gần đặc tả (0,3/0,3/0,2/0,2) | 20 840 | 589 | 2,83% | 2,91% | ×0,97 | — |
| Top-5, trọng số tốt nhất **nhìn lại** | 20 840 | 682 | 3,27% | 2,91% | ×1,12 | — |

Dòng cuối chọn vector trọng số tốt nhất trên chính 4 168 kỳ kiểm, tức cố tình rò rỉ. Ngay cả gian
lận ấy cũng chỉ được 3,27%. Mức này là thiên lệch do chọn cái tốt nhất trong 286 vector, không
phải kỹ năng: chọn trên 30 kỳ trước rồi kiểm ngoài mẫu thì nó về 2,91%.

**Phá hoà (sửa 12-10-2026).** Bản đầu xếp hạng bằng sắp xếp ổn định, nên điểm hoà luôn chọn số nhỏ.
Thành phần cầu nhịp thưa (phần lớn 100 con cùng điểm), nên ở các kỳ trọng số dồn hết vào cầu nhịp,
52% lượt chọn rơi vào 00–04 thay vì 5%. Phép chọn trọng số vì thế có thể thưởng cho một chiến lược
"chọn 00–04" không ai khai báo. Nay chọn trọng số, backtest và dự báo cùng xếp qua `rank_order`:
hoà được phá bằng một hoán vị cố định theo từng kỳ, và tỉ lệ 00–04 ở các kỳ ấy về 4,95%. Các con
số trong mục này là của bản đã sửa; bản cũ cho top-5 2,89% (603 lượt trúng), top-3 2,91%.

**Mốc so sánh (sửa 12-10-2026).** Bản đầu so số lượt trúng với mức nền LÝ THUYẾT 2,975% bằng kiểm
định nhị thức. Nhưng 4 168 kỳ chấm có tỉ lệ thực 2,914%, nên chọn bừa trên chính các kỳ ấy chỉ kỳ
vọng 607 lượt chứ không phải 620. So với lý thuyết thì lift, p và Confidence không đo điều tài liệu
nói ("hơn chọn bừa"), và một lịch sử có tỉ lệ thực cao hơn lý thuyết sẽ làm cả chọn bừa trông như
có kỹ năng. Nay cột "Chọn bừa", lift và p đều so với chọn bừa trên chính các kỳ đã chấm. Bản cũ
cho p = 0,72.

Độ nhạy: với 20 840 lượt chọn, α = 0,01 một phía và lực 80%, phép đo phát hiện được tỉ lệ thật
≥ 3,29% (lift ×1,13 so với chọn bừa).

## Tái lập

    python3 src/multi_hit_vip.py --mock                          # 100 kỳ giả định, quay công bằng
    python3 src/multi_hit_vip.py --mock --plant                  # cài tín hiệu cho 07, 38, 68
    python3 src/multi_hit_vip.py --csv data/xsmb-2-digits.csv --until 2026-10-07              # 4 228 kỳ, ~20 giây
    python3 src/multi_hit_vip.py --csv data/xsmb-2-digits.csv --until 2026-10-07 --top-k 3 --json /tmp/vip.json

CSV lịch sử dài thêm mỗi ngày; `--until` chốt đúng các kỳ của phép đo đã công bố.

## Kiểm thử

`tests/test_multi_hit_vip.py` gồm 16 phép kiểm. Đã thử mười lăm đột biến và cả mười lăm đều đỏ:

- cửa sổ đặc trưng gồm cả kỳ đang dự báo (nhìn trước);
- cửa sổ chọn trọng số gồm cả kỳ t;
- cầu nhịp lệch một kỳ;
- đồng xuất hiện ghép cùng kỳ thay vì kỳ trước → kỳ sau;
- hiệu chỉnh bỏ qua điểm;
- Confidence không đòi lift > 1;
- hằng số bị chuẩn hoá thành khác 0;
- lưới trọng số thiếu đỉnh;
- phá hoà theo thứ tự số ở chọn trọng số, ở backtest hoặc ở dự báo (ba đột biến);
- khoá phá hoà không đổi theo kỳ;
- bỏ qua `--until`;
- so với mức nền lý thuyết thay vì chọn bừa trên chính các kỳ đã chấm;
- kỳ vọng của chọn bừa tính cả các kỳ không được chấm.

## Lượt thử thứ hai — 12-10-2026

Chủ dự án thấy tỉ lệ trúng còn quá thấp và yêu cầu thử lại. Lượt này không tinh chỉnh bộ lọc cũ
mà dò rộng: 22 cách chấm thuộc mọi họ ý tưởng thường gặp, gồm cả hai mô hình học trên toàn bộ
đặc trưng. Mã: `scripts/benchmark_multi_hit.py`. Phép kiểm: `tests/test_benchmark_multi_hit.py`.

### Giao thức, cố định trước khi chạy

- Mọi chiến lược chấm kỳ t chỉ từ các kỳ < t. Hoà điểm phá bằng nhiễu cố định, không thiên về số
  nhỏ.
- Giai đoạn phát triển: kỳ 615–3 232 (2 618 kỳ). Giai đoạn kiểm: 1 000 kỳ cuối (kỳ 3 233–4 232, tới
  12-10-2026).
- Phép so: top-5 so với chọn bừa 5 trong 100 con của CÙNG kỳ (phân phối siêu bội). Nhờ vậy phép so
  giữ đúng dao động của chính các kỳ đã quay.
- Chiến lược có z cao nhất ở giai đoạn phát triển là ứng viên DUY NHẤT. Giai đoạn kiểm chỉ quyết
  định ứng viên ấy, ngưỡng p một phía < 0,01. Chọn cái tốt nhất trên giai đoạn kiểm là rò rỉ.

Các họ đã thử:

- tần suất nhiều nháy và tổng nháy ở cửa sổ 7/30/100/365 kỳ và toàn lịch sử, cả "nóng" lẫn
  "lạnh";
- lô gan dài nhất và vừa về;
- lặp lại kỳ trước;
- cùng thứ trong 52 tuần;
- thiên lệch theo vị trí giải (mỗi vị trí một phân phối, Poisson-nhị thức);
- thiên lệch chữ số hàng chục/đơn vị;
- bộ lọc VIP lượt đầu;
- hồi quy logistic và cây tăng cường (HistGradientBoosting) trên 19 đặc trưng, khớp lại mỗi 250 kỳ.

### Kết quả trên dữ liệu thật

Nền thực đo: 2,91% ở giai đoạn phát triển, 2,95% ở giai đoạn kiểm (lý thuyết 2,975%).

| Chiến lược | Phát triển: tỉ lệ | z | p Holm | Kiểm: tỉ lệ | z |
|---|---|---|---|---|---|
| `repeat_yesterday` (lặp kỳ trước) — **ứng viên** | 3,24% | +2,28 | 0,26 | 3,08% | +0,54 |
| `repeat_multi_yesterday` | 3,21% | +2,07 | 0,43 | 2,92% | −0,14 |
| `gan_shortest` (vừa về) | 3,12% | +1,43 | 1,00 | 3,28% | +1,40 |
| `multi_hot_all` | 3,05% | +0,95 | 1,00 | 3,26% | +1,31 |
| `random` (chọn bừa, đối chứng) | 3,02% | +0,73 | 1,00 | 3,02% | +0,29 |
| `gbm_all_features` | 2,92% | +0,04 | 1,00 | 2,22% | −3,14 |
| `vip_v1` (bộ lọc lượt đầu) | 2,93% | +0,15 | 1,00 | 3,02% | +0,29 |
| `logistic_all_features` | 2,83% | −0,60 | 1,00 | 2,96% | +0,03 |
| `nhay_hot_100` | 2,99% | +0,57 | 1,00 | 3,50% | +2,34 |
| `digit_bias` | 2,67% | −1,66 | 1,00 | 3,44% | +2,08 |

Bảng đầy đủ 23 dòng in ra khi chạy script.

Các kết luận:

- **Không chiến lược nào đạt.** Ứng viên trúng 3,08% ở giai đoạn kiểm, z = +0,54, p = 0,29. Ở giai
  đoạn phát triển, sau hiệu chỉnh Holm, cũng không chiến lược nào có ý nghĩa: p nhỏ nhất là 0,26.
- **Ai thắng giai đoạn này không thắng giai đoạn sau.** Tương quan hạng (Spearman) giữa z ở hai
  giai đoạn qua 22 chiến lược là −0,02, tức không có gì. Trên lịch sử có cài tín hiệu, con số ấy là
  +0,93. `nhay_hot_100` và `digit_bias` đứng đầu giai đoạn kiểm, nhưng ở giai đoạn phát triển lại
  dưới nền. Đó là dấu hiệu của dao động ngẫu nhiên.
- **Hai mô hình học không hơn.** Logistic ngang nền. GBM ngang nền ở giai đoạn phát triển rồi
  kém ở giai đoạn kiểm (z = −3,14). Với 23 chiến lược, xác suất có ít nhất một |z| ≥ 3,14 do ngẫu
  nhiên là khoảng 4%. Vì vậy đây không được coi là phát hiện.

### Độ nhạy

`--power-check` chạy đúng giao thức trên lịch sử giả định cùng độ dài. Ba con 07, 38, 68 được cài
thêm ≥ 2 nháy với xác suất 3%/kỳ, tức tỉ lệ của chúng từ ~3% lên ~6%. Kết quả:

- Ứng viên là `multi_hot_all`, z = +11,99 ở giai đoạn phát triển.
- Ở giai đoạn kiểm, ứng viên trúng 4,52% so với nền 3,01%, z = +6,40: đạt.
- Logistic và GBM cũng bắt được tín hiệu, với z lần lượt +6,31 và +6,74 ở giai đoạn kiểm.

Công cụ đo không mù. Dữ liệu thật đơn giản là không có tín hiệu cỡ ấy.

### Muốn "trúng thường hơn" thì chỉ còn cách chọn nhiều hơn

Bảng dưới là tỉ lệ kỳ có ÍT NHẤT một con trong top-k trúng, đo trên 1 000 kỳ kiểm:

| k con | ≥ 2 nháy: ứng viên / chọn bừa | ≥ 1 nháy: ứng viên / chọn bừa |
|---|---|---|
| 1 | 3,4% / 2,4% | 22,6% / 22,2% |
| 3 | 9,2% / 8,4% | 54,4% / 53,8% |
| 5 | 14,4% / 14,8% | 73,9% / 74,2% |
| 10 | 26,8% / 27,1% | 93,8% / 94,1% |
| 20 | 46,6% / 47,5% | 99,9% / 99,4% |

Tần suất "có trúng" tăng theo số con chọn, không theo cách chọn. Số tiền phải đặt cũng tăng đúng
theo tỉ lệ ấy. Tỉ lệ trúng của MỖI con vẫn ở mức nền: 2,975% cho ≥ 2 nháy, 23,8% cho ≥ 1 nháy.

### Tái lập

    python3 scripts/benchmark_multi_hit.py --until 2026-10-12 --power-check     # khoảng 2 phút, 4 lõi

`tests/test_benchmark_multi_hit.py` gồm 9 phép kiểm, mỗi phép ghim một điều:

- mọi chiến lược, kể cả hai mô hình học, chỉ đọc quá khứ (đổi các kỳ ≥ t0 không đổi điểm ở kỳ ≤ t0);
- z của chọn bừa xấp xỉ N(0, 1);
- ứng viên được chọn chỉ theo giai đoạn phát triển;
- tín hiệu cài sẵn được tìm ra và đạt;
- lịch sử công bằng không đạt;
- mô hình vị trí khởi đầu đúng mức nền;
- Holm đúng;
- phá hoà không thiên về số nhỏ.

Đã thử mười đột biến (nhìn trước một kỳ ở đặc trưng, ở độ gan và ở mô hình học; phương sai sai;
chọn ứng viên theo giai đoạn kiểm hoặc lấy z thấp nhất; Holm không đơn điệu; Poisson-nhị thức
sai; bỏ phá hoà; ngưỡng luôn đạt), cả mười đều đỏ.

Hai đột biến sống sót là tương đương: bỏ một nhóm chiến lược tần suất thì các nhóm còn lại vẫn bắt
được tín hiệu cài sẵn.

## Trang «Lô VIP nhiều nháy» — 13-10-2026

Trang in từ phép đo, đúng như mục này từng đặt điều kiện. Không con số hay kết luận nào được
viết sẵn; luật được ghim trong `tests/test_multi_hit_page.py`.

- **Số đo.** `src/multi_hit_report.py` ghi hai tệp vào `data/multi_hit/`:
  - `vip.json`, đo lại mỗi ngày (~25 giây). Gồm bộ lọc VIP, kiểm chứng walk-forward lồng nhau
    trên mọi kỳ, khoảng Wilson 95%, mức tin, top-5 cho kỳ kế tiếp và 10 kỳ gần nhất của chính
    kiểm chứng.
  - `benchmark.json`, là bản đệm. Gồm giao thức lượt hai và phép kiểm độ nhạy. Tệp chỉ đo lại khi
    lịch sử dài thêm `BENCHMARK_REFRESH_DRAWS` = 30 kỳ, khi `MEASURE_VERSION` đổi, hoặc khi lịch
    sử bị cắt hay viết lại.
- **Mã giao thức.** Giao thức lượt hai chuyển từ `scripts/` sang `src/multi_hit_benchmark.py` để
  pipeline gọi được. `scripts/benchmark_multi_hit.py` nay là lớp vỏ dòng lệnh.
- **Trình dựng.** `src/build_multi_hit_page.py` dựng trang. Kết luận rút từ ba cờ:
  - mức tin của bộ lọc: Trung bình hay Cao thì "hơn chọn bừa";
  - ứng viên lượt hai có qua giai đoạn kiểm hay không;
  - phép kiểm độ nhạy có bắt được tín hiệu cài sẵn hay không. Nếu không bắt được, trang ghi
    "chưa kết luận" thay vì "không hơn".
- **Điều phép kiểm ghim.**
  - Đưa số đo của lịch sử có cài tín hiệu thì CÙNG trình dựng ấy phải in "hơn chọn bừa".
  - Ngưỡng mức tin in trên trang là `multi_hit_vip.CONFIDENCE_P`, không phải bản chép.
- **Vị trí trên site.** Menu Dự báo → Tham khảo theo lịch sử → Lô VIP nhiều nháy.

Không in một con số như "Xác suất 2+ nháy: 28,5%". Trên dữ liệu hiện tại, mọi con đều nhận
Confidence Low và xác suất sát mức nền (2,83–2,88% ngày 12-10-2026).
