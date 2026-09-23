# Báo cáo: khung ứng dụng hai cấp

Phần này thi hành **chỉ thị bổ sung** — khung ứng dụng toàn cục theo trang
`pages/blog.html` của NexLink. Phần nội dung bên trong từng trang **không bị
đụng tới**, đúng yêu cầu đóng băng nội dung.

## 1. Điều hướng

Hai cấp, dựng từ `ui_theme.SITE_NAV` — **7 nhóm, 32 mục**, tất cả trỏ tới
trang có thật trong `docs/`. Không nhóm rỗng, không liên kết chết, không mục
bịa. `test_every_navigation_target_is_a_real_page` canh điều đó.

* **Cấp một** (`aside.app-rail`, 80px): một nút cho mỗi nhóm, `role="tab"`,
  điều hướng bằng phím mũi tên, nhãn ngắn dưới biểu tượng.
* **Cấp hai** (`div.app-panel`, 240px / 220px ở ≤1024): danh sách mục của
  nhóm đang chọn, `role="tabpanel"`, mục của trang hiện tại mang
  `aria-current="page"`.

Biểu tượng lấy từ chính ký tự đã có trong `SITE_NAV`. Không thêm phông icon:
CSP đặt `font-src 'self'` và kho không tự host được phông icon nào.

## 2. Thanh trên

`header.app-header`, cao 80px, `padding-left` 80px, viền dưới 1px — đúng số
đo. Chứa: thương hiệu, nút thu/mở, đường dẫn (nhóm / trang), nút tìm, nút đổi
chế độ màu.

**Không có** thông báo giả, hồ sơ người dùng giả hay mục CRM. VLA không có hệ
đăng nhập và không có luồng sự kiện để đổ vào chuông thông báo, nên hai thứ ấy
không được dựng. Mọi điều khiển đã dựng đều chạy thật.

## 3. Thu / mở

Nút trong thanh trên điều khiển dải chi tiết. Trạng thái ghi vào
`localStorage` và khôi phục khi sang trang.

Ở màn hẹp **luôn bắt đầu ở trạng thái đóng**, kể cả khi lần trước để mở: mở
sẵn một tấm phủ toàn màn ngay khi vừa vào trang là chặn đúng thứ người đọc vừa
bấm vào.

Mở dải chi tiết **không làm nội dung xếp lại** — `margin-left` của vùng nội
dung giữ nguyên. Đây là hành vi đo được của trang tham chiếu, và
`test_the_detail_panel_overlays_the_content_instead_of_pushing_it` khoá nó
lại.

## 4. Tìm chức năng

Lọc trên chính 32 mục điều hướng. Mỗi kết quả là một trang tồn tại; không
khớp gì thì báo rõ thay vì im lặng. `test_the_search_only_offers_pages_that_exist`
kiểm cả hai vế.

## 5. Chế độ màu

**Ba** trạng thái: theo hệ → sáng → tối. Trạng thái "theo hệ" **không** đặt
`data-ui-theme`; đặt vào là đè mất `prefers-color-scheme` và người dùng mất
khả năng đi theo cài đặt máy.

## 6. Trang đã chuyển sang khung mới

**29/29**. Khung được bọc ở **một chỗ duy nhất**, `page_output.write_page` —
đường đi chung của mọi trình dựng. Không chép khung vào từng trình dựng, nên
chúng không thể trôi khỏi nhau.

Dock nổi ở chân trang đã gỡ khỏi cả 29 trang: để lại thì hai bộ điều hướng
cùng tồn tại và cùng đòi một chỗ.

## 7. Nội dung bên trong: không đụng

`app_shell.wrap_page` chỉ **bọc**. Nội dung đi nguyên vẹn vào
`<main class="app-main">`. Không bảng nào bị xếp lại, không thẻ nào bị gộp
hay tách, không ma trận thống kê nào đổi bố cục.

## 8. QA đã chạy

* 8 trang × 9 bề ngang (1920/1440/1366/1024/768/430/390/375/320) = **72
  trường hợp**: 0 tràn ngang, 0 chồng lấn thanh trên / dải / nội dung.
* Lỗi console duy nhất là CORS của `file://` (phông và `live.json`) — hiện
  vật của việc mở tệp cục bộ, không có qua https.
* **1873 phép kiểm xanh**, 4 kịch bản chốt phát hành xanh.
* Cảm ứng ở 390px: **mọi** liên kết trong menu đều chạm được. Đây là bài học
  của dock cũ (từng đo 0/9 chạm được) và nó được chuyển thành phép kiểm mới.

## 9. Bộ kiểm co lại lặng lẽ — đã phát hiện và sửa

Gỡ dock làm **175 phép kiểm biến mất không một tiếng động**. Nguyên nhân:
`test_ui_redesign.py` có `DOCK_PAGES = [p for p in PAGES if "dock-inner" in …]`
— danh sách **tự chọn phạm vi của chính nó**. Dock đi thì danh sách rỗng, bảy
phép kiểm chạy qua tập rỗng, và pytest báo xanh.

Đã gỡ danh sách ấy và thay bằng phép kiểm quét **mọi** trang xuất bản, nên tập
của nó không thể tự rỗng. Tổng cộng 10 phép kiểm dock được thay bằng 38 phép
kiểm khung mới, mỗi cái đã thử bằng đột biến.

## 10. Còn lại

* **Phông `Instrument Sans` / `Plus Jakarta Sans` chưa có.** CSP đặt
  `font-src 'self'`; proxy không tải được tệp phông về để tự host. Lấy qua
  runner Actions rồi commit kèm giấy phép là làm được, chưa làm.
* **Nền Crafto cho `index` / `landing`**: hiện bảng màu Crafto đang dùng
  **toàn cục**. Chỉ thị yêu cầu thu hẹp nó về riêng hai trang ấy và để NexLink
  cầm phần còn lại. Chưa làm.
* **Chuyển động chữ "Vietnam Lottery Analysis"**: chuỗi này **không tồn tại
  trong kho** — đã tìm trên toàn bộ mã nguồn và trang xuất bản. Không có gì để
  "giữ nguyên"; phải dựng mới. Chưa làm.
* 14 trang thống kê vẫn dùng `.innerHTML` (nợ có từ trước, ghi ở `CLAUDE.md`).
