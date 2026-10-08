# Rà soát chuyên sâu mã nguồn — 08-10-2026

Phạm vi: toàn kho VLA (`src/` ~57 600 dòng Python, ~6 500 dòng JS; `scripts/`; `worker/`
Cloudflare Worker; engine `vietlott/`; 26 workflow GitHub Actions; 49 trang `docs/`).
Mỗi lỗi dưới đây đều được **tái hiện trước khi sửa**. Mỗi bản vá đi kèm phép kiểm, và phép
kiểm ấy đã được thử đột biến: trả mã về bản cũ thì phép kiểm phải đỏ.

## 1. Bảng tổng hợp

| Mã | Mức | Vị trí | Lỗi | Ảnh hưởng | Trạng thái |
|---|---|---|---|---|---|
| A1 | **HIGH** | `worker/src/traditional_results.js` | Khách đổi `from`/`to` tuỳ ý, kể cả ngày tương lai. Mỗi khoảng là một khoá đệm mới, và mỗi lần trượt đệm kéo một lượt tải trọn trang 500 ngày của nguồn dự phòng. | Ai cũng biến Worker thành công cụ dội vào nguồn ngoài (đo: 20 yêu cầu → 20 lượt tải). Hết hạn mức subrequest; nguồn có thể chặn IP của Worker, và dự án mất nguồn dự phòng. | Đã sửa |
| A2 | **HIGH** | `vietlott/…/api/main.py`, `core/config.py`, `docker-compose.yml` | API engine không có xác thực. CORS là `*`, và Docker publish `8000` trên mọi giao diện. Lệnh ghi (`/sync`, `/fit`, `?record=true`) và lệnh tính nặng (`/backtest`) mở cho mọi người. | Ai vào được mạng là gọi được. Bất kỳ trang web nào người dùng đang mở cũng kích hoạt được lệnh ghi vào API chạy trên máy họ (CSRF qua `<form>`/`<img>`). | Đã sửa |
| A3 | MEDIUM | `worker/src/traditional_results.js` | API trả tên nguồn trong `source.provider`, `source.kind` và `meta.warning`. | Trái luật "không đưa danh tính nguồn ra trình duyệt"; `live.json` đã ẩn danh, API này thì chưa. | Đã sửa |
| A4 | MEDIUM | `worker/src/index.js` | KV ghi hỏng (hết hạn mức) thì `fetch()` ném lỗi ra ngoài. Nền tảng trả 500 không có CORS, và ảnh chụp vừa thu bị vứt. `/health` sập khi KV chứa JSON hỏng. | Đúng kịch bản mà chú thích của tệp đã tính tới lại làm trang live báo "lỗi mạng". | Đã sửa; bản cuối: lượt yêu cầu không thu thập nữa |
| A5 | MEDIUM | `docs/live.html` | (a) Đổi tab gọi `load()` trong khi lượt trước còn chờ, hai phản hồi về lệch thứ tự. (b) `fetch` không có hạn. | (a) Bản cũ ("đang cập nhật") có thể đè bản mới ("đã xác minh"). (b) Một kết nối treo làm đứng vòng thăm dò vài phút, đúng lúc quay số. | Đã sửa |
| A6 | MEDIUM | `fun_draw_ledger`, `hot_tail_test`, `digit_sum_hypothesis`, `skill_monitor` | Sổ cái "đọc lại rồi ghi lại toàn bộ" bằng `open("w")`/`to_csv(path)`: tệp bị cắt về rỗng trước khi ghi. | Chết giữa chừng để lại sổ cụt; lần sau gộp sổ cụt và mất dòng cũ. Đây là các sổ CLAUDE.md dặn không được mất, như chuỗi kỹ năng dài hơn hạn giữ artifact và tiền tố ngẫu nhiên đã đóng băng. | Đã sửa |
| A7 | MEDIUM | `.github/workflows/vlm-results.yml`, `vietlott/docker-compose.yml` | `VQE_HTTP_BACKEND: curl_cffi` (thư viện giả vân tay trình duyệt). | Trái `SECURITY.md` ("không dùng thư viện né anti-bot"). | **Chờ chủ dự án quyết** |
| A8 | LOW | `tests/frontend/package-lock.json` | `source-map-js` 1.2.1 (GHSA-68fv-2mgg-jv7q, DoS vòng lặp sự kiện), gói phụ thuộc gián tiếp của jsdom. | Chỉ bộ kiểm dùng; không vào trang. | Đã sửa (1.2.2) |
| A9 | LOW | `.github/workflows/daily_prediction.yml` | Còn `checkout@v4`, `setup-python@v5`; mọi workflow khác dùng v7. | Lệch phiên bản; runtime cũ hết hỗ trợ trước. | Đã sửa |
| A10 | LOW | 6 bản Wilson, 2 bản BH-FDR | Chép lặp. Cùng kết quả khi n > 0, nhưng khác nhau ở biên: Wilson n = 0 ra `(0,1)`, `(0,0)` hoặc `NaN`; một bản BH biến MỌI q-value thành NaN khi có một p-value NaN. | Chưa chạm đường chạy thật (bên gọi đã chặn), nhưng là bẫy cho lần dùng sau. | Đề xuất |
| A11 | LOW | CSP của 49 trang | `script-src 'unsafe-inline'`; `connect-src` mở `*.workers.dev`, `*.deno.dev`. | Một lỗ chèn HTML sẽ thành chạy script; kênh gửi dữ liệu đi rộng. Hiện giảm thiểu nhờ luật cấm DOM sink. | Đề xuất |
| A12 | LOW | `worker` route `/api/v1/traditional-results` | Không trang nào của site gọi endpoint này (tài liệu kiến trúc giữ nó cho bên gọi khác). | Bề mặt tấn công. | Giữ route; rủi ro khuếch đại của nó đã khép ở A1 |
| A13 | LOW | `.github/workflows/dashboard-refresh.yml` | Một lần `git push`, không thử lại. | Đụng push của workflow khác thì lượt chạy đỏ (không mất dữ liệu). | Đề xuất |
| A14 | LOW | `src/lottery_codes.py:76` | ruff B023 (closure bắt biến vòng lặp). Báo nhầm, vì `map` chạy ngay trong vòng lặp, nhưng làm bẩn lint. | — | Đã sửa (ràng tham số mặc định) |

