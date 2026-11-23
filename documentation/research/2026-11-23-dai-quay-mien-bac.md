# Đài quay miền Bắc: kết quả có khác theo đài không, và thuật toán thích nghi ra sao khi cách quay đổi

Ngày 23-11-2026. Mã: `src/core/xsmb_schedule.py`, `src/stats/xsmb_venue_effects.py`. Số đo: `data/stats/venue/`.
Thẻ «Đài quay miền Bắc» trên `docs/research-lab.html` in kết luận từ tệp số đo, không viết cứng.

## Câu hỏi

Chủ dự án hỏi: khi cách quay của từng thành phố miền Bắc thay đổi, thuật toán có thích nghi không? Có
nắm bắt được cách quay của từng địa điểm trong tuần, để tính xác suất chuẩn hơn cho từng khu vực không?

## Căn cứ về cách quay

- Từ 01-09-2005, Công ty XSKT Thủ Đô thay mặt Hội đồng XSKT miền Bắc tổ chức **một lần quay chung** cho
  mọi công ty trong khu vực (Quyết định 2564/QĐ-BTC). «Đài» của một ngày là công ty phát hành vé hôm ấy.
  Mỗi ngày chỉ có một bộ 27 giải; không đài nào có bộ máy quay riêng.
- Lịch luân phiên đang ghi nhận: Hà Nội (thứ Hai, thứ Năm), Quảng Ninh (thứ Ba), Bắc Ninh (thứ Tư), Hải
  Phòng (thứ Sáu), Nam Định (thứ Bảy), Thái Bình (Chủ Nhật).
- Công văn 15825/BTC-DCTC (10-10-2025) đề nghị xây dựng lịch quay mới sau đợt sáp nhập tỉnh, dự kiến
  áp dụng từ 2026 (Nam Định thuộc Ninh Bình, Thái Bình thuộc Hưng Yên). Tới 23-11-2026 kết quả vẫn mang
  nhãn cũ; kho chưa có lịch mới chính thức.

## Thuật toán trước đợt này

| Chỗ | Vấn đề |
|---|---|
| `web/draw_metadata.STATIONS` | Bảng 7 đài cố định theo thứ, không có mốc hiệu lực: lịch đổi là đổi nhãn của CẢ lịch sử. Tên đài trong `data/draw_metadata.json` cũng suy từ bảng này, không đọc từ trang nguồn. |
| `stats.randomness_battery.weekday_effect` | Chia thứ bằng **chỉ số hàng chia 7**. Sổ chuẩn vắng mọi ngày không quay (mỗi Tết, 23 ngày giãn cách 2020), nên sau mỗi khoảng trống nhãn lệch khỏi thứ thật. Báo cáo 08-09-2026 in p = 0,024 cho một «hiệu ứng thứ» không tồn tại theo lịch thật. |
| Mô hình dự báo | Không mô hình nào phân biệt đài. Vài đặc trưng dùng thứ (`same_weekday_freq_364` của Cầu Kèo, trang soi cầu theo thứ), không có phép kiểm nào cho biết thứ hay đài có làm kết quả khác đi không. |
| Giám sát | Không có gì phát hiện được một đài, hay bộ máy chung, bắt đầu ra số lệch. |

## Thay đổi

1. **`core.xsmb_schedule`**: lịch đài có thời kỳ (`ERAS`), mỗi thời kỳ có ngày bắt đầu, 7 đài và căn cứ.
   `venue_for(ngày)` trả đài theo lịch có hiệu lực hôm đó. Khi lịch mới chính thức có hiệu lực, **thêm một
   thời kỳ** với đúng ngày áp dụng; các kỳ trước giữ nhãn cũ, và phân tích theo đài tự tách dãy của tên
   mới. `web/draw_metadata` dùng nó; phép kiểm cấm chép bảng đài ở chỗ khác.
