# Kế hoạch giữ dung lượng kho trong ngưỡng an toàn (05-11-2026, đo lại 06-11-2026)

**Trạng thái:**
- Phương án 1 (theo dõi hằng tuần) đã làm ngày 06-11-2026, theo duyệt của chủ dự án.
- Phương án 3 (hai bảng nghiên cứu lớn) đã làm ngày 07-11-2026, theo duyệt của chủ dự án.
- Phương án 2, 4 và 5 CHỜ CHỦ DỰ ÁN DUYỆT.

**Mục tiêu:** giữ gói git của kho dưới 1 GB. GitHub khuyên giữ kho dưới 1 GB, và rất nên dưới 5 GB.

Mọi bản clone đầy đủ đều tải toàn bộ lịch sử. Trên Actions, ba job làm việc ấy mỗi lượt:
- `canonical` và `update` của `update-data.yml`;
- `dashboard-refresh.yml`.

Mọi job khác chỉ lấy commit cuối (`fetch-depth` mặc định là 1). Bản đầu của tài liệu này viết «mỗi runner
đều tải toàn bộ lịch sử»: sai.

## Số đo

Đo ngày 06-11-2026 bằng `scripts/ops/repo_growth.py`, trên bản clone đầy đủ của `main`: 2 890 commit,
tới `791f40baf` lúc 21:26 giờ VN. Lệnh đo nằm ở cuối tài liệu.

