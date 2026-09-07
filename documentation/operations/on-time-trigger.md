# Chạy đúng giờ 18:15–18:30: chẩn đoán và cách sửa

## 1. Kết luận ngắn

Độ trễ **không** đến từ nghẽn hàng đợi runner, và **không** sửa được bằng cách
đổi phút cron. Nó đến từ khâu GitHub *tạo* lần chạy theo lịch. Kho này đã rải
phút lẻ từ trước và vẫn trễ 2–6 giờ.

Cách duy nhất chạy đúng giờ là **không phụ thuộc vào bộ lập lịch của GitHub**:
một dịch vụ hẹn giờ bên ngoài gọi `repository_dispatch` lúc 18:10 giờ Việt Nam.
Đường đó đã có sẵn trong mã từ trước — nhưng **chưa từng được gọi một lần nào**.

## 2. Số liệu

Đo bằng GitHub API, so mốc cron với `created_at` của lần chạy.

### 2.1 `update-data.yml` — mốc đầu tiên là `11:33 UTC` (18:33 giờ VN)

| Ngày | Mốc đầu thực nổ (UTC) | Giờ VN | Trễ | Số mốc nổ / 9 |
|---|---|---|---|---|
| 02-09 | 15:05:14 | 22:05 | **3h32m** | 7 |
| 03-09 | 14:59:05 | 21:59 | **3h26m** | 7 |
| 04-09 | 14:56:32 | 21:56 | **3h23m** | 6 |
| 05-09 | 13:57:34 | 20:57 | **2h24m** | 9 |
| 06-09 | 14:21:21 | 21:21 | **2h48m** | 9 |

### 2.2 `live-results.yml` — đầu chuỗi, mốc đầu `06:37 UTC` (13:37 giờ VN)

9 mốc mỗi ngày, khoảng **63 lần nổ kỳ vọng trong 7 ngày — thực tế 10 lần.**
Ngày 06-09 mốc sớm nhất nổ lúc `12:58 UTC`, tức **trễ 6 giờ 21 phút**.

### 2.3 Vì sao chắc chắn không phải nghẽn runner

Trong **mọi** lần chạy đã kiểm: `run_started_at == created_at`.

Chờ hàng đợi = **0 giây**. Và thời gian chạy job chỉ 30–60 giây. Nghĩa là khi
GitHub đã tạo lần chạy thì nó khởi động tức thì — toàn bộ độ trễ nằm ở trước
đó. Rải phút cron chỉ tác động tới thời điểm *đăng ký* lịch, không tác động
tới việc GitHub có tạo lần chạy đúng lúc hay không.

### 2.4 Vì sao không phải "cron đầu giờ"

Kho này đã dùng phút lẻ từ trước: `33, 41, 53, 7, 19, 27, 39, 51, 9`. Bảng
trên là số đo *sau khi đã* rải phút lẻ. Nó không giúp gì.

### 2.5 Bằng chứng quyết định

```
repository_dispatch runs của update-data.yml:  total_count = 0
```

Van thoát hiểm đã được hàn sẵn vào mã nhưng chưa ai mở. Đó là toàn bộ khoảng
cách giữa hiện trạng và mục tiêu.

## 3. Kiến trúc sau khi sửa

```
cron-job.org  ──POST 18:10 ICT──▶  repository_dispatch: daily-collect
                                            │
                                            ▼
                                   daily_update.yml
                          (chờ tới 18:15, thăm dò 60–90s/vòng,
                           thoát NGAY khi đủ 27 ô)
                                            │
                                   verified == true
                                            ▼
                              workflow_dispatch update-data.yml
                                  (pipeline hoàn tất đã có sẵn)
```

Điểm mấu chốt: kiến trúc cũ cần bộ lập lịch nổ **9–10 lần mỗi ngày**, mỗi lần
chụp một ảnh. Kiến trúc mới cần nó nổ **một lần** — và với đường
`repository_dispatch` thì không cần nó chút nào.

## 4. Dựng bộ hẹn giờ ngoài

### Bước 1 — Tạo token

1. Vào <https://github.com/settings/personal-access-tokens/new> (fine-grained).
2. **Resource owner**: `beuvivu` · **Repository access**: chỉ `beuvivu/VLA`.
3. **Repository permissions** → `Contents: Read and write`.
   Đây là quyền tối thiểu mà `repository_dispatch` chấp nhận; không cần thêm.