Không có lỗi mức CRITICAL.

## 2. Đã kiểm và KHÔNG thấy lỗi

- **Secrets:** quét 2 138 tệp đang theo dõi và 234 commit lịch sử (bản clone là shallow,
  nên lịch sử cũ hơn chưa được quét) với mẫu token GitHub/AWS/Slack/Google/khoá riêng/JWT:
  không có gì. `wrangler.toml` chỉ có id KV giữ chỗ.
- **Phụ thuộc Python:** `pip-audit` trên bốn tệp `requirements*.txt` và trên engine
  `vietlott/`: không có lỗ hổng đã biết.
- **Tiêm lệnh trong workflow:** không khối `run:` nào nội suy `github.event.*`, `inputs.*`
  hay `head_ref`. `workflow_run` của `daily_prediction` chỉ nhận lượt chạy từ một workflow
  chạy trên `main`. Mọi workflow triển khai Pages chỉ chạy khi push lên `main`. Quyền token
  đặt tối thiểu theo từng job. Mọi action đều là chính chủ.
- **SQL injection:** mọi `execute(f"…")` trong engine lấy tên bảng từ ánh xạ cố định đã
  kiểm, đường dẫn `COPY` đã thoát dấu nháy. Không có SQL ghép từ đầu vào người dùng.
- **XSS/DOM:** luật cấm DOM sink được thi hành trên toàn kho. Cả 49 trang đều có CSP.
- **Thời gian:** ruff `DTZ` bật trong CI. Kiểm tay `latest_complete_draw_date` quanh 18:35,
  nửa đêm, và cùng một thời điểm truyền theo UTC hay giờ Việt Nam: đều đúng. Khoá 18:10 của
  sổ mô phỏng dựng giờ khoá theo giờ Việt Nam rồi đổi ra UTC.
