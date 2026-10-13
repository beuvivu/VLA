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
