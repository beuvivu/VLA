# Vietlott: giao diện và đối chiếu bộ số

Trang kết quả dùng HTML/CSS/JavaScript native, cùng font và theme của site.
Nguồn dựng là `src/build_vietlott_results.py`; CSS ở
`src/templates/vietlott_main.css`; logic nhập số ở
`src/assets/vietlott-comparison.js`. Tám trang được sinh vào `docs/`.

## Tùy chỉnh màu và chuyển động

Màu bóng số lấy từ token chung ở `src/ui_theme.py`. CSS riêng thêm gradient
và bóng nhẹ, giữ màu chữ tương phản trong cả hai theme.

| Loại bóng | Token | Nền / chữ sáng | Nền / chữ tối |
|---|---|---|---|
| Thường | `--ui-n2-bg`, `--ui-n2-ink` | `#E0F2FE` / `#075985` | `#183647` / `#9DD9F3` |
| Đặc biệt/phụ | `--ui-special-bg`, `--ui-special-ink` | `#FFE4E6` / `#BE123C` | `#4C0519` / `#FDA4AF` |
| Số khớp | `--ui-n3-bg`, `--ui-n3-ink` | `#DCFCE7` / `#166534` | `#173E30` / `#A0E3BC` |

Các lớp `.vl-ball--match` và `.vl-ball--bonus-hit` thể hiện số khớp;
số phụ khớp còn có viền riêng. Nhãn chữ và nhãn truy cập giải thích màu.

Nút dùng `.vl-button`; biến `--vl-button-start`, `--vl-button-end` và
`--vl-button-ink` điều khiển gradient/chữ. Sửa `transition` trong lớp này
để đổi tốc độ hover/active; `vl-button-shimmer` và `vl-button-ripple` là
hai animation. `prefers-reduced-motion: reduce` tắt chuyển động.

Grid dùng `auto-fit` và `minmax`; jackpot dùng `clamp()` theo chiều rộng
thẻ. Dãy số giữ một dòng và cuộn trong khối khi không đủ chỗ, thay vì làm
tràn trang. Bảng đối chiếu cuộn ngang trong vùng riêng.

## Dùng logic JavaScript

Nạp `assets/vietlott-comparison.js` với `defer`, sau đó gọi:

```js
const result = window.vietlottComparison.comparePrediction(
  'mega645',
  [1, 2, 3, 7, 8, 9],
  [1, 2, 3, 4, 5, 6]
);
// hits: 3, total: 6, accuracy: 50, tier: 'third'

const power = window.vietlottComparison.comparePrediction(
  'power655',
  [1, 2, 3, 4, 5, 7],
  [1, 2, 3, 4, 5, 6],
  { actualBonus: 7 }
);
// hits: 5, total: 6, tier: 'jackpot2'

const lotto = window.vietlottComparison.comparePrediction(
  'lotto535',
  [1, 2, 3, 4, 5],
  [6, 7, 8, 9, 10],
  { predictedBonus: 9, actualBonus: 9 }
);
// hits: 0, total: 5, tier: 'consolation', bonusMatched: true
```

API kiểm số lượng, miền giá trị và số trùng; chuỗi như `"01"` được nhận,
giá trị sai ném lỗi. Hai mảng chính đủ để tính `accuracy`. Thiếu số đặc biệt
Power hoặc một trong hai số đặc biệt Lotto thì `tierKnown: false`,
`bonusMatched: null`, `tier: null`; hạng giải còn chưa xác định. Power có
sáu số chọn, không có số thứ bảy do người chơi chọn. Lotto chọn năm số chính
và số đặc biệt từ trống riêng.

Form `[data-vl-comparison-widget]` trên ba trang Mega/Power/Lotto gọi API này,
tô số trùng và thông báo lỗi/chờ kết quả. Đối chiếu thủ công không ghi sổ.

## Cách đọc bảng tự động

Bảng dùng chính bộ số đã đăng ký trước kỳ quay, ghép đúng sản phẩm, mã kỳ
và ngày. Kỳ chờ hoặc lệch ngày vẫn hiện bộ số đã lưu, chưa tính điểm.

- Mega/Power/Lotto/Keno: tỷ lệ số chính khớp trên từng bộ số; số phụ xét riêng.
- Bingo18: tỷ lệ vị trí khớp; số trùng có lặp được ghi riêng.
- Max 3D: khớp nguyên bộ ba, giữ số 0 đầu; hiện số lần xuất hiện và hạng giải.

Tỷ lệ tổng hợp chia tổng số khớp cho tổng số đã chọn của mọi bộ đã chấm trong
các kỳ hiển thị. Đây là mức khớp quan sát, không phải xác suất trúng kỳ tới.
Mức giải đọc từ engine, không suy từ phần trăm.

## Dựng lại

```bash
PYTHONPATH=src python src/build_vietlott_results.py \
  --cache-states vietlott/data/forecast
```

Workflow `vietlott-results.yml` dựng lại khi một trong hai workflow cập nhật
engine hoàn tất trên `main` của chính kho, kể cả lượt cập nhật một phần có
lỗi nguồn. Kết quả hợp lệ đã lưu của sản phẩm khác vẫn được đưa lên trang;
workflow engine giữ trạng thái lỗi để theo dõi các kỳ còn thiếu. Lượt bị hủy,
bỏ qua hoặc đến từ nhánh/kho khác không kích hoạt dựng trang.

Trang khôi phục cache engine, đọc kết quả và sổ dự báo đã commit từ đầu nhánh
hiện tại, bổ sung bảng giải đúng kỳ từ cache, ghi HTML/asset và triển khai
Pages. Các mốc cron vẫn là đường phục hồi khi chưa có sự kiện cập nhật.