- **Mạng:** không request nào thiếu timeout. Worker gọi nguồn có timeout 8 giây, lùi mũ kèm
  nhiễu, và khoá hai lớp chống khuếch đại cho `live.json`.
- **Thống kê:** đối chiếu với thư viện chuẩn trên lưới đầu vào. Sáu bản Wilson khớp công
  thức; hai bản BH khớp `scipy.stats.false_discovery_control` (sai lệch ≤ 1,1·10⁻¹⁶); Holm
  khớp chính xác; `poisson_binomial_sf` khớp quy hoạch động chính xác (≤ 2,2·10⁻¹⁶).
- **Nuốt lỗi im lặng:** quét AST mọi `except Exception/BaseException` mà thân chỉ có
  `pass`/`continue`: chỉ một chỗ, nằm trong script khảo sát, không ở đường chạy thật.
- **Validate đầu vào:** `lottery_code` từ chối cả chữ số Unicode, số âm, `bool`, số thực
  không nguyên.

## 3. Phân tích chi tiết và bản vá

### A1 — Khuếch đại yêu cầu ra nguồn ngoài (HIGH)

**Nguyên nhân gốc.** Khoá đệm phản hồi là `region:province:from:to`. Khoảng tuỳ chọn chỉ
bị chặn độ dài (500 ngày), không chặn mốc cuối. Mọi ngày còn thiếu trong lịch sử chuẩn đều
kéo `loadXsktOverlay`, và hàm này gọi nguồn mà không có khoá nào.

**Tái hiện.** 20 yêu cầu với 20 khoảng ngày năm 2030 → `{ history: 1, fallback: 20 }`.

Trước:

```js
if (!from || !to) throw new Error("Ngày phải đúng định dạng YYYY-MM-DD.");
// … không kiểm mốc cuối …
if (unresolved.length > 0) {
  const xsktUrl = env?.XSKT_HISTORY_URL || DEFAULT_XSKT_URL;
  const responseFromSource = await fetchImpl(xsktUrl, { … });
```

Bản vá đầu, ba lớp (lớp 3 sau đó được thay bằng bản cuối bên dưới):

```js
if (to > latestEligibleDate(nowUtcMs)) {                 // 1. ngày chưa quay → 400
  throw new Error("Đến ngày không được sau kỳ gần nhất đã quay.");
}
const fetchable = unresolved.filter((day) => day >= windowStart);   // 2. chỉ trong cửa sổ 500 ngày của nguồn
if (fetchable.length > 0 && !(await acquireFallbackLock(kv, nowUtcMs))) {   // 3. ≤ 1 lượt / 10 phút / isolate
  warning = "Nguồn dự phòng vừa được gọi; ngày còn thiếu sẽ được bù ở lượt sau.";
}
```

`acquireFallbackLock` dùng hai lớp như đường `live.json`. Mốc trong bộ nhớ giữ chặt "một lượt
mỗi 10 phút" trong MỘT isolate. Khoá KV chặn thêm giữa các isolate khi nó đã lan tới. KV nhất
quán sau và không có đọc-ghi nguyên tử, nên trên toàn mạng giới hạn là một lượt mỗi 10 phút cho
MỖI isolate đang chạy, không phải một lượt duy nhất (xem đề xuất "Khoá thật" ở mục 4). KV lỗi
hay từ chối ghi khoá (giới hạn một lần ghi mỗi giây trên một khoá, khi nhiều isolate cùng
giành) thì coi như đang khoá: không gọi nguồn, nhưng yêu cầu vẫn trả lịch sử chuẩn thay vì 502.

**Bản cuối: chỉ cron gọi nguồn.** Khoá trên vẫn để lại khuếch đại theo số isolate. Bản cuối
dời việc gọi nguồn khỏi lượt yêu cầu: yêu cầu chỉ đọc lớp bù trong KV, còn
`refreshFallbackOverlay` chạy trong `scheduled()`. Hàm này:
- chỉ chạy khi `TRADITIONAL_FALLBACK_REFRESH = "on"`;
- chỉ tải khi trong cửa sổ 500 ngày còn ngày thiếu;
- giãn cách các lần tải tối thiểu 10 phút;
- ghi `absent` cho ngày trang nguồn xác nhận không có (nghỉ Tết).

