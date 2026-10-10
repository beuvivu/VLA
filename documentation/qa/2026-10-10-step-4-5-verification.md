# Kiểm chứng và khép bước 4–5 — 10-10-2026

## Phạm vi và kết quả

Đối chiếu từng yêu cầu Task 4 và Task 5 của [kế hoạch ML audit](../architecture/2026-10-09-adaptive-forecast-plan.md), từ main `cbcf275612182ea7b5407aa98afdf184c15a001f`. Main chứa merge [PR #150](https://github.com/beuvivu/VLA/pull/150), commit `318ec02088780290f8f88e5a4c1f5e99342a62ce`. Kiểm chứng trong checkout riêng để không trộn các thay đổi giao diện đang làm.

Bước 4 đáp ứng yêu cầu. Bước 5 có một thiếu sót vận hành: CLI không tự ghi hash mã nguồn, dù các artifact ngày 09-10 đã được bổ sung provenance. Bản vá này tự tạo manifest, kiểm tra nguồn không đổi trước khi hoàn tất, và lưu lại hai benchmark mới có manifest tự sinh. Điểm số khớp báo cáo cũ; adaptive tiếp tục mặc định tắt.

## Bước 4: dependency và helper thống kê

| Yêu cầu | Kết quả đối chiếu |
| --- | --- |
| NaN không làm mất p-value hợp lệ | `src/statistical_corrections.py` tính BH trên phần hữu hạn, giữ vị trí thiếu là NaN. |
| Giữ hợp đồng BH hữu hạn, input invalid rõ ràng | Hai wrapper `research_diagnostics.bh_fdr` và `significance_stats._bh_fdr` dùng helper chung; từ chối vector sai chiều và p hữu hạn ngoài `[0,1]`. |
| Bỏ seaborn không caller | Dependency và import đã bỏ; Matplotlib vẫn phục vụ plot. Nhắc seaborn trong docstring không phải caller. |
| Sửa closure B023 | Bind `counts` ở navigation renderer và `page_errors` ở browser checker theo đúng vòng lặp. |
| Giữ API/research/export có caller | `statistical_matrices`, pipeline, release checker, Excel/heatmap exporters và research wrappers vẫn hoạt động. |
| Không gom Wilson khác hợp đồng | Các biến thể zero-trial `(0,1)`, `(0,0)` và `(NaN,NaN)` được giữ riêng. |

Kiểm tra trực tiếp Task 4: 42 passed, 3 pandas PerformanceWarning. Controller chạy riêng nhóm statistical/significance/navigation/ensemble provenance/documentation: 36 passed. Root và engine Ruff đều qua.

## Bước 5: benchmark, provenance, review và tích hợp

| Yêu cầu | Kết quả đối chiếu |
| --- | --- |
| Split, config, seed, ID/date, data hash | 600 kỳ cuối, 400 train và 200 holdout cho mỗi sản phẩm; seed `20261003`; config và package versions được lưu. |
| Incumbent/challenger cùng chronology | Đối soát 21 kết quả sản phẩm, 4.200 dòng holdout của ba artifact cũ; hash/ID/date và trung bình khớp. |
| Chấm trước học | `evaluate_series` dựng law từ tiền tố, chấm label rồi gọi update; regression kiểm tra thay tương lai không đổi điểm kỳ trước. |
| Brier, log gain, Top-k, fair baseline | Trace lưu cả Brier và fair Brier, joint log gain, main-set hits và fair expected hits. Hits không áp dụng cho digit-only, không phải hạng giải. |
| Kiểm định ghép cặp | Năm nhóm HAC/DM/BH trong comparison cũ khớp khi tính lại; so sánh từ chối khác data hash, ID/date hoặc count. |
| Không ghi ledger live hoặc promote | CLI dùng ProductStore tạm và seed, không collector/checkpoint/issue; cả hai lượt mới có `live_scored=0`, `live_certification=false`. |
| Source provenance cho lượt tiếp theo | CLI nay tự ghi manifest 114 file: toàn bộ 113 file Python của `vietlott/src` và runner. |
| Review | Auditor riêng cho mỗi bước; reviewer riêng tái hiện lỗi scan thư mục và xác nhận bản sửa qua 20 test evaluator. Không còn finding Critical/Important trong patch được review. |

### Thiếu sót đã sửa

`vietlott/scripts/evaluate_adaptive.py::_source_provenance` ghi schema version, SHA256 từng file và hash tổng. Đường dẫn POSIX được sort; hash tổng cập nhật bằng `path UTF-8 + NUL + raw file bytes`. Root nguồn lấy từ module pipeline thực sự được import. Toàn bộ Python source được đưa vào để bao phủ cả các dependency gián tiếp như joint-law engine, popularity, inference và evaluator, thay vì chỉ chín module scorer của manifest cũ.

Manifest được chụp trước benchmark và kiểm lại trước `completed_at`. Nếu nguồn thay đổi giữa lượt, báo RuntimeError; báo cáo tiến độ không có dấu hoàn tất. Thư mục thiếu, root là file, lỗi quyền quét thư mục hoặc đọc file đều raise; không âm thầm tạo manifest thiếu nguồn. Không thêm dependency.

Hồi quy: sáu trường hợp thất bại trước khi thêm manifest/check, rồi ba trường hợp thiếu/không đọc được source thất bại trước khi sửa scanner. Sau sửa: 20 evaluator tests passed. Các phép kiểm dùng source tạm và fault injection, không sửa model/ledger production.

### Hai lượt benchmark mới

- [Default, manifest tự sinh](../evaluations/2026-10-10-vietlott-default.json.gz).
- [Adaptive, manifest tự sinh và paired comparison với incumbent](../evaluations/2026-10-10-vietlott-adaptive.json.gz).

Hai lượt mới có 2.800 dòng holdout. Toàn bộ trace và numeric summaries khớp artifact ngày 09-10; timestamps, thời gian chạy và source provenance được ghi cho lượt mới. Default mới chạy không có `--compare-with`, nên không lưu paired comparison; so sánh incumbent của default vẫn nằm trong artifact ngày 09-10. Adaptive mới vẫn lưu paired comparison như cũ. Hash benchmark source của cả hai lượt:

`48cab5373c696868aa12e765c86adc045e8828a8d2e3008dc253c5b8cdb6536f`

Adaptive so incumbent vẫn có q BH tối thiểu `0.6281830088884883`, chưa qua ngưỡng .05. Không thay scoring hoặc bật adaptive theo kết quả hồi cứu này.

Artifact lịch sử được giữ nguyên. Incumbent lưu commit nền/config/data/ID, nhưng không lưu package environment hoặc full-source hash; không gán hồi tố những metadata đó. Hai artifact mới tự ghi manifest theo bytes, không dùng commit SHA để thay thế cho hash mã thực thi.

## Kiểm chứng vận hành

Root full suite: **3.378 passed, 11 skipped, 18 warnings**, 354.70 giây. Warning hiện có thuộc SHAP, pandas fragmentation và Pydantic; các test bị skip không được tính là đã kiểm.

Engine full suite trên mã cuối: **581 passed, 3 skipped, 1 warning**, 134.46 giây. Warning là deprecation từ Starlette test client. Nhóm evaluator có 20 test, bao gồm chín trường hợp hồi quy mới.

Ruff root (`src tests scripts`) và engine (`--select F,B023 src scripts tests`) đều qua. Biên dịch cú pháp toàn bộ **582 file Python được git theo dõi** thành công. Kiểm tra diff không có lỗi whitespace.

Main trước bản vá: [root CI](https://github.com/beuvivu/VLA/actions/runs/37971094517), [engine CI](https://github.com/beuvivu/VLA/actions/runs/37971094754) và [CodeQL](https://github.com/beuvivu/VLA/actions/runs/37971094999) đều success. [Lượt cập nhật Vietlott mới nhất được kiểm](https://github.com/beuvivu/VLA/actions/runs/38010821424) thành công ở collector, forecast ML, lưu kết quả, dựng/lưu trang; bước báo lỗi được skip. [Lượt dựng trang](https://github.com/beuvivu/VLA/actions/runs/38011154283) success. Đây là trạng thái ở thời điểm kiểm, không phải bảo đảm mọi nguồn luôn truy cập được.

[Trang công khai](https://beuvivu.github.io/VLA/vietlott.html) trả HTTP 200; HTML có Jackpot, class bonus và comparison script. Bản vá benchmark không thay giao diện.

## Đối chiếu mục tiêu 4–5 trong yêu cầu ban đầu

VLA là hệ thống phân tích xổ số CPU/NumPy; mục tiêu tự thích nghi và tự phục hồi đã được triển khai theo kiến trúc thực tế trong `vlm/forecast/{adaptation,recovery,models,pipeline,service}.py`: running statistics nhân quả, drift mô tả, challenger chuẩn hóa opt-in, finite checks, staged updates, numerical backoff/fallback, MemoryError retry có giới hạn và đối soát first-issued ledger.

Kho không có pipeline Vision–LLM/CUDA/FSDP hoặc multitask training. Không tuyên bố đã xây CUDA OOM recovery, dtype/layout guessing hoặc dynamic multitask loss. Không tự sửa shape/label sai hay nuốt lỗi lập trình. Chi tiết kiến trúc, lỗi đã tái hiện và giới hạn vẫn nằm trong [báo cáo audit đầy đủ](2026-10-09-adaptive-forecast-audit.md).

## Tái lập

Từ thư mục `vietlott`, sau cài dependency:

```sh
PYTHONPATH=src python scripts/evaluate_adaptive.py --seed-dir data/seed --output /tmp/vietlott-default.json.gz --label repaired-default
PYTHONPATH=src python scripts/evaluate_adaptive.py --seed-dir data/seed --output /tmp/vietlott-adaptive.json.gz --label adaptive-challenger --adaptive --compare-with ../documentation/evaluations/2026-10-09-vietlott-incumbent.json.gz
PYTHONPATH=src python -m pytest tests -o addopts='' -q
```

Lượt mới sẽ tự ghi provenance theo source hiện tại. Muốn so đúng snapshot lịch sử phải dùng cùng seed/hash/split/config đã lưu; kết quả trên seed mới không được gọi là tái lập chính xác snapshot cũ.
