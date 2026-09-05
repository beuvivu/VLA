# Danh mục phương pháp phân tích xổ số Việt Nam

Xác minh lần cuối: 2026-09-03

Danh mục này ghi nhận hành vi công khai, không mô tả chi tiết triển khai độc
quyền. Trừ khi ghi khác, mọi phương pháp tương đương trong VLA đều là **bản
triển khai độc lập dựa trên hành vi quan sát được công khai**. Quảng cáo không
được coi là bằng chứng dự báo. Mẫu lịch sử không bảo đảm kết quả tương lai.

## Tần suất

**Tên gọi khác:** tần suất lô tô, số lần về.

**Nguồn:** https://mketqua.net/tan-suat-loto;
https://xosodaiphat.com/thong-ke-tan-suat-loto.html;
https://www.minhngoc.net.vn/thong-ke-xo-so/tan-suat-tinh.html

**Loại:** mô tả.

**Đầu vào:** số lần xuất hiện 00..99 theo ngày.

**Định nghĩa toán học:** số lần xuất hiện là `Σ_t count_t(x)`; số kỳ có mặt là
`Σ_t 1[count_t(x)>0]`; tỷ lệ ngày về bằng số kỳ có mặt chia số kỳ hợp lệ.

**Tham số:** cửa sổ theo ngày lịch hoặc số kỳ; ngày chốt.

**Đầu ra:** số lần xuất hiện, số kỳ, tỷ lệ ngày, bội số lớn nhất, số lần đúng
hai nháy và ít nhất hai nháy.

**Trường hợp biên:** cửa sổ rỗng, ngày trùng, thiếu cột số, một số về nhiều lần.

**Rủi ro rò rỉ:** trung bình nếu ngày mục tiêu lọt vào cửa sổ; VLA chỉ dùng ngày
nhỏ hơn ngày chốt.

**Tương đương trong VLA:** `frequency_stats.compute_frequency_stats`;
`advanced_stats.compute_frequency` là lớp tương thích.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** cao.
**Bằng chứng dự báo:** chưa kiểm định.

## Lô gan

**Tên gọi khác:** gan, lô khan, số lâu chưa về.

**Nguồn:** https://mketqua.net/loto-gan; https://rongbachkim.net/thongke.html;
https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html

**Loại:** mô tả. **Đầu vào:** trạng thái có mặt của 00..99 theo ngày.

**Định nghĩa toán học:** `gap(x,D)` là số kỳ hợp lệ đã hoàn tất sau lần về gần
nhất và nằm hoàn toàn trước `D`; khoảng vắng theo lịch là `(D-last_hit).days-1`.

**Tham số:** ngày chốt; cửa sổ lịch/số kỳ tùy chọn.

**Đầu ra:** gan theo kỳ/lịch, lần về cuối, gan lịch sử, phân vị, điểm Z.

**Trường hợp biên:** chưa từng về, chỉ về một lần, phương sai 0, thiếu ngày lịch.

**Rủi ro rò rỉ:** trung bình nếu chứa kết quả mục tiêu.

**Tương đương trong VLA:** `gap_cycle_stats.compute_gap_stats`;
`cycle_stats._gap_series_calendar` cũ.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** cao.
**Bằng chứng dự báo:** bác bỏ quy tắc tự động “đến hạn”; gan dài không tự làm
tăng xác suất tương lai.

## Chu kỳ / tái xuất hiện

**Tên gọi khác:** chu kỳ, nhịp, khoảng lặp.

**Nguồn:** https://hainhay.net/chu-ky;
https://xosodaiphat.com/thong-ke-chu-ky-loto.html

**Loại:** mô tả. **Đầu vào:** ngày/chỉ số các lần về theo thứ tự.

**Định nghĩa toán học:** với `i_1,...,i_n`, chu kỳ là
`g_k=i_k-i_(k-1)` và số kỳ vắng hoàn tất là `g_k-1`.

**Tham số:** cửa sổ và số khoảng gần đây để tính xu hướng.

**Đầu ra:** trung bình, trung vị, phương sai, tứ phân vị, lớn nhất, độ dốc gần
đây và khoảng kiểm duyệt phải.

**Trường hợp biên:** dưới hai lần về, lịch không đều, khoảng hiện tại chưa hoàn tất.

**Rủi ro rò rỉ:** thấp khi có ngày chốt nghiêm ngặt.

**Tương đương trong VLA:** `gap_cycle_stats.compute_recurrence_intervals`,
`compute_gap_stats`; `cycle_stats.build_cycle_tables` cũ.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** cao.
**Bằng chứng dự báo:** chưa kiểm định.