Cron chạy tuần tự theo lịch, nên giới hạn lượt tải không còn phụ thuộc lưu lượng khách. Khoá
KV và mốc trong bộ nhớ không còn cần thiết, nên đã được gỡ.

**Kiểm chứng.** `tests/test_traditional_results_api.py`:
- 20 khoảng ngày → 0 lượt tải từ yêu cầu;
- cron bù ngày thiếu, hai yêu cầu sau đó không gọi thêm nguồn;
- cron ở phút 0/5/9/11/15/22 chỉ tải ở phút 0, 11 và 22;
- ngày nghỉ được nhớ: lượt cron sau không tải lại;
- công tắc tắt thì cron không nạp;
- khoảng tương lai → 400;
- ngày ngoài cửa sổ → 0 lượt tải;
- không lộ tên nguồn.

Sáu đột biến đều đỏ:
- yêu cầu lại gọi nguồn;
- bỏ giãn cách;
- không nhớ ngày nghỉ;
- ghi `absent` ngoài phạm vi trang;
- bỏ qua công tắc;
- cron không nạp.

### A2 — Mặc định không an toàn của API engine (HIGH)

**Nguyên nhân gốc.** `cors_origins = ["*"]` cùng `allow_methods=["*"]`, không có lớp xác
thực, và compose publish `"8000:8000"`. Chỉ siết CORS thì chưa đủ: `GET …?record=true` và
`POST /prizes/sync` thân rỗng là "simple request", nên trình duyệt vẫn GỬI chúng từ một
trang lạ, dù trang ấy không đọc được phản hồi.

Trước:

```python
cors_origins: list[str] = ["*"]
```

```yaml
ports:
  - "8000:8000"
```

Sau:

```python
cors_origins: list[str] = []
api_token: str | None = None        # VQE_API_TOKEN

@app.middleware("http")
async def _require_token_for_writes(request, call_next):
    token = settings.api_token
    writes = request.method in _MUTATING or _asks_to_record(request)
    if token and writes:
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            return JSONResponse(status_code=401, content={"error": "Unauthorized", …})
    return await call_next(request)
```

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

`_asks_to_record` đọc MỌI lần lặp của `record` bằng đúng bộ đọc bool của FastAPI (pydantic
`TypeAdapter(bool)`): `on`, `y`, `t`… cũng là True, không chỉ `1`/`true`/`yes`. Giá trị không
đọc được (FastAPI sẽ trả 422) vẫn tính là lệnh ghi. Bản đầu chỉ so với `{"1", "true", "yes"}`,
nên `?record=on` ghi được vào sổ mà không cần token.

Dịch vụ `scheduler` trong compose gửi `Authorization: Bearer $VQE_API_TOKEN`. Header tuỳ
biến buộc trình duyệt gửi preflight, nên `<form>`/`<img>` ở trang lạ không còn kích hoạt được
lệnh ghi. So khớp token bằng `hmac.compare_digest` (thời gian hằng).

Không đặt token thì client không phải trình duyệt (scheduler, curl) vẫn ghi được như cũ,
nhưng lệnh ghi mà trình duyệt đánh dấu là đến từ trang khác bị trả 403: `Sec-Fetch-Site`
khác `same-origin`/`none`, hoặc `Origin` không phải chính API và không có trong
`VQE_CORS_ORIGINS`. Swagger UI ở `/docs` (cùng trang) vẫn dùng được. Ba route GET làm mới dự
báo (`/forecast/{p}`, `/forecast/{p}/evidence`, `/ml/forecast/{p}`) cũng là lệnh ghi: chúng học
thêm từ kỳ mới, ghi sự kiện vào sổ và lưu checkpoint dù không có `record`. `/scoreboard` chỉ
đọc. `vietlott serve` mặc
định nghe `127.0.0.1` (trước: `0.0.0.0`), và cảnh báo khi được mở ra mạng mà không có token.
CORS được thêm SAU middleware xác thực nên nằm ngoài cùng: phản hồi 401/403 vẫn mang
`Access-Control-Allow-Origin` cho trang được phép, thay vì thành lỗi mạng mờ.

