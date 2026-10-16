# Trần dự báo của XSMB và suy luận cầu theo Bayes thực nghiệm (16-10-2026)

## Yêu cầu

> Tăng tính phỏng đoán và thông minh khi suy luận cầu kèo và xác suất cho toàn hệ thống lên mức
> cao nhất có thể.

"Mức cao nhất có thể" do **dữ liệu** quyết định chứ không do mô hình. Nếu các kỳ quay độc lập và
đều, mọi dự báo khác hằng số đều có logloss kỳ vọng kém hơn hằng số. Khi ấy trần là chính hằng số,
và "thông minh" nghĩa là hai việc:

- không để nhiễu đẩy xác suất ra xa trần;
- nhận ra ngay khi dữ liệu có cấu trúc thật để học.

Tài liệu này làm ba việc:

1. Đo xem dữ liệu có cấu trúc nào để học không.
2. Đặt kỹ năng đã công bố của hệ thống cạnh trần ấy.
3. Sửa chỗ cuối cùng trong chuỗi xác suất còn suy luận sai cách: cầu vị trí (`path_prob`).

## 1. Trần dự báo: dữ liệu có cấu trúc nào để học không?

Tái lập bằng `PYTHONPATH=src python3 scripts/research/audit_forecast_ceiling.py`. Số liệu thô nằm
ở `data/research/model_overhaul/forecast_ceiling.json`. Dữ liệu gồm 4 236 kỳ, từ 01-01-2015 đến
15-10-2026.

| Dạng cấu trúc có thể có thật | Phép thử | Kết quả |
|---|---|---|
| Bi hoặc lồng lệch chữ số theo vị trí | Lệch của 54 (giải × hàng chục/đơn vị) ở nửa đầu so với nửa sau | Tương quan +0,03 ± 0,05; số phép p < 0,01 là 0 (nửa đầu) và 1 (nửa sau) trên 54 |
| Các chữ số trong cùng kỳ phụ thuộc nhau | Phương sai số lần một chữ số xuất hiện trong một kỳ | 2,43 (chục), 2,42 (đơn vị); nhị thức là 2,43 |
| Lô về hôm nay kéo theo kỳ sau | P(về \| đã về) − P(về \| chưa về), độ trễ 1, 2, 3, 7 | z = +0,74, +0,69, +0,55, +1,14 |
| Lệch vật lý trôi theo thời gian | Mô hình tần suất chữ số trong W kỳ gần nhất, co về đều với độ mạnh k (20 cấu hình), walk-forward 3 836 kỳ | Cả 20 cấu hình đều kém dự báo đều. Tốt nhất là W = 60, k = 5 000 với z = −0,61; co càng mạnh càng đỡ kém |
| Cầu vị trí khác nhau thật | Tỉ lệ trúng của 170 130 đường cầu, so độ tản với dao động nhị thức | 0,99 lần (LOTO), 1,00 lần (Đặc Biệt) — mục 2 |
| Cầu đang chạy dài trúng tiếp nhiều hơn | Tỉ lệ trúng tiếp theo độ dài chuỗi, đếm trên mọi đường cầu | 23,5–24,2% ở mọi độ dài, so với nền 23,76% — mục 2 |

Kỹ năng ngoài mẫu của vector **đã công bố** (`data/model_quality/report.json`, 48 kỳ):

- LOTO: −0,008%, khoảng tin cậy 95% từ −0,031% đến +0,014%.
- Đặc Biệt: −0,007%, khoảng tin cậy 95% từ −0,19% đến +0,18%.

Cả hai không phân biệt được với 0. Phân rã Murphy cho thấy cùng điều ấy: độ phân giải (LOTO
0,000283) ngang độ lệch hiệu chỉnh (0,000302).

**Kết luận:** hệ thống đã ở trần trong phạm vi sai số đo. Không phép thử nào tìm thấy cấu trúc để
học, nên không thay đổi nào có thể làm số "về" nhiều hơn. Phần còn làm được là để mọi tầng suy
luận đúng cách: trung thực khi không có tín hiệu, và tự học khi tín hiệu xuất hiện. Kiểm toán
03-10 và 04-10 đã đưa ML, cầu-kèo, thống kê và tổ hợp về luật ấy. Cầu vị trí là tầng cuối cùng
chưa theo.

