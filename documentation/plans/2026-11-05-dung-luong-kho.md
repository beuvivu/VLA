# Kế hoạch giữ dung lượng kho trong ngưỡng an toàn (05-11-2026)

**Trạng thái:** CHỜ CHỦ DỰ ÁN DUYỆT. Không bước nào dưới đây đã được thực hiện, trừ mục «Đã làm».

**Mục tiêu:** giữ gói git của kho dưới 1 GB. Mỗi runner Actions và mỗi bản clone đều tải toàn bộ lịch sử.
GitHub khuyên giữ kho dưới 1 GB, và rất nên dưới 5 GB.

## Số đo

Đo trên bản clone đầy đủ ngày 05-11-2026. Lệnh đo nằm ở cuối tài liệu.

| Số đo | Giá trị |
|---|---|
| Gói git hiện tại | 642 MB |
| Tăng 7 ngày (29-10 → 05-11), tính theo gói mỏng (đúng lượng git phải lưu thêm) | 41 MB |
| Tăng sau đợt dọn 04-11 (PR #206 gỡ 64 MB bảng JSON bản sao và 19 ảnh không dùng) | ≈ 4 MB trong 1,2 ngày, tức ≈ 3 MB/ngày ≈ 23 MB/tuần |
| Dự báo ở tốc độ sau dọn | chạm 1 GB sau ≈ 4 tháng, ≈ 1,8 GB sau một năm |

Bản rà soát ngày 05-11 từng báo «74 MB/tuần, chạm 1 GB sau 5 tuần». Số ấy cộng kích thước nén của từng
blob riêng lẻ, nên bỏ qua delta giữa các phiên bản. Cửa sổ đo cũng còn chứa các tệp đã gỡ ngày 04-11. Số
đúng là số gói mỏng ở bảng trên.

Phần tăng chủ yếu sau đợt dọn, tính theo kích thước nén của blob mới:

| Nhóm | Ước tính / ngày | Vì sao lớn |
|---|---|---|
| `docs/` | ≈ 10 MB | ~40 trang dựng lại mỗi lượt chốt. Năm trang Đặc Biệt tuần/tháng/năm và hai trang cặp lớn mỗi trang ~2,4 MB thô. |
| `data/excel/` | ≈ 1,6 MB | xlsx là zip đã nén, nên git gần như không lấy được delta giữa hai phiên bản. Ba tệp chính ≈ 5 MB thô mỗi phiên bản. |
| `data/stats/`, `data/research/` | ≈ 1,1 MB mỗi nhóm | Hai bảng lớn nhất: `research/crosslag_positional/crosslag_rules.csv` (3,5 MB/tuần) và `stats/conditional/loto_nextday_given_special_long.csv` (2,8 MB/tuần). |
| `vietlott/data/` | ≈ 1,2 MB | Sổ kết quả và trạng thái engine. |

Hai cột không cùng thước: «≈ 3 MB/ngày» là gói mỏng, đã tính delta, còn bảng này cộng blob nén từng cái
một. Bảng chỉ dùng để xếp hạng nguồn tăng, không cộng lại thành tốc độ tăng.

## Đã làm (PR #212)

- Lượt pipeline chạy lại trên cùng dữ liệu không còn ghi lại tệp chỉ đổi giờ. Lượt 19:33 ngày 05-11 từng
  ghi lại 125 tệp. Phần này chủ yếu bớt commit rác; dung lượng tiết kiệm không lớn, vì git lưu delta rất
  tốt cho các bản gần giống nhau.
- Sắp xếp ổn định toàn `src`, nên hàng hoà điểm không còn đảo qua lại giữa các lượt chạy.

## Các phương án (chưa làm)

Xếp theo tỉ lệ lợi ích trên rủi ro.

### 1. Theo dõi tốc độ tăng: nhỏ, nên làm trước

Thêm một bước hằng tuần, đặt cạnh `dependency-audit.yml`, đo gói mỏng của 7 ngày (lệnh ở cuối) và ghi vào
tóm tắt job. Đỏ khi vượt ngưỡng, ví dụ 40 MB/tuần. Không đổi gì trong kho; chỉ báo sớm khi một thay đổi
làm kho phình.

### 2. xlsx: chỉ ghi khi dữ liệu đổi: đã có; cân nhắc thôi theo dõi trong git

`save_xlsx` đã giữ tệp khi dữ liệu không đổi. Bước tiếp theo là thôi lưu xlsx trong git và dựng chúng trong
artifact Pages, để vẫn tải được từ trang.

- Phải kiểm: ai đọc `data/excel/*.xlsx` từ git (`ingest.validate_excel_integrity`,
  `number_integrity_check.sh`, liên kết tải trên trang).
- Lợi: ≈ 1,6 MB/ngày.

### 3. Hai bảng nghiên cứu/thống kê lớn: vừa

Kiểm `crosslag_rules.csv` và `loto_nextday_given_special_long.csv` có trang nào đọc toàn bảng không.

- Nếu chỉ phục vụ chẩn đoán: ghi bản cắt (top-N theo q) vào git, bản đầy đủ đưa sang artifact của workflow.
- Nếu trang cần đủ: giữ nguyên.
- Lợi: ≈ 0,9 MB/ngày.

### 4. Thôi theo dõi trang dựng sẵn trong `docs/`: lớn, cần quyết định kiến trúc

Đây là đòn bẩy chính, khoảng 2/3 phần tăng. Trang được dựng trong CI và triển khai thẳng từ artifact;
`pages.yml` đã tải `docs/` lên bằng `upload-pages-artifact`. Phải giải quyết:

- `docs/live.html` là trang viết tay, phải tiếp tục được theo dõi; `refresh_live_page` bọc lại khung cho nó.
- Bộ kiểm `tests/site` và job `verify-published-pages` đọc `docs/` từ kho. Chúng phải chạy trên bản vừa
  dựng trong CI.
- `vietlott-results.yml` dựng tám trang Vietlott từ cache engine, không gọi mạng, rồi commit. Cần một chỗ
  ghép hai nguồn trang trước khi triển khai, giữ luật «`pages.yml` là workflow triển khai duy nhất».
- Bộ kiểm PR khi ấy không còn thấy trang đã xuất bản. Cần dựng trang trong CI của PR, thêm vài phút.
- Lợi: ≈ 10 MB/ngày nén từng blob, tức phần lớn tốc độ tăng.
- Rủi ro: cao. Nên làm theo từng chặng, mỗi chặng một PR, và giữ đường lùi (theo dõi lại `docs/`).

### 5. Viết lại lịch sử để gỡ blob cũ: chỉ khi thật cần

Dùng `git filter-repo` gỡ các phiên bản cũ của `docs/` và `data/` khỏi lịch sử. Gói giảm mạnh ngay, nhưng
phải đẩy đè `main`: mọi bản clone, nhánh và PR đang mở đều phải dựng lại. Chỉ nên làm một lần, sau các
phương án 2–4, và khi chủ dự án đồng ý rõ ràng.

## Đề xuất

1. Làm phương án 1 ngay. Đo lại sau hai tuần, khi PR #212 đã chạy: số đo sau dọn mới chỉ có 1,2 ngày.
2. Nếu tốc độ còn trên ~20 MB/tuần: làm phương án 3, rồi 2.
3. Phương án 4 chỉ làm khi kho tiến gần 1 GB. Viết thiết kế riêng trước (`documentation/architecture/`).
4. Phương án 5 không làm, trừ khi chủ dự án yêu cầu.

## Lệnh đo

```bash
# Gói mỏng: lượng git thật sự phải lưu thêm từ một mốc thời gian.
base=$(git rev-list -1 --before="2026-10-29T19:37:48Z" origin/main)
printf 'origin/main\n^%s\n' "$base" | git pack-objects --stdout --thin --revs -q | wc -c

# Xếp hạng nguồn tăng (cộng blob nén từng cái, không cộng delta).
git rev-list --objects origin/main ^"$base" \
  | git cat-file --batch-check='%(objecttype) %(objectsize:disk) %(rest)' \
  | awk '$1=="blob"{split($3,p,"/"); d[p[1]"/"p[2]]+=$2} END{for(k in d) printf "%8.1f MB %s\n", d[k]/1e6, k}' \
  | sort -rn | head
```
