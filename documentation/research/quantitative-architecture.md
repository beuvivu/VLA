# Kiến trúc thuật toán định lượng cho XSMB

> Báo cáo nghiên cứu định lượng. Mọi con số trong tài liệu này đều tái lập được
> bằng `src/run_randomness_report.py` và `src/run_model_benchmark.py`; không có
> con số nào được viết tay.

---

## Tóm tắt điều hành

Yêu cầu đặt ra là đẩy phân tích lên mức tối đa: đề xuất các mô hình toán học
nâng cao, đánh giá ưu/nhược điểm và độ phức tạp, cung cấp mã minh họa, thiết kế
phương pháp backtesting cùng bộ chỉ số đánh giá, và cuối cùng thiết kế kiến
trúc thuật toán tối ưu nhất.

Báo cáo này làm đủ cả bảy việc đó. Mười một họ mô hình, cộng kiến trúc đề
xuất, được cài đặt và chấm trên cùng một giao thức cuốn chiếu. Kết quả đo được,
trên 391 kỳ thật:

| Điều được kiểm | Kết quả |
|---|---|
| Phép kiểm cấu trúc bác bỏ được tính ngẫu nhiên | **1/7** thô, **0/7** sau Bonferroni |
| Phép dương tính duy nhất có lặp lại ở nửa sau không | **Không** (nửa đầu z=+4.07, nửa sau z=−0.19) |
| Mô hình vượt được nền có ý nghĩa thống kê | **0/12** |
| Kỹ năng của mô hình tốt nhất so với mức xáo trộn ngẫu nhiên | **Thấp hơn** (+0.00002 so với +0.00020) |
| Chênh lệch nhỏ nhất phát hiện được với 391 kỳ | **+25.4%** tương đối (một giả thuyết) |

Kết luận không phải "chưa tìm được mô hình đủ tốt". Kết luận là **dữ liệu này
không chứa cấu trúc mà 391 kỳ đủ sức phát hiện**, và điều đó quyết định kiến
trúc tối ưu là kiến trúc nào.