**Kiểm chứng.** `vietlott/tests/test_api_security.py` có 24 phép kiểm. Đột biến cả 12 luật
đều đỏ: CORS `*`, bỏ kiểm token, `record=true` không tính là ghi, so `record` phân biệt hoa
thường, chỉ đọc một lần lặp của `record`, cho giá trị không đọc được đi qua, compose mở mọi
giao diện, CORS nằm trong xác thực, bỏ chặn trang khác khi không có token, không tin origin
của chính API, cho qua `Sec-Fetch-Site` lạ khi không có `Origin`, `serve` mặc định `0.0.0.0`. Toàn bộ bộ kiểm engine vẫn xanh. Engine là mã chép từ
VLM, nên bản vá này nên được đưa ngược về kho VLM.

### A3 — API lộ danh tính nguồn (MEDIUM)

`source.provider: "<tên miền nguồn>"`, `kind: "<tên>_fallback"`, `meta.warning: "Không đọc được
<tên miền>: …"` → `kind: "fallback" | "canonical"`, bỏ `provider`, cảnh báo ghi "nguồn dự
phòng". Phép kiểm `test_the_api_never_names_its_sources` tìm tên nguồn trong toàn bộ phản
hồi, kể cả khi nguồn trả lỗi.

### A4 — Worker sập khi KV ghi hỏng (MEDIUM)

**Tái hiện.** KV đọc được nhưng `put` ném "quota exceeded": `fetch()` ném lỗi ra ngoài. JSON
hỏng trong KV làm `/health` ném lỗi.

Trước:

```js
await kv.put(KV_KEY, JSON.stringify(snapshot), { expirationTtl: 60 * 60 * 36 });
return snapshot;
```

Bản sửa đầu bọc `kv.put` trong `try/catch` để `fetch()` vẫn trả ảnh chụp vừa thu. Bản cuối
(xem dưới) bỏ hẳn việc thu thập khỏi `fetch()`:

```js
// fetch(): KV chưa có ảnh chụp thì không gọi nguồn
return jsonResponse({ schema_version: 2, status: "waiting" }, { status: 503 });
```

`/health` bắt lỗi `JSON.parse`.

**Khoá thu thập chưa từng ghi được.** KV của Cloudflare từ chối `expirationTtl` dưới 60 giây,
nên khoá 10 giây (`expirationTtl: 10`) bị từ chối ở mọi lần ghi: lớp khoá giữa các isolate chưa
từng có hiệu lực. Bộ thử không thấy vì `FakeKV` không áp giới hạn ấy; nay `FakeKV` của cả hai bộ
thử Worker từ chối TTL dưới 60 như Cloudflare.

**Bản cuối: lượt yêu cầu không thu thập nữa.** Kể cả khi ghi được, khoá KV không chặn được lúc
khởi động lạnh: KV nhất quán sau, không đọc-ghi nguyên tử, kết quả "không có" còn được đệm tới
60 giây, nên mỗi isolate ở mỗi nơi tự chạy một vòng sáu nguồn (đo: 12 yêu cầu luân phiên hai
isolate trên KV rỗng → 12 lượt gọi nguồn). Cùng cách đã chữa A1, chỉ cron gọi nguồn: KV rỗng thì
Worker trả 503 có CORS, và trang live đọc `live.json` dự phòng. Không còn khoá nào cần giữ, và
`refresh()` để lỗi ghi KV lên tới `scheduled()`, nơi nó được ghi log. Phép kiểm: 12 yêu cầu
luân phiên hai isolate, KV rỗng lẫn KV ghi mất → 0 lượt gọi nguồn, 503 kèm CORS; cron với KV
ghi hỏng không đổ. Bộ cài đặt (`worker/setup.mjs`) đọc 503 là "chờ lượt cron đầu", không in
"0/0 nguồn trả lời được".

### A5 — Vòng thăm dò trang live (MEDIUM)

Trước:

```js
var response = await fetch(urls[i] + '?t=' + Date.now(), {cache: 'no-store'});
…
async function load() {
  var status = 'waiting';
```

