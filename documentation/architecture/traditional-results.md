# Sổ kết quả truyền thống — schema và luồng dữ liệu

## Trang tĩnh: toàn bộ lịch sử nhúng sẵn, không gọi mạng

`docs/so-ket-qua-truyen-thong.html` **không** gọi REST endpoint mô tả ở dưới.
Nó mang sẵn toàn bộ lịch sử ở dạng nén và chạy hoàn toàn trong trình duyệt.
Endpoint vẫn còn trên Worker cho các bên gọi khác; phần này nói về TRANG.

### Vì sao đổi: đây là nguyên nhân lỗi "không tra cứu được quá khứ"

Bản trước nhúng `limit=500` kỳ ở dạng JSON đầy đủ. Đo được:

| | Số kỳ | Dung lượng | Dải phủ |
|---|---|---|---|
| Bản cũ, JSON đầy đủ | 500 | 658 KB | 2025-04-29 → 2026-09-14 |
| Bản mới, dạng nén | 2 399 | 281 KB | 2020-01-01 → 2026-09-14 |

Nhỏ hơn **2,3 lần** mà phủ nhiều hơn **4,8 lần**. Logic lọc ngày của bản cũ
vốn đúng — nó lọc đúng, trả về rỗng, rồi hiện "Chưa có kết quả trong khoảng
đã chọn", đọc như thể hôm ấy không quay. Hai ô chọn ngày cũng không có
`min`/`max`, nên trình duyệt cho chọn cả năm 1999.

### Định dạng nén

Mỗi kỳ là **một chuỗi 117 ký tự**: `YYYY-MM-DD` + 107 chữ số giải, ghép theo
đúng thứ tự và độ rộng của `PRIZE_SPEC`.

```
2026-09-14 83772 68785 50518 27452 … 66 21 34 78
└ 10 ký tự ┘└──────────── 107 chữ số ────────────┘
```

Mọi thứ bị bỏ đi đều suy lại được ở trình duyệt:

| Bỏ đi | Suy lại bằng |
|---|---|
| `head_tail` (20 mảng mỗi kỳ) | `headTail()` tính từ chính các giải |
| nhãn và độ rộng giải | `const PRIZES` — hằng số, giống nhau mọi kỳ |
| `region`/`province`/`status`/`source` | giống hệt nhau ở cả 2 399 kỳ |

Bảng `PRIZE_SPEC` bên Python và `const PRIZES` bên JS phải khớp từng mục.
Lệch nhau thì trang vẫn dựng được nhưng **cắt sai chuỗi và hiện số rác** —
`tests/test_traditional_results_page.py` khoá điều đó.

### Tính năng

- 12 mốc khoảng thời gian: 10/30/60/90/100/120/200/300/500/1000 kỳ, toàn bộ
  lịch sử, hoặc chọn khoảng ngày. Mốc đếm theo **số kỳ** chứ không theo ngày
  lịch: XSMB nghỉ quay dịp Tết, nên "lùi 30 ngày lịch" có thể chỉ ra 27 kỳ.
- 4 bố cục cột (1/2/3/4), như bốn nút chọn bố cục của trang tham chiếu.
- 3 công tắc ẩn/hiện: bảng đầu đuôi, dãy lô tô 27 số, tô đậm hai số cuối.
- Xuất CSV (BOM UTF-8) và Excel `.xlsx` thật (gói OOXML dựng tại chỗ, không
  CDN), cộng nút in với `@media print` bỏ hết phần điều khiển.

### Kiểm chứng bằng trình duyệt thật

`scripts/check_traditional_results_page.py` mở trang trong Chromium và đo.
Hai lỗi chỉ lộ ra khi render, không đọc CSS mà thấy được:

1. Chân bảng lấn lề: bản cũ đo được **1 px** giữa hàng giải cuối và cạnh
   dưới khung. Cột phải có 14 px đệm còn cột trái không có gì.
2. Bản sửa đầu tiên vẫn để chân tụt về **2 px**, nhưng chỉ ở tổ hợp
   "màn hình ≤ 900 px + ẩn cả hai bảng phụ" — quy tắc `padding-bottom:0` ở
   media query giả định luôn có cột phụ nằm dưới. Phép quét 96 tổ hợp
   (6 bề rộng × 4 bố cục × 4 trạng thái công tắc) bắt được ngay.

Kịch bản cũng đối chiếu **số giải đặc biệt thật** của từng kỳ với
`data/xsmb.csv`, chứ không chỉ đếm số dòng.


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
