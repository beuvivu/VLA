# Rà soát từng thành phần của tổ hợp xác suất LOTO / Đặc Biệt

Ngày: 04-10-2026. Dữ liệu: 4 225 kỳ, 01-01-2015 → 04-10-2026.
Tái lập (≈ 35 phút, 4 lõi):

    PYTHONPATH=src python3 scripts/benchmark_component_trust.py --last 1000

Số liệu thô: `data/research/model_overhaul/component_trust.json`.

## Tóm tắt

Câu hỏi: làm sao để xác suất "con lô, con đề về ngày mai" tốt hơn. Câu trả lời trung thực có hai
phần.

1. **Không công thức nào làm số "về" được.** Kiểm toán 03-10-2026 đã đo: tần suất đồng nhất qua
   mọi giai đoạn, và không mô hình nào — kể cả mô hình ba tầng mới có công cụ đo bắt được tín hiệu
   cài sẵn — hơn dự báo hằng số trên 1 000 kỳ. Rà soát này không thay đổi kết luận ấy.
2. **Nhưng tổ hợp đang công bố KÉM dự báo hằng số, và phần kém ấy sửa được.** Kiểm toán trước chấm
   từng MÔ HÌNH; lần này chấm từng THÀNH PHẦN của tổ hợp production và chính phép trộn. Tìm ra hai
   lỗi, cả hai đều làm xác suất tệ hơn việc không dự đoán gì:
   - **Mức LOTO sai.** Hai nhánh cầu vị trí (active/stable, trọng số 0,125 mỗi nhánh) có tổng xác
     suất trung vị 24,49 và 26,47 con mỗi kỳ, trong khi số con khác nhau thật sự về chỉ có kỳ vọng
     23,77. Tổ hợp trọng số mặc định vì thế tổng 24,22 và kém hằng số **z = −3,33**.
   - **Cầu-kèo không co về nền khi không có kỹ năng.** Thành phần nặng nhất (0,30) phát xác suất thô
     của cây tăng cường; xác suất Đặc Biệt thô kém hằng số **z = −2,18**. Thành phần ML đã có luật
     "không có kỹ năng thì không tin" từ 03-10; cầu-kèo thì chưa.

Sau hai sửa chữa, tổ hợp mô phỏng trên 1 000 kỳ: **LOTO hơn bản hiện hành z = +3,23**, Đặc Biệt
z = +1,77; so với hằng số còn LOTO z = +0,69, Đặc Biệt z = −0,31 — tức về đúng mức tốt nhất có thể
đạt được trên một trò chơi ngẫu nhiên.

## 1. Chẩn đoán: chấm từng thành phần

### 1.1 Trên các kỳ đã ghi (01-09 → 04-10-2026, 34 kỳ)

`data/history/pred_<mode>.csv` ghi vector của từng thành phần trước kỳ quay. Kỹ năng logloss so với
hằng số (âm = tệ hơn không dự đoán):

| Thành phần | LOTO | z | Đặc Biệt | z |
|---|---:|---:|---:|---:|
| ML | −0,023% | −1,76 | +0,158% | +1,04 |
| Cầu-kèo | −0,029% | −1,21 | +0,259% | +2,24 |
| Thống kê | −0,075% | −1,23 | −0,887% | −1,55 |
| Cầu đang chạy (active) | +0,014% | +0,67 | −0,001% | −1,92 |
| Cầu ổn định (stable) | −0,100% | **−2,69** | +0,166% | +0,82 |

34 kỳ quá ngắn để kết luận, nhưng đủ để chỉ chỗ cần đo kỹ. Thống kê Đặc Biệt kém vì nửa đầu tháng 9
nó còn nhọn (xác suất cao nhất tới 0,0233); từ 14-09-2026 nó học độ co ngót và về sát 1/100, nên
không cần sửa thêm. Hai chỗ còn lại — mức của cầu vị trí và cầu-kèo không có trust — được đo lại
trên 1 000 kỳ.

### 1.2 Walk-forward 1 000 kỳ (kỳ đích 25-12-2023 → 04-10-2026)

Cầu vị trí dựng lại mỗi kỳ bằng đúng tham số của pipeline. Cầu-kèo học lại mỗi 50 kỳ bằng chính
`cau_keo_ml._train_model` (cùng khối thời gian, cùng siêu tham số, cùng seed). Kỳ ngay sau Tết bị
loại. Mốc: tỉ lệ nền tích luỹ (LOTO) và 1/100 (Đặc Biệt).

**LOTO**