## Đầu / đuôi / tổng / chạm

**Tên gọi khác:** hàng chục, hàng đơn vị, tổng đề, tổng modulo 10.

**Nguồn:** https://mketqua.net/; https://xosodaiphat.com/;
https://hainhay.net/chu-ky-db

**Loại:** mô tả. **Đầu vào:** số `10a+b` hoặc lịch sử xuất hiện.

**Định nghĩa toán học:** đầu=`a`; đuôi=`b`; tổng thô=`a+b`; tổng modulo
10=`(a+b) mod 10`; chạm `d` chứa số có `a=d hoặc b=d`.

**Tham số:** loại nhóm và cửa sổ. **Đầu ra:** thành viên, số lần/kỳ, tỷ lệ, gan nhóm.

**Trường hợp biên:** `00`, `99`; chạm có 19 số; tổng thô 0..18 khác tổng modulo 10.

**Rủi ro rò rỉ:** thấp với ngày chốt nghiêm ngặt.

**Tương đương trong VLA:** `number_reference`,
`frequency_stats.compute_group_frequency_stats`,
`gap_cycle_stats.compute_group_gap_stats`.

**Trạng thái triển khai:** hiện hữu. **Độ tin cậy nghiên cứu:** cao.
**Bằng chứng dự báo:** chưa kiểm định.

## Tần suất cặp cùng kỳ

**Tên gọi khác:** cặp cùng về, đồng xuất hiện, lịch sử lô xiên.

**Nguồn:** https://xosodaiphat.com/thong-ke-lo-xien.html;
https://mketqua.net/tan-suat-cap-loto

**Loại:** mô tả. **Đầu vào:** tập số lô tô duy nhất của từng kỳ.

**Định nghĩa toán học:** `cooccur(i,j)=Σ_t 1[i∈draw_t và j∈draw_t]`;
`support=cooccur/N`.

**Tham số:** cửa sổ, hỗ trợ tối thiểu, số dòng đầu ra.

**Đầu ra:** số đếm thô, hỗ trợ, biên, độ nâng, ngày gần đây.

**Trường hợp biên:** một số về nhiều lần không phải cặp; cặp không thứ tự loại `i=j`.

**Rủi ro rò rỉ:** cao nếu bảng toàn lịch sử được tái dùng cho kiểm định quá khứ.

**Tương đương trong VLA:** `pair_stats.compute_pair_frequency`,
`descriptive_extensions.build_pair_recency`,
`conditional_matrices.build_cooccurrence_matrix`.

**Trạng thái triển khai:** hiện hữu. **Độ tin cậy nghiên cứu:** cao.
**Bằng chứng dự báo:** chưa kiểm định.

## Lộn và cặp lô tô 50

**Tên gọi khác:** đảo, AB-BA, cặp 50, kép-bóng.

**Nguồn:** https://xosodaiphat.com/thong-ke-tan-suat-loto-cap.html;
[`../domain/number-ontology.md`](../domain/number-ontology.md)

**Loại:** mô tả. **Đầu vào:** một số hai chữ số.

**Định nghĩa toán học:** lộn `AB→BA`. Phân hoạch 50 cặp gồm 45 cặp đảo không
kép và `00-55`, `11-66`, `22-77`, `33-88`, `44-99`.

**Tham số:** không có. **Đầu ra:** số đảo, định danh cặp, loại cặp.

**Trường hợp biên:** số kép tự đảo và ghép với số kép bóng dương trong cặp 50.

**Rủi ro rò rỉ:** không có với ánh xạ tất định.

**Tương đương trong VLA:** `number_reference.reverse`,
`cap_loto_50_partner`, `all_cap_loto_50`; `cap_loto_50_stats.build_stats`.

**Trạng thái triển khai:** hiện hữu. **Độ tin cậy nghiên cứu:** cao.
**Bằng chứng dự báo:** quan hệ chỉ là đặc trưng thử nghiệm.

## Bộ và bóng

**Tên gọi khác:** bộ/hệ, bóng dương, bóng âm.

**Nguồn:** nhiều mô tả công khai được đối chiếu tại
[`../domain/number-ontology.md`](../domain/number-ontology.md).

**Loại:** mô tả. **Đầu vào:** chữ số hoặc số hai chữ số.

**Định nghĩa toán học:** bóng dương `0↔5,1↔6,2↔7,3↔8,4↔9`; bộ VLA là quỹ
đạo sinh bởi bóng dương theo chữ số và phép đảo, gồm mười họ 8 số và năm họ 4 số.

**Tham số:** quy ước ánh xạ đã công bố. **Đầu ra:** phép biến đổi, mã họ, thành viên.

