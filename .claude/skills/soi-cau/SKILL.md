---
name: soi-cau
description: Soi cầu vị trí XSMB trong kho này — luật đã giải mã của hai trang soi cầu tham chiếu (107 vị trí chữ số, lộn/không lộn, nháy, Đặc Biệt, bạch thủ, hai nháy, bộ số, theo thứ), cách đọc trang tham chiếu bị proxy chặn, cách dựng lại vị trí cầu từ lớp CSS của trang, và kỷ luật kiểm chứng (đối chiếu từng ô, kiểm lịch sử, đột biến). Dùng khi thêm/sửa kiểu cầu, trang cầu, ô "cầu đẹp nhất", hoặc khi chủ dự án đưa một trang soi cầu mới để học theo.
---

# Soi cầu vị trí — kỹ năng đã học

## Mã nguồn

| Tệp | Vai trò |
|---|---|
| `src/position_bridges.py` | Luật trang tham chiếu thứ nhất (tham số `vt=AxB&limit&exactlimit&lon&nhay&db`), ô "cầu đẹp nhất" trang chủ, kiểm lịch sử |
| `src/bridge_rules.py` | Bảy kiểu cầu của trang tham chiếu thứ hai (bảng đầu 0–9 + số cầu mỗi ô) |
| `src/build_position_bridges.py`, `src/build_bridge_pages.py` | Trang `soi-cau-vi-tri.html`, `soi-cau-*.html`, `tao-phoi-tuan.html` |
| `src/templates/position_bridges.js`, `bridge_pages.js`, `weekly_sheet.js` | Bộ máy trình duyệt — PHẢI ra đúng từng cầu như bản Python |

## Nền chung

- 107 vị trí chữ số, đánh từ 0 theo thứ tự in: ĐB 0–4, G1 5–9, G2 10–19, G3 20–49,
  G4 50–65, G5 66–89, G6 90–98, G7 99–106.
- Cầu (a, b) của kỳ t cho số `10·d[a] + d[b]`. Cầu "chạy N ngày" = N BƯỚC kỳ-sang-kỳ
  liên tiếp gần nhất đều trúng, theo KỲ QUAY (Tết không phải kỳ trượt).
- Bóng: 0↔5, 1↔6, 2↔7, 3↔8, 4↔9. Bộ của xy = {x, x̄} × {y, ȳ} cả hai chiều (bộ 03 =
  03 30 08 80 53 35 58 85; bộ 00 chỉ có 4 số).

## Trang tham chiếu thứ nhất (tham số `vt=`)

- Lộn: a < b, báo {ab, ba}; LOTO trúng khi TỔNG nháy của hai chiều ≥ `nhay` (45 một lần
  + 54 một lần = 2 nháy). Không lộn: a ≠ b, thứ tự có nghĩa, chỉ ab.
- `db=1`: trúng khi hai số cuối ĐB ∈ {ab, ba}.
- Số kép là MỘT số; số bóng (44 → 99) chỉ HIỆN kèm ở ô tóm tắt. Tính bóng vào phép
  trúng thì ngày 28-09-2026 ra 64 cầu thay vì 43 — đã kiểm.
- "Thống kê cầu lặp": số cầu giảm dần, hoà thì theo lần xuất hiện đầu trong danh sách
  cầu (đã xếp theo số đầu rồi vị trí).
- Bảng đường cầu: kỳ mới trước; chữ số nguồn tô xanh; ô vàng là số về theo cầu của
  KỲ TRƯỚC (tô cả khi chưa đủ nháy).

## Trang tham chiếu thứ hai (bảng đầu 0–9)

Mọi kiểu: a < b, ô = số `10·d[a]+d[b]` của kỳ cuối, giá trị ô = số cầu báo số ấy.

| Kiểu | Bước t → t+1 trúng khi |
|---|---|
| LOTO | ab hoặc ba về ≥ 1 |
| Hai nháy | ab về ≥ 2, HOẶC ab và ba (khác nhau) cùng về — BẤT ĐỐI XỨNG: ba về 2 lần không tính |
| Bạch thủ | đúng ab về ≥ 1 |
| Đặc Biệt | a hoặc b trùng hàng chục/đơn vị hai số cuối ĐB; "cả hai chữ số" = ĐB ∈ {ab, ba} |
| Bộ số | bộ(ab kỳ t) == bộ(ab kỳ t+1) — số GIỮ NGUYÊN BỘ; cầu báo ĐB kỳ sau rơi vào bộ ấy |
| Theo thứ | như LOTO / Đặc Biệt nhưng chỉ trên các kỳ cùng thứ |

Tham số mặc định (số ngày cầu chạy): LOTO 3, hai nháy 2, bạch thủ 3, Đặc Biệt 2, bộ số 2,
theo thứ 3. Đối chiếu 28-09-2026: 315 / 24 / 66 / 741 / 32 / 179 (Chủ Nhật) cầu, trùng
từng ô — `tests/fixtures/bridge_reference_2026-09-28.json`.

