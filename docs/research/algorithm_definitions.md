# Định nghĩa thuật toán chuẩn và hợp đồng an toàn

Xác minh lần cuối: 2026-09-03

Các mẫu lịch sử không bảo đảm kết quả xổ số tương lai. Chỉ bằng chứng ngoài
mẫu theo thời gian mới có thể biện minh cho việc bật một đặc trưng thử nghiệm
trong hệ thống vận hành.

## Ngữ nghĩa dữ liệu và thời gian

VLA tách riêng các lớp sau:

| Lớp | Ý nghĩa | Triển khai đại diện |
| --- | --- | --- |
| `RawDraw` | Giá trị giải đã công bố, giữ đúng độ dài gốc | `lottery.Result`, dataframe gốc |
| `NormalizedDraw` | Ngày, vị trí chữ số ngữ nghĩa, số lần xuất hiện 00..99, hai số cuối ĐB | `dynamic_cau.NormalizedDraw` |
| `CandidateObservation` | Một dòng huấn luyện `(ngày neo, ứng viên)` | `cau_keo_ml.build_cau_keo_feature_frame` |
| `DerivedFeature` | Giá trị tính được từ thông tin có tại/trước ngày neo | `ml_features`, `cau_keo_feature_groups` |
| `PatternEvidence` | Hỗ trợ, lần trượt, chuỗi và chẩn đoán không gian tìm kiếm | `dynamic_cau.PatternEvidence` |
| `ModelPrediction` | Xác suất mô hình đã hiệu chỉnh cho một ngày tương lai | artifact/mô hình cầu-kèo |

Với ngày mục tiêu `D`, API mô tả/nghiên cứu chỉ dùng dòng có `date < D`. Dòng
huấn luyện dùng ngày neo `t` để dự báo mục tiêu `t+1`. `calendar_alignment`
từ chối ngày trùng và chỉ tạo cặp ngày lịch chính xác. Trục ngày của dữ liệu vị
trí gốc và dữ liệu hai chữ số chuẩn hóa phải giống nhau hoàn toàn trước khi dựng
đặc trưng ML.

## Quan hệ số chuẩn

`number_reference.py` là nguồn sự thật duy nhất; mô-đun đặc trưng không được tự
triển khai lại các quy tắc này.

- Đầu và đuôi là chữ số hàng chục và hàng đơn vị.
- Tổng thô nằm trong 0..18; tổng modulo 10 là `(đầu + đuôi) mod 10`.
- Lộn/đảo biến `AB` thành `BA`.
- Bóng dương dùng ánh xạ `0↔5, 1↔6, 2↔7, 3↔8, 4↔9`.
- Bộ là quỹ đạo sinh bởi bóng dương theo từng chữ số và phép đảo.
- Cặp lô tô 50 gồm 45 cặp đảo và `00-55`, `11-66`, `22-77`, `33-88`, `44-99`.
- Chạm `d` là tập 19 số chứa `d` ở ít nhất một vị trí.
- Kép, lệch/âm và sát-kép tuyến tính/vòng được phân biệt rõ.

Đây là các quan hệ tất định, không phải tuyên bố dự báo.

## Tần suất

Với tập kỳ hợp lệ `W_D` nằm hoàn toàn trước `D`:

```text
occurrence_count(x) = Σ[t trong W_D] count_t(x)
draw_count(x)       = Σ[t trong W_D] 1[count_t(x) > 0]
hit_rate(x)         = draw_count(x) / |W_D|
```

`frequency_stats.compute_frequency_stats` trả cả số lần xuất hiện và số kỳ có
mặt; không dùng hai đại lượng thay thế lẫn nhau. Cửa sổ theo ngày lịch và theo
số kỳ là hai cấu hình loại trừ nhau.

```python
stats = compute_frequency_stats(sparse, "2026-09-03", lookback_days=30)
```

## Gan và chu kỳ lặp

Nếu chỉ số lần về gần nhất trước `D` là `i_last` và có `n` kỳ hợp lệ:

```text
current_gap_draws = n - i_last - 1
```

Với hai chỉ số lần về liên tiếp `i_(k-1), i_k`:

```text
interval_draws = i_k - i_(k-1)
absent_draws   = interval_draws - 1
```

`gap_cycle_stats.compute_gap_stats` còn trả đơn vị lịch, trung bình/trung vị/
lớn nhất của gan hoàn tất, phân vị thực nghiệm, điểm Z khi có phương sai, tứ
phân vị chu kỳ, độ dốc chu kỳ gần đây và khoảng kiểm duyệt hiện tại. Khoảng đang
kiểm duyệt không được trộn vào chu kỳ hoàn tất.

Gan dài chỉ có giá trị mô tả. Gan lớn không làm xác suất kỳ sau tự tăng, trừ khi
một mô hình riêng chứng minh quan hệ đó bằng kiểm định ngoài mẫu.