Sau:

```js
var response = await fetch(urls[i] + '?t=' + Date.now(),
  {cache: 'no-store', signal: timeoutSignal(FETCH_TIMEOUT_MS)});   // 10 giây
…
var loading = false;
async function load() {
  if (loading) return;            // lượt đang chạy tự hẹn lượt kế khi xong
  loading = true;
```

Phép kiểm mới `tests/frontend/live-polling.test.mjs` chạy chính `docs/live.html` trong
jsdom. Nó đỏ trên mã cũ ở cả hai ca: hai lượt tải song song khi đổi tab, và `fetch` không
nhận `signal`.

### A6 — Ghi sổ cái không nguyên tử (MEDIUM)

Mô-đun mới `src/atomic_io.py` (`atomic_write_bytes`, `atomic_write_text`, `atomic_to_csv`)
ghi ra tệp tạm cạnh đích, `fsync`, rồi `os.replace`. Bốn sổ chuyển sang dùng nó;
`online_learning.py` bỏ bản chép riêng để dùng chung (DRY).

Trước:

```python
with path.open("w", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
    …
```

Sau:

```python
buffer = io.StringIO()
writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
…
atomic_write_text(path, buffer.getvalue())
```

`tests/test_atomic_ledgers.py` làm hỏng đúng lần ghi (ghi được một nửa rồi ném `OSError`)
và đòi sổ cũ còn nguyên từng byte. Trả từng hàm ghi về bản trên `main` thì phép kiểm của
hàm ấy đỏ.

### A7 — `curl_cffi` (MEDIUM, chưa sửa)

Cấu hình chép nguyên từ VLM. Bỏ nó là đúng `SECURITY.md`, nhưng có thể làm một số nguồn trả
"không khả dụng" thường hơn. Đây là quyết định của chủ dự án; tài liệu kiến trúc Vietlott
đã ghi nó vào lộ trình giai đoạn 1, mục 7.

## 4. Đề xuất nâng cao

**Kiến trúc và cache.** Site là trang tĩnh trên GitHub Pages, cộng một Worker. Thêm Redis
không giải quyết vấn đề nào đang có: Worker đã có KV và Cache API ở biên. Hai chỗ đáng làm:

- **Không cần khoá thật nữa.** KV là nhất quán cuối cùng (ghi có thể mất tới ~60 giây để
  lan khắp nơi), nên mọi khoá dựng trên KV chỉ là nỗ lực tốt nhất. A1 và A4 tránh nhu cầu này
  bằng cách chỉ cho cron gọi nguồn. Nếu sau này lại có đường yêu cầu nào cần gọi ra ngoài: một
  Durable Object làm khoá, hoặc Rate Limiting binding theo IP cho `/api/*`.
- **Chế độ B (API engine thường trực).** Chuyển `/sync`, `/fit`, `/backtest` sang hàng đợi
  nền (arq/RQ, hoặc một worker DuckDB duy nhất đọc lệnh từ bảng). DuckDB chỉ có một tiến
  trình ghi, nên xếp hàng đúng với ràng buộc ấy hơn là chạy trong luồng xử lý yêu cầu. Thêm
  giới hạn tần suất theo IP cho các lệnh tính nặng. Nếu mở ra mạng: reverse proxy có xác
  thực, TLS, và `VQE_API_TOKEN` bắt buộc.

**CI/CD.**

1. Thêm job bảo mật chạy mỗi PR: `pip-audit -r requirements*.txt`, `pip-audit vietlott`,
   `npm audit --package-lock-only` cho `tests/frontend`, và
   `ruff check --select S,B --extend-ignore S101,S311`.
2. Dependabot cho `github-actions`, `pip`, `npm`; ghim action theo SHA.
3. Quét secrets trên TOÀN lịch sử (gitleaks/trufflehog trên bản clone đầy đủ; phiên rà soát
   này chỉ có 234 commit). Bật push protection của GitHub secret scanning.
4. Thêm vòng thử lại cho `dashboard-refresh.yml` như các workflow ghi dữ liệu khác (A13).

