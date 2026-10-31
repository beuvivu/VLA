# Rà soát engine Vietlott — xác suất, kiểm định, thuật toán dự báo (31-10-2026)

## Yêu cầu

Chủ dự án: "Kiểm soát lại toàn bộ code vietlott, nâng cao xác suất suy đoán, tạo các phép tính thuật
toán chuẩn và cao cấp hơn cho phần này, đảm bảo source code được tinh chỉnh và hoàn thiện hết các bước
cuối."

Kỳ quay Vietlott là quay lồng. Một thuật toán chỉ nâng được xác suất dự đoán ở nơi kỳ quay lệch khỏi
máy công bằng, và chỉ khi độ lệch ấy được ước lượng đúng. Ở nơi không có độ lệch, "nâng cao" chỉ còn
hai nghĩa:

- con số in ra đúng định nghĩa và được kiểm định đúng;
- cách chọn nhiều vé tận dụng được cấu trúc của trò chơi, trong khi xác suất của từng vé không đổi.

## Kết quả ngắn

| Hạng mục | Kết quả |
|---|---|
| Lõi xác suất | Không có lỗi. Đã đối chiếu độc lập bằng vét cạn. |
| Nhánh ML với độ lệch Max 3D | **Không học được** độ lệch thật mà engine cũ đã chứng minh. Đã thêm chuyên gia hỗn hợp Bayes. |
| Số đặc biệt Lotto 5/35 | Năm vé dùng chung một số đặc biệt. Đã chia mỗi vé một số. |
| Kết luận e-value trên trang | Chưa hiệu chỉnh cho bảy sản phẩm. Đã dùng ngưỡng họ 140. |

Lõi xác suất đã đối chiếu độc lập bằng vét cạn:

- luật bộ số, có và không có số phụ cùng lồng;
- xác suất biên và log-likelihood;
- top-N theo nhánh cận;
- luật chữ số;
- `inclusion_probabilities`, `match_distribution`;
- "ít nhất một vé" và cận hợp;
- vé phủ rời nhau;
- xác suất từng hạng giải Mega/Power/Lotto.

## 1. Lõi xác suất — đã đúng

Đối chiếu bằng vét cạn, độc lập với mã của engine (0 sai lệch):

| Hàm | Đối chiếu |
|---|---|
| `Law.probability`, `Law.marginals`, `Law.log_likelihood` | tổng trên mọi bộ (n = 9, k = 3, có/không số phụ cùng lồng) bằng 1, xác suất biên và log-likelihood khớp |
| `Law.top` (nhánh cận) | 20 luật ngẫu nhiên n = 16, k = 4, ngân sách 300 nút: khi báo `exact` thì đúng top-5 vét cạn |
| `inclusion_probabilities`, `match_distribution` | khớp vét cạn của luật Bernoulli có điều kiện |
| `hits.any_ticket_tail`, `hits.union_bounds` | khớp vét cạn mọi kết quả, cận chứa giá trị đúng |
| `GameSpec.tier_probabilities` | Mega P(trúng) = 2,383%, Power 1,333%, Lotto 9,604%, khớp phép đếm |

Kiểm định độ ngẫu nhiên (`analytics.randomness`, `inference.sequential`) dùng phân phối null chính
xác của thiết kế k-trong-n. e-process là martingale không âm đúng nghĩa.

## 2. Nhánh ML bỏ qua độ lệch thật của Max 3D — đã sửa

**Độ lệch có thật và ổn định.** Ở Max 3D, chữ số 6 ở hàng đơn vị chiếm 10,6 / 10,9 / 10,6 / 11,3 /
11,1 / 10,8% trong sáu giai đoạn liền từ 04-2019 tới 09-2026. Mức công bằng là 10%; z từ +1,1 đến +2,7
ở MỌI giai đoạn. Engine cũ (`vietlott_engine.forecast`) thấy nó bằng e-value: 10^2,57 ở Max 3D,
10^2,84 ở Max 3D Pro.

**Nhánh ML không học được độ lệch ấy.** Nhánh ML là nơi sinh vé công bố trên trang. Luật ML ghi vào sổ
cho P(6 ở hàng đơn vị) = 0,1001 (Max 3D) và 0,1000 (Max 3D Pro), nên năm bộ ba công bố đổi mỗi kỳ theo
nhiễu: 020, 223, 123, 023, 021… Tổng log-score so với quay công bằng trên 1 000 kỳ cuối là −0,158
log10 (Max 3D) và −0,161 log10 (Max 3D Pro), tức kém máy công bằng.

**Vì sao không thêm một Dirichlet đầy đủ.** Học 27 tham số tự do tốn khoảng (d/2)·log n nats, nhiều
hơn lợi ích của một độ lệch 1%. Engine cũ thắng vì dùng hỗn hợp Bayes chia sẻ cố định trên các "tilt"
thưa (mỗi giả thuyết một tham số) cùng Dirichlet co mạnh. Hỗn hợp ấy chỉ trả log(số chuyên gia).

**Sửa.** Thêm chuyên gia `bayes_mixture` (`vietlott/src/vlm/forecast/bayes_expert.py`) vào ensemble ML,
chỉ cho thành phần chữ số. Nó chạy đúng `Component` của engine cũ trên các kỳ bộ ML học, chấm trước
rồi mới học. Trọng số Bayes của ensemble quyết định có tin nó hay không. Đo trên 1 000 kỳ cuối của
seed:

| Sản phẩm | Log-score trước | Sau | Trọng số chuyên gia mới |
|---|---|---|---|
| Max 3D | −0,158 log10 | **+0,771** | 0,70 |
| Max 3D Pro | −0,161 log10 | **+0,641** | 0,48 |
| Max 4D | −0,248 | −0,222 | 0,12 |
| Bingo18 | −0,271 | −0,241 | 0,09 |
| Số đặc biệt Lotto | −0,241 | −0,234 | 0,10 |

Kết quả của bản sửa:

- Luật ML nay cho P(6 ở hàng đơn vị) = 0,1055 với Max 3D và 0,1033 với Max 3D Pro. Mức này thận trọng
  hơn 0,1075 của engine cũ vì ensemble còn trộn các chuyên gia khác.
- Năm bộ ba công bố đều kết thúc bằng 6.
- Xác suất về của mỗi số công bố tăng khoảng ×1,057 (Max 3D) và ×1,035 (Max 3D Pro), so với ×1,006
  theo nhiễu trước đây.
- RTP vẫn dưới 1: độ lệch không biến trò chơi thành có lãi.

Checkpoint ML lên version 5:

- Sản phẩm có thành phần chữ số (Lotto, Max 3D, Max 3D Pro, Max 4D, Bingo18) học lại; bằng chứng
  live bắt đầu lại.
- Mega, Power, Keno vẫn nạp checkpoint 3/4 vì kiến trúc của chúng không đổi.
- Xác suất triển khai vẫn là luật công bằng cho tới khi cổng live mở.

## 3. Lotto 5/35: mỗi vé một số đặc biệt — `coverage-v2`

Một vé Lotto 5/35 trúng giải khi trùng ≥ 3 số chính HOẶC trùng số đặc biệt; số đặc biệt quay từ lồng
riêng 12 số. Cả hai điều kiện đọc thẳng từ bảng giải.

Trước đây trang liệt kê năm số đặc biệt, nhưng cả năm vé được chấm bằng số hạng nhất. Năm vé vì thế
cùng trúng hoặc cùng trượt phần số đặc biệt.

Từ lần ghi mang `ticket_rule = coverage-v2`, vé thứ j mang số đặc biệt hạng j và được chấm đúng số ấy.
Mốc chính xác, khớp vét cạn mọi bộ năm số × 12 số đặc biệt:

| Năm vé rời nhau | P(ít nhất một vé trúng giải) |
|---|---|
| Chung một số đặc biệt (cũ) | 14,7% |
| Năm số đặc biệt khác nhau | **45,7%** |
| (một vé riêng lẻ) | 9,6% |

Xác suất và tiền thưởng kỳ vọng của TỪNG vé không đổi. Phần tăng phần lớn là giải Khuyến khích, bằng
đúng giá một vé. Trang in các mốc ấy từ `dashboard.prize_coverage`.

Lần ghi `coverage-v1` giữ cách cũ; không kỳ nào bị chấm lại bằng quy tắc mới.

## 4. Kết luận e-value trên trang — hiệu chỉnh cho bảy sản phẩm

Engine kiểm TỪNG sản phẩm ở e-value ≥ 1/α = 20. Trang tổng quan lại kết luận cùng lúc trên bảy sản
phẩm. Với bảy phép kiểm, khả năng ít nhất một sản phẩm vượt 20 do may rủi lên tới khoảng 30%.

Trang nay dùng ngưỡng họ 7/α = 140, cũng là ngưỡng cổng live của nhánh ML (`build_vietlott_results`):

- `family_signal` quyết định huy hiệu "Có tín hiệu thống kê";
- `randomness_summary` in câu kết luận chung;
- `evidence_text` và `verdict_text` in câu cho từng sản phẩm.

Sản phẩm vượt 20 nhưng chưa tới 140 được ghi rõ là chưa đủ bằng chứng khi xét cả họ. Max 3D (10^2,57)
và Max 3D Pro (10^2,84) vượt cả 140 (10^2,15), nên kết luận hôm nay không đổi.

## 5. Phép kiểm phụ thuộc giờ máy — đã sửa

`test_rejected_source_row_cannot_be_hidden_by_a_valid_cached_row[future]` đỏ lúc 22:29 UTC.

- Engine xét dòng "tương lai" theo ngày Việt Nam (`datetime.now(VN)`).
- Phép kiểm dựng ngày tương lai bằng `date.today()` của máy (UTC).
- Từ 17:00 đến 24:00 UTC, "ngày mai UTC" là "hôm nay VN". Dòng ấy hợp lệ, engine đúng khi nhận nó, và
  phép kiểm đỏ.

Nay phép kiểm dựng ngày tương lai từ ngày VN. Bản cũ đỏ trong khung giờ ấy, bản mới xanh.

## Phép kiểm và đột biến

| Tệp | Đột biến |
|---|---|
| `vietlott/tests/test_vlm_bayes_expert.py` | 6/6 đỏ: không học; dự báo đều; tốc độ chia sẻ khác engine cũ; nạp checkpoint chữ số đời cũ; bỏ kiểm số kỳ; chặn đời cũ cho cả bộ số |
| `vietlott/tests/test_vlm_coverage.py` (3 phép kiểm `coverage-v2`) | 5/5 đỏ: chấm bằng số đầu; mốc giả định chung một số; không áp v2; áp v2 cho bản ghi v1; nhãn quy tắc sai |
| `tests/pages/test_vietlott_results.py` | 8/8 đỏ: ngưỡng họ (4) và hiển thị v2 (4) |

Phép kiểm đáng chú ý:

- Chuyên gia mới khớp tới 10⁻⁶ luật hậu nghiệm của engine cũ trên cùng lịch sử.
- Mốc "ít nhất một vé trúng giải" khớp vét cạn toàn bộ 324 632 × 12 kết quả, chấm bằng chính bảng giải.
