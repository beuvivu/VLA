# Báo cáo thi hành cuối — PHASE 1-8

Ngày 2026-09-21. Nhánh: `main` và `claude/statistical-audit-2026-09-lwfyt2`.

Quy tắc của tài liệu này: **chỉ ghi việc THẬT SỰ đã xảy ra.**

## Trạng thái theo PHASE

| PHASE | Trạng thái | Bằng chứng |
|---|---|---|
| 1 — Discovery | xong | 29 trang khôi phục từ git history; 864 tệp dữ liệu / 473 MB trong 23 thư mục |
| 2 — Design research | **xong CÓ GIỚI HẠN** | Cả 5 reference + trang production bị chặn 403 CONNECT. Nguồn thay thế: mô tả của chủ dự án |
| 3 — Master Design System | xong | 54 phép đo tương phản, 0 không đạt |
| 4 — Global App Shell | xong | 28 phép kiểm Chromium ở 7 viewport |
| 5 — Page-by-page | xong | **29/29 trang**, khớp chính xác mô hình điều hướng |
| 6 — Specialized analytics | xong | Bố cục 6.1 và 6.2; bảng nâng cao; trạng thái rỗng/lỗi |
| 7 — Regression & QA | xong | 420/420 lượt viewport sạch; bộ kiểm đầy đủ |
| 8 — Final verification | xong | Đối chiếu hai chiều điều hướng ↔ thư mục xuất bản |

## Trang đã dựng

**29/29.** Đối chiếu hai chiều với mô hình điều hướng: không thiếu, không thừa.

Nhóm: Tổng quan 4 · Kết quả 2 · Đặc Biệt 8 · Lô tô 5 · Dự đoán & Mô hình 3 ·
Soi path 4 · Nghiên cứu 1 · Biến thể trang chủ 2 (ngoài sidebar).

## Thành phần dùng chung

`tokens` · `stylesheet` · `shell_css` · `component_css` · `shell` ·
`navigation` · `icons` (21 hình) · `blocks` · `data_access` ·
`ensemble_view` · `assets/vla-shell.js`.

## Lệnh đã chạy

```
ruff check src tests scripts
PYTHONPATH=src python3 -m pytest tests -q
PYTHONPATH=src python3 src/build_site.py
PYTHONPATH=src python3 src/build_shell_preview.py
```

## Kết quả đo

| Phép đo | Kết quả |
|---|---|
| Tương phản WCAG AA | 27 cặp × 2 bảng màu = **54/54 đạt**, biên thấp nhất 1,025× |
| Tràn ngang | **0/420** lượt (30 trang × 7 viewport × 2 chủ đề) |
| Lỗi console | **0** trên 29/29 trang |
| Tài nguyên tải lỗi | **0** trên 29/29 trang |
| Trang có CSP | 29/29 |
| Bảng có `<caption>` | tất cả |
| Đột biến đã giết | **60+** qua các lượt |

## Lỗi đã sửa

**Trình duyệt tìm ra 5 lỗi mà đọc CSS không thấy:** nút ba gạch hiện ở
1440px (thứ tự khai CSS); liên kết điều hướng cao 39px; `frame-ancestors`
bị bỏ qua trong `<meta>`; số KPI xuống hai dòng ở đúng 1024px; tên tệp dài
làm tràn trang ở 320px.

**Ảnh chụp tìm ra 3 lỗi thiết kế:** tiêu đề lặp hai lần; 4 thẻ KPI xếp dọc
chiếm ~580px; mốc 380px loại đúng 375px.

**Đột biến tìm ra 5 phép kiểm yếu của chính tôi:** hợp đồng tương phản chỉ
đòi token xuất hiện "đâu đó" (che mất lỗi `text-secondary`); cảnh báo tính
cả chân sidebar nên luôn xanh; mục đang mở chỉ đếm số lượng nên trỏ sai trang
vẫn xanh; cột đường cơ sở chỉ kiểm tồn tại không kiểm giá trị; đường cơ sở
làm tròn khác nhau giữa các trang.

## Giới hạn còn lại — nói rõ, không giấu

1. **Năm reference và trang production không truy cập được** (403 CONNECT).
   Không nhận xét nào về hình thức thật của chúng được phát biểu. Nếu mở được
   egress, phải đối chiếu lại thiết kế.
2. **Không kiểm chứng được deploy** vì trang production bị chặn. Phải do chủ
   dự án xác nhận sau khi CI chạy.
3. **VLA không được bảo vệ khỏi bị nhúng iframe.** `frame-ancestors` chỉ
   hoạt động qua HTTP header mà GitHub Pages không cho đặt. Cần CDN cho phép
   đặt header.
4. **`live.html` không phải luồng trực tiếp.** Kho chưa có hợp đồng dữ liệu
   cho kết quả đang về; trang nói rõ điều đó thay vì giả vờ.
5. **`soi-path-de-active.html` ở trạng thái rỗng** vì tệp nguồn chỉ có dòng
   tiêu đề. Đúng dữ liệu, không phải lỗi.
6. **Chưa có biểu đồ.** Mọi số liệu hiện ở dạng bảng. Mục XV liệt kê
   `Frequency Chart`; chưa dựng.
7. **Chưa có sắp xếp/lọc/phân trang phía trình duyệt.** Bảng dài hiện đầy đủ
   hàng, cuộn trong khung. Mục 6.4 liệt kê các tính năng này là "where
   appropriate"; chúng cần JavaScript thao tác DOM, và ràng buộc cấm DOM sink
   khiến chúng phải dựng bằng `createElement` — làm được, chưa làm.
8. **Ma trận thống kê ô-lưới (mục 6.3) chưa dựng.** Các trang hiện dùng bảng;
   hệ màu ô trúng/trượt với hoa văn chéo chưa thi hành.

## Không tuyên bố

Không tuyên bố sản phẩm không còn lỗi. Tám giới hạn trên là những gì tôi
BIẾT còn thiếu; có thể còn thứ tôi chưa biết.
