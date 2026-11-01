# Python 3.15, đồng bộ Keno/Bingo18 và tinh gọn vận hành — bằng chứng nghiệm thu (01-11-2026)

## Yêu cầu

Chủ dự án: "nâng cấp các code thuộc version Python cũ lên bản cập nhật mới nhất, tìm nguồn có thể upgrade
bản vietlott, kết quả còn thiếu hụt. Tinh gọn một cách logic và khoa học nhất nhưng không làm giảm hoặc
thay đổi tính năng về hiệu suất, xác suất và các dự đoán… Xây dựng workflow thật chi tiết…"

## 1. Python 3.11/3.12 → 3.15

**Chọn phiên bản.** Bản ổn định mới nhất trong danh mục `actions/setup-python` là 3.15.2. Mọi thư viện có
phần biên dịch đều đã có bánh xe cp315 cho Linux, Windows và macOS (đối chiếu PyPI ngày 01-11-2026), trừ
PyYAML 6.0.3. PyYAML chỉ dùng cho phép kiểm và tự dựng bản thuần Python từ sdist.

Ba bản đang ghim không có bánh xe cho 3.15 nên phải nâng:

| Gói | Cũ | Mới | Lý do |
|---|---|---|---|
| numpy | 2.2.6 | 2.5.4 | 2.2 chỉ tới 3.13 |
| pandas | 3.0.5 | 3.1.0 | 3.0.5 không có cp315 |
| pydantic (core) | 2.11.4 (2.33.2) | 2.14.2 (2.50.2) | core 2.33 không có cp314/cp315 |

**Ghim đúng bản** cả scikit-learn 1.9.1, scipy 1.18.1, joblib 1.6.0 và requests 2.34.2. Gói mô hình lưu bằng
joblib phụ thuộc phiên bản scikit-learn, còn `MODEL_LOAD_ERRORS` nuốt lỗi nạp, nên một bản mới lọt qua khoảng
`>=` có thể làm bước dự báo lặng lẽ coi gói là hỏng.

**Một nguồn phiên bản.** Trước đây 23 bước `setup-python` ghim "3.11", 6 bước ghim "3.12", ruff đọc `py311`
và Docker của engine dùng 3.12. Nay:

- tệp `.python-version` (`3.15`) là nguồn duy nhất, mọi bước đọc qua `python-version-file`;
- ruff `py315`, Docker `python:3.15-slim`;
- ma trận CI của engine kiểm 3.11 (sàn của `requires-python`) và 3.15.

`tests/repo/test_python_version.py` canh việc này (4/4 đột biến đỏ).

Hai job còn ghim tay phiên bản cũ ngay trong workflow, và các bản ấy không có bánh xe cho 3.15, nên lượt chạy
kế sẽ hỏng ở bước cài đặt:

- `verify-published-pages` của `update-data.yml`: numpy 2.2.6, pandas 3.0.5;
- `dashboard-refresh.yml`: pandas 2.2.3, numpy 2.2.6.

Cả hai nay theo bản ghim của `requirements*.txt`, và phép kiểm buộc mọi bản ghim viết thẳng trong workflow
phải trùng nó (đột biến đỏ).

**Mã.** Mọi thay đổi đều cho ra cùng giá trị:

- ruff `UP` an toàn cho 61 tệp: `datetime.UTC`, `collections.abc`, `X | None`, `functools.cache`;
- các API pandas 3.1 báo sắp gỡ: `.weekday` → `.day_of_week`, `inplace=True` → gán lại, bỏ
  `float_precision="round_trip"`;
- mọi chỗ `inplace` đều là khung cục bộ (bản sao hoặc vừa dựng), nên gán lại không đổi đối tượng nào khác thấy.
- `fillna("")` trên cột số (sắp bị cấm) đổi thành đổi kiểu tường minh ĐÚNG những cột có ô thiếu. Kết quả trùng
  giá trị, kiểu và cách in trên pandas 3.0.5 lẫn 3.1.0; `docs/statistics.html` dựng lại trùng từng byte trừ dấu giờ
  "Tạo lúc".

Bộ đọc CSV mặc định của pandas 3.1.0 đúng từng bit trên 350 000 giá trị, còn của 3.0.5 thì không.
`tests/core/test_csv_float_round_trip.py` canh giả định ấy: đỏ trên 3.0.5, xanh trên 3.1.0.

**Chứng minh dự đoán không đổi.** Chạy cùng pipeline sản xuất trên cùng dữ liệu (`--skip-sync`, mọi tham số
như `update-data.yml`):