2. **`stats.xsmb_venue_effects`** (bước pipeline, khoảng 15 giây):
   - *Đồng nhất*: 5 thống kê (100 con LOTO, 2 số cuối Đặc Biệt, chữ số ở 107 vị trí, chữ số theo 5 lồng,
     số con khác nhau mỗi kỳ) × 2 cách gom (6 đài, 7 thứ). p bằng **hoán vị nhãn giữa các kỳ** (1 999
     lần; giữ nguyên mọi phụ thuộc trong một kỳ), Holm trên cả họ 10 phép kiểm.
   - *Lồng cầu từng đài*: χ² đều (mô tả), e-process KT tính từ kỳ đầu của thời kỳ (đã từng lệch chưa),
     và **e-detector Shiryaev–Roberts** với ước lượng KT quên dần (nhớ khoảng 104 kỳ) để phát hiện một
     đài **bắt đầu** lệch. Thêm dãy **«Toàn miền Bắc»** trên mọi kỳ: lỗi ở bộ máy chung hiện ở mọi đài, và
     dãy gộp thấy nhanh gấp khoảng 7 lần tính theo ngày.
   - *Xác suất theo đài*: walk-forward 730 kỳ cuối, mỗi kỳ chỉ dùng kỳ trước nó. Ba mô hình: hằng số, tần
     suất gộp, tần suất riêng đài co về tần suất gộp (κ học bằng hợp lý biên Dirichlet–đa thức trên các
     kỳ trước cửa sổ). Đề bạt chỉ khi thắng CẢ hằng số LẪN tần suất gộp với z ≥ 2,326.
   - *Mô hình lồng thích nghi*: xác suất con LOTO từ lồng chục × lồng đơn vị (KT quên dần), luôn bật hoặc
     chỉ bật khi e-detector của dãy gộp đang báo động ở kỳ trước.
   - *Hồ sơ từng đài* (`xsmb_venue_profile.csv`): tỉ lệ thô cạnh mức nền, z, q (BH) và xác suất đã co cho
     mỗi (đài, con), cả LOTO lẫn Đặc Biệt.
3. **`randomness_battery.weekday_effect`** nhận thứ thật; `scripts/research/run_randomness_report.py`
   truyền thứ từ ngày. Báo cáo ngẫu nhiên chạy lại trên 4 273 kỳ.

## Số đo (sổ chuẩn 01-01-2015 → 21-11-2026, 4 273 kỳ)

- **Không có hiệu ứng đài hay thứ.** p sau Holm nhỏ nhất là 0,620 (2 số cuối Đặc Biệt theo đài; p thô
  0,066). LOTO theo đài p = 0,60; chữ số theo vị trí p = 0,59; theo lồng p = 0,09.
- **Xác suất riêng từng đài không chuẩn hơn.** Hợp lý biên chọn κ lớn nhất của lưới (10⁸), tức dữ liệu tự
  gộp mọi đài làm một. So với tần suất gộp z = +1,05 (LOTO), +0,77 (Đặc Biệt); chính tần suất gộp đã kém
  hằng số (LOTO z = −3,18). Xác suất cho mọi đài giữ mức chung: mỗi con LOTO 23,77%, mỗi số Đặc Biệt 1%.
- **Lồng cầu từng đài**: χ² mô tả nhỏ nhất ở Quảng Ninh (p = 0,0076, sau Holm 0,053, chưa tới α = 0,01).
  Không e-process nào vượt ngưỡng.
- **Một đợt lệch của lồng đơn vị trong năm 2024, ở dãy gộp.** E-detector «Toàn miền Bắc» báo động từ
  20-04-2024 tới 24-11-2024, đỉnh 10^13,5 so với ngưỡng 10^7,0, rồi về mức nền từ giữa 2025. Trong cửa sổ
  03–12/2024 (306 kỳ, chọn SAU khi thấy báo động nên chỉ là mô tả), lồng đơn vị có χ² = 61 (9 bậc tự do):
  chữ số 2 và 9 ra nhiều (z = +4,2 và +4,0), chữ số 8, 4, 1 ra ít. Bốn lồng còn lại bình thường. Độ lệch
  rải đều trên cả 27 giải, cùng chiều; lỗi bóc tách thường dồn vào vài giải. Đối chiếu với hai nơi ghi
  khác (mục «Đối chiếu đợt 2024» dưới đây) trùng từng ô trên cả 306 kỳ, nên độ lệch nằm trong kết quả công
  bố, không phải lỗi của sổ chuẩn.
