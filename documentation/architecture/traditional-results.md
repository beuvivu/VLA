# Sổ kết quả truyền thống — schema và luồng dữ liệu

## Phạm vi Miền Bắc

Chỉ phục vụ Miền Bắc (`north/hanoi`), theo schema XSMB 27 số và 8 hạng giải
từ Đặc Biệt đến Giải Bảy. API từ chối khu vực ngoài Miền Bắc.

## REST endpoint

```http
GET /api/v1/traditional-results?region=north&province=hanoi&days=30
GET /api/v1/traditional-results?region=north&province=hanoi&from=2026-08-01&to=2026-09-13
```

- Preset hợp lệ: `30`, `60`, `90`, `100` ngày.
- Khoảng tùy chọn phải có đủ `from` và `to`, theo `YYYY-MM-DD`, tối đa 500 ngày.
- Mốc xác định kỳ mới nhất: `18:35`, múi giờ `Asia/Ho_Chi_Minh`.
- Query sai trả `400`; không đọc được cả dữ liệu chuẩn lẫn bản last-good trả `502`.

## API response v1

```json
{
  "schema_version": 1,
  "query": {
    "region": "north",
    "province": "hanoi",
    "from": "2026-08-15",
    "to": "2026-09-13",
    "preset_days": 30,
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "meta": {
    "generated_at_utc": "2026-09-13T12:00:00.000Z",
    "total_results": 30,
    "requested_calendar_days": 30,
    "latest_draw_date": "2026-09-13",
    "source_counts": {"vla_db": 29, "xskt_fallback": 1},
    "sources_used": ["vla_db", "xskt_fallback"],
    "fallback_requested": true,
    "fallback_network_fetch": true,
    "unresolved_dates": [],
    "primary_cache": "hit",
    "response_cache": "miss",
    "warning": null
  },
  "data": [
    {
      "id": "north:hanoi:2026-09-13",
      "region": {"code": "north", "name": "Miền Bắc"},
      "province": {"code": "hanoi", "name": "Hà Nội"},
      "draw_date": "2026-09-13",
      "status": "official",
      "source": {
        "kind": "vla_db",
        "provider": "VLA canonical database",
        "canonical": true
      },
      "prizes": [
        {"code": "special", "name": "Đặc Biệt", "width": 5, "values": ["83799"]},
        {"code": "prize1", "name": "Giải Nhất", "width": 5, "values": ["63029"]}
      ],
      "head_tail": {
        "heads": {"0": ["5", "9", "9"]},
        "tails": {"0": ["3", "3", "4"]}
      }
    }
  ]
}
```

Mọi kết quả giải là **chuỗi**, không phải số, để giữ `01`, `083`, `0008`.
`prizes` là mảng có thứ tự; mỗi phần tử tự khai báo `width`, nên frontend
không phải suy đoán cách đệm số. `source.canonical=false` chỉ có nghĩa là kỳ
đang nằm ở lớp bù, chưa được pipeline hằng ngày đưa vào kho chuẩn.

## Thứ tự dữ liệu và cache

1. Worker đọc `data/xsmb.json` từ nhánh `main` và chuẩn hóa vào cache 5 phút.
2. Nếu nguồn GitHub tạm lỗi, Worker dùng bản `last-good` tối đa 36 giờ.
3. Với từng ngày trong query, bản ghi VLA luôn thắng.
4. Chỉ khi còn ngày thiếu, Worker gọi **một lần** sổ cuộn
   `xskt.vn/xsmb-500-ngay/`, cắt từng bảng `kqmb`, kiểm đủ 27 số và đúng độ
   rộng. Tên URL không được coi là cam kết số kỳ; ngày nguồn không trả về nằm
   trong `unresolved_dates`.
5. Bản bù được lưu KV 30 ngày. Response đã gộp được cache 5 phút.
6. `XsktVnSource` của Python nằm cuối danh mục nguồn. Quy trình canonical hằng
   ngày có thể dùng nó để bù dữ liệu rồi vẫn đi qua validation/consensus trước
   khi ghi `data/xsmb.json` và `data/xsmb.csv`.

Không có token GitHub trong trình duyệt hoặc source code. Worker chỉ đọc file
public; phần ghi kho chuẩn tiếp tục do GitHub Actions hiện hữu đảm nhiệm.

## Frontend

`docs/so-ket-qua-truyen-thong.html` là trang tĩnh, dựng bởi:

```bash
python src/build_traditional_results.py
```

Trang nhúng 500 kỳ VLA mới nhất để vẫn hoạt động khi Worker chưa cấu hình.
`npm run setup` trong thư mục `worker/` tự điền endpoint Worker vào cả trang
trực tiếp và Sổ kết quả. Tải xuống gồm CSV UTF-8 và XLSX OOXML thật, không cần
thư viện/CDN bên ngoài.
