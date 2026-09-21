from __future__ import annotations

"""CSS của các thành phần: thẻ, KPI, bảng, trạng thái phản hồi.

Hai điểm đáng giải thích, cả hai đều là chỗ một design system thường đánh đổi
sai cho một sản phẩm dày dữ liệu:

**Bảng KHÔNG được thưa ra cho đẹp.** Mục 6.4 nói thẳng: bảng thống kê ưu tiên
so sánh chính xác và quét nhanh. Đệm ô ở đây là 6px/10px, không phải 16px như
một bảng CRM — mỗi pixel chiều cao dòng là một hàng số bị đẩy khỏi màn hình.

**Cuộn ngang nằm trong khung ``.vla-table-scroll``, không ở trang.** Mục X
phân biệt rõ hai thứ: cuộn ngang trong khung bảng là có chủ đích, còn trang
tràn ngang là lỗi.

Một điều tôi từng chú thích sai ở đây: rằng khung này "cần ``min-width: 0`` ở
mọi tổ tiên mới hoạt động". Đo bằng đột biến thì không đúng — bỏ ``min-width``
ở bốn tổ tiên, hay bỏ cả ``overflow-x`` của chính khung này, đều không làm
trang tràn ngang, vì ``<table>`` khai ``inline-size: 100%`` nên hộp của nó
không vượt khung chứa. Các khai báo ấy là phòng ngự cho trường hợp nội dung
rộng KHÔNG phải bảng.
"""