Vì vậy kiến trúc tôi đề xuất ở [Phần 4](#phần-4--kiến-trúc-thuật-toán-tối-ưu)
tối ưu hóa một hàm mục tiêu khác với hàm mà người ta thường mặc định. Không
phải "cực đại hóa kỹ năng kỳ vọng" — đại lượng đó bằng 0 và không có kiến trúc
nào làm nó khác 0. Mà là ba mục tiêu đo được:

1. **Không tự lừa mình.** Không bao giờ báo cáo một phát hiện không qua nổi
   hiệu chỉnh đa kiểm định và phép kiểm lặp lại.
2. **Bắt được tín hiệu nếu nó xuất hiện.** Nếu ngày mai nguồn dữ liệu đổi và
   cấu trúc thật sự có, hệ thống phải phát hiện được — và [đã được chứng minh
   là phát hiện được](#43-bằng-chứng-hai-chiều) trên dữ liệu cấy tín hiệu.
3. **Khai báo xác suất trung thực.** Sai số hiệu chuẩn thấp quan trọng hơn
   thứ hạng đẹp.

Kiến trúc đạt cả ba, và trên dữ liệu thật nó tự động rơi về nền với trọng số
1.000000 — điểm kỹ năng đúng bằng 0, tốt hơn **mọi** mô hình đơn lẻ trong bảng
(tất cả đều âm).

---

## Phần 0 — Nền tảng thực nghiệm: ta đủ sức phát hiện cái gì?

Trước khi chọn thuật toán, phải trả lời một câu hỏi mà việc chọn thuật toán
hoàn toàn phụ thuộc vào: *với lịch sử hiện có, hiệu ứng nhỏ nhất ta đủ sức
phát hiện là bao nhiêu?* Bỏ qua bước này là cách phổ biến nhất để dành ba
tháng tinh chỉnh siêu tham số cho một đại lượng mà dữ liệu không đo nổi.

### 0.1 Phân tích công suất

Với tỉ lệ nền `p₀ = 1 − (1−0.01)²⁷ = 0.2377` và `n` kỳ, sai số chuẩn của một
ước lượng tỉ lệ là `√(p₀(1−p₀)/n)`. Chênh lệch nhỏ nhất phát hiện được ở mức ý
nghĩa `α` và công suất `1−β` là:

```
δ_min = (z_{1−α/2k} + z_{1−β}) · √(p₀(1−p₀)/n)
```

với `k` là số giả thuyết được thử (hiệu chỉnh Bonferroni).

Thay số cho 391 kỳ, `α = 0.05`, công suất 80%:

| Số giả thuyết | Chênh tuyệt đối cần có | Chênh tương đối |
|---|---|---|
| 1 (một mô hình duy nhất) | +0.0603 | **+25.4%** |
| 20 (số đặc trưng đã xây) | +0.0832 | +35.0% |
| 100 (một giả thuyết mỗi con) | +0.0930 | +39.2% |
| 412 164 (họ cầu ghép chéo ngày đã quét) | +0.1320 | **+55.6%** |

Đọc bảng này cho đúng: để một mô hình được kết luận là có tác dụng, nó phải
nâng tỉ lệ trúng từ 23.77% lên **29.8%** — và nếu ta chọn nó ra từ họ 412 164
cầu thì phải lên **37.0%**.

Không có phương pháp soi cầu nào từng được ghi nhận đạt mức đó. Nghĩa là: kể
cả khi một hiệu ứng thật tồn tại ở mức vài phần trăm, **391 kỳ không đủ để
phân biệt nó với may rủi**. Mọi kết quả dương tính trong khoảng đó sẽ là dương
tính giả.

Đây không phải lý do để bỏ cuộc; đó là lý do để thiết kế hệ thống *biết* điều
đó, thay vì một hệ thống báo cáo con số 29% với vẻ tự tin.

### 0.2 Bộ kiểm định cấu trúc

Bảy phép kiểm, mỗi phép nhắm vào một dạng cấu trúc mà một họ phương pháp soi
cầu ngầm giả định là có. Giá trị p hiệu chuẩn bằng Monte Carlo (2 000 mô phỏng)
chứ không dùng phân phối tiệm cận — với 391 kỳ, xấp xỉ tiệm cận của kiểm định
phổ lệch đáng kể, và lệch đúng chiều làm ta tin nhầm là có tín hiệu.

| Phép kiểm | Giả định của phương pháp nào | z | p | Kết luận |
|---|---|---|---|---|
| Đồng đều biên (χ²) | số nóng / số lạnh | +1.22 | 0.1114 | không bác bỏ |
| Chỉ số phân tán | cầu hai nháy | −1.26 | 0.2169 | không bác bỏ |
| **Thông tin tương hỗ trễ-1** | **bạc nhớ** | **+2.51** | **0.0095** | **bác bỏ (thô)** |
| Phân bố khoảng cách (KS rời rạc) | nhịp gan, điểm rơi | +1.08 | 0.1364 | không bác bỏ |
| Đỉnh phổ (Fisher g) | chu kỳ tuần/tháng | +0.11 | 0.3868 | không bác bỏ |
| Hiệu ứng thứ trong tuần | lịch quay | +0.04 | 0.4768 | không bác bỏ |
| Độ bền "số nóng" | nuôi số dài ngày | +0.55 | 0.6037 | không bác bỏ |

Một phép bác bỏ ở mức thô. Ba câu hỏi tiếp theo giết nó:

**Có qua hiệu chỉnh đa kiểm định không?** Ngưỡng Bonferroni cho 7 phép kiểm là
0.05/7 = 0.0071. Giá trị p = 0.0095 **không qua**. Theo Benjamini–Hochberg,
q = 0.0665 — cũng **không qua**.

**Hiệu ứng lớn cỡ nào?** Thông tin tương hỗ quan sát vượt mức rỗng đúng
0.0000679 bit mỗi cặp, tức **3.64%** trên mức ngẫu nhiên. Entropy nền là
H(0.2377) = 0.7911 bit, nên chặn trên cho mức cải thiện log-loss lấy được từ
lượng thông tin đó là:

| Giả định khai thác | Chặn trên cải thiện log-loss |
|---|---:|
| Một con dự báo cho một con mục tiêu | **0.0086%** |
| Cả 100 con dự báo, cộng dồn, bỏ qua mọi dư thừa | **0.859%** |

Dòng thứ hai là chặn hào phóng đến mức phi thực tế — nó giả định 100 dự báo
mang thông tin hoàn toàn không chồng lấn, điều chắc chắn sai. Nhưng dùng chính
con số hào phóng đó vẫn không cứu được kết luận: mô hình xích Markov, tức mô
hình *được thiết kế riêng* để khai thác đúng phụ thuộc này, đo được kỹ năng
**−0.00009** trên dữ liệu thật. Trần lý thuyết 0.859% và kết quả thực tế
−0.009% cách nhau hai bậc, và phần chênh đó chính là phương sai ước lượng.

**Có lặp lại không?** Đây là phép kiểm quyết định. Cắt đôi lịch sử và chấm lại:

```
nửa đầu:  z = +4.07
nửa sau:  z = −0.19
```

Cấu trúc thật thì lặp lại. Nhiễu được khớp quá mức thì không. Kết quả này là
dạng thứ hai.

> **Ghi chú kỹ thuật.** Phép kiểm khoảng cách ban đầu dùng `scipy.stats.kstest`
> và cho `p = 1.0` với độ lệch chuẩn rỗng đúng bằng 0 — dấu hiệu của một thống
> kê hằng số. Nguyên nhân: `kstest` giả định biến liên tục nên so hàm phân phối
> lý thuyết với hàm kinh nghiệm *ngay trước* mỗi điểm dữ liệu. Khoảng cách nhỏ
> nhất luôn bằng 1, nên số hạng `F(1) − 0 = p` luôn có mặt và át mọi sai lệch
> thật khi phần khớp còn lại tốt. Đã thay bằng so sánh tại chính các điểm giá
> đỡ. Kết luận không đổi.

---

## Phần 1 — Các họ thuật toán

Mỗi mục dưới đây gồm: cơ sở toán học, lý do nó *có thể* cải thiện xác suất
phỏng đoán, ưu/nhược điểm, độ phức tạp tính toán, mã minh họa, và **kết quả đo
được trên 391 kỳ thật**.

Ký hiệu chung: `n` = số kỳ (391), `N` = 100 con, `d` = số đặc trưng,
`m` = số ngày đánh giá (271).

### Bảng tổng hợp kết quả đo

Giao thức: cuốn chiếu, khởi động 120 kỳ, đánh giá 271 kỳ, mỗi kỳ 100 quan sát
Bernoulli. Kiểm định t ghép cặp ở **mức ngày** (xem [§2.3](#23-kiểm-định-ghép-cặp-ở-mức-ngày)).

| Mô hình | Họ | Kỹ năng log-loss | t ghép cặp | Trúng@27 | Lệch hiệu chuẩn | Vượt nền |
|---|---|---:|---:|---:|---:|:---:|
| Nền đồng đều | nền | 0.00000 | +0.00 | 6.22 | 0.0006 | — |
| Tần suất kinh nghiệm | tần suất | −0.00329 | −3.83 | **6.67** | 0.0213 | ✗ |
| Co rút Beta–Nhị thức | Bayes | −0.00001 | −0.10 | 6.64 | 0.0098 | ✗ |
| Xích Markov bậc 1 (gộp) | Markov | −0.00009 | −0.59 | 6.46 | 0.0077 | ✗ |
| Xích Markov bậc 2 (gộp) | Markov | +0.00002 | +0.03 | 6.59 | 0.0063 | ✗ |
| Xích Markov bậc 1 (riêng từng con) | Markov | −0.00705 | −6.12 | 6.58 | 0.0312 | ✗ |
| Nguy cơ theo độ gan | sống sót | −0.00037 | −1.67 | 6.21 | 0.0090 | ✗ |
| HMM hai chế độ | không gian trạng thái | −0.0000004 | −0.46 | 6.22 | 0.0022 | ✗ |
| Phân cụm k-means (k=4) | phân cụm | −0.00063 | −1.22 | 6.63 | 0.0101 | ✗ |
| Cây tăng cường gradient | học có giám sát | −0.00087 | −3.74 | 6.29 | 0.0115 | ✗ |
| Mạng nơ-ron dung lượng cao | học sâu | −0.00168 | −3.75 | 6.58 | 0.0158 | ✗ |
| **Kết hợp co rút (đề xuất)** | **kiến trúc** | **0.00000** | **+0.00** | 6.22 | **0.0006** | — |

Ba điều đáng đọc kỹ trong bảng này:

**Thứ nhất — mọi mô hình đều âm, và mức âm tỉ lệ với số tham số.** Xếp theo
dung lượng: HMM (2 tham số, −0.0000004) → Beta–Nhị thức (2, −0.00001) → Markov
gộp (2–4, −0.00009) → phân cụm (4, −0.00063) → tăng cường gradient (~360 nút,
−0.00087) → mạng nơ-ron (4 801 tham số, −0.00168) → tần suất (100, −0.00329)
→ Markov riêng từng con (200, −0.00705). Đây không phải trùng hợp: khi tín hiệu
bằng 0, mỗi tham số thêm vào chỉ đóng góp phương sai. Đường cong này *chính là*
thang phương sai, đo trực tiếp.

**Thứ hai — trúng@27 đi ngược với kỹ năng.** Mô hình tần suất có trúng@27 cao
nhất bảng (6.67 so với 6.22 của nền) *và* kỹ năng tệ thứ hai. Nếu chọn mô hình
bằng "tỉ lệ trúng", ta sẽ chọn đúng mô hình tệ nhất. Đây là lý do
[Phần 3](#phần-3--chỉ-số-đánh-giá) tồn tại.

**Thứ ba — đối chứng xáo trộn.** Mô hình duy nhất có kỹ năng dương (Markov bậc
2, +0.00002) được chấm lại trên 12 phiên bản dữ liệu bị xáo trộn chu kỳ. Trung
bình kỹ năng khi xáo trộn là −0.00037, cao nhất **+0.00020** — gấp mười lần con
số "thật". Kỹ năng quan sát được nằm gọn trong phân phối mà việc xáo trộn tạo
ra, nên nó không phải bằng chứng của bất cứ điều gì.

---

### 1.1 Nền miền — thứ mọi mô hình phải vượt qua

**Cơ sở toán học.** Nếu 27 giải là 27 lần rút độc lập, đều trên 00–99, *có hoàn
lại*, thì xác suất một con bất kỳ về ít nhất một lần là

```
p₀ = 1 − (1 − 1/100)²⁷ = 0.23765728…
```

Đây không phải "mô hình ngây thơ" mà là **giả thuyết rỗng đúng của miền**. Điểm
kỹ năng của mọi mô hình khác đều đo tương đối với nó:

```
skill = (loss_nền − loss_mô_hình) / loss_nền
```

**Vì sao phải nói rõ.** Rất nhiều báo cáo soi cầu so với nền sai — thường là
1/100 cho mỗi con, tức bỏ qua việc có 27 giải. So với nền sai đó thì *mọi* mô
hình đều "thắng" ngoạn mục mà không cần biết gì.

Trong kho này, `LOTO_BASELINE_RATE` được định nghĩa một lần duy nhất tại
`src/xsmb_domain.py`. Module benchmark nhập lại chứ không tính lại — hai bản
sao của một hằng số rồi sẽ lệch nhau.

```python
from xsmb_domain import LOTO_BASELINE_RATE

class UniformBaseline:
    def predict_next(self, history):
        return np.full(100, LOTO_BASELINE_RATE)
```

**Độ phức tạp.** `O(N)` mỗi ngày. Không có gì để khớp.

---

### 1.2 Suy luận Bayes — co rút Beta–Nhị thức

**Cơ sở toán học.** Đặt tiên nghiệm `pₙ ~ Beta(a, b)` cho tỉ lệ về của con `n`.
Với `kₙ` lần về trong `m` kỳ, hậu nghiệm là `Beta(a + kₙ, b + m − kₙ)`, trung
bình hậu nghiệm:

```
p̂ₙ = (a + kₙ) / (a + b + m)
```

— tức trung bình có trọng số giữa tần suất riêng của con và trung bình chung,
với trọng số quyết định bởi `a + b`.

`a` và `b` ước lượng bằng phương pháp mô-men trên chính lịch sử đã thấy, nên
không có siêu tham số nào phải chỉnh tay:

```
Var_quan_sát = Var_lấy_mẫu + Var_tín_hiệu,   Var_lấy_mẫu = p̄(1−p̄)/m
a + b = p̄(1−p̄)/Var_tín_hiệu − 1
```

**Vì sao có thể cải thiện.** Ước lượng riêng từng con có phương sai `p(1−p)/m`;
co rút về trung bình chung đánh đổi một chút chệch lấy mức giảm phương sai lớn
hơn nhiều. Đây chính là hiệu ứng Stein — với `N ≥ 3` tham số cần ước lượng
đồng thời, ước lượng co rút *chắc chắn* có sai số bình phương kỳ vọng nhỏ hơn
ước lượng riêng lẻ.

**Ưu điểm.** Có tính chất tự bảo vệ mạnh nhất trong toàn bộ danh sách: nếu các
con thật sự đồng nhất thì `Var_tín_hiệu ≤ 0`, `a+b → ∞`, và mô hình **tự động
thoái hóa về nền**. Nó không thể tệ hơn nền nhiều — và đo được đúng như vậy
(−0.00001, gần 0 nhất trong các mô hình có tham số).

**Nhược điểm.** Chỉ mô hình hóa tần suất biên. Không nhìn thứ tự thời gian,
nên không thể phát hiện bạc nhớ dù nó có tồn tại.

**Độ phức tạp.** `O(nN)` để khớp, `O(N)` để dự đoán. Vài mili-giây.

```python
class BetaBinomialShrinkage:
    def predict_next(self, history):
        hits = (history > 0).astype(float)
        m = hits.shape[0]
        rates = hits.mean(axis=0)
        grand = float(rates.mean())
        sampling_var = grand * (1 - grand) / m
        signal_var = float(rates.var(ddof=1)) - sampling_var
        if signal_var <= 0:                     # không có bằng chứng khác biệt
            return np.full(100, grand)          # → co rút hoàn toàn
        strength = max(grand * (1 - grand) / signal_var - 1.0, 0.0)
        a, b = grand * strength, (1 - grand) * strength
        return (a + hits.sum(axis=0)) / (a + b + m)
```

**Kết quả đo.** Kỹ năng −0.00001, t = −0.10. Trên dữ liệu thật, `signal_var`
âm ở gần như mọi cửa sổ, tức mô hình co rút hoàn toàn — **kết luận Bayes là
các con không phân biệt được với nhau**.

---

### 1.3 Xích Markov — hình thức hóa của "bạc nhớ"

**Cơ sở toán học.** Mô hình hóa `P(hitₜ | hitₜ₋₁)` bằng ma trận chuyển 2×2. Ước
lượng hợp lý cực đại là tỉ lệ đếm chuyển, cộng giả đếm Laplace để hậu nghiệm
xác định khi một ô trống. Bậc `k` cần `2ᵏ` trạng thái.

**Vì sao có thể cải thiện.** Đây *đúng là* giả thuyết mà phương pháp bạc nhớ
đưa ra. Nếu đúng, hai hàng của ma trận chuyển phải khác nhau rõ rệt.

**Ưu điểm.** Trực tiếp kiểm được giả thuyết miền quan trọng nhất. Rẻ. Diễn
giải được — ma trận chuyển đọc thẳng ra thành câu tiếng Việt.

**Nhược điểm.** Số tham số nhân đôi mỗi bậc, trong khi số quan sát mỗi trạng
thái giảm một nửa. Đó là lý do bậc cao gần như luôn thua trên chuỗi ngắn.

**Độ phức tạp.** Gộp: `O(nN)` khớp, `O(N)` dự đoán. Riêng từng con: `O(nN)`
khớp nhưng chia dữ liệu ra `N` lần — mỗi con chỉ còn ~391 quan sát cho 2ᵏ ô.

```python
class MarkovChain:
    def predict_next(self, history):
        hits = (history > 0).astype(np.int64)
        k = self.order
        windows = np.stack([hits[i:hits.shape[0] - k + i] for i in range(k)])
        states = (windows * (2 ** np.arange(k))[:, None, None]).sum(axis=0)
        outcomes = hits[k:]
        successes = np.bincount(states.ravel(), weights=outcomes.ravel(),
                                minlength=2 ** k)
        totals = np.bincount(states.ravel(), minlength=2 ** k)
        table = (successes + 1.0) / (totals + 2.0)      # làm trơn Laplace
        current = (hits[-k:] * (2 ** np.arange(k))[:, None]).sum(axis=0)
        return table[current]
```

**Kết quả đo.** Ba biến thể, và chúng kể đúng câu chuyện dự đoán được từ lý
thuyết:

| Biến thể | Tham số | Kỹ năng |
|---|---:|---:|
| Bậc 1, gộp | 2 | −0.00009 |
| Bậc 2, gộp | 4 | +0.00002 |
| Bậc 1, riêng từng con | 200 | **−0.00705** |

Bản riêng từng con — bản *linh hoạt nhất*, bản mà trực giác nói là "cá nhân hóa
cho từng con" — tệ hơn bản gộp **78 lần**. Đó là chi phí của việc chia 391 quan
sát cho 200 tham số.

---

### 1.4 Mô hình Poisson và mô hình đếm

**Cơ sở toán học.** Số lần con `n` xuất hiện trong 27 giải tuân theo
`Binomial(27, 1/100)`, xấp xỉ tốt bằng `Poisson(λ = 0.27)`. Số kỳ giữa hai lần
về tuân theo phân phối hình học với `p₀ = 0.2377`.

**Vì sao quan trọng — nhưng không phải như một mô hình dự đoán.** Poisson đóng
vai trò lớn hơn nhiều trong hệ thống này ở chỗ khác: **tính giá trị p đúng
trong miền hiếm**. Khi quét 412 164 cầu, xấp xỉ chuẩn cho đuôi phân phối sai
nghiêm trọng ở tỉ lệ 1% (đề đặc biệt). Trước khi sửa, 69 cầu đề "sống sót" qua
cổng BH-FDR. Sau khi thay bằng đuôi Poisson chính xác: **0**.

```python
from scipy import stats

def tail_probability(successes, expected, variance, day_rate,
                     rare_threshold=0.1):
    """Xác suất đuôi phải, chọn xấp xỉ theo chế độ.

    Xấp xỉ chuẩn với hiệu chỉnh liên tục hỏng khi tỉ lệ nhỏ: phân phối nhị
    thức lệch mạnh, và xấp xỉ sai *về phía đánh giá thấp* xác suất đuôi —
    đúng chiều biến nhiễu thành phát hiện.
    """
    if float(np.max(day_rate)) <= rare_threshold:
        return stats.poisson.sf(successes - 1, expected)
    z = (successes - 0.5 - expected) / np.sqrt(variance)
    return stats.norm.sf(z)
```

**Ưu điểm.** Chính xác trong chế độ hiếm, rẻ, có dạng đóng.

**Nhược điểm.** Là mô hình cho *phân phối biên*, không mang khả năng dự đoán
thời gian nào.

**Độ phức tạp.** `O(1)` mỗi phép tính đuôi.

**Kết quả đo.** Khi dùng làm mô hình dự đoán, Poisson thoái hóa về đúng nền
(§1.1) vì `λ` ước lượng được không khác `0.27` một cách có ý nghĩa. Giá trị
thật của nó nằm ở cổng thống kê, không ở tầng dự đoán.

---

### 1.5 Mô hình sống sót — nguy cơ theo độ gan

**Cơ sở toán học.** Hàm nguy cơ `h(g) = P(về hôm nay | đã gan g ngày)`. Với
chuỗi độc lập, `h` là **hằng số** — đó là tính không nhớ của phân phối hình
học. Mọi phương pháp "nuôi khung", "điểm rơi", "nhịp gan" đều ngầm khẳng định
`h` tăng theo `g`.

**Vì sao có thể cải thiện.** Nếu `h` thật sự dốc lên, thì biết độ gan hiện tại
của một con cho ta thông tin mà nền không có. Đây là giả thuyết kiểm được trực
tiếp, và nó là giả thuyết đứng sau phần lớn các phương pháp phổ biến nhất.

**Ưu điểm.** Ước lượng phi tham số (bảng sống), không áp đặt dạng hàm. Diễn
giải cực tốt: vẽ `h(g)` ra là thấy ngay có dốc hay không.

**Nhược điểm.** Số quan sát ở mức gan lớn rất thưa — phải nhóm đuôi lại, nếu
không các mức gan hiếm cho ước lượng 0 hoặc 1 và log-loss nổ.

**Độ phức tạp.** `O(nN)` khớp bằng một lượt quét, `O(N)` dự đoán.

```python
class GapHazard:
    def predict_next(self, history):
        hits = history > 0
        successes = np.zeros(self.max_gap + 1)
        totals = np.zeros(self.max_gap + 1)
        gaps = np.zeros(100, dtype=np.int64)
        for day in range(hits.shape[0]):
            bucket = np.minimum(gaps, self.max_gap)
            np.add.at(totals, bucket, 1)
            np.add.at(successes, bucket, hits[day].astype(float))
            gaps = np.where(hits[day], 0, gaps + 1)
        # Co rút về nền theo cỡ mẫu từng ô gan.
        hazard = (successes + self.prior * BASELINE_RATE) / (totals + self.prior)
        return hazard[self._current_gaps(hits)]
```

**Kết quả đo.** Kỹ năng −0.00037, t = −1.67. Hàm nguy cơ ước lượng được trên
391 kỳ:

| Độ gan | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12+ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| h(g) | .2421 | .2397 | .2418 | .2332 | .2449 | .2268 | .2345 | .2224 | .2090 | .2401 |
| sai số | ±.0044 | ±.0051 | ±.0058 | ±.0066 | ±.0077 | ±.0086 | ±.0100 | ±.0128 | ±.0163 | ±.0109 |

Biên độ giữa mức cao nhất và thấp nhất là 0.0359, gấp 3.5 lần sai số chuẩn
trung bình (0.0104) — nhìn qua thì tưởng có cấu trúc. **Nhưng so biên độ của 13
điểm với sai số chuẩn của một điểm chính là lỗi đa kiểm định mà cả tài liệu này
nói về.** Biên độ của 13 biến ngẫu nhiên tự nhiên lớn hơn độ lệch của từng biến.

Mô phỏng 20 000 lần dưới giả thuyết `h(g)` phẳng, dùng đúng cỡ mẫu thật của
từng ô gan:

```
biên độ kỳ vọng khi hoàn toàn phẳng = 0.0399   (3.84 lần sai số chuẩn trung bình)
biên độ quan sát                    = 0.0359
                                p   = 0.5869
```

Biên độ quan sát **thấp hơn** mức mà tính phẳng dự đoán. Kiểm định χ² cho cùng
giả thuyết đồng ý:

```
χ² = 9.08,  df = 12,  p = 0.6963
```

Không có dấu hiệu nào của độ dốc. Đây là bằng chứng trực tiếp bác bỏ phương
pháp nuôi khung theo nhịp gan, và nó khớp với kết quả phép kiểm KS ở §0.2
(p = 0.1364).

Đáng chú ý là `h(0) = 0.2421`: con vừa về hôm qua có xác suất về lại **cao
hơn** một chút, chứ không thấp hơn — ngược hoàn toàn với giả định "vừa ra thì
nghỉ". Chênh lệch này (+0.0044 so với nền, đúng bằng một sai số chuẩn) không có
ý nghĩa thống kê, nhưng nó cùng dấu với phép kiểm thông tin tương hỗ ở §0.2, và
đó là lý do phép kiểm ấy là phép duy nhất dương tính.

---

### 1.6 Mô hình Markov ẩn (HMM)

**Cơ sở toán học.** Giả định tồn tại chuỗi trạng thái ẩn `zₜ ∈ {0,1}` theo xích
Markov, và quan sát `yₜ` (số con phân biệt trong kỳ) sinh từ `N(μ_{zₜ}, σ²_{zₜ})`.
Ước lượng bằng Baum–Welch (EM): bước E chạy tiến–lùi để lấy
`γₜ(i) = P(zₜ = i | y)`, bước M cập nhật tham số theo trung bình có trọng số `γ`.

**Vì sao có thể cải thiện.** Nếu tồn tại "kỳ nở" và "kỳ co" thì số con phân
biệt trong kỳ sẽ có hai chế độ, và biết đang ở chế độ nào cho phép điều chỉnh
mức xác suất chung lên hoặc xuống.

**Ưu điểm.** Bắt được cấu trúc chế độ mà mô hình không trạng thái bỏ sót. Chỉ
2 trạng thái nên rất ít tham số — và điều đó thể hiện rõ trong kết quả: kỹ năng
−0.0000004, con số **gần 0 nhất** trong toàn bảng.

**Nhược điểm.** EM chỉ đảm bảo cực trị địa phương. Cần chuẩn hóa thang log, nếu
không tích của 391 mật độ nhỏ hơn 1 sẽ về 0 trong dấu phẩy động. Không có
`hmmlearn` trong môi trường này nên phải cài bằng NumPy thuần.

**Độ phức tạp.** `O(n·K²·I)` với `K` = 2 trạng thái, `I` = 30 vòng lặp EM. Với
n = 391 thì khoảng 47 000 phép — vài chục mili-giây.

```python
def forward_backward(log_emission, log_transition, log_start):
    """Tiến–lùi trên thang log. Chuẩn hóa log là bắt buộc, không phải tối ưu:
    tích 391 mật độ < 1 sẽ tràn số dưới về 0 nếu nhân trực tiếp."""
    n, k = log_emission.shape
    log_alpha = np.empty((n, k))
    log_alpha[0] = log_start + log_emission[0]
    for t in range(1, n):
        log_alpha[t] = log_emission[t] + logsumexp(
            log_alpha[t - 1][:, None] + log_transition, axis=0)
    log_beta = np.zeros((n, k))
    for t in range(n - 2, -1, -1):
        log_beta[t] = logsumexp(
            log_transition + log_emission[t + 1] + log_beta[t + 1], axis=1)
    log_gamma = log_alpha + log_beta
    log_gamma -= logsumexp(log_gamma, axis=1, keepdims=True)
    return np.exp(log_gamma)
```

**Kết quả đo.** Kỹ năng −0.0000004, t = −0.46. Hai trạng thái ước lượng được có
`μ` gần như trùng nhau, tức EM **không tìm thấy hai chế độ phân biệt được**.
Mô hình thoái hóa về một trạng thái, và đó là lý do nó gần nền đến vậy.

---

### 1.7 Phân cụm

**Cơ sở toán học.** Nếu các con không đồng nhất nhưng chia thành vài nhóm hành
vi, thì ước lượng ở mức nhóm có phương sai thấp hơn nhiều so với mức từng con
trong khi vẫn giữ được phần khác biệt. Hồ sơ gồm tỉ lệ về, độ gan trung bình,
tỉ lệ ra hai nháy; phân cụm bằng k-means.

**Vì sao có thể cải thiện.** Đây là **co rút có cấu trúc** — nằm giữa "mọi con
như nhau" và "mỗi con một tham số". Nếu bác bỏ được tính đồng nhất thì nó phải
thắng cả hai đầu.

**Ưu điểm.** Giảm mạnh số tham số hiệu dụng so với mô hình từng con.

**Nhược điểm.** `k` là siêu tham số phải chọn, và chọn `k` bằng cách nhìn kết
quả đánh giá là một dạng rò rỉ. K-means giả định cụm hình cầu trong không gian
đã chuẩn hóa — giả định này không được kiểm chứng ở đây.

**Độ phức tạp.** `O(nN)` để xây hồ sơ + `O(N·k·I·d)` cho k-means. Không đáng kể.

**Kết quả đo.** Kỹ năng −0.00063, t = −1.22.

Trên toàn bộ lịch sử, bốn cụm tìm được có tỉ lệ về khác nhau rất rõ: 0.2085,
0.2380, 0.2409, 0.2747 — cách nhau hơn mười lần sai số chuẩn danh nghĩa. Nếu
dừng ở đây, ta sẽ kết luận đã tìm được bốn nhóm con có hành vi khác biệt.

Đó là suy luận sai, và sai theo một cách rất dễ mắc: **k-means được khớp trên
chính tỉ lệ về**, nên các cụm được *định nghĩa* để tách nhau theo tỉ lệ. Sai số
chuẩn tính như trên giả định cụm đã cho trước, trong khi nó được chọn ra để cực
đại hóa đúng sự tách biệt đang được kiểm. Đây là suy luận sau chọn lọc
(post-selection inference), và nó luôn cho kết quả "có ý nghĩa".

Phép kiểm đúng: phân cụm trên nửa đầu lịch sử, rồi đo tỉ lệ của **chính các cụm
đó** ở nửa sau.

| Cụm | Số con | Nửa đầu (nơi phân cụm) | Nửa sau (ngoài mẫu) |
|---|---:|---:|---:|
| 0 | 26 | 0.2146 | 0.2369 |
| 1 | 25 | 0.2806 | 0.2394 |
| 2 | 12 | 0.1825 | 0.2364 |
| 3 | 37 | 0.2456 | 0.2375 |
| **Biên độ** | | **0.0981** | **0.0030** |

Biên độ giữa các cụm co từ 0.0981 xuống 0.0030 — còn **3%**. Cả bốn cụm đều rơi
về xấp xỉ 0.237, tức đúng nền. Cấu trúc cụm hoàn toàn là sản phẩm của việc khớp;
không một phần nào của nó tồn tại ngoài mẫu.

Đây là ví dụ gọn nhất trong toàn bộ báo cáo về vì sao [§2.1](#21-cuốn-chiếu-không-phải-chia-ngẫu-nhiên)
là bắt buộc: cùng một phương pháp, cùng một dữ liệu, kết luận đảo ngược hoàn
toàn tùy theo có đánh giá ngoài mẫu hay không.

---

### 1.8 Cây tăng cường gradient (XGBoost / LightGBM / CatBoost)

**Cơ sở toán học.** Xây tổng các cây hồi quy theo hướng gradient âm của hàm
mất mát: `F_m(x) = F_{m−1}(x) + ν·h_m(x)`, với `h_m` khớp gradient của log-loss
và `ν` là tốc độ học. Chính quy hóa L2 trên giá trị lá.

**Vì sao có thể cải thiện.** Bắt được tương tác phi tuyến giữa đặc trưng mà mô
hình tuyến tính bỏ sót — ví dụ "con này gan lâu **và** con bóng của nó vừa về".
Đây là họ mô hình mạnh nhất trên dữ liệu bảng có tín hiệu thật.

**Ưu điểm.** Không cần chuẩn hóa đặc trưng, xử lý tương tác tự động, có SHAP để
giải thích. Là lựa chọn đúng *nếu* có tín hiệu.

**Nhược điểm — và đây là điểm mấu chốt.** Chính khả năng khớp tương tác phi
tuyến làm nó nguy hiểm nhất khi không có tín hiệu: nó sẽ tìm ra tương tác trong
nhiễu, và tìm rất giỏi. Không có cách nào phân biệt bằng cách nhìn mô hình; chỉ
có đánh giá ngoài mẫu mới phân biệt được.

**Độ phức tạp.** `O(m·d·log m·B)` mỗi lần khớp với `B` = 120 cây. Ở đây
m ≈ 24 000 hàng × d = 8 → khoảng 1.5 giây mỗi lần khớp, khớp lại mỗi 14 ngày →
~30 giây cho toàn bộ đánh giá cuốn chiếu.

`HistGradientBoostingClassifier` dùng cùng thuật toán lược đồ như LightGBM;
trên vài chục nghìn hàng, chênh lệch giữa các cài đặt là nhiễu so với chênh
lệch giữa mô hình và nền — nên việc thiếu XGBoost/CatBoost trong môi trường
không ảnh hưởng đến kết luận.

```python
def build_features(history, day):
    """Đặc trưng cho từng con tại ``day``. Bất biến duy nhất thực sự quan
    trọng: mọi cột là hàm của ``history[:day]``, không cột nào chạm
    ``history[day]``. Kiểm thử khẳng định điều này bằng cách sửa
    ``history[day]`` rồi so mảng đặc trưng phải không đổi."""
    past = history[:day] > 0
    columns = [past[-w:].mean(axis=0) for w in (10, 30, 90)]
    last = np.where(past.any(axis=0),
                    past.shape[0] - 1 - np.argmax(past[::-1], axis=0), -1)
    columns.append(np.minimum(past.shape[0] - 1 - last, 30) / 30.0)  # độ gan
    columns.append(past[-1].astype(float))                            # hôm qua
    columns.append(past[-2].astype(float))                            # hôm kia
    columns.append((history[:day][-30:] >= 2).mean(axis=0))           # hai nháy
    columns.append(np.array([(n // 10 + n % 10) / 18.0 for n in range(100)]))
    return np.stack(columns, axis=1)
```

**Kết quả đo.** Kỹ năng −0.00087, t = −3.74. Âm **có ý nghĩa thống kê** — tức
mô hình không chỉ vô dụng mà chủ động tệ hơn nền, và ta đủ dữ liệu để khẳng
định điều đó. Kết quả này nhất quán với vòng đánh giá đặc trưng trước đó trong
kho: 0/20 đặc trưng vượt nền, t tốt nhất là +1.47.

---

### 1.9 Mạng nơ-ron hồi tiếp (LSTM / GRU)

**Cơ sở toán học.** GRU cập nhật trạng thái ẩn qua hai cổng:

```
zₜ = σ(W_z·[hₜ₋₁, xₜ]),  rₜ = σ(W_r·[hₜ₋₁, xₜ])
h̃ₜ = tanh(W·[rₜ⊙hₜ₋₁, xₜ]),  hₜ = (1−zₜ)⊙hₜ₋₁ + zₜ⊙h̃ₜ
```

Cổng cho phép giữ thông tin qua nhiều bước thời gian, giải quyết vấn đề gradient
tiêu biến của RNN thuần.

**Vì sao có thể cải thiện.** Trên nguyên tắc, học được phụ thuộc thời gian dài
hạn tùy ý mà không cần đặc tả trước dạng của nó.

**Nhược điểm — quyết định.** Một GRU 64 chiều với đầu vào 100 chiều có
`3 × (64 × 164 + 2 × 64) + 64 × 100 + 100 = 38 372` tham số — ba cổng nhân
(trọng số vào + trọng số hồi tiếp + hai véc-tơ chệch), cộng lớp đầu ra. Dữ
liệu có `391 × 100 = 39 100` quan
sát nhị phân, và theo §0.2 chúng không phân biệt được với độc lập. Tỉ lệ tham
số trên quan sát xấp xỉ **1:1.02** — gần đúng một tham số cho mỗi quan sát. Ở
tỉ lệ đó mạng ghi nhớ tập huấn luyện chứ
không học quy luật, và không có phương pháp chính quy hóa nào cứu được — vấn đề
không phải chọn siêu tham số mà là **lượng thông tin trong dữ liệu**.

**Độ phức tạp.** `O(n·H·(H+F))` mỗi epoch với `H` = 64, `F` = 100. Cần GPU để
huấn luyện thoải mái; không có PyTorch trong môi trường này.

**Kết quả đo — đo bằng thứ có sẵn.** PyTorch không có, nhưng điều cần chứng
minh không phụ thuộc vào kiến trúc hồi tiếp: đó là chuyện gì xảy ra khi số tham
số vượt xa lượng thông tin. Mạng MLP hai lớp 64 nút (4 801 tham số, tức chỉ
bằng **12.5%** dung lượng của GRU nói trên) đạt kỹ năng **−0.00168, t = −3.75** —
tệ hơn cây tăng cường gần gấp đôi, và xếp thứ ba từ dưới lên trong bảng.

Đây là điểm quan trọng cần nói thẳng: **kết quả này không phải bằng chứng trực
tiếp rằng GRU sẽ thất bại**; nó là bằng chứng rằng thang phương sai theo dung
lượng — vốn đã hiện rõ qua tám mô hình khác — tiếp tục đúng ở dải dung lượng
cao. Với số tham số của GRU cao hơn MLP này 8.0 lần, dự đoán
hợp lý là nó nằm xa hơn nữa về phía âm. Muốn kết luận chắc chắn thì phải cài
PyTorch và đo.

---

### 1.10 Monte Carlo

**Cơ sở toán học.** Xấp xỉ phân phối của một thống kê bằng cách sinh nhiều mẫu
từ giả thuyết rỗng và đếm tần suất. Giá trị p ước lượng bằng
`(số lần cực trị + 1) / (số mô phỏng + 1)`.

**Vì sao `+1` ở cả tử và mẫu.** Cho ước lượng không chệch và **không bao giờ
trả về p = 0**. Một giá trị p bằng 0 là lời khẳng định mạnh hơn mức số lần mô
phỏng cho phép — với 2 000 mô phỏng, điều mạnh nhất có thể nói là `p < 1/2001`.

**Vì sao quan trọng ở đây.** Monte Carlo không phải mô hình dự đoán; nó là công
cụ **suy luận**, và trong bài toán này nó là công cụ quan trọng nhất trong toàn
bộ danh sách. Toàn bộ Phần 0 dựa trên nó, vì với 391 kỳ, xấp xỉ tiệm cận của
kiểm định phổ và kiểm định chuỗi lệch đáng kể theo hướng làm ta tin nhầm.

**Ưu điểm.** Đúng theo định nghĩa, không cần giả định phân phối. Áp dụng được
cho *bất kỳ* thống kê nào, kể cả thống kê không có dạng đóng.

**Nhược điểm.** Chỉ tốn thời gian. Độ phân giải của p bị chặn bởi số mô phỏng.

**Độ phức tạp.** `O(S · C)` với `S` mô phỏng và `C` là chi phí thống kê. Bộ 7
phép kiểm × 2 000 mô phỏng chạy trong **17 giây**.

```python
def monte_carlo_test(statistic_of, observed_counts, simulations=2000, seed=0):
    observed = float(statistic_of(observed_counts))
    rng = np.random.default_rng(seed)
    null = np.array([statistic_of(simulate_draws(observed_counts.shape[0], rng))
                     for _ in range(simulations)])
    extreme = int(np.sum(null >= observed))
    return (extreme + 1) / (simulations + 1)     # không bao giờ trả về 0
```

---

### 1.11 Thuật toán di truyền

**Cơ sở toán học.** Tìm kiếm tiến hóa trên không gian cấu hình: quần thể lời
giải, chọn lọc theo độ thích nghi, lai ghép, đột biến, lặp qua nhiều thế hệ.

**Vì sao nó là mục nguy hiểm nhất trong danh sách này.** Thuật toán di truyền
không phải mô hình mà là **bộ tối ưu hóa**, và nó tối ưu hóa rất giỏi. Trong
bài toán này, "độ thích nghi" chỉ có thể là điểm trên dữ liệu lịch sử — nên GA
sẽ tìm ra cấu hình cầu đạt điểm cao nhất trong không gian tìm kiếm, kể cả khi
mọi cấu hình đều vô giá trị. Kết quả trông y hệt một phát hiện thật.

Kho này đã đo trực tiếp hiện tượng đó, không phải bằng GA mà bằng quét vét cạn
— tương đương một GA hội tụ hoàn hảo:

```
412 164 giả thuyết cầu × 3 loại mục tiêu → 0 cầu sống sót sau BH-FDR
Cầu thật tốt nhất:              kỹ năng +0.1085
Cầu tốt nhất trên dữ liệu xáo trộn: kỹ năng +0.1015
```

Chênh lệch giữa "cầu tốt nhất tìm được trên dữ liệu thật" và "cầu tốt nhất tìm
được trên dữ liệu đã bị phá hủy tín hiệu" là **6.9%** — nằm gọn trong dao động
của chính phép xáo trộn. Toàn bộ +0.1085 đó là sản phẩm của việc tìm kiếm, và
[§0.1](#01-phân-tích-công-suất) đã nói trước điều này: trên họ 412 164 giả
thuyết, ngưỡng phát hiện là +55.6%.

**Nếu vẫn muốn dùng GA**, bắt buộc phải có hai thứ, không có ngoại lệ:

1. **Độ thích nghi phải đo ngoài mẫu**, trên dữ liệu mà quá trình tiến hóa chưa
   từng chạm tới — không phải tập kiểm tra được dùng lại qua các thế hệ, vì
   dùng lại chính là rò rỉ.
2. **Phải trừ đi mức sàn của tìm kiếm**: chạy đúng GA đó trên dữ liệu xáo trộn
   với cùng số thế hệ, lấy phân phối độ thích nghi tốt nhất làm phân phối rỗng.
   Chỉ phần vượt lên trên phân phối đó mới là tín hiệu.

**Độ phức tạp.** `O(G · P · C)` với `G` thế hệ, `P` cỡ quần thể, `C` chi phí
đánh giá độ thích nghi. Nhân đôi nếu làm đúng phép đối chứng xáo trộn — và phép
đối chứng đó không phải tùy chọn.

---

## Phần 2 — Phương pháp backtesting

Một mô hình sai có thể trông tốt vì bốn lý do, và mỗi lý do cần một biện pháp
riêng. Bốn mục dưới đây là bốn biện pháp đó.

### 2.1 Cuốn chiếu, không phải chia ngẫu nhiên

`train_test_split` ngẫu nhiên là sai trên chuỗi thời gian: nó cho mô hình thấy
ngày mai để dự đoán hôm nay. Cả `KFold` cũng vậy.

Giao thức đúng: với mỗi ngày `t ≥ warmup`, mô hình chỉ thấy `counts[:t]` và
khai báo xác suất cho ngày `t`. Không có ngoại lệ — kể cả cho việc chuẩn hóa,
chọn siêu tham số, hay ước lượng tiên nghiệm. Vì vậy trong kiến trúc này *mọi*
bước đó đều nằm bên trong `predict_next`.

```python
def walk_forward(counts, model, warmup=120):
    for day in range(warmup, counts.shape[0]):
        probabilities = model.predict_next(counts[:day])   # chỉ quá khứ
        outcome = (counts[day] > 0).astype(float)
        ...
```

**Cách kiểm chứng rằng không rò rỉ** — và đây là phần thường bị bỏ qua. Không
đủ nếu chỉ đọc code cho kỹ; phải có phép kiểm tự động khẳng định bất biến:

```python
def test_features_ignore_the_day_being_predicted():
    """Sửa chính ngày đang dự đoán; mảng đặc trưng phải không đổi."""
    before = build_features(counts, 100)
    tampered = counts.copy()
    tampered[100] = 0
    tampered[100, :27] = 1
    assert np.array_equal(before, build_features(tampered, 100))
```

Phép kiểm này chạy cho **mọi** mô hình trong kho qua `pytest.mark.parametrize`.

### 2.2 Đối chứng dương cho chính thước đo

Một bộ đánh giá luôn báo "không vượt nền" là vô dụng — không phân biệt được
"không có tín hiệu" với "thước đo hỏng". Vì vậy bộ đánh giá phải được kiểm bằng
một mô hình *biết trước đáp án*:

```python
def test_a_model_that_knows_the_answer_scores_high():
    """Nếu kẻ gian lận không được điểm cao thì thước đo hỏng, và mọi kết quả
    âm tính phía sau đều vô nghĩa."""
    class Oracle:
        def predict_next(self, history):
            outcome = (counts[history.shape[0]] > 0).astype(float)
            return np.where(outcome > 0, 0.95, 0.05)
    result = walk_forward(counts, Oracle(), warmup=120)
    assert result.logloss_skill > 0.5 and result.paired_t > 10.0
```

Cùng nguyên tắc ở mức mô hình: cấy tín hiệu bạc nhớ vào chuỗi ngẫu nhiên và
khẳng định xích Markov **phải** bắt được nó. Nếu không bắt được thì kết luận
"không có bạc nhớ" trên dữ liệu thật không có giá trị.

Xây phép cấy đó đúng cách khó hơn vẻ ngoài. Hai phiên bản đầu của tôi đều hỏng:

| Phiên bản | Cách cấy | Vì sao hỏng |
|---|---|---|
| 1 | Bật `k` chỉ số đầu trong tập hôm qua | Ưu ái con nhỏ → thành thiên lệch *giữa các con*; mô hình tần suất cũng bắt được |
| 2 | Bật `k` con ngẫu nhiên của hôm qua | Nâng tỉ lệ về **chung** lên trên nền → mô hình tần suất bắt được mức nền mới |
| 3 ✓ | Bật `k` con của hôm qua **và tắt `k` con không thuộc hôm qua** | Giữ nguyên tần suất biên; thông tin duy nhất cấy vào là thứ tự thời gian |

Kiểm chứng phiên bản 3: tỉ lệ về chung 0.23742 so với nền 0.23766; xích Markov
đạt kỹ năng **+0.373** (t = +40.0) còn mô hình tần suất đạt **−0.0099**
(t = −3.58). Đúng một mô hình bắt được, và đó là mô hình đúng.

### 2.3 Kiểm định ghép cặp ở mức ngày

Mỗi ngày đóng góp 100 quan sát Bernoulli, nhưng **100 con trong cùng một kỳ
không độc lập với nhau** — tổng số con về bị ràng buộc bởi 27 giải. Coi chúng
là 100 mẫu độc lập sẽ thổi phồng bậc tự do lên 100 lần, tức nhân thống kê t
lên khoảng `√100 = 10`, và biến nhiễu thành "có ý nghĩa thống kê".

Vì vậy kiểm định t ghép cặp chạy trên chuỗi **hiệu log-loss theo ngày**:

```python
difference = baseline_daily_loss - model_daily_loss     # một giá trị mỗi ngày
t = difference.mean() / (difference.std(ddof=1) / np.sqrt(difference.size))
```

Ghép cặp chứ không phải hai mẫu độc lập: cùng một ngày, cùng một kết quả, chỉ
khác mô hình — nên phương sai chung theo ngày bị triệt tiêu và phép kiểm mạnh
hơn nhiều.

### 2.4 Đối chứng xáo trộn chu kỳ

Câu hỏi cuối: **mức "kỹ năng" nào thu được thuần túy nhờ tìm kiếm?**

Xáo trộn chu kỳ (`np.roll` theo trục ngày) giữ nguyên toàn bộ cấu trúc tự tương
quan bên trong chuỗi nhãn mà chỉ phá bỏ liên hệ giữa đặc trưng và nhãn. Chạy
lại đúng quy trình đó trên nhiều lần xáo trộn cho phân phối kỹ năng dưới giả
thuyết "không có liên hệ". Nếu điểm trên dữ liệu thật không cao hơn hẳn phân
phối đó, điểm ấy không phải bằng chứng.

Xáo trộn chu kỳ tốt hơn hoán vị ngẫu nhiên ở chính điểm này: hoán vị phá luôn
cả tự tương quan, nên phân phối rỗng thu được **dễ hơn thực tế**, và mô hình
trông tốt hơn nó thực sự là.

Kết quả trên mô hình tốt nhất (Markov bậc 2): thật **+0.00002**, xáo trộn trung
bình −0.00037, xáo trộn cao nhất **+0.00020**.

### 2.5 Kiểm tra lặp lại

Cấu trúc thật lặp lại; nhiễu khớp quá mức thì không. Cắt đôi lịch sử, chấm cùng
một thống kê trên hai nửa, so với cùng một phân phối rỗng. Đây là phép kiểm
phân biệt được hai trường hợp mà giá trị p trên toàn bộ dữ liệu **không** phân
biệt nổi — và nó chính là phép đã giết kết quả dương tính duy nhất ở §0.2.

---

## Phần 3 — Chỉ số đánh giá

### 3.1 Vì sao độ chính xác thuần túy là chỉ số tệ nhất có thể

Ở nền 23.77%, một mô hình luôn nói "không về" đạt **76.23% độ chính xác** mà
không mang một bit thông tin nào. Bất kỳ báo cáo nào nêu độ chính xác mà không
nêu nền đều vô nghĩa, và ở miền này con số đó luôn nghe ấn tượng.

### 3.2 Quy tắc chấm điểm chặt

Quy tắc chấm điểm **chặt** (proper scoring rule) đạt cực trị khi và chỉ khi mô
hình khai báo đúng xác suất thật. Đó là tính chất bắt buộc: dưới quy tắc không
chặt, mô hình có thể ăn điểm bằng cách khai báo lệch đi.

| Chỉ số | Công thức | Cho biết điều gì |
|---|---|---|
| Log-loss | `−[y·log p + (1−y)·log(1−p)]` | Phạt rất nặng khi tự tin mà sai |
| Brier | `(p − y)²` | Phạt vừa phải, dễ diễn giải hơn |
| Kỹ năng | `(loss_nền − loss_mô_hình)/loss_nền` | Cải thiện **tương đối** so với nền |

Dùng cả hai: log-loss nhạy với sự tự tin thái quá, Brier ổn định hơn khi mô
hình khai báo xác suất gần 0 hoặc 1.

### 3.3 Sai số hiệu chuẩn

Chia dự đoán thành 10 nhóm theo phân vị và đo `|xác suất khai báo − tần suất
thật|` bình quân có trọng số:

```python
def calibration_error(probabilities, outcomes, bins=10):
    edges = np.quantile(probabilities, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    total = 0.0
    for i in range(bins):
        mask = (probabilities > edges[i]) & (probabilities <= edges[i + 1])
        if mask.sum():
            total += mask.mean() * abs(probabilities[mask].mean()
                                       - outcomes[mask].mean())
    return total
```

**Vì sao chỉ số này quan trọng nhất trong hệ thống có người dùng thật.** Người
dùng đọc "72%" như một xác suất. Một mô hình xếp hạng tốt nhưng hiệu chuẩn tệ
sẽ nói "85%" cho những trường hợp thực tế chỉ về 30% — và đó là loại sai lầm
gây thiệt hại thật.

Trong bảng ở Phần 1, sai số hiệu chuẩn bám sát số tham số gần như hoàn hảo:
nền 0.0006, kết hợp co rút 0.0001, HMM 0.0022, Markov bậc 2 0.0063, tăng cường
gradient 0.0115, mạng nơ-ron 0.0158, Markov riêng từng con 0.0312.

### 3.4 Chỉ số xếp hạng — và vì sao không được dùng một mình

Trúng@27: chọn 27 con có xác suất cao nhất, đếm số trúng.

Chỉ số này trực giác và là thứ người dùng quan tâm, nhưng **nó không phải quy
tắc chấm điểm chặt**, và bảng ở Phần 1 cho thấy hậu quả rõ ràng:

| Mô hình | Trúng@27 | Kỹ năng log-loss | t ghép cặp |
|---|---:|---:|---:|
| Tần suất kinh nghiệm | **6.67** ← cao nhất | **−0.00329** ← tệ nhì | **−3.83** |
| Nền đồng đều | 6.22 | 0.00000 | +0.00 |

Chọn mô hình bằng trúng@27 sẽ chọn đúng mô hình tệ. Lý do: xếp hạng chỉ quan
tâm *thứ tự*, nên một mô hình có thể cải thiện thứ tự chút ít trong khi làm hỏng
hoàn toàn mức xác suất.

Hơn nữa, mốc 6.22 của nền không phải mốc so sánh đúng. Nền khai báo xác suất
**như nhau cho cả 100 con**, nên "chọn 27 con cao nhất" chỉ là phá hòa tùy ý
theo thứ tự chỉ số. Kỳ vọng của một lần chọn ngẫu nhiên 27 trong 100 là

```
27/100 × (số con thực về trong kỳ) = 0.27 × 23.830 = 6.4342
```

So với mốc đúng đó, lợi thế của mô hình tần suất là +0.2374, kiểm định t ghép
cặp theo ngày cho **t = +1.97, p = 0.0485**.

Đọc con số này cho đúng. Nó vượt ngưỡng 0.05 — sát sạt, và chỉ khi xét riêng
một mình. Nhưng bảng này có 12 mô hình, nên ngưỡng đã hiệu chỉnh Bonferroni là
`t ≈ 2.87`; **1.97 không qua**. Trong khi đó mức suy giảm log-loss của cùng mô
hình ấy đạt `t = −3.83`, **qua** ngưỡng đó thoải mái.

Vậy ta có một mô hình mà lợi thế xếp hạng biến mất sau hiệu chỉnh, còn thiệt hại
về chất lượng xác suất thì trụ lại. Chỉ số xếp hạng nhiễu hơn quy tắc chấm điểm
chặt, đúng như lý thuyết dự đoán: nó vứt bỏ toàn bộ thông tin về độ lớn và chỉ
giữ lại thứ tự.

**Kết luận vận hành:** báo cáo trúng@27 cho người dùng, nhưng **quyết định** mô
hình bằng kỹ năng log-loss cùng t ghép cặp.

### 3.5 Bộ chỉ số tối thiểu

Không chỉ số nào trong sáu chỉ số dưới đây là thừa; mỗi cái bắt một dạng hỏng
mà các cái khác bỏ sót.

| # | Chỉ số | Bắt được dạng hỏng nào |
|---|---|---|
| 1 | Kỹ năng log-loss | mô hình vô dụng nói chung |
| 2 | Kỹ năng Brier | tự tin thái quá ở đuôi |
| 3 | t ghép cặp mức ngày | chênh lệch nhỏ hơn nhiễu ngày qua ngày |
| 4 | Sai số hiệu chuẩn | xác suất khai báo không trung thực |
| 5 | Trúng@27 so với nền | (báo cáo cho người dùng, không dùng để quyết định) |
| 6 | Kỹ năng khi xáo trộn | "kỹ năng" thu được thuần túy nhờ tìm kiếm |

---

## Phần 4 — Kiến trúc thuật toán tối ưu

### 4.1 Tối ưu theo hàm mục tiêu nào

Đây là câu hỏi phải trả lời trước khi vẽ sơ đồ, và câu trả lời bị quyết định
bởi Phần 0.

Hàm mục tiêu mặc định — "cực đại hóa kỹ năng dự đoán kỳ vọng" — không dùng được
ở đây, vì đại lượng đó bằng 0 và không kiến trúc nào làm nó khác 0. Tối ưu hóa
một hàm mục tiêu bằng hằng số chỉ tối ưu hóa nhiễu.

Hàm mục tiêu đúng có ba thành phần đo được:

```
Cực tiểu hóa:  P(báo cáo phát hiện | không có tín hiệu)     — dương tính giả
Cực đại hóa:   P(báo cáo phát hiện | có tín hiệu thật)      — công suất
Cực tiểu hóa:  E|xác suất khai báo − tần suất thật|         — hiệu chuẩn
```

Ba mục tiêu này *đo được*, và một kiến trúc có thể được kiểm chứng là đạt hay
không đạt — khác hẳn "làm mô hình tốt hơn".

### 4.2 Sáu tầng

```
┌──────────────────────────────────────────────────────────────┐
│ Tầng 5 · GIÁM SÁT TRÔI                                       │
│   Cổng kỹ năng chạy hằng ngày trên lịch sử dự đoán.          │
│   Đã chứng minh: phát hiện hồi quy ngay ngày đầu tiên        │
│   (2025-12-28) thay vì 8 tháng sau.                          │
├──────────────────────────────────────────────────────────────┤
│ Tầng 4 · KẾT HỢP CO RÚT          ← hạt nhân của kiến trúc    │
│   wᵢ ∝ max(0, tᵢ − t_ngưỡng)²,  nền giữ phần còn lại         │
│   Trên dữ liệu thật: nền = 1.000000                          │
├──────────────────────────────────────────────────────────────┤
│ Tầng 3 · CỔNG THỐNG KÊ                                       │
│   BH-FDR → đối chứng xáo trộn → kiểm tra lặp lại             │
│   Cả ba đều phải qua. Không có ngoại lệ.                     │
├──────────────────────────────────────────────────────────────┤
│ Tầng 2 · CHẤM ĐIỂM CUỐN CHIẾU                                │
│   Quy tắc chấm điểm chặt · t ghép cặp mức ngày               │
│   Bất biến không-rò-rỉ được kiểm thử tự động khẳng định      │
├──────────────────────────────────────────────────────────────┤
│ Tầng 1 · THƯ VIỆN GIẢ THUYẾT                                 │
│   Bayes · Markov · sống sót · HMM · phân cụm · tăng cường    │
│   Mỗi mô hình khai báo rõ giả thuyết miền mà nó kiểm         │
├──────────────────────────────────────────────────────────────┤
│ Tầng 0 · NỀN MIỀN + CỔNG DỮ LIỆU                             │
│   p₀ = 1 − 0.99²⁷, định nghĩa một lần tại xsmb_domain.py     │
│   Kiểm tra ngày liên tục, đối chiếu nhiều nguồn              │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 Bằng chứng hai chiều

Tầng 4 là điểm mà kiến trúc này khác với một chồng mô hình thông thường. Một
`StackingClassifier` chuẩn hóa trọng số sao cho tổng bằng 1 **giữa các mô hình
thành phần** — nghĩa là luôn có một mô hình nhận trọng số cao nhất, kể cả khi
mọi mô hình đều vô dụng. Cấu trúc đó **không có cách nào diễn đạt câu "không
cái nào đáng tin"**.

Ở đây nền là một thành phần đặc biệt: nó giữ toàn bộ trọng số cho tới khi một
mô hình chứng minh được điều ngược lại. Về mặt Bayes, đây là trung bình hóa mô
hình với tiên nghiệm spike-and-slab đặt khối lượng dương tại "không có hiệu
ứng".

```python
class ShrinkageEnsemble:
    @property
    def threshold(self):
        """Ngưỡng t đã hiệu chỉnh Bonferroni. Không hiệu chỉnh thì với 10 mô
        hình, xác suất có ít nhất một mô hình vượt 1.96 hoàn toàn do may rủi
        là khoảng 40%."""
        return stats.norm.isf(self.alpha / (2 * len(self.models)))

    def weights(self, history):
        excess = np.maximum(self._evidence(history) - self.threshold, 0.0) ** 2
        total = excess.sum()
        # Nền nhận toàn bộ phần trọng số không mô hình nào giành được.
        return np.append(excess / (total + 1.0), 1.0 / (total + 1.0))
```

Bình phương phần vượt ngưỡng, chứ không dùng trực tiếp `t`, làm trọng số tắt
trơn về 0 tại ngưỡng thay vì nhảy bậc — một mô hình dao động quanh ngưỡng sẽ
không làm dự báo giật.

Một kiến trúc như thế này chỉ có giá trị nếu nó đúng ở **cả hai chiều**. Im
lặng khi không có gì thì dễ: một hàm trả về hằng số cũng làm được. Điều phải
chứng minh là nó *không* im lặng khi có tín hiệu thật.

| Dữ liệu | Bayes | Markov | Nguy cơ gan | **Nền** | Kỹ năng |
|---|---:|---:|---:|---:|---:|
| **391 kỳ thật** | 0.000000 | 0.000000 | 0.000000 | **1.000000** | 0.00000 |
| **Cấy bạc nhớ** | 0.0000 | 0.4827 | 0.5165 | **0.0008** | +0.373 |

Trên dữ liệu thật, nền giữ trọn trọng số. Trên chuỗi cấy tín hiệu bạc nhớ *giữ
nguyên tần suất biên* (§2.2, phiên bản 3), nền nhường gần hết trọng số, và
nhường cho đúng hai mô hình nhìn thứ tự thời gian — mô hình tần suất nhận đúng
0.0000.

Việc trọng số chia đôi giữa xích Markov và mô hình nguy cơ là **đúng**, không
phải nhược điểm: ép một con của hôm qua về lại hôm nay chính là làm nguy cơ ở
mức gan 0 tăng vọt, nên cả hai mô hình đều đang nhìn cùng một hiện tượng thật.

### 4.4 Kết quả cuối

Trên 391 kỳ thật, kiến trúc này cho kết quả **trùng khít với nền đến từng chữ
số** trên mọi chỉ số:

| | Log-loss | Brier | Kỹ năng | t | Trúng@27 | Lệch hiệu chuẩn |
|---|---:|---:|---:|---:|---:|---:|
| Nền đồng đều | 0.5491166 | 0.1815149 | 0.0 | 0.0 | 6.2214022 | 0.0006453 |
| Kết hợp co rút | 0.5491166 | 0.1815149 | 0.0 | 0.0 | 6.2214022 | 0.0006453 |

Đây không phải trùng hợp mà là điều phải xảy ra: trọng số của nền bằng đúng
1.000000, nên kiến trúc *là* nền trên dữ liệu này. Nó **thắng cả 11 mô hình đơn
lẻ**, vì cả 11 đều có kỹ năng âm.

Đây không phải một kết quả đáng thất vọng được diễn đạt cho dễ nghe. Khi giá
trị kỳ vọng của mọi dự đoán bằng nhau, kiến trúc tốt nhất là kiến trúc **không
thêm phương sai** — và nó phải là kiến trúc *đo được điều đó rồi mới quyết
định*, chứ không phải kiến trúc được lập trình sẵn để trả về nền.

Khác biệt giữa hai thứ đó chính là bảng ở §4.3.

---

## Phần 5 — Điều gì sẽ làm tôi đổi kết luận

Một kết luận không kèm điều kiện bác bỏ thì không phải kết luận khoa học. Dưới
đây là những gì sẽ làm tôi đổi ý, và toàn bộ đều đã được cài đặt sẵn để chạy:

1. **Phép kiểm cấu trúc qua được Bonferroni *và* lặp lại ở cả hai nửa.** Chạy
   `src/run_randomness_report.py`; điều kiện là `significant_after_bonferroni ≥ 1`
   và `replication.replicates == true`.
2. **Một mô hình đạt t ghép cặp > 2.5 trên ít nhất 200 ngày cuốn chiếu, và kỹ
   năng của nó vượt phân vị 95% của phân phối xáo trộn.** Chạy
   `src/run_model_benchmark.py`.
3. **Kết hợp co rút tự chuyển trọng số khỏi nền trên dữ liệu sản xuất.** Đây là
   tín hiệu mạnh nhất vì nó không cần ai phải nhìn: hệ thống tự phát hiện.
4. **Có thêm dữ liệu.** Ngưỡng phát hiện co theo `1/√n`. Để hạ mức +25.4%
   xuống +10% cần khoảng **2 500 kỳ** — gần bảy năm. Ngưỡng đó cũng sẽ tự nới
   ra khi lịch sử dài thêm, không cần làm gì.

Cho đến khi một trong bốn điều đó xảy ra, câu trả lời trung thực nhất mà hệ
thống có thể đưa ra là con số nền — và kiến trúc ở Phần 4 đưa ra đúng con số
đó, sau khi đã đo để chắc chắn.

---

## Tái lập

```bash
# Phần 0 — bộ kiểm định cấu trúc và phân tích công suất (~17 giây)
PYTHONPATH=src python src/run_randomness_report.py

# Phần 1 — đấu trường mô hình và đối chứng xáo trộn (~25 phút)
PYTHONPATH=src python src/run_model_benchmark.py

# Kiểm thử: bất biến không-rò-rỉ, đối chứng dương/âm, hành vi kiến trúc
PYTHONPATH=src python -m pytest tests/test_randomness_battery.py \
                                tests/test_model_benchmark.py -q
```

| Tệp | Vai trò |
|---|---|
| `src/randomness_battery.py` | 7 phép kiểm cấu trúc, phân phối rỗng Monte Carlo, phân tích công suất |
| `src/modeling/benchmark.py` | 11 họ mô hình + kết hợp co rút, đánh giá cuốn chiếu |
| `src/run_randomness_report.py` | → `data/research/randomness_report.json` |
| `src/run_model_benchmark.py` | → `data/research/model_benchmark.json` |
| `tests/test_randomness_battery.py` | 29 phép kiểm |
| `tests/test_model_benchmark.py` | 61 phép kiểm, gồm bất biến không-rò-rỉ cho mọi mô hình |
