# Vì sao kết quả về muộn, và cách chạy đúng giờ

## Vấn đề đo được

Lịch chạy (`schedule`) của GitHub Actions là **cố gắng tốt nhất**, không phải
cam kết. Trên kho này, độ trễ đo trực tiếp từ lịch sử chạy:

| Ngày | Cron đặt (UTC) | Chạy thật (UTC) | Trễ |
|---|---|---|---|
| 2026-09-01 | 11:00 | 15:26 | 4 giờ 26 |
| 2026-09-02 | 11:00 | 15:02 | 4 giờ 02 |
| 2026-09-03 | 11:00 | 14:57 | 3 giờ 57 |
| 2026-09-04 | 11:00 | 14:53 | 3 giờ 53 |
| 2026-09-05 | 11:00 | 13:39 | 2 giờ 39 |

Hệ quả: workflow `live-results.yml` đặt chạy lúc 18:00 giờ Việt Nam (trước kỳ
quay 18:15) nhưng thực tế khởi động lúc **20:39–22:26 giờ Việt Nam**. Khi đó kỳ
quay đã xong, nên vòng thăm dò lấy được kết quả hoàn tất ngay lần đầu rồi thoát
sau khoảng 20 giây. Dữ liệu vẫn đúng, nhưng về muộn vài tiếng và người xem
không bao giờ thấy các số hiện dần.

## Đã làm được gì trong kho

### Đo lại 05-10-2026 — chờ trong runner thay vì đuổi theo độ trễ

Đo trên 26 ngày (10-09 → 05-10-2026), lấy `created_at` của lần chạy trừ giờ
mốc:

| Mốc (UTC) | Trễ ngắn nhất | Trễ dài nhất |
|---|---|---|
| 00:15 (watchdog) | 4 giờ 16 | 5 giờ 33 |
| 06:37 (live-results) | 4 giờ 34 | 8 giờ 34 |
| 08:51 (daily_update) | 3 giờ 31 | 8 giờ 11 |

Ngày 05-10 không mốc nào của `daily_update.yml` nổ trong 7,7 giờ đầu: GitHub
còn bỏ mốc. Hệ quả của lịch cũ:

- `daily_update.yml` nổ lúc 19:00–23:30 giờ VN, **sau** hạn thăm dò 19:30, nên
  bộ thăm dò thoát mà không gọi nguồn lần nào.
- `live-results.yml` nổ khi kỳ quay đã xong; kỳ về kho lúc 18:58–20:51 giờ VN
  (trung vị ~20:00) chỉ nhờ lượt live ấy kích hoạt hoàn tất.

Ba thay đổi:

1. **Lượt đến sớm CHỜ trong runner.** `daily_update.yml` chờ tối đa 260 phút
   (timeout 350, dưới trần 360 của GitHub), `live-results.yml` chờ tối đa 240
   phút (timeout 315). Lượt nào nổ từ ~14:00 giờ VN đều thăm dò đúng 18:08–18:15.
2. **Mốc dời vào sáng sớm** (08:13–13:17 giờ VN), cách nhau ≤ 45 phút, để độ
   trễ 4–8 giờ đẩy chúng rơi vào buổi chiều. Với mọi độ trễ trong dải đo được,
   ít nhất BA mốc của mỗi workflow rơi vào khung chờ — dự phòng cho mốc bị bỏ.
   Mốc cuối của `daily_update.yml` (15:17 VN) vừa là lưới an toàn vừa lo
   trường hợp GitHub bỗng đúng giờ, và nổ trước nửa đêm VN kể cả ở độ trễ dài
   nhất đo được.
3. **Lượt nổ muộn vẫn thử một vòng.** Trước đây bộ thăm dò khởi động sau hạn
   19:30 thoát ngay; nay nó gọi nguồn một lần, lấy được kỳ đã xong thì kích
   hoạt hoàn tất luôn.

Mô phỏng trên chính 26 ngày đo: **26/26 ngày** thu được kỳ lúc 18:35 giờ VN.
`tests/test_workflows.py` ghim phép tính ấy cùng bảng độ trễ — dải trễ trôi
thì đo lại, cập nhật `MEASURED_DELAYS`, và phép kiểm nói lịch còn đủ hay không.

Phút lẻ vẫn giữ: hàng đợi của GitHub dồn nặng nhất ở phút `:00` và `:30`.

## Cách chạy đúng giờ chắc chắn

Gọi từ một bộ lập lịch bên ngoài. Cả hai workflow nay nhận
`repository_dispatch`:

| Workflow | `event_type` |
|---|---|
| `live-results.yml` | `live-window` |
| `update-data.yml` | `daily-finalize` |

### Bước 1 — tạo token

Tạo một fine-grained personal access token với quyền **Contents: read** và
**Actions: write** trên đúng kho này.

### Bước 2 — gọi API đúng giờ

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/beuvivu/VLA/dispatches \
  -d '{"event_type":"live-window"}'
```

Đặt lệnh trên chạy lúc **18:05 giờ Việt Nam** (11:05 UTC) cho `live-window`, và
**18:35 giờ Việt Nam** (11:35 UTC) cho `daily-finalize`.

### Bước 3 — chọn nơi chạy lệnh

Bất kỳ dịch vụ nào chạy đúng giờ đều được. Vài lựa chọn miễn phí:

* **cron-job.org** — nhập URL, phương thức POST, header và body ở trên.
* **Cloudflare Workers Cron Triggers** — viết một worker gọi `fetch` như trên.
* **Một máy chủ/VPS sẵn có** — thêm một dòng vào `crontab`.

Điểm chung: chúng chạy đúng phút đã đặt, không qua hàng đợi chia sẻ của GitHub.

## Cách kiểm chứng đã hết trễ

Sau khi nối bộ lập lịch ngoài, so giờ khởi động của workflow với giờ đã đặt.
Độ trễ của các lượt `repository_dispatch` nên xuống dưới một phút.