4. **Expiration**: 90 ngày. Đặt nhắc gia hạn — token hết hạn thì đường đúng
   giờ chết **im lặng**, và lưới cron sẽ che mất triệu chứng.
5. Sao token (`github_pat_…`), chỉ hiện một lần.

### Bước 2 — Kiểm tra token bằng tay trước

Đừng dựng lịch rồi mới phát hiện token sai. Chạy trước:

```bash
curl -i -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer github_pat_XXXXXXXX" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/beuvivu/VLA/dispatches \
  -d '{"event_type":"daily-collect"}'
```

Đúng: **`HTTP/2 204`**, không có thân phản hồi. Vào tab Actions phải thấy
"Thu thập XSMB đúng giờ" chạy trong vài giây.

| Mã trả về | Nguyên nhân |
|---|---|
| `401` | Token sai hoặc đã hết hạn |
| `403` | Thiếu quyền `Contents: write` |
| `404` | Sai tên kho, hoặc token không được cấp quyền vào kho này |
| `422` | Sai JSON (thiếu `event_type`) |

### Bước 3 — Dựng lịch trên cron-job.org

1. Đăng ký tại <https://cron-job.org> (miễn phí).
2. **Create cronjob**, điền:

   | Trường | Giá trị |
   |---|---|
   | Title | `VLA — thu thập XSMB` |
   | URL | `https://api.github.com/repos/beuvivu/VLA/dispatches` |
   | Schedule | `Every day at 18:10` |
   | **Timezone** | **`Asia/Ho_Chi_Minh`** ← đặt sai là lệch 7 tiếng |

3. Tab **Advanced**:
   * Request method: **`POST`**
   * Request body:
     ```json
     {"event_type":"daily-collect"}
     ```
   * Headers:
     ```
     Accept: application/vnd.github+json
     Authorization: Bearer github_pat_XXXXXXXX
     X-GitHub-Api-Version: 2022-11-28
     Content-Type: application/json
     ```
4. Bật **Notify on failure** → email. Không bật thì token hết hạn cũng không
   ai biết.
5. **Save**, rồi bấm **TEST RUN** và xác nhận nhận `204`.

### Bước 4 — Vì sao 18:10 chứ không phải 18:15

Kỳ quay bắt đầu quanh 18:15. Gọi lúc 18:10 chừa 5 phút cho khâu khởi động
runner và cài `requests`. Lớp thăm dò tự chờ tới 18:15 rồi mới gửi yêu cầu
đầu tiên, nên gọi sớm **không** làm nó nã vào trang chưa có số.

### Bước 5 — Dịch vụ thay thế

| Dịch vụ | POST + header tuỳ ý | Ghi chú |
|---|---|---|
| **cron-job.org** | Có | Khuyến nghị. Miễn phí, có múi giờ, báo lỗi qua email |
| **UptimeRobot** | Chỉ gói trả phí | Gói miễn phí chỉ GET, **không dùng được** |
| **Google Cloud Scheduler** | Có | Miễn phí 3 job/tháng, cần thẻ |
| **Máy tự chạy** | Có | `crontab` với `10 18 * * *` và `TZ=Asia/Ho_Chi_Minh` |

> Lưu ý về UptimeRobot: yêu cầu trong đề bài có nhắc dịch vụ này, nhưng gói
> miễn phí của nó chỉ gửi được `GET` và không đặt được header `Authorization`,
> nên **không** kích hoạt được `repository_dispatch`. Dùng cron-job.org.

## 5. Kiểm chứng sau khi dựng

Sau đêm đầu tiên, chạy:

```bash
gh run list --workflow=daily_update.yml --limit 5 \
  --json event,createdAt,conclusion
```

Cần thấy `"event": "repository_dispatch"` với `createdAt` quanh `11:10 UTC`
(18:10 giờ VN). Nếu chỉ thấy `"schedule"` thì bộ hẹn giờ ngoài chưa gọi được
— quay lại Bước 2.

Mỗi lần chạy còn đính kèm `poll-summary-<run_id>.json` với số ô đã xác minh,
số vòng và độ trễ từng nguồn.

## 6. Điều chưa sửa được

