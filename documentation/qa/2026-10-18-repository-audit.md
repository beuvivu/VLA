# Kiểm toán và hoàn thiện VLA — 18/10/2026

## Phạm vi và cách đánh giá

Mốc bắt đầu là `696a7c78a5d8f0db8c42847d1e586ab38226061c`; bản sửa đã được đặt trên `4f9ad95`, giữ các cập nhật dữ liệu tự động mới hơn trong lúc kiểm toán. Kiểm kê tại mốc bắt đầu có 2.456 tệp được quản lý bằng Git, 354 tệp nguồn Python/JavaScript với 95.364 dòng, 50 trang HTML và 27 workflow. XSMB, engine Vietlott, Worker và site tĩnh được xem như bốn ranh giới riêng.

Việc kiểm toán kết hợp đọc các đường gọi thực tế, kiểm thử toàn dự án, tái hiện nhỏ có kiểm soát, kiểm tra Chromium và review độc lập bản vá. Đây không phải tuyên bố đã kiểm thủ công từng dòng của 95.364 dòng hoặc chứng minh chương trình không còn lỗi. Các nhận xét dưới đây gắn với hành vi đã tái hiện; đề xuất dài hạn được tách khỏi bản sửa.

Ràng buộc: giữ lịch sử kết quả, sổ dự báo, mô hình đã lưu và giao thức kiểm định đã đăng ký. Không đề bạt mô hình mới dựa trên kết quả hồi cứu. Các thay đổi nghiên cứu không được tự đưa vào tổ hợp sản xuất.

## 1. Logic, dự báo và tự học

| Vấn đề đã xác nhận | Nguyên nhân trong mã | Cách sửa và bằng chứng |
| --- | --- | --- |
| Dự báo mới có thể được ghi sau 18:00 | `online_learning.run_online` đọc giờ trước khi chờ khóa; `save_state` chưa kiểm sau I/O | Đọc giờ sau khóa; kiểm sau mã hóa và ngay trước `os.replace`, sau flush/fsync. Dự báo mới quá hạn bị từ chối, giữ byte sổ cũ; bản đã đóng băng vẫn khôi phục được sau hạn. Test phủ khóa chậm, học chậm, mã hóa chậm, fsync chậm và đồng hồ được tiêm. |
| Hiệu chuẩn tác tử giải nén cùng sổ 100 lần | `PredictiveEngine.explain` gọi `MetaLearner.calibration_band` cho từng số | Bổ sung `calibration_bands` tính cả vector trong một lượt, gom sai số theo nhóm xác suất. Giữ cách tính trung bình theo kỳ, SE khối 7 kỳ, ngưỡng 60 kỳ, khoảng và cỡ mẫu; pending/non_draw không được chấm. |
| Benchmark Vietlott không dùng component sau cập nhật | `vlm.forecast.hit_benchmark.run_ml` giữ `comp` ngoài vòng lặp, trong khi `MLForecaster.update` thay component | Lấy component hiện hành trong từng kỳ, dự đoán trước rồi cập nhật sau. Test bật/tắt multi-agent và thay nhãn kỳ hiện tại để kiểm không nhìn trước. Không sửa `PROTOCOL` hay chấm lại artifact benchmark đóng băng. |
| Nhánh temporal bị tắt khi thiếu Torch | `_build_arms` kiểm `CAPABILITIES.torch`, dù `TemporalSequenceModel` đã có backend tuyến tính | Quyết định bật/tắt theo `use_temporal`; model tự chọn GRU hoặc đường lui. Test chạy fit/predict tuyến tính thật khi Torch không có. Đây là khung nghiên cứu `ml_engine`, chưa tự đưa vào daily pipeline. |
| ROI nghiên cứu mất số nháy | Hai caller đổi counts thành nhị phân trước tracker; doanh thu dùng số con trúng | Thêm counts tùy chọn và `DailyScore.occurrences_at`; caller truyền counts thật. Brier, log-loss và Hit-Rate vẫn dùng nhãn nhị phân. Với quy ước nội bộ 23/điểm, 80/nháy, hai nháy trả 160 thay vì 80. Nền kinh tế là 27/100 nháy, không phải xác suất có ít nhất một lần. |