## Thống kê nhóm

`compute_group_frequency_stats` và `compute_group_gap_stats` nhận `head`,
`tail`, `total_mod10` hoặc `cham`. Số lần xuất hiện cộng cả bội số của thành
viên; số kỳ là số ngày có ít nhất một thành viên. Các nhóm chạm cố ý chồng lấn.

## Ngữ nghĩa hai nháy

VLA tính riêng cho từng số được dự báo:

```text
trúng lô tô thường = occurrence_count >= 1
trúng hai nháy     = occurrence_count >= 2
số lần chính xác  = occurrence_count
```

Hai ứng viên khác nhau mỗi số về một lần không được gộp thành một lần trúng hai
nháy. `PatternEvidence` trả tỷ lệ ít nhất một lần, ít nhất hai lần và biểu đồ
số lần chính xác.

## Bộ máy cầu vị trí động

Vị trí nguồn có định danh ngữ nghĩa:

```text
(prize_name, result_index, digit_index)
```

Không phụ thuộc độ lệch của bảng hiển thị. Quy tắc trễ một kỳ đọc vị trí từ
ngày lịch liền trước rồi áp dụng một trong các phép:

- `concat`: `a,b -> 10a+b`;
- `reverse_concat`: `a,b -> 10b+a`;
- `reverse_pair`: `{10a+b, 10b+a}`;
- `bo`: bộ chuẩn chứa `10a+b`.

```python
result = find_running_patterns(
    raw_history,
    days_count=3,
    source_positions=[position_a, position_b],
    transformations=["concat", "reverse_pair"],
    target_type="loto",
    minimum_support=30,
    max_hypotheses=50_000,
)
```

Kết quả ghi đầy đủ kích thước không gian tìm kiếm, số giả thuyết đã quét, số
còn lại, chuỗi hiện tại/dài nhất, hỗ trợ, số trúng/trượt, độ tin cậy thô và làm
trơn Laplace, độ phủ và ngày trúng gần đây. Khi tìm nhiều hơn một giả thuyết,
hệ thống gắn `PATTERN_SELECTION_BIAS_RISK`. Chuỗi lịch sử dài chỉ là phát hiện
mẫu, không phải bằng chứng ngoài mẫu.

## Đồng xuất hiện, chuyển tiếp và luật kết hợp

Với `N` quan sát hợp lệ:

```text
support(A -> B)    = count(A and B) / N
confidence(A -> B) = count(A and B) / count(A)
lift(A -> B)       = confidence(A -> B) / P(B)
```

`conditional_matrices.build_cooccurrence_matrix` dùng tập số cùng kỳ.
`build_transition_matrix` chỉ dùng cặp ngày lịch kế tiếp chính xác. Cả hai giữ
số đếm thô và hỗ trợ biên. Vì lô tô là bài toán đa nhãn, mỗi số đích là một
kết quả Bernoulli; tỷ lệ có điều kiện đã làm trơn là:

```text
(count(A and B) + alpha) / (count(A) + 2*alpha)
```

Các hàng không bị ép có tổng bằng một. `association_rules.mine_association_rules`
thêm ngưỡng bằng chứng tối thiểu và cận dưới Wilson để mẫu `1/1` không vượt mẫu
`70/100` chỉ vì độ tin cậy thô.

## Chuỗi Markov trạng thái loại trừ

Với không gian trạng thái loại trừ lẫn nhau `S`:

```text
P_ij = (count(i -> j) + alpha)
       / (sum_k count(i -> k) + alpha*|S|)
```

`markov_stats.build_markov_chain` giữ ma trận số đếm và kiểm tra tổng mỗi hàng
khi có làm trơn dương. `compute_markov_for_loto` hiện hữu mô hình hóa chuyển
tiếp trúng/trượt Bernoulli của cùng số, phù hợp hơn với lô tô đa nhãn.
`number_dynamics` chứa đặc trưng bậc hai có giới hạn và co ước lượng. Không đặc
trưng nào được đưa vào vận hành chỉ vì khớp lịch sử.

## Điểm ứng viên và xác suất

`candidate_scoring.rank_candidates` trả một điểm xếp hạng:

```text
score(x) = Σ available_i weight_i * normalized_component_i(x)
           / Σ available_i weight_i
```

Thành phần mặc định có trọng số khác 0 là tần suất, độ gần và EMA. Phân vị gan
và chu kỳ có sẵn nhưng mặc định trọng số 0 để không cài sẵn ngụy biện “đến
hạn”. Đầu vào điều kiện/mẫu là tùy chọn và mặc định tắt; khi bật phải được chuẩn
hóa `[0,1]`, nếu sai thang đo cấu hình sẽ thất bại.

```text
alpha = 2 / (span + 1)
EMA_t = alpha*y_t + (1-alpha)*EMA_(t-1)
```