**Lịch cron của GitHub vẫn sẽ trễ và vẫn rơi mốc.** Không có cách nào sửa từ
phía kho — đó là hành vi "cố gắng tốt nhất" của nền tảng, và tài liệu GitHub
nói rõ sự kiện theo lịch có thể bị trì hoãn hoặc bỏ khi hệ thống tải cao. Ba
mốc cron trong `daily_update.yml` chỉ là lưới an toàn cho trường hợp bộ hẹn
giờ ngoài chết; chúng **không** phải đường chạy đúng giờ.

Nói cách khác: nếu không dựng Bước 1–3, phần mã trong PR này **không** làm hệ
thống chạy đúng giờ. Nó chỉ làm cho việc chạy đúng giờ trở nên khả thi và
giảm số lần đánh thức cần thiết từ mười xuống một.

---

## 7. Thử lại có lùi mũ (bổ sung)

Trong khung 18:15–18:40 cả nước cùng vào xem, nên `429 Too Many Requests` và
`5xx` là chuyện thường. Bản đầu bỏ nguồn ngay lần hỏng đầu tiên — mất nguồn đó
cho trọn một vòng thăm dò 60–90 giây.

Nay mỗi yêu cầu được thử tối đa **3 lần**, chờ lùi mũ giữa các lần
(0,5s → 1s → 2s, trần 4s) kèm **nhiễu ngẫu nhiên**.

Nhiễu là phần bắt buộc chứ không phải trang trí: sáu nguồn chạy song song, nếu
cùng thất bại rồi cùng chờ đúng một khoảng thì lần thử sau lại dội vào cùng
một thời điểm — đúng lúc máy chủ đang quá tải.

Chỉ thử lại mã **thoáng qua**: `408, 425, 429, 500, 502, 503, 504`.
`403` và `404` thì không — câu trả lời sẽ y hệt, thử lại chỉ tốn thời gian.

`Retry-After` được tôn trọng nhưng vẫn bị kẹp theo trần: một số nơi trả về
hàng trăm giây, chờ chừng đó thì hết cả kỳ quay.

Ngân sách xấu nhất là `max_attempts × request_timeout` = 3 × 8 = 24 giây, và
`PollConfig` **từ chối khởi tạo** nếu con số đó vượt chu kỳ thăm dò — nếu
không, một nguồn chậm sẽ nuốt trọn vòng và vòng kế tiếp bị trượt.

## 8. Chốt chặn silent fail

`continue-on-error` ở bước thăm dò là cố ý: thiếu số ở mốc sớm là chuyện bình
thường vì mốc sau sẽ thử lại, và để job đỏ mỗi lần như vậy sẽ làm người ta
quen với việc bỏ qua cảnh báo.

Nhưng ở **mốc lưới an toàn cuối cùng trong ngày** thì không còn lần thử nào
nữa. Để job xanh lúc đó chính là silent fail: không ai biết dữ liệu đã hỏng
cho tới khi tự mở trang ra xem. Nay bước kết luận so `github.event.schedule`
với mốc cuối và `exit 1` nếu vẫn thiếu số.

Một phép kiểm đối chiếu hằng số `LAST_CRON` với mốc cuối thật trong khối
`schedule` — đổi lịch mà quên sửa hằng số thì chốt sẽ im lặng ngừng hoạt động,
đúng kiểu hỏng không ai phát hiện.

## 9. Hai điều KHÔNG cần sửa (đã kiểm chứng)

Có hai lo ngại thường gặp không đúng với kho này:

**Không có cào theo DOM/CSS selector.** `sources.py` dùng BeautifulSoup ĐÚNG
MỘT việc: bóc thẻ để lấy văn bản thuần (`get_text`), rồi so khớp bằng biểu
thức chính quy trên văn bản đó. Không có `select_one`, không `find_all` theo
lớp CSS. Đây vốn đã là cách bền nhất: trang đổi khung HTML thì bản này không
gãy.

**Không có cache cứng nào chặn cập nhật.** Toàn bộ mã lấy dữ liệu không dùng
`lru_cache` hay bộ nhớ đệm đĩa. Thứ duy nhất liên quan là đầu mục
`Cache-Control: no-cache` gửi ĐI, tức yêu cầu phía kia đừng trả bản cũ — ngược
lại với việc tự giữ bản cũ.
