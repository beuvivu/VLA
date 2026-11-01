# Nhật ký thay đổi

## Chưa phát hành — Keno/Bingo18 đồng bộ lại, Python 3.15 (01-11-2026)

- **Cổng hồ sơ kiểm chứng cho bản sao Keno/Bingo18 (`ProductSyncPipeline._vet_fast_mirror`).**
  - Từ 19-10-2026 vietlott.vn trả thử thách Cloudflare cho runner. Kho NhanAZ chỉ còn đăng lại kết quả từ
    trang thứ cấp (`pending`), nên hai sản phẩm đứng ở kỳ 299797 / 191942 suốt 13 ngày.
  - Bản sao `vietvudanh/vietlott-data` nay được nhập khi, đo lại mỗi lượt:
    - trùng tuyệt đối ≥ 10 000 kỳ seed có xuất xứ chính thức mà nó chồng lên;
    - trùng tuyệt đối ≥ 50 kỳ "trang đăng lại" độc lập của kho NhanAZ (nguồn thu thập khác);
    - một kỳ lệch ở bất kỳ phép so nào thì loại cả bản sao lượt ấy.
  - Đo 01-11-2026:
    - Keno: 86 272 kỳ chính thức và 1 509 kỳ đối chiếu, 0 lệch; tiến tới #301336;
    - Bingo18: 92 759 và 1 558, 0 lệch; tiến tới #193999.
  - `ArchiveDraws.secondary` giữ kỳ bị loại chỉ vì xuất xứ, để làm phép đối chiếu; chúng không bao giờ được nhập.
- **`data/seed/known_gaps.json`:** 2 khoảng mã kỳ Keno và 20 khoảng Bingo18 đã kiểm là không có ở seed, bản sao
  lẫn kho NhanAZ.
  - Khoảng hở nằm trọn trong sổ không còn là lỗi đồng bộ, nên workflow thôi đỏ mãi vì thứ không nguồn nào lấp được.
  - Không phải thông báo loại kỳ, không có số nào được suy ra. Khoảng hở mới hoặc chỉ trùng một phần vẫn là lỗi.
- **Python 3.15:** Docker `python:3.15-slim`; bộ cài ưu tiên 3.15 (vẫn nhận 3.11+); ma trận CI 3.11 (sàn) + 3.15.
  Phép kiểm `test_vlm_hit_benchmark` dùng bước `np.timedelta64(3, 'D')`: numpy sắp cấm bước số nguyên cho ngày.

## Chưa phát hành — hỗn hợp Bayes cho bộ chữ số, số đặc biệt Lotto theo vé (31-10-2026)

- **Chuyên gia `bayes_mixture` trong bộ ML (`vlm.forecast.bayes_expert`), chỉ cho thành phần chữ số.**
  - Là luật hậu nghiệm của hỗn hợp Bayes chia sẻ cố định của `vietlott_engine.forecast`, chạy trên đúng
    các kỳ bộ ML học, chấm trước – học sau.
  - Max 3D lệch thật ở hàng đơn vị: chữ số 6 chiếm 10,6–11,3% ở cả sáu giai đoạn 2019 → 2026. Bộ ML cũ
    không học được độ lệch ấy.
  - Log-score so với quay công bằng trên 1 000 kỳ cuối:
    - Max 3D: −0,158 → +0,771 log10;
    - Max 3D Pro: −0,161 → +0,641 log10;
    - Max 4D, Bingo18, số đặc biệt Lotto: không kém đi.
  - Checkpoint ML lên version 5. Sản phẩm có thành phần chữ số học lại; Mega, Power, Keno vẫn nạp
    checkpoint 3/4.
- **`ticket_rule = coverage-v2`:** vé Lotto 5/35 thứ j mang số đặc biệt hạng j
  (`distribution.coverage_specials`), chấm đúng từng vé.
  - "Ít nhất một vé trúng giải" tăng từ 14,7% lên 45,7% (`dashboard.prize_coverage`, chính xác, đọc
    điều kiện trúng từ bảng giải). Xác suất và kỳ vọng của từng vé không đổi.
  - Lần ghi `coverage-v1` giữ số đặc biệt chung.