## Đọc trang tham chiếu (proxy chặn)

1. Dispatch `.github/workflows/inspect-reference-bridge.yml` (input `urls` cách nhau
   dấu phẩy, `max_rows`), ref `main`.
2. Lấy job id (`actions_list list_workflow_jobs`), đọc log (`get_job_logs`); log lớn thì
   lưu tệp, parse JSON `logs_content`, bỏ tiền tố thời gian.
3. Log in điều khiển biểu mẫu, chữ trên trang (cắt 5 000 ký tự), liên kết, từng ô bảng
   kèm lớp CSS và CSS của các lớp.

## Giải mã khi đoán không ra

- Đừng đoán quá ba lần. Tìm dữ liệu vị trí ngay trên trang: trang thứ hai gắn lớp
  `digit.<id>.<id>…` cho từng chữ số của bảng kết quả — mỗi id là một cầu, nên hai chữ
  số mang cùng id là hai vị trí của cầu đó. Luật bộ số được giải bằng cách dựng lại đúng
  32 cặp vị trí rồi xem số của chúng qua ba kỳ (35 → 03 → 85: cùng bộ 03).
- So khớp bằng CHÍNH dữ liệu `data/xsmb.csv` cắt tới đúng ngày của trang tham chiếu;
  đối chiếu cả tổng, từng ô, "cầu dài nhất" và thứ tự xếp hạng — khớp tổng chưa đủ.

## Kỷ luật

- Ghim số đối chiếu trong phép kiểm Python VÀ so bộ máy JS với Python bằng jsdom
  (`tests/frontend/position-bridges.test.mjs`, `bridge-pages.test.mjs`).
- Mỗi phép kiểm mới phải thử đột biến (đổi đúng luật nó canh → phải đỏ).
- Kiểm lịch sử là bắt buộc: trên 4 217 kỳ, cầu dài hơn KHÔNG trúng nhiều hơn ở bất kỳ
  kiểu nào; nhiều cầu cùng báo một cặp cũng không. Trang in kết luận TỪ SỐ ĐO. Đừng thêm
  "điểm tin cậy" theo độ dài cầu; đừng gọi cầu là "dự đoán".
- Trang xuất bản: không tên host/nguồn, không chuỗi `vla`, không gán chuỗi HTML (chỉ
  `createElement` + `textContent`), biểu mẫu phải tự chặn `submit` vì CSP có
  `form-action 'none'`, mọi màu đọc token.
- Thêm trang: SITE_NAV + `app_icons.BIEU_TUONG` + `nexlink_icons._NAVIGATION` +
  `tests/test_app_icons.py` REFERENCE_MAP + số mục nhóm trong `tests/frontend/navigation.test.mjs`
  + pipeline (trước `build_landing_page`) + danh sách `test -s` / production_audit / release_check.

## Phương pháp "tổng – bóng – chạm" của chuyên mục bài dự đoán (05-10-2026)

`src/digit_sum_rules.py` — luật đã giải mã từ loạt bài tuần, khớp từng con số (ghim trong
`tests/test_digit_sum_rules.py`). tổng(xy) = (x + y) mod 10, bóng(x) = x + 5 mod 10, giải đệm 0
đủ độ dài.

| Quy tắc | Công thức |
|---|---|
| Đầu ĐB | {tổng 2 số CUỐI ĐB, bóng} |
| Đuôi ĐB | {tổng 2 số ĐẦU ĐB, bóng} |
| Chạm | {tổng 2 số cuối giải nhất, bóng}; dàn = {cd, dc}, d ∈ 3 số đầu ĐB và bóng |
| Lô cặp G5 | lộn {tổng 2 số đầu G5.2, tổng 2 số cuối G5.4} |
| Song thủ lô | lộn {tổng 2 số cuối G2.1, tổng 2 số đầu G1} |

Khung: Chủ Nhật mở tuần (đầu – đuôi cả tuần; chạm thứ Hai – Năm; lô G5 thứ Hai – Ba; song thủ
thứ Hai), thứ Năm mở cuối tuần. Loạt bài HẰNG NGÀY không tái lập được (BTL/STL không khớp chính
phương pháp bài nêu). Kiểm 4 225 kỳ: cả năm quy tắc ngang chọn bừa (p Holm ≥ 0,966); "nổ cả
tuần" là do khung dài (1 − 0,8⁷ ≈ 79%). Mốc LOTO có điều kiện: 1 − C(100 − m, k)/C(100, k), m = số
con khác nhau đã về. Bằng chứng tiến cứu cộng dồn trong `digit_sum_hypothesis` (sổ
`data/hypotheses/digit_sum_rules.csv`, từ kỳ 06-10-2026, kết luận sau 180 kỳ) — đọc trạng thái ở
đó trước khi nói một quy tắc "đang chạy". Đọc bài: dispatch `inspect-reference-articles.yml` (`start_url`), log dài thì
lưu tệp rồi tách theo dòng `BÀI`.