**Trường hợp biên:** thuật ngữ khác nhau giữa nguồn; VLA không gọi bù 9 là bóng.

**Rủi ro rò rỉ:** không với ánh xạ; trung bình nếu chọn họ theo kết quả mục tiêu.

**Tương đương trong VLA:** `number_reference.bo`, `bong_duong`, `bong_am`.

**Trạng thái triển khai:** hiện hữu. **Độ tin cậy nghiên cứu:** trung bình cho
thuật ngữ, cao cho quy tắc VLA. **Bằng chứng dự báo:** không tự động có.

## Cầu vị trí động

**Tên gọi khác:** cầu lô tô chạy N ngày, ghép vị trí, bạch thủ, cầu đặc biệt.

**Nguồn:** https://mketqua.net/cau-loto;
https://mketqua.net/cau-bach-thu; https://hainhay.net/cau-loto

**Loại:** khai phá mẫu. **Đầu vào:** vị trí giải/kết quả/chữ số ngữ nghĩa từ
kỳ `t-1` và mục tiêu kỳ `t`.

**Định nghĩa toán học:** chọn chữ số nguồn rồi ghép, ghép đảo, tạo cặp đảo hoặc
bộ. Chuỗi đang chạy là dãy ngày lịch liên tiếp mới nhất thỏa tiêu chí mục tiêu.

**Tham số:** vị trí, phép biến đổi, mục tiêu, chuỗi/hỗ trợ tối thiểu, trần giả thuyết.

**Đầu ra:** mã mẫu, ứng viên kế tiếp, chuỗi hiện tại/dài nhất, hỗ trợ, trúng/
trượt, độ tin cậy, độ phủ, ngày trúng gần đây và số lượng giả thuyết.

**Trường hợp biên:** thiếu ngày làm đứt chuỗi; ngày trùng bị từ chối; mẫu 1/1 yếu.

**Rủi ro rò rỉ:** cao; chọn và báo cáo cùng giai đoạn gắn
`PATTERN_SELECTION_BIAS_RISK`.

**Tương đương trong VLA:** `dynamic_cau.find_running_patterns`;
`crosslag_positional_lab.evaluate_lab` chuyên biệt cũ.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** trung bình
vì cách liệt kê/xếp hạng của nguồn là độc quyền. **Bằng chứng dự báo:** chưa kiểm định.

## Cầu hai nháy

**Tên gọi khác:** cầu ăn hai nháy.

**Nguồn:** https://mketqua.net/cau-hai-nhay;
https://hainhay.net/cau-loto-2-nhay; https://rongbachkim.net/thongke.html

**Loại:** giả thuyết dự báo. **Đầu vào:** ứng viên vị trí và số lần xuất hiện
của từng số trong kỳ mục tiêu.

**Định nghĩa toán học:** VLA dùng `max_x count_t(x)>=2` cho từng `x` được dự
báo riêng; không gộp số lần của các ứng viên khác nhau.

**Tham số:** quy tắc, độ dài chuỗi, hỗ trợ tối thiểu.

**Đầu ra:** số lần trúng thường/hai nháy và biểu đồ số lần chính xác.

**Trường hợp biên:** đúng hai khác ít nhất hai; hai số mỗi số một nháy không
tạo thành hai nháy.

**Rủi ro rò rỉ:** cao khi tìm mẫu.

**Tương đương trong VLA:** `dynamic_cau.evaluate_pattern(target_type="loto_2_nhay")`;
mô tả `advanced_stats.compute_daily_nhay_stats`.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** trung bình.
**Bằng chứng dự báo:** chưa kiểm định.

## Cầu vị trí giải đặc biệt

**Tên gọi khác:** cầu đề, cầu ĐB, bạch thủ đề.

**Nguồn:** https://mketqua.net/cau-giai-dac-biet;
https://hainhay.net/cau-dac-biet

**Loại:** giả thuyết dự báo. **Đầu vào:** vị trí chữ số trước đó và hai số cuối
ĐB kế tiếp.

**Định nghĩa toán học:** thành công khi `1[tập dự báo chứa special_t mod 100]`.

**Tham số:** vị trí, phép biến đổi, ngưỡng chuỗi/hỗ trợ.

**Đầu ra:** bằng chứng mẫu và tập ứng viên tất định kế tiếp.

**Trường hợp biên:** giải ĐB đầy đủ và hai số cuối là hai mục tiêu khác nhau.

**Rủi ro rò rỉ:** cao.

**Tương đương trong VLA:** `dynamic_cau.evaluate_pattern(target_type="special")`;
`crosslag_positional_lab` chỉ nghiên cứu.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** trung bình.
**Bằng chứng dự báo:** chưa kiểm định.

