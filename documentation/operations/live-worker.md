# Worker đúng giờ: đồng hồ và nguồn phát live.json

## 1. Vì sao có thành phần này

GitHub Pages là hosting **tĩnh** — không có tiến trình nào chạy ở đó. GitHub
Actions chỉ chạy khi có thứ gì kích hoạt nó. Không tồn tại "mã tự chạy lúc
18:15" nếu đồng hồ không nằm ở đâu đó.

Đồng hồ chỉ có thể ở một trong ba chỗ: bộ lập lịch của GitHub, một nơi luôn
bật bên ngoài, hoặc trình duyệt người xem. Trang `docs/live.html` đã dùng chỗ
thứ ba đúng cách — nó tự thăm dò 5 giây một lần trong khung quay số. Nhưng nó
đọc `live.json`, mà tệp ấy do `live-results.yml` ghi, tức lại quay về chỗ thứ
nhất. Trình duyệt không đọc thẳng được trang nguồn vì CORS chặn.

Worker này là chỗ thứ hai.

### Số đo, không phải phỏng đoán

Đo trên chính `daily_update.yml`, 4 ngày 09–12/09/2026, 32 mốc lịch:

| | Kỳ vọng khi đặt lịch | Thực tế đo được |
|---|---|---|
| Tỷ lệ mốc nổ | — | **32/32 = 100 %** |
| Trễ tối thiểu | 49 phút | **2h50m** |
| Trễ trung vị | 2h24m | **4h04m** |
| Trễ tối đa | 5h05m | 4h40m |

Mốc lịch **không** bị bỏ — con số "63 kỳ vọng, 10 thực tế" ở
`on-time-trigger.md` đo trên `live-results.yml`, một workflow khác, và không
suy rộng sang đây được. Vấn đề là các mốc được chỉnh theo độ trễ trung vị 144
phút, trong khi độ trễ thật giờ là ~244 phút. Ngày 12/09, mốc "chính"
`08:51 UTC` nổ lúc `12:22 UTC` = **19:22 giờ VN**; không mốc nào rơi trước
18:43.

Dải trễ ấy đã tự trôi một lần (144 → 244 phút) và sẽ trôi nữa. Chỉnh lại mốc
là cải thiện, không phải đảm bảo. Lịch của Cloudflare nổ đúng phút đã đặt, nên
Worker mới là đảm bảo.

## 2. Kiến trúc

```
Cron Cloudflare ──mỗi phút 18:08-18:59 ICT──▶ scheduled()
                 (và 5 phút/lần 19:00-19:55)
                                                 │ đọc 2 nguồn chính, đồng thuận
                                                 ▼
                                             Workers KV
                                                 │
   docs/live.html ──5 giây/lần──▶ fetch() ───────┘
          │
          └── Worker không trả lời? ──▶ live.json trên nhánh `live`
                                        (GitHub Actions ghi, trễ nhưng có)
```

**GitHub Actions không còn nằm trên đường găng đúng giờ.** Nó vẫn ghi lịch sử
vào kho; trễ bao nhiêu cũng không ảnh hưởng trang live nữa.

## 3. Vì sao chọn Cloudflare Workers

| | Cloudflare Workers | Deno Deploy |
|---|---|---|
| Cron riêng, chính xác | Có | Có |
| Miễn phí, không cần thẻ | Có | Có |
| Kho lưu giữa hai lượt chạy | Workers KV, sẵn trong gói free | Deno KV |
| Rủi ro tuổi thọ | Nền tảng ổn định nhiều năm | Deno Deploy Classic đang chuyển nền |

Chọn Cloudflare vì rủi ro tuổi thọ thấp hơn. Mã trong `worker/src/` cố ý chỉ
dùng `fetch`, `Response` và đúng hai API riêng của nền tảng (`env.LIVE` và
handler `scheduled`), nên chuyển sang Deno Deploy là sửa khoảng 20 dòng trong
`index.js`, không phải viết lại.

## 4. Triển khai: một lệnh

Không cần token GitHub. Không cần thẻ tín dụng. Không phải chép–dán gì.

### Bước 1 — Tài khoản Cloudflare

Đăng ký tại <https://dash.cloudflare.com/sign-up>. Gói Workers Free là đủ.

### Bước 2 — Chạy một lệnh

