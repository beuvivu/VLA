# Kiểm kê thành phần

| Thành phần | Nơi định nghĩa | Ghi chú |
|---|---|---|
| Token màu / chữ / khoảng cách | `vla_design/tokens.py` | Nguồn duy nhất; CSS sinh ra từ đây |
| Hợp đồng tương phản | `tokens.CONTRAST_CONTRACT` | DỮ LIỆU, phép kiểm tính lại chứ không đọc lại |
| CSS nền tảng | `vla_design/stylesheet.py` | Reset, biến, focus, reduced-motion, skip link |
| CSS khung | `vla_design/shell_css.py` | Sidebar, topbar, breadcrumb, lưới 12 cột, nút, badge |
| CSS thành phần | `vla_design/component_css.py` | Thẻ, KPI, bảng, trạng thái, cảnh báo, `<dl>` siêu dữ liệu |
| App Shell | `vla_design/shell.py` | `render_page()` — một hàm cho cả 29 trang |
| Điều hướng | `vla_design/navigation.py` | 7 nhóm / 29 trang; quy tắc "Đặc Biệt" áp ở đây |
| Icon | `vla_design/icons.py` | 21 hình SVG, khung 24×24, nét 1,75, `currentColor` |
| Khối HTML | `vla_design/blocks.py` | `card`, `kpi`, `table`, `empty_state`, `error_state`, `disclaimer` |
| Truy cập dữ liệu | `vla_design/data_access.py` | Ba trạng thái `ok`/`empty`/`error`; fail-closed |
| Hiển thị trọng số | `vla_design/ensemble_view.py` | Gọi `weights_provenance`, không tự suy xuất xứ |
| JavaScript khung | `vla_design/assets/vla-shell.js` | Chủ đề + drawer; không dùng DOM sink |
| Trang | `vla_pages/*.py` | overview (4), results (2), loto (5), special (8), models (10) |
| Trình dựng | `src/build_site.py` | Một lệnh dựng cả 29 trang |

## Ba trạng thái dữ liệu — điểm chính của tầng truy cập

| Trạng thái | Nghĩa | Hiển thị |
|---|---|---|
| `ok` | Có dữ liệu | Bảng/thẻ bình thường |
| `empty` | Tệp đọc được nhưng rỗng | Trạng thái rỗng, nêu nguồn |
| `error` | Thiếu tệp, hỏng, hoặc sai kiểu | Trạng thái LỖI, nêu lý do và nguồn |

Phân biệt `empty` với `error` là lý do tầng này tồn tại. Gộp hai thứ lại thì
một đường ống hỏng trông y như một ngày chưa có số liệu, và không ai đi sửa.