## Ma trận điều kiện và chuyển tiếp

**Tên gọi khác:** lô tô theo lô tô, lô tô theo ĐB, ma trận ngày kế.

**Nguồn:** https://mketqua.net/; https://hainhay.net/chu-ky

**Loại:** khai phá mẫu. **Đầu vào:** trạng thái nguồn theo ngày và trạng thái
đích đúng ngày lịch kế tiếp.

**Định nghĩa toán học:** `count(i,j)=Σ_t 1[i_t và j_(t+1)]`;
`confidence=count/source_count`; `support=count/N`; `lift=confidence/P(j)`;
làm trơn Beta đa nhãn `(count+alpha)/(source_count+2alpha)`.

**Tham số:** ngày chốt nghiêm ngặt, `alpha`.

**Đầu ra:** số đếm thô, hỗ trợ biên, độ tin cậy, tỷ lệ làm trơn, độ nâng.

**Trường hợp biên:** bỏ qua ngày thiếu; hàng lô tô đa nhãn không cần tổng bằng một.

**Rủi ro rò rỉ:** cao nếu khớp bằng chuyển tiếp tương lai.

**Tương đương trong VLA:** `conditional_matrices.build_transition_matrix`,
`conditional_nextday`, `number_dynamics.transition_posterior`.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** cao.
**Bằng chứng dự báo:** chưa kết luận; chỉ nghiên cứu/thử nghiệm.

## Luật kết hợp

**Tên gọi khác:** A→B, quy tắc cặp có điều kiện.

**Nguồn:** công thức thống kê chuẩn áp dụng độc lập cho tính năng cặp/điều kiện công khai.

**Loại:** khai phá mẫu. **Đầu vào:** tập hiện diện cùng kỳ hoặc đúng ngày kế tiếp.

**Định nghĩa toán học:** `support=count(A∩B)/N`;
`confidence=count(A∩B)/count(A)`; `lift=confidence/P(B)`.

**Tham số:** độ trễ 0/1, hỗ trợ/độ tin cậy/độ nâng và số quan sát nguồn tối
thiểu, `alpha`.

**Đầu ra:** số đếm, chỉ số và cận dưới Wilson.

**Trường hợp biên:** nguồn hiếm, mẫu nhỏ hoàn hảo, có hướng/không thứ tự.

**Rủi ro rò rỉ:** cao khi chọn và đánh giá trên cùng giai đoạn.

**Tương đương trong VLA:** `association_rules.mine_association_rules`.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** cao cho
toán học. **Bằng chứng dự báo:** chưa kiểm định.

## Chuỗi Markov bậc một

**Tên gọi khác:** chuyển tiếp Markov.

**Nguồn:** định nghĩa thống kê chuẩn; không nhận là mô hình độc quyền của nguồn nào.

**Loại:** giả thuyết dự báo. **Đầu vào:** chuỗi trạng thái loại trừ theo thứ tự.

**Định nghĩa toán học:**
`P_ij=(count(i→j)+alpha)/(Σ_k count(i→k)+alpha|S|)`.

**Tham số:** không gian trạng thái, `alpha`.

**Đầu ra:** số đếm, hỗ trợ đi ra, xác suất từng hàng có tổng một.

**Trường hợp biên:** trạng thái chưa thấy, `alpha=0`, lô tô đa nhãn cần mô
hình Bernoulli thay thế.

**Rủi ro rò rỉ:** cao nếu ngày kiểm thử lọt vào ma trận.

**Tương đương trong VLA:** `markov_stats.build_markov_chain`;
`compute_markov_for_loto`; nghiên cứu bậc hai giới hạn trong `number_dynamics`.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** cao cho
toán học. **Bằng chứng dự báo:** chưa kết luận; phải vượt nền biên/cuốn chiếu ngoài mẫu.

## Chấm điểm ứng viên / chỉ số nổ

**Tên gọi khác:** điểm, điểm tổng hợp, chỉ số nổ.

**Nguồn:** tái dựng tổng quát từ màn hình nhiều chỉ báo công khai; không tuyên
bố sao chép công thức độc quyền.

**Loại:** giả thuyết dự báo. **Đầu vào:** tần suất, gan, độ gần, EMA, chu kỳ và
điểm điều kiện/mẫu tùy chọn, tất cả chỉ từ lịch sử nghiêm ngặt.

**Định nghĩa toán học:** trung bình có trọng số của thành phần chuẩn hóa;
`alpha=2/(span+1)` và `EMA_t=alpha*y_t+(1-alpha)*EMA_(t-1)`.

