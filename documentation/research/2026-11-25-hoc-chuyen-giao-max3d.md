# Học chuyển giao giữa Max 3D và Max 3D Pro

Ngày 25-11-2026. Mã: `vietlott/src/vlm/forecast/transfer.py`. Số đo: `vietlott/data/forecast/transfer.json`.
Sổ tiến cứu: `vietlott/data/forecast/transfer-ledger.jsonl` (chỉ nối thêm). Chạy mỗi lượt của
`vlm-results.yml`, sau dự báo ML; bước lưu dữ liệu (`vietlott/scripts/persist_site.py`) commit hai tệp ấy.

## Câu hỏi

Chủ dự án yêu cầu nâng cấp thuật toán Vietlott, và khi được hỏi giữa sửa tiến trình hay nâng mô hình, đã chọn
«vẫn thử nâng mô hình dự báo».

## Engine đã có gì

Engine (`vietlott_engine.forecast.engine`) đã là một hỗn hợp Bayes chia sẻ cố định (Herbster–Warmuth) với:

- chuyên gia thích nghi: nóng/lạnh, EWMA, Dirichlet, logistic học trực tuyến;
- một rổ «tilt» thưa: mỗi giả thuyết một chữ số ở một vị trí lệch ±10–25%;
- bằng chứng e luôn hợp lệ so với máy công bằng.

Tín hiệu thật duy nhất nó tìm ra là chữ số 6 ở hàng đơn vị của Max 3D và Max 3D Pro, với e đỉnh 10^2,57 và
10^2,84.

**Bộ máy Bayes theo đoạn (BOCPD Dirichlet) không giúp ở đây.** Thử đúng bộ máy vừa đưa vào XSMB
(`forecast.cage_bayes`) trên các trò chữ số:

| Sản phẩm | BOCPD Dirichlet: log₁₀ W cuối / đỉnh | Engine: cuối / đỉnh |
|---|---|---|
| Max 3D | +0,88 / +2,19 | +1,67 / +2,57 |
| Max 3D Pro | +0,41 / +2,09 | +1,45 / +2,84 |

Tín hiệu là thưa: chỉ một chữ số ở một vị trí. Một Dirichlet đầy đủ phải trả giá học 27 tham số, trong khi tilt
một tham số thì không. Docstring của `vlm.forecast.bayes_expert` đã cảnh báo đúng điều này.

## Ý tưởng: hai sản phẩm, một độ lệch

Max 3D (từ 04-2019, quay thứ Hai/Tư/Sáu) và Max 3D Pro (từ 09-2021, quay thứ Ba/Năm/Bảy) cùng một khuôn: 20 số
ba chữ số mỗi kỳ. Cả hai lệch cùng một chữ số, ở cùng một vị trí, cỡ như nhau. Tỉ lệ chữ số 6 ở hàng đơn vị
theo năm (seed tới 30-09-2026 và 01-10-2026):

| Năm | Max 3D | Max 3D Pro |
|---|---|---|
| 2021 | 11,1% (z +2,0) | 12,1% (z +2,2) |
| 2022 | 10,4% (+0,7) | 10,9% (+1,6) |
| 2023 | 11,1% (+2,1) | 12,7% (+4,9) |
| 2024 | 11,7% (+3,2) | 9,8% (−0,4) |
| 2025 | 10,5% (+1,0) | 10,8% (+1,5) |
| 2026 | 11,2% (+1,9) | 10,8% (+1,3) |

Nếu nguyên nhân là chung, như cùng bộ máy hay cùng bộ bóng, thì dữ liệu của sản phẩm này là bằng chứng cho sản
phẩm kia. Engine học riêng từng sản phẩm nên bỏ phí một nửa dữ liệu. Năm 2024 cho thấy nguyên nhân không trùng
hoàn toàn: Max 3D Pro hết lệch đúng năm Max 3D lệch mạnh nhất.

## Luật

Với mỗi sản phẩm, dự báo là hỗn hợp chia sẻ cố định của hai luật:

- **luật riêng:** chính `Component` của engine, học riêng sản phẩm ấy. Đây là luật engine đang công bố.
- **luật gộp:** cùng `Component`, học mọi kỳ của cả hai sản phẩm theo thời gian.

Các tham số:

- **Tiên nghiệm** 0,5 / 0,5.
- **Tốc độ chuyển** là chính tốc độ của engine (`Forecaster.SWITCH_YEARS`), tức một lần mỗi mười năm, 1/1 560
  kỳ. Không có tham số nào chỉnh theo dữ liệu.
- **Thứ tự chấm và học:** theo ngày. Mọi kỳ của một ngày được chấm xong mới học kỳ nào của ngày ấy, để luật gộp
  không thấy kỳ cùng giờ của sản phẩm kia.

**Bảo đảm tất định.** Với mọi dãy kết quả, log-loss của hỗn hợp không vượt luật riêng quá
`−ln 0,5 − T·ln(1 − 1/1 560)`: 0,62 log₁₀ với 1 162 kỳ Max 3D, 0,53 với 808 kỳ Max 3D Pro.

