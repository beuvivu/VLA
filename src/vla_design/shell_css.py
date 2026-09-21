from __future__ import annotations

"""CSS của App Shell: sidebar, topbar, breadcrumb, container, lưới 12 cột.

Ba quyết định đáng giải thích, vì cả ba đều là chỗ dễ làm sai:

**Sidebar dùng ``position: fixed`` chứ không phải một cột của lưới.** Cột lưới
sẽ cuộn cùng nội dung, nên trên một trang thống kê dài hai mươi nghìn pixel
thì điều hướng biến mất khỏi màn hình. Phần chừa chỗ cho nó là
``padding-inline-start`` của vùng nội dung, chỉ bật từ 1024px.

**Điện thoại dùng drawer có nền mờ, không dùng sidebar thu gọn.** Mục X cấm
điều hướng che nội dung vĩnh viễn. Một sidebar 72px luôn hiện trên màn 320px
là ăn 22% chiều ngang của mọi trang, mà các trang này là bảng số.

**Nhóm điều hướng là ``<details>``/``<summary>``, không phải div có onclick.**
Nó mở/đóng bằng bàn phím sẵn, trình đọc màn hình hiểu sẵn, và chạy được khi
JavaScript lỗi — ba thứ mà một div có ``onclick`` mất cả ba. Mục XII cấm
thẳng div bấm được.
"""