**Tham số:** cửa sổ, `span`, khởi tạo/lịch sử EMA tối thiểu, trọng số rõ ràng.

**Đầu ra:** `CandidateScore` gồm điểm, thành phần, bằng chứng, giải thích, nguồn gốc.

**Trường hợp biên:** thành phần tùy chọn thiếu được công bố và loại khỏi mẫu
số; lịch sử thiếu trả 0.

**Rủi ro rò rỉ:** trung bình; mọi đầu vào phải tôn trọng ngày chốt.

**Tương đương trong VLA:** `candidate_scoring.rank_candidates`;
`cau_keo_ml._add_ai_judgement` vận hành vẫn độc lập.

**Trạng thái triển khai:** đã triển khai. **Độ tin cậy nghiên cứu:** cao cho
công thức VLA, thấp cho tính tương đương nguồn. **Bằng chứng dự báo:** chưa kiểm
định; điểm không phải xác suất đã hiệu chỉnh.

## Phép biến đổi kiểu Pascal

**Tên gọi khác:** cầu Pascal, tam giác Pascal xổ số.

**Nguồn:** https://caulo100.com/soi-cau-pascal-cau-lo-100;
https://soicauvn247.com/soi-cau-pascal

**Loại:** giả thuyết dự báo. **Đầu vào:** chuỗi chữ số hạt giống do bên ngoài chọn.

**Định nghĩa toán học:** `r_(k+1,j)=(r_(k,j)+r_(k,j+1)) mod 10`; cách chọn hạt
giống và trích ứng viên chưa đủ đặc tả.

**Tham số:** hạt giống, độ sâu, quy tắc trích. **Đầu ra:** tam giác tất định.

**Trường hợp biên:** độ tin cậy quảng cáo không có phương pháp hiệu chỉnh công khai.

**Rủi ro rò rỉ:** cao nếu chọn hạt giống/quy tắc sau khi nhìn kết quả.

**Tương đương trong VLA:** chưa có. **Trạng thái triển khai:** bác bỏ.
**Độ tin cậy nghiên cứu:** trung bình cho truy hồi, thấp cho cách trích.
**Bằng chứng dự báo:** bác bỏ cho tới khi có ánh xạ tái lập được.

## Phép biến đổi kiểu Fibonacci

**Tên gọi khác:** cầu Fibonacci.

**Nguồn:** chưa tìm thấy mô tả ánh xạ xổ số Việt Nam ổn định và đủ chi tiết.

**Loại:** giả thuyết dự báo. **Đầu vào/đầu ra:** chưa xác định.

**Định nghĩa toán học:** chỉ `F_0=0`, `F_1=1`,
`F_n=F_(n-1)+F_(n-2)` là không mơ hồ; chưa có ánh xạ lịch sử→ứng viên.

**Tham số:** chưa xác định. **Trường hợp biên:** tự phát minh ánh xạ sẽ là bịa
đặt phương pháp bên ngoài.

**Rủi ro rò rỉ:** cao nếu hồi cứu quy tắc.

**Tương đương trong VLA:** chưa có. **Trạng thái triển khai:** bác bỏ.
**Độ tin cậy nghiên cứu:** thấp. **Bằng chứng dự báo:** bác bỏ vì thiếu đặc tả.

## Phân tích đồ thị

**Tên gọi khác:** đồ thị số, mạng đồng xuất hiện.

**Nguồn:** thuật toán đồ thị chuẩn áp dụng cho ma trận trên; không tuyên bố
tương đương nguồn độc quyền.

**Loại:** khai phá mẫu. **Đầu vào:** ma trận đồng xuất hiện, chuyển tiếp hoặc độ nâng.

**Định nghĩa toán học:** nút là 00..99; cạnh có trọng số đã công bố dùng cho
bậc có trọng số, PageRank, cộng đồng hoặc độ trung tâm.

**Tham số:** chỉ số/ngưỡng/hướng cạnh và thuật toán đồ thị.

**Đầu ra:** tóm tắt nút/cạnh mô tả.

**Trường hợp biên:** nền cạnh dày và độ nhạy với ngưỡng.

**Rủi ro rò rỉ:** cao nếu đồ thị dùng toàn bộ tương lai để tạo đặc trưng quá khứ.

**Tương đương trong VLA:** chưa có; đầu vào ma trận chuẩn đã tồn tại.

**Trạng thái triển khai:** dự kiến. **Độ tin cậy nghiên cứu:** cao cho toán đồ
thị, thấp cho giá trị dự báo. **Bằng chứng dự báo:** chưa kiểm định.