### Số đo hiệu năng

Đo riêng khối tạo 100 khoảng hiệu chuẩn của **một mode**, bằng cùng fixture trong RAM, clone cấu trúc bản ghi hợp lệ; không sửa sổ thật:

| Lịch sử | Trước | Sau | Tỷ lệ thời gian trước/sau |
| --- | ---: | ---: | ---: |
| 365 kỳ đã chấm, chưa nén | 0,79699 s | 0,01352 s | khoảng 59 lần |
| 1.000 kỳ, 635 kỳ lưu nén | 29,51125 s | 0,33130 s | khoảng 89 lần |

Đây không phải mức tăng tốc của toàn pipeline và không phải bằng chứng tăng xác suất dự đoán đúng. Thay đổi loại việc giải nén lặp theo từng số; độ phức tạp vẫn tuyến tính theo chiều dài sổ khi số miền cố định. Số nhóm xác suất khác nhau quyết định phần tính thống kê còn lại.

### Ý nghĩa thống kê được giữ

- LOTO: xác suất một số xuất hiện ít nhất một lần khác số nháy kỳ vọng. Chỉ số xác suất và doanh thu dùng đúng đại lượng riêng.
- Không thay đổi cutoff, ngưỡng đề bạt, lịch thử nghiệm, ngân sách alpha hay trọng số sản xuất để làm số đo đẹp hơn.
- Không có kết quả trong đợt sửa này chứng minh dự báo đạt bốn số hoặc vượt chọn ngẫu nhiên. Các cổng ngoài mẫu tiếp tục quyết định việc đề bạt.
- Artifact benchmark cũ có dấu vết source hash khác trạng thái pipeline hiện tại. Cần dựng lại đúng mã theo hash trước khi quyết định artifact đó bị ảnh hưởng; không tự sửa số đo lịch sử.

## 2. Toàn vẹn dữ liệu và độ bền

### Khoảng hở kỳ quay Vietlott

`FallbackDrawSource.fetch` trước đây lấy mã lớn nhất của lô đầu làm cursor. Với repo `[1]`, nguồn chính `[3]`, dự phòng `[2,3]`, dự phòng nhận `since_id=3`; kỳ 2 bị bỏ và các lượt sau tiếp tục bỏ.

Bản sửa giữ bộ đệm theo ID, ưu tiên giá trị nguồn đứng trước và chỉ tăng cursor qua đoạn ID liên tiếp. Nguồn sau lấp khoảng hở rồi nối các kỳ đã chờ trong bộ đệm. Không lưu đoạn vượt khoảng hở chưa lấp. Khởi động không có cursor vẫn nhận phần lịch sử mà nguồn đầu thực sự có.

`SyncPipeline.run` còn tìm khoảng hở **nội bộ** đã lưu từ trước, lùi cursor về trước khoảng hở và chỉ nhận ID thiếu hoặc kỳ mới; dữ liệu chuẩn đã có không bị nguồn chồng lấn ghi đè. Kho thiếu phần đầu không tự bị biến thành full refresh. Nếu các nguồn không cung cấp kỳ cũ còn thiếu, cổng chỉ có thể báo khoảng hở; cần nguồn lịch sử hợp lệ để bù, không nội suy kết quả.

### Correction, journal và cache

Trước sửa, cache được cập nhật rồi journal mới append. Nếu append lỗi, lượt retry lấy cache đã sửa làm baseline nên có thể lọc mất correction của kỳ cũ chưa từng vào journal. Mất cache sau đó làm mất bản sửa.

Bản sửa dùng outbox nhỏ cho từng sản phẩm, chỉ chứa delta với giá trị trước/sau. Outbox được ghi nguyên tử trước khi ghi journal/cache; khởi động lại dùng đối chiếu có điều kiện để hoàn tất. Cache khác giá trị trước/sau và không phải trạng thái trung gian hợp lệ do các bước upsert của giao dịch tạo ra được ghi nhận xung đột, không bị đè bằng một bản pending cũ. Dòng journal lịch sử không có outbox giữ chính sách xung đột cũ.