- **Phép kiểm dòng "tương lai"** dựng ngày từ ngày Việt Nam như engine. Bản cũ dùng `date.today()` của máy
  (UTC) nên đỏ từ 17:00 đến 24:00 UTC.

## Chưa phát hành — kiểm toán định lượng (19-10-2026)

- **`vlm.multi_agent.models.SubsetDistribution` nhanh hơn 4–9 lần, kết quả không đổi một bit.**
  - Chiều xuôi của quy hoạch động tính mỗi hàng bằng một lời gọi `np.logaddexp` theo cột.
  - Xác suất rẽ nhánh của chiều ngược tính một lần cho cả ma trận n × k.
  - Phần lan khối lượng giữ đúng thứ tự cộng cũ.
  - Phép kiểm so `_dp` và biên với bản vô hướng cũ bằng `assert_array_equal` trên 49 ca, kể cả
    logit ±1e308 và k = n.
  - Báo cáo: `../documentation/qa/2026-10-19-kiem-toan-dinh-luong.md`.

## Chưa phát hành — vé công bố rời nhau, nguồn kết quả nhanh (15-10-2026)

- **Vé công bố:** lần ghi mới mang `ticket_rule = coverage-v1`; bảng điều khiển dựng năm vé rời nhau từ luật đã ghi (`distribution.coverage_tickets`) kèm mốc chính xác "ít nhất một vé ≥ 2/≥ 3 số" (`dashboard.coverage_summary`). Mega 30,6% → 70,9%, Power 22,2% → 53,7% với cùng năm vé; xác suất từng vé không đổi. Lần ghi cũ giữ `Law.top`.
- **Nguồn `xskt`** cho Mega/Power/Lotto (`crawler/sources/xskt.py`), đứng sau bản sao NhanAZ trong `fallback_order`; trang không đọc được báo lỗi để chuỗi hỏi nguồn sau. Chuỗi sản phẩm (Max 3D, Keno…) bỏ qua nó.

## Chưa phát hành — kiểm chứng xác suất và số khớp H (13-10-2026)

- **Sửa đặc trưng ML:** `pair_link`/`triple_link` không còn gộp tần suất của chính số ấy (đường chéo); checkpoint ML lên version 3, bản cũ được học lại.
- **Sửa chấm benchmark ML:** `evaluate_series` chấm đúng vé công bố (bộ đầu của `Law.top(PUBLISHED_TOP_N)`, cùng lệnh gọi với bảng điều khiển) thay vì sáu số biên cao nhất.
- **`vlm.forecast.hits`:** phân bố H của vé chốt trước kỳ quay so với siêu bội, Clopper–Pearson, p nhị thức chính xác, phân tích công suất, danh mục nhiều vé có mốc "ít nhất một vé" tính chính xác theo vùng giao của các vé (Monte Carlo chỉ dự phòng, kẹp vào cận Bonferroni bậc hai chính xác; phép kiểm của kỳ ấy dùng cận trên chính xác) và p e-process luôn hợp lệ khi danh mục học lại theo kết quả; `--render-only` từ chối artifact của giao thức khác.
- **`vlm.forecast.challengers`, `vlm.forecast.hit_benchmark`, `scripts/hit_benchmark.py`:** giao thức walk-forward đăng ký trước (dev/validation/test), challenger co về công bằng và conditional logit trên đặc trưng nhân quả, ablation theo nhóm, hiệu chuẩn nhiệt độ, luật đề bạt năm điều kiện, artifact có provenance. Báo cáo: `reports/VLM_HIT_BENCHMARK_2026-10-13.md`; tài liệu: `docs/VLM_HIT_BENCHMARK.md`.

## 4.0.0 — repo riêng, bộ cài hoàn chỉnh

Tách khỏi VLA thành repo độc lập.

