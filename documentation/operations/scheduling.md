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

Hai biện pháp giảm xác suất trượt, **không** loại bỏ độ trễ:

1. **Rải nhiều mốc ở phút lẻ.** Hàng đợi của GitHub dồn nặng nhất ở phút `:00`
   và `:30`. Mọi mốc trong `live-results.yml` và `update-data.yml` nay nằm ở
   phút lẻ, trải từ 13:37 tới 18:07 giờ Việt Nam cho workflow live.
2. **Chờ tới khung quay khi khởi động sớm.** Mốc nào rơi trước 18:08 giờ Việt
   Nam sẽ chờ tối đa 90 phút rồi mới thăm dò; rơi sớm hơn nữa thì thoát ngay để
   mốc sau xử lý, thay vì giữ runner hàng giờ.

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