| Số đo | Giá trị |
|---|---|
| Gói git | 608 MB (580 MiB) |
| Tăng 7 ngày (30-10 → 06-11), tính theo gói mỏng (đúng lượng git phải lưu thêm) | 50,1 MB |
| Tăng mỗi ngày từ 25-10 tới 04-11 (trước và trong ngày dọn) | 7–10 MB (riêng 24-10: 16 MB) |
| Tăng ngày 05-11, ngày đủ đầu tiên sau đợt dọn | 4,4 MB |
| Tăng ngày 06-11 (có PR #212 và một lượt chạy lại) | 5,5 MB |
| Dự báo | ở 4,4 MB/ngày, chạm 1 GB sau ≈ 89 ngày (≈ 3 tháng); ở tốc độ tuần qua (7,2 MB/ngày), sau ≈ 55 ngày |

Đợt dọn ngày 04-11 là PR #206: gỡ 64 MB bảng JSON bản sao và 19 ảnh không dùng.

### Đính chính số đo ngày 05-11

Bản đầu của tài liệu này đo trên bản clone NÔNG của phiên làm việc, nên ba số sai:

- **«Gói 642 MB»** là gói của bản nông (642 MiB, dồn qua nhiều lần fetch). Bản đầy đủ là 580 MiB, tức
  608 MB.
- **«41 MB trong 7 ngày»**: chuỗi cha thứ nhất của bản nông chỉ còn tới 01-11. Vì thế mốc «7 ngày trước» rơi
  vào một commit nhánh phụ ngày 24-10.
- **«≈ 3 MB/ngày sau đợt dọn»** đo trên 1,2 ngày, trước lượt chạy lại và PR #212. Ngày đủ đầu tiên sau đợt
  dọn là 4,4 MB.

Số «74 MB/tuần» của bản rà soát trước đó cũng sai, vì nó cộng `%(objectsize:disk)` của từng blob. Phép cộng
ấy bỏ qua delta. Nó còn nặng thêm vì gói của máy chủ giữ bản MỚI nhất nguyên vẹn và lưu bản cũ thành delta.

Kịch bản đo nay từ chối bản nông (thoát 2) và chọn mốc theo chuỗi cha thứ nhất. Hai luật này được ghim trong
`tests/repo/test_repo_growth.py`.

## Nguồn tăng

Bảng chia CHÍNH gói mỏng. Chỉ mục của gói cho biết mỗi đối tượng chiếm bao nhiêu byte, đã tính delta, nên
các dòng cộng lại đúng bằng phần tăng. «Sau dọn» là 1,9 ngày, từ 05-11 0:00 tới 06-11 21:26 giờ VN, tổng
10,2 MB.

| Nhóm | 7 ngày (30-10 → 06-11) | Sau dọn |
|---|---|---|
| `data/stats` | 12,7 MB (25%) | 2,8 MB (27%) |
| `data/research` | 9,1 MB (18%) | 2,8 MB (28%) |
| `images` | 8,4 MB (17%) | 0,4 MB (4%) |
| `docs` | 7,6 MB (15%) | 1,4 MB (14%) |
| `data/excel` | 4,2 MB (8%) | 1,4 MB (14%) |
| `data/evaluation` | 2,4 MB (5%) | 0,1 MB (1%) |
| `data/soi_cau` | 1,6 MB (3%) | 0,4 MB (4%) |

Tệp lớn nhất sau dọn:

| Tệp | MB | Tỉ phần |
|---|---|---|
| `data/research/crosslag_positional/crosslag_rules.csv` | 1,5 | 15% |
| `data/stats/conditional/loto_nextday_given_special_long.csv` | 0,9 | 9% |
| `data/excel/xsmb.xlsx` | 0,7 | 7% |
| `data/excel/xsmb-2-digits.xlsx` | 0,5 | 5% |
| `data/research/legacy_extensions/pair_recency_loto.csv` | 0,4 | 4% |
| `data/soi_cau/path_ui/paths_loto_stable.csv` | 0,3 | 3% |

Bản đầu của tài liệu xếp `docs/` đầu bảng (≈ 10 MB/ngày, «khoảng 2/3 phần tăng»). Số ấy cũng cộng blob nén
từng cái. Theo gói mỏng, `docs/` chỉ chiếm khoảng 15%.

## Đã làm

### PR #212

- Lượt pipeline chạy lại trên cùng dữ liệu không còn ghi lại tệp chỉ đổi giờ. Lượt 19:33 ngày 05-11 từng
  ghi lại 125 tệp. Phần này chủ yếu bớt commit rác; dung lượng tiết kiệm không lớn, vì git lưu delta rất
  tốt cho các bản gần giống nhau.
- Sắp xếp ổn định toàn `src`, nên hàng hoà điểm không còn đảo qua lại giữa các lượt chạy.

### Phương án 1 (06-11-2026)

- **Workflow:** `.github/workflows/repo-growth.yml`, chạy thứ Hai 10:41 giờ VN và chạy tay được. Nó lấy bản
  clone đầy đủ rồi gọi `scripts/ops/repo_growth.py --days 7 --limit-mb 40`.
- **Trang tóm tắt** của lượt chạy có: gói, phần tăng 7 ngày, số ngày tới 1 GB, và phần tăng theo thư mục.
- **Đỏ** khi kho tăng quá 40 MB/tuần.
- **Lượt đầu (thứ Hai 09-11) nhiều khả năng đỏ.** Cửa sổ bắt đầu 10:41 ngày 02-11, nên còn chứa phần lớn ba
  ngày 02–04-11, trước và trong ngày dọn (tối đa ≈ 26 MB). Lượt 16-11 là tuần đầu tiên nằm trọn sau đợt dọn
  và PR #212.

### Phương án 3 (07-11-2026): hai bảng nghiên cứu lớn, lợi ước tính ≈ 24% (≈ 1,3 MB/ngày)

Hai bảng chỉ có trang Phòng nghiên cứu đọc, và trang chỉ hiện 10 dòng của mỗi bảng. Ngoài trang, chỉ
`research_release_check.sh` đọc chúng; kịch bản ấy tự chạy hai phòng thí nghiệm trước khi kiểm.

| Bảng đầy đủ (ra khỏi git) | Bản cắt (git theo dõi, trang đọc) |
|---|---|
| `crosslag_rules.csv`, 5 832 quy tắc, 3,2 MB | `crosslag_rules_top.csv`, 199 dòng, 107 KB (`crosslag_positional_lab.cut_table`) |
| `loto_nextday_given_special_long.csv`, 10 000 ô, 1,8 MB | `current_special_next_loto.csv`, 20 dòng, 4 KB (`conditional_nextday.current_special_rows`) |

- **Bản cắt của bảng vị trí chéo** giữ ba loại dòng: mọi quy tắc qua cổng nghiên cứu, 100 dòng đầu theo thứ tự
  của trang, và 100 quy tắc có p huấn luyện nhỏ nhất.
- **Bản cắt của bảng có điều kiện** là 20 con LOTO của trạng thái Đặc Biệt hiện tại. Tệp này đã có sẵn từ
  trước; trang chuyển sang đọc nó.
- **Bảng đầy đủ** vẫn được sinh mỗi lượt. Nó nằm trong `.gitignore`, và `update-data.yml` tải nó lên artifact
  `research-full-tables-*`, giữ 30 ngày.
- **Kiểm chứng:**
  - trang dựng từ hai bản cắt trùng từng byte với trang đã xuất bản;
  - chạy lại hai phòng thí nghiệm trên dữ liệu thật ra tệp trùng từng byte với tệp pipeline đã ghi;
  - `tests/research/test_research_table_cuts.py` buộc trang dựng chỉ từ tệp git theo dõi phải trùng trang
    dựng từ bảng đầy đủ.
- **Đo lại** ở lượt theo dõi thứ Hai 16-11. Ước tính tốc độ giảm từ ≈ 4,4 xuống ≈ 3,4 MB/ngày, và kho chạm
  1 GB sau ≈ 115 ngày thay vì ≈ 89.

## Các phương án còn lại (chưa làm)

Xếp theo tỉ lệ lợi ích trên rủi ro. Phần lợi là tỉ phần của phần tăng sau dọn ở bảng trên.

### 2. xlsx: thôi theo dõi trong git: vừa, lợi ≈ 13% (≈ 0,7 MB/ngày)

`save_xlsx` đã giữ tệp khi dữ liệu không đổi. xlsx là zip đã nén, nên git gần như không lấy được delta giữa
hai phiên bản. Bước tiếp theo là thôi lưu xlsx trong git và dựng chúng trong artifact Pages, để vẫn tải
được từ trang.

Phải kiểm ai đọc `data/excel/*.xlsx` từ git:
- `ingest.validate_excel_integrity`;
- `number_integrity_check.sh`;
- liên kết tải trên trang.

### 4. Thôi theo dõi trang dựng sẵn trong `docs/`: lớn, lợi ≈ 15% (≈ 0,8 MB/ngày)

Trang được dựng trong CI và triển khai thẳng từ artifact: `pages.yml` đã tải `docs/` lên bằng
`upload-pages-artifact`. Bỏ theo dõi `docs/` thì phải giải quyết bốn việc:

- `docs/live.html` là trang viết tay, phải tiếp tục được theo dõi; `refresh_live_page` bọc lại khung cho nó.
- Bộ kiểm `tests/site` và job `verify-published-pages` đọc `docs/` từ kho. Chúng phải chạy trên bản vừa
  dựng trong CI.
- `vietlott-results.yml` dựng tám trang Vietlott từ cache engine, không gọi mạng, rồi commit. Cần một chỗ
  ghép hai nguồn trang trước khi triển khai, giữ luật «`pages.yml` là workflow triển khai duy nhất».
- Bộ kiểm PR khi ấy không còn thấy trang đã xuất bản. Cần dựng trang trong CI của PR, thêm vài phút.

Rủi ro cao mà lợi chỉ ≈ 15%, nên phương án này không còn là đòn bẩy chính như bản đầu viết.

### 5. Viết lại lịch sử để gỡ blob cũ: chỉ khi thật cần

Dùng `git filter-repo` gỡ các phiên bản cũ của `docs/` và `data/` khỏi lịch sử. Gói giảm mạnh ngay, nhưng
phải đẩy đè `main`: mọi bản clone, nhánh và PR đang mở đều phải dựng lại. Chỉ nên làm một lần, sau các
phương án 2–4, và khi chủ dự án đồng ý rõ ràng.

## Đề xuất

1. Đọc lượt theo dõi thứ Hai 16-11, tuần đầu nằm trọn sau đợt dọn và sau phương án 3.
2. Làm phương án 2. Cộng với phương án 3, hai phương án là ≈ 37% phần tăng sau dọn. Ước tính tốc độ giảm từ
   ≈ 4,4 xuống ≈ 2,8 MB/ngày, và kho chạm 1 GB sau ≈ 140 ngày thay vì ≈ 89.
3. Phương án 4 chỉ làm khi 2 và 3 chưa đủ. Viết thiết kế riêng trước (`documentation/architecture/`).
4. Phương án 5 không làm, trừ khi chủ dự án yêu cầu.

## Lệnh đo

Chạy trên bản clone ĐẦY ĐỦ. Bản nông bị từ chối, vì nó cho số sai mà trông hợp lý.

```bash
git clone --bare --single-branch --branch main https://github.com/beuvivu/VLA vla.git

# Phần tăng 7 ngày gần nhất, chia theo thư mục.
python3 scripts/ops/repo_growth.py --repo vla.git --ref main --days 7 --summary /dev/null

# Đúng các số của tài liệu này: ghim commit đỉnh 06-11 21:26 giờ VN.
python3 scripts/ops/repo_growth.py --repo vla.git --ref 791f40baf --now 2026-11-06T14:26:32+00:00 \
  --days 7 --summary /dev/null
python3 scripts/ops/repo_growth.py --repo vla.git --ref 791f40baf --now 2026-11-06T14:26:32+00:00 \
  --days 1.8934 --by-file --top 15 --summary /dev/null
```
