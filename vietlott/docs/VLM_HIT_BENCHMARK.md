# VLM: kiểm chứng xác suất và số khớp H (Mega 6/45, Power 6/55)

Mục đích: đo xem mô hình nào — đang chạy hay challenger — cho xác suất trung thực hơn luật công
bằng, và vé sáu số của nó trùng bao nhiêu số chính (H) so với đúng mốc ngẫu nhiên. Kết quả gần
nhất: `reports/VLM_HIT_BENCHMARK_2026-10-13.md`; artifact đầy đủ: `reports/vlm/hit-benchmark/`.

## Chạy và tái lập

```bash
cd vietlott
python -m pip install -e ".[dev]"
python scripts/hit_benchmark.py                      # cả hai sản phẩm, gồm bộ ML (~10 phút)
python scripts/hit_benchmark.py --no-ml              # nhanh, không đủ để đề bạt
python scripts/hit_benchmark.py --render-only        # dựng lại báo cáo từ artifact đã ghi
```

Mỗi `<sản phẩm>.json.gz` lưu: hash seed, nhật ký kết quả và toàn bộ lịch sử dùng để học
(`history_sha256`), commit git và cờ `git_dirty`, sha256 từng tệp mã quyết định kết quả
(`source_sha256`), phiên bản Python/NumPy/SciPy/scikit-learn, cấu hình ML, seed, ranh giới
dev/validation/test (ID và ngày), và cho TỪNG kỳ của mọi nhánh: xác suất biên π của 45/55 số, vé,
log-score bộ chính, log-score số đặc biệt (Power), Brier, số khớp H; danh mục 5 vé của ML; số vé
và ngân sách mỗi kỳ; thời gian chạy. Hai lần chạy trên cùng `history_sha256` và cùng
`source_sha256` phải cho cùng số (seed cố định).

## Giao thức (đăng ký 13-10-2026, `vlm.forecast.hit_benchmark.PROTOCOL`)

- Dữ liệu: seed + `data/results/results.jsonl`, cắt ở Mega #1574, Power #1409; ID phải liền từ 1,
  nhật ký mâu thuẫn seed thì dừng.
- 300 kỳ đầu chỉ để học; phần còn lại chia liền: dev 50% · validation 20% · test 30%.
- Mỗi kỳ được dự báo TRƯỚC khi mô hình thấy kết quả; học sau nhãn chỉ ảnh hưởng kỳ sau.
- Challenger chọn siêu tham số trên dev, bỏ nhóm đặc trưng không dương ở ≥ 3/4 fold liền của
  dev + validation, hiệu chuẩn nhiệt độ trên validation, rồi chốt. Test nhìn MỘT lần.
- Thước đo chính: log-score cả kỳ so với công bằng (nats/kỳ), Diebold–Mariano HAC một phía theo
  kỳ, Holm trên mọi ứng viên × sản phẩm. Kèm Brier biên, reliability/ECE, phân bố H.

Các nhánh:

| Nhánh | Là gì | Vé |
|---|---|---|
| Công bằng | luật đều; vé ngẫu nhiên chốt trước để kiểm mốc siêu bội | ngẫu nhiên |
| Legacy | `vietlott_engine.forecast` (hỗn hợp chuyên gia, e-value) | 6 số π cao nhất — đúng vé ghi sổ |
| ML | `vlm.forecast` (logistic, GRU, RF; fixed-share) | `Law.top` — đúng vé trên bảng điều khiển |
| … + hiệu chuẩn τ | trọng số mỗi chuyên gia mũ τ, τ học trên validation | 6 số π cao nhất |
| Co về công bằng | tần suất mũ hoá, co Beta về k/n, nhiệt độ | 6 số trọng số cao nhất |
| Đặc trưng nhân quả | conditional logit: tần suất, gap/lag, lịch, đồng xuất hiện trễ; L2; học lại mỗi 26 kỳ | 6 số trọng số cao nhất |

Mọi luật đều là conditional Bernoulli hoặc hỗn hợp của chúng: π của các số chính cộng lại đúng
bằng 6, phân phối trên các bộ sáu số chuẩn hoá đúng, số đặc biệt Power có P(b | bộ chính) =
w_b / Σ_{i∉S} wᵢ và được chấm riêng — KHÔNG cộng vào H. Hiệu chuẩn nhiệt độ giữ nguyên các ràng
buộc ấy.

## Số khớp H