- **Đợt ấy không làm xác suất chuẩn hơn được bao nhiêu.** Mô hình lồng thích nghi luôn bật kém hằng số
  (z = −5,85, trả giá học nhiễu); chỉ bật khi báo động thì +1,7·10⁻⁵ log-loss, z = +0,91 trên 3 908 kỳ, kể
  cả trong đợt 2024 (z = +0,90). Độ lệch ±15% ở vài chữ số hàng đơn vị chỉ đổi xác suất LOTO rất ít.
- **Báo cáo ngẫu nhiên** (4 273 kỳ, thứ thật): 0/7 phép kiểm bác bỏ tính ngẫu nhiên. Hiệu ứng thứ trong
  tuần p = 0,77 (bản cũ 0,024 do lệch nhãn). Tín hiệu duy nhất từng sống sót Bonferroni ở bản 08-09-2026
  (đỉnh phổ, p = 0,001) không còn trên lịch sử dài gấp đôi (p = 0,092).

## Hiệu chuẩn bộ phát hiện (hai lỗi đã sửa trong lúc làm)

- Bản đầu đặt ngưỡng e-detector bằng ARL mong muốn (2 000 kỳ) và báo động ở 3/6 đài. ARL chỉ bảo đảm
  THỜI GIAN TRUNG BÌNH tới báo nhầm; vì `E[R_t] = t`, xác suất báo nhầm trong n kỳ tới n/2 000 (0,3–0,6 mỗi
  đài). Ngưỡng nay là `H · số dãy / α`, với H là số kỳ của dãy trong 38 năm, nên xác suất báo nhầm của cả
  họ trong tầm ấy không quá α.
- Bản đầu dùng 999 hoán vị: p Holm nhỏ nhất đạt được là 10/1 000 = α, nên module không bao giờ kết luận
  được «khác nhau». Nay 1 999 hoán vị, và phép kiểm ghim luật ấy.
- Sức phát hiện (giả lập 5 lần, lỗi bắt đầu sau 400 kỳ công bằng của một đài): một quả ra 50% mức đều →
  73–115 kỳ; mất hẳn một quả ở lồng đơn vị → 24–42 kỳ; một quả ra 70% mức đều → thường quá 300 kỳ; không lỗi
  → không báo nhầm lần nào.

## Đối chiếu đợt 2024 với nơi ghi khác (23-11-2026)