Luồng ghi là nguồn đã kiểm → delta/outbox bền → journal → cache → xác nhận bền và xóa outbox. Luồng phục hồi kiểm outbox trước; tệp hỏng dừng xử lý thay vì bỏ bằng chứng. Các hook đặt trước upsert kết quả, sản phẩm và bảng giải, sau các bước loại dữ liệu không được xác nhận/ưu tiên nguồn. Không sao chép toàn lịch sử Keno vào journal mỗi lần thăm dò.

Kiểm thử chèn lỗi tại mở tệp, fsync, upsert, giữa ghi số và bảng giải, và khi tạo AppState mới; kiểm cả cache rỗng, cache chuẩn khác và outbox nhiều sản phẩm.

## 3. UI/UX và hệ thiết kế

Các sửa tập trung vào tương tác, giữ palette, số đo shell và cỡ chữ theo hệ thiết kế hiện có.

| Luồng | Lỗi tái hiện | Bản sửa |
| --- | --- | --- |
| Điều hướng bằng chứng | Mũi tên/Enter chọn số ở hàng đã ẩn, khối đóng hoặc active vừa bị lọc | Dùng điều kiện hiển thị thống nhất khi tìm số và khi xác thực active trước thao tác; vẫn cho phép dùng số sau khi mở lại khối. |
| Picker họ cặp | Space chọn một cặp rồi focus rơi về body | Cập nhật `aria-pressed` trên node hiện có thay vì dựng lại picker; giữ focus và trạng thái chọn. |
| Dấu chọn sổ kết quả | Chọn ô riêng rồi chọn cả cặp; bỏ cặp vẫn còn ô sáng hoặc đếm lặp | Lưu map định danh ô → giá trị, hợp nhất dấu ô cùng cặp khi bật/tắt cặp; giữ danh tính qua dựng lại danh sách. |
| Popup chu kỳ gan | `role=dialog` chỉ là div; focus và Tab đi ra sau lớp phủ | Dùng dialog native, nhãn truy cập, focus ban đầu, Tab/Shift+Tab ở biên, Escape/Đóng và phục hồi trigger; đổi mode không mất focus. |

Trang thống kê, trang chủ và sổ kết quả được dựng lại bằng generator. Bảng mô phỏng lấy payload và ledger **đang có**, chỉ đọc; không tạo lại dự báo để phục vụ sửa UI. Khung chung và băm tài nguyên được chốt trên toàn bộ 50 trang để trình duyệt nhận JavaScript mới.

## 4. Kiến trúc, bảo mật và khả năng bảo trì

- **Atomic I/O:** thêm hook tùy chọn trước replace; caller không dùng hook giữ hành vi cũ. Khi hook từ chối, tệp đích cũ còn nguyên và tệp tạm được dọn.
- **API:** hai GET huấn luyện GCN đi qua cùng cổng token/Origin và khai báo OpenAPI như các GET làm mới dự báo. Giữ route, schema phản hồi và hành vi của client được cấp quyền. Tác động availability có điều kiện khi API được mở cho client không tin cậy; mặc định loopback giảm phơi bày.
- **Kiểm thử không ghi dữ liệu thật:** fixtures API dùng thư mục tạm cho data, forecast, calibration và updates. Trước sửa, test với lịch sử tổng hợp 120 kỳ đã ghi đè summary trong cây làm việc; bytes gốc đã được phục hồi.
- **Lint và guard UI:** thêm `strict=True` cho phép ghép hai Series cùng hàng ở lịch Đặc Biệt, xử lý B905 ở baseline. Guard trang chủ còn đòi ba cột 400px bằng nhau trong khi generator và trang baseline đã chuyển sang 2:1:1; cập nhật guard theo hợp đồng hiện hành và đo Chromium 390/1440px: ba thẻ cùng hàng, mô phỏng rộng hơn, cuộn trong khung, toàn trang không tràn.
- **Một chính sách nguồn:** README, template automation và SECURITY khớp chính sách một nguồn chính/hai dự phòng/ngưỡng một nhóm hiện có. Không tự thay ngưỡng sản xuất. SECURITY nêu đúng rủi ro tin cậy một nhóm.
- **Phụ thuộc:** Dependabot theo dõi thêm manifest pip của engine `/vietlott`, dùng lịch và giới hạn PR hiện có.