## 2. Cầu vị trí: từ "tỉ lệ lịch sử của cầu được chọn" sang kinh nghiệm học từ mọi cầu

### Bản cũ sai ở đâu

`path_prob` chấm khoảng 5 671 cặp vị trí ở mỗi độ trễ (1–30), giữ 300 cầu có điểm cao nhất, rồi
in cho mỗi con số trung bình tỉ lệ trúng lịch sử của các cầu báo nó. Bước co về nền có độ mạnh đặt
tay, `6·√(1 + 2·ln(5671/300)) ≈ 15,7`. Tỉ lệ lịch sử của cầu được chọn ra từ hàng nghìn cầu mang
lời nguyền người thắng. Ngày neo 15-10-2026:

- **Mức bị thổi:** tổng xác suất LOTO của nhánh ổn định là 24,40 con mỗi kỳ, kỳ vọng thật là 23,76.
- **Mọi gợi ý đều cao hơn nền:** trang `soi-path-loto-stable.html` in 24,52–24,57% cho mười con.
- **Trang tự mâu thuẫn:** ghi chú cuối khối viết "đây là điểm xếp hạng, không phải xác suất đã
  hiệu chuẩn", ngay dưới tiêu đề «Gợi ý ngày mai (xác suất)».

Tổ hợp không bị ảnh hưởng, vì `finalize_blend` neo mức LOTO từ 04-10. Nhưng trang soi cầu và câu
lý do của cầu-kèo vẫn in con số thổi ấy.

### Câu hỏi đúng và câu trả lời của dữ liệu

**Câu hỏi 1: các cầu có khác nhau thật không?** Nếu mọi cầu có cùng một tỉ lệ thật, tỉ lệ quan
sát của chúng vẫn tản ra đúng bằng dao động nhị thức. Đo trên mọi cầu của cửa sổ 365 kỳ, ngày neo
15-10-2026:

| | Đường cầu | Độ tản so với nhị thức | Tỉ lệ trúng của cầu "tốt nhất" |
|---|---:|---:|---:|
| LOTO | 170 130 | 0,99 lần | 34,4% (nền 23,8%) |
| Đặc Biệt | 170 130 | 1,00 lần | 4,2% (nền 1,0%) |

Không có phần vượt. Tách riêng từng độ trễ cũng vậy: tỉ số dao động từ 0,93 đến 1,03 (LOTO) và từ
0,92 đến 1,07 (Đặc Biệt), quanh 1. Một cầu trúng 34% trong 365 kỳ là đúng cỡ cầu may mắn nhất trong
170 130 cầu.

**Câu hỏi 2: cầu đang chạy dài có trúng tiếp nhiều hơn không?** Đếm trên mọi cầu và mọi kỳ của
cửa sổ, tỉ lệ trúng ở kỳ kế tiếp theo độ dài chuỗi ngay trước kỳ ấy (LOTO, ngày neo 15-10-2026):

| Chuỗi trước kỳ | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8+ |
|---|---|---|---|---|---|---|---|---|---|
| Lần chấm | 46,9 tr | 11,1 tr | 2,63 tr | 623 nghìn | 148 nghìn | 35 246 | 8 286 | 1 948 | 608 |
| Trúng tiếp | 23,76% | 23,75% | 23,73% | 23,73% | 23,93% | 23,56% | 23,51% | 23,72% | 24,18% |

Cửa sổ bốn năm cho cùng kết quả: chuỗi 3–8 trúng tiếp 23,5–23,9%, so với nền 23,8%.

### Phép suy luận mới (`path_prob.BridgeEvidence`)

Mỗi đường cầu nhận **xác suất trúng kỳ tới** theo kinh nghiệm học từ MỌI cầu, không riêng các cầu
được giữ.

- **Phần riêng của cầu, co theo mức chênh thật giữa các cầu.** Đây là Bayes thực nghiệm bằng
  phương pháp mô men (`hierarchical_pooling.fit_shrinkage_to_prior`), dùng một tâm và một κ chung
  cho 30 độ trễ:
  - `p_post = m + N/(N + κ)·(trúng/N − m)`;
  - m là tỉ lệ trúng chung của mọi cầu;
  - N là số lần chấm của chính độ trễ ấy, không phải một trung bình chung (theo review Codex).

  Không có phần chênh vượt thì κ chạm trần và mọi cầu co về m. Hậu nghiệm Bayes không bị việc chọn
  top cầu làm lệch, nên lời nguyền người thắng biến mất mà không cần độ co đặt tay.
