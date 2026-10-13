# Hoàn thiện chủ đề màu, biểu tượng và tìm kiếm

## Mục tiêu và phạm vi

Hoàn tất giao diện Crafto đang triển khai, đồng thời thực hiện yêu cầu bổ sung của chủ dự án ngày 26-09-2026: Dark/Light trên toàn bộ trang, SVG chuẩn tương đương Nexlink và hai tìm kiếm độc lập. Chủ dự án đã ủy quyền tự quyết các bước thiết kế, kiểm thử, PR và xuất bản. Không thay đổi tính toán, dữ liệu lịch sử, mô hình hoặc hợp đồng chọn số.

## Thiết kế

1. Theme: một runtime nhỏ `src/assets/app-theme.js` chạy đồng bộ trong head trước stylesheet, sau meta CSP. Nó đọc `app-theme`, chấp nhận auto/light/dark, đặt `.dark` theo màu thực tế và giữ `data-ui-theme` cho lựa chọn tường minh. Không có lựa chọn thì theo OS và lắng nghe OS thay đổi. Nút Header đảo trực tiếp sáng/tối thực tế, aria-pressed và nhãn phản ánh đúng; lưu lựa chọn và đồng bộ tab khác. Storage hỏng không chặn giao diện. Một initializer duy nhất, không ghi HTML từ chuỗi.
2. CSS: gỡ light pin trên body; mọi nền/chữ/viền/control/card/modal lấy token dùng chung. Các CSS riêng chuyển alias sang token. `.dark` và lựa chọn `data-ui-theme` cùng kích hoạt dark; CSS media là fallback khi JS tắt. Giữ logic thang số nháy và màu ngữ nghĩa, đo contrast chữ ít nhất 4.5:1, ô có về nổi rõ so với ô trống nhưng không trắng lóa trên dark.
3. Icons: Nexlink thực tế dùng Flaticon và có Lucide; dùng SVG Lucide chính thức, pin phiên bản nguồn và giữ giấy phép. `icon_svg` giữ API và khóa SITE_NAV, đổi viewBox 24, cỡ20, stroke2, currentColor. Header/rail/panel gồm cả menu, search, theme, fullscreen đều cùng bộ; active/hover Indigo #4F46E5, dark có sắc chữ sáng đạt contrast. Không dùng CDN, không tải icon font.
4. Global search: dialog riêng trước app-main; `app-global-search`, input `app-global-search-input`. Tất cả href SITE_NAV, SITE_SEARCH_EXTRAS (bản máy tính) và section trang chủ, dedup href, nhóm + nhãn, không dấu. Ctrl/Cmd+K và Header mở dialog mà không mở/đổi/filter Sidebar. ↑/↓/Home/End chọn, Enter điều hướng, Escape/backdrop/close đóng, focus trả về nút đã mở; focus được giữ trong dialog. Empty state và số kết quả có aria-live. Kết quả là link thật, không thực thi truy vấn.
5. Sidebar: `app-sidebar-filter` và `app-sidebar-filter-empty`; chỉ thu hẹp link của nhóm đang hiển thị. Đổi nhóm reset filter; tìm global không đụng filter. Giữ menu responsive, inert và đóng bằng Escape.

## Kiểm chứng và triển khai

Test hành vi runtime theme và hai tìm kiếm bằng JSDOM; test markup/idempotence/coverage link/SVG; đo contrast và kiểm tra source token, toàn bộ Python suite + frontend suite + lint. Dựng lại trang từ nguồn; so bảng/data JSON/number hooks với bản trước. Kiểm tra trực tiếp bản public sau CI và deploy. Không khẳng định kiểm chứng trên thiết bị/viewport không thực sự chạy. Giữ 80px rail/header, 240px panel overlay, bo menu8px; CSS vanilla và local assets.
