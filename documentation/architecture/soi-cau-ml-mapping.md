# Ánh xạ "soi cầu" sang Machine Learning — hiện trạng và khoảng trống

Tài liệu đối chiếu bốn ánh xạ ML thường được đề xuất với mã **đã có** trong
kho, và ghi lại hai lỗi thiết kế trong bản đề xuất kèm số đo.

## 1. Bốn ánh xạ: đã có sẵn cả bốn

| Phương pháp | Ánh xạ ML đề xuất | Đã có tại | Dòng |
|---|---|---|---|
| Cầu chạy / cầu động | Bi-LSTM + Spatial Attention | `src/bridges/scanner.py` — quét toàn bộ họ cầu ghép chéo bằng phép ma trận, có tỉ lệ nền và đuôi xác suất | 482 |
| Lô gan / chu kỳ | Survival Analysis, Hazard | `src/hazard_stats.py` — `hazard_curve_loto`, `hazard_curve_de` | 157 |
| Bóng âm dương / ngũ hành | Feature engineering + XGBoost | `src/cau_keo_domain_challenger.py`, `src/ml_engine/features.py` | — |
| Cầu chạm / cầu tổng | Hidden Markov Model | `src/markov_stats.py` — `MarkovChain`, `build_markov_chain` | 174 |

Ngoài ra `src/ml_engine/` đã có LightGBM/CatBoost, LambdaMART, GRU chuỗi thời
gian, Thompson Sampling, phát hiện trôi khái niệm và walk-forward validation.

**Viết lại bốn module này là làm lại việc đã xong.** Khoảng trống thật nằm ở
chỗ khác — xem mục 4.

## 2. Lỗi thứ nhất: mô hình 4,65 triệu tham số trên 363 mẫu

Kiến trúc `DynamicBridgeLSTM` được đề xuất (attention 1070 chiều, Bi-LSTM 2
lớp, hidden 256):

| Thành phần | Tham số |
|---|---|
| Spatial attention | 275 118 |
| Bi-LSTM 2 lớp | 4 296 704 |
| Tầng đầu ra | 78 564 |
| **Tổng** | **4 650 386** |

Dữ liệu có **393 kỳ**. Với cửa sổ 30 ngày còn **363 mẫu huấn luyện**.

```
4 650 386 tham số / 363 mẫu = 12 811 tham số trên mỗi mẫu
```

Một mô hình có nhiều tham số hơn mẫu vài nghìn lần sẽ **học thuộc lòng** tập
huấn luyện và không tổng quát hoá được gì. Walk-forward validation phát hiện
được điều đó nhưng không sửa được nó.

Đây không phải chuyện chỉnh siêu tham số. `src/ml_engine/models.py` đã chọn
`hidden_size = 16` (**7 364 tham số**) và ghi rõ trong docstring rằng ràng
buộc nằm ở dữ liệu chứ không ở siêu tham số. Bản đề xuất lớn hơn **632 lần**.

Muốn dùng kiến trúc cỡ đó cần khoảng 10⁵ kỳ quay — tức **hơn 270 năm** xổ số
hàng ngày.

## 3. Lỗi thứ hai: `np.outer` không chứa thông tin tương tác

Hàm `extract_top_bridges` được đề xuất tính điểm cặp vị trí bằng:

```python
pair_scores = np.outer(pos_scores, pos_scores)
```

Tích ngoài của một véc-tơ với chính nó là **tích hai điểm biên**. Nó không
chứa bất kỳ thông tin nào về quan hệ giữa vị trí `i` và `j`. Hệ quả xác định
được bằng đại số, không cần chạy thử: cặp hạng 1 luôn là (top1, top2), hạng 2
là (top1, top3), và cứ thế.

Chạy kiểm với điểm ngẫu nhiên:

```
Top vị trí đơn lẻ : [26, 77, 94, 27]
Top cặp           : (26,77) (26,94) (26,27) (77,94) ...
Mọi cặp top đều chứa vị trí top1: True
```

Bảng "cặp cầu uy tín nhất" sinh ra từ hàm này chỉ là bảng xếp hạng đơn lẻ
viết lại dưới dạng cặp. Nó **không phát hiện được cầu nào**.

Muốn đo tương tác thật thì cần một đại lượng bậc hai thực sự — thông tin
tương hỗ giữa cặp vị trí và kết quả, hoặc tần suất đồng xuất hiện so với tỉ lệ
nền. Đó chính là việc `src/bridges/scanner.py` đang làm, kèm kiểm soát đa
kiểm định.

## 4. Khoảng trống thật: không phải thiếu thuật toán

Kết quả đo trên chính kho này (xem `documentation/research/`):

| Phép đo | Kết quả |
|---|---|
| Bộ kiểm định ngẫu nhiên | 1/7 thô, **0/7 sau Bonferroni**, không lặp lại được ở nửa sau dữ liệu |
| So sánh 12 họ mô hình | **0/12 vượt tỉ lệ nền** |
| `ml_engine` trên 192 kỳ thật | skill **−0,000670** (t = −1,79), chế độ an toàn 120/192 kỳ |
| Điểm hoà vốn | cần lift **+21,0%** so với nền 0,2377 |

Thêm một mô hình thứ mười ba vào danh sách mười hai mô hình không vượt nền là
việc có chi phí và không có bằng chứng nào cho thấy nó sẽ khác.

Khoảng trống thật đã được ghi lại và vẫn đang mở:

1. **Dữ liệu quá ngắn.** 393 kỳ là trần cứng cho mọi mô hình. Bổ sung lịch sử
   nhiều năm là thay đổi duy nhất làm dịch chuyển được mọi kết quả ở trên.
2. **Chạy đúng giờ.** `repository_dispatch` vẫn chưa từng được gọi; lịch
   GitHub trễ 2–6 giờ (`documentation/operations/on-time-trigger.md`).

## 5. Về kiến trúc Next.js + FastAPI + Redis + DuckDB

Kho phát hành dưới dạng site tĩnh trên GitHub Pages. Một backend FastAPI
không chạy được ở đó — cần chọn nơi lưu trữ khác, và đó là quyết định vận
hành, không phải kỹ thuật.

Về hiệu năng: toàn bộ lịch sử là **56 KB**. Tầng L1 dict + Redis + DuckDB +
`np.memmap` được thiết kế cho dữ liệu lớn hơn nhiều bậc. Ở 56 KB, mọi truy
vấn thống kê chạy trong bộ nhớ dưới một mili-giây mà không cần thành phần nào
trong số đó. Thêm chúng vào là thêm bốn thứ phải vận hành để giải quyết một
vấn đề chưa tồn tại.
