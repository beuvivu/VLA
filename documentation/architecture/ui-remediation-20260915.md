# Đặc tả Master UI Remediation VLA — 2026-09-15

## Mục tiêu

Chuẩn hóa các màn hình VLA được người dùng chỉ định về cùng Master Design System: **Soft Modern UI + Bento Grid**, nền sáng gradient, glass surface nhẹ, container `max-w-7xl`, mật độ dữ liệu cao nhưng không dàn trải, bảng không phá container, dock/footer không che nội dung và responsive ổn định trên desktop/mobile.

## Phạm vi thực thi

Danh sách yêu cầu hiện tại có 11 URL được nêu trực tiếp, cộng `soi-path-de-active.html` đã được bổ sung ở lượt trước. Vì bốn trang soi cầu dùng cùng một nguồn giao diện, contract được áp dụng nhất quán cho cả active/stable của LOTO và Đặc Biệt.

1. `live.html`: chuyển từ console tối sang Realtime Bento sáng; giữ nguyên polling, reveal animation, source consensus và toàn bộ ID JavaScript.
2. `bang-dac-biet.html`: bảng tuần giãn đủ chiều rộng card/box điều khiển; mobile giữ scroll an toàn.
3. `lo-gan.html`: giới hạn chiều cao bảng, dùng scroll nội bộ và Bento hai cột để giảm chiều dài trang.
4. `dau-duoi-loto.html`: hai bảng Đầu/Đuôi cân bằng; ba bảng 20 kỳ gần nhất xếp thành responsive Bento grid.
5. `giai-dac-biet-theo-tong.html`: chống overflow/vỡ khung cho bảng tổng, transition và parity trên mọi breakpoint.
6. `soi-path-loto-active.html`: chuẩn hóa hero, quick-pick, matrix card và vùng scroll theo Master Design System.
7. `dashboard.html`: nâng thành AI/ML Command Center với glass cards, Indigo accent, status widgets và hierarchy rõ.
8. `cau-dac-biet-theo-bo-so.html`: áp dụng Soft Modern/Bento và bounded scroll.
9. `giai-db-ngay-mai.html`: áp dụng Soft Modern/Bento và bounded scroll.
10. `cap-lon-loto.html`: áp dụng Soft Modern/Bento, bảng chính/kép cân đối và bounded scroll.
11. `research-lab.html`: High-Tech Data Lab/Cyber-Lab trên nền hệ thống sáng; hero tối, LED accent nhẹ, pipeline kiểm chứng, experiment modules, scanning effect và monospace.
12. `soi-path-de-active.html`: sửa triệt để dock/footer overflow; cùng contract với LOTO. Hai sibling `soi-path-loto-stable.html` và `soi-path-de-stable.html` tự động nhận cùng layout để tránh phân nhánh giao diện.

## Master Design System

- Page ground: `linear-gradient(135deg, #F4F5FF 0%, #EAEBFF 48%, #E8ECFF 100%)`.
- Content width: 1280 px, tương đương `max-w-7xl`, căn giữa và có responsive gutter.
- Bento surface: trắng 82–90%, blur 12–18 px, border trắng mờ, shadow thấp, radius 18–24 px.
- Accent: Indigo `#4F46E5` / `#818CF8`.
- Ô không về: `#E2E8F0` + hatch xám gần `#9CA3AF`.
- Đặc Biệt: chữ `#DC2626`, nền `#FEE2E2`, viền đỏ.
- Dock/mobile: luôn có `env(safe-area-inset-bottom)` và vùng đệm theo `--ui-dock-h`.
- Reduced motion: các hiệu ứng quét LAB phải tôn trọng `prefers-reduced-motion`.

## Kiến trúc triển khai

Thay vì sửa riêng từng builder lớn, visual refinement được tập trung tại `src/ui_page_refinements.py` và áp dụng ở **output boundary** thông qua `src/page_output.write_page()`:

`builder/template → HTML semantic → refine_page(path, html) → strip_comments() → docs/*.html`

Cách này giữ builder tập trung vào dữ liệu/ngữ nghĩa, đồng thời bảo đảm pipeline hằng ngày sinh lại HTML vẫn tái áp dụng đúng Master Design System. Refinement dựa trên filename và class scope; trang không thuộc phạm vi là no-op.

## Ràng buộc an toàn

- `assets/ui.css` vẫn là stylesheet nền chuẩn; không khôi phục `assets/vla.css`.
- Không thay đổi công thức thống kê, xác suất, model, prediction artifact hoặc ngữ nghĩa dữ liệu.
- Không đổi/xóa element ID hoặc JavaScript hook hiện có.
- Không cắt dữ liệu để làm trang ngắn; dùng Bento hierarchy, bounded scroll, sticky header và responsive grid.
- Refinement phải idempotent vì `live.html` có thể được refresh nhiều lần trong cùng pipeline.
- Research Lab không được hiển thị gauge trang trí như xác suất trúng; gauge chỉ đại diện trạng thái cổng FDR/OOS/Reality Check và phải ghi chú rõ.

## Nguyên nhân gốc đã xác minh

- Các trang thống kê chi tiết dùng chung cấu trúc bảng vốn tối ưu cho bảng hẹp (`width:auto`/`fit-content`), khiến lịch/ma trận rộng co lệch hoặc dàn trải không phù hợp.
- `lo-gan.html` render nhiều bảng dài nối tiếp, tạo chiều cao trang quá lớn.
- `dau-duoi-loto.html` xếp ba bảng lịch sử theo chiều dọc thay vì theo Bento grid.
- `soi-path-*` từng dùng palette tối riêng và chưa có safe-area contract đầy đủ, dẫn tới dock/footer dễ chồng nội dung trên màn nhỏ.
- `dashboard.html` và `research-lab.html` có dữ liệu tốt nhưng hierarchy thị giác chưa phản ánh vai trò Command Center / Research Lab.

## Regression contracts

`tests/test_targeted_ui_remediation.py` khóa các invariants chính: full-width bảng tuần, bounded scroll, responsive recent grid, path safe area, light miss/special palette, dashboard glass hierarchy, Research Lab experiment pipeline, giữ nguyên polling script và tính idempotent của refinement layer.