| Thành phần | Tổng xác suất (trung vị) | So với hằng số |
|---|---:|---:|
| Cầu đang chạy | 24,49 | z = −5,44 |
| Cầu ổn định | **26,47** | **z = −27,34** |
| Cầu đang chạy, neo mức | 23,77 | z = −0,06 |
| Cầu ổn định, neo mức | 23,77 | z = −0,03 |
| Cầu-kèo thô | 23,84 | z = +0,03 |

Toàn bộ phần thua của cầu vị trí nằm ở MỨC: neo tổng về 23,77 xong, cả hai nhánh về ngang hằng số.
Nguồn của sai mức là lời nguyền người thắng: `path_prob` chọn 300 quy tắc tốt nhất mỗi độ trễ trong
khoảng 5 600, nên tỉ lệ trúng trong mẫu của quy tắc được giữ cao hơn tỉ lệ thật. Phép co
`selection_shrinkage_strength` có làm nhỏ độ lệch nhưng không đủ.

**Đặc Biệt**

| Thành phần | So với hằng số |
|---|---:|
| Cầu-kèo thô | **z = −2,18** (nửa đầu −0,80, nửa sau −2,03) |
| Cầu-kèo co theo kỹ năng | z = −0,45 |
| Cầu đang chạy | z = +0,49 |
| Cầu ổn định | z = −0,89 |

Kỹ năng thẩm định của cầu-kèo dương ở khoảng một nửa số lần học, nhưng luôn rất nhỏ: trust trung
bình 0,0007 (LOTO) và 0,0001 (Đặc Biệt). Tức là luật tin gần như luôn trả về tỉ lệ nền — đúng với
những gì dữ liệu nói.

## 2. Hai sửa chữa

### 2.1 Neo mức LOTO của tổ hợp

`ensemble_utils.anchor_loto_level`: nhân mọi số với cùng một hệ số để `Σp = 100·(1 − 0,99²⁷)`.
Đó là số con khác nhau kỳ vọng mỗi kỳ, suy thẳng từ luật 27 giải; 4 225 kỳ lịch sử đo 23,83 ± 0,02
(chênh 0,3%, tác động lên logloss dưới 10⁻⁶ nats mỗi số). Đặc Biệt đã có ràng buộc cùng loại là tổng
bằng 1; LOTO thì chưa.

Phép nhân giữ nguyên thứ hạng, nên danh sách gợi ý không đổi vì riêng phép này. Nó đi vào
`ensemble_utils.finalize_blend`, nay là phép chốt DUY NHẤT trước hiệu chỉnh cho cả năm nơi chấm vector
tổ hợp: đường dự đoán thật, bộ học trọng số và hiệu chỉnh, tầng xếp chồng, trang Chất lượng, bảng
đóng góp thành phần. Trước đây năm nơi ấy tự chép `floor_distribution`/`clip01`.

### 2.2 Độ tin của cầu-kèo

Cùng luật với ML: `prob = trust·thô + (1 − trust)·nền`, `trust = clip(20·s, 0, 1)`, s là kỹ năng
(kém hơn trong logloss/Brier) so với tỉ lệ nền trên khối thẩm định 60 kỳ chưa dùng để học. Trust và
nền lưu trong gói mô hình; `trust_from_pack` không có giá trị mặc định, nên gói cũ (trước luật này)
bị học lại chứ không bị đọc thành trust = 1. `ml_prob_raw` giữ xác suất thô cho điểm cầu-kèo và cột
«Bằng chứng», nên thứ hạng trên trang Thống kê không đổi. `validate_cau_keo_domain` canh `prob` đúng
bằng bản đã co, với đúng trust trong gói.

## 3. Kết quả trên tổ hợp

Tổ hợp mô phỏng với trọng số mặc định; ML và thống kê lấy đúng tỉ lệ nền (trust của ML bằng 0 ở gần
như mọi lần học theo walk-forward 03-10; thống kê co hoàn toàn từ 14-09). Không hiệu chỉnh, không
xếp chồng — cả hai đang tắt trong production.

| | LOTO | Đặc Biệt |
|---|---:|---:|
| Hiện hành so với hằng số | z = −3,33 | z = −1,72 |
| **Mới so với hằng số** | **z = +0,69** | **z = −0,31** |
| **Mới so với hiện hành** | **z = +3,23** (nửa +2,52 / +2,03) | **z = +1,77** (nửa +0,67 / +1,64) |
| Chỉ neo mức, so với hiện hành | z = +4,24 (nửa +3,11 / +2,87) | không áp cho Đặc Biệt |
| Độ tin cầu-kèo khi đã neo | z = −1,65 (nửa −0,90 / −1,50) | z = +1,77 |

