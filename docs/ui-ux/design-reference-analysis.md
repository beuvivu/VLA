# Phân tích tham chiếu thiết kế

## Giới hạn TRUY CẬP — đọc trước mọi thứ khác

Cả năm tham chiếu **và** trang production đều bị chặn bởi network egress
policy. Đo bằng `curl` qua agent proxy lúc 2026-09-21T13:23Z; cả sáu lần đều
là `connect_rejected`, gateway trả **403 cho CONNECT**:

| URL | Kết quả |
|---|---|
| `https://tapotik-ai.vercel.app/` | 403 CONNECT |
| `https://themes.coderthemes.com/paces/index.html` | 403 CONNECT |
| `https://nexlink.layoutdrop.com/demo/index.html` | 403 CONNECT |
| `https://gxon.layoutdrop.com/laravel/demo/` | 403 CONNECT |
| `https://preskool.dreamstechnologies.com/html/teacher-dashboard.html` | 403 CONNECT |
| `https://beuvivu.github.io/VLA/` | 403 CONNECT |

Không phải lỗi tạm thời: `curl -sS "$HTTPS_PROXY/__agentproxy/status"` liệt kê
đủ sáu lần từ chối trong `recentRelayFailures`.

Mục II của spec quy định: *"If a reference is inaccessible, explicitly document
the limitation and use verifiable screenshots or existing project references
rather than inventing observations."*

**Vì vậy không một nhận xét nào trong tài liệu này mô tả hình thức thật của năm
trang đó.** Nguồn duy nhất là mô tả mà chính chủ dự án đã viết trong spec —
quan sát của người CÓ truy cập.

## Nguyên tắc đã áp dụng, theo nguồn

| Nguyên tắc | Nguồn | Đã làm gì trong VLA |
|---|---|---|
| Bento Grid, hình học nhất quán | mô tả Tapotik AI | Lưới 12 cột, thẻ chung một bán kính và một thang shadow |
| Glassmorphism có chọn lọc | mô tả Tapotik AI | CHỈ dùng ở topbar (`--vla-surface-glass`), không dùng dưới bảng thống kê |
| Dark mode cao cấp | mô tả Tapotik AI | Nền navy `#0A0D18`, thiết kế riêng, không đảo ngược |
| Kiến trúc dashboard doanh nghiệp | mô tả Paces | Một shell duy nhất cho 29 trang, token tập trung |
| Token mở rộng được | mô tả Paces | `tokens.py` là nguồn duy nhất, CSS sinh ra từ đó |
| KPI và thẻ phân tích | mô tả NexLink | `.vla-kpi-grid` với thang chữ riêng theo bề rộng |
| Nhấn chàm/tím | mô tả NexLink | `--vla-primary #5941C8` (đã tinh chỉnh theo đo tương phản) |
| Bảng nâng cao | mô tả Paces + GXON | Đầu bảng dính, sọc vằn nhạt, cuộn trong khung |
| Chỉ báo trạng thái | mô tả GXON | Badge `-soft`/`-ink`, sáu sắc thái ngữ nghĩa |
| Nhóm thông tin, truy cập nhanh | mô tả PreSkool | Sidebar 7 nhóm `<details>`, thẻ dẫn nhánh ở trang chủ |

## Điều KHÔNG áp dụng, và vì sao

**Typography lớn.** Mô tả Tapotik AI nhấn "contemporary typography", thường đi
kèm chữ lớn. VLA là sản phẩm dày dữ liệu; mục 4.2 của chính spec cảnh báo
"avoid oversized typography that reduces the amount of usable analytical
information". Thang chữ ở đây nằm ở cận DƯỚI của khoảng spec cho.

**Gradient nhiều màu.** Đẹp trên trang giới thiệu, nhưng nền có gradient làm
mất khả năng bảo đảm tương phản chữ — và hợp đồng tương phản của VLA kiểm 27
cặp × 2 bảng màu bằng số học chính xác, không kiểm được trên gradient.

**Glassmorphism dưới bảng.** Mục 4.4 cấm, và lý do đo được: `rgba()` không
tính được độ chói nếu không biết nền dưới nó, nên không bảo đảm được đọc ra.
Hàm `relative_luminance` của VLA NÉM LỖI cho đầu vào `rgba()` thay vì trả một
con số vô nghĩa.