def shell_css() -> str:
    """CSS cho khung ứng dụng và các thành phần khung dùng."""
    return """
/* ============================ Khung ứng dụng ============================ */

.vla-app {
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--vla-background);
}

.vla-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 100vh;
  min-height: 100dvh;
}

@media (min-width: 1024px) {
  .vla-main { padding-inline-start: var(--vla-sidebar-w); }
}

/* `min-width: 0` ở đây là PHÒNG NGỰ, không phải chỗ chịu lực — và tôi đã chú
   thích sai điều này ở bản trước. Đo bằng đột biến trên chính trang xem thử:
   bỏ nó khỏi `.vla-main`, `.vla-content`, `.vla-container`, `.vla-grid > *`
   hay bỏ cả `overflow-x` của `.vla-table-scroll` đều KHÔNG làm trang tràn
   ngang, vì `<table>` khai `inline-size: 100%` nên hộp của nó không vượt khỏi
   khung chứa dù ô bên trong `nowrap`.

   Vẫn giữ, vì bất biến "phần tử con của flex/grid không được co nhỏ hơn nội
   dung" là thứ sẽ chịu lực ngay khi một trang dùng `<div>` rộng hoặc
   `<pre>` thay cho `<table>` — và phép kiểm tràn ngang CÓ bắt được trường hợp
   ấy: chèn một phần tử rộng 3000px thì cả bảy viewport đỏ. */
.vla-content { flex: 1 1 auto; min-width: 0; padding-block: var(--vla-space-24) var(--vla-space-48); }

.vla-container {
  width: 100%;
  max-width: var(--vla-page-max);
  margin-inline: auto;
  padding-inline: var(--vla-page-gutter);
  min-width: 0;
}

/* Trang ma trận và bảng lớn được dùng khung rộng hơn — mục 5.1 nói rõ không
   ép bảng thống kê vào khung hẹp. */
.vla-container--wide { max-width: var(--vla-page-max-wide); }

.vla-grid {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: var(--vla-space-20);
}

@media (min-width: 768px) {
  .vla-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (min-width: 1024px) {
  .vla-grid { grid-template-columns: repeat(12, minmax(0, 1fr)); gap: var(--vla-space-24); }
  .vla-col-3 { grid-column: span 3; }
  .vla-col-4 { grid-column: span 4; }
  .vla-col-5 { grid-column: span 5; }
  .vla-col-6 { grid-column: span 6; }
  .vla-col-7 { grid-column: span 7; }
  .vla-col-8 { grid-column: span 8; }
  .vla-col-9 { grid-column: span 9; }
  .vla-col-12 { grid-column: span 12; }
}

/* Hàng KPI có lưới RIÊNG, và đó là thiết kế mobile có chủ đích chứ không phải
   xếp máy móc. Đo trên ảnh chụp 375px: bốn thẻ KPI xếp dọc một cột chiếm
   khoảng 580px chiều cao để hiện BỐN con số — người đọc phải cuộn qua gần một
   màn hình rưỡi trước khi tới nội dung. Hai cột từ 380px đưa nó về hai hàng.

   Mục X cấm "áp layout máy tính một cách máy móc lên điện thoại", và một lưới
   một-cột cho mọi thứ chính là dạng máy móc đó. */
.vla-kpi-grid {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: var(--vla-space-12);
  margin-block-end: var(--vla-space-20);
}

/* Mốc 360px, không phải 380px. Mốc đầu tôi chọn là 380 và nó loại đúng 375px
   — chiều rộng "Mobile" trong bảng viewport của spec, tức chiều rộng điện
   thoại phổ biến nhất. Sai một mốc là mất nguyên hạng thiết bị. */
@media (min-width: 360px) {
  .vla-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* Bốn cột từ 1280px, KHÔNG phải 1024px. Đo trên Chromium: ở 1024px sidebar
   ăn 264px nên mỗi thẻ còn 159px, và "2026-09-21" ở 2rem XUỐNG HAI DÒNG —
   chiều cao thẻ nhảy 143px lên 181px, đúng thứ mục 5.2 cấm là chiều cao lệch
   trong cùng nhóm thị giác. Ở 1280px mỗi thẻ còn khoảng 237px và vừa một
   dòng.

   Phép đo đầu của tôi ở đây SAI THỨ CẦN ĐO: tôi kiểm `scrollWidth` và thấy
   "không tràn" rồi tưởng là ổn — nhưng con số không tràn vì nó XUỐNG DÒNG
   được. Phải đếm số dòng, không đo chiều rộng. */
@media (min-width: 1280px) {
  .vla-kpi-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--vla-space-20); }
}

.vla-kpi-grid > * { min-width: 0; }

/* Ràng buộc THẬT của việc xếp hai cột trên điện thoại không phải mốc màn hình
   mà là CHIỀU RỘNG CON SỐ. Đo ở 375px: trừ 32px lề và 12px khe thì mỗi thẻ
   còn 165px, trong khi "2026-09-21" ở 2rem chiếm khoảng 190px — tràn ô.
   Hạ xuống 1,5rem (24px, vẫn trong khoảng 24-36px mục 4.2 cho) thì còn khoảng
   142px và vừa. Đây là lý do thang chữ có sẵn mức `kpi-sm`. */
@media (max-width: 1279px) {
  .vla-kpi-grid .vla-kpi-value {
    font-size: var(--vla-font-kpi-sm-size);
    line-height: var(--vla-font-kpi-sm-line);
  }
}

/* Thẻ cùng một nhóm phải cao bằng nhau — mục 5.2 cấm chiều cao lệch trong
   cùng nhóm thị giác. `align-items: stretch` là mặc định của grid, nhưng thẻ
   phải tự giãn thì mới dùng được chỗ ấy. */
.vla-grid > * { min-width: 0; }

/* ================================ Sidebar =============================== */

.vla-sidebar {
  position: fixed;
  inset-block: 0;
  inset-inline-start: 0;
  z-index: 40;
  display: flex;
  flex-direction: column;
  width: var(--vla-sidebar-w);
  background: var(--vla-surface);
  border-inline-end: 1px solid var(--vla-border);
  transform: translateX(-100%);
  transition: transform var(--vla-motion-base) var(--vla-motion-ease-out);
  overflow: hidden;
}

[dir="rtl"] .vla-sidebar { transform: translateX(100%); }

.vla-sidebar[data-open="true"] { transform: translateX(0); box-shadow: var(--vla-shadow-lg); }

@media (min-width: 1024px) {
  .vla-sidebar { transform: translateX(0); box-shadow: none; }
}

.vla-sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--vla-space-12);
  height: var(--vla-topbar-h);
  padding-inline: var(--vla-space-20);
  border-block-end: 1px solid var(--vla-border);
  flex: 0 0 auto;
}

.vla-brand-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--vla-radius-sm);
  background: var(--vla-primary);
  color: var(--vla-on-primary);
  font-weight: 700;
  font-size: 0.8125rem;
  letter-spacing: 0.02em;
  flex: 0 0 auto;
}

.vla-brand-text { display: flex; flex-direction: column; min-width: 0; }
.vla-brand-name { font-size: 0.9375rem; font-weight: 640; line-height: 1.2; color: var(--vla-text-primary); }
.vla-brand-sub { font-size: var(--vla-font-support-size); color: var(--vla-text-muted); line-height: 1.3; }

.vla-sidebar-scroll {
  flex: 1 1 auto;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--vla-space-12) var(--vla-space-12) var(--vla-space-24);
}

.vla-nav-group { border: 0; margin-block-end: var(--vla-space-4); }

.vla-nav-group > summary {
  display: flex;
  align-items: center;
  gap: var(--vla-space-12);
  padding: var(--vla-space-8) var(--vla-space-12);
  border-radius: var(--vla-radius-sm);
  cursor: pointer;
  list-style: none;
  color: var(--vla-text-secondary);
  font-size: var(--vla-font-body-sm-size);
  font-weight: 560;
  transition: background var(--vla-motion-fast) var(--vla-motion-ease),
              color var(--vla-motion-fast) var(--vla-motion-ease);
}

.vla-nav-group > summary::-webkit-details-marker { display: none; }
.vla-nav-group > summary:hover { background: var(--vla-surface-secondary); color: var(--vla-text-primary); }

.vla-nav-group-label { flex: 1 1 auto; min-width: 0; }

.vla-nav-caret {
  flex: 0 0 auto;
  transition: transform var(--vla-motion-fast) var(--vla-motion-ease);
  color: var(--vla-text-muted);
}

.vla-nav-group[open] > summary > .vla-nav-caret { transform: rotate(90deg); }

.vla-nav-list { list-style: none; margin: var(--vla-space-4) 0 var(--vla-space-8); padding-inline-start: var(--vla-space-20); }

.vla-nav-link {
  /* `min-height` 40px là ngưỡng vùng chạm của mục X. Đo trên Chromium ở
     375px: chỉ dùng `padding` cho ra 39px — thiếu ĐÚNG một pixel, và đó là
     loại thiếu mà không ai thấy khi nhìn trang. */
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: var(--vla-space-8) var(--vla-space-12);
  border-radius: var(--vla-radius-sm);
  color: var(--vla-text-secondary);
  font-size: var(--vla-font-body-sm-size);
  text-decoration: none;
  transition: background var(--vla-motion-fast) var(--vla-motion-ease),
              color var(--vla-motion-fast) var(--vla-motion-ease);
}

.vla-nav-link:hover { background: var(--vla-surface-secondary); color: var(--vla-text-primary); }

/* Mục đang mở phải nhận ra được KHÔNG CHỈ bằng màu — mục 6.3 và XII đòi vậy.
   Nền nhạt là màu, dải bên trái là hình dạng, `font-weight` là độ đậm, và
   `aria-current` là ngữ nghĩa cho trình đọc màn hình. Bốn kênh độc lập. */
.vla-nav-link[aria-current="page"] {
  position: relative;
  background: var(--vla-primary-soft);
  color: var(--vla-primary);
  font-weight: 620;
}

.vla-nav-link[aria-current="page"]::before {
  content: "";
  position: absolute;
  inset-block: 20%;
  inset-inline-start: calc(-1 * var(--vla-space-12));
  width: 3px;
  border-radius: var(--vla-radius-pill);
  background: var(--vla-primary);
}

.vla-sidebar-foot {
  flex: 0 0 auto;
  padding: var(--vla-space-12) var(--vla-space-20);
  border-block-start: 1px solid var(--vla-border);
  font-size: var(--vla-font-support-size);
  color: var(--vla-text-muted);
}

.vla-backdrop {
  position: fixed;
  inset: 0;
  z-index: 30;
  background: rgba(10, 13, 24, 0.44);
  opacity: 0;
  visibility: hidden;
  transition: opacity var(--vla-motion-base) var(--vla-motion-ease),
              visibility var(--vla-motion-base) var(--vla-motion-ease);
}

.vla-backdrop[data-open="true"] { opacity: 1; visibility: visible; }

@media (min-width: 1024px) {
  .vla-backdrop { display: none; }
}

/* ================================ Topbar ================================ */

.vla-topbar {
  position: sticky;
  inset-block-start: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: var(--vla-space-12);
  height: var(--vla-topbar-h);
  padding-inline: var(--vla-page-gutter);
  background: var(--vla-surface-glass);
  backdrop-filter: blur(12px);
  border-block-end: 1px solid var(--vla-border);
  flex: 0 0 auto;
}

/* Không có `backdrop-filter` thì mặt kính thành trong suốt và chữ đè lên nội
   dung cuộn phía dưới. Rơi về màu đặc thay vì để nó hỏng. */
@supports not (backdrop-filter: blur(12px)) {
  .vla-topbar { background: var(--vla-surface); }
}

.vla-topbar-title { flex: 1 1 auto; min-width: 0; }

.vla-topbar-context {
  font-size: var(--vla-font-body-sm-size);
  font-weight: 600;
  color: var(--vla-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

.vla-topbar-actions { display: flex; align-items: center; gap: var(--vla-space-8); flex: 0 0 auto; }

.vla-menu-button { flex: 0 0 auto; }


/* ============================== Breadcrumb ============================== */

.vla-breadcrumb { margin-block-end: var(--vla-space-8); }
.vla-breadcrumb-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--vla-space-4);
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: var(--vla-font-support-size);
  color: var(--vla-text-muted);
}
.vla-breadcrumb-list a { color: var(--vla-text-secondary); text-decoration: none; }
.vla-breadcrumb-list a:hover { color: var(--vla-primary); text-decoration: underline; }
.vla-breadcrumb-sep { color: var(--vla-text-muted); }

/* ============================= Đầu trang =============================== */

.vla-page-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--vla-space-16);
  margin-block-end: var(--vla-space-24);
}

.vla-page-head-text { min-width: 0; flex: 1 1 320px; }

.vla-page-title {
  margin: 0;
  font-size: var(--vla-font-page-title-size);
  line-height: var(--vla-font-page-title-line);
  font-weight: var(--vla-font-page-title-weight);
  color: var(--vla-text-primary);
  letter-spacing: -0.01em;
}

.vla-page-sub {
  margin: var(--vla-space-4) 0 0;
  font-size: var(--vla-font-body-sm-size);
  color: var(--vla-text-secondary);
  max-width: 76ch;
}

.vla-page-actions { display: flex; flex-wrap: wrap; gap: var(--vla-space-8); }

/* =============================== Nút bấm =============================== */

.vla-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--vla-space-8);
  min-height: 40px;
  padding: 0 var(--vla-space-16);
  border: 1px solid transparent;
  border-radius: var(--vla-radius-sm);
  background: transparent;
  color: var(--vla-text-primary);
  font: inherit;
  font-size: var(--vla-font-body-sm-size);
  font-weight: 560;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--vla-motion-fast) var(--vla-motion-ease),
              border-color var(--vla-motion-fast) var(--vla-motion-ease),
              color var(--vla-motion-fast) var(--vla-motion-ease);
}

.vla-btn:disabled { opacity: 0.55; cursor: not-allowed; }

.vla-btn--primary { background: var(--vla-primary); color: var(--vla-on-primary); }
.vla-btn--primary:hover:not(:disabled) { background: var(--vla-primary-hover); }

.vla-btn--outline { border-color: var(--vla-border-strong); color: var(--vla-text-secondary); }
.vla-btn--outline:hover:not(:disabled) { background: var(--vla-surface-secondary); color: var(--vla-text-primary); }

/* Nút chỉ có icon: 40px là ngưỡng vùng chạm mục X đòi, và nó KHÔNG được nhỏ
   hơn chỉ vì nút không có chữ. */
.vla-btn--icon { width: 40px; min-height: 40px; padding: 0; border-color: var(--vla-border-strong); color: var(--vla-text-secondary); }
.vla-btn--icon:hover:not(:disabled) { background: var(--vla-surface-secondary); color: var(--vla-text-primary); }

.vla-icon { flex: 0 0 auto; display: block; }

/* ================================ Badge ================================= */

.vla-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--vla-space-4);
  padding: 2px var(--vla-space-8);
  border-radius: var(--vla-radius-pill);
  font-size: var(--vla-font-support-size);
  font-weight: 600;
  white-space: nowrap;
}

.vla-badge--neutral { background: var(--vla-surface-secondary); color: var(--vla-text-secondary); }
.vla-badge--success { background: var(--vla-success-soft); color: var(--vla-success-ink); }
.vla-badge--warning { background: var(--vla-warning-soft); color: var(--vla-warning-ink); }
.vla-badge--danger  { background: var(--vla-danger-soft);  color: var(--vla-danger-ink); }
.vla-badge--info    { background: var(--vla-info-soft);    color: var(--vla-info-ink); }
.vla-badge--accent  { background: var(--vla-accent-soft);  color: var(--vla-accent-ink); }

/* ======================== Hiện/ẩn theo kích thước ====================== */

/* Đặt Ở CUỐI, và dùng HAI lớp, vì cả hai đều cần thiết. Bản trước khai
   `.vla-menu-button { display: none }` trong khối `@media` ở phần Topbar, tức
   TRƯỚC `.vla-btn { display: inline-flex }`. Cùng độ đặc hiệu một lớp thì
   luật sau thắng, nên nút ba gạch vẫn hiện ở 1440px — hai đường điều hướng
   cùng lúc. Trình duyệt tìm ra, phép đọc CSS thì không. */
@media (min-width: 1024px) {
  .vla-btn.vla-menu-button { display: none; }
}

/* ============================ Chọn chủ đề ============================== */

/* Ba nhãn, MỘT nút. Chỉ nhãn khớp `data-theme-state` hiện ra, nên không cần
   viết chữ vào DOM bằng JavaScript — tránh luôn `.innerHTML` mà kho cấm. */
.vla-theme-label { display: none; }
[data-theme-state="system"] .vla-theme-label--system,
[data-theme-state="light"] .vla-theme-label--light,
[data-theme-state="dark"] .vla-theme-label--dark { display: block; }
"""