```bash
cd worker
npm run setup
```

Kịch bản tự làm cả năm việc:

1. đăng nhập Cloudflare (mở trình duyệt nếu chưa),
2. tạo kho KV, **tự đọc id, tự điền** vào `wrangler.toml`,
3. triển khai Worker, **tự đọc địa chỉ, tự điền** vào `docs/live.html`,
4. gọi `/health` để xác minh Worker sống thật,
5. ép một lượt thu thập và báo mấy nguồn trả lời được.

Chạy lại nhiều lần đều an toàn — bước nào xong rồi thì bỏ qua.

Muốn xem trước mà không đụng vào gì:

```bash
npm run setup:dry
```

Bản thử khô không gọi mạng và không sửa tệp nào.

### Bước 3 — Commit

Kịch bản in ra đúng ba dòng cần chạy:

```bash
git add worker/wrangler.toml docs/live.html
git commit -m "worker: trỏ trang live vào Worker đã triển khai"
git push
```

### Nếu kịch bản dừng giữa chừng

Nó **không** báo "xong" khi thất bại. Mọi phép bóc dữ liệu từ đầu ra của
wrangler đều ném lỗi kèm nguyên văn đầu ra, để bạn thấy ngay chỗ hỏng. Trường
hợp cần làm tay, chỉ có hai giá trị:

* id kho KV → thay `THAY_BANG_ID_KV_CUA_BAN` trong `worker/wrangler.toml`
* địa chỉ Worker → điền vào `window.LIVE_WORKER_URL` trong `docs/live.html`,
  nhớ thêm đuôi `/live.json`

### Theo dõi

```bash
cd worker && npx wrangler tail
```

## 5. Chống trôi lệch giữa hai bản mã

Worker chạy JavaScript nên không dùng lại được `src/ingest/sources.py` và
`src/ingest/live_sync.py`. Hai bản cùng một logic là nợ kỹ thuật thật: lệch ở đây
nghĩa là **trang live hiện một dãy số khác với dãy ghi vào lịch sử** — kiểu
sai không bao giờ nổ, chỉ âm thầm mâu thuẫn.

Bốn phép kiểm đối chiếu chạy trong CI, mỗi phép khoá một tầng:

| Phép kiểm | Khoá gì |
|---|---|
| `test_worker_parser_parity.py` | Bóc bảng giải từ HTML, 30 mẫu gồm cả trang độc |
| `test_worker_consensus_parity.py` | Đồng thuận nguồn, 400 ca sinh ngẫu nhiên |
| `test_worker_snapshot_parity.py` | **Toàn bộ payload live.json** kể cả luật chuyển nguồn, 160 ca |
| `test_worker_sources_parity.py` | Danh mục nguồn, thứ tự ưu tiên, địa chỉ |

| `test_worker_handler.py` | Hành vi vận hành: lượt yêu cầu không gọi nguồn, dừng khi đã xong, cron hỏng không đổ, thiếu KV báo rõ, định tuyến |
| `test_worker_setup.py` | Bộ cài đặt một lệnh: bóc id/địa chỉ từ mọi dạng đầu ra wrangler, vá đúng dòng gán, chạy lại an toàn, thử khô không đụng tệp |

Bốn phép đầu đều đã kiểm ngược: đột biến trên bản JS làm chúng đỏ (10 + 10 + 10 đột
biến, tất cả bị bắt). Hai phép kiểm này đã bắt được lỗi thật ngay trong lúc
viết: bảng nhóm nguồn độc lập thiếu bốn mục, và `mketqua.net` quên nối ngày
vào địa chỉ.

Ngoại lệ đã biết: trong `consensus.js`, thứ tự hai phần tử đầu của
`consensus_score` và dấu của phần tử thứ ba là **mã bất khả đạt** với bộ sáu
nguồn cũ — đo trên 9 630 ô sinh ngẫu nhiên, 0 ô mà chúng phân định (chưa đo lại
với bộ ba nguồn từ 13-10-2026). Phép
đối chiếu không phân biệt được chúng; chốt chặn ở đó là chú thích trong mã,
không phải phép kiểm. Ghi rõ để không ai tưởng là đã được khoá.

### Lượt yêu cầu không bao giờ gọi nguồn