Rà soát bảo mật dựa trên source và tái hiện offline. Hosted Codex Security Standard scan không thực hiện được do host thiếu preflight và shared reference/scripts. Không có kết luận đã chạy CodeQL, fuzz toàn bộ parser, truy vấn CVE hiện hành hay kiểm tra deployment Cloudflare/API thật trong đợt này.

## 5. Mã thay thế và cách kiểm tra

Các tệp nguồn trong cùng bản vá là mã thay thế đầy đủ, giữ convention Python/JavaScript thuần của kho. Các điểm vào để review:

- `src/atomic_io.py::atomic_write_bytes` và `src/online_learning.py::save_state`, `run_online`.
- `src/xsmb_agents/engine.py::MetaLearner.calibration_bands`, `PredictiveEngine.explain`.
- `vietlott/src/vlm/forecast/hit_benchmark.py::run_ml`.
- `vietlott/src/vietlott_engine/crawler/sources/fallback.py::FallbackDrawSource.fetch` và `crawler/pipeline.py::SyncPipeline.run`.
- `vietlott/src/vlm/updates/service.py`: stage/replay outbox, `sync_matrix`, `sync_product`, `update_product`.
- `src/ml_engine/metrics.py::score_day`, `PerformanceTracker.report`; `main_pipeline.py::step`, `validation.py::evaluate`.
- `src/assets/app-evidence.js`, `src/templates/{frequency_bento,shared_results,stat_pages}.js` và generator modal.

Ví dụ bản sửa benchmark giữ đúng thứ tự dự báo → quan sát → học:

```python
from vietlott_engine.forecast.data import Series
from vlm.forecast.distribution import Law
from vlm.forecast.pipeline import MLConfig, MLForecaster


def run_ml(
    series: Series, start: int, end: int, config: MLConfig, tickets: int,
) -> tuple[list[Law], list[list[list[int]]]]:
    """Dự báo trước mỗi kỳ; chỉ học nhãn sau khi đã ghi luật của kỳ đó."""
    model = MLForecaster(series.product, config)
    model.update(series.head(start))
    laws, portfolios = [], []
    for t in range(start, end):
        comp = model.components['main']
        law = comp.law(str(series.dates[t])[:10], next_id=int(series.draw_ids[t]))
        top, _ = law.top(tickets, max_nodes=config.search_nodes)
        laws.append(law)
        portfolios.append([row['numbers'] for row in top])
        model.update(series.head(t + 1))
    return laws, portfolios
```

Đây là hàm thay thế đầy đủ trong môi trường engine đã cài phụ thuộc. Các bộ số lấy từ đúng trường `numbers` của kết quả `Law.top`.

## 6. Bằng chứng kiểm thử

Kiểm chứng trên Python 3.12, NumPy 2.2.6, pandas 3.0.5, scikit-learn 1.9.1; tính toán số chạy một thread. Kết quả cuối:

| Lớp kiểm chứng | Kết quả và phạm vi |
| --- | --- |
| Python root | Phủ đủ 3.877 ca: nhóm 1 đạt 1.080, nhóm 2 đạt 1.077, nhóm 3 đạt 1.091; nhóm 4 đạt 628 và phát hiện một guard CSS cũ. Đã sửa guard theo bố cục 2:1:1 có sẵn trong generator và chạy lại toàn tệp UI: 322/322 đạt; các ca còn lại không đổi. |
| Engine Vietlott | 759 đạt, 3 bỏ qua, 43 subtest đạt; một cảnh báo TestClient/Starlette deprecated, không có lỗi. |
| JavaScript/jsdom | `npm test --prefix tests/frontend`: 209 đạt, không bỏ qua. |
| Worker | `pytest tests/test_worker*.py -q`: 37 đạt; các ca này cũng thuộc tập root. |
| Chromium | Kiểm toàn 50 trang × hai độ rộng × hai theme: 200 trạng thái, 0 lỗi; kiểm bảng: 124 lượt; kiểm cuối cho điều hướng số/đánh dấu cặp: 20 đạt. |
| Release | `domain_challenger_check.sh`, `number_integrity_check.sh`, `research_release_check.sh`: đạt. Phần còn lại của `release_check.sh` cũng đạt trên cây QA cô lập; bước pytest được chạy riêng để không lặp bộ root. |
| Lint và cú pháp | Ruff theo cấu hình root, Ruff F/B023 engine, compileall, `git diff --check`: đạt. |
| Gói trang | Manifest/hash của 50 trang đồng bộ; `site_assets.py --check` đạt. `production_audit.py --consistency-only --strict`: không critical, không warning; dữ liệu mới nhất 17/10/2026. |
| Review bản vá | Hai vòng review độc lập lõi và journal; các phát hiện sau review đã có test hồi quy và sửa, bao gồm fsync qua cutoff, active bị lọc và pending chứa cả khóa thành công/xung đột. |