**Frontend.** CSP dùng hash (`'sha256-…'`) cho từng inline script, tính lúc dựng trang, và
bỏ `'unsafe-inline'`. Thu `connect-src` về đúng tên Worker đã triển khai thay vì wildcard
(A11).

**Chất lượng mã.** Gom Wilson/BH về một mô-đun thống kê dùng chung, với hợp đồng biên ghi
rõ (n = 0 → `(0, 1)`; NaN bị loại khỏi BH chứ không lan) (A10). Route
`/api/v1/traditional-results` được giữ cho bên gọi ngoài kho; nếu chắc không còn ai dùng thì
gỡ nó (A12).

## 5. Giới hạn của lượt rà soát

57 600 dòng Python không được đọc từng dòng. Lượt này kết hợp ba cách: quét tự động toàn kho
(ruff các nhóm S/B/PLW/PERF/DTZ, pip-audit, npm audit, quét secrets, quét AST tìm nuốt lỗi);
đọc tay các bề mặt rủi ro cao (Worker, API engine, workflow, trang live, sổ cái, chính sách
thời gian); và đối chiếu số học cho các thủ tục thống kê dùng chung. Phần logic nghiệp vụ còn
lại dựa vào bộ kiểm hiện có (3 232 phép kiểm VLA, toàn bộ bộ kiểm engine) và các bản kiểm
toán số liệu trước trong `documentation/research/`.

## 6. Kiểm bổ sung trước khi hợp nhất PR #149

Rà soát độc lập phát hiện thêm ba đường biên còn bỏ sót trong bản vá ban đầu.
Các ca kiểm dưới đây đã được chạy đỏ trên bản chưa sửa rồi chạy xanh sau bản sửa:

- Cache phản hồi còn dùng namespace v1, nên bản lưu cũ vẫn có thể trả
  `source.provider`. Đổi sang v2 để không đọc lại payload cũ. Lỗi JSON lịch sử
  và cảnh báo dùng bản lưu cũng chỉ trả thông báo chung, không đưa tên nguồn
  hoặc URL từ lỗi upstream ra API. Kiểm `legacy_response_cache` và
  `invalid_primary_is_anonymous` chạy qua handler Worker thực tế.
- Bảng đã có ngày nhưng thiếu một giải bị nhầm với ngày không có bảng, rồi
  bị đệm là ngày nghỉ trong bảy ngày. Parser nay giữ riêng tập ngày có bảng;
  cron chỉ đánh dấu vắng khi không có bảng. Kiểm
  `incomplete_table_is_retried` đòi ngày còn unresolved khi thiếu G7, rồi
  nhận đủ kết quả ngay ở lần cron tiếp theo sau khi nguồn sửa.
- Middleware xác thực dùng đường dẫn có tiền tố mount/reverse proxy, trong
  khi router dùng đường dẫn tương đối. Chuẩn hóa theo `scope.root_path` trước
  khi xét GET ghi trạng thái. Sáu ca của
  `test_a_prefixed_forecast_get_cannot_write_without_the_token` chạy cả
  mount và root_path cho forecast/evidence/ML; không token phải 401 và không
  có checkpoint, token hợp lệ phải 200.

Phạm vi này giữ nguyên payload kết quả quay, sổ dự báo và chính sách mô hình.
Các nâng cấp dependency và thay đổi CI/vận hành được ghi riêng trong
`2026-10-08-pending-work.md` khi chốt main.

Review tổng thể còn phát hiện Swagger `/docs` thiếu khai báo HTTP Bearer:
khi bật token, người dùng không có nút Authorize để gửi nó. OpenAPI nay khai
báo scheme và gắn đúng các POST/PUT/PATCH/DELETE cùng GET làm mới dự báo;
không gắn xác thực cho lệnh đọc công khai hoặc khi chưa cấu hình token.
Kiểm `test_openapi_exposes_bearer_for_guarded_try_it_out` đã chạy đỏ rồi xanh,
kèm kiểm không đưa giá trị token vào schema. Hướng dẫn API ghi cách dùng
Authorize. Middleware tiếp tục là nơi thực thi xác thực.