Luật quyết định chốt TRƯỚC khi đo, cùng luật với lần bỏ sàn `model_trust`: đổi khi bản mới không kém
bản hiện hành ở cả hai chế độ, thắng z ≥ 2 ở ít nhất một, và không kém hằng số có ý nghĩa thống kê.
Đạt: LOTO z = +3,23, Đặc Biệt z = +1,77; so với hằng số +0,69 và −0,31.

Tách riêng hai sửa chữa: toàn bộ phần thắng ở LOTO đến từ neo mức. Độ tin cầu-kèo ở LOTO, khi đã
neo, cho ước lượng điểm ÂM: −0,0000087 nats mỗi kỳ, z = −1,65, cả hai nửa cùng dấu. Không có ý nghĩa
thống kê, nhưng nhất quán, nên ghi ra thay vì bỏ qua. Một mình, xác suất thô của cầu-kèo LOTO ngang
hằng số (z = +0,03) và bản co ngang bản thô (z = −0,02); phần chênh chỉ xuất hiện khi trộn với cầu vị
trí.

Vẫn giữ MỘT luật cho cả hai chế độ, và đây là lựa chọn có cân nhắc, không phải hệ quả của số đo:
- Ứng viên được chốt TRƯỚC khi đo tổ hợp là "cả hai sửa chữa", và nó qua luật quyết định. Chọn biến
  thể "chỉ neo cho LOTO" SAU khi thấy nó cao hơn là đúng kiểu chọn sau khi đọc kết quả mà kiểm toán
  03-10 đã cảnh báo (Top-5 Đặc Biệt 7,0%).
- Trên một trò chơi công bằng, kỳ vọng thật của mọi dự báo khác hằng số là không hơn hằng số. Biến
  thể chỉ neo hơn hằng số z = +1,76 nhờ xác suất thô của cầu-kèo — một mô hình không có kỹ năng thẩm
  định — nên phần hơn ấy nhiều khả năng là may.
- Ở Đặc Biệt luật này sửa một khoản thua có thật (z = +2,18 so với bản thô), cùng tinh thần với
  `ml_train.model_trust` và `meta_trust`: không có kỹ năng thì không tin.

Bộ theo dõi `skill_monitor` vẫn canh kỹ năng ngoài mẫu của vector đã công bố theo cả hai hướng.

## 4. Điều thay đổi với người đọc trang

- Tổng xác suất LOTO đã công bố bằng 23,77 con (khi hiệu chỉnh là phép đồng nhất và tầng xếp chồng
  tắt, như hiện nay); tháng 9 nó dao động 23,2–24,4.
- Cột xác suất cầu-kèo nay gần như bằng nhau cho mọi số (trust ≈ 0). Điểm cầu-kèo và thứ hạng của nó
  không đổi vì vẫn đọc xác suất thô.
- Danh sách gợi ý của tổ hợp: khi cả ML lẫn cầu-kèo đều phát tỉ lệ nền, thứ tự do hai nhánh cầu vị
  trí và thống kê quyết định. Không nhánh nào trong số đó có kỹ năng đo được, nên danh sách vẫn chỉ
  là thứ tự, không phải lợi thế.

## 5. Chưa làm

- **Mức của từng nhánh cầu vị trí.** Trang soi cầu vẫn in xác suất của nhánh trước khi neo (tổng
  24,5–26,5). Neo ở tổ hợp đã sửa thứ được công bố và chấm điểm; sửa tận gốc ở `path_prob` đổi nhiều
  trang và phép kiểm nên để thành việc riêng.
- **Học trực tuyến** (`online_learning`, đang chạy bóng) cần 60 kỳ đã chốt trước khi cổng của nó được
  phép quyết định; hôm nay mới có 7.
- **Mô hình xếp chồng** vẫn tắt vì chưa đủ 100 kỳ lịch sử đủ năm thành phần.

## 6. Kiểm thử

`tests/test_loto_level_anchor.py` (9 phép) và `tests/test_cau_keo_ml.py` (thêm 5 phép), cùng bốn
phép cũ được viết lại: ba phép chấm vector LOTO đồng đều — dạng mà phép neo làm mất khả năng phân
biệt trọng số — và bản tham chiếu điểm theo ngày của bộ học trọng số. 16 đột biến đều làm đỏ: bỏ
neo, hàng rỗng nhận 0, `finalize_blend` quay về `clip01`, từng nơi trong năm nơi chấm quay về bản
chép riêng; bỏ trust, Đặc Biệt không chuẩn hoá lại, trust mặc định cho gói cũ, nền nhìn khối thẩm
định, trust = 1, dùng lại gói cũ không học lại, `prob` = xác suất thô.
