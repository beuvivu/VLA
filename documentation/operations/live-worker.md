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
                                                 │ đọc 6 nguồn, đồng thuận
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

## 4. Triển khai (một lần, ~5 phút)

Không cần token GitHub. Không cần thẻ tín dụng.

### Bước 1 — Tài khoản

Đăng ký tại <https://dash.cloudflare.com/sign-up>. Gói Workers Free là đủ.

### Bước 2 — Tạo kho KV

Worker không có bộ nhớ riêng giữa các lượt chạy, nên không có kho này thì cron
thu thập xong sẽ mất trắng.

```bash
cd worker
npx wrangler login
npx wrangler kv namespace create LIVE
```

Lệnh cuối in ra một `id`. Mở `worker/wrangler.toml` và thay
`THAY_BANG_ID_KV_CUA_BAN` bằng `id` ấy.

### Bước 3 — Triển khai

```bash
npx wrangler deploy
```

In ra địa chỉ dạng `https://vla-live.<ten-cua-ban>.workers.dev`.

### Bước 4 — Kiểm ngay

```bash
curl -s https://vla-live.<ten-cua-ban>.workers.dev/health
```

Ngoài khung quay số thì `has_snapshot` có thể là `false` — đó là bình thường.
Gọi `/live.json` sẽ ép thu thập ngay một lượt:

```bash
curl -s https://vla-live.<ten-cua-ban>.workers.dev/live.json | head -20
```

Cần thấy `"schema_version": 2` và danh sách `source_status` sáu dòng. Nếu mọi
dòng đều có `error` thì xem mục 6.

### Bước 5 — Trỏ trang live vào Worker

Mở `docs/live.html`, tìm dòng gần đầu:

```js
window.LIVE_WORKER_URL = '';
```

Điền địa chỉ vừa có, kèm đuôi `/live.json`:

```js
window.LIVE_WORKER_URL = 'https://vla-live.<ten-cua-ban>.workers.dev/live.json';
```

Commit và đẩy lên `main`. Để trống dòng ấy thì trang chạy **y như trước** —
đọc `live.json` do GitHub Actions ghi.

## 5. Chống trôi lệch giữa hai bản mã

Worker chạy JavaScript nên không dùng lại được `src/sources.py` và
`src/live_sync.py`. Hai bản cùng một logic là nợ kỹ thuật thật: lệch ở đây
nghĩa là **trang live hiện một dãy số khác với dãy ghi vào lịch sử** — kiểu
sai không bao giờ nổ, chỉ âm thầm mâu thuẫn.

Bốn phép kiểm đối chiếu chạy trong CI, mỗi phép khoá một tầng:

| Phép kiểm | Khoá gì |
|---|---|
| `test_worker_parser_parity.py` | Bóc bảng giải từ HTML, 30 mẫu gồm cả trang độc |
| `test_worker_consensus_parity.py` | Đồng thuận nguồn, 400 ca sinh ngẫu nhiên |
| `test_worker_snapshot_parity.py` | **Toàn bộ payload live.json**, 120 ca |
| `test_worker_sources_parity.py` | Danh mục nguồn, thứ tự ưu tiên, địa chỉ |

| `test_worker_handler.py` | Hành vi vận hành: chặn khuếch đại, cron hỏng không đổ, thiếu KV báo rõ, định tuyến |

Bốn phép đầu đều đã kiểm ngược: đột biến trên bản JS làm chúng đỏ (10 + 10 + 10 đột
biến, tất cả bị bắt). Hai phép kiểm này đã bắt được lỗi thật ngay trong lúc
viết: bảng nhóm nguồn độc lập thiếu bốn mục, và `mketqua.net` quên nối ngày
vào địa chỉ.

Ngoại lệ đã biết: trong `consensus.js`, thứ tự hai phần tử đầu của
`consensus_score` và dấu của phần tử thứ ba là **mã bất khả đạt** với bộ sáu
nguồn hiện tại — đo trên 9 630 ô sinh ngẫu nhiên, 0 ô mà chúng phân định. Phép
đối chiếu không phân biệt được chúng; chốt chặn ở đó là chú thích trong mã,
không phải phép kiểm. Ghi rõ để không ai tưởng là đã được khoá.

### Chặn khuếch đại yêu cầu

Nhánh "KV rỗng thì thu thập ngay" là đúng cho lần gọi đầu sau khi triển khai.
Nhưng nếu KV ghi hỏng, nó biến thành: mỗi người xem, 5 giây một lần, dội sáu
lượt vào trang nguồn — đúng lúc các trang ấy tải nặng nhất trong ngày. Mười
người xem là hơn 700 lượt mỗi phút.

Có **hai** lớp khoá, và cần cả hai:

| Lớp | Phạm vi | Mất tác dụng khi |
|---|---|---|
| Khoá trong KV | Toàn cầu | Chính KV đang hỏng |
| Mốc trong bộ nhớ | Một isolate | Isolate bị tái tạo |

Bản đầu chỉ có lớp KV. Đo được: với KV ghi hỏng, 12 lượt truy cập sinh **72**
lượt gọi ra nguồn — tức chốt chặn bốc hơi đúng lúc cần nhất. Sau khi thêm lớp
thứ hai: 12 lượt truy cập, **6** lượt gọi, đúng một vòng thu thập.

## 6. Điều CHƯA kiểm chứng được

**Bộ phân tích chưa từng chạy trên HTML thật trong môi trường dựng.** Proxy
của môi trường phát triển chặn toàn bộ sáu trang nguồn (`curl` trả `000`). Mọi
phép kiểm ở mục 5 chạy trên mẫu dựng tay và dữ liệu sinh ra, **không** phải
trang thật hôm nay.

**Các nguồn có thể chặn IP trung tâm dữ liệu.** Worker gọi từ mạng Cloudflare,
không phải từ máy gia đình. Có sáu nguồn nên xác suất chặn hết là thấp, nhưng
tôi không đo được từ đây. Bước 4 là phép thử thật đầu tiên: nếu cả sáu dòng
`source_status` đều có `error`, đó chính là hiện tượng này.

Nếu gặp: đường lùi vẫn nguyên vẹn. Xoá nội dung `window.LIVE_WORKER_URL` là
trang quay về đúng hành vi hôm nay, không mất gì.

## 7. Hạn mức và chi phí

Gói Workers Free: 100 000 lượt gọi/ngày. Cron gọi ~85 lượt/ngày. KV free:
1 000 lượt ghi/ngày (ta dùng ~85) và 100 000 lượt đọc/ngày.

Lượt đọc là chỗ duy nhất có thể chạm trần: mỗi người xem thăm dò 5 giây/lần
trong 40 phút là ~480 lượt. Worker đặt `Cache-Control` theo trạng thái (3 giây
khi đang về số, 60 giây khi đã xác minh) nên biên Cloudflare đỡ phần lớn.

## 8. Gỡ bỏ

```bash
cd worker && npx wrangler delete
```

Rồi xoá nội dung `window.LIVE_WORKER_URL` trong `docs/live.html`. Hệ thống trở
lại đúng trạng thái trước khi có Worker.