def component_css() -> str:
    """CSS cho thẻ, KPI, bảng và các trạng thái phản hồi."""
    return """
/* ================================= Thẻ ================================= */

.vla-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--vla-surface);
  border: 1px solid var(--vla-border);
  border-radius: var(--vla-radius-lg);
  box-shadow: var(--vla-shadow-sm);
  overflow: hidden;
}

/* `height: 100%` phía trên là thứ giữ cho các thẻ trong cùng một nhóm lưới
   cao bằng nhau — mục 5.2 cấm chiều cao lệch trong cùng nhóm thị giác. Không
   có nó, mỗi thẻ cao theo nội dung của nó và hàng thẻ trông như bị vỡ. */

.vla-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vla-space-12);
  padding: var(--vla-space-16) var(--vla-space-20);
  border-block-end: 1px solid var(--vla-border);
  flex: 0 0 auto;
}

.vla-card-title {
  margin: 0;
  font-size: var(--vla-font-card-title-size);
  line-height: var(--vla-font-card-title-line);
  font-weight: var(--vla-font-card-title-weight);
  color: var(--vla-text-primary);
}

.vla-card-body { padding: var(--vla-space-20); flex: 1 1 auto; min-width: 0; }
.vla-card-body > :first-child { margin-block-start: 0; }
.vla-card-body > :last-child { margin-block-end: 0; }

.vla-card-note {
  margin-block-start: var(--vla-space-12);
  font-size: var(--vla-font-support-size);
  color: var(--vla-text-muted);
}

.vla-card-body ul { padding-inline-start: var(--vla-space-20); margin-block: var(--vla-space-8); }
.vla-card-body li { margin-block-end: var(--vla-space-4); }

.vla-card-body code {
  padding: 1px 5px;
  border-radius: var(--vla-radius-sm);
  background: var(--vla-surface-secondary);
  border: 1px solid var(--vla-border);
  font-size: 0.875em;
}

/* ================================= KPI ================================= */

.vla-card--kpi { padding: var(--vla-space-20); }

.vla-kpi-label {
  margin: 0;
  font-size: var(--vla-font-label-size);
  line-height: var(--vla-font-label-line);
  font-weight: var(--vla-font-label-weight);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--vla-text-muted);
}

.vla-kpi-value {
  margin: var(--vla-space-8) 0 0;
  font-size: var(--vla-font-kpi-size);
  line-height: var(--vla-font-kpi-line);
  font-weight: var(--vla-font-kpi-weight);
  color: var(--vla-text-primary);
  letter-spacing: -0.02em;
}

.vla-kpi-note { margin: var(--vla-space-12) 0 0; }

/* ================================ Bảng ================================= */

/* Khung cuộn. `max-inline-size: 100%` cùng với min-width: 0 của tổ tiên là
   điều kiện để bảng rộng cuộn TRONG đây chứ không đẩy trang tràn ngang. */
.vla-table-scroll {
  max-inline-size: 100%;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  border: 1px solid var(--vla-border);
  border-radius: var(--vla-radius-md);
  background: var(--vla-surface);
}

.vla-table {
  inline-size: 100%;
  border-collapse: collapse;
  font-size: var(--vla-font-table-size);
  line-height: var(--vla-font-table-line);
}

.vla-table caption { text-align: start; }

/* Đầu bảng DÍNH: trên một bảng 4 212 hàng, cuộn xuống 200 hàng rồi không còn
   biết cột nào là cột nào. `position: sticky` cần nền ĐẶC, nếu không chữ của
   hàng bên dưới hiện xuyên qua nó. */
.vla-table thead th {
  position: sticky;
  inset-block-start: 0;
  z-index: 1;
  background: var(--vla-surface-secondary);
  padding: var(--vla-space-8) var(--vla-space-12);
  text-align: start;
  font-size: var(--vla-font-label-size);
  font-weight: 640;
  letter-spacing: 0.02em;
  color: var(--vla-text-secondary);
  white-space: nowrap;
  border-block-end: 1px solid var(--vla-border);
}

.vla-table td {
  padding: 6px var(--vla-space-12);
  border-block-end: 1px solid var(--vla-border);
  color: var(--vla-text-primary);
  white-space: nowrap;
}

.vla-table tbody tr:last-child td { border-block-end: 0; }

/* Sọc vằn dùng màu RẤT nhạt: đủ để mắt lần theo hàng, không đủ để cạnh tranh
   với màu ngữ nghĩa của ô dữ liệu. */
.vla-table tbody tr:nth-child(even) { background: color-mix(in srgb, var(--vla-surface-secondary) 55%, transparent); }

@supports not (background: color-mix(in srgb, red 50%, transparent)) {
  .vla-table tbody tr:nth-child(even) { background: var(--vla-surface-secondary); }
}

.vla-table tbody tr:hover { background: var(--vla-primary-soft); }

.vla-table td.vla-num, .vla-table th.vla-num { text-align: end; }

/* ========================= Trạng thái phản hồi ========================= */

/* Ba trạng thái này KHÔNG phải trang trí. Mục VIII cấm che lỗi tải dữ liệu
   bằng chỗ giữ chỗ bịa: không có dữ liệu thì nói không có, tải lỗi thì nói
   lỗi và cho đường phục hồi. */
.vla-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--vla-space-8);
  padding: var(--vla-space-40) var(--vla-space-20);
  text-align: center;
}

.vla-state-icon { color: var(--vla-text-muted); }
.vla-state-title { margin: 0; font-size: var(--vla-font-card-title-size); font-weight: 600; color: var(--vla-text-primary); }
.vla-state-text { margin: 0; font-size: var(--vla-font-body-sm-size); color: var(--vla-text-secondary); max-width: 52ch; }
.vla-state--error .vla-state-icon { color: var(--vla-danger-ink); }
.vla-state--error .vla-state-title { color: var(--vla-danger-ink); }

/* Khung xương khi đang tải. Chuyển động bị `prefers-reduced-motion` tắt qua
   quy tắc chung ở tầng nền, nên không cần khai lại ở đây. */
.vla-skeleton {
  border-radius: var(--vla-radius-sm);
  background: linear-gradient(
    90deg,
    var(--vla-surface-secondary) 25%,
    var(--vla-background-secondary) 37%,
    var(--vla-surface-secondary) 63%
  );
  background-size: 400% 100%;
  animation: vla-shimmer 1.4s ease-in-out infinite;
}

@keyframes vla-shimmer {
  from { background-position: 100% 50%; }
  to { background-position: 0 50%; }
}
"""