- **Kinh nghiệm theo độ dài chuỗi, chỉ cộng cho nhánh "đang chạy".** Tỉ lệ trúng tiếp theo nhóm
  chuỗi 0…7, 8+ được co bằng mô hình hiệu ứng ngẫu nhiên DerSimonian–Laird
  (`path_prob.streak_experience` → `hierarchical_pooling.random_effects_posterior`), mỗi nhóm
  nặng theo độ chính xác.
  - Phương sai mỗi nhóm tính theo **cụm kỳ quay** (ước lượng sandwich), không nhỏ hơn mức nhị thức.
    Hàng nghìn cầu chấm trên cùng một kỳ không độc lập với nhau: kỳ về nhiều con khác nhau thì mọi
    cầu LOTO cùng dễ trúng hơn. Coi chúng là phép thử độc lập thì chênh lệch ngẫu nhiên rất nhỏ
    giữa các nhóm thành τ² dương (theo review Codex).
  - Thống kê Q đo quanh trung bình theo nghịch đảo phương sai, chỉ tâm ấy cho E[Q] = k − 1 khi
    không có khác biệt thật. Hậu nghiệm vẫn co về tỉ lệ chung (theo review Codex).
  - Nhóm chỉ xuất hiện trong một kỳ quay có đúng một quan sát độc lập, nên co hẳn về tỉ lệ chung
    (theo review Codex).
  - Đo trên 80 lịch sử giả định có cú sốc theo kỳ nhưng không có khác biệt thật giữa nhóm: phương
    sai theo cụm co hoàn toàn ở 72,5% số lần, phương sai nhị thức chỉ 21%.
  - Phương pháp mô men không trọng số bị loại vì nhóm nhiễu nhất chi phối nó: trên lịch sử công
    bằng giả định, nó giữ lại tới 1,4 điểm phần trăm nhiễu ở nhóm ít dữ liệu.
  - τ² = 0 thì mọi độ dài co hẳn về nền. Trên dữ liệu thật, LOTO có τ² = 0. Đặc Biệt có τ² rất nhỏ:
    nhóm chuỗi 1 nhận 1,005% so với 1,000%.
- **Một con số** nhận trung bình (theo độ tin cậy) dự báo của các cầu đủ điều kiện cùng báo nó.
  Các cầu ấy tương quan với nhau qua chung chữ số và chung kỳ gốc, nên lấy trung bình chứ không
  cộng dồn.

Nếu một ngày các cầu khác nhau thật — lồng cầu lệch, hay một quy luật xuất hiện — độ tản sẽ vượt
nhị thức, κ hữu hạn, và cầu tốt tự giữ lại phần tỉ lệ riêng tương xứng. Phép kiểm
`test_real_bridges_keep_part_of_their_own_rate` ghim đúng điều này: trên lịch sử giả định có 27 cầu
thật trúng 62%, các cầu ấy giữ trên nền ít nhất 5 điểm phần trăm, và con mà chúng báo xếp trên các
con khác.

## 3. Đo ngoài mẫu

Tái lập bằng `PYTHONPATH=src python3 scripts/research/benchmark_bridge_inference.py --last 2000`
(khoảng 20 phút, 4 lõi). Số liệu thô nằm ở `data/research/model_overhaul/bridge_inference.json`.

Walk-forward 2 000 kỳ, cầu dựng lại mỗi kỳ bằng đúng tham số của pipeline. Bản cũ được tái lập từng
bit: sai lệch 0,0 so với mã trước 16-10-2026 ở cả bốn ô, kiểm trên hai ngày neo. Mốc hằng số là tỉ
lệ nền tích luỹ (LOTO) và 1/100 (Đặc Biệt).

Luật quyết định chốt TRƯỚC khi đo, ghi trong docstring của kịch bản:

1. **Nhánh cầu:** bản mới không kém bản cũ với z ≤ −2 ở bất kỳ ô nào trong bốn ô, và thắng với
   z ≥ 2 ở ít nhất một ô.
2. **Tổ hợp:** bản mới không kém bản cũ với z ≤ −2 ở cả hai chế độ.
3. **Hằng số:** tổ hợp mới không kém dự báo hằng số với z ≤ −2.