- (A) mã cũ, Python 3.11, thư viện cũ;
- (B) mã cũ, Python 3.15, thư viện mới;
- (C) mã mới, Python 3.15.

Rồi so 123 tệp đầu ra.

| So sánh | Kết quả |
|---|---|
| Xác suất công bố (`prob` của `predict_next_*`) | trùng **từng bit** giữa A, B và bản production |
| Thứ tự mọi danh sách số | 1 287 cột số trong mọi CSV đầu ra, 0 khác thứ tự |
| 25 danh sách trong sổ phỏng đoán trong ngày | trùng hệt số và thứ tự |
| Số còn lại | lệch tương đối ≤ 10⁻¹¹ (tối đa 2,7·10⁻⁹ ở một chỉ số nghiên cứu): làm tròn dấu phẩy động |
| Mã mới so mã cũ, cùng Python 3.15 (C ↔ B) | 118/121 tệp trùng (61 từng byte, 57 sau khi bỏ dấu thời gian). 3 tệp nhị phân chỉ khác giờ ghi: bảng Excel trùng 22 743/22 743 ô; mô hình meta cùng trạng thái RNG, dự đoán trùng từng bit trên 5 000 hàng |
| Cảnh báo sắp-gỡ của pandas trong log pipeline | 4 034 (B) → 0 (C) |
| Thời gian pipeline | 1 255 s (3.11) và 1 247 s (3.15), chạy song song cùng máy |

Một khác biệt có giải thích. Ở bản B, `predict_next_*` mang thêm ba cột `online_*`, như bản production đang
có. Nguyên nhân: `online_learning` so vector bằng `np.array_equal`, nên lệch một ULP ở thành phần tuyến tính
khiến nó ghi lại tệp bằng chính vector đã công bố trong sổ. Xác suất công bố vẫn trùng từng bit.

Bộ kiểm engine trên 3.15: toàn bộ xanh (304 s).

## 2. Keno/Bingo18 — nguồn lấp 13 ngày thiếu

**Sự cố.** Từ 19-10-2026 vietlott.vn trả thử thách Cloudflare; engine cố ý không vượt. Kho NhanAZ chỉ còn
đăng lại từ trang thứ cấp (`xosominhngoc_net_vn`, `pending`). Hệ quả:

- Keno đứng ở #299797, Bingo18 ở #191942;
- `vlm-results.yml` đỏ 105/117 lượt trong 7 ngày;
- trang vẫn in "kỳ mới nhất 19/10" và "dự báo kỳ kế tiếp" của 13 ngày trước.

**Nguồn tìm được.** Bản sao `vietvudanh/vietlott-data` (engine đã khai là `mirror`) cập nhật tới hôm nay,
không hở mã kỳ nào sau #299797.

| Phép đo | Keno | Bingo18 |
|---|---|---|
| Trùng seed có xuất xứ chính thức | 86 272 / 86 272 | 92 759 / 92 759 |
| Trùng kho NhanAZ (thu thập độc lập, tháng 10) | 1 509 / 1 509 | 1 558 / 1 558 |
| Kỳ mới nhận | tới #301336 (01-11) | tới #193999 (01-11) |

Không lệch trong n kỳ cho cận trên 95% tỉ lệ sai mỗi kỳ là 3/n, tức ≤ 3,5·10⁻⁵.

**Luật (`product_store._vet_fast_mirror`).** Bản sao được nhập khi, đo lại mỗi lượt:

- hồ sơ ≥ 10 000 kỳ chính thức của seed (không đếm dòng trong kho, vì đếm vào là tự chứng nhận);
- đối chiếu ≥ 50 kỳ độc lập trên phần mới;
- 0 lệch. Một kỳ lệch thì loại cả bản sao lượt ấy.

Mọi chốt sẵn có vẫn áp dụng: mâu thuẫn với kỳ đã lưu, ngày tương lai, mã kỳ liên tục, thông báo loại kỳ.
Đột biến: 8/8 đỏ.

**Khoảng hở lịch sử.** Sau khi lấp còn 2 khoảng Keno (74 kỳ ngày 27–28/08/2020, 1 kỳ ngày 18/01/2023) và 20
khoảng Bingo18 (24–25/01/2026). Cả ba nguồn đều không có các kỳ ấy, nên trước đây chúng làm workflow đỏ mãi.

`vietlott/data/seed/known_gaps.json` ghi lại chúng kèm ngày kiểm:

- khoảng nằm trọn trong sổ không còn là lỗi;
- khoảng mới hoặc chỉ trùng một phần vẫn đỏ;
- không thêm hay suy ra số nào.

Đột biến: 2/2 đỏ. Chạy thật: cả hai sản phẩm thoát 0, `error = None`.

**Lượt production thứ hai — hai chỗ phải sửa.** Lượt chạy ngay sau khi gộp đã đưa Keno lên #301336 và
Bingo18 lên #193999, nhưng vẫn đỏ vì hai lý do:

- **Lỗi của cổng.** Phép đối chiếu chỉ so trên phần kho NhanAZ tải từ ngày của kho. Phần ấy toàn kỳ mới hơn
  bản sao, vì bản sao chỉ cập nhật lúc ~00:00 và ~12:00 UTC (đọc từ `process_time` của nó), nên phép đối chiếu
  ra 0 và cổng từ chối. Nay cửa sổ neo theo ngày mới nhất của bản sao (31 ngày).
- **Báo đỏ không có nghĩa.** Engine báo lỗi khi NhanAZ có kỳ mới hơn chưa xác minh, và báo `not_advancing`
  sau 20 phút không tiến. Với nguồn 12 giờ một lần, cả hai đúng gần như suốt ngày. Nay:
  - kỳ đăng lại mới hơn là "chờ xác minh", không phải lỗi;
  - `not_advancing` theo nhịp của nguồn vừa làm kho tiến: 13 giờ với bản sao, 20 phút với nguồn khác.
    "Nguồn vừa làm kho tiến" là nguồn của kỳ có mã lớn nhất vừa nhận (`latest_source`), không phải chuỗi
    ghép mọi nguồn có góp dòng. Ân hạn đo từ lần tiến thật; trong ân hạn, kho mang ngày hôm qua là
    `date_only`, quá ân hạn là `behind_schedule` (hai điểm do Codex chỉ ra, sửa ở `94b79e13`, đột biến 4/4 đỏ).
  - Đỏ còn nghĩa là bản sao đã lỡ một lượt, hoặc có dữ liệu sai.
- Bảng tóm tắt in thêm loại lỗi, chỉ từ một danh sách nhãn cố định.
- Đột biến: 5/5 đỏ.
- Chạy thật từ trạng thái sau gộp: thoát 0; đối chiếu 1 509 / 1 558 kỳ, 0 lệch; 18 kỳ chờ xác minh.

## 3. Tinh gọn không đổi tính năng

- **Commit chỉ đổi giờ dựng.** 78/100 commit dựng trang Vietlott chỉ đổi câu "Bản dữ liệu được dựng lúc
  HH:MM…"; tháng 10 có 548 commit như thế cho `docs/vietlott.html`.
  - `scripts/web/stamp_only_change.py` nhận ra trường hợp ấy, và workflow giữ bản HEAD, không commit.
  - Trang vẫn đúng: câu ấy nói "đây là bản chụp tại lần dựng trang", và nội dung bản chụp không đổi.
  - `tests/repo/test_vietlott_release_snapshot.py` chạy nguyên bước trên git cục bộ; 3/3 đột biến đỏ.
- **Phép kiểm chập chờn `tests/frontend/live-polling.test.mjs`.** Phép kiểm này đã làm đỏ `main` ngày 31-10
  (commit `6abd5ea0`).
  - Nguyên nhân: lượt tải do `timers.advance` mở còn chạy khi `t.after` đóng cửa sổ, rồi `schedule()` đọc
    document đã đóng.
  - Tái hiện chắc chắn bằng `json()` chậm một macrotask: đúng thông báo lỗi trên CI.
  - Sau khi sửa (chờ hàng đợi cạn rồi mới đóng): 0 lỗi; bản thật xanh 5/5 lượt.

## 4. Bản đồ workflow

[`operations/workflow-map.md`](../operations/workflow-map.md) gồm:

- bốn chuỗi theo thứ tự từng bước;
- sơ đồ và bảng 27 workflow dựng từ YAML (`scripts/ops/workflow_map.py`).

`tests/repo/test_workflow_map.py` canh:

- tên `workflow_run` có thật;
- tệp được gọi qua API có thật và khai `workflow_dispatch`;
- không có vòng kích hoạt;
- mọi loại sự kiện của bộ hẹn giờ ngoài đều có trong tài liệu;
- bản đồ khớp YAML.

6/6 đột biến đỏ.