## Kết quả walk-forward (dữ liệu tới 23-11-2026 và 21-11-2026)

Đơn vị là log₁₀ của tỉ số hợp lý so với máy công bằng, cộng trên các kỳ. Chênh lệch giữa hai luật là tổng của
chênh lệch log-likelihood từng kỳ.

| Sản phẩm | Kỳ | Luật riêng | Luật gộp | Hỗn hợp | Hỗn hợp − riêng (z) | Trọng số luật gộp lúc cuối |
|---|---|---|---|---|---|---|
| Max 3D | 1 162 | +1,50 | +4,74 | **+4,42** | **+2,92 (3,15)** | 0,96 |
| Max 3D Pro | 808 | +1,60 | +0,92 | +1,58 | −0,02 (−0,02) | 0,12 |

Theo năm, phần lợi của Max 3D đến từ 2023 (+0,68), 2024 (+0,34), 2025 (+1,25) và 2026 (+0,75): đó là lúc Max 3D
Pro đã đủ dài để góp dữ liệu. Với Max 3D Pro, hỗn hợp được lợi năm 2024 (+0,57) và trả lại ở các năm khác.
Cả hai không bao giờ vượt quá cận lý thuyết.

Luật kỳ tới cũng đổi theo. Với Max 3D, hỗn hợp cho chữ số 6 ở hàng đơn vị hệ số ×1,047 so với mức đều, trong
khi luật riêng cho ×1,072. Luật gộp ước lượng độ lệch nhỏ hơn mà vẫn chấm tốt hơn, vì nó học trên gấp đôi dữ
liệu. Với Max 3D Pro, hỗn hợp cho ×1,073, luật riêng ×1,077.

## Trung thực

- **Hồi cứu.** Ý tưởng gộp hai sản phẩm nảy ra SAU khi đã thấy cả hai lệch, nên bảng trên chỉ là mô tả. Không có
  tham số nào chỉnh theo dữ liệu, nhưng chính việc chọn cặp sản phẩm là một lựa chọn hậu nghiệm.
- **Phép kiểm tiến cứu.** Luật đóng băng cùng `VERSION = 1`. `REGISTERED_ON = 25-11-2026`, nên kỳ chấm đầu
  tiên là 26-11-2026, chưa quay lúc commit. Mỗi kỳ ghi chênh lệch log-likelihood của hỗn hợp so với luật riêng,
  và so với máy công bằng.
  - Đủ điều kiện xét bật khi chênh lệch so với luật riêng trên kỳ tiến cứu đạt z ≥ 2,326 (một phía, α = 0,01).
  - Sổ không bao giờ sửa dòng cũ. Tính lại khác dòng đã ghi thì `ledger_consistent = false`.
- **Chạy bóng.** Module không đổi luật engine, checkpoint (`VERSION = 5` của bộ ML), e-value hay vé đang công bố.
  Theo luật «challenger mặc định tắt», muốn đưa luật này vào dự báo công bố phải qua phép đo tiến cứu, rồi là
  một quyết định riêng.
- **Thay đổi duy nhất ngoài module:** `.gitignore` và `persist_site.FILES` thêm hai tệp mới, và `vlm-results.yml`
  thêm một bước (`continue-on-error`). Bước này lỗi thì các bước khác vẫn chạy như cũ.

## Phép kiểm

`vietlott/tests/test_vlm_transfer.py` canh:

- cận chia sẻ cố định trên mọi tiền tố;
- học nhanh hơn khi hai sản phẩm lệch chung, và luật kỳ tới nghiêng về luật gộp;
- lùi về luật riêng khi hai sản phẩm khác nhau;
- kỳ cùng ngày không thấy nhau;
- sàn trọng số của chia sẻ cố định;
- sổ tiến cứu chỉ chấm kỳ sau ngày đăng ký và không bao giờ sửa dòng cũ;
- ghi tệp tất định;
- tệp đã commit mang đúng luật đang chạy.

Đột biến từng luật đều làm phép kiểm đỏ: học ngay trong ngày, bỏ chia sẻ cố định, chấm cả ngày đăng ký, ghi trùng
sổ, luật gộp không học, luật trộn bỏ luật gộp, điểm trộn bằng luật riêng.

## Việc tiếp theo

1. Đọc sổ tiến cứu sau vài chục kỳ. Mỗi sản phẩm quay 156 kỳ một năm, và độ lệch thì nhỏ. Lợi thế hồi cứu của Max
   3D là +2,92 log₁₀ qua 1 162 kỳ, tức khoảng 0,0058 nat mỗi kỳ. Cỡ ấy cần vài trăm kỳ tiến cứu mới đạt z ≥ 2,326.
2. Thêm một khối nhỏ lên trang Vietlott, in kết quả từ `transfer.json`, nếu chủ dự án muốn thấy nó trên trang.