Chỉ cron gọi trang nguồn. Lượt yêu cầu của người xem chỉ đọc KV; KV chưa có ảnh
chụp thì Worker trả **503** (JSON có CORS), và trang live coi đó là lỗi rồi đọc
`live.json` dự phòng trên nhánh `live`. Có hai lúc KV rỗng: lần đầu sau khi
triển khai, cho tới lượt cron đầu trong khung quay số; và khi cron hỏng quá 36
giờ (hạn giữ ảnh chụp).

Trước 08-10-2026, KV rỗng thì lượt yêu cầu thu thập ngay, chặn bằng một khoá
trong KV cộng một mốc trong bộ nhớ của isolate. Cả hai đều chỉ là nỗ lực tốt
nhất:

- khoá KV 10 giây chưa từng ghi được, vì KV từ chối `expirationTtl` dưới 60 giây;
- kể cả khi ghi được, KV nhất quán sau, không có đọc-ghi nguyên tử, và kết quả
  "không có" còn được đệm tới 60 giây. Lúc khởi động lạnh, mỗi isolate ở mỗi nơi
  vẫn tự chạy một vòng sáu nguồn.

Đo được: 12 yêu cầu luân phiên hai isolate trên KV rỗng sinh 12 lượt gọi nguồn.
Khoá mạnh (Durable Object) chữa được triệu chứng; bỏ hẳn việc gọi nguồn khỏi lượt
yêu cầu thì không còn gì để khoá. Nay số đo ấy là 0
(`test_viewer_requests_never_call_the_sources`).

### Dừng khi kỳ đã xong

Cron chạy mỗi phút suốt khung quay số. Sau khi đủ 27 ô và đã xác minh, không
còn gì để thu thập, nên Worker dừng gọi nguồn cho tới ngày hôm sau — đo được:
vòng cron đầu tiên 1 lượt gọi (nguồn chính trả trọn kỳ), năm vòng tiếp theo 0 lượt.

Chốt so theo **ngày quay**, không chỉ theo trạng thái. So theo trạng thái thôi
thì ảnh chụp đã xác minh của hôm qua sẽ chặn luôn việc thu thập hôm nay, và hệ
thống đứng im vĩnh viễn sau đúng một ngày thành công.

## 6. Chính sách nguồn: một nguồn chính, hai dự phòng, ẩn danh

### Danh mục (từ 13-10-2026)

| Tầng | Mã | Nhóm | Nguồn |
|---|---|---|---|
| Chính | `P1` | `G1` | `xoso.com.vn` |
| Dự phòng | `F1` | `G2` | `mketqua.net` |
| Dự phòng | `F2` | `G3` | `www.minhngoc.net.vn` |

Danh sách nằm ở **một chỗ duy nhất**: `PRIMARY_SOURCE_NAMES` và
`FALLBACK_SOURCE_NAMES` trong `src/ingest/sources.py`. Bản JS
(`worker/src/sources.js`) bị `tests/test_worker_sources_parity.py` buộc khớp
từng mục, và `src/ingest/reconcile_live_canonical.py` nhập lại thay vì chép.

Năm nguồn đã nghỉ, đo trên runner Actions ngày 12/13-10-2026 bằng
`scripts/ops/diagnose_live_sources.py` (workflow `diagnose-live-sources.yml`):

| Nguồn đã nghỉ | Vì sao |
|---|---|
| `xosothudo.com.vn` | Mẫu đường dẫn chưa từng đúng: cả năm ứng viên đều hỏng ở mọi lượt — nguồn "chính số 1" mà không bao giờ trả gì, nên tầng chính không bao giờ đủ và cả sáu dự phòng bị gọi ở MỌI lượt thăm dò |
| `xskt.vn` | Chặn runner |
| `xosodaiphat.com` | Khi kỳ chưa quay, bóc liên kết "XSMB 12/10/2026" thành giải 7 `12 10 14 10` |
| `hainhay.net` | Hai nhãn giải 7 liền nhau làm mất trọn giải 7 |
| `xosominhngoc.com` | Bản sao của `minhngoc.net.vn`, không thêm bằng chứng độc lập |

Tên các nguồn đã nghỉ vẫn nằm trong `RETIRED_SOURCE_NAMES` để phép kiểm riêng
tư còn quét được chúng. `xskt.vn` vẫn là nguồn **lịch sử** của trang kết quả
truyền thống (`HISTORY_API_SOURCE_NAMES`), không liên quan tới live.