H = |vé ∩ sáu số chính|. Với vé chốt trước kỳ quay, dưới máy quay công bằng H theo siêu bội
C(6,h)·C(N−6,6−h)/C(N,6), N = 45 hoặc 55, bất kể vé được chọn thế nào. `vlm.forecast.hits` báo
số kỳ đạt H ≥ 3, 4, 5, = 6, khoảng Clopper–Pearson, p nhị thức chính xác một phía, H trung bình
và z theo phương sai siêu bội. Đơn vị là kỳ quay.

H ≥ 4 hiếm: Mega 0,139%, Power 0,062% mỗi vé. `hits.detectable_lift` cho hệ số tăng nhỏ nhất
phát hiện được với công suất 80%: trên ~380 kỳ test chỉ một mức tăng khoảng ×8 (Mega) hoặc ×14
(Power) mới thấy được, và để phát hiện ×2 cần ~6.900 kỳ Mega (≈ 44 năm quay). Vì thế H ≥ 4 được
báo cáo nhưng KHÔNG dùng để đề bạt; "không thấy H ≥ 4" trên cửa sổ này là "chưa đủ bằng chứng".

Nhiều vé: `hits.portfolio_summary` cố định số vé, tách chỉ số từng vé với "ít nhất một vé đạt
mức", đo độ trùng và độ phủ, và ước lượng mốc ngẫu nhiên của "ít nhất một vé" bằng Monte Carlo
trên CHÍNH bộ vé ấy. Năm vé tốn năm lần tiền; tăng số vé không phải dự báo tốt hơn.

## Điều kiện đề bạt (đăng ký trước)

Một ứng viên chỉ đủ điều kiện CHẠY THỬ TIẾN CỨU khi đạt cả năm:

1. Δ log-score so với công bằng trên test > 0, p Holm (mọi ứng viên × sản phẩm) < 0,05.
2. Δ so với TỪNG mô hình đang chạy (legacy và ML) > 0, p < 0,05.
3. Δ so với công bằng trên validation > 0.
4. Δ so với công bằng dương ở ít nhất 2 trong 3 đoạn liền của test.
5. Brier biên trên test không kém Brier công bằng.

Đạt cả năm cũng chưa đổi xác suất triển khai: ứng viên phải được nối vào luồng phát hành (thay
đổi riêng, có review), ghi luật vào sổ TRƯỚC mỗi kỳ, và qua cổng live có sẵn của bộ ML (≥ 100 kỳ
live, e-value hiện tại ≥ 140, tổng log-score 100 kỳ gần nhất dương, dữ liệu không có gap/anomaly).
Drift của đặc trưng không bao giờ là bằng chứng mô hình dự báo tốt hơn.

## Trạng thái production và rollback

- Xác suất triển khai (`p_deployed`) là luật công bằng cho tới khi cổng live mở; benchmark này
  không đổi điều đó.
- Vé công bố giữ quy tắc cũ: legacy = 6 số π cao nhất (sổ `ledger.jsonl`), ML = `Law.top`
  (`ml-ledger.jsonl`). Sổ chỉ ghi thêm; bảng điều khiển lấy bản ghi SỚM NHẤT trước giờ quay.
- Checkpoint ML lên version 3 ngày 13-10-2026 (`pair_link`/`triple_link` không còn gộp tần suất
  của chính số ấy). Checkpoint version 2 được cất thành `.invalid`, mô hình học lại từ lịch sử và
  báo `checkpoint_recovered`; bằng chứng live bắt đầu lại — sổ `ml-ledger.jsonl` giữ nguyên.
- Rollback mô hình ML: `vlm-forecast fit --product <p>` (học lại từ đầu, reset bằng chứng live),
  hoặc khôi phục `data/forecast/ml/<p>.json.gz` từ cache trạng thái `vqe-state-` của workflow.
  Rollback legacy: `vietlott forecast fit` hoặc khôi phục `data/forecast/<p>.json`. Rollback về
  luật công bằng không cần thao tác: đó là mặc định khi cổng chưa mở.

## Kiểm toán nguyên nhân (13-10-2026)

Ba loại được tách bạch: xác suất TÍNH SAI, xác suất THIẾU HIỆU CHUẨN, và xác suất hợp lệ nhưng
CHƯA CÓ SỨC DỰ BÁO.

**Đã kiểm, không có lỗi:**

- Dữ liệu: Mega #1–#1574 và Power #1–#1409 liền mạch, ngày tăng ngặt, không kỳ trùng, mỗi kỳ đúng
  sáu số phân biệt trong phạm vi, số đặc biệt Power luôn nằm ngoài bộ chính, nhật ký kết quả không
  mâu thuẫn seed. Power có một bộ lặp lại ở #647 và #993 (cách nhau hơn hai năm, khác số đặc biệt):
  hợp lệ — khả năng có ít nhất một cặp trùng trên chừng ấy kỳ khoảng 3%.
