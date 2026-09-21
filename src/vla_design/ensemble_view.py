from __future__ import annotations

"""Hiển thị trọng số tổ hợp và XUẤT XỨ của chúng.

Gọi thẳng ``ensemble_utils.weights_provenance`` — không tự đọc tệp, không suy
xuất xứ bằng cách so trọng số với mặc định. Phép suy ấy nói SAI với một tệp
hoàn toàn lành: nó báo "tệp thiếu hoặc sai lược đồ" cho một tệp lược đồ 7 mang
đúng mặc định vì cổng thẩm định ĐÃ ĐO rồi từ chối đề bạt.

Ba xuất xứ, ba câu khác nhau, vì hai trong ba cho cùng một bộ trọng số hiển
thị. Không phân biệt thì người đọc không biết hệ thống đã đo rồi từ chối hay
chưa đo được gì.
"""

from pathlib import Path

from ensemble_utils import weights_provenance
from vla_design.blocks import card, esc, table
from vla_design.data_access import decimal_text

COMPONENT_LABEL = {
    "w_ml": "Học máy",
    "w_cau": "Cầu",
    "w_stat": "Thống kê",
    "w_active": "Cầu đang hoạt động",
    "w_stable": "Cầu ổn định",
}

ORIGIN_LABEL = {
    "da_hoc": ("Đã học và vượt cổng thẩm định ngoài mẫu", "success"),
    "bi_tu_choi": ("Mặc định — cổng đã đo và TỪ CHỐI đề bạt", "info"),
    "khong_co_ho_so": ("Mặc định — chưa có hồ sơ đề bạt", "neutral"),
}


def weights_card(data_dir: Path) -> str:
    """Thẻ trọng số cho cả hai chế độ, kèm lý do và số đo ngoài mẫu."""
    blocks: list[str] = []
    for mode, label in (("loto", "Lô tô"), ("de", "Đặc Biệt")):
        report = weights_provenance(Path(data_dir), mode)
        origin_text, tone = ORIGIN_LABEL.get(
            report.get("xuat_xu", ""), ("Không rõ xuất xứ", "danger")
        )
        rows = [
            (COMPONENT_LABEL.get(key, key), decimal_text(value, places=4))
            for key, value in report["weights"].items()
        ]
        tham = report.get("tham_dinh") or {}
        detail = ""
        if tham:
            logloss = tham.get("logloss_ngoai_mau") or {}
            detail = (
                '<dl class="vla-meta">'
                f'<div><dt>Số kỳ khớp</dt><dd>{esc(tham.get("so_ky_khop"))}</dd></div>'
                f'<div><dt>Số kỳ thẩm định</dt><dd>{esc(tham.get("so_ky_tham_dinh"))}</dd></div>'
                f'<div><dt>LogLoss mặc định</dt><dd>{decimal_text(logloss.get("mac_dinh"), places=6)}</dd></div>'
                f'<div><dt>LogLoss ứng viên</dt><dd>{decimal_text(logloss.get("ung_vien"), places=6)}</dd></div>'
                "</dl>"
            )
        reason = report.get("ly_do") or ""
        blocks.append(
            '<div class="vla-col-6">'
            + card(
                f"Trọng số — {label}",
                table(
                    (("thanhphan", "Thành phần"), ("trongso", "Trọng số")),
                    rows,
                    caption=f"Trọng số tổ hợp đang có hiệu lực cho {label}",
                    numeric=(1,),
                )
                + f'<p class="vla-origin"><span class="vla-badge vla-badge--{tone}">{esc(origin_text)}</span></p>'
                + (f'<p class="vla-card-note">{esc(reason)}</p>' if reason else "")
                + detail,
            )
            + "</div>"
        )
    return f'<div class="vla-grid">{"".join(blocks)}</div>'