### Khi nào nguồn dự phòng được gọi

Chỉ khi nguồn chính **gặp sự cố** (`sources.primary_has_failed`,
`snapshot.js::primaryHasFailed`):

1. Không bóc được giá trị nào — HTTP hỏng, bị chặn, hay trang đổi bố cục đều
   rơi vào đây.
2. Đã quá **18:40 giờ Việt Nam** (`PRIMARY_COMPLETE_BY`) mà vẫn thiếu ô. Thiếu
   ô TRONG lúc quay là bình thường; quá giờ quay xong mà còn thiếu là nguồn kẹt.

Khi dự phòng được gọi, **chỉ dữ liệu của dự phòng** được hợp nhất: bản rỗng hay
kẹt của nguồn chính không được cầm phiếu ở ô nào
(`test_a_primary_stuck_after_the_deadline_hands_over_to_the_fallbacks`). Ngưỡng
đồng thuận là **một** nhóm (`MIN_AGREEMENT = 1`), nhưng hai dự phòng nói hai số
khác nhau ở một ô là **thế hoà**: ô ấy là xung đột, không được xác minh
(`test_two_disagreeing_fallbacks_leave_the_slot_unverified`).

Lịch sử chuẩn (`Lottery.fetch`, `src/ingest/fetch_results.py`) theo cùng thứ tự:
lấy kết quả trọn vẹn đầu tiên theo ưu tiên, nên ngày thường chỉ một lượt gọi
nguồn chính thay vì hỏi tuần tự cả tám nguồn (~3,3 phút đo ngày 12-10).
`tests/test_source_failover_parity.py` buộc hai bản Python/JS ra cùng kết luận
trên từng ca, kể cả đúng mốc 18:40:00.

### Nguồn còn hiện kỳ trước không phải kết quả hôm nay

Đo trên runner lúc 00:37 ngày 13-10-2026: trang **live** của cả ba nguồn, và trang
theo ngày 13-10 của `mketqua.net`/`minhngoc.net.vn`, đều hiện **trọn kỳ 12-10**.
Sổ chuẩn đã có chốt "trùng khít kỳ đã lưu" (`Lottery`), nhưng bản chụp live và bộ
thăm dò `src/ingest/fetch_results.py` thì chưa: lượt thăm dò gặp trang chưa xoá bảng
sẽ báo kỳ hôm nay "đã xác minh" bằng số của hôm qua, gọi hoàn tất `live_verified`,
rồi ngừng thăm dò trước cả khi kỳ hôm nay bắt đầu.

Nay nguồn có giá trị mà mọi giá trị trùng đúng ô của kỳ đã lưu gần nhất bị coi là
chưa có gì (`sources.shows_previous_draw`, `snapshot.js::showsPreviousDraw`), với
lỗi `StalePage` trong `source_status` — TRƯỚC khi quyết định chuyển nguồn, nên nguồn
chính còn hiện kỳ trước cũng kích hoạt dự phòng. Kỳ trước lấy từ sổ chuẩn
`data/xsmb.csv` (`--history`) ở bản Python. Worker lấy kỳ MỚI NHẤT trong ba nơi:
ảnh chụp đã xác minh của ngày khác còn trong KV, bản giữ ở khoá
`previous-draw.json` (7 ngày, ghi lại trước khi lượt cron đầu của ngày mới ghi đè
`live.json`), và sổ chuẩn `data/xsmb.json` (đệm 5 phút trong KV, đúng đường mà API
Sổ kết quả đã dùng). Sổ chuẩn phủ lúc khởi động lạnh; ảnh chụp KV phủ lúc sổ chuẩn
chưa kịp chốt kỳ hôm qua. Không có nơi nào trả lời thì kỳ đủ ô KHÔNG được chốt
(`complete_provisional`) và cron thu thập tiếp — thiếu bước này, lượt cron đầu
chốt số của hôm qua thành kết quả hôm nay và `alreadySettled` chặn cả ngày. Kỳ mới về dần từ giải nhất (năm chữ số), nên một trang
đang quay trùng kỳ trước ở mọi ô đã về gần như không thể.

### Hàng giải chỉ đọc số của chính nó