Kỳ đích từ 31-03-2021 đến 15-10-2026, 2 000 kỳ.

**Nhánh cầu** (chính vector trang soi cầu in):

| Ô | Mới so với cũ | Cũ so với hằng số | Mới so với hằng số | Tổng LOTO (trung vị): cũ → mới |
|---|---:|---:|---:|---:|
| LOTO đang chạy | **z = +7,86** (nửa +5,73 / +5,38) | z = −8,09 | z = −1,65 | 24,48 → 23,82 |
| LOTO ổn định | **z = +38,25** (nửa +26,61 / +27,48) | z = −38,55 | z = −1,62 | 26,46 → 23,82 |
| Đặc Biệt đang chạy | z = +1,10 | z = −0,75 | z = +0,83 | — |
| Đặc Biệt ổn định | z = +1,08 (nửa +0,63 / +0,91) | z = −0,97 | z = +0,84 | — |

**Tổ hợp** (trọng số mặc định, chốt bằng `finalize_blend`):

| | Mới so với cũ | Mới so với hằng số |
|---|---:|---:|
| LOTO | z = −0,42 (nửa +0,23 / −0,84) | z = +0,43 |
| Đặc Biệt | z = +0,27 | z = +0,98 |

**Quyết định: đạt cả ba luật, nên đổi.**

1. Nhánh: thấp nhất z = +1,08, cao nhất z = +38,25.
2. Tổ hợp so với cũ: thấp nhất z = −0,42.
3. Tổ hợp so với hằng số: thấp nhất z = +0,43.

Đọc cho đúng:

- **Phần thắng lớn nằm ở nhánh, không ở tổ hợp.**
  - Nhánh cũ kém hằng số rất xa (LOTO ổn định z = −38,55) vì lời nguyền người thắng ở MỨC.
  - Ở tầng tổ hợp, `finalize_blend` đã neo mức từ 04-10, nên hai bản ngang nhau. Đó là điều mong
    đợi: tổ hợp đã ở trần, và phép sửa này không được phép làm nó tệ đi.
- **Nhánh LOTO mới vẫn nhỉnh kém hằng số**, z = −1,65 và −1,62, cùng dấu ở cả hai nửa nhưng không
  có ý nghĩa thống kê. Có hai nguồn, ghi ra thay vì sửa sau khi đã xem kết quả:
  - tâm co là tỉ lệ trúng chung của cửa sổ 365 kỳ (tổng trung vị 23,82), không phải mốc tích luỹ;
  - ở 53% số ngày, phương pháp mô men rơi về phía dương do nhiễu nên κ hữu hạn. Phần chênh được giữ
    khi ấy không quá 1,0%, và độ lệch lớn nhất của kinh nghiệm chuỗi so với nền là 0,06 điểm phần
    trăm.

  Docstring của `hierarchical_pooling.fit_shrinkage_to_prior_rows` đã cảnh báo đúng hiện tượng này:
  κ hữu hạn không phải một phát hiện.
- Độ tản giữa các cầu qua 2 000 ngày neo: trung vị 1,00 lần nhị thức, khoảng 0,99–1,01 (LOTO);
  trung vị 1,00 lần, khoảng 0,99–1,01 (Đặc Biệt).

## 4. Điều thay đổi với người đọc

- **Trang `soi-path-*.html`:**
  - Khối gợi ý in xác suất trúng kỳ tới đã co theo kinh nghiệm mọi cầu (LOTO khoảng 23,76%), thay
    cho 24,5%.
  - Bảng đường cầu có thêm cột «Dự báo kỳ tới» cạnh «Tỷ lệ lịch sử».
  - Khối mới «Kinh nghiệm học từ mọi đường cầu» in độ tản so với dao động ngẫu nhiên và bảng trúng
    tiếp theo độ dài chuỗi. Câu kết luận suy TỪ số đo của ngày neo; một phép kiểm dựng cả hai
    trường hợp (có và không có phần vượt) để trang PHẢI nói khác nhau.
  - Phạm vi (cặp vị trí, độ trễ) in theo đúng cấu hình đã sinh dự báo, đọc từ
    `bridge_evidence_<mode>.json`. Tệp ấy khác ngày neo của trang thì khối bị bỏ, không ghép
    kinh nghiệm của ngày này với bảng cầu của ngày khác.
  - Cột «Dự báo kỳ tới» và xác suất dùng để xếp gợi ý cùng do `path_prob.rule_next_probability`
    tính, kể cả thiên lệch khi chạy phạm vi gần Đặc Biệt.
  - Ghi chú tự mâu thuẫn "không phải xác suất đã hiệu chuẩn" đã bỏ.