Cấu hình ghi rõ `span`, lịch sử tối thiểu và cách khởi tạo (`zero`, `first`,
`historical_mean`). `CandidateScore.score` không bao giờ được trình bày như xác
suất đã hiệu chỉnh.

## Họ đặc trưng ML và manifest vận hành

Mô hình nền trong `cau_keo_ml.py` vẫn là mô hình vô địch hiện hành. Các nhóm
thử nghiệm được định nghĩa tập trung trong `cau_keo_feature_groups.py`:

| Nhóm | Nguồn sự thật | Trạng thái mặc định |
| --- | --- | --- |
| `baseline` | `cau_keo_ml.FEATURE_COLS` | bật |
| `partner` | `number_reference.cap_loto_50_partner` | thử nghiệm, tắt |
| `cap_50` | tổng hợp cặp cùng ngày neo | thử nghiệm, tắt |
| `bo` | họ bộ chuẩn | thử nghiệm, tắt |
| `bong` | phép biến đổi bóng chuẩn | thử nghiệm, tắt |
| `cham` | nhóm chạm chuẩn | thử nghiệm, tắt |
| `tong` | nhóm tổng modulo 10 chuẩn | thử nghiệm, tắt |
| `dynamic_pattern` | `dynamic_cau` | chỉ nghiên cứu |
| `conditional_matrix` | `conditional_matrices` | chỉ nghiên cứu |
| `markov` | `markov_stats`, `number_dynamics` | chỉ nghiên cứu |
| đồ thị/Pascal/Fibonacci | chưa triển khai | tắt |

Mỗi nhóm có danh sách cột, nguồn gốc, yêu cầu thời gian và cờ mặc định rõ ràng.
Artifact cổng chứa manifest cho phép tường minh:

```json
{
  "schema_version": 3,
  "baseline_features": [],
  "feature_groups": {},
  "promoted_groups": [],
  "production_features": [],
  "evaluation": {}
}
```

Suy luận vận hành gọi `predict_with_feature_allowlist`; cột bị từ chối không
được truyền cho mô hình. Kiểm thử hồi quy thay đặc trưng bị từ chối bằng giá trị
cực đoan và yêu cầu dự báo không thay đổi.

## Kiểm định cuốn chiếu và cổng đưa vào vận hành

Thử nghiệm nhóm miền có bốn nếp thời gian:

1. Sàng lọc từng nhóm trên nếp 1–2.
2. Xác nhận nhóm sống sót trên nếp 3 muộn hơn.
3. Kết hợp nhóm đã xác nhận và chỉ đánh giá một lần trên nếp 4 chưa chạm.
4. So sánh nền/thử nghiệm với cùng ngày, nhãn, ứng viên, siêu tham số và hạt giống.

Với mỗi hàm mất mát:

```text
improvement = baseline_loss - challenger_loss
skill       = improvement / baseline_loss
```

Brier và LogLoss đều là mất mát, nên mức cải thiện/kỹ năng dương là tốt hơn.
Độ bất định dùng bootstrap ghép cặp theo cụm ngày: lấy mẫu ngày ngoài mẫu có
hoàn lại, giữ toàn bộ 100 dòng của mỗi ngày và giữ cả bội số ngày được lấy lặp.
Mặc định dùng 1.000 lượt, hạt giống `20260902`, khoảng 95% và ít nhất 30 ngày.

Đưa vào vận hành chỉ khi toàn bộ điều kiện sau cùng đạt:

- phân vùng thời gian nghiêm ngặt hợp lệ;
- đủ ngày ngoài mẫu;
- kỹ năng Brier và LogLoss vượt ngưỡng dương;
- cận dưới khoảng tin cậy của cải thiện Brier và LogLoss đều lớn hơn 0;
- mọi trạng thái/chỉ số hữu hạn và hợp lệ.

Cổng đóng khi không chắc chắn và ghi lý do như `negative_brier_skill`,
`negative_logloss_skill`, `brier_ci_crosses_zero`,
`logloss_ci_crosses_zero`, `insufficient_oos_dates` hoặc `temporal_leakage`.
Nếu không có nhóm nào đạt, xác suất của mô hình nền không đổi.

## Trạng thái Pascal, Fibonacci và đồ thị

Quy tắc Pascal công khai quan sát được là tam giác tổng hai số kề nhau modulo
10. Cách chọn hạt giống và trích ứng viên chưa đủ rõ để tái lập độc lập, vì vậy
VLA ghi tài liệu và bác bỏ thay vì đoán. Truy hồi Fibonacci chuẩn là rõ ràng,
nhưng chưa tìm thấy ánh xạ lịch sử xổ số→ứng viên có thể tái lập. Tóm tắt đồ thị
vẫn là nghiên cứu mô tả dự kiến trên các ma trận chuẩn. Không phương pháp nào
được nối vào vận hành.