Lỗi "trùng lặp giải 7" của trang live: giải 7 là nhãn CUỐI của bảng, và khối
số của nó từng kéo tới nhãn kế tiếp ở tận bảng lô tô hay ô chọn tháng. Khi giải
7 chưa quay, bộ bóc vớ số hai chữ số ở đó — `xoso.com.vn` cho `10 11 12` (ô
chọn tháng), bảng lô tô cho `06 16 24 24`. Nay một hàng là dòng nhãn cộng các
dòng NGAY SAU mà mọi mẩu đều là số ASCII đúng độ rộng của giải; gặp dòng khác
là hết hàng (`_value_line_tokens`, `valueLineTokens`). Mẫu trang thật nằm trong
`tests/fixtures/prize_pages.json` (`thuc_*`), canh bởi
`tests/test_live_prize_rows.py` và `test_worker_parser_parity.py`.

### Ẩn nguồn

Không thứ gì ra tới trình duyệt được mang tên miền nguồn. Bản chụp công khai
chỉ có mã `P1`/`F2` và mã nhóm `G1`…`G3`; thông điệp lỗi bị **bỏ hẳn** chứ
không cắt ngắn, vì tên miền thường nằm ngay đầu chuỗi.

Phép ẩn danh chạy ở **ranh giới ghi**, không phải lúc hiển thị:

* Worker ẩn danh **trước khi ghi vào KV**, nên mọi đường đọc — kể cả đường
  thêm về sau — đều an toàn theo cấu trúc.
* `live_sync.py` và `reconcile_live_canonical.py` ẩn danh trước khi ghi tệp.
* `data/source_audit.json` lưu mã, không lưu tên miền.

`tests/test_source_privacy.py` **quét toàn bộ tải trọng** tìm mọi chuỗi định
danh nguồn, thay vì kiểm từng khoá — tên nguồn nằm rải ở bốn chỗ khác nhau
trong cùng một bản chụp, nên phép kiểm liệt kê sẽ xanh trong khi khoá thứ năm
ai đó vừa thêm thì lộ.

Chi tiết từng nguồn vẫn xem được khi cần: `wrangler tail` cho Worker, và nhật
ký chạy của Actions — cả hai đều không công khai.

## 7. Điều CHƯA kiểm chứng được

**Proxy của môi trường phát triển chặn toàn bộ các trang nguồn.** Phép kiểm ở
mục 5 chạy trên mẫu; các mẫu `thuc_*` dựng lại bố cục đo trên trang thật qua
runner Actions (`diagnose-live-sources.yml`, chạy tay với `draw_date`). Muốn
xem trang lúc ĐANG quay thì chạy workflow ấy trong khung 18:10–18:35.

**Các nguồn có thể chặn IP trung tâm dữ liệu.** Worker gọi từ mạng Cloudflare,
không phải từ máy gia đình. Có ba nguồn ở ba nhóm nên xác suất chặn hết là thấp, nhưng
tôi không đo được từ đây. Bước 4 là phép thử thật đầu tiên: nếu mọi dòng
`source_status` đều có `failed: true`, đó chính là hiện tượng này.

Nếu gặp: đường lùi vẫn nguyên vẹn. Xoá nội dung `window.LIVE_WORKER_URL` là
trang quay về đúng hành vi hôm nay, không mất gì.

## 8. Hạn mức và chi phí

Gói Workers Free: 100 000 lượt gọi/ngày. Cron gọi tối đa ~64 lượt/ngày, và thường ít hơn nhiều vì dừng ngay khi kỳ đã xác minh xong. KV free:
1 000 lượt ghi/ngày (ta dùng ~85) và 100 000 lượt đọc/ngày.

Lượt đọc là chỗ duy nhất có thể chạm trần: mỗi người xem thăm dò 5 giây/lần
trong 40 phút là ~480 lượt. Worker đặt `Cache-Control` theo trạng thái (3 giây
khi đang về số, 60 giây khi đã xác minh) nên biên Cloudflare đỡ phần lớn.

## 9. Gỡ bỏ

```bash
cd worker && npx wrangler delete
```

Rồi xoá nội dung `window.LIVE_WORKER_URL` trong `docs/live.html` (đặt lại
thành `''`). Hệ thống trở
lại đúng trạng thái trước khi có Worker.