**Sổ chuẩn lấy các kỳ ấy từ đâu.** Các kỳ 2015 → 08-2026 vào kho trong đợt bổ sung lịch sử tháng 9-2026
(`src/ingest/backfill_history.py`, PR #46 → #49), với `min_agreement = 1`. Mỗi kỳ lấy từ nguồn ĐẦU TIÊN bóc
được trong `default_sources` khi ấy: xoso.com.vn, rồi mketqua.net, rồi Minh Ngọc, rồi ba nguồn đã nghỉ. Kho không
ghi nguồn của từng kỳ (`data/source_audit.json` chỉ có các kỳ 2026), nên không biết chắc kỳ nào đến từ đâu.

**Cách làm.** `scripts/ops/crosscheck_canonical_history.py` đọc lại dải kỳ trên runner, vì máy phiên làm việc
không gọi được trang ngoài. Lệnh chạy là `diagnose-live-sources.yml` với `crosscheck_start` = 2024-03-01 và
`crosscheck_end` = 2024-12-31. Kịch bản bóc 27 giải bằng chính bộ bóc của kho (`ingest.sources`) và so từng ô với
`data/xsmb.csv`. Nó in từng ô khác, cùng số đếm chữ số lồng đơn vị trên bản ghi của nơi ghi kia. Không có gì
được ghi vào kho hay lưu lại.

| Nơi ghi | Trang đọc | Kỳ đọc được | Ô so | Ô khác | Lồng đơn vị (chữ số 0 … 9) trên bản ghi của nơi ấy |
| --- | --- | --- | --- | --- | --- |
| Minh Ngọc | 44 (mỗi trang bảy kỳ) | 306 / 306 | 8 262 | 0 | 843, 760, 941, 827, 744, 811, 886, 776, 739, 935; χ² = 60,97 |
| mketqua.net | 306 (mỗi trang một kỳ), rồi đọc lại 3 | 306 / 306 ¹ | 8 262 | 0 | trên 304 kỳ của lượt đầu: 840, 757, 937, 820, 737, 808, 880, 771, 732, 926; χ² = 61,00 |

¹ Lượt đầu (826 giây) đọc được 304 kỳ; hai trang 30-10 và 01-11-2024 lỗi kết nối. Lượt đọc lại 30-10 → 01-11 cho 3/3 kỳ, 81 ô, 0 ô khác.

**Kết luận.** Dù một kỳ đến từ nguồn nào trong sáu, Minh Ngọc và mketqua thuộc hai nhóm độc lập khác nhau
(`source_independence_key`). Ít nhất một trong hai vì thế khác nơi đã ghi kỳ ấy, và cả hai đều trùng từng ô. Độ lệch lồng đơn vị năm
2024 vì thế nằm trong kết quả được công bố. Nó không do khâu thu thập của kho, cũng không do lỗi của một nơi ghi.
Các trang tin đều chép từ buổi quay trực tiếp, nên phép đối chiếu không loại được một lỗi chung ở thượng
nguồn. Nhưng một lỗi chép rải đều trên 27 giải suốt tám tháng, cùng chiều, giống hệt nhau ở nơi đã ghi sổ
và ở hai nơi đối chiếu, là khó tin.

**Điều này đổi gì.** Không đổi gì ở dự báo. Mô hình chỉ bật khi e-detector báo động vẫn chỉ hơn hằng số z =
+0,91 trên 3 908 kỳ, nên đợt lệch thật nhưng quá nhỏ để khai thác. Không sửa sổ chuẩn. E-detector giữ nguyên
vai trò: báo động mới là lý do kiểm lại, không phải tín hiệu dự báo. Nguyên nhân vật lý (bộ bóng, cách vận
hành lồng cầu trong giai đoạn ấy) chưa rõ. Kho không tìm thấy nguồn đáng tin nào ghi việc thay máy hay bộ bóng
năm 2024.

Bộ đối chiếu được ghim ở `tests/repo/test_crosscheck_canonical_history.py`, trên bảy kỳ thật 09 → 15-06-2024
dựng theo hình dạng hai trang. Các phép kiểm canh: tách đúng bảy kỳ trên một trang, bỏ kỳ thiếu giải thay vì
mượn số của kỳ bên cạnh, bỏ trang trả kỳ khác ngày hỏi, báo đúng một ô khi đổi một chữ số, và bỏ trang vượt trần
thời gian tổng. Đổi đúng thứ mỗi phép kiểm canh thì nó đỏ.

## Việc còn mở

1. **Khi lịch đài mới có hiệu lực**: thêm thời kỳ vào `core.xsmb_schedule.ERAS` đúng ngày áp dụng. Nên kèm
   đọc nhãn đài từ trang nguồn vào `data/draw_metadata.json` để phát hiện khi lịch đổi mà kho chưa biết.
2. Không đưa xác suất theo đài hay mô hình lồng thích nghi vào tổ hợp: cả hai đều không thắng ngoài mẫu.
   E-detector tiếp tục chạy mỗi lượt và in trạng thái lên trang; một lần báo động mới là lý do kiểm lại,
   không phải tín hiệu dự báo. Báo động mới trên các kỳ 2015 → 08-2026 thì đối chiếu bằng cùng lệnh trước khi
   kết luận gì.