- Hai sổ dự báo: mọi dòng Mega/Power ghi trước giờ quay ít nhất 5 phút, `target_id = based_on_id + 1`,
  ngày đích khớp ngày quay thật, điểm đã ghi khớp tính lại; nhiều dòng cho cùng một kỳ thì bảng
  điều khiển và bảng thành tích chỉ lấy dòng ghi SỚM NHẤT.
- Đơn vị xác suất: π các số chính cộng đúng 6 ở cả legacy lẫn ML, luật trên bộ sáu số chuẩn hoá
  đúng, hỗn hợp trộn các LUẬT chứ không nhân các xác suất biên; Power có P(b | bộ chính) =
  w_b / Σ_{i∉S} wᵢ, và H chỉ đếm số chính (bảng điều khiển ghi `bonus_hit` riêng).
- Nhân quả: đặc trưng ML là ảnh chụp trước kỳ, chuẩn hoá chạy chỉ dùng kỳ đã biết, legacy chấm
  rồi mới học; benchmark dựng lại luật legacy và khớp phần tăng e-value của engine tới 10⁻¹³ nats.

**Tính sai — đã sửa, có phép kiểm tái hiện:**

1. `pair_link`/`triple_link` (đặc trưng giả): `pairs[i, i]` là tần suất của chính số i, không phải
   cặp. Gộp nó vào thì `pair_link` của số vừa về tương quan 0,99 với `lag1` (Mega; Power 0,97),
   tức "đồng xuất hiện" thực chất là "có về kỳ trước". `triple_link` chia cho |S|² trong khi chỉ
   m(m − 1) ô có nghĩa. Checkpoint ML lên version 3.
2. `evaluate_series` chấm sáu số có π cao nhất, trong khi vé ML công bố là bộ có xác suất đồng
   thời cao nhất (`Law.top`) — trên Power, ví dụ `6 13 36 39 43 45` so với `13 36 39 43 45 54`.
   Benchmark cũ vì thế báo số trùng của một vé chưa từng phát.
3. Trang Vietlott in "tỷ lệ trùng theo từng vé" (ví dụ 13%) mà không có mốc; 13,3% chính là tỷ lệ
   của vé chọn bừa ở Mega. Nay in "chọn bừa k/n" bên cạnh.

**Thiếu hiệu chuẩn — đo được, production không đổi:**

- Legacy trên Mega kém luật công bằng có ý nghĩa ngoài mẫu, và nhiệt độ học trên validation gần
  bằng 0: các hệ số "×" mà legacy tự báo cho bộ đề xuất nên đọc là ×1. Không chỉnh engine: hỗn
  hợp ấy là e-process, phải giữ chuyên gia khác công bằng để có công suất; câu kết luận của nó vốn
  đã nói "mọi bộ số vẫn có cùng xác suất" khi chưa có bằng chứng, và xác suất triển khai là công bằng.
- ML: nhiệt độ validation không ổn định (Mega chạm biên trên, test lại kém hơn bản gốc), nên
  không hiệu chuẩn production bằng nó.

**Hợp lệ nhưng chưa có sức dự báo:** không nhánh nào thắng luật công bằng có ý nghĩa trên test;
H ≥ 4 không xuất hiện ở nhánh nào trên test (kỳ vọng ngẫu nhiên 0,53 kỳ Mega, 0,21 kỳ Power), và
cỡ mẫu chỉ đủ phát hiện mức tăng ×8 (Mega) hoặc ×14 (Power).

**Ghi nhận về danh mục 5 vé của ML:** năm bộ xác suất cao nhất của một luật gần đều là các "hàng
xóm" của nhau — trung bình hai vé chung 5/6 số (Mega) và 4,8/6 (Power), độ phủ 27–33%. Đó là xếp
hạng, không phải danh mục mua; ai mua cả năm vé chủ yếu mua lại cùng một rủi ro.

## Hướng tiếp theo

- Bằng chứng thật chỉ đến từ các kỳ SAU 13-10-2026: luồng live sẵn có (sổ ghi trước giờ quay, cổng
  e-value) tiếp tục chạy; đừng chạy lại benchmark hồi cứu này với cấu hình khác rồi gọi là test.
- Nguồn tín hiệu duy nhất có thể là vật lý (máy quay, bộ bóng) — chỉ khi Vietlott công bố siêu dữ
  liệu ấy; mọi đặc trưng thuần lịch sử kết quả đã được thử và bị ablation loại.
- Nếu cần nhiều vé, dùng danh mục ít trùng (`MLForecaster.portfolio`) và đo nó bằng
  `hits.portfolio_summary`, với số vé và ngân sách cố định.