Phép đối chiếu Excel kiểm đủ 4.238 kỳ, 114.426 ô số gốc và 114.426 đuôi hai chữ số, giữ đúng độ dài và số 0 đầu. Các phép đảo sửa đổi (mutation) chạy trên bản sao tạm, xác nhận test bắt được lỗi; không mutation source trong lúc chạy kiểm tích hợp.

Lượt pytest tổng hợp trước đó dừng ở 42% mà không có summary nên **không được tính là đạt**. Lỗi chỉ mục tài liệu quan sát trong lượt đó đã được sửa và kiểm lại 2/2. Tập root cuối được chia thành các nhóm tệp không trùng nhau, giữ cùng source; bản sao QA giữ đúng dữ liệu và asset của bản vá. Các cổng huấn luyện/dựng artifact chạy ở cây thử nghiệm khác; sản phẩm phát hành không nhận lại dữ liệu, ledger hoặc model được tạo bởi smoke test.

Để chạy lại các bộ chính từ gốc kho (bật browser khi đã cài Playwright Chromium):

```bash
PYTHONPATH=src:vietlott/src python -m pytest tests -q
(cd vietlott && PYTHONPATH=src:. python -m pytest -q -o addopts='')
npm ci --prefix tests/frontend
npm test --prefix tests/frontend
python -m ruff check src tests scripts
python -m ruff check --select F,B023 vietlott/src vietlott/tests
PYTHONPATH=src:vietlott/src python src/site_assets.py --check
PYTHONPATH=src:vietlott/src python src/production_audit.py --consistency-only --strict
```

Các test Chromium riêng nhận `VN_LOTTERY_CHROMIUM` là đường dẫn executable. Máy QA này dùng bản `chromium_headless_shell` đã cài; browser Chrome đầy đủ bị host chặn socket, không phải lỗi ứng dụng. Kiểm browser toàn trang và 20 ca cuối dùng Chromium thật, không thay bằng mock.


## 7. Checklist duy trì chất lượng

### Kiểm tra khi tiếp tục phát hành ngày 18-10-2026

Bản vá local `6f61eaf2d` / `f269a526b` được khôi phục và đồng bộ với
`ee3002188` trên main. Manifest trang được tạo lại sau khi nhận các bản
cập nhật Vietlott tự động; dữ liệu, ledger và mô hình khớp main từng byte.

Review cuối phát hiện thêm trường hợp replay tự từ chối trạng thái dở dang:
kỳ đã có số nhưng chưa có bảng giải, replay ghi Draw thành công rồi lỗi
trước khi ghi PrizeRecord. Lần khởi động sau coi phần finance chưa có
provenance do chính replay ghi là xung đột. Bản sửa nhận đúng các giá trị
finance đã stage khi baseline chưa có provenance, vẫn từ chối bảng giải
khác. Hai ca fault injection trên InMemory và DuckDB đã đỏ trước sửa,
xanh sau sửa. Bộ recovery/crawler/API/benchmark liên quan chạy lại đạt;
459 ca root liên quan và 209 ca frontend đạt, Ruff root/engine sạch.
CI trên GitHub và triển khai được xác minh riêng khi hoàn tất tích hợp.

CI Windows phát hiện thêm cleanup outbox chạy khi handle tệp tạm còn mở,
làm lỗi unlink che lỗi fsync gốc. Cleanup nay chạy sau khi thoát context
tệp; test mô phỏng quy tắc unlink Windows đã đỏ trước sửa và xanh sau sửa.
Fixture sửa checkpoint cũng đóng rõ kết nối SQLite: context giao dịch của
SQLite chỉ commit/rollback, không tự đóng connection. Không bỏ test Windows.