- **Gói Python `vietlott_engine`** (bố cục `src/`, `pip install -e .`, lệnh `vietlott`). Thay cho package `src` cũ (trùng tên với VLA). Mã gọi `from src.… import …` cần đổi thành `from vietlott_engine.… import …`; `python -m src.cli …` thành `vietlott …`.
- **Bộ cài:** `install.cmd` / `install.ps1` cho Windows (PowerShell 5.1 trở lên, tự tìm Python qua `py` và thư mục cài mặc định, tùy chọn cài Python bằng winget, cài gói ở chế độ thường để an toàn với tên thư mục có dấu) và `install.sh` cho Linux / macOS (cài editable). Bộ cài tạo `.venv` (tạo lại nếu hỏng), cài gói, tạo `.env`, nạp dữ liệu, học bộ dự báo, tạo lệnh tắt `vietlott(.cmd)`, ghi thư mục dự án vào `.venv/vietlott_home.txt` và kiểm tra. Chạy lại an toàn.
- **`vietlott init`, `vietlott doctor`, `vietlott --version`.** Lệnh tự chuyển về thư mục dự án (`VQE_HOME` để chỉ định), tự đưa đầu ra về UTF-8 trên Windows và báo lỗi một dòng dễ đọc (`VQE_DEBUG=1` để xem chi tiết).
- **Sổ dự báo theo lịch quay chính thức.** Chỉ ghi khi kỳ được dự báo chưa quay. Keno/Bingo18 chỉ ghi trong khoảng 22:15–05:55 và khi ngày dữ liệu đã đủ kỳ. `--force-record` ghi nhưng không tính vào thành tích. API `?record=true` theo cùng quy tắc. Max 4D (đã ngừng) không có kỳ tới.
- **GitHub Actions:** CI (test trên Linux và Windows), `installer.yml` (chạy bộ cài trên Linux / macOS / Windows khi bộ cài đổi và mỗi tuần); `update.yml` chạy 2 lần/ngày: đồng bộ, học kỳ mới, ghi sổ dự báo vào repo (trước bước dựng trang, để trang lỗi cũng không mất sổ), rồi đăng trang GitHub Pages kèm JSON cho VLA / trang khác; `release.yml` phát hành bằng tag; Dependabot.
- **Hai sổ dự báo tách nhau:** máy cài bằng bộ cài ghi vào `data/local/forecast/` (đặt trong `.env`, không theo dõi bằng git); GitHub Actions ghi sổ công khai `data/forecast/ledger.jsonl` và commit vào repo. Chạy trên máy không làm đổi tệp nào của repo, nên `git pull` / GitHub Desktop không xung đột với các commit tự động.
- **`scripts/build_site.py`:** trang tĩnh tiếng Việt (sáng / tối, điện thoại) và `data/*.json`.
- Docker: Python 3.12, cài gói thay vì chép mã; các script báo cáo đọc `VQE_PRODUCT_SEED_DIR`.

## 3.5.0 — dự báo tự học có kiểm chứng

Hỗn hợp Bayes fixed-share của các chuyên gia cho cả 8 sản phẩm, có e-value hợp lệ ở mọi thời điểm và sổ dự báo. Trên dữ liệu thật, chỉ thấy tín hiệu ở chữ số 6 hàng đơn vị của Max 3D / Max 3D Pro. README mục 1.9.

## 3.4.0 — vietlott.vn có Cloudflare

Nhận ra thử thách Cloudflare và dừng, không vượt. Nhập trang hoặc HAR do người dùng tự lưu, có đối chiếu (`products import-pages`). Danh sách trang nên kiểm. README mục 1.8.

## 3.3.0 — nguồn dự phòng

Chuỗi `--source auto` (vietlott.vn → kho cộng đồng → bản sao → snapshot 1.3.0); Keno 297 nghìn kỳ; Max 4D; danh sách kỳ không xác nhận. README mục 1.7.

## 3.0 – 3.2

Dữ liệu giải thưởng chính thức, hiệu chỉnh hành vi người chơi, chơi bao, toàn bộ sản phẩm Vietlott, cơ chế hai pha của Jackpot Lotto 5/35. README mục 1.4–1.6.

## 1.x – 2.x

Kiểm định ngẫu nhiên, Bayes/Markov/GCN, EV chống trùng số, bao lô, backtest walk-forward, suy luận thống kê.