- **Câu lý do của cầu-kèo** (`cau_position_evidence`): thay "lịch sử 117/361, p≈0.324" bằng "trúng
  117/361 kỳ trong cửa sổ; dự báo kỳ tới 23,76% theo kinh nghiệm mọi đường cầu".
- **Tổ hợp:** hai nhánh cầu vị trí nay gần như bằng nền ngay tại nguồn. Vector công bố vì thế phẳng
  hơn nữa, và thứ tự gợi ý do các thành phần còn lại quyết định — không thành phần nào có kỹ năng đo
  được.

## 5. Kiểm thử

- **`tests/test_bridge_inference.py`** (18 phép) ghim:
  - đếm kinh nghiệm chuỗi khớp phép đếm thẳng;
  - lịch sử công bằng: mọi cầu co về tỉ lệ chung, tỉ lệ lịch sử của cầu được chọn cao hơn hẳn còn
    hậu nghiệm thì không, và tổng nhánh đúng mức;
  - lịch sử có cầu thật: cầu ấy giữ phần riêng và con nó báo xếp trên;
  - kinh nghiệm chuỗi theo dữ liệu;
  - nhánh lấy trung bình hậu nghiệm, và chỉ nhánh đang chạy cộng kinh nghiệm chuỗi;
  - cầu thiếu hậu nghiệm bị từ chối;
  - trang nói đúng điều số đo nói, ở cả hai trường hợp;
  - trang in cột dự báo và khối kinh nghiệm;
  - DerSimonian–Laird co hoàn toàn khoảng một nửa số lần khi không có khác biệt thật, và giữ khác
    biệt thật;
  - kinh nghiệm chuỗi coi một kỳ quay là một cụm, và nhóm chỉ thấy trong một kỳ co hẳn về nền;
  - phần riêng giữ theo đúng số lần chấm của từng độ trễ;
  - trang in đúng phạm vi đã cấu hình;
  - bằng chứng của ngày neo khác không được in;
  - cột trên trang và xác suất của gợi ý là cùng một số, kể cả khi có thiên lệch;
  - Q của DerSimonian–Laird đo quanh trung bình nghịch đảo phương sai.
- **`tests/test_cau_position_evidence.py`:** câu lý do in xác suất đã co, không in tỉ lệ trong mẫu;
  xác suất ấy dùng chung `rule_next_probability` nên luôn nằm trong (0, 1).
- **23 đột biến** đều đỏ đúng chỗ:
  - không co, hoặc co hoàn toàn;
  - nhánh đang chạy bỏ kinh nghiệm chuỗi, hoặc nhánh ổn định cũng cộng nó;
  - nhóm chuỗi lệch một; đếm sau khi cập nhật chuỗi; nhóm chỉ một kỳ vẫn được học;
  - τ² luôn bằng 0; τ² không trừ bậc tự do;
  - dự báo dùng tỉ lệ lịch sử; cầu thiếu hậu nghiệm vẫn được nhận;
  - trang bỏ cờ gộp; trang bỏ cột dự báo;
  - câu lý do bỏ chuỗi; câu lý do in tỉ lệ lịch sử; câu lý do không chặn biên;
  - giữ phần riêng theo N điều hoà chung; phương sai nhị thức thay cho phương sai cụm; trang ghi
    cứng phạm vi;
  - trang không đọc `p_next`; bỏ kiểm ngày neo; cột trang bỏ thiên lệch; Q đo quanh tỉ lệ chung.

**Một bài học về đột biến.** Đột biến "đếm sau khi cập nhật chuỗi" chỉ đổi chỗ hai khối mã, nên tệp
giữ nguyên kích thước. Khi tệp được khôi phục trong cùng giây, Python vẫn tin bản `.pyc` của mã đột
biến, và một lượt dựng sau đó chạy mã đột biến dù mã nguồn trên đĩa đúng. Mọi lượt đột biến ở đây
chạy với `PYTHONDONTWRITEBYTECODE=1`.