- [ ] PR thay dự báo phải chứng minh không nhìn trước, cutoff ở ranh giới công bố và khả năng khôi phục bản đã đóng băng.
- [ ] Thay định nghĩa thành phần thì tăng policy/schema theo hợp đồng hiện có; không viết lại ledger để khớp định nghĩa mới.
- [ ] Mô hình mới phải thắng cả đối chứng hằng số và mô hình đương nhiệm trên giao thức ngoài mẫu đã đăng ký; giữ tập kiểm đóng băng.
- [ ] Bổ sung fault injection vào mọi đường ghi dữ liệu bền: lỗi giữa ghi, sau fsync, giữa journal/cache và khi retry sau restart.
- [ ] UI mới phải có kiểm bàn phím với nội dung đang bị lọc/đóng, lưu lựa chọn qua render và mobile hai theme.
- [ ] Chỉ thêm abstraction khi có ít nhất hai luồng thực sự dùng cùng hợp đồng; giữ generator là nguồn chuẩn, tránh vá riêng HTML dẫn xuất.
- [ ] Chạy kiểm gói trang sau generator cuối; asset hash và manifest phải cùng một cây nội dung.
- [ ] Theo dõi phụ thuộc riêng cho root/engine, review các nâng cấp; có thể pin Actions theo SHA trong một PR riêng có xác minh nguồn.
- [ ] Định kỳ xem số đo thời gian từng bước pipeline, peak RSS, số node và độ trễ tương tác trên lịch sử dài; chỉ nhận tối ưu khi output/hợp đồng giữ đúng.
- [ ] Ghi nhận phạm vi chưa kiểm trực tiếp: nền tảng Python/Windows khác môi trường cục bộ, optional ML backends, dữ liệu nguồn đang thay đổi và deployment thật.


## 8. Lộ trình tiếp theo theo mã hiện có

| Ưu tiên | Việc cụ thể | Điều kiện nghiệm thu |
| --- | --- | --- |
| Trước lần đề bạt mô hình tiếp theo | Dựng đúng source hash của benchmark lưu trong `vietlott/reports/vlm/hit-benchmark`; xác định artifact nào thực sự chạy component cũ rồi đăng ký lượt kiểm mới nếu cần. | Không thay `PROTOCOL` hoặc điểm lịch sử; có trace mã, cấu hình và trạng thái component của từng lượt. |
| PR kiến trúc kế tiếp | Tách phần chuẩn bị dữ liệu và render trong các generator lớn `build_landing_page.py`, `build_statistics_dashboard.py`, `build_stat_pages.py`; bắt đầu từ một nhóm trang có cùng payload, giữ `page_output.write_page` làm biên xuất. | DOM/ID, dữ liệu nhúng, điều hướng và token không đổi; bộ 50 trang và kiểm bàn phím tiếp tục đạt. |
| Khi đo hiệu năng định kỳ | Đo riêng giải nén journal, tạo feature, huấn luyện và render; theo dõi cảnh báo phân mảnh DataFrame trong `statistical_matrices.py`, gom tạo cột theo lô nếu profiler xác nhận chi phí đáng kể. | So sánh output với bản tham chiếu trên cùng lịch sử; báo thời gian và peak RSS, không suy ra tăng chất lượng dự báo từ tốc độ. |
| Bảo trì CI | Pin Actions theo SHA đã đối chiếu upstream, thử nâng dependency theo từng manifest; bổ sung runner Windows cho đường file-fsync/replace không có directory-fsync. | Bốn cổng phát hành, test API và phục hồi lỗi I/O đạt trên nền tảng được hỗ trợ; không tắt phép kiểm để nhận nâng cấp. |
| Vận hành API thật | Xác minh cấu hình token/Origin của deployment đang dùng và đo tải cho endpoint huấn luyện/forecast khi triển khai ngoài loopback. | Client không được cấp quyền không kích hoạt huấn luyện; có ngân sách tải và phép đo độ trễ thực tế. |
