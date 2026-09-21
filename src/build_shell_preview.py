from __future__ import annotations

"""Dựng trang XEM THỬ khung ứng dụng — công cụ QA, không phải trang sản phẩm.

Vì sao cần: PHASE 4 giao khung chứ chưa giao trang nào, nên không có gì để mở
bằng trình duyệt mà kiểm. Không có trang thật thì mọi phát biểu về responsive,
về nút đổi chủ đề, về drawer trên điện thoại đều là suy luận từ CSS — mà mục
X của spec nói rõ "do not rely on CSS media queries alone".

Trang này ghi ra ``docs/_shell-preview.html``. Tiền tố gạch dưới là cố ý: đây
là hiện vật QA, và ``docs/.nojekyll`` bảo đảm GitHub Pages vẫn phục vụ tệp bắt
đầu bằng gạch dưới thay vì bỏ qua nó.

Số liệu trên trang lấy từ ``data/health.json`` thật. Không bịa số để trang
trông đầy — mục XVIII.2 cấm, và một con số bịa trong trang QA là con số sẽ bị
ai đó tin.
"""

import argparse
import json
from pathlib import Path

from vla_design.assets import write_assets
from vla_design.navigation import NAV
from vla_design.shell import Crumb, Page, render_page

PREVIEW_NAME = "_shell-preview.html"


def _health(data_dir: Path) -> dict:
    try:
        blob = json.loads((Path(data_dir) / "health.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return blob if isinstance(blob, dict) else {}


def _kpi(label: str, value: str, note: str, tone: str) -> str:
    return (
        "<article>"
        '<div class="vla-card vla-card--kpi">'
        f'<p class="vla-kpi-label">{label}</p>'
        f'<p class="vla-kpi-value vla-num">{value}</p>'
        f'<p class="vla-kpi-note"><span class="vla-badge vla-badge--{tone}">{note}</span></p>'
        "</div></article>"
    )


def build(docs_dir: Path, data_dir: Path) -> Path:
    write_assets(docs_dir)
    health = _health(data_dir)

    rows = int(health.get("row_count") or 0)
    missing = int(health.get("missing_count") or 0)
    kpis = "".join(
        (
            _kpi("Số kỳ trong kho", f"{rows:,}".replace(",", "."), "dữ liệu thật", "info"),
            _kpi("Kỳ mới nhất", str(health.get("latest_date") or "—"), "từ health.json", "neutral"),
            _kpi("Kỳ đầu tiên", str(health.get("first_date") or "—"), "từ health.json", "neutral"),
            _kpi(
                "Ngày thiếu",
                str(missing),
                "liên tục" if missing == 0 else "có lỗ hổng",
                "success" if missing == 0 else "danger",
            ),
        )
    )

    groups = "".join(
        f"<li><strong>{group.label}</strong> — {len(group.items)} trang</li>"
        for group in NAV
    )
    total = sum(len(group.items) for group in NAV)

    content = f"""
<div class="vla-kpi-grid">{kpis}</div>
<div class="vla-grid">
  <section class="vla-col-7">
    <div class="vla-card">
      <header class="vla-card-head"><h2 class="vla-card-title">Khung ứng dụng đang kiểm</h2></header>
      <div class="vla-card-body">
        <p>Trang này tồn tại để kiểm khung bằng trình duyệt thật, không phải để
        đọc số. Những thứ cần thử tay trên đây:</p>
        <ul>
          <li>Nút đổi chủ đề xoay ba trạng thái: theo hệ thống, sáng, tối.</li>
          <li>Dưới 1024px, nút ba gạch mở drawer; nền mờ và phím Esc đóng nó.</li>
          <li>Phím Tab từ đầu trang phải gặp liên kết bỏ qua điều hướng trước tiên.</li>
          <li>Nhóm điều hướng mở/đóng được bằng Enter và Space, không cần chuột.</li>
          <li>Mục đang mở có nền, có dải bên trái, có chữ đậm hơn, và mang
          <code>aria-current="page"</code> — bốn kênh, không chỉ màu.</li>
        </ul>
      </div>
    </div>
  </section>
  <section class="vla-col-5">
    <div class="vla-card">
      <header class="vla-card-head"><h2 class="vla-card-title">Điều hướng</h2></header>
      <div class="vla-card-body">
        <p>{len(NAV)} nhóm, {total} trang trong sidebar.</p>
        <ul>{groups}</ul>
      </div>
    </div>
  </section>
  <section class="vla-col-12">
    <div class="vla-card">
      <header class="vla-card-head"><h2 class="vla-card-title">Bảng rộng — cuộn ngang phải nằm TRONG bảng</h2></header>
      <div class="vla-card-body">
        <div class="vla-table-scroll">
          <table class="vla-table">
            <caption class="vla-visually-hidden">Bảng thử tràn ngang</caption>
            <thead><tr>{"".join(f'<th scope="col">Cột {i:02d}</th>' for i in range(1, 25))}</tr></thead>
            <tbody>{"".join('<tr>' + "".join(f'<td class="vla-num">{(r * 24 + c) % 100:02d}</td>' for c in range(24)) + '</tr>' for r in range(6))}</tbody>
          </table>
        </div>
        <p class="vla-card-note">Bảng này rộng hơn màn hình một cách có chủ đích.
        Cuộn ngang phải xuất hiện trong khung bảng; trang KHÔNG được tràn ngang.</p>
      </div>
    </div>
  </section>
</div>
"""

    page = Page(
        nav_key="bang-dieu-khien",
        title="Kiểm khung ứng dụng",
        subtitle=(
            "Hiện vật QA của PHASE 4. Số liệu lấy từ data/health.json thật; "
            "bảng phía dưới là bảng thử tràn ngang."
        ),
        crumbs=(Crumb("Kiểm thử"),),
    )
    out = Path(docs_dir) / PREVIEW_NAME
    out.write_text(render_page(page, content), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Dựng trang xem thử khung ứng dụng.")
    ap.add_argument("--docs-dir", default="docs")
    ap.add_argument("--data-dir", default="data")
    args = ap.parse_args()
    out = build(Path(args.docs_dir), Path(args.data_dir))
    print(f"[OK] trang xem thử khung -> {out}")


if __name__ == "__main__":
    main()
